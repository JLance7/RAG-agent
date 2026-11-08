"""Launch Data Desk as a real MCP subprocess, discover tools and ask a question.

Run from any folder with the project's Python executable. The host owns the
server process and closes it when the client context exits.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


async def demo(question):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "mcp_server.py")],
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    async with Client(parameters, read_timeout_seconds=30) as client:
        tools = await client.list_tools()
        print("Tools:", ", ".join(tool.name for tool in tools.tools))
        result = await client.call_tool("ask_question", {"question": question})
        if result.is_error:
            raise RuntimeError(str(result.content))
        print(json.dumps(result.structured_content, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", default="Compare home price in 2000 and 2024")
    asyncio.run(demo(parser.parse_args().question))
