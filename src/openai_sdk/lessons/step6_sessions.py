import asyncio

from dotenv import load_dotenv
from agents import Agent, Runner, SQLiteSession

load_dotenv()

agent = Agent(
    name="IT Assistant",
    instructions="You are a concise assistant for an IT infrastructure team.",
    model="gpt-5.1",
)

# A file path (not ":memory:") means this survives past this process exiting -
# run step6_sessions_resume.py afterward to see it resume from disk.
session = SQLiteSession(session_id="incident-4821", db_path="sessions.db")

result = Runner.run_sync(
    agent, "We have a server named 'db-primary'. Remember that name.", session=session
)
print("Turn 1:", result.final_output)

# No manual history threading (to_input_list) needed - the session already
# has turn 1 stored, and Runner reads it automatically.
result2 = Runner.run_sync(
    agent, "What was the server name I just mentioned?", session=session
)
print("Turn 2:", result2.final_output)

result3 = Runner.run_sync(
    agent, "One more thing: that server's disk is at 92%. Remember that too.", session=session
)
print("Turn 3:", result3.final_output)

items = asyncio.run(session.get_items())
print(f"\n{len(items)} items now stored on disk under session_id='{session.session_id}'")
