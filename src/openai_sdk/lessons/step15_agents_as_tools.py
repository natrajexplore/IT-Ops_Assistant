from dotenv import load_dotenv
from agents import Agent, Runner, function_tool

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
    instructions="You are a network specialist. Answer connectivity questions concisely.",
    model="gpt-5.1",
    tools=[ping_host],
)

security_agent = Agent(
    name="Security Agent",
    instructions="You are a security specialist. Answer login/intrusion questions concisely.",
    model="gpt-5.1",
    tools=[check_failed_logins],
)

# The key difference from Step 5's handoff(): a handoff transfers control -
# the specialist's reply IS the final output, and the triage agent is done.
# as_tool() instead wraps a whole agent as a callable tool - the orchestrator
# stays in charge, can call several specialist-agents-as-tools in the same
# turn, and writes the final synthesized answer itself.
orchestrator = Agent(
    name="Incident Orchestrator",
    instructions=(
        "You investigate IT incidents. For any question, consult whichever "
        "specialist tools are relevant, then write ONE combined summary "
        "covering everything you found."
    ),
    model="gpt-5.1",
    tools=[
        network_agent.as_tool(
            tool_name="ask_network_agent",
            tool_description="Ask the network specialist about connectivity/reachability.",
        ),
        security_agent.as_tool(
            tool_name="ask_security_agent",
            tool_description="Ask the security specialist about logins/intrusions.",
        ),
    ],
)


def investigate(prompt: str) -> None:
    print(f"\n>>> {prompt}")
    result = Runner.run_sync(orchestrator, prompt)

    tool_calls = [
        item.raw_item.name
        for item in result.new_items
        if type(item).__name__ == "ToolCallItem"
    ]
    print("Specialist tools invoked:", tool_calls)
    print("last_agent stayed:", result.last_agent.name, "(never handed off)")
    print("\nFinal:", result.final_output)


# This question spans BOTH specialties. A handoff-based triage agent could
# only route it to one specialist and stop there. The orchestrator instead
# calls both as tools and merges the findings into a single report.
investigate(
    "Full status check: is db-backup reachable, and are there any suspicious "
    "login attempts on web-01?"
)
