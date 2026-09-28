"""NORTH7 MCP Server — stdio mode for Glama/mcp-proxy."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from api.v1.mcp_server import server
from mcp.server.stdio import stdio_server


async def main():
    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
