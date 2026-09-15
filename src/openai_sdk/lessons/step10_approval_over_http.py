import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents import Agent, RunState, Runner, ToolApprovalItem, function_tool

load_dotenv()


@function_tool
def check_disk_usage(hostname: str) -> str:
    """Check disk usage percentage on a host. Read-only, no approval needed.

    Args:
        hostname: The hostname to check.
    """
    return f"{hostname} disk usage: 92%"


# needs_approval=True: whatever the model decides, this call always pauses
# the run and comes back as an interruption instead of executing.
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

app = FastAPI()

# A run that's paused on an approval has to wait somewhere between the two
# HTTP requests (the /chat that triggered it and the later /approve). This
# in-memory dict is that "somewhere" - fine for one process/demo, but it
# means pending approvals are lost on restart; a real deployment would
# persist RunState (it's serializable) in Redis/a DB instead.
PENDING: dict[str, dict] = {}


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
    """Turn a RunResult into an HTTP response, parking it if it needs approval."""
    if result.interruptions:
        request_id = uuid.uuid4().hex
        PENDING[request_id] = {"state": result.to_state(), "items": result.interruptions}
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
    # call_id -> True (approve) / False (reject). Any call_id left out is
    # rejected by default - fail closed, not open.
    decisions: dict[str, bool]


@app.post("/approve", response_model=ChatResponse)
async def approve(req: ApproveRequest) -> ChatResponse:
    pending = PENDING.pop(req.request_id, None)
    if pending is None:
        raise HTTPException(status_code=404, detail="Unknown or already-resolved request_id")

    state: RunState = pending["state"]
    for item in pending["items"]:
        if req.decisions.get(item.call_id, False):
            state.approve(item)
        else:
            state.reject(item)

    result = await Runner.run(agent, state)
    return await _settle(result)
