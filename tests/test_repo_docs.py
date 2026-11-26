import re
from importlib import metadata
from pathlib import Path

import eob

ROOT = Path(__file__).resolve().parents[1]


def test_every_doc_is_listed_in_the_docs_index():
    index = (ROOT / "docs" / "README.md").read_text()
    for path in sorted((ROOT / "docs").glob("*.md")):
        if path.name != "README.md":
            assert path.name in index, f"{path.name} is missing from docs/README.md"


def test_relative_links_in_the_readme_and_docs_index_resolve():
    for name, base in (("README.md", ROOT), ("docs/README.md", ROOT / "docs")):
        text = (ROOT / name).read_text()
        for link in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            assert (base / link).exists(), f"{name}: broken link {link}"


def test_the_installed_version_matches_the_package_version():
    assert metadata.version("eob-explainer") == eob.__version__