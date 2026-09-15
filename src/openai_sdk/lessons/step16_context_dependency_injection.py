from dataclasses import dataclass, field

from dotenv import load_dotenv
from agents import Agent, RunContextWrapper, Runner, function_tool

load_dotenv()


# This is the "dependency" being injected - real code, not the LLM's own
# training data. Nothing here is hardcoded into the agent or the tools.
@dataclass
class EngineerContext:
    name: str
    role: str  # "junior" or "senior"
    authorized_hosts: list[str] = field(default_factory=list)


# Dynamic instructions: instead of a fixed string, a function receives the
# context and agent and returns the prompt at run time - so the same Agent
# object behaves differently per caller without rebuilding it.
def dynamic_instructions(ctx: RunContextWrapper[EngineerContext], agent: Agent) -> str:
    eng = ctx.context
    if eng.role == "senior":
        return (
            f"You are assisting {eng.name}, a senior on-call engineer. "
            "They may restart any service on hosts they're authorized for. "
            "Be concise, skip basic safety caveats they already know."
        )
    return (
        f"You are assisting {eng.name}, a junior on-call engineer. "
        "Explain the impact of any destructive action before doing it, "
        "and double-check the hostname with them if it's ambiguous."
    )


# The first parameter typed RunContextWrapper[...] is injected by the SDK -
# it's excluded from the tool's schema the model sees, so the model can't
# forge or override authorized_hosts. That's the actual security property:
# authorization data flows in through Python, never through model output.
@function_tool
def restart_service(ctx: RunContextWrapper[EngineerContext], hostname: str, service_name: str) -> str:
    """Restart a service on a host. This is a DESTRUCTIVE action.

    Args:
        hostname: The host the service runs on.
        service_name: The name of the service to restart.
    """
    eng = ctx.context
    if hostname not in eng.authorized_hosts:
        return (
            f"DENIED: {eng.name} is not authorized for host '{hostname}'. "
            f"Authorized hosts: {eng.authorized_hosts}"
        )
    return f"Restarted '{service_name}' on {hostname} (authorized by {eng.name}'s scope)."


agent = Agent[EngineerContext](
    name="IT Assistant",
    instructions=dynamic_instructions,
    model="gpt-5.1",
    tools=[restart_service],
)


def ask(prompt: str, eng: EngineerContext) -> None:
    print(f"\n>>> [{eng.role}] {eng.name}: {prompt}")
    result = Runner.run_sync(agent, prompt, context=eng)
    print("Reply:", result.final_output)


junior = EngineerContext(name="Alex", role="junior", authorized_hosts=["web-01"])
senior = EngineerContext(name="Priya", role="senior", authorized_hosts=["web-01", "db-primary"])

# Same agent object, same tool - the ONLY thing that changes is the context
# passed at run time. Compare the two replies' tone.
ask("Restart the billing-api service on web-01.", junior)
ask("Restart the billing-api service on db-primary.", junior)
ask("Restart the billing-api service on db-primary.", senior)

# Isolate the authorization check itself (not instruction-driven hesitation):
# senior's instructions don't add caveats, so this proves the DENIED comes
# from the ctx.context.authorized_hosts check inside the tool, not the prompt.
ask("Restart the billing-api service on mail-01.", senior)
