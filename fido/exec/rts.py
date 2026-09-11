"""A1 — Regression arm: RTS selection + (class-conditioned) sanitizer hardening.

Selection mirrors Ekstazi-style dependency selection using the project's
coverage map (test -> files touched). If no map exists, degrade to all tests.
Hardening: when the classifier gives MEM/INT_UB real probability mass, the
selected regression tests are ALSO run on the sanitizer build — running
existing tests under sanitizers is a cheap class-conditioned upgrade (it is
how 'selection-only' pipelines start catching UB without new tests).
"""
from __future__ import annotations

import json
import os

from fido.exec import builds
from fido.exec.runner import run, sanitize_markers


def _manifest(repo: str, commit: str) -> list:
    out = _git_show(repo, commit, "tests/manifest.json")
    return json.loads(out) if out else []


def _git_show(repo, commit, path):
    import subprocess
    r = subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _inputs(repo: str, commit: str, rel: str) -> bytes:
    data = _git_show(repo, commit, rel)
    return data.encode() if data else b""


def select_tests(cr, manifest: list) -> list:
    changed = set(cr.touched_files)
    cov = cr.coverage_map or {}
    selected = []
    for t in manifest:
        files = set(cov.get(t["name"], []))
        if not files or (files & changed):
            selected.append(t)
    return selected


def execute(cr, budget_s: float, cache_dir: str, ledger, probs: dict, san_capable: dict) -> dict:
    manifest = _manifest(cr.repo, cr.commit)
    if not manifest:
        return {"arm": "rts", "status": "skipped", "reason": "no tests/manifest.json",
                "findings": [], "exec_s": 0.0}
    selected = select_tests(cr, manifest)
    plain = builds.build(cr.repo, cr.commit, "plain", cache_dir, ledger)
    hardened = (probs.get("MEM", 0) + probs.get("INT_UB", 0)) > 0.30 and san_capable.get("asan")
    findings, notes, exec_s = [], [], 0.0

    def run_suite(exe: str, label: str):
        nonlocal exec_s
        for t in selected:
            stdin = _inputs(cr.repo, cr.commit, t.get("stdin", "")) if t.get("stdin") else b""
            rc, out, err, el = run([exe], stdin_data=stdin, timeout_s=5, cpu_s=5)
            exec_s += el
            marker = sanitize_markers(err)
            ok = (rc == 0) and (marker is None)
            if t.get("expect_regex"):
                import re
                ok = ok and re.search(t["expect_regex"], out.decode("utf-8", "replace"))
            if not ok:
                findings.append({"arm": "rts", "kind": "sanitizer" if marker else "test_fail",
                                 "label": label, "test": t["name"], "rc": rc,
                                 "stderr_tail": err.decode("utf-8", "replace")[-1500:],
                                 "stdout": out.decode("utf-8", "replace")[-500:]})

    run_suite(plain, "plain")
    if hardened:
        san = builds.build(cr.repo, cr.commit, "sanitized", cache_dir, ledger)
        run_suite(san, "sanitized")
        notes.append("hardened rerun: MEM+INT_UB mass %.2f" %
                     (probs.get("MEM", 0) + probs.get("INT_UB", 0)))
    return {"arm": "rts", "status": "ok",
            "selected": [t["name"] for t in selected], "total": len(manifest),
            "hardened_rerun": hardened, "notes": notes,
            "findings": findings, "exec_s": round(exec_s, 3)}
