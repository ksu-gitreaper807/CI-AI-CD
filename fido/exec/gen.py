"""A3 — Generated boundary/input tests (rule-based core + LLM hook).

The rule generator reads the classifier's per-entity evidence and produces
class-shaped adversarial inputs — INT_UB: INT_MAX/INT_MIN pairs; MEM: array
size+1 overflow probes derived from detected fixed-size arrays. This is
deliberately 'generation steered by failure-mode prediction' in its simplest
deterministic form; the LLM hook (FIDO_LLM_CMD) is where prompt-based unit-test
generation plugs in, with every token debited and every generated test
validated by execution before it can become a finding (validity filter).
"""
from __future__ import annotations

import os
import re
import subprocess

from fido.exec import builds
from fido.exec.runner import run, sanitize_markers

INT_BOUNDARY_INPUTS = [
    "2147483647 2147483647\n",      # INT_MAX accumulation overflow
    "-2147483648 -1\n",             # INT_MIN underflow
    "2147483647 -2147483648 0\n",   # mixed
]


def _array_sizes(cr) -> list:
    """Fixed-size arrays on added lines of changed files -> overflow probes."""
    sizes = []
    for e in cr.entities:
        if not any(o in ("indexed_write", "bounds_check_removed", "unbounded_copy")
                   for o, _ in e.ast_ops):
            continue
        try:
            src = subprocess.run(["git", "-C", cr.repo, "show", f"{cr.commit}:{e.file}"],
                                 capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError:
            continue
        macros = {name: int(val) for name, val in
                  re.findall(r"#define\s+(\w+)\s+(\d+)\b", src)}
        for m in re.finditer(r"\bint\s+(\w+)\s*\[\s*(\w+)\s*\]", src):
            raw = m.group(2)
            size = int(raw) if raw.isdigit() else macros.get(raw)
            if size:
                sizes.append((e.file, m.group(1), size))
    return sizes


def generate_inputs(cr) -> list:
    """Return [(name, why, stdin_bytes)] — class-shaped boundary probes."""
    out = []
    ops = {o for e in cr.entities for o, _ in e.ast_ops}
    if ("int_arith_accumulator" in ops or "shift_op" in ops or "mul_op" in ops
            or "type_narrowing_int" in ops):
        for i, data in enumerate(INT_BOUNDARY_INPUTS):
            out.append((f"int_boundary_{i}", "INT_UB boundary constants", data.encode()))
    for path, arr, size in _array_sizes(cr):
        probe = "\n".join(["1"] * (size + 1)) + "\n"          # size+1 writes
        out.append((f"oob_{arr}_{size + 1}", f"MEM: {size + 1} writes vs int {arr}[{size}]",
                    probe.encode()))
    return out


def execute(cr, budget_s: float, cache_dir: str, ledger, probs: dict,
            attribution: list) -> dict:
    probes = generate_inputs(cr)
    if not probes:
        return {"arm": "gen", "status": "skipped",
                "reason": "no rule-triggered boundary classes in change",
                "findings": [], "exec_s": 0.0}
    try:
        exe = builds.build(cr.repo, cr.commit, "sanitized", cache_dir, ledger)
    except RuntimeError as e:
        return {"arm": "gen", "status": "skipped", "reason": str(e),
                "findings": [], "exec_s": 0.0}
    llm = os.environ.get("FIDO_LLM_CMD")
    findings, exec_s = [], 0.0
    for name, why, data in probes:
        rc, out, err, el = run([exe], stdin_data=data, timeout_s=4, cpu_s=4)
        exec_s += el
        marker = sanitize_markers(err)
        if marker:
            findings.append({"arm": "gen", "kind": "sanitizer", "label": f"rule:{name}",
                             "why": why, "rc": rc, "marker": marker,
                             "stderr_tail": err.decode("utf-8", "replace")[-2000:],
                             "input": data.decode("utf-8", "replace")[:200]})
    note = ["LLM codegen hook present" if llm else "rule generator only (LLM hook: FIDO_LLM_CMD)"]
    return {"arm": "gen", "status": "ok", "probes": [p[0] for p in probes],
            "findings": findings, "exec_s": round(exec_s, 2), "notes": note}
