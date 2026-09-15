from dotenv import load_dotenv
from agents import Agent, Runner, function_tool, handoff, trace

load_dotenv()


@function_tool
def ping_host(hostname: str) -> str:
    """Ping a host to check if it is reachable.

    Args:
        hostname: The hostname to ping.
    """
    unreachable = {"db-backup"}
    return f"{hostname} is UNREACHABLE" if hostname in unreachable else f"{hostname} is reachable"


@function_tool
def check_failed_logins(hostname: str) -> str:
    """Check recent failed login attempts on a host.

    Args:
        hostname: The hostname to check.
    """
    return f"{hostname}: 47 failed login attempts in the last hour"


network_agent = Agent(
    name="Network Agent",
    handoff_description="Handles connectivity and reachability issues.",
    instructions="You are a network specialist.",
    model="gpt-5.1",
    tools=[ping_host],
)

security_agent = Agent(
    name="Security Agent",
    handoff_description="Handles suspected intrusions and failed logins.",
    instructions="You are a security specialist.",
    model="gpt-5.1",
    tools=[check_failed_logins],
)

triage_agent = Agent(
    name="Triage Agent",
    instructions="Route IT issues to the correct specialist. Don't solve them yourself.",
    model="gpt-5.1",
    handoffs=[network_agent, handoff(security_agent)],
)

# Without `trace()`, each Runner.run_sync call below would show up in the
# dashboard as its own separate, disconnected trace named "Agent workflow".
# Wrapping them groups both turns of this incident into ONE named trace.
with trace(workflow_name="IT Incident Investigation") as t:
    print(f"Trace ID: {t.trace_id}")
    print("View at: https://platform.openai.com/traces (search/sort by name or time to find it)\n")

    result1 = Runner.run_sync(triage_agent, "db-backup seems unreachable, can you check?")
    print("Step 1 answered by:", result1.last_agent.name)

    result2 = Runner.run_sync(triage_agent, "Separately: web-01 has a ton of failed logins, is it under attack?")
    print("Step 2 answered by:", result2.last_agent.name)
