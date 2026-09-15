import os

from dotenv import load_dotenv
from agents import Agent, Runner

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

agent = Agent(
    name="IT Assistant",
    instructions="You are a helpful assistant for an IT infrastructure team.",
)

result = Runner.run_sync(agent, "In one sentence, what is your job here?")
print(result.final_output)
