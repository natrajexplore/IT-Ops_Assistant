import os
import subprocess
import sys

import psutil
from dotenv import load_dotenv

from agents import Agent, Runner, function_tool

load_dotenv()

# Set LESSON_AUTO_APPROVE=1 to auto-approve destructive actions when this
# script is run non-interactively (no stdin attached). This override exists
# ONLY to demo the real restart below without a human at a keyboard - a real
# deployment should never auto-approve; the safe default (see
# get_human_decision) is still to reject when nobody's there to say yes.
AUTO_APPROVE_FOR_DEMO = os.environ.get("LESSON_AUTO_APPROVE") == "1"

# A real background process standing in for a "service." Every earlier lesson
# faked disk/service data as return strings; this one controls something
# genuinely real (an actual OS process, actual PIDs) - scoped to a throwaway
# process we spawn ourselves, so a real restart is safe to actually perform.
DUMMY_SERVICE_CMD = [sys.executable, "-c", "import time; time.sleep(999999)"]
dummy_service: dict[str, subprocess.Popen] = {}


def start_dummy_service() -> None:
    dummy_service["proc"] = subprocess.Popen(DUMMY_SERVICE_CMD)


@function_tool
def list_top_processes(limit: int = 5) -> str:
    """List the top processes on this machine by memory usage. Real data, read-only.

    Args:
        limit: How many processes to return.
    """
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem_mb = p.info["memory_info"].rss / (1024 * 1024)
            procs.append((mem_mb, p.info["pid"], p.info["name"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(reverse=True)
    lines = [f"{name} (pid={pid}): {mem:.1f}MB" for mem, pid, name in procs[:limit]]
    return "\n".join(lines)


@function_tool
def check_host_reachable(host: str) -> str:
    """Check whether a host responds to a real network ping. Read-only.

    Args:
        host: Hostname or IP to ping.
    """
    result = subprocess.run(
        ["ping", "-n", "1", "-w", "1000", host],
        capture_output=True,
        text=True,
    )
    reachable = result.returncode == 0
    status = "REACHABLE" if reachable else "UNREACHABLE"
    return f"{host}: {status} (real ping, exit code {result.returncode})"


@function_tool(needs_approval=True)
def restart_dummy_service() -> str:
    """Restart the lesson's dummy background service.

    REAL destructive action: actually terminates and relaunches a real OS
    process (scoped to our own throwaway process, not a system service).
    """
    proc = dummy_service.get("proc")
    old_pid = proc.pid if proc else None
    if proc is not None:
        proc.terminate()
        proc.wait(timeout=5)
    start_dummy_service()
    return f"Restarted dummy service: old pid={old_pid}, new pid={dummy_service['proc'].pid}"


agent = Agent(
    name="IT Assistant",
    instructions="You are an IT infrastructure assistant with access to real tools.",
    model="gpt-5.1",
    tools=[list_top_processes, check_host_reachable, restart_dummy_service],
)


def get_human_decision(item) -> bool:
    print(f"\n[APPROVAL REQUIRED] {item.name}({item.arguments})")
    try:
        return input("Approve this action? [y/N]: ").strip().lower() == "y"
    except EOFError:
        if AUTO_APPROVE_FOR_DEMO:
            print("(no interactive terminal - LESSON_AUTO_APPROVE=1 set, approving for this demo run)")
            return True
        print("(no interactive terminal attached in this run - auto-rejecting for safety)")
        return False


def run_with_approval(prompt: str) -> None:
    print(f"\n>>> {prompt}")
    result = Runner.run_sync(agent, prompt)
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


start_dummy_service()
print(f"Dummy service started, pid={dummy_service['proc'].pid}")

try:
    run_with_approval("List the top 3 processes by memory usage on this machine.")
    run_with_approval("Is 8.8.8.8 reachable?")
    run_with_approval("Is definitely-not-a-real-host.invalid reachable?")

    before_pid = dummy_service["proc"].pid
    run_with_approval("Restart the dummy service.")
    after_pid = dummy_service["proc"].pid
    if before_pid == after_pid:
        print(f"\nVerified: pid unchanged ({before_pid}) - the approval gate held, no restart happened.")
    else:
        print(f"\nVerified: pid changed {before_pid} -> {after_pid} - a real process was actually killed and relaunched.")
finally:
    proc = dummy_service.get("proc")
    if proc is not None:
        proc.terminate()
