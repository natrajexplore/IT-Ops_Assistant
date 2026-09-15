import asyncio
import time

from dotenv import load_dotenv
from openai.types.responses import ResponseTextDeltaEvent

from agents import Agent, Runner, function_tool

load_dotenv()


@function_tool
def check_disk_usage(hostname: str) -> str:
    """Check disk usage percentage on a host.

    Args:
        hostname: The hostname to check.
    """
    return f"{hostname} disk usage: 92%"


agent = Agent(
    name="IT Assistant",
    instructions="You are a concise IT infrastructure assistant. Use tools when needed.",
    model="gpt-5.1",
    tools=[check_disk_usage],
)


async def main() -> None:
    # run_streamed() returns immediately with a RunResultStreaming - the
    # actual model call happens in the background while we iterate events.
    # Without this, Runner.run()/run_sync() blocks until the ENTIRE reply
    # (including any tool calls) is done before you see a single character.
    start = time.monotonic()
    first_delta_at: float | None = None
    last_delta_at: float | None = None
    delta_count = 0

    result = Runner.run_streamed(agent, "Check disk usage on db-primary, then explain if it's a concern.")

    async for event in result.stream_events():
        # Low-level: individual token deltas as OpenAI streams them back -
        # this is what you'd forward to a chat UI character-by-character.
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            now = time.monotonic()
            if first_delta_at is None:
                first_delta_at = now
            last_delta_at = now
            delta_count += 1
            print(event.data.delta, end="", flush=True)

        # Higher-level: whole items completing (tool calls, their outputs,
        # full messages) - useful for showing "the agent is checking..." UX.
        elif event.type == "run_item_stream_event":
            if event.item.type == "tool_call_item":
                print("\n[tool call started]", flush=True)
            elif event.item.type == "tool_call_output_item":
                print(f"[tool result: {event.item.output}]\n", flush=True)

    print("\n\n--- stream complete ---")
    print(f"is_complete={result.is_complete}, final_output length={len(result.final_output)} chars")
    print(f"{delta_count} text-delta events arrived over "
          f"{last_delta_at - first_delta_at:.2f}s (not all at once) - "
          f"first delta at +{first_delta_at - start:.2f}s, run ended at +{time.monotonic() - start:.2f}s")


asyncio.run(main())
