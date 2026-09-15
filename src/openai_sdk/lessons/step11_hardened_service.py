import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agents import Agent, RunState, Runner, ToolApprovalItem, function_tool

load_dotenv()

# Set this in .env alongside OPENAI_API_KEY for real use. Left un-set here
# on purpose - this file never writes to .env itself, and if it's missing
# the API is unusable rather than silently open (fail closed, not open).
API_KEY = os.environ.get("AGENT_API_KEY")

DB_PATH = "approvals.db"


@function_tool
def check_disk_usage(hostname: str) -> str:
    """Check disk usage percentage on a host. Read-only, no approval needed.

    Args:
        hostname: The hostname to check.
    """
    return f"{hostname} disk usage: 92%"


@function_tool(needs_approval=True)
def restart_service(hostname: str, service_name: str) -> str:
    """Restart a service on a host. This is a DESTRUCTIVE action.

    Args:
        hostname: The host the service runs on.
        service_name: The name of the service to restart.
    """
    return f"Restarted '{service_name}' on {hostname}."


agent = Agent(
    name="IT Assistant",
    instructions="You are an IT infrastructure assistant with access to real tools.",
    model="gpt-5.1",
    tools=[check_disk_usage, restart_service],
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Unlike Step 10's PENDING dict, this table survives a process restart -
    # a run parked mid-approval is recoverable by request_id from disk.
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pending_approvals ("
        "request_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()
    yield


app = FastAPI(lifespan=lifespan, dependencies=[Depends(require_api_key)])


def _save_pending(request_id: str, state: RunState) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO pending_approvals (request_id, state_json, created_at) VALUES (?, ?, ?)",
        (request_id, state.to_string(), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


async def _pop_pending(request_id: str) -> RunState:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT state_json FROM pending_approvals WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row is not None:
        conn.execute("DELETE FROM pending_approvals WHERE request_id = ?", (request_id,))
        conn.commit()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown or already-resolved request_id")
    return await RunState.from_string(agent, row[0])


class ChatRequest(BaseModel):
    message: str


class PendingAction(BaseModel):
    call_id: str
    tool_name: str
    arguments: str


class ChatResponse(BaseModel):
    status: str  # "done" or "pending_approval"
    reply: str | None = None
    request_id: str | None = None
    actions: list[PendingAction] | None = None


def _actions_for(items: list[ToolApprovalItem]) -> list[PendingAction]:
    return [
        PendingAction(call_id=i.call_id, tool_name=i.tool_name, arguments=i.arguments)
        for i in items
    ]


async def _settle(result) -> ChatResponse:
    if result.interruptions:
        request_id = uuid.uuid4().hex
        _save_pending(request_id, result.to_state())
        return ChatResponse(
            status="pending_approval",
            request_id=request_id,
            actions=_actions_for(result.interruptions),
        )
    return ChatResponse(status="done", reply=result.final_output)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    result = await Runner.run(agent, req.message)
    return await _settle(result)


class ApproveRequest(BaseModel):
    request_id: str
    decisions: dict[str, bool]  # call_id -> approve?; anything omitted is rejected


@app.post("/approve", response_model=ChatResponse)
async def approve(req: ApproveRequest) -> ChatResponse:
    state = await _pop_pending(req.request_id)
    for item in state.get_interruptions():
        if req.decisions.get(item.call_id, False):
            state.approve(item)
        else:
            state.reject(item)

    result = await Runner.run(agent, state)
    return await _settle(result)
