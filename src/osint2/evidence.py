"""Sources and claims. A source is a tool result stored on disk with its sha256. A claim is what the
model proposes; code decides whether it is admitted, per kind:

  finding    needs a source_id from this run and an excerpt that re-anchors in that source's text
             (exact after normalization, else rapidfuzz partial alignment >= 95). The stored excerpt
             is the RAW source span at the anchored offsets, never the model's text. The span must
             contain the value. Code stamps content_hash and method; model-supplied values for
             those fields are ignored.
  not_found  needs searched[] naming at least one source id or data tool from this run.
  conflict   needs two admitted finding ids with the same field and different values.
  synthesis  needs two or more admitted finding ids in based_on; never attributed for scoring.
"""
from __future__ import annotations

import re

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from .workspace import Workspace

Kind = Literal["finding", "not_found", "conflict", "synthesis"]
MARKDOWN_CHARS = set("*_#`>|")
REANCHOR_SCORE = 92.0
EXTEND_WINDOW = 400   # chars the span may grow to reach the value in the same source

# tool name -> method label on the claim
METHOD_BY_TOOL = {
    "github_intel": "github_commit_email", "gravatar_lookup": "gravatar", "wayback_lookup": "wayback",
    "whatsmyname": "whatsmyname", "web_search": "web_search", "exa_contents": "exa_contents",
    "fetch_page": "fetch_page", "subagent": "subagent", "anchor": "anchor", "openalex_lookup": "openalex",
    "roblox_lookup": "roblox", "tinder_check": "tinder", "holehe_check": "holehe", "people_search": "people_search", "profile_read": "profile_read",
}


def normalize(text: str) -> tuple[str, list[int]]:
    """NFKC, casefold, markdown chars to spaces, whitespace collapsed. Returns the normalized text
    and, for every normalized character, the raw offset it came from, so a match in normalized
    space maps back to a verbatim raw span."""
    raw = str(text or "")
    out: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for i, ch in enumerate(raw):
        n = unicodedata.normalize("NFKC", ch).casefold()
        if ch in MARKDOWN_CHARS or n.isspace():
            pending_space = True
            continue
        if pending_space and out:
            out.append(" ")
            offsets.append(i)
        pending_space = False
        for c in n:
            out.append(c)
            offsets.append(i)
    return "".join(out), offsets


def norm_text(text: str) -> str:
    return normalize(text)[0]


def anchor_excerpt(source_text: str, excerpt: str) -> Optional[tuple[int, int, float]]:
    """Locate the model's excerpt in the source. Returns raw (start, end, score) or None."""
    ns, offsets = normalize(source_text)
    ne, _ = normalize(excerpt)
    if not ne or not ns:
        return None
    pos = ns.find(ne)
    if pos >= 0:
        return offsets[pos], offsets[pos + len(ne) - 1] + 1, 100.0
    if len(ne) < 12:
        return None
    al = fuzz.partial_ratio_alignment(ne, ns)
    if al is None or al.score < REANCHOR_SCORE or al.dest_end <= al.dest_start:
        return None
    return offsets[al.dest_start], offsets[min(al.dest_end, len(offsets)) - 1] + 1, float(al.score)


META_VALUE_RE = re.compile(r"\b(fetch_page|exa_contents|web_search|whatsmyname|returned only|HTML framework|no (public )?(profile|page)|could not (be )?(read|fetch|load)|unable to|not accessible|login wall)\b", re.I)


@dataclass
class Source:
    id: str
    tool: str
    args: dict[str, Any]
    path: str
    url: Optional[str]
    content_hash: str
    step: int = 0
    chars: int = 0


class Claim(BaseModel):
    id: str
    kind: Kind = "finding"
    field: str
    value: str = ""
    category: Optional[str] = None
    confidence: float = 0.0
    sensitive: bool = False
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    excerpt: Optional[str] = None
    excerpt_span: Optional[list[int]] = None
    content_hash: Optional[str] = None
    method: Optional[str] = None
    candidate_id: Optional[str] = None
    based_on: list[str] = Field(default_factory=list)
    searched: list[str] = Field(default_factory=list)
    step: int = 0
    thread: str = "lead"


class EvidenceStore:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.sources: dict[str, Source] = {}
        self.claims: list[Claim] = []
        self.rejected: list[dict[str, Any]] = []
        self.proposed = 0
        raw = ws.read_json("sources.json") or []
        for s in raw:
            self.sources[s["id"]] = Source(**s)
        cpath = ws.dir / "claims.jsonl"
        if cpath.exists():
            for line in cpath.read_text().splitlines():
                if line.strip():
                    self.claims.append(Claim(**json.loads(line)))

    # ---------------------------------------------------------------- sources
    def add_source(self, tool: str, args: dict[str, Any], text: str, url: str | None, step: int) -> Source:
        sid = f"s{len(self.sources) + 1:03d}"
        rel = self.ws.write_source(tool, f"{sid}_{url or json.dumps(args, sort_keys=True)[:40]}", text)
        digest = hashlib.sha256((self.ws.dir / rel).read_bytes()).hexdigest()
        src = Source(id=sid, tool=tool, args=args, path=rel, url=url, content_hash=digest, step=step, chars=len(text))
        self.sources[sid] = src
        self.ws.write_json("sources.json", [asdict(s) for s in self.sources.values()])
        return src

    def source_text(self, sid: str) -> str:
        src = self.sources[sid]
        return (self.ws.dir / src.path).read_text()

    def source_id_for_path(self, rel: str) -> Optional[str]:
        return next((s.id for s in self.sources.values() if s.path == rel), None)

    # ----------------------------------------------------------------- claims
    def findings(self) -> list[Claim]:
        return [c for c in self.claims if c.kind == "finding"]

    def by_id(self, cid: str) -> Optional[Claim]:
        return next((c for c in self.claims if c.id == cid), None)

    def _persist(self, claim: Claim) -> None:
        with (self.ws.dir / "claims.jsonl").open("a", encoding="utf-8") as f:
            f.write(claim.model_dump_json() + "\n")

    def admit(self, proposal: dict[str, Any], *, step: int = 0, thread: str = "lead",
              default_candidate: str | None = None) -> tuple[Optional[Claim], Optional[str]]:
        """Returns (claim, None) when admitted or (None, reason) when rejected."""
        self.proposed += 1
        kind = proposal.get("kind") or "finding"
        field_name = str(proposal.get("field") or "").strip()
        if not field_name:
            return self._reject(proposal, "missing field")
        cid = f"c{len(self.claims) + 1:03d}"
        base = dict(id=cid, kind=kind, field=field_name, value=str(proposal.get("value") or "").strip(),
                    category=proposal.get("category"), sensitive=bool(proposal.get("sensitive")),
                    candidate_id=proposal.get("candidate_id") or default_candidate, step=step, thread=thread)

        if kind == "finding":
            if not base["value"]:
                return self._reject(proposal, "missing value")
            if META_VALUE_RE.search(base["value"]):
                return self._reject(proposal, "the value describes a tool result, not a fact about the person; record nothing for it")
            sid = proposal.get("source_id")
            if not sid or sid not in self.sources:
                return self._reject(proposal, f"unknown source_id {sid!r}; cite a source id returned by a tool in this run")
            excerpt = str(proposal.get("excerpt") or "")
            if not excerpt.strip():
                return self._reject(proposal, "missing excerpt; quote the sentence you read")
            text = self.source_text(sid)
            loc = anchor_excerpt(text, excerpt)
            if loc is None:
                return self._reject(proposal, "excerpt not found in the source; quote it verbatim")
            start, end, score = loc
            nv = norm_text(base["value"])
            if not self._contains(text[start:end], nv):
                # The model quoted a nearby line. If the value sits within EXTEND_WINDOW chars of the
                # quoted span in the same source, grow the span to include it: the stored excerpt is
                # still verbatim source text. Otherwise reject and show the line to quote.
                grown = self._extend_to_value(text, start, end, nv)
                if grown is None and len(nv) > len(norm_text(text[start:end])) + 8:
                    return self._reject(proposal, "the value says more than the quoted line does; record only what the source states, in its words")
                if grown is None:
                    hint = self._line_with_value(text, nv)
                    if hint:
                        return self._reject(proposal, f"the excerpt does not contain the value; the source states it here, quote this line: {hint[:200]!r}")
                    return self._reject(proposal, "the excerpt does not contain the value, and the value does not appear in that source at all; do not record it from this source")
                start, end = grown
            span = text[start:end]
            src = self.sources[sid]
            claim = Claim(**base, source_id=sid, source_url=src.url or proposal.get("source_url"),
                          excerpt=span, excerpt_span=[start, end], content_hash=src.content_hash,
                          method=METHOD_BY_TOOL.get(src.tool, src.tool))
        elif kind == "not_found":
            searched = [str(s) for s in (proposal.get("searched") or []) if s]
            known = set(self.sources) | {s.tool for s in self.sources.values()}
            if not searched or not any(s in known for s in searched):
                return self._reject(proposal, "not_found needs searched[] naming a source id or tool used in this run")
            claim = Claim(**base, searched=searched, confidence=1.0)
        elif kind == "conflict":
            ids = [str(x) for x in (proposal.get("based_on") or [])]
            fs = [self.by_id(x) for x in ids]
            fs = [f for f in fs if f and f.kind == "finding"]
            if len(fs) < 2 or len({f.field for f in fs}) != 1 or len({norm_text(f.value) for f in fs}) < 2:
                return self._reject(proposal, "conflict needs two admitted finding ids with the same field and different values")
            base.update(field=fs[0].field, value=" | ".join(f.value for f in fs))
            claim = Claim(**base, based_on=[f.id for f in fs])
        elif kind == "synthesis":
            ids = [str(x) for x in (proposal.get("based_on") or [])]
            fs = [self.by_id(x) for x in ids]
            fs = [f for f in fs if f and f.kind == "finding"]
            if len(fs) < 2:
                return self._reject(proposal, "synthesis needs two or more admitted finding ids in based_on")
            if not base["value"]:
                return self._reject(proposal, "missing value")
            claim = Claim(**base, based_on=[f.id for f in fs])
        else:
            return self._reject(proposal, f"unknown kind {kind!r}")
        self.claims.append(claim)
        self._persist(claim)
        return claim, None

    @staticmethod
    def _contains(span: str, nv: str) -> bool:
        """The value must be inside the span. A value longer than the span cannot be inside it: that
        is the model adding words the source does not state, and it is rejected outright."""
        nspan = norm_text(span)
        if "@" in nv or "/" in nv:
            return nv in nspan
        if nv in nspan:
            return True
        if len(nv) > len(nspan) + 8:
            return False
        return fuzz.partial_ratio(nv, nspan) >= REANCHOR_SCORE

    def _extend_to_value(self, text: str, start: int, end: int, nv: str) -> Optional[tuple[int, int]]:
        ns, offsets = normalize(text)
        pos = ns.find(nv)
        if pos < 0:
            return None
        # map every occurrence; pick the one nearest the quoted span
        best = None
        while pos >= 0:
            vs, ve = offsets[pos], offsets[pos + len(nv) - 1] + 1
            dist = 0 if (vs < end and ve > start) else min(abs(vs - end), abs(start - ve))
            if dist <= EXTEND_WINDOW and (best is None or dist < best[0]):
                best = (dist, vs, ve)
            pos = ns.find(nv, pos + 1)
        if best is None:
            return None
        _, vs, ve = best
        return min(start, vs), max(end, ve)

    @staticmethod
    def _line_with_value(text: str, nv: str) -> Optional[str]:
        for line in text.splitlines():
            if nv and nv in norm_text(line):
                return line.strip()
        return None

    def _reject(self, proposal: dict[str, Any], reason: str) -> tuple[None, str]:
        self.rejected.append({"proposal": {k: (str(v)[:200] if v is not None else None) for k, v in proposal.items()}, "reason": reason})
        self.ws.write_json("rejected.json", self.rejected)
        return None, reason

    def stats(self) -> dict[str, int]:
        return {"sources": len(self.sources), "proposed": self.proposed, "admitted": len(self.claims),
                "rejected": len(self.rejected), "findings": len(self.findings())}
