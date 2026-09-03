"""Identity resolution in code. The model extracts candidate attributes; this module scores
them against the anchor set deterministically. Hard keys (email, profile URL, avatar hash,
handle) carry the weight; names are weak. A single matching field is capped; a hard
contradiction vetoes. The LLM judge (judge_candidates) only runs in the ambiguous band and
can never override a veto. No I/O in the scoring path, so it is unit-testable."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

# ----------------------------------------------------------------------------- models

Relation = Literal["current", "former", "unknown"]
TargetType = Literal["name", "email", "handle", "role_at_company"]
Status = Literal["resolved", "ambiguous", "unresolved"]


class CompanyRef(BaseModel):
    name: str
    relation: Relation = "unknown"


class Anchor(BaseModel):
    target_type: TargetType = "name"
    raw: str = ""
    names: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    handles: list[str] = Field(default_factory=list)
    companies: list[CompanyRef] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)


class Employment(BaseModel):
    name: str
    role: str | None = None
    start: str | None = None  # "YYYY" or "YYYY-MM"
    end: str | None = None    # None means current


class Evidence(BaseModel):
    claim: str
    source_url: str


class Candidate(BaseModel):
    id: str
    label: str
    names: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    handles: list[str] = Field(default_factory=list)
    profile_urls: list[str] = Field(default_factory=list)
    avatar_hash: str | None = None
    employers: list[Employment] = Field(default_factory=list)
    education: list[Employment] = Field(default_factory=list)  # schools, same shape (name, role=degree, start, end)
    locations: list[str] = Field(default_factory=list)
    bio: str | None = None
    disclaims_identity: bool = False  # page explicitly says "not the X at Y"
    evidence: list[Evidence] = Field(default_factory=list)
    first_seen_step: int = 0


class ScoreBreakdown(BaseModel):
    candidate_id: str
    score: float = 0.0
    fields: dict[str, float] = Field(default_factory=dict)      # similarity per compared field
    weights_used: dict[str, float] = Field(default_factory=dict)
    matched_markers: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    capped: bool = False
    gated: bool = False
    reason: str | None = None


class Judge(BaseModel):
    verdict: Literal["same", "different", "unsure"]
    candidate_id: str | None = None
    same_person_ids: list[str] = Field(default_factory=list)  # other candidate ids that are this same person
    reasons: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    model: str | None = None


class Resolution(BaseModel):
    status: Status = "unresolved"
    best_candidate_id: str | None = None
    score: float = 0.0
    matched_markers: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    runner_up: dict[str, Any] | None = None
    judge: Judge | None = None
    candidates_considered: int = 0
    breakdowns: list[ScoreBreakdown] = Field(default_factory=list)


# ----------------------------------------------------------------------------- weights and thresholds

WEIGHTS = {"email": 0.92, "url": 0.90, "avatar": 0.85, "handle": 0.70, "employer": 0.60,
           "role": 0.40, "location": 0.35, "name": 0.35}
HARD_KEYS = ("email", "url", "avatar", "handle")
NAME_GATE = 0.80
RESOLVED_SCORE = 0.85
AMBIGUOUS_SCORE = 0.60
RESOLVED_MARKERS = 3
RUNNER_UP_GAP = 0.10
SINGLE_FIELD_CAP = 0.60

# ----------------------------------------------------------------------------- normalizers

_COUNTRIES = {
    "united states": "us", "usa": "us", "us": "us", "u.s.": "us", "america": "us",
    "united kingdom": "uk", "uk": "uk", "england": "uk", "scotland": "uk", "wales": "uk",
    "canada": "ca", "india": "in", "pakistan": "pk", "germany": "de", "france": "fr", "spain": "es",
    "italy": "it", "netherlands": "nl", "sweden": "se", "norway": "no", "denmark": "dk", "finland": "fi",
    "poland": "pl", "ireland": "ie", "switzerland": "ch", "austria": "at", "belgium": "be", "portugal": "pt",
    "australia": "au", "new zealand": "nz", "japan": "jp", "china": "cn", "south korea": "kr", "korea": "kr",
    "singapore": "sg", "brazil": "br", "mexico": "mx", "argentina": "ar", "israel": "il", "turkey": "tr",
    "uae": "ae", "united arab emirates": "ae", "nigeria": "ng", "kenya": "ke", "south africa": "za",
    "egypt": "eg", "indonesia": "id", "vietnam": "vn", "philippines": "ph", "bangladesh": "bd",
}
_US_STATES = {"al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky", "la",
              "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
              "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc"}


def norm_email(e: str) -> str:
    return e.strip().lower()


def norm_handle(h: str) -> str:
    return h.strip().lstrip("@").lower()


def norm_url(u: str) -> str:
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


_HONORIFICS = {"dr", "prof", "professor", "mr", "mrs", "ms", "miss", "sir", "mx"}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "esq"}
_SCHOOL_WORDS = ("university", "college", "institute", "school", "polytechnic", "academy", "universidad",
                 "universit", "berkeley", "stanford", "harvard", "ucla", "caltech", "mit ", "uc ", "u of ")


def _is_school(name: str) -> bool:
    n = name.lower()
    return any(w in n for w in _SCHOOL_WORDS)


def norm_name(n: str) -> str:
    n = re.sub(r"[^\w\s]", " ", n.lower())
    toks = [t for t in n.split() if t not in _HONORIFICS and t not in _SUFFIXES]
    # if stripping removed everything (e.g. the input was just "Dr"), fall back to the raw tokens
    return " ".join(toks or n.split())


def _country(loc: str) -> str | None:
    parts = [p.strip().lower() for p in loc.split(",") if p.strip()]
    for part in reversed(parts):
        if part in _COUNTRIES:
            return _COUNTRIES[part]
        if part in _US_STATES or re.fullmatch(r"[a-z ]+ [a-z]{2}", part) and part.split()[-1] in _US_STATES:
            return "us"
    return None


def _loc_match(a: str, b: str) -> bool:
    ta = [p.strip().lower() for p in a.split(",") if p.strip()]
    tb = [p.strip().lower() for p in b.split(",") if p.strip()]
    return any(fuzz.token_set_ratio(x, y) >= 85 for x in ta for y in tb)


_ORG_STOP = {"university", "of", "the", "inc", "corp", "corporation", "llc", "ltd", "company", "co", "college",
             "institute", "group", "lab", "labs", "ai", "technologies", "technology", "tech", "and", "&", "at",
             "research", "center", "centre", "school", "department", "dept"}
_ORG_ALIASES = {"uc": "university of california", "ucb": "university of california berkeley", "mit": "massachusetts institute of technology",
                "cmu": "carnegie mellon university", "nyu": "new york university", "ucla": "university of california los angeles",
                "usc": "university of southern california", "ucsd": "university of california san diego"}


def _org_tokens(name: str) -> set[str]:
    n = re.sub(r"[^\w\s]", " ", name.lower())
    words = []
    for w in n.split():
        words.extend(_ORG_ALIASES.get(w, w).split())
    return {w for w in words if len(w) >= 4 and w not in _ORG_STOP}


def org_similarity(a: str, b: str) -> float:
    """1.0 for a fuzzy full match, 0.85 when the two names share a distinctive token
    (berkeley, sixtyfour, inferlink), else 0. Handles 'UC Berkeley BAIR' vs 'University of California, Berkeley'."""
    r = fuzz.token_set_ratio(a.lower(), b.lower()) / 100
    if r >= 0.85:
        return r
    if _org_tokens(a) & _org_tokens(b):
        return 0.85
    return 0.0


def _year(s: str | None) -> int | None:
    if not s:
        return None
    m = re.match(r"(\d{4})", s)
    return int(m.group(1)) if m else None


def is_current(emp: "Employment") -> bool:
    """No end date, or an end date in the future (a student graduating in 2027), counts as current."""
    from datetime import date
    y = _year(emp.end)
    return emp.end is None or emp.end == "" or (y is not None and y >= date.today().year)


# ----------------------------------------------------------------------------- scoring

def score_candidate(anchor: Anchor, cand: Candidate) -> ScoreBreakdown:
    b = ScoreBreakdown(candidate_id=cand.id)
    sims: dict[str, float] = {}

    # hard keys
    a_emails = {norm_email(e) for e in anchor.emails}
    c_emails = {norm_email(e) for e in cand.emails}
    if a_emails and c_emails:
        sims["email"] = 1.0 if a_emails & c_emails else 0.0
    a_urls = {norm_url(u) for u in anchor.urls}
    c_urls = {norm_url(u) for u in cand.profile_urls}
    if a_urls and c_urls:
        sims["url"] = 1.0 if a_urls & c_urls else 0.0
    a_handles = {norm_handle(h) for h in anchor.handles}
    c_handles = {norm_handle(h) for h in cand.handles}
    if a_handles and c_handles:
        sims["handle"] = 1.0 if a_handles & c_handles else 0.0
    # avatar: anchor has no avatar hash; it matches when two of the candidate's own sources share it,
    # so we treat a present avatar_hash as comparable only when the anchor email hashes to it (set by caller).
    # (kept simple: callers may put the anchor's email hash into anchor.urls as "gravatar:<hash>")
    a_avatar = {u.split(":", 1)[1] for u in anchor.urls if u.startswith("gravatar:")}
    if a_avatar and cand.avatar_hash:
        sims["avatar"] = 1.0 if cand.avatar_hash in a_avatar else 0.0

    # name
    name_best = 0.0
    if anchor.names and cand.names:
        name_best = max(JaroWinkler.normalized_similarity(norm_name(x), norm_name(y))
                        for x in anchor.names for y in cand.names)
        sims["name"] = name_best if name_best >= NAME_GATE else 0.0

    hard_hit = any(sims.get(k, 0.0) >= 1.0 for k in HARD_KEYS)
    if anchor.names and cand.names and not hard_hit and name_best < NAME_GATE:
        b.gated = True
        b.reason = f"name gate: best Jaro-Winkler {name_best:.2f} < {NAME_GATE} and no hard key match"
        b.fields = sims
        return b

    # employer (+ current bonus); schools count as affiliations too (a university is a valid anchor company)
    affiliations = cand.employers + cand.education
    if anchor.companies and affiliations:
        best = 0.0
        for ac in anchor.companies:
            for emp in affiliations:
                r = org_similarity(ac.name, emp.name)
                if r >= 0.85:
                    val = r
                    if ac.relation == "current" and is_current(emp):
                        val = min(1.0, val + 0.1)
                    best = max(best, val)
        sims["employer"] = best

    # role
    if anchor.roles and cand.employers:
        best = 0.0
        for ar in anchor.roles:
            for emp in cand.employers:
                if emp.role:
                    r = fuzz.token_set_ratio(ar.lower(), emp.role.lower()) / 100
                    if r >= 0.80:
                        best = max(best, r)
        sims["role"] = best

    # location
    if anchor.locations and cand.locations:
        sims["location"] = 1.0 if any(_loc_match(a, c) for a in anchor.locations for c in cand.locations) else 0.0

    # contradictions (vetoes) -- computed from structured fields only. The model-supplied
    # disclaims_identity flag is NOT a veto: in practice the model sets it while noting a
    # handle-collision on some OTHER page, and one misplaced boolean must not zero out a
    # candidate corroborated by hard evidence (it produced a 0-finding run). It is applied
    # below as a penalty + cap so the candidate lands in the ambiguous band and the judge decides.
    # a school marked "current" is where they studied, not a current employer -- do not veto on it
    current_anchor = [c for c in anchor.companies if c.relation == "current" and not _is_school(c.name)]
    if current_anchor and cand.employers:
        current_cand = [e for e in cand.employers if is_current(e)]
        anchor_matched = any(org_similarity(ac.name, e.name) >= 0.85
                             for ac in current_anchor for e in cand.employers + cand.education)
        # People hold several current roles (student + intern). Veto only when nothing the candidate lists,
        # current or past, matches the anchor's current company.
        if current_cand and not anchor_matched:
            b.contradictions.append(
                f"current employer mismatch: anchor says {current_anchor[0].name}, candidate is at {current_cand[0].name}")
    if anchor.locations and cand.locations:
        ac = {_country(l) for l in anchor.locations} - {None}
        cc = {_country(l) for l in cand.locations} - {None}
        if ac and cc and not (ac & cc) and not hard_hit:
            b.contradictions.append(f"country mismatch: anchor {sorted(ac)} vs candidate {sorted(cc)}")

    b.fields = sims
    b.weights_used = {k: WEIGHTS[k] for k in sims}
    if b.contradictions:
        b.score = 0.0
        b.reason = "vetoed: " + "; ".join(b.contradictions)
        return b

    if not sims:
        b.reason = "no comparable fields"
        return b
    num = sum(WEIGHTS[k] * v for k, v in sims.items())
    den = sum(WEIGHTS[k] for k in sims)
    score = num / den if den else 0.0
    if len(sims) == 1 and score > SINGLE_FIELD_CAP:
        score, b.capped = SINGLE_FIELD_CAP, True
    if cand.disclaims_identity:
        # penalize and cap below auto-resolve: a disclaimed candidate can only resolve via the judge
        score = min(score * 0.85, RESOLVED_SCORE - 0.01)
        b.reason = ((b.reason + "; ") if b.reason else "") + "disclaims_identity set: score penalized and capped below auto-resolve (judge decides)"
    b.score = round(score, 4)
    b.matched_markers = [k for k, v in sims.items() if v > 0]
    # Corroboration: the same person described on two independent sites (distinct domains) is a
    # marker in its own right. It lets a name + employer anchor resolve in code when a personal site,
    # LinkedIn and GitHub all agree, instead of always needing the judge.
    if "employer" in b.matched_markers:
        domains = {re.sub(r"^www\.", "", re.sub(r"^https?://", "", e.source_url).split("/")[0].lower())
                   for e in cand.evidence if e.source_url}
        if len(domains) >= 2:
            b.matched_markers.append("corroboration")
            b.fields["corroboration"] = float(len(domains))
    return b


def resolve(anchor: Anchor, candidates: list[Candidate]) -> Resolution:
    breakdowns = [score_candidate(anchor, c) for c in candidates]
    res = Resolution(candidates_considered=len(candidates), breakdowns=breakdowns)
    if not breakdowns:
        return res
    ranked = sorted(breakdowns, key=lambda x: -x.score)
    best = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    res.best_candidate_id = best.candidate_id
    res.score = best.score
    res.matched_markers = best.matched_markers
    res.contradictions = best.contradictions
    if runner:
        res.runner_up = {"id": runner.candidate_id, "score": runner.score}
    close_runner = runner is not None and runner.score > 0 and (best.score - runner.score) < RUNNER_UP_GAP
    if best.score >= RESOLVED_SCORE and len(best.matched_markers) >= RESOLVED_MARKERS and not close_runner:
        res.status = "resolved"
    elif best.score >= AMBIGUOUS_SCORE or (best.score > 0 and close_runner):
        res.status = "ambiguous"
    else:
        res.status = "unresolved"
    return res


def missing_evidence_hint(anchor: Anchor, b: ScoreBreakdown) -> str:
    """One line telling the model what would raise this candidate's score."""
    if b.gated:
        return "name does not match the target closely enough; only a hard key (email, handle, profile URL) can rescue it"
    if b.contradictions:
        return "vetoed; do not attribute findings to this candidate"
    missing = []
    if "email" not in b.fields:
        missing.append("an email (github_intel on their handle, then gravatar_lookup)")
    if "employer" not in b.fields and anchor.companies:
        missing.append("employer confirmation (LinkedIn, company team page, conference bio)")
    if "location" not in b.fields and anchor.locations:
        missing.append("location")
    if "handle" not in b.fields and anchor.handles:
        missing.append("a matching handle")
    if not missing:
        return "well supported; add one more independent source if fewer than 3 markers"
    return "would raise the score: " + "; ".join(missing)


def apply_judge(res: Resolution, judge: Judge) -> Resolution:
    """Judge may promote ambiguous -> resolved (same, >=2 cited reasons) or demote -> unresolved.
    Never overrides a veto (contradictions stay vetoed)."""
    res.judge = judge
    if res.status != "ambiguous":
        return res
    if judge.verdict == "same" and len([r for r in judge.reasons if "http" in r]) >= 2 and not res.contradictions:
        if judge.candidate_id in (None, res.best_candidate_id):
            res.status = "resolved"
    elif judge.verdict == "different":
        res.status = "unresolved"
    return res


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["same", "different", "unsure"]},
        "candidate_id": {"type": ["string", "null"]},
        "same_person_ids": {"type": "array", "items": {"type": "string"},
                            "description": "Ids of OTHER candidates that are the same real person as candidate_id (e.g. their LinkedIn and GitHub profiles recorded separately). Empty if none."},
        "reasons": {"type": "array", "items": {"type": "string"},
                    "description": "Each reason must cite a source URL in the text."},
        "confidence": {"type": "number"},
    },
    "required": ["verdict", "candidate_id", "same_person_ids", "reasons", "confidence"],
    "additionalProperties": False,
}

JUDGE_PROMPT = """You are settling whether a candidate profile is the same real person as the research target.
Be conservative: a wrong merge is worse than an unresolved one. Use only the evidence given; do not rely on
memory. 'same' requires at least two independent facts that both point to one person, each with its source URL
quoted in the reason. If the two candidates could each be the target, answer 'unsure'. If the candidates are
different profiles of ONE person (same name, same employer or school, same email or handle across pages), say so
in same_person_ids: they were recorded separately only because no shared hard key was captured."""


async def judge_candidates(llm: Any, model: str, anchor: Anchor, cands: list[Candidate],
                           breakdowns: list[ScoreBreakdown], evidence_text: str) -> Judge:
    payload = {
        "anchor": anchor.model_dump(),
        "candidates": [c.model_dump() for c in cands],
        "scores": [b.model_dump() for b in breakdowns],
        "evidence_excerpts": evidence_text[:12000],
    }
    import json as _json
    result = await llm.chat(
        [{"role": "system", "content": JUDGE_PROMPT},
         {"role": "user", "content": _json.dumps(payload, ensure_ascii=False)}],
        tools=None, model=model, thread="judge",
        response_format={"type": "json_schema", "json_schema": {"name": "judge", "strict": True, "schema": JUDGE_SCHEMA}},
    )
    try:
        data = _json.loads(result.text)
        return Judge(**data, model=model)
    except Exception:  # noqa: BLE001
        return Judge(verdict="unsure", reasons=[f"judge output unparseable: {result.text[:200]}"], model=model)
