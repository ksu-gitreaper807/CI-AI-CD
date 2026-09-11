"""E — Budget-fair historical replay: run the pipeline across a repo's commits.

This is the experiment engine: every commit is a replayed 'push' with a fixed
budget; the summary table is the raw material for defect-discovery-per-compute.
"""
from __future__ import annotations

import argparse
import json
import subprocess

from fido.pipeline import run as run_pipeline


def commits(repo: str, limit: int) -> list:
    out = subprocess.run(["git", "-C", repo, "rev-list", "--reverse", f"HEAD~{limit}..HEAD"
                          if limit else "HEAD"], capture_output=True, text=True, check=True)
    return [c for c in out.stdout.split() if c]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--budget", type=float, default=240.0)
    ap.add_argument("--policy", default="p4")
    ap.add_argument("--limit", type=int, default=0, help="only last N commits")
    args = ap.parse_args()

    cs = commits(args.repo, args.limit)
    rows = []
    for c in cs:
        has_parent = subprocess.run(["git", "-C", args.repo, "rev-parse", f"{c}^"],
                                    capture_output=True).returncode == 0
        if not has_parent:
            continue
        subj = subprocess.run(["git", "-C", args.repo, "log", "-1", "--format=%s", c],
                              capture_output=True, text=True).stdout.strip()
        try:
            rec = run_pipeline(args.repo, c, budget_s=args.budget, policy=args.policy,
                               out_dir=f"runs/replay_{c[:8]}", quiet=True)
            rows.append({
                "commit": c[:10], "subject": subj[:44],
                "top_class": next(iter(rec["predictions"]["commit_probs"])),
                "findings": [f["class"] for f in rec["findings"]],
                "attributed_high": sum(1 for f in rec["findings"]
                                       if f["attribution"]["level"] == "high"),
                "spent_s": rec["ledger"]["spent"],
            })
        except Exception as e:
            rows.append({"commit": c[:10], "subject": subj[:44],
                         "error": str(e)[:120]})
    print("\n## Replay summary\n")
    print("| commit | subject | top class | findings | attributed(high) | spent |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        if "error" in r:
            print(f"| {r['commit']} | {r['subject']} | ERROR: {r['error']} | | | |")
        else:
            print(f"| {r['commit']} | {r['subject']} | {r['top_class']} | "
                  f"{','.join(r['findings']) or '-'} | {r['attributed_high']} | "
                  f"{r['spent_s']}s |")
    with open("runs/replay_summary.json", "w") as f:
        json.dump(rows, f, indent=2)


if __name__ == "__main__":
    main()
