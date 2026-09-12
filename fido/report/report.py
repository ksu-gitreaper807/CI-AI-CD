"""S6 — Per-commit CI report (markdown + JSON)."""
from __future__ import annotations


def render(record: dict) -> str:
    p = record["predictions"]
    record_deep_guard = record.get("deep_guard")
    plan = record["plan"]
    led = record["ledger"]
    fs = record["findings"]
    lines = []
    a = lines.append
    a(f"# FIDO CI report — commit `{record['commit'][:10]}`")
    a("")
    a(f"**Predicted classes:** " +
      " | ".join(f"{c} {v:.2f}" for c, v in list(p["commit_probs"].items())[:4]) +
      f"  (tier {p['tier']}, confidence {p['confidence']})")
    a("")
    a("**Sanitizer plan:** " + ", ".join(f"{c}→{s}" for c, s in plan["sanitizer_plan"].items()))
    a("")
    a("**Plan (policy %s):** " % plan["policy"] +
      " · ".join(f"{arm} {s}s" for arm, s in plan["allocation_s"].items()))
    skipped = [x for x in plan["arms"] if not x["available"]]
    if skipped:
        a("")
        a("**Unavailable arms (constraint-propagated):** " +
          "; ".join(f"{x['name']} ({x['reason']})" for x in skipped))
    dg = record_deep_guard
    if dg and dg.get("triggered"):
        a("")
        a("**Deep-guard trigger fired** (hard input guards in changed code): "
          + "; ".join(dg.get("evidence", [])[:3]) +
          " — mutation fuzzing is unlikely to reach these; a concolic engine is required.")
    a("")
    a(f"**Spent:** {led['spent']}/{led['budget_s']}s — " +
      " · ".join(f"{k} {v}s" for k, v in sorted(led["by_arm"].items())))
    a("")
    if not fs:
        a("**Findings:** none (change-attributed) at this budget.")
    else:
        a(f"**Findings:** {len(fs)}")
        for f in fs:
            a("")
            a(f"### {f['id']} — {f['class']} (severity {f['severity']}) "
              f"@ {f['attribution']['entity']}:{f['attribution']['line']}")
            a(f"- attribution: **{f['attribution']['level']}** · intent: {f['intent']} · arm: {f['arm']} ({f['kind']})")
            ev = (f.get("evidence") or "").strip().splitlines()
            a("- evidence: `" + (ev[0][:120] if ev else "n/a") + "`")
            if f.get("input"):
                a(f"- triggering input: `{str(f['input'])[:120]}`")
    a("")
    a("---")
    a(f"*arms skipped at runtime:* " + "; ".join(
        f"{r['arm']} ({r.get('reason', 'n/a')})" for r in record["arm_results"]
        if r.get("status") in ("skipped", "adapter-not-implemented")) or "*none*")
    return "\n".join(lines)
