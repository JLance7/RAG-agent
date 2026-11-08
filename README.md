# Data Desk — a local RAG chatbot for your files

Upload data or documents, ask questions, and inspect the source passages and rows behind each response. **Ollama with the local `qwen3:4b` model now generates answers by querying the read-only RAG tools over MCP.** The app includes persistent indexing, decimal table calculations, citations, charts, and optional semantic retrieval.

## Start

On this computer, Ollama and `qwen3:4b` are already installed and live-tested. Double-click **Start.bat**: it prepares the Python environment, indexes the sample if needed, starts the project-local Ollama server if it is stopped, and opens Streamlit at **http://localhost:8501**. The default answer mode and model are already selected. Stop the Streamlit console with Ctrl+C. If port 8501 is in use, stop the other Streamlit app first or run manually on another port.

On a fresh copy, run **Setup Local Model.bat** first. It downloads the pinned official Ollama Windows runtime (~1.5 GB) and `qwen3:4b` weights (~2.5 GB). Generation afterward uses this machine, not a cloud provider. No global PATH, Windows service, or startup task is installed. The runtime lives in `.runtime/ollama/`, models in `storage/ollama-models/`, and the local server listens only on `127.0.0.1:11434` with `OLLAMA_NO_CLOUD=1`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502
```

Manual startup does not automatically seed the library: click **Load included public sample** in the sidebar. To start the bundled model server manually, run `.venv\Scripts\python.exe -m ragbot.local_runtime start`. First-time dependencies and model setup need internet; generation, retrieval and calculations work offline afterward. No API key or paid subscription is required.

## What it can do

- Index **UTF-8 text, Markdown, CSV, JSON, text PDFs, and XLSX**.
- Search selected files with local **SQLite FTS5/BM25** retrieval.
- Return matching excerpts with file names, page/row locators and source IDs such as `[S1]`.
- Calculate sums, means, medians, minima, maxima, and exact-year comparisons from a named numeric column.
- Use **local qwen3:4b** to select read-only MCP tools and write cited answers from their results.
- Build optional **Ollama embedding vectors** and combine cosine/vector ranking with keyword ranking.
- Inspect/filter dataset rows, create basic charts, and export results.
- Store documents/indexes locally, deduplicate identical uploads, download originals and remove indexed files.

The starter corpus uses real public data from the earlier Gen Z Lens project. Try:

```text
Compare home price in 2000 and 2024
What is the mean income?
What are the limits of price-to-income comparisons?
Living with spouse for ages 18-24 in 1990 and 2023
```

For your own CSV, ask something like **“What is the total revenue?”** or **“Compare revenue in 2023 and 2024”**. Naming the source column makes the intent unambiguous. Select the relevant file when several datasets contain the same column name.

## Default: local Ollama + MCP RAG tools

The default path is **question → real MCP data query → local model tool selection if needed → read-only MCP results → local structured answer writer → citation checks**. The model can discover documents/tables, search passages, preview rows and request numeric summaries. An initial grounded query runs for every question. Numeric questions get a verified table result before the model explains the answer; they are no longer returned directly without model generation.

The tool loop is bounded to four planning rounds and ten tool calls. Only the supplied MCP tool names can run. A dedicated MCP subprocess enforces the selected-file scope for all discovery, retrieval, preview and calculation calls. The model cannot query an unselected table by guessing its ID. No shell, arbitrary SQL, filesystem mutation, or web tool is available.

A structured tool-planning response is used to avoid displaying internal planning text. A separate JSON-constrained final writer produces the user-visible answer. Truncated final output and invalid citation IDs are rejected. If generation fails, the app explicitly labels the fallback as local evidence/calculations and shows a warning; it never pretends fallback output came from Ollama.

## Model settings and explicit evidence mode

**Local evidence + table tools** remains an explicitly selected fallback. Numeric questions matching its supported grammar produce deterministic calculations; other questions return quoted passages. It is not the default response generator.

In **Model & retrieval**, choose another installed **local, tool-capable** model if desired. The app discovers installed local models automatically. **Save model preferences** persists the local URL, chat/embedding model and mode in `storage/settings.json`. For semantic search in evidence mode, choose a compatible installed embedding model and click **Build / update semantic index**. An embedding model is not the same thing as a chat model. The default Ollama agent queries the MCP keyword and table tools; it does not require embedding weights.

Normal chat never downloads models. The explicit setup helper installs the pinned runtime and chosen weights. See [Ollama's documentation](https://docs.ollama.com/) for other installations. Official API references used here: [chat](https://docs.ollama.com/api/chat), [tool calling](https://docs.ollama.com/capabilities/tool-calling), [embeddings](https://docs.ollama.com/api/embed), and [installed models](https://docs.ollama.com/api/tags). Only loopback endpoints are accepted; redirects/proxy environment settings are disabled for document/model traffic. Cloud-tagged or remote models and models without tool capability are rejected on the agent path. The bundled server disables cloud use; independent server configurations remain the user's responsibility.

Citation-ID validation is not a factual-entailment checker. Always inspect cited text: a model can still write unsupported claims despite valid citation syntax. There is no automatic web search, cloud AI connection, ChatGPT subscription integration, or model-driven code execution. First requests after loading weights/context can be slower; subsequent requests reuse the warm model. The live tests on this machine are recorded in VALIDATION.md.

## Table calculations

The MCP tools use fixed Python operations, not generated SQL/Python. They resolve numeric columns, optionally filter exact years and supported age/sex categories, then calculate with decimal arithmetic. The model is instructed to explain those results rather than recalculate. Tool displays use at most four decimal places; relative changes display two. Values retain source units, without automatic inflation adjustment.

The tool deliberately declines unsupported filters such as “after 2020”, negation, grouped operations, or ambiguous columns. Those questions fall back to evidence retrieval rather than silently calculating a different answer. There is no general natural-language SQL agent. In the explorer, charts use numeric coercion for plotting and do not aggregate duplicate X values; up to 5,000 filtered records are plotted in source order.

## Persistence and limits

`storage/desk.sqlite3` contains original uploaded bytes, extracted chunks, table records and optional embeddings. It is excluded from Git. Chat history is in Streamlit's server memory for the current browser session, and can be exported to JSON. No credentials are saved. Stop the app before manually copying its SQLite database; while it runs, WAL sidecars may contain recent writes.

The hidden Ollama server is separate from Streamlit and may remain running after closing the web app. It unloads idle model weights after its keep-alive period. Its process ID is recorded in `storage/ollama-process.json`; runtime diagnostics are in `storage/ollama-server.log`. No Windows autostart/service is configured. Restart it with Start.bat when needed. `.runtime/`, models and private settings are excluded from Git.

- Maximum upload: 20 MB/file. Tables: at most 200 columns and 50,000 rows each, also subject to extracted-text/chunk limits.
- Extracted text: two million characters; up to 4,000 chunks/document. Table chunk expansion is additionally bounded.
- XLSX: at most 25 sheets and bounded ZIP expansion. First row is the header. Blank rows are preserved; cached formula results are read, formulas/macros are never executed.
- PDF: at most 500 pages, embedded text only. Scanned documents need external OCR. Extracted table layout may be imperfect.
- CSV citations use logical records after the header, not byte offsets or physical text lines when quoted fields span lines. JSON tables use the same logical header/data-row convention.
- Semantic indexing is limited to 5,000 pending chunks per operation. Partially indexed corpora are disclosed and retain keyword retrieval for other chunks.

This is a **single-user local development app**, bound to loopback by default. It has no multi-user authentication, document access-control service, parser sandbox, encrypted database, or cloud production deployment. Keep it local and use files you intend to index. Document content is untrusted evidence; prompts do not grant it authority. The agent has no shell, arbitrary SQL, web, or external-action tools.

## Project structure

```text
app.py               Streamlit chat, evidence panels, library, settings and charts
ragbot/ingest.py      file parsing, limits, chunking, logical source locations
ragbot/store.py       transactional SQLite storage, FTS5 and vector metadata
ragbot/agent.py       bounded tool routing, decimal calculations, retrieval, citations
ragbot/ollama.py      optional loopback-only model API adapter
ragbot/tool_agent.py  bounded local-model planner/writer using real MCP calls
ragbot/settings.py    persistent local model preferences
ragbot/local_runtime.py  pinned Ollama setup/start helper
ragbot/cli.py         terminal ingest/list/ask commands
sample_data/         real public starter CSVs and source methodology/provenance
tests/               ingestion, calculation, retrieval, model-contract and UI checks
```

Terminal usage:

```powershell
.\.venv\Scripts\python.exe -m ragbot.cli ingest sample_data/annual.csv sample_data/source_notes.md
.\.venv\Scripts\python.exe -m ragbot.cli ask "Compare home price in 2000 and 2024"
.\.venv\Scripts\python.exe -m ragbot.cli list
.\.venv\Scripts\python.exe -m ragbot.cli ask "mean income" --evidence-only
```

Put `--db PATH` **before** the subcommand for a separate library. The app also supports the `RAGBOT_DB` environment variable, used by tests to isolate their databases.

## MCP tools

The project also exposes seven simple read-only tools over MCP stdio: status, document listing/search, cited Q&A, table listing/preview, and numeric column summaries. See [MCP.md](MCP.md) for setup, client configuration, the runnable client demo, and tool examples. No MCP host configuration is changed automatically.

Run **Setup MCP.bat** to prepare the optional SDK dependency. The ordinary Streamlit app remains available through Start.bat.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

Unit tests use temporary databases, real MCP tool execution and mocked model responses; they do not need to run the live model. `scripts/verify_local_model.py` separately exercises actual local weights against the real sample index. See [VALIDATION.md](VALIDATION.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
