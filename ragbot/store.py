"""SQLite document store with transactional FTS5 indexing. No pickled objects."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .ingest import parse_file

DEFAULT_DB = Path(__file__).resolve().parents[1] / "storage" / "desk.sqlite3"
STOP = set("a an the is are was were be been to of in on at by for from and or with about what how does did do can you me tell please it its that this as which".split())


def tokens(text):
    return [word for word in re.findall(r"[^\W_]+", text.lower()) if word not in STOP and len(word) > 1][:40]


class Store:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, original BLOB NOT NULL,
                    imported_at TEXT NOT NULL, warnings TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    locator TEXT NOT NULL, content TEXT NOT NULL,
                    embedding_model TEXT, embedding TEXT);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search USING fts5(content, tokenize='unicode61');
                CREATE TRIGGER IF NOT EXISTS chunk_insert AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunk_search(rowid,content) VALUES(new.id,new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS chunk_delete AFTER DELETE ON chunks BEGIN
                    DELETE FROM chunk_search WHERE rowid=old.id;
                END;
                CREATE TABLE IF NOT EXISTS data_tables (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, columns_json TEXT NOT NULL, rows_json TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, name, payload):
        document_id = hashlib.sha256(payload).hexdigest()
        with self.connection() as db:
            existing = db.execute("SELECT name FROM documents WHERE id=?", (document_id,)).fetchone()
            if existing:
                return {"name": existing["name"], "duplicate": True, "warnings": []}
        parsed = parse_file(name, payload)
        with self.connection() as db:
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?)", (document_id, parsed.name, payload, datetime.now(timezone.utc).isoformat(), json.dumps(parsed.warnings)))
            db.executemany("INSERT INTO chunks(document_id,locator,content) VALUES(?,?,?)",
                           [(document_id, chunk.locator, chunk.content) for chunk in parsed.chunks])
            db.executemany("INSERT INTO data_tables(document_id,name,columns_json,rows_json) VALUES(?,?,?,?)",
                           [(document_id, table.name, json.dumps(table.columns), json.dumps(table.rows, ensure_ascii=False)) for table in parsed.tables])
        return {"name": parsed.name, "duplicate": False, "chunks": len(parsed.chunks), "tables": len(parsed.tables), "warnings": parsed.warnings}

    def documents(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("""SELECT d.id,d.name,d.imported_at,length(d.original) bytes,d.warnings,
                (SELECT count(*) FROM chunks c WHERE c.document_id=d.id) chunks,
                (SELECT count(*) FROM data_tables t WHERE t.document_id=d.id) tables
                FROM documents d ORDER BY d.imported_at""")]

    def tables(self, document_ids=None):
        with self.connection() as db:
            rows = db.execute("SELECT t.*,d.name document_name FROM data_tables t JOIN documents d ON d.id=t.document_id ORDER BY t.id").fetchall()
        allowed = set(document_ids) if document_ids is not None else None
        return [{**dict(row), "columns": json.loads(row["columns_json"]), "rows": json.loads(row["rows_json"])}
                for row in rows if allowed is None or row["document_id"] in allowed]

    def search(self, question, document_ids=None, limit=16):
        words = list(dict.fromkeys(tokens(question)))
        if not words or document_ids == []:
            return []
        expression = " OR ".join('"' + word + '"' for word in words)
        condition, params = "", [expression]
        if document_ids is not None:
            condition = " AND c.document_id IN (" + ",".join("?" for _ in document_ids) + ")"
            params.extend(document_ids)
        params.append(limit)
        with self.connection() as db:
            rows = db.execute("""SELECT c.id,c.document_id,c.locator,c.content,d.name,
                bm25(chunk_search) rank FROM chunk_search JOIN chunks c ON c.id=chunk_search.rowid
                JOIN documents d ON d.id=c.document_id WHERE chunk_search MATCH ?""" + condition + " ORDER BY rank LIMIT ?", params).fetchall()
        return [dict(row) for row in rows]

    def chunks(self, document_ids=None):
        with self.connection() as db:
            rows = db.execute("SELECT c.*,d.name FROM chunks c JOIN documents d ON c.document_id=d.id ORDER BY c.id").fetchall()
        return [dict(row) for row in rows if document_ids is None or row["document_id"] in document_ids]

    def set_embeddings(self, model, values):
        with self.connection() as db:
            db.executemany("UPDATE chunks SET embedding_model=?,embedding=? WHERE id=?",
                           [(model, json.dumps(vector), identifier) for identifier, vector in values])

    def delete(self, document_id):
        with self.connection() as db:
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))

    def original(self, document_id):
        with self.connection() as db:
            row = db.execute("SELECT name,original FROM documents WHERE id=?", (document_id,)).fetchone()
        return (row["name"], bytes(row["original"])) if row else None
