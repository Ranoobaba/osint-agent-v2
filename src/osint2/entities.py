"""The entity graph: people, organizations, accounts, emails, domains and documents as typed nodes,
with typed edges, and an `explored` flag on every node. The attribution graph (graph.py) answers
"where did this claim come from"; this graph answers "what have we found and what have we not yet
looked into". Unexplored nodes are the frontier: the lead loop recites them and the deep dive fans
out over them. Nodes are derived in code from admitted claims and from tool calls, never written by
the model directly, so a frontier entry is always backed by a claim id."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from .workspace import Workspace

NodeType = str  # person | org | account | email | domain | document | project

PERSON_FIELDS = ("collaborator", "coauthor", "co_author", "connection", "manager", "supervisor", "mentor", "advisor",
                 "teammate", "cofounder", "co_founder", "partner_person", "colleague", "relative", "family", "spouse", "sibling",
                 "director", "lead", "professor", "pi", "boss", "chair", "head", "officer", "president", "ceo", "cto", "founder",
                 "friend", "contact", "reference", "recommender", "author")
ROLE_FIELDS = ("role", "title", "position")   # a role field holds a title, not a person
# fields whose values are never people even when they look like names
NOT_PERSON_FIELDS = ("location", "city", "country", "region", "address", "area", "topic", "research", "interest", "skill",
                     "language", "award", "honor", "headline", "bio", "summary", "degree", "major", "field_of_study", "hobby")
NAME_SHAPE = re.compile(r"^(?:[A-Z][a-zA-Z'\-.]+\s){1,3}[A-Z][a-zA-Z'\-.]+$")
TITLE_WORDS = {"president", "director", "manager", "intern", "engineer", "officer", "co", "vice", "chief", "head", "lead", "professor", "student", "founder", "ceo", "cto", "analyst", "fellow", "research", "researcher", "assistant", "associate", "university", "lab", "club", "college", "school", "company", "inc", "llc"}


def looks_like_person_name(v: str) -> bool:
    v = (v or "").strip()
    if not NAME_SHAPE.match(v) or any(ch.isdigit() for ch in v):
        return False
    return not any(w.lower().strip(".,") in TITLE_WORDS for w in v.split())
ORG_FIELDS = ("employer", "company", "organization", "school", "education", "university", "lab", "club", "startup", "affiliation")
PROJECT_FIELDS = ("project", "repo", "repository", "paper", "publication", "talk", "product")
ACCOUNT_FIELDS = ("handle", "username", "profile", "account", "_url")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s)\]]+")
GITHUB_REPO_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
PLATFORM_HOSTS = {"github.com": "github", "linkedin.com": "linkedin", "x.com": "x", "twitter.com": "x", "kaggle.com": "kaggle",
                  "devpost.com": "devpost", "medium.com": "medium", "open.spotify.com": "spotify", "scholar.google.com": "scholar",
                  "instagram.com": "instagram", "facebook.com": "facebook", "youtube.com": "youtube", "substack.com": "substack",
                  "huggingface.co": "huggingface", "stackoverflow.com": "stackoverflow", "reddit.com": "reddit", "dev.to": "devto"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:60] or "x"


def _host(url: str) -> str:
    try:
        h = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


@dataclass
class Node:
    id: str
    type: NodeType
    label: str
    explored: bool = False
    about: str = "target"            # "target" | "connection" | "candidate:<id>"
    claims: list[str] = field(default_factory=list)
    url: Optional[str] = None
    hints: dict[str, str] = field(default_factory=dict)   # platform, handle, relation, etc.


@dataclass
class Edge:
    src: str
    dst: str
    rel: str
    claim: Optional[str] = None


class EntityGraph:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        raw = ws.read_json("entities.json")
        if raw:
            self.nodes = {n["id"]: Node(**n) for n in raw.get("nodes", [])}
            self.edges = [Edge(**e) for e in raw.get("edges", [])]

    # ---------------------------------------------------------------- basics
    def upsert(self, node: Node) -> Node:
        cur = self.nodes.get(node.id)
        if cur is None:
            self.nodes[node.id] = node
            return node
        cur.claims = sorted(set(cur.claims) | set(node.claims))
        cur.url = cur.url or node.url
        cur.hints.update({k: v for k, v in node.hints.items() if v})
        cur.explored = cur.explored or node.explored
        return cur

    def link(self, src: str, dst: str, rel: str, claim: str | None = None) -> None:
        if src == dst or any(e.src == src and e.dst == dst and e.rel == rel for e in self.edges):
            return
        self.edges.append(Edge(src, dst, rel, claim))

    def persist(self) -> None:
        self.ws.write_json("entities.json", {"nodes": [asdict(n) for n in self.nodes.values()], "edges": [asdict(e) for e in self.edges]})

    def frontier(self, limit: int = 8) -> list[Node]:
        """Unexplored nodes worth a pivot, people and accounts first."""
        order = {"person": 0, "account": 1, "domain": 2, "email": 3, "org": 4, "project": 5, "document": 6}
        items = [n for n in self.nodes.values() if not n.explored and n.type != "target"]
        # a connection with a handle or profile URL is a hard lead; a bare name is a soft one
        items.sort(key=lambda n: (order.get(n.type, 9), 0 if (n.hints.get("handle") or n.url) else 1, -len(n.claims)))
        return items[:limit]

    def mark_explored(self, *, url: str | None = None, handle: str | None = None, email: str | None = None,
                      name: str | None = None, domain: str | None = None) -> list[str]:
        hit = []
        for n in self.nodes.values():
            if url and n.url and _host(n.url) == _host(url) and urlparse(n.url).path.rstrip("/").lower() == urlparse(url if "://" in url else "https://" + url).path.rstrip("/").lower():
                n.explored = True; hit.append(n.id)
            elif handle and n.type == "account" and n.hints.get("handle", "").lower() == handle.lower():
                n.explored = True; hit.append(n.id)
            elif email and n.type == "email" and n.label.lower() == email.lower():
                n.explored = True; hit.append(n.id)
            elif name and n.type in ("person", "org", "project") and name.lower() in n.label.lower():
                n.explored = True; hit.append(n.id)
            elif domain and n.type == "domain" and n.label.lower() == domain.lower():
                n.explored = True; hit.append(n.id)
        return hit

    # ------------------------------------------------------------- derivation
    def ingest_target(self, label: str) -> None:
        self.upsert(Node(id="target", type="target", label=label, explored=True))

    def ingest_candidate(self, cid: str, label: str, names: list[str], handles: list[str], emails: list[str],
                         profile_urls: list[str], employers: list[str], education: list[str], resolved: bool) -> None:
        pid = f"person:{cid}"
        self.upsert(Node(id=pid, type="person", label=(names[0] if names else label), explored=True, about=f"candidate:{cid}"))
        self.link("target", pid, "resolved_as" if resolved else "candidate")
        for h in handles:
            self._account(pid, h, None, None, about=f"candidate:{cid}")
        for e in emails:
            nid = f"email:{e.lower()}"
            self.upsert(Node(id=nid, type="email", label=e.lower(), about=f"candidate:{cid}"))
            self.link(pid, nid, "has_email")
        for u in profile_urls:
            self._account_from_url(pid, u, None, about=f"candidate:{cid}")
        for o in employers:
            oid = f"org:{_slug(o)}"; self.upsert(Node(id=oid, type="org", label=o, about=f"candidate:{cid}")); self.link(pid, oid, "works_at")
        for o in education:
            oid = f"org:{_slug(o)}"; self.upsert(Node(id=oid, type="org", label=o, about=f"candidate:{cid}")); self.link(pid, oid, "studied_at")
        self.persist()

    def ingest_claim(self, claim: Any, resolved_id: str | None) -> None:
        """Derive nodes and edges from one admitted finding. The person node is the candidate the
        claim is about; when identity is resolved that is the target person."""
        if getattr(claim, "kind", "finding") != "finding":
            return
        cid = claim.candidate_id or resolved_id
        if not cid:
            return
        pid = f"person:{cid}"
        if pid not in self.nodes:
            self.upsert(Node(id=pid, type="person", label=cid, explored=True, about=f"candidate:{cid}"))
        f = (claim.field or "").lower()
        v = (claim.value or "").strip()
        about = "target" if cid == resolved_id else f"candidate:{cid}"
        for e in EMAIL_RE.findall(v):
            nid = f"email:{e.lower()}"
            self.upsert(Node(id=nid, type="email", label=e.lower(), claims=[claim.id], about=about))
            self.link(pid, nid, "has_email", claim.id)
        for u in URL_RE.findall(v):
            self._account_from_url(pid, u, claim.id, about=about)
        blocked = any(k in f for k in ROLE_FIELDS + NOT_PERSON_FIELDS)
        person_field = any(k in f for k in PERSON_FIELDS) and not blocked
        if (person_field and (looks_like_person_name(v) or GITHUB_REPO_RE.match(v) or "_" in v or v.islower())) or (
                looks_like_person_name(v) and not blocked and not any(k in f for k in ORG_FIELDS + PROJECT_FIELDS) and about == "target"
                and f not in ("name", "full_name", "legal_name", "alias")):
            m = GITHUB_REPO_RE.match(v)
            if m:
                owner, repo = m.groups()
                other = f"person:gh_{_slug(owner)}"
                self.upsert(Node(id=other, type="person", label=owner, claims=[claim.id], about="connection",
                                 hints={"platform": "github", "handle": owner, "relation": f, "via": f"{owner}/{repo}"}))
                self.link(pid, other, "collaborates_with", claim.id)
                self._account(other, owner, "github", f"https://github.com/{owner}", about="connection", claim=claim.id)
                proj = f"project:{_slug(v)}"
                self.upsert(Node(id=proj, type="project", label=v, claims=[claim.id], url=f"https://github.com/{v}", about=about, explored=True))
                self.link(pid, proj, "contributes_to", claim.id); self.link(other, proj, "contributes_to", claim.id)
            elif v and not URL_RE.search(v) and (looks_like_person_name(v) or person_field):
                other = f"person:{_slug(v)}"
                self.upsert(Node(id=other, type="person", label=v, claims=[claim.id], about="connection", hints={"relation": f}))
                self.link(pid, other, f, claim.id)
        elif any(k in f for k in ORG_FIELDS) and v and not URL_RE.search(v):
            oid = f"org:{_slug(v)}"
            self.upsert(Node(id=oid, type="org", label=v, claims=[claim.id], about=about))
            self.link(pid, oid, "studied_at" if any(k in f for k in ("school", "education", "university")) else "works_at", claim.id)
        elif any(k in f for k in PROJECT_FIELDS) and v and not URL_RE.search(v):
            m = GITHUB_REPO_RE.match(v)
            url = f"https://github.com/{v}" if m else None
            pj = f"project:{_slug(v)}"
            self.upsert(Node(id=pj, type="project", label=v, claims=[claim.id], url=url, about=about,
                             hints={"kind": "publication" if any(k in f for k in ("paper", "publication")) else "project"}))
            self.link(pid, pj, "authored" if "paper" in f or "publication" in f else "works_on", claim.id)
        elif any(k in f for k in ACCOUNT_FIELDS) and v and not URL_RE.search(v) and "@" not in v:
            platform = next((p for p in PLATFORM_HOSTS.values() if p in f), None)
            self._account(pid, v, platform, None, about=about, claim=claim.id)
        self.persist()

    def _account(self, pid: str, handle: str, platform: str | None, url: str | None, *, about: str, claim: str | None = None) -> None:
        handle = handle.strip().lstrip("@")
        if not handle or len(handle) > 40 or " " in handle:
            return
        key = f"account:{platform or 'any'}:{handle.lower()}"
        self.upsert(Node(id=key, type="account", label=f"{platform + ' ' if platform else ''}{handle}", url=url, claims=[claim] if claim else [],
                         about=about, hints={"platform": platform or "", "handle": handle}))
        self.link(pid, key, "owns_account", claim)

    def _account_from_url(self, pid: str, url: str, claim: str | None, *, about: str) -> None:
        host = _host(url)
        platform = next((p for h, p in PLATFORM_HOSTS.items() if host == h or host.endswith("." + h)), None)
        path = urlparse(url if "://" in url else "https://" + url).path.strip("/")
        if platform:
            handle = path.split("/")[-1] if platform == "linkedin" else path.split("/")[0]
            handle = handle.lstrip("@")
            if handle and handle not in ("in", "pub", "company"):
                key = f"account:{platform}:{handle.lower()}"
                self.upsert(Node(id=key, type="account", label=f"{platform} {handle}", url=url, claims=[claim] if claim else [], about=about,
                                 hints={"platform": platform, "handle": handle}))
                self.link(pid, key, "owns_account", claim)
        elif host and not host.endswith(("web.archive.org", "gravatar.com", "whatsmyname.app", "api.github.com")):
            did = f"domain:{host}"
            self.upsert(Node(id=did, type="domain", label=host, url=f"https://{host}", claims=[claim] if claim else [], about=about))
            self.link(pid, did, "linked_domain", claim)

    # ---------------------------------------------------------------- output
    def summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for n in self.nodes.values():
            by_type[n.type] = by_type.get(n.type, 0) + 1
        return {"nodes": len(self.nodes), "edges": len(self.edges), "by_type": by_type,
                "unexplored": sum(1 for n in self.nodes.values() if not n.explored and n.type != "target")}

    def to_report(self) -> dict[str, Any]:
        return {"nodes": [asdict(n) for n in self.nodes.values()], "edges": [asdict(e) for e in self.edges], "summary": self.summary(),
                "frontier": [{"id": n.id, "type": n.type, "label": n.label, "hints": n.hints} for n in self.frontier(20)]}

    def frontier_text(self, limit: int = 6) -> str:
        items = self.frontier(limit)
        if not items:
            return ""
        lines = ["Unexplored leads (each is backed by an admitted claim):"]
        for n in items:
            move = {"person": "identify their public profile and how they relate to the target; record as a connection with evidence",
                    "account": "read the profile page (exa_contents) and record what it states",
                    "domain": "read it and its archived versions (wayback_lookup)",
                    "email": "github_intel by email, gravatar_lookup",
                    "org": "search the target's name with this organization for roles, dates, colleagues",
                    "project": "read it; note collaborators and dates",
                    "document": "read it"}.get(n.type, "look into it")
            extra = f" ({n.hints['relation']} via {n.hints.get('via', '')})" if n.hints.get("relation") else ""
            lines.append(f"  - {n.type} {n.label}{extra}: {move}")
        return "\n".join(lines)
