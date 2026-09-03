"""Evidence graph, the Atlas-style attribution graph the report is a view over. The target is
the ground-truth root; each candidate is a node off the root (the resolved one is the person,
the rest are rejected same-name others with the reason on the edge); each finding is a node off
the resolved person with its confidence and the method on the edge; synthesis inferences are
their own nodes. Every finding node keeps its source_url, so a reader can walk root -> person ->
finding -> source. Pure function, no I/O, unit-testable."""
from __future__ import annotations

import re
from typing import Any

from .resolution import Anchor, Candidate, Resolution

STATUS_RANK = {"unresolved": 0, "ambiguous": 1, "resolved": 2}


def _slug(text: str, n: int = 30) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:n] or "x"


def build_graph(
    anchor: Anchor,
    resolution: Resolution,
    candidates: list[Candidate],
    findings: list[dict[str, Any]],
    synthesis: list[dict[str, Any]] | None = None,
    same_person_ids: set[str] | None = None,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    same = set(same_person_ids or ([resolution.best_candidate_id] if resolution.best_candidate_id else []))

    root = "input.target"
    nodes.append({"id": root, "type": "ground_truth", "kind": "target", "value": anchor.raw,
                  "field": None, "confidence": 100})

    by_id = {c.id: c for c in candidates}
    for b in resolution.breakdowns:
        c = by_id.get(b.candidate_id)
        if c is None:
            continue
        resolved = c.id in same
        cid = f"candidate.{c.id}"
        nodes.append({"id": cid, "type": "candidate",
                      "kind": "person" if resolved else "same_name_other",
                      "value": c.label, "field": None, "confidence": round(b.score * 100)})
        if resolved:
            label = f"resolved: markers {b.matched_markers}"
        elif b.contradictions:
            label = "rejected: " + "; ".join(b.contradictions)
        elif b.reason:
            label = f"rejected: {b.reason}"
        else:
            label = "rejected: lower score"
        edges.append({"from": root, "to": cid, "confidence": round(b.score * 100), "label": label})

    person = f"candidate.{resolution.best_candidate_id}" if (
        resolution.best_candidate_id and resolution.status != "unresolved") else root

    field_to_node: dict[str, str] = {}
    for i, f in enumerate(findings):
        conf = round(float(f.get("confidence") or 0) * 100)
        fid = f.get("id") or f"found.{_slug(f.get('category') or 'fact')}_{_slug(f.get('field') or str(i + 1), 20)}"
        if any(n["id"] == fid for n in nodes):
            fid = f"{fid}_{i + 1}"
        if f.get("field"):
            field_to_node[f["field"]] = fid
        nodes.append({"id": fid, "type": "finding", "kind": f.get("category"), "value": f.get("value"),
                      "field": f.get("field"), "confidence": conf, "sensitive": bool(f.get("sensitive"))})
        edges.append({"from": person, "to": fid, "confidence": conf,
                      "label": f.get("method") or "", "source_url": f.get("source_url")})

    for j, s in enumerate(synthesis or []):
        sid = f"synthesis.{j + 1}"
        nodes.append({"id": sid, "type": "inference", "kind": "synthesis", "value": s.get("claim"),
                      "field": None, "confidence": round(float(s.get("confidence") or 0) * 100),
                      "based_on": s.get("based_on") or []})
        edges.append({"from": person, "to": sid, "confidence": round(float(s.get("confidence") or 0) * 100),
                      "label": "inference"})
        for basis in s.get("based_on") or []:
            tgt = field_to_node.get(basis)
            if not tgt:
                key = basis.split(":", 1)[-1].strip().lower()
                tgt = next((fid for fld, fid in field_to_node.items() if key and key in fld.lower()), None)
            if tgt:
                edges.append({"from": sid, "to": tgt, "confidence": None, "label": "based on"})

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "findings": sum(1 for n in nodes if n["type"] == "finding"),
            "candidates": sum(1 for n in nodes if n["type"] == "candidate"),
            "rejected": sum(1 for n in nodes if n.get("kind") == "same_name_other"),
            "inferences": sum(1 for n in nodes if n["type"] == "inference"),
        },
    }
