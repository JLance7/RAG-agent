"""Live smoke test: actual local weights + actual read-only MCP queries."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ragbot.agent import ask
from ragbot.ollama import Ollama
from ragbot.store import DEFAULT_DB, Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--question", help="Run just one specified live question.")
    parser.add_argument("--trace", action="store_true", help="Print chosen tool names and final response for diagnostics.")
    args = parser.parse_args()
    client = Ollama()
    if args.trace:
        original_plan, original_writer = client.plan, client.final_answer
        def traced_plan(*arguments):
            result = original_plan(*arguments)
            print("PLAN:", json.dumps(result), flush=True)
            return result
        def traced_writer(*arguments):
            result = original_writer(*arguments)
            print("FINAL:", result, flush=True)
            return result
        client.plan, client.final_answer = traced_plan, traced_writer
    print("Installed local models:", client.models(), flush=True)
    info = client.model_info(args.model)
    print("Model capabilities:", info.get("capabilities"), flush=True)
    results = []
    questions = [args.question] if args.question else ["Compare home price in 2000 and 2024", "What are the limits of price-to-income comparisons?",
                     "Use list_tables to show the available tables and their column names."]
    for question in questions:
        started = time.monotonic()
        print("Question:", question, flush=True)
        answer = ask(Store(args.db), question, client=client, chat_model=args.model, top_k=3)
        print(answer.engine, "in", round(time.monotonic() - started, 1), "seconds", flush=True)
        print(answer.text, flush=True)
        if not answer.engine.startswith("Ollama tool agent") or not answer.sources or "[S" not in answer.text:
            raise RuntimeError("Live local generation did not complete with cited MCP evidence: " + answer.warning)
        results.append({"question": question, "seconds": round(time.monotonic() - started, 2), **asdict(answer)})
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"model": args.model, "capabilities": info.get("capabilities"), "answers": results}, indent=2), encoding="utf-8")
    print("PASS: local model generated all answers using MCP evidence.", flush=True)


if __name__ == "__main__":
    main()
