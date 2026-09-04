"""Find public same-name pairs for the collision targets. Given a common name and a school, list
LinkedIn profiles that match through Exa's 'linkedin profile' category, and print candidate pairs
with the facts that distinguish them, for a human to confirm. Costs a few cents per query.

    uv run python evals/find_collisions.py "Michael Chen" "Stanford"
    uv run python evals/find_collisions.py "Priya Patel" "UC Berkeley" --num 10

Output is a JSON list of profiles (name, headline, url, snippet) plus a suggested pair. Nothing is
written to the golden file; pick the pair, then build the two entries by hand (with-key and
without-key) from the printed facts. Only public professional facts go into the golden file."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from osint2.config import load_dotenv  # noqa: E402

EXA_SEARCH_URL = "https://api.exa.ai/search"
PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"


def search_perplexity(name: str, school: str, num: int) -> list[dict]:
    """Fallback when Exa is unavailable: LinkedIn-filtered search snippets. Less complete than Exa's
    profile index but enough to surface a same-name pair for a human to confirm."""
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        sys.exit("neither EXA_API_KEY nor PERPLEXITY_API_KEY is set")
    body = {"query": f"{name} {school}", "max_results": min(num, 20), "search_domain_filter": ["linkedin.com"], "search_context_size": "low"}
    r = httpx.post(PERPLEXITY_SEARCH_URL, json=body, headers={"Authorization": f"Bearer {key}", "content-type": "application/json"}, timeout=60)
    r.raise_for_status()
    return [{"title": it.get("title"), "url": it.get("url"), "snippet": " ".join((it.get("snippet") or "").split())[:400]}
            for it in r.json().get("results", [])]


def search(name: str, school: str, num: int) -> list[dict]:
    key = os.environ.get("EXA_API_KEY", "")
    if not key:
        print("EXA_API_KEY is empty; using the Perplexity fallback (LinkedIn snippets)", file=sys.stderr)
        return search_perplexity(name, school, num)
    body = {"query": f"{name} {school}", "category": "linkedin profile", "numResults": num, "type": "auto",
            "contents": {"text": {"maxCharacters": 600}}}
    r = httpx.post(EXA_SEARCH_URL, json=body, headers={"x-api-key": key, "content-type": "application/json"}, timeout=60)
    r.raise_for_status()
    out = []
    for item in r.json().get("results", []):
        text = " ".join((item.get("text") or "").split())
        out.append({"title": item.get("title"), "url": item.get("url"), "snippet": text[:400]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("school")
    ap.add_argument("--num", type=int, default=10)
    args = ap.parse_args()
    load_dotenv()
    profiles = search(args.name, args.school, args.num)
    same = [p for p in profiles if args.name.lower().split()[0] in (p["title"] or "").lower()
            and args.name.lower().split()[-1] in (p["title"] or "").lower()]
    print(f"{len(profiles)} results, {len(same)} with the full name in the title\n")
    for i, p in enumerate(same, 1):
        print(f"{i}. {p['title']}\n   {p['url']}\n   {p['snippet']}\n")
    if len(same) >= 2:
        print("Suggested pair: 1 and 2 above. For the with-key target, add a hard key of person A to the target string "
              "(their LinkedIn slug or a handle). For the without-key target use only the name and school, expect "
              "status ambiguous with both names listed. Person B's distinguishing facts become decoys on the with-key entry.")
    print("\nJSON:")
    print(json.dumps(same, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
