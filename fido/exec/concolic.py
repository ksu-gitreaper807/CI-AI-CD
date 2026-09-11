"""A4 — Selective concolic (trigger-gated, never scheduled by default).

Trigger: deep-guard evidence in ADDED lines — magic constants / multi-char
literal comparisons / checksum-like patterns. Rationale (QSYM, F3): concolic
overhead (10^3-10^5x) forbids always-on; it is allocated only when predicted
logic guards are input-hard for mutation. Adapter: FIDO_CONCOLIC_CMD.
"""
from __future__ import annotations

import os
import re

DEEP_GUARD = [
    re.compile(r"\b0x[0-9a-fA-F]{6,}\b"),          # magic constants
    re.compile(r"==\s*'[^']{2,4}'"),               # multi-char literal compares
    re.compile(r"\b(crc|checksum|md5|sha)\w*\s*\(", re.I),
]


def triggered(cr) -> tuple:
    evidence = []
    for e in cr.entities:
        for _, text in e.added_lines:
            for rx in DEEP_GUARD:
                if rx.search(text):
                    evidence.append((e.file, text.strip()[:80]))
    return (bool(evidence), evidence)


def execute(cr, budget_s: float, cache_dir: str, ledger, probs: dict) -> dict:
    hit, evidence = triggered(cr)
    if not hit:
        return {"arm": "concolic", "status": "skipped",
                "reason": "no deep-guard evidence (trigger-gated by design)",
                "findings": [], "exec_s": 0.0}
    cmd = os.environ.get("FIDO_CONCOLIC_CMD")
    if not cmd:
        return {"arm": "concolic", "status": "skipped",
                "reason": f"deep guards found {evidence[:2]} but no engine configured (FIDO_CONCOLIC_CMD)",
                "findings": [], "exec_s": 0.0}
    # Production: shell out to QSYM-class engine on the changed TU with the
    # triggered constants as solve targets. MVP: adapter stub, honest about it.
    return {"arm": "concolic", "status": "adapter-not-implemented",
            "reason": "engine adapter pending; trigger fired", "evidence": evidence[:5],
            "findings": [], "exec_s": 0.0}
