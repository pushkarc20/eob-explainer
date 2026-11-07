"""Fetch ExplanationOfBenefit resources for ONE synthetic beneficiary
from the CMS Blue Button 2.0 sandbox (synthetic data only).

The access token is read from the BB_TOKEN environment variable
(never pass tokens on the command line: they end up in shell history).

Usage:
    python scripts/fetch_sandbox_eobs.py BBUser10000

Output: data/raw/<label>/<eob id>.json  (data/ is gitignored)
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HOST = "sandbox.bluebutton.cms.gov"
START_URL = f"https://{HOST}/v2/fhir/ExplanationOfBenefit/"
MAX_PAGES = 3  # cap the download; this is a test-data pull
ROOT = Path(__file__).resolve().parents[1]


def get_json(url: str, token: str) -> dict:
    # Only ever send the token to the sandbox host. The "next page" link comes
    # from the server's response, so we verify it before following it.
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != HOST:
        sys.exit(f"Refusing to send the token to unexpected URL host: {parsed.hostname}")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "eob-explainer-learning-project/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        hints = {
            401: "Token missing, expired, or issued for a different user. Get a fresh one.",
            403: "Refused. If the body is an HTML 'Access Denied' page, the request was "
            "blocked before reaching the API (not a token problem).",
        }
        sys.exit(f"HTTP {err.code} {err.reason}. {hints.get(err.code, '')}")
    except urllib.error.URLError as err:
        sys.exit(f"Network error: {err.reason}")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", sys.argv[1]):
        sys.exit("usage: python scripts/fetch_sandbox_eobs.py BBUser10000")
    label = sys.argv[1]
    token = os.environ.get("BB_TOKEN")
    if not token:
        sys.exit("BB_TOKEN is not set. See the instructions for how to set it safely.")

    out_dir = ROOT / "data" / "raw" / label
    out_dir.mkdir(parents=True, exist_ok=True)

    url, pages, total = START_URL, 0, None
    counts: Counter = Counter()
    while url and pages < MAX_PAGES:
        bundle = get_json(url, token)
        pages += 1
        if total is None:
            total = bundle.get("total")
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") != "ExplanationOfBenefit":
                continue
            rid = resource.get("id", "unknown")
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", rid)
            (out_dir / f"{safe_name}.json").write_text(json.dumps(resource, indent=2))
            counts[rid.split("--")[0]] += 1  # claim type is the id prefix, e.g. "carrier"
        url = next(
            (link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"),
            None,
        )

    print(
        f"{label}: saved {sum(counts.values())} EOBs from {pages} page(s); "
        f"server reports total={total} -> {out_dir.relative_to(ROOT)}"
    )
    for claim_type, n in sorted(counts.items()):
        print(f"  {claim_type}: {n}")
    if url:
        print(f"  (more pages exist; stopped at the {MAX_PAGES}-page cap)")


if __name__ == "__main__":
    main()
