from dotenv import load_dotenv
from agents import Agent, Runner, function_tool, ItemHelpers

load_dotenv()


# Mocked here on purpose - real infra calls (SSH, cloud APIs, monitoring
# systems) come in Step 10 via MCP. For now we prove the *mechanism*.
@function_tool
def check_disk_usage(hostname: str) -> str:
    """Check disk usage percentage on a given host.

    Args:
        hostname: The hostname or server name to check.
    """
    fake_usage = {"db-primary": 92, "web-01": 41}
    pct = fake_usage.get(hostname, 15)
    return f"{hostname} disk usage: {pct}%"


@function_tool
def ping_host(hostname: str) -> str:
    """Ping a host to check if it is reachable.

    Args:
        hostname: The hostname or server name to ping.
    """
    unreachable = {"db-backup"}
    if hostname in unreachable:
        return f"{hostname} is UNREACHABLE (100% packet loss)"
    return f"{hostname} is reachable (avg 4ms)"


agent = Agent(
    name="IT Assistant",
    instructions=(
        "You are an IT infrastructure assistant. Use the available tools to "
        "check real system state before answering. Never guess a status."
    ),
    model="gpt-5.1",
    tools=[check_disk_usage, ping_host],
)

result = Runner.run_sync(
    agent,
    "Is db-primary healthy? Check both its disk usage and whether it's reachable.",
)

print("--- Final answer ---")
print(result.final_output)

print("\n--- What actually happened this run ---")
for item in result.new_items:
    if item.type == "tool_call_item":
        print(f"[tool call] {item.raw_item.name}({item.raw_item.arguments})")
    elif item.type == "tool_call_output_item":
        print(f"[tool result] {item.output}")
    elif item.type == "message_output_item":
        print(f"[message] {ItemHelpers.text_message_output(item)}")
