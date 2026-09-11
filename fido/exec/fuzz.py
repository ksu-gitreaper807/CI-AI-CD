"""A2 — Change-directed fuzzing arm.

MVP fuzzer: integer-stream grammar (structure-aware for the demo target class)
biased toward boundary/extreme values and overlong sequences, executed against
the ASan+UBSan build. Targeting: the arm consumes the classifier's
entity_attribution to prioritize inputs exercising changed functions (MVP
targeting is input-shape bias; AFLGo/WAFLGO adapter provides real
distance-guided targeting — see adapter below).

AFLGo adapter: if FIDO_AFLGO_CMD is set, the arm shells out to it instead
(args: <binary> <corpus_dir> <budget_s>); its crashes are ingested as findings.
"""
from __future__ import annotations

import os
import random
import time

from fido.exec import builds
from fido.exec.runner import run, sanitize_markers

EXTREMES = [2147483647, -2147483648, 0, 1, -1, 100, 1000000]


class MiniFuzzer:
    """Integer-stream input generator: demo-grade but genuinely executing.
    Production replaces this with AFLGo/WAFLGO/AFL++ via the adapter below."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def input_bytes(self) -> bytes:
        r = self.rng.random()
        if r < 0.35:  # short extreme sequence (signed-overflow hunter)
            n = self.rng.randint(1, 4)
            vals = [self.rng.choice(EXTREMES) for _ in range(n)]
        elif r < 0.70:  # overlong sequence (buffer-overflow hunter)
            n = self.rng.randint(50, 220)
            vals = [self.rng.randint(0, 9) for _ in range(n)]
            if self.rng.random() < 0.5:
                vals[self.rng.randrange(len(vals))] = self.rng.choice(EXTREMES)
        else:  # benign-ish
            n = self.rng.randint(1, 20)
            vals = [self.rng.randint(-100, 100) for _ in range(n)]
        return ("\n".join(map(str, vals)) + "\n").encode()


def execute(cr, budget_s: float, cache_dir: str, ledger, probs: dict,
            attribution: list, seed: int = 0) -> dict:
    aflgo = os.environ.get("FIDO_AFLGO_CMD")
    t_end = time.time() + budget_s
    try:
        exe = builds.build(cr.repo, cr.commit, "sanitized", cache_dir, ledger)
    except RuntimeError as e:
        return {"arm": "fuzz", "status": "skipped", "reason": str(e),
                "findings": [], "exec_s": 0.0}
    target_note = f"targets={[_a['entity'] for _a in attribution[:3]]}"
    findings, exec_s, n_inputs, corpus_hits = [], 0.0, 0, 0
    fz = MiniFuzzer(seed=seed)

    if aflgo:
        t0 = time.time()
        corpus_dir = os.path.join(cache_dir, "corpus")
        os.makedirs(corpus_dir, exist_ok=True)
        r = run([aflgo, exe, corpus_dir, str(int(budget_s))],
                timeout_s=budget_s + 30, cpu_s=budget_s + 10)
        exec_s += time.time() - t0
        err = r[2].decode("utf-8", "replace")
        if sanitize_markers(r[2]):
            findings.append({"arm": "fuzz", "kind": "sanitizer", "label": "aflgo",
                             "rc": r[0], "stderr_tail": err[-2000:], "input_ref": corpus_dir})
        return {"arm": "fuzz", "status": "ok", "engine": "aflgo-adapter",
                "findings": findings, "exec_s": round(exec_s, 2), "notes": [target_note]}

    max_inputs = int(os.environ.get("FIDO_FUZZ_MAX_INPUTS", "250"))
    while time.time() < t_end and len(findings) < 3 and n_inputs < max_inputs:
        data = fz.input_bytes()
        t0 = time.time()
        rc, out, err, el = run([exe], stdin_data=data, timeout_s=3.0, cpu_s=3.0)
        exec_s += time.time() - t0
        n_inputs += 1
        marker = sanitize_markers(err)
        if marker or rc not in (0,):
            findings.append({"arm": "fuzz", "kind": "sanitizer" if marker else "crash",
                             "label": "minifuzz", "rc": rc, "marker": marker or "nonzero-exit",
                             "stderr_tail": err.decode("utf-8", "replace")[-2000:],
                             "input": data.decode("utf-8", "replace")[:400],
                             "n_execs": n_inputs})
    return {"arm": "fuzz", "status": "ok", "engine": "minifuzz", "execs": n_inputs,
            "findings": findings, "exec_s": round(exec_s, 2), "notes": [target_note]}
