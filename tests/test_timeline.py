import sys
from pathlib import Path

# Set up path for root i.e., skyvault
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src" # Create a relative path starting from this root directory

# (I believe it means) If there doesn't exist such path, add into the system so it exists
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# from skyvault import timeline

# Set up path to read the output file for tests
textfile_path = REPO_ROOT / "output" / "timeline.txt"

with open(textfile_path, "r") as f:

    textfile = f.read()

    # Check if the output file is text
    def test_type_str():

        for line in textfile:

            assert isinstance(line, str)

    # Check if the header is written into the textfile
    def test_header_exists():

        assert "SKYVAULT Tactical Reference Timeline" in textfile
        assert "tactical_reference_001" in textfile

    # Check if "Tick" is mentioned in the textfile
    def test_tick():

        assert "Tick" in textfile

    # Check if any events is converted into human-readable text
    def test_events():

        assert "selected" or "moved" or "attacked" or "missed" or "destroyed" or "Scenario ended" in textfile

    # Check if sentences can be written into timeline.txt
    def test_writing_file():

        assert textfile_path.is_file()

