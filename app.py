"""Data Desk: local file Q&A with retrieved evidence, citations and table tools."""
from dataclasses import asdict
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from ragbot.agent import ask, build_embeddings
from ragbot.ingest import SUPPORTED
from ragbot.ollama import Ollama
from ragbot.store import DEFAULT_DB, Store
from ragbot.settings import load_settings, save_settings

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Data Desk · Ask your files", page_icon="◈", layout="wide")
st.markdown("""<style>
.block-container{max-width:1350px;padding-top:2rem}
h1{letter-spacing:-.045em;font-weight:800!important}
.eyebrow{color:#85e0ca;letter-spacing:3px;font-size:12px;font-weight:700}
.deck{color:#adbfca;font-size:18px;line-height:1.6;max-width:850px}
div[data-testid="stMetric"]{background:#172533;border:1px solid #2c4250;border-radius:12px;padding:14px}
</style>""", unsafe_allow_html=True)

store = Store(os.environ.get("RAGBOT_DB", str(DEFAULT_DB)))
preferences = load_settings()
if "messages" not in st.session_state:
    st.session_state.messages = []
@st.cache_data(ttl=30, show_spinner=False)
def available_models(url):
    try:
        return Ollama(url).models(), ""
    except Exception as error:
        return [], f"Local Ollama is unavailable ({type(error).__name__}). Run Setup Local Model.bat, then Start.bat."


def sample_files():
    return [path for path in (ROOT / "sample_data").iterdir() if path.suffix.lower() in (".csv", ".md") and path.name != "README.md"]


def source_cards(sources, trace):
    if sources:
        with st.expander(f"Evidence & citations · {len(sources)} sources"):
            for index, source in enumerate(sources, 1):
                st.write(f"**[S{index}] {source['name']}**")
                st.caption(source["locator"] + " · file fingerprint " + source["document_id"][:12])
                st.code(source["content"][:5000], language=None)
    if trace:
        with st.expander("How this answer was produced"):
            for step in trace:
                st.write("• " + step)


with st.sidebar:
    st.markdown("### ◈ Data Desk")
    st.caption("ASK YOUR FILES. CHECK THE EVIDENCE.")
    files = st.file_uploader("Add documents or datasets", type=list(SUPPORTED), accept_multiple_files=True)
    if st.button("Index uploaded files", width="stretch", disabled=not files):
        for uploaded in files:
            try:
                result = store.ingest(uploaded.name, uploaded.getvalue())
                st.success(f"{result['name']}: " + ("already indexed" if result["duplicate"] else f"{result['chunks']} chunks indexed"))
                for warning in result["warnings"]:
                    st.warning(warning)
            except Exception as error:
                st.error(f"{uploaded.name}: {error}")
    if st.button("Load included public sample", width="stretch"):
        with st.spinner("Indexing public Gen Z Lens data and methodology…"):
            for path in sample_files():
                store.ingest(path.name, path.read_bytes())
        st.success("Public sample indexed. Duplicate files are skipped.")
    st.divider()
    documents = store.documents()
    selected_ids = st.multiselect("Search these files", options=[doc["id"] for doc in documents],
                                 default=[doc["id"] for doc in documents],
                                 format_func=lambda identifier: next(doc["name"] + " · " + identifier[:8] for doc in documents if doc["id"] == identifier))
    top_k = st.slider("Evidence chunks per answer", 2, 8, 5)
    mode = st.radio("Answer mode", ["Ollama agent · local model + RAG tools", "Local evidence + table tools"], index=1 if preferences["answer_mode"] == "evidence" else 0)
    st.caption("The Ollama model generates answers using read-only MCP retrieval and calculation tools. Evidence mode is an explicit non-LLM fallback.")
    st.caption("Documents and their index stay in storage/desk.sqlite3. Chats are held only in this browser session.")

st.markdown('<div class="eyebrow">LOCAL RAG / GROUNDED DATA ASSISTANT</div>', unsafe_allow_html=True)
st.title("Questions in. Evidence out.")
st.markdown('<div class="deck">A local Ollama model queries your files through read-only RAG tools, explains the results, '
            'and cites the evidence. Inspect the rows and every tool call behind the answer.</div>', unsafe_allow_html=True)
cards = st.columns(3)
cards[0].metric("Indexed files", len(documents))
cards[1].metric("Searchable chunks", sum(doc["chunks"] for doc in documents))
cards[2].metric("Data tables", sum(doc["tables"] for doc in documents))

chat, explorer, library, settings = st.tabs(["Ask your data", "Data explorer", "Document library", "Model & retrieval"])

with settings:
    with st.expander("MCP server · use these tools from another AI app"):
        st.write("Data Desk exposes read-only document search, cited Q&A, table previews, and numeric summaries over MCP stdio.")
        st.code(r'.venv\Scripts\python.exe mcp_server.py', language="powershell")
        st.caption("Run Setup MCP.bat once if needed, then use mcp-config.example.json in your MCP host. See MCP.md in the project folder. The host launches the server; it does not use an HTTP port.")
    st.subheader("Local response generator")
    st.write("Default: qwen3:4b through local Ollama. Setup Local Model.bat installs the project-local runtime and weights; Start.bat starts the local server. No ChatGPT subscription or cloud AI API is used.")
    endpoint = st.text_input("Ollama local URL", preferences["ollama_url"])
    if st.button("Discover installed models"):
        available_models.clear()
    installed, model_error = ([], "") if os.environ.get("RAGBOT_ANSWER_MODE") == "evidence" else available_models(endpoint)
    if model_error:
        st.warning(model_error)
    choices = list(dict.fromkeys([preferences["chat_model"], *installed, ""]))
    chat_model = st.selectbox("Local tool-capable chat model", choices, format_func=lambda value: value or "No chat model selected")
    if chat_model in installed:
        st.success(f"Local generator ready: {chat_model}. Tools and local weights are verified when you ask a question.")
    embedding_choices = list(dict.fromkeys([preferences["embedding_model"], "", *installed]))
    embedding_model = st.selectbox("Installed embedding model (optional)", embedding_choices, format_func=lambda value: value or "Keyword retrieval only")
    if st.button("Save model preferences"):
        try:
            save_settings({"ollama_url": endpoint, "chat_model": chat_model, "embedding_model": embedding_model,
                           "answer_mode": "evidence" if mode == "Local evidence + table tools" else "ollama"})
            st.success("Local model preferences saved for the next session.")
        except ValueError as error:
            st.error(str(error))
    st.caption("Choose a chat-capable model for answers and an embedding-capable model for vectors. Not every installed model supports both APIs.")
    if st.button("Build / update semantic index", disabled=not embedding_model or not selected_ids):
        try:
            with st.spinner("Embedding selected chunks locally…"):
                count = build_embeddings(store, Ollama(endpoint), embedding_model, selected_ids)
            st.success(f"Embedded {count} new/changed chunks. Search now combines vectors and keyword matches.")
        except Exception as error:
            st.error(f"Semantic indexing failed: {error}")
    st.info("No embedding model: SQLite FTS5/BM25 keyword retrieval. With vectors: cosine similarity plus reciprocal-rank fusion. "
            "Retrieval scores are ranking signals, not calibrated confidence. Model citation checks verify reference IDs, not the truth of every generated claim.")
    st.caption("Only loopback endpoints are allowed. Redirects and proxy environment settings are disabled for document/model traffic. "
               "Your Ollama configuration and selected model must themselves run locally; this app cannot audit an external service's internals.")

with chat:
    st.subheader("Ask a question")
    if not documents:
        st.info("Upload files in the sidebar or click Load included public sample to begin.")
    st.caption("Try questions about a specific file, metric, year, or section. For precise math, name a numeric column and ask for a sum, mean, median, minimum, maximum, or exact year comparison.")
    suggestions = ["Compare home price in 2000 and 2024", "What are the limits of price-to-income comparisons?",
                   "What is the mean income?", "Living with spouse for ages 18-24 in 1990 and 2023"]
    pending = None
    suggestion_columns = st.columns(2)
    for index, suggestion in enumerate(suggestions):
        if suggestion_columns[index % 2].button(suggestion, key=f"suggest_{index}", width="stretch", disabled=not selected_ids):
            pending = suggestion
    if st.button("Clear conversation", disabled=not st.session_state.messages):
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["text"])
            if message["role"] == "assistant":
                st.caption(message["engine"])
                if message.get("warning"):
                    st.warning(message["warning"])
                source_cards(message.get("sources", []), message.get("trace", []))
    question = st.chat_input("Ask about your indexed files…", disabled=not selected_ids, max_chars=3000)
    question = pending or question
    if question:
        history = "\n".join(f"{message['role']}: {message['text'][:900]}" for message in st.session_state.messages[-4:])
        st.session_state.messages.append({"role": "user", "text": question})
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Selecting tools and checking evidence…"):
                    client = Ollama(endpoint) if mode != "Local evidence + table tools" or embedding_model else None
                    answer = ask(store, question, selected_ids, top_k, client,
                                 chat_model if mode != "Local evidence + table tools" else "", embedding_model, history)
                st.markdown(answer.text)
                st.caption(answer.engine)
                if answer.warning:
                    st.warning(answer.warning)
                source_cards(answer.sources, answer.trace)
                st.session_state.messages.append({"role": "assistant", **asdict(answer)})
            except Exception as error:
                st.error(f"The question could not be completed: {error}")
    if st.session_state.messages:
        st.download_button("Download this conversation", json.dumps(st.session_state.messages, indent=2, ensure_ascii=False), "conversation.json", "application/json")

with explorer:
    st.subheader("Inspect and visualize the actual rows")
    tables = store.tables(selected_ids)
    if tables:
        table_id = st.selectbox("Dataset / sheet", [table["id"] for table in tables],
                                format_func=lambda identifier: next(f"{table['document_name']} · {table['name']}" for table in tables if table["id"] == identifier))
        table = next(table for table in tables if table["id"] == table_id)
        frame = pd.DataFrame(table["rows"], columns=table["columns"])
        st.caption(f"{len(frame):,} logical data records · first source data row is 2. Blank rows are retained. No formulas are executed.")
        filter_column = st.selectbox("Optional equality filter", ["", *table["columns"]], format_func=lambda value: value or "No filter")
        if filter_column:
            choices = sorted(frame[filter_column].astype(str).unique().tolist())
            if len(choices) <= 1000:
                value = st.selectbox("Keep rows equal to", choices)
                frame = frame.loc[frame[filter_column].astype(str) == value]
            else:
                value = st.text_input("Keep rows equal to (exact text)")
                if value:
                    frame = frame.loc[frame[filter_column].astype(str) == value]
        st.dataframe(frame, hide_index=True, width="stretch")
        numeric = {column: pd.to_numeric(frame[column].str.replace(",", "", regex=False), errors="coerce") for column in table["columns"]}
        numeric_columns = [column for column, values in numeric.items() if values.notna().any()]
        if numeric_columns and not frame.empty:
            options = st.columns(3)
            x_column = options[0].selectbox("Chart X", table["columns"])
            default_y = next((index for index, column in enumerate(numeric_columns) if column != x_column), 0)
            y_column = options[1].selectbox("Chart numeric Y", numeric_columns, index=default_y)
            kind = options[2].selectbox("Chart type", ["Line", "Bar", "Scatter"])
            plotted = frame[[x_column, y_column]].copy() if x_column != y_column else frame[[x_column]].copy()
            plotted[y_column] = numeric[y_column]
            if x_column in numeric_columns:
                plotted[x_column] = numeric[x_column]
            plotted = plotted.dropna(subset=[y_column]).head(5000)
            figure = {"Line": px.line, "Bar": px.bar, "Scatter": px.scatter}[kind](plotted, x=x_column, y=y_column, color_discrete_sequence=["#85E0CA"])
            figure.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=380)
            st.plotly_chart(figure, width="stretch")
            st.caption("Chart uses up to the first 5,000 filtered records, in source order; it does not silently aggregate duplicate X values. Non-numeric Y values are excluded.")
        st.download_button("Download filtered rows", frame.to_csv(index=False), "filtered_data.csv", "text/csv")
    else:
        st.info("CSV, XLSX, and flat JSON records appear here after indexing.")

with library:
    st.subheader("Your indexed sources")
    st.caption(f"Local database: {store.path}")
    for document in documents:
        with st.expander(f"{document['name']} · {document['chunks']} chunks · {document['tables']} tables"):
            st.caption(f"Imported UTC: {document['imported_at']} · SHA-256: {document['id']} · {document['bytes']:,} bytes")
            for warning in json.loads(document["warnings"]):
                st.warning(warning)
            original = store.original(document["id"])
            if original:
                st.download_button("Download original file", original[1], original[0], key=f"original_{document['id']}")
            confirmed = st.checkbox("Confirm removal of this file and its index", key=f"confirm_{document['id']}")
            if st.button("Remove file", key=f"delete_{document['id']}", disabled=not confirmed):
                store.delete(document["id"])
                st.session_state.messages = []  # No stale citations to removed files.
                st.rerun()
    st.info("Uploaded content is treated as evidence, never as instructions. This app does not run code from documents, "
            "execute arbitrary SQL, browse the web, or perform external actions from model output. Generated answers can still be wrong: inspect their cited excerpts.")
