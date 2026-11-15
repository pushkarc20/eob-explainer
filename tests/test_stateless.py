import logging

from guards import forbid_file_writes, forbid_network, tree_snapshot
from support import FakeClient, good_reply, prepare_case

from eob import app_logic
from eob.evaluation import ROOT, load_gold
from healthcore.privacy.pseudonymizer import Pseudonymizer

MEMBER_NAME = "Jane Q. Member"
MEMBER_ID = "ABC123456"


def exercise(case, detector):
    """Everything the app does for one claim: load, draft, preview, and a cloud run against a fake model."""
    claim = app_logic.load_claim_from_path(ROOT / case["file"], case["id"])
    app_logic.make_draft(claim, MEMBER_NAME, MEMBER_ID)
    pseudonymizer = Pseudonymizer()
    prepared = app_logic.preview_payload(claim, pseudonymizer, detector)
    payload, _ = prepare_case(case["id"], detector)
    client = FakeClient([good_reply(payload)])
    return claim, app_logic.run_cloud(claim, client, pseudonymizer, prepared.json_text, detector)


def test_a_full_run_writes_no_files_and_opens_no_connections(detector):
    gold = load_gold()
    before = tree_snapshot(ROOT)
    with forbid_file_writes() as writes, forbid_network() as connections:
        for case in gold["cases"]:
            _, result = exercise(case, detector)
            assert result.source == "ai", case["id"]
    assert writes == []
    assert connections == []
    assert tree_snapshot(ROOT) == before


def test_logs_and_console_output_contain_no_document_content(detector, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    secrets = {MEMBER_NAME, MEMBER_ID}
    for case in load_gold()["cases"]:
        claim, _ = exercise(case, detector)
        secrets.update(case["canaries"])
        secrets.update(claim.blocked_values)
        if claim.eob.claim_id:
            secrets.add(claim.eob.claim_id)
    captured = capsys.readouterr()
    everything = (caplog.text + captured.out + captured.err).casefold()
    leaked = sorted(value for value in secrets if len(value) >= 4 and value.casefold() in everything)
    assert leaked == []
