"""RAG index = find the runs a question is about (vector store later).

Important:
Pure and deterministic: an inverted index from lower-case word tokens to
the documents that contain them. query ranks documents by how many of the
question's distinct tokens they contain, then by their order in the index.
The technology list names a RAG index now and a vector store later; this
is the index, with no embedding model.
"""

import re
from typing import Any

TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    """Lower-case word tokens, underscores and punctuation as separators."""
    return TOKEN.findall(text.lower().replace("_", " "))


def build_rag_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """{documents, postings}: each document needs doc_id and text."""
    postings: dict[str, list[int]] = {}
    for position, document in enumerate(documents):
        for token in sorted(set(tokens(document["text"]))):
            postings.setdefault(token, []).append(position)
    return {
        "documents": list(documents),
        "postings": dict(sorted(postings.items())),
    }


def query(index: dict[str, Any], text: str, k: int = 5) -> list[dict[str, Any]]:
    """The k documents sharing most distinct tokens with text, best first."""
    hits: dict[int, int] = {}
    for token in set(tokens(text)):
        for position in index["postings"].get(token, []):
            hits[position] = hits.get(position, 0) + 1
    ranked = sorted(hits.items(), key=lambda item: (-item[1], item[0]))[:k]
    return [
        {**index["documents"][position], "matched_tokens": count}
        for position, count in ranked
    ]


def run_document(entry: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    """The searchable summary of one run (an anti-gaming report entry + package)."""
    evaluation = package["evaluation_result"]
    text = " ".join(
        [
            entry["scenario_id"],
            entry["scenario_version"],
            entry.get("domain") or "",
            evaluation["winner_or_result"],
            evaluation["overall_judgement"]["status"],
            entry["bucket"],
            entry["success_type"],
            *entry["labels"],
            *evaluation["failure_causes"],
            *evaluation["key_findings"],
        ]
    )
    return {
        "doc_id": f"{entry['scenario_id']}/{entry['scenario_version']}@{entry['seed']}",
        "output_hash": entry["output_hash"],
        "bucket": entry["bucket"],
        "success_type": entry["success_type"],
        "text": text,
    }
