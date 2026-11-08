# Validation

Checked locally on Windows with Python 3.12 and the pinned application dependencies.

- Thirty-one pytest tests cover the original chatbot, MCP integration, and local-model agent workflow.
- Tested text/Markdown, CSV, flat JSON, XLSX cached values and blank rows, PDF text extraction with page citations, and scanned/empty PDF rejection.
- Tested content deduplication, transactional indexing, document-scoped retrieval, deletion of original content and FTS entries, and unknown-question behavior.
- Tested deterministic decimal sums/means, large integer precision, exact-year comparisons, unsupported-filter refusal and row citations.
- Tested optional semantic indexing, rank fusion, model-answer citations, invalid-citation fallback and unavailable-model fallback with mocked Ollama APIs.
- Tested loopback-only endpoint validation and the separation between system instructions and untrusted source content.
- Streamlit AppTest loads the public corpus and submits a chat question through the interface without exceptions.
- A temporary loopback Streamlit server returned successful HTTP responses for its page and health endpoint, then was stopped.
- Real public sample questions calculate new-home price changes and same-age living-with-spouse changes from the indexed source CSVs, with logical row references.

The pinned Ollama Windows runtime 0.40.15 and local qwen3:4b weights are now installed in this project. Actual local-model generation was verified against real MCP queries and the existing sample data. The runtime archive SHA-256 was checked against the official release digest, and the server was launched with cloud features disabled. No cloud AI provider, API key or ChatGPT subscription is used. Optional semantic embedding quality has not been benchmarked; the default agent uses MCP keyword/table tools.

Evidence-only mode is extractive retrieval plus bounded calculations, not an LLM. Citation syntax checks do not establish that a generated claim is supported by its citation. PDF extraction does not include OCR. This is a single-user local application, without authentication, encrypted storage, or a parser sandbox.

Git was initialized locally; nothing was pushed to GitHub. Public sample files retain their original provenance manifest and methodology notes.

## Local Ollama agent

- The default app mode is Ollama with qwen3:4b; model preferences persist locally. Evidence mode is an explicit fallback.
- Real local-generation checks cover home prices in 2000 versus 2024, methodological limits, and table schemas, all with MCP citations. Warm examples on this computer took approximately 6–40 seconds; cold loads/context processing can take longer.
- Unit tests mock model replies while using real MCP subprocess calls. They exercise additional retrieval, schema discovery, document-scope isolation, rejected tools, source-ID repair, turn limits, offline fallbacks, model validation and preferences.
- Numeric answers still use the local model to write the response after verified decimal calculations. Planning text and truncated final output are not shown as the user answer.
- Structured final replies supply answer and source IDs. If inline markers are absent, the adapter renders validated IDs as a Sources footer. This validates IDs, not factual entailment.
- No shell, arbitrary SQL, file-writing or web tool is exposed. Tool rounds/calls are bounded. Selected-file scope is enforced in the MCP server, including table-ID guesses.
- No global PATH, Windows service or startup task was installed. Project-local Ollama can remain running separately from Streamlit; keep-alive unloads idle weights. See OLLAMA.md.

## MCP extension

- Official MCP Python SDK 2.3.0 is pinned in requirements-mcp.txt and verified compatible with the app environment.
- All seven read-only tools are discovered and called over actual MCP, both in-process and through a stdio subprocess.
- The subprocess checks cover automatic/current discovery and the legacy initialization mode, a different working directory, and an index path containing spaces.
- Checked typed structured output, input bounds, unknown document/table/column errors, pagination, source citations, decimal column summaries, and the overview resource.
- An attempted database DELETE through the server's connection is rejected by SQLite. Missing indexes are not silently created.
- The example MCP client calls the new server against the existing public sample index. No external MCP host configuration is edited automatically.
