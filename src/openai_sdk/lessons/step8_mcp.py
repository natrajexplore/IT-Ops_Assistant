import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

load_dotenv()

SERVER_SCRIPT = Path(__file__).parent / "mcp_infra_server.py"


async def main() -> None:
    # This spawns mcp_infra_server.py as its own subprocess and talks to it
    # over stdio using the MCP protocol - it is NOT a Python import, it's a
    # separate program, which is the point: in production this could be on
    # a completely different machine (SSH/HTTP transport instead of stdio).
    async with MCPServerStdio(
        name="Local Infra Server",
        params={"command": sys.executable, "args": [str(SERVER_SCRIPT)]},
    ) as mcp_server:
        tools = await mcp_server.list_tools()
        print("Tools discovered from MCP server:", [t.name for t in tools])

        agent = Agent(
            name="IT Assistant",
            instructions="You are an IT infrastructure assistant with access to real system tools.",
            model="gpt-5.1",
            mcp_servers=[mcp_server],
        )

        result = await Runner.run(
            agent, "What host is this, and what's the disk usage look like?"
        )
        print("\n" + result.final_output)


asyncio.run(main())
