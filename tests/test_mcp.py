"""Exercise real MCP discovery/tool calls in-process and over a stdio subprocess."""
import asyncio
import os
from pathlib import Path
import sqlite3
import sys

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from ragbot.mcp_server import ReadOnlyStore, create_server
from ragbot.store import Store

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {"get_status", "list_documents", "search_documents", "ask_question", "list_tables", "preview_table", "summarize_column"}


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "index.sqlite3"
    store = Store(path)
    store.ingest("revenue.csv", b"year,revenue\n2023,100.10\n2024,200.20\n2025,\n")
    store.ingest("policy.md", b"The archive retention period is fourteen days.")
    return path


async def exercise_tools(client):
    discovered = await client.list_tools()
    assert {tool.name for tool in discovered.tools} == TOOLS
    assert all(tool.annotations.read_only_hint for tool in discovered.tools)

    status = await client.call_tool("get_status", {})
    assert not status.is_error
    assert status.structured_content["documents"] == 2

    documents = (await client.call_tool("list_documents", {"limit": 1})).structured_content
    assert len(documents["documents"]) == 1 and documents["next_offset"] == 1
    scoped = documents["documents"][0]["id"]
    hits = await client.call_tool("search_documents", {"query": "retention"})
    assert not hits.is_error and "fourteen" in hits.structured_content["matches"][0]["excerpt"]
    empty = await client.call_tool("search_documents", {"query": "retention", "document_ids": []})
    assert empty.structured_content["matches"] == []

    answer = await client.call_tool("ask_question", {"question": "Compare revenue in 2023 and 2024"})
    assert not answer.is_error
    assert "100.1" in answer.structured_content["text"] and "200.2" in answer.structured_content["text"]
    assert answer.structured_content["sources"][0]["name"] == "revenue.csv"

    tables = (await client.call_tool("list_tables", {"document_ids": [scoped]})).structured_content["tables"]
    assert len(tables) == 1
    identifier = tables[0]["table_id"]
    preview = (await client.call_tool("preview_table", {"table_id": identifier, "limit": 1, "offset": 1})).structured_content
    assert preview["rows"][0]["year"] == "2024" and preview["logical_source_rows"] == [3]
    assert preview["next_offset"] == 2
    summary = (await client.call_tool("summarize_column", {"table_id": identifier, "column": "revenue"})).structured_content
    assert summary["numeric_count"] == 2 and summary["missing_or_nonnumeric_count"] == 1
    assert summary["statistics"]["sum"] == "300.30" and summary["statistics"]["mean"] == "150.15"

    assert (await client.call_tool("preview_table", {"table_id": 999999})).is_error
    assert (await client.call_tool("search_documents", {"query": "retention", "document_ids": ["unknown"]})).is_error
    assert (await client.call_tool("preview_table", {"table_id": identifier, "limit": 10000})).is_error
    assert (await client.call_tool("summarize_column", {"table_id": identifier, "column": "DROP TABLE documents"})).is_error
    assert (await client.call_tool("search_documents", {"query": "   "})).is_error

    resource = await client.read_resource("datadesk://overview")
    assert resource.contents


def test_read_only_database_connection(index):
    store = ReadOnlyStore(index)
    with store.connection() as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM documents")
    assert len(Store(index).documents()) == 2


def test_missing_index_is_not_created(tmp_path):
    missing = tmp_path / "absent" / "index.sqlite3"
    with pytest.raises(ValueError, match="does not exist"):
        create_server(missing)
    assert not missing.parent.exists()


def test_mcp_in_process(index):
    async def check():
        async with Client(create_server(index)) as client:
            await exercise_tools(client)
    asyncio.run(check())


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_mcp_real_stdio_subprocess(index, mode):
    async def check():
        # Deliberately use a different cwd and a DB path containing spaces.
        copied = index.with_name("index with spaces.sqlite3")
        copied.write_bytes(index.read_bytes())
        parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py"), "--db", str(copied)],
                                           cwd=str(index.parent), env={**os.environ, "PYTHONUTF8": "1"})
        async with Client(parameters, mode=mode, read_timeout_seconds=30) as client:
            await exercise_tools(client)
    asyncio.run(check())
