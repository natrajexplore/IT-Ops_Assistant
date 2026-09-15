import os
import sys
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis

from agents import Agent, RunState, Runner, ToolApprovalItem, function_tool, trace

load_dotenv()


@dataclass(frozen=True)
class Settings:
    agent_api_key: str
    redis_url: str
    rate_limit: int = 5
    rate_window: int = 10       # seconds
    approval_ttl: int = 3600    # seconds

    @classmethod
    def from_env(cls) -> "Settings":
        # Fail fast at startup with a clear message, not a confusing 401/500
        # on the first request - every other config value below has a
        # sane default; secrets never do.
        api_key = os.environ.get("AGENT_API_KEY")
        redis_url = os.environ.get("REDIS_URL")
        missing = [
            name
            for name, val in [("AGENT_API_KEY", api_key), ("REDIS_URL", redis_url)]
            if not val
        ]
        if missing:
            sys.exit(f"Missing required environment variable(s): {', '.join(missing)}")
        return cls(
            agent_api_key=api_key,
            redis_url=redis_url,
            rate_limit=int(os.environ.get("RATE_LIMIT", 5)),
            rate_window=int(os.environ.get("RATE_WINDOW", 10)),
            approval_ttl=int(os.environ.get("APPROVAL_TTL", 3600)),
        )


settings = Settings.from_env()
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
    if x_api_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")
    return x_api_key


async def enforce_rate_limit(api_key: str = Depends(require_api_key)) -> None:
    key = f"ratelimit:{api_key}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.rate_window)
    if count > settings.rate_limit:
        ttl = await redis.ttl(key)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit} requests per {settings.rate_window}s",
            headers={"Retry-After": str(max(ttl, 0))},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    # redis_url carries the password (redis://:password@host:port) - a bad
    # or missing password fails here at startup via .ping(), same fail-fast
    # philosophy as the missing-env-var check above, not on the first request.
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    yield
    await redis.aclose()


app = FastAPI(lifespan=lifespan, dependencies=[Depends(enforce_rate_limit)])


async def _save_pending(request_id: str, state: RunState) -> None:
    await redis.set(f"pending:{request_id}", state.to_string(), ex=settings.approval_ttl)


async def _pop_pending(request_id: str) -> RunState:
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
    state = await _pop_pending(req.request_id)
    for item in state.get_interruptions():
        if req.decisions.get(item.call_id, False):
            state.approve(item)
        else:
            state.reject(item)

    with trace(workflow_name="IT Assistant Chat", group_id=req.request_id):
        result = await Runner.run(agent, state)
    return await _settle(result, req.request_id)
