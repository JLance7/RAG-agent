"""Mock only the LLM; tool discovery and data queries use the real MCP server."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ragbot.agent import ask
from ragbot.ollama import Ollama
from ragbot.settings import load_settings, save_settings
from ragbot.store import Store


@pytest.fixture
def indexed(tmp_path):
    store = Store(tmp_path / "library.sqlite3")
    store.ingest("visible.md", b"The retention policy keeps reports for fourteen days.")
    store.ingest("secret.md", b"The restricted launch code is 987654.")
    store.ingest("revenue.csv", b"year,revenue\n2023,100.10\n2024,200.20\n")
    return store


class ToolModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def model_info(self, model):
        return {"capabilities": ["tools", "completion"]}

    def chat(self, model, messages, tools):
        self.requests.append(json.loads(json.dumps({"messages": messages, "tools": tools})))
        return next(self.responses)


def tool_call(name, arguments):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def test_ollama_generates_numeric_response_after_real_mcp_tool(indexed):
    model = ToolModel([{"role": "assistant", "content": "Revenue rose from 100.1 to 200.2 in the source units. [S1]"}])
    answer = ask(indexed, "Compare revenue in 2023 and 2024", client=model, chat_model="test-local")
    assert answer.engine == "Ollama tool agent · test-local"
    assert answer.sources and "MCP tool 1: ask_question" in answer.trace[0]
    assert "untrusted DATA" in model.requests[0]["messages"][0]["content"]
    assert model.requests[0]["messages"][-1]["role"] == "tool"
    assert "200.2" in model.requests[0]["messages"][-1]["content"]


def test_model_can_request_additional_retrieval_tools(indexed):
    model = ToolModel([tool_call("search_documents", {"query": "retention", "limit": 2}),
                       {"role": "assistant", "content": "Reports are retained for fourteen days. [S1]"}])
    answer = ask(indexed, "What is the retention policy?", client=model, chat_model="local")
    assert answer.engine.startswith("Ollama tool agent")
    assert any("MCP tool 2: search_documents" in step for step in answer.trace)
    assert any(message.get("tool_name") == "search_documents" for message in model.requests[-1]["messages"])


def test_selected_file_scope_cannot_be_bypassed(indexed):
    visible = next(doc["id"] for doc in indexed.documents() if doc["name"] == "visible.md")
    model = ToolModel([tool_call("search_documents", {"query": "launch"}),
                       tool_call("preview_table", {"table_id": indexed.tables()[0]["id"]}),
                       {"role": "assistant", "content": "Reports are retained fourteen days. [S1]"}])
    answer = ask(indexed, "retention policy", [visible], client=model, chat_model="local")
    assert answer.engine.startswith("Ollama tool agent")
    assert all(source["name"] == "visible.md" for source in answer.sources)
    assert "987654" not in json.dumps(model.requests)
    assert "Unknown table" in json.dumps(model.requests)


def test_disallowed_tool_is_never_executed(indexed):
    model = ToolModel([tool_call("run_shell", {"command": "anything"}),
                       {"role": "assistant", "content": "Reports are retained fourteen days. [S1]"}])
    answer = ask(indexed, "retention policy", client=model, chat_model="local")
    assert answer.engine.startswith("Ollama tool agent")
    assert "disallowed" in json.dumps(model.requests[-1]["messages"])


def test_invalid_citation_gets_a_bounded_repair(indexed):
    model = ToolModel([{"content": "Invalid source [S999]"}, {"content": "Fourteen days. [S1]"}])
    answer = ask(indexed, "retention policy", client=model, chat_model="local")
    assert answer.engine.startswith("Ollama tool agent") and len(model.requests) == 2


def test_no_evidence_does_not_accept_unsupported_model_claim(indexed):
    model = ToolModel([{"content": "The answer is an invented fact. [S1]"}])
    answer = ask(indexed, "zyxwvutsrqponmlk", [], client=model, chat_model="local")
    assert not answer.sources and "did not find" in answer.text
    assert "invented" not in answer.text


def test_turn_limit_returns_explicit_evidence_fallback(indexed):
    model = ToolModel([tool_call("get_status", {}) for _ in range(4)])
    answer = ask(indexed, "retention policy", client=model, chat_model="local")
    assert answer.engine == "Local evidence mode" and answer.warning
    assert len(model.requests) == 4


def test_remote_and_non_tool_models_rejected(monkeypatch):
    client = Ollama()
    with pytest.raises(ValueError, match="cloud"):
        client.model_info("model:cloud")
    monkeypatch.setattr(client, "request", lambda *args: {"remote_host": "https://elsewhere", "capabilities": ["tools"]})
    with pytest.raises(ValueError, match="remotely"):
        client.model_info("remote-alias")
    monkeypatch.setattr(client, "request", lambda *args: {"capabilities": ["completion"]})
    with pytest.raises(ValueError, match="tool calling"):
        client.model_info("no-tools")


def test_local_preferences_persist(tmp_path, monkeypatch):
    monkeypatch.delenv("RAGBOT_ANSWER_MODE", raising=False)
    path = tmp_path / "settings.json"
    defaults = load_settings(path)
    assert defaults["answer_mode"] == "ollama" and defaults["chat_model"] == "qwen3:4b"
    save_settings({**defaults, "chat_model": "other:local"}, path)
    assert load_settings(path)["chat_model"] == "other:local"
    with pytest.raises(ValueError):
        save_settings({**defaults, "ollama_url": "https://example.com"}, path)


def test_ui_defaults_to_ollama(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGBOT_DB", str(tmp_path / "ui.sqlite3"))
    monkeypatch.delenv("RAGBOT_ANSWER_MODE", raising=False)
    monkeypatch.setattr(Ollama, "models", lambda self: ["qwen3:4b"])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=40).run()
    assert not app.exception
    assert next(item for item in app.radio if item.label == "Answer mode").value.startswith("Ollama agent")
    assert next(item for item in app.selectbox if item.label == "Local tool-capable chat model").value == "qwen3:4b"


def test_numeric_answers_are_written_by_local_model(indexed):
    class Writer(ToolModel):
        def final_answer(self, model, question, sources, results, history=""):
            assert sources and "200.2" in results[0]
            return "Revenue in 2024 is 200.2 source units. [S1]"
    model = Writer([])
    answer = ask(indexed, "Revenue in 2024", client=model, chat_model="local")
    assert answer.engine.startswith("Ollama tool agent")
    assert any("final-answer writer" in step for step in answer.trace)
    assert not model.requests  # No redundant planning step for a verified numeric lookup.


def test_final_writer_is_structured_and_rejects_truncation(monkeypatch):
    client, captured = Ollama(), {}
    def request(endpoint, payload):
        captured.update(payload)
        return {"done_reason": "stop", "message": {"content": '{"answer":"Fourteen days. [S1]","source_ids":[1]}'}}
    monkeypatch.setattr(client, "request", request)
    sources = [{"name": "policy", "locator": "text", "content": "fourteen days"}]
    assert client.final_answer("local", "retention", sources, []) == "Fourteen days. [S1]"
    assert captured["format"]["required"] == ["answer", "source_ids"] and captured["think"] is False
    monkeypatch.setattr(client, "request", lambda *args: {"done_reason": "length", "message": {"content": '{"answer":"partial [S1]"}'}})
    with pytest.raises(ValueError, match="token limit"):
        client.final_answer("local", "retention", sources, [])


def test_structured_tool_planning_adapter(monkeypatch):
    client = Ollama()
    captured = {}
    def request(endpoint, payload):
        captured.update(payload)
        return {"done_reason": "stop", "message": {"content": '{"ready":false,"tool_calls":[{"name":"list_tables","arguments":{}}]}'}}
    monkeypatch.setattr(client, "request", request)
    result = client.plan("local", [{"role": "system", "content": "rules"}, {"role": "user", "content": "list tables"}],
                         [{"type": "function", "function": {"name": "list_tables", "description": "List indexed schemas", "parameters": {"type": "object"}}}])
    assert result["tool_calls"][0]["function"]["name"] == "list_tables"
    assert captured["format"]["properties"]["tool_calls"]


def test_metadata_questions_use_discovery_tool(indexed):
    class Writer(ToolModel):
        def final_answer(self, model, question, sources, results, history=""):
            assert sources[0]["name"] == "revenue.csv"
            assert "indexed table schema" in sources[0]["locator"]
            assert "year" in results[0] and "revenue" in results[0]
            return "The revenue table has year and revenue columns. [S1]"
    answer = ask(indexed, "Show the available tables and columns", client=Writer([]), chat_model="local")
    assert answer.engine.startswith("Ollama tool agent")
    assert "list_tables" in answer.trace[0]


def test_final_writer_validates_ids_and_renders_source_footer(monkeypatch):
    client = Ollama()
    sources = [{"name": "table.csv", "locator": "schema", "content": "year,amount"}]
    response = {"done_reason": "stop", "message": {"content": '{"answer":"The columns are year and amount.","source_ids":[1]}'}}
    monkeypatch.setattr(client, "request", lambda *args: response)
    assert client.final_answer("local", "columns?", sources, []).endswith("Sources: [S1]")
    response["message"]["content"] = '{"answer":"Unknown reference","source_ids":[99]}'
    with pytest.raises(ValueError, match="source IDs"):
        client.final_answer("local", "columns?", sources, [])
