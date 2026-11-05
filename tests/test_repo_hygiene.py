from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_protects_data_and_secrets():
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert "data/" in lines
    assert ".env" in lines
