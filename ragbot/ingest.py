"""Turn untrusted file bytes into text chunks and bounded, typed table records.

Nothing here executes scripts, spreadsheet formulas, macros, or instructions in
documents. Source locators survive extraction so answers can cite actual rows/pages.
"""
from dataclasses import dataclass, field
from io import BytesIO, StringIO
import csv
import json
from pathlib import Path
import re
import zipfile

import pandas as pd
from openpyxl import load_workbook
from pypdf import PdfReader

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000
MAX_TEXT_CHARS = 2_000_000
MAX_CHUNKS = 4000
SUPPORTED = ("txt", "md", "csv", "json", "pdf", "xlsx")


@dataclass
class Chunk:
    locator: str
    content: str


@dataclass
class Table:
    name: str
    columns: list[str]
    rows: list[dict[str, str]]


@dataclass
class Parsed:
    name: str
    chunks: list[Chunk] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def decode_text(payload):
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Text files must be UTF-8. Export the file as UTF-8 and try again.") from error


def text_chunks(text: str, locator: str, target=1100, overlap=160):
    text = text.replace("\x00", "").replace("\r\n", "\n")
    chunks, start = [], 0
    while start < len(text):
        end = min(start + target, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + target // 2, end)
            if boundary > start:
                end = boundary
        content = text[start:end].strip()
        if content:
            chunks.append(Chunk(f"{locator} · characters {start + 1}–{end}", content))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def column_names(values):
    seen, columns = set(), []
    for index, value in enumerate(values):
        original = str(value).strip() if value is not None else ""
        original = original or f"column_{index + 1}"
        candidate, suffix = original, 2
        while candidate in seen:
            candidate = f"{original}_{suffix}"
            suffix += 1
        seen.add(candidate)
        columns.append(candidate)
    if len(columns) > 200:
        raise ValueError("Tables are limited to 200 columns.")
    return columns


def attach_table(parsed, name, headers, records):
    columns = column_names(headers)
    if len(records) > MAX_ROWS:
        raise ValueError(f"Tables are limited to {MAX_ROWS:,} rows.")
    rows = []
    for record in records:
        if not record:
            record = [""] * len(columns)  # Preserve blank row positions for citations.
        if len(record) != len(columns):
            raise ValueError("A table row has a different number of fields than its header.")
        rows.append({column: "" if value is None else str(value) for column, value in zip(columns, record)})
    table = Table(name, columns, rows)
    parsed.tables.append(table)
    # Smaller table chunks make row citations useful without sending an entire
    # spreadsheet to a language model. Header row is row 1; data starts at row 2.
    for start in range(0, len(rows), 8):
        subset = rows[start:start + 8]
        content = "Table: " + name + "\n" + "\n".join(
            f"Row {start + offset + 2}: " + "; ".join(f"{key}={value}" for key, value in row.items())
            for offset, row in enumerate(subset))
        if len(content) > 10_000:
            raise ValueError("A table chunk is too large; shorten very long cell contents.")
        parsed.chunks.append(Chunk(f"{name} · rows {start + 2}–{start + len(subset) + 1}", content))


def parse_file(name: str, payload: bytes) -> Parsed:
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise ValueError("Choose a nonempty file no larger than 20 MB.")
    safe_name = Path(name.replace("\\", "/")).name
    extension = Path(safe_name).suffix.lower().lstrip(".")
    if extension not in SUPPORTED:
        raise ValueError("Supported files: TXT, Markdown, CSV, JSON, text PDF, and XLSX.")
    parsed = Parsed(safe_name)
    if extension in ("txt", "md"):
        text = decode_text(payload)
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError("Extracted text exceeds the two-million-character limit.")
        parsed.chunks = text_chunks(text, "text")
    elif extension == "csv":
        text = decode_text(payload)
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        records = list(csv.reader(StringIO(text), dialect))
        if not records:
            raise ValueError("CSV is empty.")
        attach_table(parsed, "CSV", records[0], records[1:])
    elif extension == "json":
        try:
            data = json.loads(decode_text(payload))
        except (json.JSONDecodeError, RecursionError) as error:
            raise ValueError("JSON is malformed or too deeply nested.") from error
        if isinstance(data, list) and data and all(isinstance(row, dict) and all(not isinstance(value, (dict, list)) for value in row.values()) for row in data):
            headers = list(dict.fromkeys(key for row in data for key in row))
            attach_table(parsed, "JSON records", headers, [[row.get(key, "") for key in headers] for row in data])
        else:
            text = json.dumps(data, indent=2, ensure_ascii=False)
            if len(text) > MAX_TEXT_CHARS:
                raise ValueError("JSON text exceeds extraction limits.")
            parsed.chunks = text_chunks(text, "JSON")
    elif extension == "pdf":
        try:
            reader = PdfReader(BytesIO(payload))
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported. Upload a decrypted copy.")
            if len(reader.pages) > 500:
                raise ValueError("PDFs are limited to 500 pages.")
            total = 0
            for index, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                total += len(text)
                if total > MAX_TEXT_CHARS:
                    raise ValueError("PDF extracted text exceeds limits.")
                parsed.chunks.extend(text_chunks(text, f"page {index + 1}"))
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f"Could not extract this PDF: {type(error).__name__}") from error
        parsed.warnings.append("PDF extraction reads embedded text, not OCR. Table layout may not be preserved.")
    elif extension == "xlsx":
        # Bound expanded ZIP size before the workbook parser touches its parts.
        try:
            with zipfile.ZipFile(BytesIO(payload)) as archive:
                if len(archive.infolist()) > 5000 or sum(item.file_size for item in archive.infolist()) > 80 * 1024 * 1024:
                    raise ValueError("Workbook expands beyond the allowed size.")
            workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True, keep_links=False)
            if len(workbook.worksheets) > 25:
                raise ValueError("Workbooks are limited to 25 sheets.")
            for sheet in workbook.worksheets:
                iterator = sheet.iter_rows(values_only=True)
                headers = next(iterator, None)
                if not headers:
                    continue
                records = []
                for row in iterator:
                    records.append(row)
                    if len(records) > MAX_ROWS:
                        raise ValueError("Workbook sheet has too many rows.")
                attach_table(parsed, sheet.title, headers, records)
            workbook.close()
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f"Could not read this workbook: {type(error).__name__}") from error
        parsed.warnings.append("XLSX uses the first row as headers and cached formula values; formulas/macros are never executed.")
    if not parsed.chunks:
        raise ValueError("No readable content found. Scanned PDFs need OCR before upload.")
    if len(parsed.chunks) > MAX_CHUNKS or sum(len(chunk.content) for chunk in parsed.chunks) > MAX_TEXT_CHARS * 2:
        raise ValueError("Document produces too much indexed content; split it into smaller files.")
    return parsed
