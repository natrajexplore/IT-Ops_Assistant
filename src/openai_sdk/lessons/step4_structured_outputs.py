from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from agents import Agent, Runner, function_tool

load_dotenv()


@function_tool
def check_disk_usage(hostname: str) -> str:
    """Check disk usage percentage on a host.

    Args:
        hostname: The hostname to check.
    """
    fake_usage = {"db-primary": 92, "web-01": 41}
    return f"{hostname} disk usage: {fake_usage.get(hostname, 15)}%"


@function_tool
def ping_host(hostname: str) -> str:
    """Ping a host to check if it is reachable.

    Args:
        hostname: The hostname to ping.
    """
    unreachable = {"db-backup"}
    return f"{hostname} is UNREACHABLE" if hostname in unreachable else f"{hostname} is reachable"


# The shape a dashboard/ticket system would actually consume - not the
# model's natural prose shape.
class HealthCheckResult(BaseModel):
    status: Literal["ok", "warning", "critical"]
    findings: list[str]
    recommended_action: str | None


agent = Agent(
    name="IT Assistant",
    instructions=(
        "You are an IT infrastructure health-check assistant. Use the tools to "
        "gather real data, then summarize your findings in the required format."
    ),
    model="gpt-5.1",
    tools=[check_disk_usage, ping_host],
    output_type=HealthCheckResult,
)

result = Runner.run_sync(agent, "Run a health check on db-primary.")

report = result.final_output  # this is a HealthCheckResult instance, not a string
print(type(report))
print(report)

print("\n--- Fields, individually addressable ---")
print("status:", report.status)
print("findings:", report.findings)
print("recommended_action:", report.recommended_action)

if report.status == "critical":
    print("\n[ALERT] Would page on-call here.")
