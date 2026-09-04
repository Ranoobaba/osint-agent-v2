from pathlib import Path

from osint2.evidence import EvidenceStore, anchor_excerpt, normalize
from osint2.workspace import Workspace

PAGE = """# Jane Doe
**Staff Engineer** at Example Labs since 2021.
Previously she led infrastructure at Widget Co (2017 to 2021).
Contact: jane.doe@example.com | GitHub: janedoe
"""


def make_store(tmp_path: Path) -> EvidenceStore:
    ws = Workspace(tmp_path, "run1")
    store = EvidenceStore(ws)
    store.add_source("fetch_page", {"url": "https://example.com/jane"}, PAGE, "https://example.com/jane", step=1)
    return store


def test_normalize_offsets_map_back_to_raw():
    norm, offsets = normalize("**Staff  Engineer**\tat Example")
    assert norm == "staff engineer at example"
    start = norm.find("engineer")
    assert "**Staff  Engineer**\tat Example"[offsets[start]:offsets[start] + 8] == "Engineer"


def test_exact_excerpt_is_admitted_with_raw_span_and_hash(tmp_path):
    store = make_store(tmp_path)
    claim, reason = store.admit({"field": "current_title", "value": "Staff Engineer", "source_id": "s001",
                                "excerpt": "staff engineer at example labs since 2021"}, step=1)
    assert reason is None and claim is not None
    assert claim.excerpt in PAGE and claim.excerpt.startswith("Staff Engineer") and claim.excerpt.endswith("2021")
    assert claim.content_hash == store.sources["s001"].content_hash
    assert claim.method == "fetch_page"
    assert claim.source_url == "https://example.com/jane"


def test_fuzzy_excerpt_reanchors_to_verbatim_span(tmp_path):
    store = make_store(tmp_path)
    claim, reason = store.admit({"field": "prior_employer", "value": "Widget Co", "source_id": "s001",
                                "excerpt": "Previously she lead infrastructure at Widget Co (2017 to 2021)"}, step=1)
    assert reason is None, reason
    assert "Widget Co" in claim.excerpt and claim.excerpt in PAGE


def test_excerpt_not_in_source_is_rejected(tmp_path):
    store = make_store(tmp_path)
    claim, reason = store.admit({"field": "current_employer", "value": "Acme", "source_id": "s001",
                                "excerpt": "Jane works at Acme Corporation as CTO"}, step=1)
    assert claim is None and "not found" in reason


def test_excerpt_far_from_value_is_rejected_with_line_hint(tmp_path):
    ws = Workspace(tmp_path, "run2")
    store = EvidenceStore(ws)
    page = "Header line about Widget Co.\n" + ("filler text. " * 60) + "\nJane is a Staff Engineer at Example Labs."
    store.add_source("fetch_page", {"url": "https://example.com/far"}, page, "https://example.com/far", step=1)
    claim, reason = store.admit({"field": "prior_employer", "value": "Widget Co", "source_id": "s001",
                                "excerpt": "Jane is a Staff Engineer at Example Labs"}, step=1)
    assert claim is None and "quote this line" in reason and "Widget Co" in reason


def test_email_value_needs_exact_containment(tmp_path):
    store = make_store(tmp_path)
    ok, _ = store.admit({"field": "email", "value": "jane.doe@example.com", "source_id": "s001",
                         "excerpt": "Contact: jane.doe@example.com"}, step=1)
    bad, reason = store.admit({"field": "email", "value": "jane.doe@example.org", "source_id": "s001",
                               "excerpt": "Contact: jane.doe@example.com"}, step=1)
    assert ok is not None and bad is None


def test_unknown_source_and_missing_excerpt_rejected(tmp_path):
    store = make_store(tmp_path)
    a, r1 = store.admit({"field": "x", "value": "y", "source_id": "s999", "excerpt": "y"})
    b, r2 = store.admit({"field": "x", "value": "y", "source_id": "s001"})
    assert a is None and "unknown source_id" in r1
    assert b is None and "missing excerpt" in r2
    assert store.stats()["rejected"] == 2


def test_not_found_conflict_synthesis_rules(tmp_path):
    store = make_store(tmp_path)
    nf, r = store.admit({"kind": "not_found", "field": "phone", "searched": ["s001"]})
    assert nf is not None and nf.kind == "not_found"
    nf2, r2 = store.admit({"kind": "not_found", "field": "phone", "searched": ["nothing"]})
    assert nf2 is None
    f1, _ = store.admit({"field": "current_title", "value": "Staff Engineer", "source_id": "s001",
                         "excerpt": "Staff Engineer at Example Labs"})
    store.add_source("web_search", {"q": "jane"}, "Jane Doe is a Principal Engineer at Example Labs", None, step=2)
    f2, _ = store.admit({"field": "current_title", "value": "Principal Engineer", "source_id": "s002",
                         "excerpt": "Principal Engineer at Example Labs"})
    conf, r3 = store.admit({"kind": "conflict", "field": "current_title", "based_on": [f1.id, f2.id]})
    assert conf is not None and conf.kind == "conflict"
    syn_bad, r4 = store.admit({"kind": "synthesis", "field": "seniority", "value": "senior IC", "based_on": [f1.id]})
    assert syn_bad is None
    syn, r5 = store.admit({"kind": "synthesis", "field": "seniority", "value": "senior IC", "based_on": [f1.id, f2.id]})
    assert syn is not None


def test_store_reloads_from_disk(tmp_path):
    store = make_store(tmp_path)
    store.admit({"field": "current_title", "value": "Staff Engineer", "source_id": "s001", "excerpt": "Staff Engineer at Example Labs"})
    again = EvidenceStore(Workspace(tmp_path, "run1"))
    assert len(again.sources) == 1 and len(again.claims) == 1


def test_anchor_excerpt_returns_none_for_short_fuzzy():
    assert anchor_excerpt("some text here", "zzz") is None


def test_span_extends_to_nearby_value(tmp_path):
    store = make_store(tmp_path)
    claim, reason = store.admit({"field": "personal_email", "value": "jane.doe@example.com", "source_id": "s001",
                                "excerpt": "Previously she led infrastructure at Widget Co"}, step=1)
    assert reason is None, reason
    assert "jane.doe@example.com" in claim.excerpt and "Widget Co" in claim.excerpt and claim.excerpt in PAGE


def test_value_absent_from_source_is_rejected_with_reason(tmp_path):
    store = make_store(tmp_path)
    claim, reason = store.admit({"field": "phone", "value": "555-0100", "source_id": "s001",
                                "excerpt": "Contact: jane.doe@example.com"}, step=1)
    assert claim is None and "does not appear in that source" in reason


def test_value_that_says_more_than_the_line_is_rejected(tmp_path):
    ws = Workspace(tmp_path, "run3")
    store = EvidenceStore(ws)
    store.add_source("wayback_lookup", {"url": "x"}, "Professor, MIT, 1988-1998\nOther line.", "https://x", step=1)
    claim, reason = store.admit({"field": "past_employer", "value": "Department of Brain and Cognitive Sciences at MIT from 1988 to 1998",
                                "source_id": "s001", "excerpt": "Professor, MIT, 1988-1998"}, step=1)
    assert claim is None and "says more" in reason
    ok, _ = store.admit({"field": "past_employer", "value": "MIT, 1988-1998", "source_id": "s001", "excerpt": "Professor, MIT, 1988-1998"}, step=1)
    assert ok is not None
