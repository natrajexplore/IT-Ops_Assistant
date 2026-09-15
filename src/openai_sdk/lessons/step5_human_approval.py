from dotenv import load_dotenv
from agents import Agent, Runner, function_tool

load_dotenv()


@function_tool
def check_disk_usage(hostname: str) -> str:
    """Check disk usage percentage on a host. Read-only, no approval needed.

    Args:
        hostname: The hostname to check.
    """
    return f"{hostname} disk usage: 92%"


# needs_approval=True: no matter what the model decides, this tool call
# always pauses the run and waits for a human decision before executing.
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


def get_human_decision(item) -> bool:
    print(f"\n[APPROVAL REQUIRED] {item.name}({item.arguments})")
    try:
        return input("Approve this action? [y/N]: ").strip().lower() == "y"
    except EOFError:
        print("(no interactive terminal attached in this run - auto-rejecting for safety)")
        return False


def run_with_approval(prompt: str) -> None:
    print(f"\n>>> {prompt}")
    result = Runner.run_sync(agent, prompt)

    # A run can pause more than once if multiple approvals are needed across turns.
    while result.interruptions:
        state = result.to_state()
        for item in result.interruptions:
            if get_human_decision(item):
                state.approve(item)
                print(" -> approved")
            else:
                state.reject(item)
                print(" -> rejected")
        result = Runner.run_sync(agent, state)

    print("Final:", result.final_output)


run_with_approval("What's the disk usage on db-primary?")
run_with_approval("Restart the billing-api service on web-01.")
