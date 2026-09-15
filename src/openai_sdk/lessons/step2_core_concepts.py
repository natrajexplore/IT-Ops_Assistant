from dotenv import load_dotenv
from agents import Agent, Runner, ModelSettings

load_dotenv()

agent = Agent(
    name="IT Assistant",
    instructions="You are a concise assistant for an IT infrastructure team. Keep answers to 1-2 sentences.",
    model="gpt-5.1",
    model_settings=ModelSettings(temperature=0.2),
)

# Turn 1
result = Runner.run_sync(agent, "We have a server named 'db-primary'. Remember that name.")
print("Turn 1:", result.final_output)

# Turn 2: continue the same conversation by feeding turn 1's history back in.
history = result.to_input_list()
history.append({"role": "user", "content": "What was the server name I just mentioned?"})

result2 = Runner.run_sync(agent, history)
print("Turn 2:", result2.final_output)

# Inspecting the run result object itself
print("\n--- Run metadata ---")
print("Number of items generated this run:", len(result2.new_items))
print("Last agent that handled the run:", result2.last_agent.name)
