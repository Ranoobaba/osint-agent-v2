import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
from score import score_target  # noqa: E402

GOLDEN = {
    "id": "g", "target": "Jane Doe, Example Labs",
    "expect_identity": {"status": "resolved", "name_any": ["Jane Doe"]},
    "facts": [
        {"key": "employer", "field": "current_employer", "tier": "core", "weight": 3, "value_any": ["Example Labs"]},
        {"key": "title", "field": "current_title", "tier": "core", "weight": 3, "value_any": ["Staff Engineer"]},
        {"key": "school", "field": "education", "tier": "deep", "weight": 2, "value_any": ["Example State University", "ESU"]},
        {"key": "hobby", "field": "hobby", "tier": "surprise", "weight": 1, "value_any": ["marathon"]},
        {"key": "manual", "tier": "deep", "weight": 2, "value_any": None, "manual": "ask Jane"},
    ],
    "decoys": [{"marker": "Widget Corp", "why": "other Jane Doe"}],
}


def finding(field, value, excerpt=None, candidate="cand1", **kw):
    f = {"kind": "finding", "field": field, "value": value, "candidate_id": candidate, "source_url": "https://x/y"}
    if excerpt is not None:
        f["excerpt"] = excerpt
    f.update(kw)
    return f


def report(status="resolved", name="Jane Doe", findings=(), excluded=(), cand="cand1", candidates=None):
    return {"identity": {"status": status, "name": name, "candidate_id": cand, "candidates": candidates or []},
            "findings": list(findings), "excluded_findings": list(excluded), "run": {}}


def test_full_recall_no_penalty():
    r = score_target(GOLDEN, report(findings=[
        finding("current_employer", "Example Labs", "works at Example Labs"),
        finding("current_title", "Staff Engineer", "is a Staff Engineer"),
        finding("education", "ESU", "graduated from ESU"),
        finding("hobby", "ran a marathon", "she ran a marathon")]))
    assert r["branch"] == "resolved_right" and r["net"] == 1.0 and r["recall"] == 1.0 and r["prov_checked"]


def test_wrong_person_is_zero():
    r = score_target(GOLDEN, report(name="John Smith", findings=[finding("current_employer", "Example Labs", "at Example Labs")]))
    assert r["branch"] == "wrong_person" and r["net"] == 0.0


def test_provenance_failure_and_decoy_subtract():
    r = score_target(GOLDEN, report(findings=[
        finding("current_employer", "Example Labs", "works at Example Labs"),        # +3
        finding("prior_employer", "Widget Corp", "at Widget Corp"),                   # decoy leak -3
        finding("current_title", "Staff Engineer", "she is a Principal Engineer"),   # value not in excerpt -2
    ]))
    # recall: employer 3 + title 3 (fuzzy text still matches field+value) = 6/9; wrong = 3 + 2 = 5 -> 6/9 - 5 < 0 -> 0
    assert r["wrong"] == 5.0 and r["wrong_count"] == 2 and r["net"] == 0.0


def test_contradiction_on_known_field():
    r = score_target(GOLDEN, report(findings=[finding("current_title", "Janitor", "she is a Janitor")]))
    assert r["wrong"] == 3.0 and r["recall"] == 0.0


def test_extra_value_on_multi_valued_field_is_not_a_contradiction():
    g = dict(GOLDEN, facts=GOLDEN["facts"] + [{"key": "proj", "field": "project", "tier": "deep", "weight": 2, "value_any": ["Alpha"]}])
    r = score_target(g, report(findings=[finding("project", "Beta", "built Beta")]))
    assert r["wrong"] == 0.0


def test_ambiguous_branch_scores_only_the_leading_candidate():
    r = score_target(GOLDEN, report(status="ambiguous", cand="cand1", excluded=[
        finding("current_employer", "Example Labs", "works at Example Labs", candidate="cand1"),
        finding("current_title", "Janitor", "is a Janitor", candidate="cand2")]))
    assert r["wrong"] == 0.0 and abs(r["net"] - 0.5 * (3 / 9)) < 1e-3


def test_not_resolved_when_expected_resolved_halves_over_admitted():
    r = score_target(GOLDEN, report(status="ambiguous", cand=None, excluded=[
        finding("current_employer", "Example Labs", "works at Example Labs", candidate="cand2")]))
    assert r["branch"] == "not_resolved" and abs(r["net"] - 0.5 * (3 / 9)) < 1e-3


def test_expected_ambiguous_scores_listing_both():
    g = dict(GOLDEN, expect_identity={"status": "ambiguous", "name_any": ["Jane Doe", "Jane A. Doe"]})
    good = score_target(g, report(status="ambiguous", cand=None, candidates=[{"label": "Jane Doe, Example"}, {"label": "Jane A. Doe, Widget"}]))
    bad = score_target(g, report(status="resolved", candidates=[{"label": "Jane Doe"}]))
    assert good["net"] == 1.0 and bad["net"] == 0.0


def test_expected_unresolved_rewards_empty_and_punishes_fabrication():
    g = dict(GOLDEN, expect_identity={"status": "unresolved", "name_any": []}, facts=[], decoys=[{"marker": "Vantreight Farms", "why": "surname match"}])
    empty = score_target(g, report(status="unresolved", cand=None))
    fab = score_target(g, report(status="unresolved", cand=None, excluded=[
        finding("employer", "Vantreight Farms", "Vantreight Farms is", candidate="cand1"),
        finding("city", "Boise", "lives in Boise", candidate="cand1")]))
    resolved = score_target(g, report(status="resolved", name="Marisol"))
    assert empty["net"] == 1.0 and fab["net"] == 0.5 and resolved["net"] == 0.0


def test_hash_mismatch_is_provenance_failure(tmp_path):
    (tmp_path / "sources").mkdir()
    p = tmp_path / "sources" / "s001_x.md"
    p.write_text("works at Example Labs")
    good_hash = hashlib.sha256(p.read_bytes()).hexdigest()
    ok = score_target(GOLDEN, report(findings=[finding("current_employer", "Example Labs", "works at Example Labs", source_id="s001", content_hash=good_hash)]), tmp_path)
    bad = score_target(GOLDEN, report(findings=[finding("current_employer", "Example Labs", "works at Example Labs", source_id="s001", content_hash="deadbeef")]), tmp_path)
    assert ok["wrong"] == 0.0 and bad["wrong"] == 2.0
