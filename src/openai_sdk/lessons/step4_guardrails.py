from dotenv import load_dotenv
from pydantic import BaseModel

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
    function_tool,
    input_guardrail,
)

load_dotenv()


@function_tool
def restart_service(hostname: str, service_name: str) -> str:
    """Restart a service on a host. This is a DESTRUCTIVE action.

    Args:
        hostname: The host the service runs on.
        service_name: The name of the service to restart.
    """
    return f"Restarted '{service_name}' on {hostname}."


# --- Guardrail: classify whether a request needs elevated authorization ---

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
    return GuardrailFunctionOutput(
        output_info=risk,
        tripwire_triggered=risk.is_high_risk,
    )


agent = Agent(
    name="IT Assistant",
    instructions="You are an IT infrastructure assistant with access to real tools.",
    model="gpt-5.1",
    tools=[restart_service],
    input_guardrails=[high_risk_guardrail],
)


def ask(prompt: str) -> None:
    print(f"\n>>> {prompt}")
    try:
        result = Runner.run_sync(agent, prompt)
        print("Response:", result.final_output)
    except InputGuardrailTripwireTriggered as e:
        risk: RiskCheck = e.guardrail_result.output.output_info
        print(f"BLOCKED by guardrail. Reason: {risk.reasoning}")


ask("What's the disk usage on db-primary?")
ask("Restart the billing-api service on web-01.")
