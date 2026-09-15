from dotenv import load_dotenv
from agents import Agent, Runner, SQLiteSession

load_dotenv()

agent = Agent(
    name="IT Assistant",
    instructions="You are a concise assistant for an IT infrastructure team.",
    model="gpt-5.1",
)

# Fresh process, zero in-memory history of its own - reopening the same
# session_id + db_path is the only reason this can possibly answer correctly.
session = SQLiteSession(session_id="incident-4821", db_path="sessions.db")

result = Runner.run_sync(
    agent, "Remind me: what server did we discuss, and what was wrong with it?", session=session
)
print("Resumed answer:", result.final_output)
