"""Settings from the environment. Every mechanism the ladder can switch is a field here, read from
an env var, so a rung is nothing more than a set of env overrides."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALL_DATA_TOOLS = ("github", "gravatar", "wayback", "whatsmyname", "perplexity", "exa", "firecrawl")
BOOKKEEPING_TOOLS = ("record_candidate", "record_claim", "record_not_found", "finish")

# Dollars per call, charged to the run budget at reserve time and settled after the call.
# Updated from each dashboard when the paid tool lands (Stages 4 to 6).
TOOL_PRICES: dict[str, float] = {
    "web_search": 0.005,       # perplexity or exa search
    "exa_contents": 0.001,     # per page
    "fetch_page": 0.002,       # firecrawl scrape
    "github_intel": 0.0, "gravatar_lookup": 0.0, "wayback_lookup": 0.0, "whatsmyname": 0.0,
}


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] in ('"', "'") and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if key:
            os.environ.setdefault(key, value)


def _flag(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v not in ("0", "false", "False", "no", "off")


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    perplexity_api_key: str
    exa_api_key: str
    firecrawl_api_key: str
    github_token: str
    lead_model: str
    judge_model: str
    tools: tuple[str, ...]
    deep_dive: bool
    max_tool_calls: int
    max_usd: float
    max_seconds: int
    max_steps: int
    saturation_dry_steps: int
    prune_steps: int
    reasoning_max_tokens: int
    max_output_tokens: int
    nudges: frozenset[str]
    runs_dir: Path
    app_url: str
    agent_api_key: str

    @classmethod
    def from_env(cls, overrides: dict[str, Any] | None = None) -> "Settings":
        load_dotenv()
        env = dict(os.environ)
        if overrides:
            env.update({k: str(v) for k, v in overrides.items() if v is not None})
        tools_raw = env.get("TOOLS", ",".join(ALL_DATA_TOOLS))
        tools = tuple(t.strip() for t in tools_raw.split(",") if t.strip() and t.strip() != "none")
        unknown = [t for t in tools if t not in ALL_DATA_TOOLS]
        if unknown:
            raise ValueError(f"unknown TOOLS entries {unknown}; allowed {ALL_DATA_TOOLS}")
        nudges = frozenset(k for k, v in env.items() if k.startswith("NUDGE_") and _flag(v, False))
        return cls(
            openrouter_api_key=env.get("OPENROUTER_API_KEY", ""),
            perplexity_api_key=env.get("PERPLEXITY_API_KEY", ""),
            exa_api_key=env.get("EXA_API_KEY", ""),
            firecrawl_api_key=env.get("FIRECRAWL_API_KEY", ""),
            github_token=env.get("GITHUB_TOKEN", ""),
            lead_model=env.get("LEAD_MODEL", "anthropic/claude-opus-5"),
            judge_model=env.get("JUDGE_MODEL", "openai/gpt-5.6-luna"),
            tools=tools,
            deep_dive=_flag(env.get("DEEP_DIVE"), False),
            max_tool_calls=int(env.get("MAX_TOOL_CALLS", "20")),
            max_usd=float(env.get("MAX_USD", "1.25")),
            max_seconds=int(env.get("MAX_SECONDS", "480")),
            max_steps=int(env.get("MAX_STEPS", "60")),
            saturation_dry_steps=int(env.get("SATURATION_DRY_STEPS", "3")),
            # 0 keeps every tool result in the window (append-only, so Anthropic prompt caching hits);
            # N replaces results older than N steps with a stub (smaller window, cache prefix rewritten).
            prune_steps=int(env.get("PRUNE_STEPS", "0")),
            reasoning_max_tokens=int(env.get("REASONING_MAX_TOKENS", "1024")),
            max_output_tokens=int(env.get("MAX_OUTPUT_TOKENS", "6000")),
            nudges=nudges,
            runs_dir=Path(env.get("RUNS_DIR", "runs")),
            app_url=env.get("APP_URL", "https://github.com/Ranoobaba/osint-agent-v2"),
            agent_api_key=env.get("AGENT_API_KEY", ""),
        )

    def flags(self) -> dict[str, Any]:
        """What this run was configured with; written into report.run so a row is reproducible."""
        return {"tools": list(self.tools), "deep_dive": self.deep_dive, "nudges": sorted(self.nudges),
                "max_tool_calls": self.max_tool_calls, "max_usd": self.max_usd, "max_seconds": self.max_seconds,
                "saturation_dry_steps": self.saturation_dry_steps, "prune_steps": self.prune_steps, "lead_model": self.lead_model,
                "judge_model": self.judge_model}
