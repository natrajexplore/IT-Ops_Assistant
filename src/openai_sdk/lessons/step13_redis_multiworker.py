import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis

from agents import Agent, RunState, Runner, ToolApprovalItem, function_tool, trace

load_dotenv()

API_KEY = os.environ.get("AGENT_API_KEY")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

RATE_LIMIT = 5       # requests
RATE_WINDOW = 10     # seconds
APPROVAL_TTL = 3600  # seconds a pending approval is kept before it's considered abandoned

redis: Redis | None = None


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


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")
    return x_api_key


async def enforce_rate_limit(api_key: str = Depends(require_api_key)) -> None:
    # INCR+EXPIRE on Redis is atomic per-command and shared by every worker
    # process hitting the same Redis instance - unlike Step 12's Python dict,
    # which each worker process would keep separately, silently multiplying
    # the effective limit by the number of workers.
    key = f"ratelimit:{api_key}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, RATE_WINDOW)
    if count > RATE_LIMIT:
        ttl = await redis.ttl(key)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {RATE_LIMIT} requests per {RATE_WINDOW}s",
            headers={"Retry-After": str(max(ttl, 0))},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    await redis.ping()
    yield
    await redis.aclose()


app = FastAPI(lifespan=lifespan, dependencies=[Depends(enforce_rate_limit)])


async def _save_pending(request_id: str, state: RunState) -> None:
    await redis.set(f"pending:{request_id}", state.to_string(), ex=APPROVAL_TTL)


async def _pop_pending(request_id: str) -> RunState:
    # GETDEL is one atomic Redis command: whichever worker process handles
    # the /approve call gets the value and deletes it in the same step, so
    # two workers racing on the same request_id can't both resume it.
    state_json = await redis.getdel(f"pending:{request_id}")
    if state_json is None:
        raise HTTPException(status_code=404, detail="Unknown or already-resolved request_id")
    return await RunState.from_string(agent, state_json)


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
    worker_pid: int = os.getpid()


def _actions_for(items: list[ToolApprovalItem]) -> list[PendingAction]:
    return [
        PendingAction(call_id=i.call_id, tool_name=i.tool_name, arguments=i.arguments)
        for i in items
    ]


async def _settle(result, request_id: str) -> ChatResponse:
    if result.interruptions:
        await _save_pending(request_id, result.to_state())
        return ChatResponse(
            status="pending_approval",
            request_id=request_id,
            actions=_actions_for(result.interruptions),
        )
    return ChatResponse(status="done", reply=result.final_output, request_id=request_id)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    request_id = uuid.uuid4().hex
    with trace(workflow_name="IT Assistant Chat", group_id=request_id):
        result = await Runner.run(agent, req.message)
    return await _settle(result, request_id)


class ApproveRequest(BaseModel):
    request_id: str
    decisions: dict[str, bool]


@app.post("/approve", response_model=ChatResponse)
async def approve(req: ApproveRequest) -> ChatResponse:
    # Whichever of the N worker processes receives this HTTP request, it did
    # NOT necessarily receive the original /chat call - it recovers the run
    # from Redis, not from any state kept in its own process memory.
    state = await _pop_pending(req.request_id)
    for item in state.get_interruptions():
        if req.decisions.get(item.call_id, False):
            state.approve(item)
        else:
            state.reject(item)

    with trace(workflow_name="IT Assistant Chat", group_id=req.request_id):
        result = await Runner.run(agent, state)
    return await _settle(result, req.request_id)
