"""A standalone MCP server - a separate process from the agent, speaking the
Model Context Protocol over stdio. This is the piece that would, in a real
deployment, live on/near actual infrastructure (a jump host, a sidecar,
a cloud function) instead of on the agent's own machine.

Tools here return REAL data about this machine, not mocked values like
earlier lessons - proof the agent is looking at something real.
"""

import platform
import shutil

from mcp.server.mcpserver import MCPServer

server = MCPServer(name="local-infra-server")


@server.tool()
def get_disk_usage(path: str = ".") -> str:
    """Get real disk usage for a path on this machine."""
    total, used, free = shutil.disk_usage(path)
    gb = 1024**3
    pct = used / total * 100
    return (
        f"Disk usage for '{path}': {used / gb:.1f}GB used / {total / gb:.1f}GB total "
        f"({pct:.1f}%), {free / gb:.1f}GB free"
    )


@server.tool()
def get_system_info() -> str:
    """Get real OS and host info for this machine."""
    return f"{platform.node()} - {platform.system()} {platform.release()} ({platform.machine()})"


if __name__ == "__main__":
    server.run()  # defaults to stdio transport
