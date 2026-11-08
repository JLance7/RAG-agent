"""A bounded tool-using Q&A workflow: calculate -> retrieve -> answer -> cite.

The agent cannot execute Python, shell commands, arbitrary SQL, or web requests
from model output. Exact table operations take precedence over generated prose.
"""
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
import json
import math
import re

import pandas as pd

from .store import tokens


@dataclass
class Answer:
    text: str
    engine: str
    sources: list[dict] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    warning: str = ""


def cosine(left, right):
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def build_embeddings(store, client, model, document_ids=None):
    chunks = store.chunks(document_ids)
    pending = [chunk for chunk in chunks if chunk["embedding_model"] != model or not chunk["embedding"]]
    if len(pending) > 5000:
        raise ValueError("Select fewer files: semantic indexing is limited to 5,000 chunks per operation.")
    for start in range(0, len(pending), 16):
        batch = pending[start:start + 16]
        vectors = client.embed(model, [chunk["content"] for chunk in batch])
        store.set_embeddings(model, [(chunk["id"], vector) for chunk, vector in zip(batch, vectors)])
    return len(pending)


def retrieve(store, question, document_ids=None, top_k=5, client=None, embedding_model=""):
    lexical = store.search(question, document_ids, limit=30)
    ranked, fused, semantic_count = {}, {}, 0
    for rank, hit in enumerate(lexical, 1):
        ranked[hit["id"]] = hit
        fused[hit["id"]] = 1 / (60 + rank)
    warning = ""
    if client and embedding_model:
        chunks = store.chunks(document_ids)
        embedded = [chunk for chunk in chunks if chunk["embedding_model"] == embedding_model and chunk["embedding"]]
        semantic_count = len(embedded)
        if embedded:
            query_vector = client.embed(embedding_model, [question])[0]
            scored = sorted([(cosine(query_vector, json.loads(chunk["embedding"])), chunk) for chunk in embedded], key=lambda pair: pair[0], reverse=True)
            for rank, (similarity, chunk) in enumerate(scored[:30], 1):
                if similarity <= 0:
                    continue
                ranked[chunk["id"]] = {key: chunk[key] for key in ("id", "document_id", "locator", "content", "name")}
                fused[chunk["id"]] = fused.get(chunk["id"], 0) + 1 / (60 + rank)
            if len(embedded) < len(chunks):
                warning = f"Semantic coverage: {len(embedded)} of {len(chunks)} selected chunks; remaining chunks use keyword search."
        else:
            warning = "No semantic vectors for this model. Using local keyword search; build the semantic index in Settings."
    ordered = sorted(fused, key=fused.get, reverse=True)[:top_k]
    hits = [{**ranked[identifier], "retrieval_score": fused[identifier]} for identifier in ordered]
    return hits, [f"Keyword candidates: {len(lexical)}", f"Embedded chunks available: {semantic_count}", f"Evidence chunks selected: {len(hits)}"], warning


def canonical(value):
    return " ".join(re.findall(r"[^\W_]+", str(value).lower()))


ALIASES = {
    "home_price": ["home price", "house price", "housing price", "new home price"],
    "income": ["income", "household income"],
    "mortgage_rate": ["mortgage rate", "interest rate"],
    "price_to_income": ["price to income", "price income ratio"],
    "median_age": ["marriage age", "age at marriage", "age at first marriage"],
    "living_with_spouse_pct": ["living with a spouse", "living with spouse", "spouse share"],
    "child_of_householder_pct": ["child of householder", "child of the householder"],
    "living_with_partner_pct": ["living with partner", "unmarried partner"],
}


def number(value):
    return f"{value:,.4f}".rstrip("0").rstrip(".") if value % 1 else f"{int(value):,}"


def decimal_value(value):
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
        return parsed if parsed.is_finite() and len(parsed.as_tuple().digits) <= 24 else None
    except InvalidOperation:
        return None


def calculate(question, tables):
    # This tool has a deliberately small grammar. Unsupported filters/grouping
    # must not be silently ignored and converted into a different calculation.
    if re.search(r"\b(after|before|between|since|excluding|except|without|above|below|under|over|gen z|millennials?|boomers?|grouped)\b|\bby\s+\w+", question, re.I):
        return None
    normalized = " " + canonical(question) + " "
    candidates = []
    for table in tables:
        for column in table["columns"]:
            if canonical(column) in ("year", "id", "row", "row number"):
                continue
            variants = [canonical(column), *ALIASES.get(column, [])]
            matches = [phrase for phrase in variants if " " + phrase + " " in normalized]
            if matches:
                strength = max(len(phrase.split()) + len(phrase) / 100 for phrase in matches)
                candidates.append((strength, table, column))
    operation = next((label for words, label in [(["average", "mean"], "mean"), (["sum", "total"], "sum"),
                          (["minimum", "lowest", "smallest", "min"], "min"), (["maximum", "highest", "largest", "max"], "max"), (["median"], "median")]
                      if any(re.search(r"\b" + word + r"\b", question, re.I) for word in words)), None)
    years = list(dict.fromkeys(int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", question)))
    if not candidates or not (operation or years):
        return None
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    best = candidates[0]
    tied = [candidate for candidate in candidates if candidate[0] == best[0]]
    if len(tied) > 1:
        return None  # Ambiguous dataset/column: use search, never guess a table.
    _, table, column = best
    frame = pd.DataFrame(table["rows"], columns=table["columns"])
    if frame.empty:
        return None
    frame["_source_row"] = range(2, len(frame) + 2)
    # Keep explicit age/sex groups separate; combined rows are not independent
    # observations to add to men's/women's rows in a demographic table.
    if "age_group" in frame:
        match = re.search(r"\b(18\s*[-–]\s*24|25\s*[-–]\s*34)\b", question)
        if not match:
            return None
        group = re.sub(r"\s", "", match[0]).replace("–", "-")
        frame = frame.loc[frame.age_group == group]
    if "sex" in frame:
        target = "Women" if re.search(r"\bwomen\b|\bfemale\b", question, re.I) else "Men" if re.search(r"\bmen\b|\bmale\b", question, re.I) else "All (weighted)"
        if target not in set(frame.sex):
            return None  # For marriage-age data, the question must specify sex.
        frame = frame.loc[frame.sex == target]
    frame[column] = frame[column].map(decimal_value)
    frame = frame.loc[frame[column].notna()]
    if frame.empty:
        return None
    if years:
        if "year" not in frame:
            return None
        frame["year"] = pd.to_numeric(frame.year, errors="coerce")
        frame = frame.loc[frame.year.isin(years)]
        if not all(year in set(frame.year) for year in years):
            return None
    row_numbers = frame["_source_row"].astype(int).tolist()
    location = f"{table['name']} · logical data rows " + ", ".join(map(str, row_numbers[:12])) + (f" … ({len(row_numbers)} rows)" if len(row_numbers) > 12 else "")
    source = {"name": table["document_name"], "document_id": table["document_id"], "locator": location,
              "content": frame.drop(columns="_source_row").head(15).to_csv(index=False)}
    trace = [f"Table tool: {table['document_name']} / {table['name']}", f"Validated column: {column}", f"Rows used: {len(frame)}"]
    if operation:
        values = frame[column].tolist()
        with localcontext() as context:
            context.prec = 50
            if operation in ("sum", "mean"):
                value = sum(values, Decimal(0))
                if operation == "mean":
                    value /= Decimal(len(values))
            elif operation == "median":
                ordered = sorted(values)
                middle = len(ordered) // 2
                value = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
            else:
                value = min(values) if operation == "min" else max(values)
        answer = f"The **{operation} of `{column}` is {number(value)}**, calculated from {len(frame):,} non-missing numeric rows"
        answer += f" for {', '.join(map(str, years))}" if years else " across the selected table"
        answer += ". [S1]\n\nUnits are those of the source column. The tool does not infer currencies or convert percentages."
        trace.append(f"Operation: decimal {operation} (display rounded to at most 4 decimal places)")
    else:
        if any(len(frame.loc[frame.year == year]) != 1 for year in years):
            return None
        values = [frame.loc[frame.year == year, column].iloc[0] for year in years]
        answer = "\n".join(f"- **{year}: {number(value)}** (`{column}`) [S1]" for year, value in zip(years, values))
        if len(values) == 2:
            delta = values[1] - values[0]
            unit = " percentage points" if column.endswith("_pct") else " in source units"
            answer += f"\n\nChange from {years[0]} to {years[1]}: **{number(delta)}{unit}**"
            if values[0] != 0:
                answer += f"; relative change **{delta / values[0] * 100:+.2f}%**"
            answer += ". [S1]"
        trace.append("Operation: exact year lookup" + (" and change" if len(values) == 2 else ""))
    return Answer(answer, "Deterministic table tool", [source], trace)


def extractive_answer(question, hits):
    terms = set(tokens(question))
    quotes = []
    for index, hit in enumerate(hits[:3], 1):
        sentences = re.split(r"(?<=[.!?])\s+|\n", hit["content"])
        sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
        ranked = sorted(sentences, key=lambda sentence: len(set(tokens(sentence)) & terms), reverse=True)
        excerpt = (ranked[0] if ranked else hit["content"])[:700]
        quotes.append(f"**Evidence from {hit['name']}** [S{index}]\n\n> " + excerpt.replace("\n", "\n> "))
    return "I found these passages in your indexed files. This is an **extractive evidence view**, not a model-generated explanation.\n\n" + "\n\n".join(quotes)


def ask(store, question, document_ids=None, top_k=5, client=None, chat_model="", embedding_model="", history=""):
    question = question.strip()
    if not question or len(question) > 3000:
        raise ValueError("Ask a question between 1 and 3,000 characters.")
    if client and chat_model and callable(getattr(client, "chat", None)):
        from .tool_agent import ask_ollama
        try:
            return ask_ollama(store, question, client, chat_model, document_ids, top_k, history)
        except Exception as error:
            while isinstance(error, BaseExceptionGroup) and error.exceptions:
                error = error.exceptions[0]
            fallback = ask(store, question, document_ids, top_k)
            fallback.warning = f"Ollama tool-agent generation failed ({type(error).__name__}: {str(error)[:300]}). Showing verified local evidence/calculations instead."
            return fallback
    exact = calculate(question, store.tables(document_ids))
    if exact:
        return exact
    try:
        hits, trace, warning = retrieve(store, question, document_ids, top_k, client, embedding_model)
    except Exception as error:
        hits, trace, warning = retrieve(store, question, document_ids, top_k)
        warning = f"Semantic retrieval unavailable ({type(error).__name__}); keyword retrieval used."
    if not hits:
        return Answer("I could not find supporting evidence in the selected files. Try a more specific question, select the right files, or upload the missing data.", "No matching evidence", [], trace, warning)
    # Strip internal vector fields from anything returned to the UI/history.
    sources = [{key: hit[key] for key in ("name", "document_id", "locator", "content")} for hit in hits]
    if client and chat_model:
        try:
            answer = client.generate(chat_model, question, hits, history[-3500:])
            references = [int(value) for value in re.findall(r"\[S(\d+)\]", answer)]
            if not references or any(index < 1 or index > len(hits) for index in references):
                raise ValueError("Generated answer has missing or invalid source citations.")
            return Answer(answer, f"Ollama · {chat_model}", sources, trace + ["Generated from bounded retrieved evidence"], warning)
        except Exception as error:
            warning = (warning + " " + f"Generation unavailable or citation check failed ({type(error).__name__}); evidence shown instead.").strip()
    return Answer(extractive_answer(question, hits), "Local evidence mode", sources, trace, warning)
