"""The same idea as mcp_infra_server.py (a standalone MCP server, run as its
own process) but reachable over HTTP instead of stdio - this is what "remote
MCP" means in practice: the server can live on a completely different
machine, reachable by URL, rather than being spawned as a child process on
the agent's own box.

get_system_info deliberately returns a fake internal asset tag alongside the
real host info, to give step20's output guardrail something concrete to catch.
"""

import platform
import shutil

from mcp.server.mcpserver import MCPServer

server = MCPServer(name="remote-infra-server")


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
    """Get real OS/host info for this machine, plus its internal asset tag."""
    host = f"{platform.node()} - {platform.system()} {platform.release()} ({platform.machine()})"
    return f"{host}, asset_tag=IT-CORP-48213"


if __name__ == "__main__":
    server.run(transport="streamable-http", host="127.0.0.1", port=8765)
