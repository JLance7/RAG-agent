# Data Desk MCP server

The chatbot now includes an **MCP stdio server** sharing its existing SQLite document index. A compatible MCP host can discover tools, search indexed files, ask cited questions, inspect rows and calculate numeric summaries. No Ollama model, API key or cloud account is required for these tools.

The Streamlit chatbot now acts as one such host: local Ollama `qwen3:4b` queries this MCP server and writes the final response. The tools themselves remain read-only and model-free, preventing recursion. External hosts can still connect independently. The built-in client passes a per-question `RAGBOT_DOCUMENT_IDS` scope, enforced by all tools. See [OLLAMA.md](OLLAMA.md).

## Ready-to-use tools

| Tool | Purpose | Example arguments |
| --- | --- | --- |
| `get_status` | Index counts and server capabilities | `{}` |
| `list_documents` | Document IDs, names and counts; paginated | `{"limit": 20}` |
| `search_documents` | BM25 excerpts with file/page/row locations | `{"query": "inflation adjustment", "limit": 3}` |
| `ask_question` | Existing evidence/table agent with source citations and trace | `{"question": "Compare home price in 2000 and 2024"}` |
| `list_tables` | Table IDs, source files, column names and row counts | `{}` |
| `preview_table` | Bounded, paginated source rows | `{"table_id": 1, "limit": 5, "offset": 0}` |
| `summarize_column` | Numeric count, sum, mean, median, min and max | `{"table_id": 1, "column": "income"}` |

Use discovery tools to obtain the actual document/table IDs rather than assuming the examples' IDs. `document_ids` on search, questions and table listing accepts IDs from `list_documents`; omit it for all files or use `[]` for none. Unknown IDs produce a tool error.

The server also exposes **`datadesk://overview`**, a small read-only resource reporting index counts.

## Setup on this computer

Dependencies have been installed and the connection smoke-tested for this task. To set up again or after cloning, double-click **Setup MCP.bat**, or run:

```powershell
.\setup-mcp.ps1
```

Setup prepares the app's virtual environment/index and installs `requirements-mcp.txt`, which pins the official `mcp` Python SDK to **2.3.0**. SDK v2 supports current discovery and legacy handshake clients; both stdio paths are covered by tests. Setup itself requires internet to download missing dependencies. Serving the indexed data does not.

## Connect an MCP host

The client launches the server subprocess. You do not need to start a web service, run Streamlit, or reserve a port.

`mcp-config.example.json` contains a common MCP-host configuration with the actual project paths:

```json
{
  "mcpServers": {
    "data-desk": {
      "command": "D:\\joshu\\Documents\\programming\\github\\agent\\.venv\\Scripts\\python.exe",
      "args": ["D:\\joshu\\Documents\\programming\\github\\agent\\mcp_server.py"],
      "env": {
        "RAGBOT_DB": "D:\\joshu\\Documents\\programming\\github\\agent\\storage\\desk.sqlite3",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

Merge this entry into a host that accepts the `mcpServers` JSON format, or enter the same command, arguments and environment in its MCP settings. Hosts use different configuration locations/formats; this file is an example, not an automatic edit to any host's settings. Paths must be changed if you move the project.

Point the host **directly at the Python executable and `mcp_server.py`**. Do not use `Start.bat`, `Setup MCP.bat`, `run.ps1`, or an installer as a protocol wrapper. Their normal console output is not MCP JSON-RPC. The server itself keeps stdout for protocol messages and diagnostics on stderr.

For manual startup:

```powershell
.\.venv\Scripts\python.exe mcp_server.py
```

It waits quietly for MCP input. That is normal; it is not an interactive chat terminal. Exit with Ctrl+C. `--db PATH` selects a different existing Data Desk index, taking precedence over `RAGBOT_DB`. The default database path is resolved from this project, so the client's current working directory does not matter.

## Try the real client demo

```powershell
.\.venv\Scripts\python.exe scripts/mcp_client_demo.py
.\.venv\Scripts\python.exe scripts/mcp_client_demo.py "What are the limits of price-to-income comparisons?"
```

The demo starts the server as a subprocess, discovers its tools, calls `ask_question`, prints the structured result, and shuts down the subprocess. It does not modify your documents. The demo uses the same Python environment as the server; its paths are resolved from the script location.

## Behavior and boundaries

- **Read-only is enforced**, not just an annotation: database connections use SQLite `mode=ro` and `query_only`. There are no upload/delete/write tools. Upload documents using the existing app or CLI first.
- The server reads only its configured index; it has no arbitrary-file, web, SQL or shell-execution tool. It does not open an HTTP listening port.
- `ask_question` uses the existing deterministic table tool or extractive RAG evidence mode. It does not call Ollama or an external LLM. The MCP host can use its own model to write a narrative from the returned evidence; that host's data-handling policy is separate from this server.
- File contents, metadata and cell text are untrusted data, not instructions. Returned text is not proof that a quoted claim is true. Source IDs and locators let the user inspect the evidence.
- Search limits are 1–8 results and excerpts are capped at 2,500 characters. Table pages allow 1–50 rows, a response budget, and cell clipping at 500 characters; flags reveal truncation. Offsets are zero-based. `next_offset` supports pagination.
- Numeric summaries are **decimal strings** rather than binary floats. Finite values up to 24 significant input digits and decimal exponents -100 through 100 are supported; other cells count as missing/unsupported. Means use 50-digit decimal precision. The summary covers the whole column, with no hidden filtering/grouping.
- A sum is not automatically a meaningful statistic: percentages, indices and demographic subtotal rows may not be additive. The tool preserves source units and warns that subgroups may overlap.
- An absent database fails clearly instead of creating an empty library. Existing document changes made through the app become visible to subsequent tool calls. Existing SQLite WAL sidecars may be used for normal read coordination; read-only here means no document/index mutations, not a forensic guarantee of no filesystem metadata changes.
- This is a local, single-user integration. No MCP client has been registered automatically, and no external messages or cloud requests are sent by these tools.

## Code and tests

`ragbot/mcp_server.py` contains the commented tool definitions and read-only adapter. `mcp_server.py` is the location-independent entry point. Existing RAG/ingestion implementations are reused rather than duplicated.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

The suite checks actual tool discovery/calls in-process and through a real stdio subprocess, in both current and legacy client modes. It also checks errors, pagination, source citations, parameter bounds, read-only enforcement, paths with spaces and a different working directory, and the unchanged Streamlit chatbot tests.

Official SDK references: [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/), [running a server](https://py.sdk.modelcontextprotocol.io/run/), and [client usage](https://py.sdk.modelcontextprotocol.io/client/).
