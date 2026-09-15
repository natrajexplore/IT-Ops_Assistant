from dotenv import load_dotenv

from agents import Agent, Runner, function_tool
from agents.usage import Usage

load_dotenv()

# Prices are per 1M tokens, illustrative only - check platform.openai.com/pricing
# for current rates before using this for real budgeting. Cached input tokens
# (context the model has seen before, e.g. repeated system instructions) are
# billed at a steep discount, which is why we track them separately below.
MODEL = "gpt-5.1"
PRICING_PER_MILLION_TOKENS = {
    "gpt-5.1": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
}


def cost_for_usage(usage: Usage) -> float:
    rates = PRICING_PER_MILLION_TOKENS[MODEL]
    cached = usage.input_tokens_details.cached_tokens or 0
    uncached_input = usage.input_tokens - cached
    return (
        uncached_input * rates["input"]
        + cached * rates["cached_input"]
        + usage.output_tokens * rates["output"]
    ) / 1_000_000


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
    model=MODEL,
    tools=[check_disk_usage],
)

questions = [
    "Check disk usage on db-primary.",
    "Now check web-01 too, and tell me if either is a concern.",
    "Summarize both hosts in one sentence.",
]

# Usage() with no args starts at all-zeros; .add() accumulates another Usage
# into it turn by turn, so this tracks the whole session's spend.
session_usage = Usage()
history: list = []

for i, question in enumerate(questions, start=1):
    history.append({"role": "user", "content": question})
    result = Runner.run_sync(agent, history)
    history = result.to_input_list()

    # Every RunResult carries its own per-run usage on context_wrapper.usage -
    # this is populated by the SDK from the raw API response, not estimated.
    usage = result.context_wrapper.usage
    session_usage.add(usage)
    cost = cost_for_usage(usage)

    print(f"--- turn {i}: {question!r}")
    print(f"    requests={usage.requests} input={usage.input_tokens} "
          f"(cached={usage.input_tokens_details.cached_tokens}) "
          f"output={usage.output_tokens} total={usage.total_tokens}")
    print(f"    turn cost: ${cost:.6f}")

print("\n=== session totals ===")
print(f"requests={session_usage.requests} total_tokens={session_usage.total_tokens}")
print(f"session cost: ${cost_for_usage(session_usage):.6f}")

# request_usage_entries preserves the per-request breakdown even after
# aggregating into session_usage - useful for finding which single call in a
# long-running agent blew the budget, not just the total.
print("\n--- per-request breakdown (from request_usage_entries) ---")
for j, entry in enumerate(session_usage.request_usage_entries, start=1):
    print(f"    request {j}: input={entry.input_tokens} output={entry.output_tokens} "
          f"total={entry.total_tokens}")
