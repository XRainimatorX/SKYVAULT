"""Write the briefing report of a workspace as Markdown, PDF and DOCX.

    python3 scripts/dev/export_briefing.py
    python3 scripts/dev/export_briefing.py --workspace some/folder

The workspace (default: output/) needs result_package.json; the failure
exploration and batch outputs, when present, add their sections. The three
files are written into the same folder.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.report import build_briefing, render_docx, render_markdown, render_pdf
from skyvault.views import load_workspace


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export the briefing report.")
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT / "output")
    args = parser.parse_args(argv)

    briefing = build_briefing(load_workspace(args.workspace))
    (args.workspace / "briefing.md").write_text(
        render_markdown(briefing), encoding="utf-8"
    )
    (args.workspace / "briefing.pdf").write_bytes(render_pdf(briefing))
    (args.workspace / "briefing.docx").write_bytes(render_docx(briefing))

    print(briefing["title"])
    print("Sections: " + ", ".join(part["title"] for part in briefing["sections"]))
    print(f"Output: {args.workspace}")


if __name__ == "__main__":
    main()
