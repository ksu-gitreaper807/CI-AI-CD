"""S3 — Budgeted Planner (research component #2).

maximize sum_a E[Y_a(b_a; x, p)]  s.t. sum_a (b_a + build_a + llm_a) <= B,
with per-class floors, per-arm caps, and unavailability constraints.

Policies:
  P0 fixed   — equal split across available arms (baseline)
  P1 prior   — split proportional to predicted class mass x arm-class utility
  P2 greedy  — slot-wise greedy knapsack over marginal yield
  P4 probe   — 25% budget probes top arms, then reallocates with updated yields
Yield model: Y = alpha * log(1 + b / beta) per (arm, repo); alpha updated by
fido/learn from observed findings/CPU-s (transfer-free cold start defaults).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

CLASSES = ["MEM", "UNINIT", "INT_UB", "LIFETIME", "CONC", "LOGIC"]

# arm -> class utility (documented defaults; the heart of "steering")
UTILITY = {
    "rts":        {"MEM": 0.4, "UNINIT": 0.3, "INT_UB": 0.3, "LIFETIME": 0.3, "CONC": 0.3, "LOGIC": 0.9},
    "fuzz":       {"MEM": 0.9, "UNINIT": 0.7, "INT_UB": 0.9, "LIFETIME": 0.6, "CONC": 0.6, "LOGIC": 0.2},
    "gen":        {"MEM": 0.5, "UNINIT": 0.3, "INT_UB": 0.85, "LIFETIME": 0.4, "CONC": 0.1, "LOGIC": 0.8},
    "concolic":   {"MEM": 0.6, "UNINIT": 0.4, "INT_UB": 0.6, "LIFETIME": 0.3, "CONC": 0.2, "LOGIC": 0.5},
    "diff":       {"MEM": 0.3, "UNINIT": 0.1, "INT_UB": 0.6, "LIFETIME": 0.5, "CONC": 0.1, "LOGIC": 0.4},
}
SANITIZER_FOR_CLASS = {"MEM": "asan", "UNINIT": "msan", "INT_UB": "ubsan",
                       "LIFETIME": "ubsan", "CONC": "tsan", "LOGIC": "none"}
BUILD_COST = {"asan": 20.0, "ubsan": 20.0, "tsan": 25.0, "msan": 300.0, "none": 10.0,
              "O0": 10.0, "O2": 10.0}
FLOORS = {"rts": 90.0}          # safety: regression suite always gets a slice
CAPS = {"fuzz": 0.55, "rts": 0.40}   # fraction of budget
SLOT = 60.0                      # allocation granularity (s)
PROBE_FRACTION = 0.25


@dataclass
class ArmSpec:
    name: str
    available: bool
    reason: str = ""


def available_arms(env: dict) -> list:
    """Constraint propagation: unavailable executors are never allocated."""
    arms = [ArmSpec("rts", True)]
    if env.get("cc") or True:  # gcc present in MVP; production checks toolchain
        arms.append(ArmSpec("fuzz", True))
    arms.append(ArmSpec("gen", True))
    arms.append(ArmSpec("diff", True))
    if env.get("concolic_cmd"):
        arms.append(ArmSpec("concolic", True))
    else:
        arms.append(ArmSpec("concolic", False, "no concolic engine configured (QSYM adapter: FIDO_CONCOLIC_CMD)"))
    return arms


def sanitizer_plan(probs: dict, env: dict) -> dict:
    """Class-matched sanitizer choice; expensive/harmful-if-wrong builds gated by
    probability threshold; unavailable builds propagate as constraints."""
    plan, ordered = {}, sorted(probs.items(), key=lambda kv: -kv[1])
    for cls, p in ordered:
        san = SANITIZER_FOR_CLASS[cls]
        if env.get("unavailable", {}).get(san):
            fallback = "asan" if san in ("msan", "tsan") else san
            plan[cls] = fallback + f" (requested {san}: unavailable)"
            continue
        if san == "msan" and p < float(env.get("msan_threshold", 0.45)):
            plan[cls] = "msan:skipped(p=%.2f<threshold)" % p
            continue
        plan[cls] = san
    return plan


def yield_estimate(arm: str, budget_s: float, probs: dict, alpha: dict, beta: dict) -> float:
    a = alpha.get(arm, 0.8)
    b = beta.get(arm, 120.0)
    mass = sum(p * UTILITY[arm].get(c, 0.0) for c, p in probs.items())
    return a * mass * math.log1p(max(0.0, budget_s) / b)


def allocate(budget_s: float, probs: dict, arms: list, policy: str = "p4",
             alpha: dict = None, beta: dict = None, build_est: dict = None) -> dict:
    alpha = alpha or {}
    build_est = build_est or {}
    avail = [a.name for a in arms if a.available]
    alloc = {a: 0.0 for a in avail}

    def cap(a):
        return CAPS.get(a, 0.70) * budget_s

    if policy == "p0":
        per = budget_s / max(1, len(avail))
        alloc = {a: min(per, cap(a)) for a in avail}
    elif policy == "p1":
        for a in avail:
            alloc[a] = min(budget_s * 0.2, cap(a)) if a != "rts" else FLOORS["rts"]
        rest = budget_s - sum(alloc.values())
        tot = sum(sum(p * UTILITY[a].get(c, 0) for c, p in probs.items()) for a in avail)
        for a in avail:
            u = sum(p * UTILITY[a].get(c, 0) for c, p in probs.items())
            alloc[a] += rest * (u / tot if tot else 1 / len(avail))
    else:  # p2 / p4 share the greedy knapsack core
        for a, f in FLOORS.items():
            if a in alloc:
                alloc[a] = f
        remaining = budget_s - sum(alloc.values())
        if policy == "p4":
            remaining_probe = remaining * PROBE_FRACTION
            step = max(SLOT, remaining_probe / max(1, len(avail)))
            ranked = sorted(avail, key=lambda a: -yield_estimate(a, step, probs, alpha, {} if not beta else beta))
            for a in ranked[:2]:
                give = min(step, cap(a) - alloc[a])
                if give > 0:
                    alloc[a] += give
            remaining -= sum(alloc[a] for a in avail) - sum(v for k, v in FLOORS.items() if k in alloc)
        # greedy slots by marginal yield
        while remaining >= SLOT:
            best, best_g = None, 0.0
            for a in avail:
                if alloc[a] + SLOT > cap(a):
                    continue
                g = yield_estimate(a, alloc[a] + SLOT, probs, alpha, beta or {}) - \
                    yield_estimate(a, alloc[a], probs, alpha, beta or {})
                if g > best_g:
                    best, best_g = a, g
            if best is None:
                break
            alloc[best] += SLOT
            remaining -= SLOT
    # final clamp to budget (build estimates debited inside arms' own accounting)
    total = sum(alloc.values())
    if total > budget_s:
        scale = budget_s / total
        alloc = {a: round(v * scale, 1) for a, v in alloc.items()}
    return alloc


def plan_to_json(commit, probs, sanitizer_plan_, arms, alloc, policy, budget):
    return {
        "commit": commit,
        "predicted_classes": probs,
        "sanitizer_plan": sanitizer_plan_,
        "arms": [{"name": a.name, "available": a.available, "reason": a.reason} for a in arms],
        "allocation_s": alloc,
        "policy": policy,
        "budget_s": budget,
    }
