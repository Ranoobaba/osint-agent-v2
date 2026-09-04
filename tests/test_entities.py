from osint2.entities import EntityGraph, Node
from osint2.evidence import Claim
from osint2.workspace import Workspace


def claim(cid, field, value, cand="cand1"):
    return Claim(id=cid, kind="finding", field=field, value=value, candidate_id=cand)


def test_collaborator_repo_creates_person_account_project(tmp_path):
    g = EntityGraph(Workspace(tmp_path, "r"))
    g.ingest_target("kunal baldava uc berkeley")
    g.ingest_candidate("cand1", "Kunal Baldava, GitHub kvnalb", ["Kunal Baldava"], ["kvnalb"], ["k@berkeley.edu"], ["https://github.com/kvnalb"], ["UC Berkeley"], [], resolved=True)
    g.ingest_claim(claim("c1", "collaborator_repo", "anayaajogani/taskmaster-agent-alex-"), "cand1")
    types = {n.type for n in g.nodes.values()}
    assert {"target", "person", "account", "email", "org", "project"} <= types
    other = g.nodes["person:gh_anayaajogani"]
    assert other.about == "connection" and not other.explored
    assert any(e.rel == "collaborates_with" and e.dst == other.id for e in g.edges)
    front = g.frontier()
    assert front and front[0].type == "person" and front[0].label == "anayaajogani"


def test_mark_explored_by_handle_and_url(tmp_path):
    g = EntityGraph(Workspace(tmp_path, "r"))
    g.ingest_target("x")
    g.ingest_claim(claim("c1", "kaggle_profile", "https://www.kaggle.com/kvnalb"), "cand1")
    acct = next(n for n in g.nodes.values() if n.type == "account")
    assert not acct.explored
    g.mark_explored(url="https://kaggle.com/kvnalb/")
    assert acct.explored
    g.ingest_claim(claim("c2", "collaborator_repo", "someone/repo"), "cand1")
    g.mark_explored(handle="someone")
    assert g.nodes["account:github:someone"].explored


def test_frontier_text_and_persist(tmp_path):
    ws = Workspace(tmp_path, "r")
    g = EntityGraph(ws)
    g.ingest_target("x")
    g.ingest_claim(claim("c1", "coauthor", "Jane Doe"), "cand1")
    g.ingest_claim(claim("c2", "past_employer", "Widget Co"), "cand1")
    assert "Jane Doe" in g.frontier_text()
    again = EntityGraph(ws)
    assert "person:jane_doe" in again.nodes and "org:widget_co" in again.nodes
    assert again.summary()["unexplored"] >= 2


def test_locations_and_topics_are_not_people(tmp_path):
    g = EntityGraph(Workspace(tmp_path, "r"))
    g.ingest_target("x")
    g.ingest_claim(claim("c1", "location_city", "San Francisco Bay Area"), "cand1")
    g.ingest_claim(claim("c2", "research_topic", "Disparities In Park Access"), "cand1")
    g.ingest_claim(claim("c3", "lab_director", "Abhishek Nagaraj"), "cand1")
    g.ingest_claim(claim("c4", "past_role", "Co President"), "cand1")
    people = [n.label for n in g.nodes.values() if n.type == "person" and n.about == "connection"]
    assert people == ["Abhishek Nagaraj"]


def test_connection_attributes_attach_to_one_node(tmp_path):
    g = EntityGraph(Workspace(tmp_path, "r"))
    g.ingest_target("x")
    g.ingest_claim(claim("c1", "collaborator", "saqibmtz"), "cand1")
    g.ingest_claim(claim("c2", "collaborator_email", "saqib.mumtaz.h@gmail.com"), "cand1")
    g.ingest_claim(claim("c3", "collaborator_identity", "Saqib Mumtaz"), "cand1")
    g.ingest_claim(claim("c4", "connection_saqibmtz_profile", "https://www.linkedin.com/in/saqib-mumtaz-b3306020"), "cand1")
    g.ingest_claim(claim("c5", "connection_saqibmtz_employer", "Georgia Tech"), "cand1")
    g.ingest_claim(claim("c6", "github_profile_name", "Kunal Baldava"), "cand1")
    g.ingest_claim(claim("c7", "account_twitter", "twitter"), "cand1")
    g.ingest_claim(claim("c8", "github_account_created", "2021-09-14"), "cand1")
    people = [n for n in g.nodes.values() if n.type == "person" and n.about == "connection"]
    assert len(people) == 1 and people[0].label == "Saqib Mumtaz" and people[0].explored
    assert "email:saqib.mumtaz.h@gmail.com" in g.nodes and "org:georgia_tech" in g.nodes
    accounts = [n.label for n in g.nodes.values() if n.type == "account"]
    assert "twitter (email registered)" in accounts and not any("2021" in a for a in accounts)
