"""github_intel: the named OSINT tactic. Git commits permanently record the author's email even when
the GitHub profile hides it, and that data is on no HTML page. Given a username, read the profile,
the public event stream and recent commits to recover real emails with repo@sha evidence. Given an
email, reverse the pivot through GitHub's user and commit search. Given a name, search profile
names. Salvaged from v1."""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from typing import Any

from . import RunContext, Tool, ToolResult
from ._http import UA, request_with_retry

API = "https://api.github.com"
NOREPLY = "users.noreply.github.com"


def _headers() -> tuple[dict[str, str], bool]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA, "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers, bool(token)


async def _get(path: str, **params: Any) -> tuple[int, Any, dict[str, str]]:
    headers, _ = _headers()
    url = path if path.startswith("http") else API + path
    response, _ = await request_with_retry("GET", url, headers=headers, params=params or None, timeout=30.0)
    try:
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
    except ValueError:
        data = response.text
    return response.status_code, data, {k.lower(): v for k, v in response.headers.items()}


def _classify(email: str) -> str:
    return "private_noreply" if email.lower().endswith(NOREPLY) else "real"


class EmailLedger:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "evidence": [], "names": defaultdict(int)})

    def add(self, email: str | None, name: str | None, evidence: str) -> None:
        if not email or "@" not in email:
            return
        email = email.strip().lower()
        row = self.rows[email]
        row["count"] += 1
        if name:
            row["names"][name.strip()] += 1
        if len(row["evidence"]) < 5 and evidence not in row["evidence"]:
            row["evidence"].append(evidence)

    def summary(self) -> list[dict[str, Any]]:
        out = []
        for email, row in sorted(self.rows.items(), key=lambda kv: -kv[1]["count"]):
            names = sorted(row["names"].items(), key=lambda kv: -kv[1])
            out.append({"email": email, "kind": _classify(email), "count": row["count"],
                        "names": [n for n, _ in names[:3]], "evidence": row["evidence"]})
        return out


async def _by_username(username: str, max_repos: int) -> tuple[dict[str, Any], str | None]:
    status, profile, hdrs = await _get(f"/users/{username}")
    if status == 404:
        return {}, f"GitHub user '{username}' does not exist."
    if status in (403, 429):
        return {}, f"GitHub rate limit hit (remaining={hdrs.get('x-ratelimit-remaining')}). Set GITHUB_TOKEN or wait."
    if status != 200:
        return {}, f"GitHub returned HTTP {status} for user '{username}'."
    ledger = EmailLedger()
    if profile.get("email"):
        ledger.add(profile["email"], profile.get("name"), "profile public email field")
    status_ev, events, _ = await _get(f"/users/{username}/events/public", per_page=100)
    push_commits = 0
    if status_ev == 200 and isinstance(events, list):
        for ev in events:
            if ev.get("type") != "PushEvent":
                continue
            repo = (ev.get("repo") or {}).get("name", "?")
            for c in (ev.get("payload") or {}).get("commits", []) or []:
                author = c.get("author") or {}
                ledger.add(author.get("email"), author.get("name"), f"push event {repo}@{(c.get('sha') or '')[:7]}")
                push_commits += 1
    status_r, repos, _ = await _get(f"/users/{username}/repos", sort="pushed", per_page=30, type="owner")
    own_repos = [r for r in repos if not r.get("fork")] if status_r == 200 and isinstance(repos, list) else []
    top = own_repos[:max_repos]

    async def commits_for(repo: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        st, data, _ = await _get(f"/repos/{repo['full_name']}/commits", author=username, per_page=10)
        return repo["full_name"], data if st == 200 and isinstance(data, list) else []

    scanned = await asyncio.gather(*(commits_for(r) for r in top))
    commit_count = 0
    for full_name, commits in scanned:
        for c in commits:
            author = ((c.get("commit") or {}).get("author") or {})
            ledger.add(author.get("email"), author.get("name"), f"{full_name}@{(c.get('sha') or '')[:7]}")
            commit_count += 1
    st_keys, keys_text, _ = await _get(f"https://github.com/{username}.keys")
    ssh_keys = len([ln for ln in str(keys_text).splitlines() if ln.strip()]) if st_keys == 200 else 0
    return {
        "profile": {k: profile.get(k) for k in ("login", "name", "company", "blog", "location", "bio", "email", "twitter_username",
                                                 "created_at", "avatar_url", "public_repos", "followers", "html_url")},
        "emails": ledger.summary(),
        "repos": [{"name": r["name"], "description": r.get("description"), "language": r.get("language"),
                   "stars": r.get("stargazers_count"), "pushed_at": r.get("pushed_at"), "url": r.get("html_url")} for r in own_repos[:10]],
        "stats": {"push_events_commits": push_commits, "repos_scanned": len(top), "commits_scanned": commit_count,
                  "ssh_keys": ssh_keys, "rate_limit_remaining": hdrs.get("x-ratelimit-remaining")},
    }, None


async def _by_email(email: str) -> tuple[dict[str, Any], str | None]:
    email = email.strip().lower()
    _, authenticated = _headers()
    out: dict[str, Any] = {"email": email, "users_by_public_email": [], "commit_authors": [], "authenticated": authenticated}
    st, users, hdrs = await _get("/search/users", q=f"{email} in:email", per_page=10)
    if st == 200 and isinstance(users, dict):
        out["users_by_public_email"] = [{"login": u.get("login"), "url": u.get("html_url")} for u in users.get("items", [])]
    elif st in (403, 429):
        return out, f"GitHub rate limit hit (remaining={hdrs.get('x-ratelimit-remaining')}). Set GITHUB_TOKEN or wait."
    if not authenticated:
        out["note"] = "Commit search (author-email:) needs GITHUB_TOKEN; only the public-email-field search ran."
        return out, None
    st, commits, hdrs = await _get("/search/commits", q=f"author-email:{email}", per_page=30, sort="author-date")
    if st == 200 and isinstance(commits, dict):
        by_login: dict[str, dict[str, Any]] = defaultdict(lambda: {"commits": 0, "repos": set(), "names": set()})
        for item in commits.get("items", []):
            author = item.get("author") or {}
            login = author.get("login") or "(no linked account)"
            row = by_login[login]
            row["commits"] += 1
            row["repos"].add((item.get("repository") or {}).get("full_name", "?"))
            name = ((item.get("commit") or {}).get("author") or {}).get("name")
            if name:
                row["names"].add(name)
        out["commit_authors"] = [{"login": k, "commits": v["commits"], "repos": sorted(v["repos"])[:5], "names": sorted(v["names"])[:3]}
                                 for k, v in by_login.items()]
        out["total_commits_matching"] = commits.get("total_count")
    else:
        out["note"] = f"commit search returned HTTP {st}"
    out["rate_limit_remaining"] = hdrs.get("x-ratelimit-remaining")
    return out, None


async def _by_name(name: str, hint: str | None) -> tuple[dict[str, Any], str | None]:
    q = f'"{name.strip()}" in:name'
    if hint:
        q += f" {hint.strip()}"
    st, data, hdrs = await _get("/search/users", q=q, per_page=10)
    if st in (403, 429):
        return {}, f"GitHub rate limit hit (remaining={hdrs.get('x-ratelimit-remaining')}). Set GITHUB_TOKEN or wait."
    if st != 200 or not isinstance(data, dict):
        return {}, f"GitHub user search returned HTTP {st}."
    logins = [u.get("login") for u in data.get("items", [])][:8]

    async def profile(login: str) -> dict[str, Any]:
        st2, p, _ = await _get(f"/users/{login}")
        if st2 != 200 or not isinstance(p, dict):
            return {"login": login}
        return {k: p.get(k) for k in ("login", "name", "company", "location", "bio", "blog", "public_repos", "followers", "created_at", "html_url")}

    profiles = await asyncio.gather(*(profile(lg) for lg in logins))
    return {"query": q, "total": data.get("total_count"), "profiles": list(profiles), "rate_limit_remaining": hdrs.get("x-ratelimit-remaining")}, None


def _render_name(d: dict[str, Any]) -> str:
    lines = [f"# github_intel: user search {d['query']}  (total matches: {d['total']})", ""]
    if not d["profiles"]:
        lines.append("No GitHub accounts whose profile name matches. Try a shorter name form or drop the hint.")
    for p in d["profiles"]:
        bio = " ".join(str(p.get("bio") or "").split())[:120]
        lines.append(f"- {p.get('login')}: name={p.get('name')!r} company={p.get('company')!r} location={p.get('location')!r} "
                     f"repos={p.get('public_repos')} created={str(p.get('created_at'))[:10]} {p.get('html_url')}")
        if bio:
            lines.append(f"    bio: {bio}")
    lines.append("")
    lines.append("Next: for any account whose company/location/bio fits, github_intel(username=...) recovers commit emails; then record_candidate.")
    return "\n".join(lines)


def _render_user(d: dict[str, Any]) -> str:
    p = d["profile"]
    lines = [f"# github_intel: {p.get('login')}", "",
             f"profile: name={p.get('name')!r} company={p.get('company')!r} location={p.get('location')!r} blog={p.get('blog')!r} "
             f"twitter={p.get('twitter_username')!r} created={str(p.get('created_at'))[:10]} public_repos={p.get('public_repos')} followers={p.get('followers')}"]
    if p.get("bio"):
        lines.append(f"bio: {' '.join(str(p['bio']).split())[:300]}")
    lines.append(f"url: {p.get('html_url')}  avatar: {p.get('avatar_url')}")
    lines.append("")
    real = [e for e in d["emails"] if e["kind"] == "real"]
    noreply = [e for e in d["emails"] if e["kind"] != "real"]
    lines.append(f"emails recovered from commit metadata: {len(real)} real, {len(noreply)} github-noreply (ignore those)")
    for e in real:
        lines.append(f"  - {e['email']}  x{e['count']}  names={e['names']}  evidence={e['evidence'][:3]}")
    if not real:
        lines.append("  (no real email in scanned commits; the account may use GitHub's noreply address)")
    lines.append("")
    lines.append(f"top repos (own, by last push): {len(d['repos'])}")
    for r in d["repos"][:6]:
        desc = " ".join((r.get("description") or "").split())[:100]
        lines.append(f"  - {r['name']} [{r.get('language')}] stars={r.get('stars')} pushed={str(r.get('pushed_at'))[:10]} {desc}")
    s = d["stats"]
    lines.append("")
    lines.append(f"scanned: {s['repos_scanned']} repos, {s['commits_scanned']} commits, {s['push_events_commits']} push-event commits; ssh_keys={s['ssh_keys']}")
    return "\n".join(lines)


def _render_email(d: dict[str, Any]) -> str:
    lines = [f"# github_intel: email {d['email']}", "", f"accounts with this public email: {[u['login'] for u in d['users_by_public_email']] or 'none'}"]
    if d.get("commit_authors"):
        lines.append(f"commit authors using this email ({d.get('total_commits_matching')} matching commits):")
        for a in d["commit_authors"]:
            lines.append(f"  - {a['login']}: {a['commits']} commits in {a['repos']} names={a['names']}")
        lines.append("Next: github_intel(username=<login>) to read the profile and confirm the email from its own commits.")
    else:
        lines.append("commit authors using this email: none found" + ("" if d.get("authenticated") else " (commit search skipped)"))
    if d.get("note"):
        lines.append(f"note: {d['note']}")
    return "\n".join(lines)


async def _github_intel(ctx: RunContext, username: str | None = None, email: str | None = None,
                        name: str | None = None, hint: str | None = None, max_repos: int = 3) -> ToolResult:
    given = [x for x in (username, email, name) if x]
    if len(given) != 1:
        return ToolResult(content="github_intel needs exactly one of username, email, or name.", error="BadArguments")
    max_repos = max(1, min(int(max_repos), 6))
    if name:
        data, err = await _by_name(name, hint)
        if err:
            return ToolResult(content=f"github_intel: {err}", error="Lookup")
        return ToolResult(content=_render_name(data), url=f"https://github.com/search?q={name}&type=users",
                          meta={"mode": "name", "accounts_found": len(data["profiles"])})
    if username:
        username = username.strip().lstrip("@")
        data, err = await _by_username(username, max_repos)
        if err:
            return ToolResult(content=f"github_intel: {err}", error="Lookup")
        real = [e for e in data["emails"] if e["kind"] == "real"]
        return ToolResult(content=_render_user(data), url=data["profile"].get("html_url") or f"https://github.com/{username}",
                          meta={"mode": "username", "emails_real": len(real), "commits_scanned": data["stats"]["commits_scanned"]})
    data, err = await _by_email(email)
    if err:
        return ToolResult(content=f"github_intel: {err}", error="Lookup")
    return ToolResult(content=_render_email(data), url=f"https://api.github.com/search/commits?q=author-email:{email}",
                      meta={"mode": "email", "accounts_found": len(data["users_by_public_email"]) + len(data.get("commit_authors", []))})


github_intel = Tool(
    name="github_intel",
    description=(
        "OSINT on GitHub. Git commits permanently record the author's email even when the profile hides it. "
        "Given a username: profile, real emails recovered from public commits and push events (with repo@sha evidence), top repos. "
        "Given an email: which GitHub accounts authored commits with it (reverse pivot). Given a name: GitHub's search over "
        "profile names (add hint, e.g. a city or employer word). A recovered email is hard identity evidence: follow it with "
        "gravatar_lookup and record_candidate."
    ),
    parameters={"type": "object", "properties": {
        "username": {"type": "string", "description": "GitHub login. Use this OR email OR name."},
        "email": {"type": "string", "description": "Email to reverse into GitHub accounts."},
        "name": {"type": "string", "description": "Full name to search GitHub profile names for."},
        "hint": {"type": "string", "description": "With name: one narrowing word, e.g. 'Berkeley'."},
        "max_repos": {"type": "integer", "description": "Own repos to scan for commits, 1 to 6. Default 3.", "default": 3},
    }},
    fn=_github_intel, requires=("github",),
)
