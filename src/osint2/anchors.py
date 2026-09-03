"""Turn the freeform target into an Anchor. A regex pre-pass captures emails, URLs and @handles
deterministically (an email target must never depend on the model); one small LLM call fills
names, companies, roles, locations and the target type. Code wins on conflict. Salvaged from v1."""
from __future__ import annotations

import json
import re
from typing import Any

from .config import Settings
from .llm import OpenRouterClient
from .resolution import Anchor, CompanyRef

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s,]+|(?:www\.|linkedin\.com/|github\.com/|x\.com/|twitter\.com/)[^\s,]+")
HANDLE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_][A-Za-z0-9_.-]{1,38})")
DENY = {"in", "company", "orgs", "i", "about", "sponsors", "pub", "home", "explore"}

ANCHOR_SCHEMA = {
    "type": "object",
    "properties": {
        "target_type": {"type": "string", "enum": ["name", "email", "handle", "role_at_company"]},
        "names": {"type": "array", "items": {"type": "string"}},
        "companies": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "relation": {"type": "string", "enum": ["current", "former", "unknown"]}},
            "required": ["name", "relation"], "additionalProperties": False}},
        "roles": {"type": "array", "items": {"type": "string"}},
        "locations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["target_type", "names", "companies", "roles", "locations"],
    "additionalProperties": False,
}

PROMPT = """Extract the research anchor from a freeform description of a person. Return only what the text
states or clearly implies; never add facts from memory.
- names: full name variants written in the text (empty if none, e.g. for an email-only target).
- companies: each with relation 'current' (works there now), 'former' (ex-, formerly, previously, before), or
  'unknown'. If the text names an organization and a unit inside it, list both. A bare 'name, company' means 'current'.
- roles: job titles or roles mentioned.
- locations: places mentioned.
- target_type: 'email' if the text is essentially an email address; 'handle' if it is a username;
  'role_at_company' if it names a role at a company but no person's name; otherwise 'name'."""


def prefill(target: str) -> Anchor:
    emails = sorted({m.lower() for m in EMAIL_RE.findall(target)})
    urls = sorted({m.rstrip(".,)") for m in URL_RE.findall(target)})
    handles = sorted({m for m in HANDLE_RE.findall(target)})
    rest = target
    for x in emails + urls:
        rest = rest.replace(x, " ")
    rest = HANDLE_RE.sub(" ", rest)
    words = [w for w in re.split(r"[\s,;|]+", rest) if w]
    url_handles = []
    for u in urls:
        m = re.search(r"(?:github\.com|x\.com|twitter\.com|instagram\.com)/@?([A-Za-z0-9_.-]+)", u)
        if m and m.group(1).lower() not in DENY:
            url_handles.append(m.group(1))
    handles = sorted(set(handles) | set(url_handles))
    if emails and len(words) <= 1:
        ttype = "email"
    elif handles and len(words) <= 1:
        ttype = "handle"
    elif len(words) == 1 and re.fullmatch(r"[A-Za-z0-9_.\-]{3,39}", words[0]) and not re.fullmatch(r"[A-Z][a-z]+", words[0]):
        # a single bare token like 'Ranoobaba' is a handle, not a name
        ttype = "handle"
        handles = sorted(set(handles) | {words[0]})
    else:
        ttype = "name"
    return Anchor(target_type=ttype, raw=target, emails=emails, urls=urls, handles=handles)


async def parse_anchor(target: str, llm: OpenRouterClient | None, settings: Settings) -> Anchor:
    anchor = prefill(target)
    data: dict[str, Any] | None = None
    if llm is not None and anchor.target_type not in ("email", "handle"):
        messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": target}]
        try:
            result = await llm.chat(messages, tools=None, model=settings.lead_model, thread="anchor", reasoning=False,
                                    response_format={"type": "json_schema", "json_schema": {"name": "anchor", "strict": True, "schema": ANCHOR_SCHEMA}})
            data = json.loads(result.text)
        except Exception:  # noqa: BLE001
            try:
                result = await llm.chat(messages + [{"role": "user", "content": "Reply with one JSON object only, keys: target_type, names, companies, roles, locations."}],
                                        tools=None, model=settings.lead_model, thread="anchor", reasoning=False)
                text = result.text
                data = json.loads(text[text.find("{"): text.rfind("}") + 1])
            except Exception:  # noqa: BLE001
                data = None
    if data:
        if anchor.target_type == "name" and data.get("target_type") in ("role_at_company", "name"):
            anchor.target_type = data["target_type"]
        anchor.names = sorted({*anchor.names, *[n.strip() for n in data.get("names", []) if n and n.strip()]})
        anchor.companies = [CompanyRef(name=c["name"].strip(), relation=c.get("relation", "unknown"))
                            for c in data.get("companies", []) if c.get("name")]
        anchor.roles = [r.strip() for r in data.get("roles", []) if r.strip()]
        anchor.locations = [loc.strip() for loc in data.get("locations", []) if loc.strip()]
    elif anchor.target_type == "name" and not anchor.names:
        t = target.strip()
        looks_like_name = ("://" not in t and "@" not in t and "/" not in t
                           and not re.fullmatch(r"[\d\s()+.\-]{7,}", t) and 0 < len(t.split()) <= 5)
        if looks_like_name:
            anchor.names = [t]
    return anchor
