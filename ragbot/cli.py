"""Simple terminal entry points for indexing and checking answers."""
import argparse
from pathlib import Path

from .agent import ask
from .store import DEFAULT_DB, Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    subcommands = parser.add_subparsers(dest="command", required=True)
    ingest = subcommands.add_parser("ingest")
    ingest.add_argument("files", nargs="+", type=Path)
    query = subcommands.add_parser("ask")
    query.add_argument("question")
    query.add_argument("--evidence-only", action="store_true", help="Skip Ollama and return only evidence/calculations.")
    query.add_argument("--model", help="Override the configured local model for this question.")
    subcommands.add_parser("list")
    args = parser.parse_args()
    store = Store(args.db)
    if args.command == "ingest":
        for path in args.files:
            print(store.ingest(path.name, path.read_bytes()))
    elif args.command == "list":
        for document in store.documents():
            print(document["name"], document["chunks"], "chunks")
    else:
        from .ollama import Ollama
        from .settings import load_settings
        settings = load_settings()
        use_model = not args.evidence_only and settings["answer_mode"] != "evidence"
        answer = ask(store, args.question, client=Ollama(settings["ollama_url"]) if use_model else None,
                     chat_model=(args.model or settings["chat_model"]) if use_model else "")
        print(answer.text)
        if answer.warning:
            print(answer.warning)
        for index, source in enumerate(answer.sources, 1):
            print(f"[S{index}] {source['name']} · {source['locator']}")


if __name__ == "__main__":
    main()
