from dotenv import load_dotenv
from agents import Agent, RunContextWrapper, Runner, function_tool, handoff

load_dotenv()


# --- Specialist 1: network ---

@function_tool
def ping_host(hostname: str) -> str:
    """Ping a host to check if it is reachable.

    Args:
        hostname: The hostname to ping.
    """
    unreachable = {"db-backup"}
    return f"{hostname} is UNREACHABLE" if hostname in unreachable else f"{hostname} is reachable"


network_agent = Agent(
    name="Network Agent",
    handoff_description="Handles connectivity, latency, and reachability issues between hosts.",
    instructions="You are a network specialist. Diagnose connectivity issues using your tools.",
    model="gpt-5.1",
    tools=[ping_host],
)


# --- Specialist 2: security ---

@function_tool
def check_failed_logins(hostname: str) -> str:
    """Check recent failed login attempts on a host.

    Args:
        hostname: The hostname to check.
    """
    fake_data = {"web-01": 47}
    count = fake_data.get(hostname, 0)
    return f"{hostname}: {count} failed login attempts in the last hour"


security_agent = Agent(
    name="Security Agent",
    handoff_description="Handles suspected intrusions, failed logins, and access-control concerns.",
    instructions="You are a security specialist. Investigate using your tools and flag real risk.",
    model="gpt-5.1",
    tools=[check_failed_logins],
)


# --- Triage agent: routes, doesn't solve directly ---

def log_handoff_to_security(ctx: RunContextWrapper) -> None:
    # A real audit trail would write this to a log/ticket system.
    print("[AUDIT] Triage handed off to Security Agent")


triage_agent = Agent(
    name="Triage Agent",
    instructions=(
        "You are the first point of contact for IT infrastructure issues. "
        "Do not attempt to solve issues yourself - hand off to the correct specialist."
    ),
    model="gpt-5.1",
    handoffs=[
        network_agent,
        handoff(security_agent, on_handoff=log_handoff_to_security),
    ],
)


def ask(prompt: str) -> None:
    print(f"\n>>> {prompt}")
    result = Runner.run_sync(triage_agent, prompt)
    print("Answered by:", result.last_agent.name)
    print("Response:", result.final_output)


ask("db-backup seems unreachable, can you check?")
ask("web-01 has a ton of failed login attempts, is it under attack?")
