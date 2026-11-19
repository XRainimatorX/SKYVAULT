"""The briefing says what the fixture froze, in three formats, reproducibly."""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
EXPECTED = REPO_ROOT / "tests" / "fixtures" / "briefing_reference.json"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.report import build_briefing, render_docx, render_markdown, render_pdf
from skyvault.views import load_workspace

with EXPECTED.open(encoding="utf-8") as _file:
    FROZEN = json.load(_file)


@pytest.fixture(scope="module")
def briefing(reference_workspace):
    return build_briefing(load_workspace(reference_workspace))


def text_of(part):
    return "\n".join(part["paragraphs"] + part["bullets"])


def flat(text):
    return re.sub(r"\s+", " ", text)


# ── content ──────────────────────────────────────────────────────────────────


def test_the_briefing_has_the_frozen_title_and_sections(briefing):
    assert briefing["title"] == FROZEN["title"]
    assert [part["title"] for part in briefing["sections"]] == FROZEN["sections"]


@pytest.mark.parametrize("title", list(FROZEN["must_state"]))
def test_each_section_states_what_the_fixture_froze(briefing, title):
    part = next(p for p in briefing["sections"] if p["title"] == title)

    for sentence in FROZEN["must_state"][title]:
        assert sentence in text_of(part)


def test_without_failure_or_batch_outputs_their_sections_are_left_out(
    run_only_workspace,
):
    briefing = build_briefing(load_workspace(run_only_workspace))

    assert [p["title"] for p in briefing["sections"]] == FROZEN[
        "sections_without_optional_inputs"
    ]


def test_ticks_count_what_was_done_with_plurals(briefing):
    happened = next(p for p in briefing["sections"] if p["title"] == "What happened")

    assert happened["bullets"][3] == "Tick 4: 1 miss; 5 moves"
    assert happened["bullets"][4] == "Tick 5: 4 attacks; 2 misses"


def test_the_failure_and_batch_tables_have_a_row_per_variable_and_variant(briefing):
    failure, comparison = briefing["sections"][5:7]

    assert failure["table"]["columns"] == [
        "Variable",
        "mild",
        "moderate",
        "severe",
        "collapse",
        "Breaks at",
        "Sensitivity",
    ]
    assert failure["table"]["rows"][1] == [
        "communication_failure",
        "70%",
        "80%",
        "50%",
        "0%",
        "collapse",
        "+0.60",
    ]
    assert len(comparison["table"]["rows"]) == 9
    assert comparison["table"]["rows"][1][0] == "support-rear"


# ── the three formats ────────────────────────────────────────────────────────


def every_sentence():
    return [s for sentences in FROZEN["must_state"].values() for s in sentences]


def test_markdown_carries_every_section_and_sentence(briefing):
    text = render_markdown(briefing)

    assert text.startswith(f"# {FROZEN['title']}\n")
    for title in FROZEN["sections"]:
        assert f"\n## {title}\n" in text
    for sentence in every_sentence():
        assert sentence in text
    assert "| communication_failure | 70% | 80% | 50% | 0% | collapse | +0.60 |" in text


def test_the_word_document_carries_every_section_and_sentence(briefing):
    document = Document(io.BytesIO(render_docx(briefing)))
    headings = [p.text for p in document.paragraphs if p.style.name == "Heading 1"]
    text = "\n".join(p.text for p in document.paragraphs)

    assert headings == FROZEN["sections"]
    for sentence in every_sentence():
        assert sentence in text
    assert len(document.tables) == 2
    assert document.core_properties.title == FROZEN["title"]


def test_the_pdf_carries_every_section_and_sentence(briefing):
    reader = PdfReader(io.BytesIO(render_pdf(briefing)))
    text = flat(" ".join(page.extract_text() for page in reader.pages))

    assert reader.metadata.title == FROZEN["title"]
    for title in FROZEN["sections"]:
        assert title in text
    for sentence in every_sentence():
        assert flat(sentence) in text


# ── reproducible ─────────────────────────────────────────────────────────────


def test_the_same_briefing_renders_to_the_same_bytes(briefing):
    assert render_pdf(briefing) == render_pdf(briefing)
    assert render_docx(briefing) == render_docx(briefing)


def test_the_word_document_is_dated_by_the_run_not_by_the_clock(briefing):
    data = render_docx(briefing)
    ended = datetime.fromisoformat(briefing["created"]).replace(
        tzinfo=None, microsecond=0
    )

    properties = Document(io.BytesIO(data)).core_properties
    assert properties.created.replace(tzinfo=None) == ended
    assert properties.modified.replace(tzinfo=None) == ended
    stamps = {info.date_time for info in zipfile.ZipFile(io.BytesIO(data)).infolist()}
    assert stamps == {(ended.year, ended.month, ended.day, ended.hour, ended.minute, 0)}

    other = render_docx(briefing, created=datetime(2030, 1, 2, 3, 4, 5))
    assert other != data
    assert Document(io.BytesIO(other)).core_properties.created.year == 2030


def test_the_export_is_identical_across_hash_seeds(reference_workspace, tmp_path):
    outputs = []
    for seed in ("1", "2"):
        folder = tmp_path / seed
        shutil.copytree(reference_workspace, folder)
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "dev" / "export_briefing.py"),
                "--workspace",
                str(folder),
            ],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append(
            [
                (folder / name).read_bytes()
                for name in ("briefing.md", "briefing.pdf", "briefing.docx")
            ]
        )

    assert outputs[0] == outputs[1]


@pytest.mark.parametrize(
    ("count", "kind", "words"),
    [
        (1, "miss", "1 miss"),
        (2, "miss", "2 misses"),
        (4, "attack", "4 attacks"),
        (3, "refused order", "3 refused orders"),
        (2, "resupply", "2 resupplies"),
        (2, "delay", "2 delays"),
    ],
)
def test_counts_read_as_plain_english(count, kind, words):
    from skyvault.report.briefing import _count

    assert _count(count, kind) == words
