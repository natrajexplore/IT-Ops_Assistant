from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
    SQLiteSession,
    input_guardrail,
)

load_dotenv()


class RiskCheck(BaseModel):
    is_high_risk: bool
    reasoning: str


risk_classifier_agent = Agent(
    name="Risk Classifier",
    instructions=(
        "Classify whether the user's request would cause a destructive or "
        "high-impact change to production infrastructure (restarting/stopping "
        "services, deleting data, changing configs on prod). "
        "Read-only checks (ping, disk usage, logs) are NOT high risk."
    ),
    model="gpt-5.1",
    output_type=RiskCheck,
)


@input_guardrail
async def high_risk_guardrail(
    ctx: RunContextWrapper[None], agent: Agent, user_input: str | list
) -> GuardrailFunctionOutput:
    result = await Runner.run(risk_classifier_agent, user_input, context=ctx.context)
    risk: RiskCheck = result.final_output
    return GuardrailFunctionOutput(output_info=risk, tripwire_triggered=risk.is_high_risk)


# Built once at startup, not per-request - the whole point of a service
# instead of a script is that the agent definition is paid for once and
# every request just reuses it.
agent: Agent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    agent = Agent(
        name="IT Assistant",
        instructions="You are a concise assistant for an IT infrastructure team.",
        model="gpt-5.1",
        input_guardrails=[high_risk_guardrail],
    )
    yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    blocked: bool = False


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # session_id is the multi-tenant key: every caller with a different
    # session_id gets independent conversation memory, all backed by the
    # same on-disk SQLite file.
    session = SQLiteSession(session_id=req.session_id, db_path="sessions.db")
    try:
        result = await Runner.run(agent, req.message, session=session)
        return ChatResponse(reply=result.final_output)
    except InputGuardrailTripwireTriggered as e:
        risk: RiskCheck = e.guardrail_result.output.output_info
        return ChatResponse(reply=f"Blocked: {risk.reasoning}", blocked=True)
