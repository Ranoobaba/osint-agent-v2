from osint2.resolution import (Anchor, Candidate, CompanyRef, Employment, Evidence, Judge, apply_judge,
                                    resolve, score_candidate)

EV = [Evidence(claim="x", source_url="https://example.com/a")]


def anchor_sixtyfour():
    return Anchor(target_type="name", raw="Saarth Shah, Sixtyfour", names=["Saarth Shah"],
                  companies=[CompanyRef(name="Sixtyfour", relation="current")], locations=["San Francisco, CA"])


def test_same_name_different_current_employer_is_vetoed():
    cand = Candidate(id="c1", label="other", names=["Saarth Shah"],
                     employers=[Employment(name="Acme Dental", role="Dentist")], locations=["Fresno, CA"], evidence=EV)
    b = score_candidate(anchor_sixtyfour(), cand)
    assert b.score == 0.0 and b.contradictions and "current employer mismatch" in b.contradictions[0]


def test_email_match_alone_is_capped_but_an_email_target_resolves_on_it():
    # v1 kept this ambiguous. v2 rule: when the target IS the email, the matching candidate is the
    # person by definition; the single-field cap still applies to the score itself.
    a = Anchor(target_type="email", raw="a@b.com", emails=["a@b.com"])
    cand = Candidate(id="c1", label="x", emails=["A@B.com"], evidence=EV)
    b = score_candidate(a, cand)
    assert b.capped and b.score == 0.6
    res = resolve(a, [cand])
    assert res.status == "resolved" and "target_key" in res.matched_markers
    # but a name-type anchor that merely carries an email stays ambiguous on one field
    a2 = Anchor(target_type="name", raw="Jane a@b.com", names=["Jane Doe"], emails=["a@b.com"])
    assert resolve(a2, [cand]).status == "ambiguous"


def test_three_markers_resolve():
    a = anchor_sixtyfour()
    a.emails = ["saarth@sixtyfour.ai"]
    cand = Candidate(id="c1", label="real", names=["Saarth Shah"], emails=["saarth@sixtyfour.ai"],
                     employers=[Employment(name="Sixtyfour AI", role="CEO")], locations=["San Francisco Bay Area"], evidence=EV)
    res = resolve(a, [cand])
    assert res.status == "resolved"
    assert {"email", "employer", "location", "name"} <= set(res.matched_markers)
    assert res.score >= 0.85


def test_two_close_candidates_are_ambiguous():
    a = anchor_sixtyfour()
    c1 = Candidate(id="c1", label="one", names=["Saarth Shah"], employers=[Employment(name="Sixtyfour")], evidence=EV)
    c2 = Candidate(id="c2", label="two", names=["Saarth Shah"], employers=[Employment(name="Sixtyfour")], evidence=EV)
    res = resolve(a, [c1, c2])
    assert res.status == "ambiguous" and res.runner_up is not None


def test_name_gate_blocks_unrelated_but_passes_variants():
    a = Anchor(names=["John Doe"], companies=[CompanyRef(name="Acme", relation="unknown")])
    variant = Candidate(id="c1", label="v", names=["Jon Doe"], employers=[Employment(name="Acme")], evidence=EV)
    other = Candidate(id="c2", label="o", names=["Priya Natarajan"], employers=[Employment(name="Acme")], evidence=EV)
    assert not score_candidate(a, variant).gated
    assert score_candidate(a, other).gated


def test_hard_key_rescues_name_mismatch():
    a = Anchor(names=["Rayyan Ali"], handles=["Ranoobaba"])
    cand = Candidate(id="c1", label="gh", names=["Ranoobaba"], handles=["ranoobaba"], evidence=EV)
    b = score_candidate(a, cand)
    assert not b.gated and b.fields["handle"] == 1.0


def test_country_mismatch_vetoes_without_hard_key():
    a = Anchor(names=["Sarah Chen"], locations=["San Francisco, CA"])
    cand = Candidate(id="c1", label="x", names=["Sarah Chen"], locations=["Singapore"], evidence=EV)
    b = score_candidate(a, cand)
    assert b.contradictions and "country mismatch" in b.contradictions[0]


def test_judge_promotes_only_with_two_cited_reasons_and_no_veto():
    a = anchor_sixtyfour()
    cand = Candidate(id="c1", label="x", names=["Saarth Shah"], employers=[Employment(name="Sixtyfour")], evidence=EV)
    res = resolve(a, [cand])
    assert res.status == "ambiguous"
    weak = Judge(verdict="same", candidate_id="c1", reasons=["looks right"], confidence=0.9)
    assert apply_judge(res, weak).status == "ambiguous"
    strong = Judge(verdict="same", candidate_id="c1", confidence=0.9,
                   reasons=["bio names Sixtyfour https://a", "photo matches LinkedIn https://b"])
    assert apply_judge(res, strong).status == "resolved"
    res2 = resolve(a, [cand])
    assert apply_judge(res2, Judge(verdict="different", reasons=[], confidence=0.8)).status == "unresolved"


def test_org_abbreviations_and_units_match():
    from osint2.resolution import org_similarity
    assert org_similarity("UC Berkeley BAIR", "University of California, Berkeley") >= 0.85
    assert org_similarity("Sixtyfour", "Sixtyfour AI Inc.") >= 0.85
    assert org_similarity("Presto", "Presto (YC W16)") >= 0.85
    assert org_similarity("Acme Dental Group", "University of California, Berkeley") == 0.0


def test_linkedin_style_candidate_reaches_ambiguous_then_judge_path():
    a = Anchor(names=["Syed Rayyan Ali"], companies=[CompanyRef(name="UC Berkeley BAIR", relation="unknown")])
    cand = Candidate(id="c1", label="Syed Rayyan Ali - UC Berkeley CS student", names=["Syed Rayyan Ali"],
                     employers=[Employment(name="Presto", role="AI Engineering Intern"),
                                Employment(name="University of California, Berkeley", role="Student", start="2023", end="2027")],
                     locations=["Berkeley, California, United States"], evidence=EV)
    res = resolve(a, [cand])
    assert res.status == "ambiguous" and set(res.matched_markers) == {"name", "employer"}


def test_future_end_date_counts_as_current_and_does_not_veto():
    a = Anchor(names=["Syed Rayyan Ali"], companies=[CompanyRef(name="UC Berkeley", relation="current")])
    cand = Candidate(id="c1", label="li", names=["Syed Rayyan Ali"],
                     employers=[Employment(name="Presto", role="Intern"),
                                Employment(name="University of California, Berkeley", role="Student", start="2023", end="2099")],
                     evidence=EV)
    b = score_candidate(a, cand)
    assert not b.contradictions and b.fields["employer"] >= 0.85


def test_education_matches_university_anchor_and_blocks_veto():
    a = Anchor(names=["Syed Rayyan Ali"], companies=[CompanyRef(name="UC Berkeley", relation="current")])
    cand = Candidate(id="c1", label="li", names=["Syed Rayyan Ali"],
                     employers=[Employment(name="Presto Phoenix, Inc.", role="Intern", start="2026-06")],
                     education=[Employment(name="University of California, Berkeley", role="BA CS", start="2023", end="2027")],
                     evidence=EV)
    b = score_candidate(a, cand)
    assert not b.contradictions and b.fields["employer"] >= 0.85


def test_judge_same_person_ids_parse():
    j = Judge(verdict="same", candidate_id="c1", same_person_ids=["c2"], reasons=["a https://x", "b https://y"], confidence=0.9)
    assert j.same_person_ids == ["c2"]


def test_corroboration_marker_resolves_name_plus_employer_anchor():
    a = Anchor(names=["Henry Wang"], companies=[CompanyRef(name="Sixtyfour AI", relation="current")])
    one_site = Candidate(id="c1", label="x", names=["Henry Wang"], employers=[Employment(name="Sixtyfour")],
                         evidence=[Evidence(claim="founding eng", source_url="https://github.com/braindead-dev")])
    assert resolve(a, [one_site]).status == "ambiguous"
    two_sites = Candidate(id="c1", label="x", names=["Henry Wang"], employers=[Employment(name="Sixtyfour")],
                          evidence=[Evidence(claim="founding eng", source_url="https://github.com/braindead-dev"),
                                    Evidence(claim="Founding Engineer at Sixtyfour", source_url="https://www.linkedin.com/in/henry00c")])
    res = resolve(a, [two_sites])
    assert res.status == "resolved" and "corroboration" in res.matched_markers


def test_dedupe_findings_collapses_repeats_and_keeps_provenance():
    from osint2.report import dedupe_findings
    out = dedupe_findings([
        {"field": "current_role", "value": "Founding Engineer at Sixtyfour AI", "confidence": 0.7,
         "source_url": "https://a.com"},
        # exact repeat from another source: merges, keeps both sources, takes the higher confidence
        {"field": "current_role", "value": "founding engineer at sixtyfour ai.", "confidence": 0.9,
         "source_url": "https://b.com"},
        # shorter restatement of the same field: merges into the richer text
        {"field": "current_role", "value": "Founding Engineer", "confidence": 0.5, "source_url": "https://c.com"},
        # genuinely different fact: kept
        {"field": "email", "value": "x@y.com", "confidence": 0.9, "source_url": "https://d.com", "sensitive": True},
    ])
    assert len(out) == 2
    role = next(f for f in out if f["field"] == "current_role")
    assert role["confidence"] == 0.9
    assert role["value"] == "Founding Engineer at Sixtyfour AI"  # richer text wins
    assert set(role["also_sourced_from"]) == {"https://b.com", "https://c.com"}  # provenance preserved
    assert any(f["field"] == "email" and f["sensitive"] for f in out)


def test_dedupe_findings_promotes_sensitive_and_drops_empty():
    from osint2.report import dedupe_findings
    out = dedupe_findings([
        {"field": "home_address", "value": "5867 Santa Teresa Blvd", "confidence": 0.6, "sensitive": False},
        {"field": "home_address", "value": "5867 santa teresa blvd", "confidence": 0.6, "sensitive": True},
        {"field": "junk", "value": ""},
    ])
    assert len(out) == 1 and out[0]["sensitive"] is True


def test_bare_handle_target_resolves_on_the_handle_alone():
    from osint2.anchors import prefill
    anchor = prefill("Ranoobaba")
    assert anchor.target_type == "handle" and anchor.handles == ["Ranoobaba"]
    cand = Candidate(id="c1", label="Syed Rayyan Ali, GitHub Ranoobaba", names=["Syed Rayyan Ali"], handles=["Ranoobaba"],
                     evidence=[Evidence(claim="github profile", source_url="https://github.com/Ranoobaba")])
    other = Candidate(id="c2", label="someone else", names=["Syed Ali"], handles=["syedali"],
                      evidence=[Evidence(claim="x", source_url="https://example.com")])
    res = resolve(anchor, [cand, other])
    assert res.status == "resolved" and res.best_candidate_id == "c1" and "target_key" in res.matched_markers


def test_email_target_resolves_on_the_email_alone():
    from osint2.anchors import prefill
    anchor = prefill("jane.doe@example.com")
    assert anchor.target_type == "email"
    cand = Candidate(id="c1", label="Jane", names=["Jane Doe"], emails=["jane.doe@example.com"],
                     evidence=[Evidence(claim="commit email", source_url="https://github.com/janedoe")])
    assert resolve(anchor, [cand]).status == "resolved"
