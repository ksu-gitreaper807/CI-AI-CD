"""S7 — Learning loop: yield-model update + auto-labeling hooks.

Every run appends a run record (JSONL). The yield model keeps EWMA estimates
of findings/CPU-hour per arm (alpha); the next allocation consumes them. This
closes the loop the user's diagram was missing — without it 'adaptive' is a
label, not a mechanism. Auto-labeling: findings whose attribution is 'high'
are candidates for BIC auto-label (production: only after maintainer
confirmation, to avoid ghost-commit label noise — Rezk et al. TSE'21).
"""
from __future__ import annotations

import json
import os
import time


class YieldModel:
    def __init__(self, state_path: str):
        self.path = state_path
        self.alpha = {}
        if os.path.exists(state_path):
            with open(state_path) as f:
                self.alpha = json.load(f).get("alpha", {})

    def get(self, arm: str) -> float:
        return self.alpha.get(arm, 0.8)

    def update(self, arm: str, exec_s: float, attributed_findings: int, ewma: float = 0.3):
        if exec_s <= 0:
            return
        obs = attributed_findings / (exec_s / 3600.0)   # findings per CPU-hour
        prior = self.get(arm)
        # damp observations (MVP: obs scale is noisy); keep alpha bounded
        self.alpha[arm] = round(max(0.05, (1 - ewma) * prior + ewma * min(obs / 10.0, 2.0)), 4)

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({"alpha": self.alpha, "updated": time.time()}, f, indent=2)


def append_run_record(runs_dir: str, record: dict):
    os.makedirs(runs_dir, exist_ok=True)
    with open(os.path.join(runs_dir, "runs.jsonl"), "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def autolabel_candidates(findings: list) -> list:
    return [{"class": f["class"], "entity": f["attribution"]["entity"],
             "commit": f["commit"], "status": "pending-maintainer-confirmation"}
            for f in findings if f.get("attribution", {}).get("level") == "high"]
