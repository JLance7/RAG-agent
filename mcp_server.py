"""Absolute-path entry point for MCP clients, independent of their working directory.

Run with the project's Python: .venv/Scripts/python.exe mcp_server.py
stdout is the MCP protocol; diagnostics belong on stderr, never print().
"""
from ragbot.mcp_server import main


if __name__ == "__main__":
    main()
