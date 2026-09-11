"""FIDO pipeline — implements the diagram, with the three omissions restored:

  push -> S1 extract -> S2 predict (Tier A [+ Tier B if uncertain]) ->
  S3 plan (constraint probe + allocation; floors/caps/ledger) ->
  S4 execute arms (P4: probe-then-reallocate) ->
  S5 triage (normalize/attribute/dedup/intent) ->
  S6 report -> S7 learn (yield update + autolabel candidates)
"""
from __future__ import annotations

import json
import os
import time

from fido.change.extractor import extract
from fido.predict.classifier import load_model, LLMJudge
from fido.plan import planner
from fido.exec import builds, rts, fuzz, gen, concolic, diffbuild
from fido.triage.triage import triage
from fido.report.report import render
from fido.learn.loop import YieldModel, append_run_record, autolabel_candidates
from fido.ledger import Ledger


def _log(msg: str):
    print(f"[fido] {msg}", flush=True)


def run(repo: str, commit: str, budget_s: float = 900.0, policy: str = "p4",
        out_dir: str = None, quiet: bool = False) -> dict:
    import subprocess as _sp
    commit = _sp.run(["git", "-C", repo, "rev-parse", commit],
                     capture_output=True, text=True, check=True).stdout.strip()
    out_dir = out_dir or os.path.join("runs", commit[:8])
    os.makedirs(out_dir, exist_ok=True)
    cache_dir = os.path.join(out_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    ledger = Ledger(budget_s=budget_s)
    ledger.start()
    t_wall0 = time.time()

    # ---- S1 -------------------------------------------------------------
    _log("S1 extracting change ...")
    cr = extract(repo, commit)
    if not quiet:
        for e in cr.entities:
            _log(f"  entity {e.file}::{e.name} ops={[o for o, _ in e.ast_ops]} risk={e.risk}")

    # ---- S2 -------------------------------------------------------------
    _log("S2 predicting failure modes ...")
    model = load_model()
    preds = model.predict(cr)
    probs = dict(preds["commit_probs"])
    _log(f"  probs={probs} confidence={preds['confidence']}")
    llm = LLMJudge(ledger)
    if preds["confidence"] == "low" and llm.available():
        _log("  low margin -> Tier-B LLM judge")
        jb = llm.judge(cr, preds, "low margin")
        if jb and "commit_probs" in jb:
            probs = jb["commit_probs"]
            preds["tier"] += "+B"

    # ---- capability probe (constraint propagation) -----------------------
    san_capable = builds.probe_sanitizers()
    unavailable = {k: not v for k, v in san_capable.items() if not v}
    env = {"unavailable": {k: True for k in unavailable},
           "concolic_cmd": os.environ.get("FIDO_CONCOLIC_CMD"),
           "msan_threshold": os.environ.get("FIDO_MSAN_THRESHOLD", 0.45)}
    _log(f"  sanitizer capability: {san_capable}")

    # ---- S3 -------------------------------------------------------------
    _log("S3 planning ...")
    arms = planner.available_arms(env)
    san_plan = planner.sanitizer_plan(probs, env)
    yield_model = YieldModel(os.path.join("runs", "yield_model.json"))
    alpha = {a: yield_model.get(a) for a in ("rts", "fuzz", "gen", "diff", "concolic")}
    alloc = planner.allocate(budget_s, probs, arms, policy=policy, alpha=alpha)
    plan = planner.plan_to_json(cr.commit[:12], probs, san_plan, arms, alloc, policy, budget_s)
    _log(f"  allocation={alloc}")

    # ---- S4 (P4: probe-then-reallocate) ----------------------------------
    attribution = preds.get("entity_attribution", [])
    arm_results, raw_findings = [], []
    order = [a for a in ("rts", "fuzz", "gen", "diff", "concolic") if a in alloc and alloc[a] > 0]
    phase1 = order[:2] if policy == "p4" else order
    phase2 = [a for a in order if a not in phase1]
    spent_track = {a: 0.0 for a in order}

    def run_arm(name, budget):
        if budget < 5 and name != "concolic":
            return None
        _log(f"S4 executing arm {name} (budget {budget:.0f}s) ...")
        if name == "rts":
            r = rts.execute(cr, budget, cache_dir, ledger, probs, san_capable)
        elif name == "fuzz":
            r = fuzz.execute(cr, budget, cache_dir, ledger, probs, attribution, seed=0)
        elif name == "gen":
            r = gen.execute(cr, budget, cache_dir, ledger, probs, attribution)
        elif name == "diff":
            r = diffbuild.execute(cr, budget, cache_dir, ledger, probs)
        elif name == "concolic":
            r = concolic.execute(cr, budget, cache_dir, ledger, probs)
        else:
            return None
        arm_results.append(r)
        raw_findings.extend(r.get("findings", []))
        ledger.debit(name, "exec", r.get("exec_s", 0.0), "arm execution")
        spent_track[name] = spent_track.get(name, 0.0) + r.get("exec_s", 0.0)
        n_attr = sum(1 for f in r.get("findings", []))
        yield_model.update(name, r.get("exec_s", 0.0), n_attr)
        _log(f"  {name}: status={r.get('status')} findings={len(r.get('findings', []))} "
             f"exec={r.get('exec_s', 0)}s")
        return r

    for name in phase1:
        run_arm(name, alloc[name])
    if policy == "p4" and phase2:
        remaining = budget_s - ledger.spent
        alpha2 = {a: yield_model.get(a) for a in order}
        alloc2 = planner.allocate(max(remaining, 0), probs, arms, policy="p2", alpha=alpha2)
        _log(f"  P4 reallocation after probes: {alloc2}")
        for name in phase2:
            run_arm(name, min(alloc2.get(name, 0), max(budget_s - ledger.spent, 0)))

    # ---- S5 -------------------------------------------------------------
    _log("S5 triaging ...")
    findings = triage(raw_findings, cr)
    for f in findings:
        f["commit"] = cr.commit[:12]

    # ---- S6 -------------------------------------------------------------
    record = {
        "commit": cr.commit, "parent": cr.parent, "policy": policy,
        "predictions": preds, "plan": plan,
        "ledger": {"budget_s": ledger.budget_s, "spent": ledger.spent,
                   "by_arm": ledger.by_arm()},
        "arm_results": arm_results, "findings": findings,
        "wall_s": round(time.time() - t_wall0, 2),
        "change": cr.to_dict(),
    }
    with open(os.path.join(out_dir, "run_record.json"), "w") as f:
        json.dump(record, f, indent=2, default=str)
    md = render(record)
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write(md)

    # ---- S7 -------------------------------------------------------------
    yield_model.save()
    append_run_record("runs", {"commit": cr.commit[:12], "policy": policy,
                               "spent": ledger.spent, "n_findings": len(findings),
                               "classes": [f["class"] for f in findings],
                               "attributed_high": sum(1 for f in findings
                                                      if f["attribution"]["level"] == "high")})
    autolabel_candidates(findings)  # writes nothing in MVP; contract documented

    if not quiet:
        print()
        print(md)
    return record
