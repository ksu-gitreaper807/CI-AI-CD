"""A5 — Differential/metamorphic arm: O0 vs O2 build replay.

Replays existing corpus inputs (regression inputs) against two optimization
levels and compares observable behavior. Motivated by sanitizer-eliding
optimizations (Don't Look UB, PLDI'23): UB can change observable behavior
across -O levels while each individual build may or may not trap. Zero new
input-generation cost — reuses inputs the project already has.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

from fido.exec import builds
from fido.exec.runner import run, sanitize_markers


def _corpus(cr) -> list:
    out = subprocess.run(["git", "-C", cr.repo, "ls-tree", "-r", "--name-only", cr.commit],
                         capture_output=True, text=True, check=True).stdout
    data = []
    for p in out.splitlines():
        if p.startswith("tests/inputs/"):
            blob = subprocess.run(["git", "-C", cr.repo, "show", f"{cr.commit}:{p}"],
                                  capture_output=True, check=True).stdout
            data.append((p, blob))
    return data


def execute(cr, budget_s: float, cache_dir: str, ledger, probs: dict) -> dict:
    corpus = _corpus(cr)
    if not corpus:
        return {"arm": "diff", "status": "skipped", "reason": "no corpus inputs to replay",
                "findings": [], "exec_s": 0.0}
    try:
        o0 = builds.build(cr.repo, cr.commit, "O0", cache_dir, ledger)
        o2 = builds.build(cr.repo, cr.commit, "O2", cache_dir, ledger)
    except RuntimeError as e:
        return {"arm": "diff", "status": "skipped", "reason": str(e),
                "findings": [], "exec_s": 0.0}
    findings, exec_s = [], 0.0
    for name, data in corpus:
        rc0, out0, err0, el = run([o0], stdin_data=data, timeout_s=4, cpu_s=4)
        rc2, out2, err2, el2 = run([o2], stdin_data=data, timeout_s=4, cpu_s=4)
        exec_s += el + el2
        if (out0, rc0) != (out2, rc2):
            findings.append({
                "arm": "diff", "kind": "diff_violation", "input_ref": name,
                "o0": {"rc": rc0, "sha": hashlib.sha1(out0).hexdigest()[:12],
                       "san": sanitize_markers(err0) is not None},
                "o2": {"rc": rc2, "sha": hashlib.sha1(out2).hexdigest()[:12],
                       "san": sanitize_markers(err2) is not None},
                "class_hint": "optimizer-sensitive UB"})
    return {"arm": "diff", "status": "ok", "replayed": len(corpus),
            "findings": findings, "exec_s": round(exec_s, 2)}
