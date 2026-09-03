from osint2.graph import build_graph
from osint2.resolution import Anchor, Candidate, CompanyRef, Employment, Evidence, resolve
from osint2.schema import validate_report

EV = [Evidence(claim="x", source_url="https://github.com/braindead-dev")]


def _resolved():
    a = Anchor(names=["Henry Wang"], raw="Henry Wang, Sixtyfour AI",
               companies=[CompanyRef(name="Sixtyfour AI", relation="current")])
    good = Candidate(id="c1", label="Henry Wang, GitHub braindead-dev", names=["Henry Wang"],
                     handles=["braindead-dev"], employers=[Employment(name="Sixtyfour")],
                     evidence=[Evidence(claim="founding eng", source_url="https://github.com/braindead-dev"),
                               Evidence(claim="Founding Engineer", source_url="https://linkedin.com/in/henry00c")])
    other = Candidate(id="c2", label="Henry Wang, RSS3", names=["Henry Wang"], employers=[Employment(name="RSS3")],
                      disclaims_identity=True, evidence=EV)
    res = resolve(a, [good, other])
    return a, res, [good, other]


def test_graph_has_root_person_findings_and_rejected():
    a, res, cands = _resolved()
    assert res.status == "resolved"
    findings = [
        {"category": "professional_history", "field": "current_role", "value": "Founding Engineer",
         "confidence": 0.9, "source_url": "https://henr.ee/", "method": "personal site", "candidate_id": "c1"},
        {"category": "online_presence", "field": "github", "value": "braindead-dev", "confidence": 0.9,
         "source_url": "https://github.com/braindead-dev", "method": "github_intel"},
    ]
    synth = [{"claim": "joins pre-PMF startups early", "based_on": ["current_role"], "confidence": 0.6}]
    g = build_graph(a, res, cands, findings, synth, same_person_ids={"c1"})
    types = {n["type"] for n in g["nodes"]}
    assert {"ground_truth", "candidate", "finding", "inference"} <= types
    root = next(n for n in g["nodes"] if n["type"] == "ground_truth")
    assert root["id"] == "input.target"
    # rejected same-name candidate is present and marked
    rej = [n for n in g["nodes"] if n.get("kind") == "same_name_other"]
    assert len(rej) == 1 and rej[0]["value"].startswith("Henry Wang, RSS3")
    # findings hang off the resolved person, and the veto reason is on the rejected edge
    person = next(n for n in g["nodes"] if n["type"] == "candidate" and n["kind"] == "person")
    fedges = [e for e in g["edges"] if e["from"] == person["id"] and e["to"].startswith("found.")]
    assert len(fedges) == 2 and all(e["source_url"] for e in fedges)
    veto_edge = next(e for e in g["edges"] if e["to"] == f"candidate.c2")
    assert "rejected" in veto_edge["label"]
    # synthesis links back to the finding it is based on
    syn = next(n for n in g["nodes"] if n["type"] == "inference")
    assert any(e["from"] == syn["id"] and e["label"] == "based on" for e in g["edges"])
    assert g["stats"]["findings"] == 2 and g["stats"]["rejected"] == 1


def test_report_schema_validates():
    a, res, cands = _resolved()
    report = {
        "target": "Henry Wang, Sixtyfour AI", "run_id": "t1", "anchor": a.model_dump(),
        "identity": {"status": "resolved", "name": "Henry Wang", "score": 0.97, "candidates_considered": 2},
        "findings": [{"category": "online_presence", "field": "github", "value": "braindead-dev",
                      "confidence": 0.9, "source_url": "https://github.com/braindead-dev"}],
        "synthesis": [{"claim": "x", "based_on": ["github"], "confidence": 0.6}],
        "graph": {"nodes": [], "edges": []},
        "run": {"duration_s": 1.0, "stop_reason": "saturation", "llm_calls": 3, "tool_calls": 5},
    }
    ok, err = validate_report(report)
    assert ok, err


def test_report_schema_flags_missing_required():
    ok, err = validate_report({"identity": {}, "run": {}})  # missing target/run_id/anchor
    assert not ok and err
