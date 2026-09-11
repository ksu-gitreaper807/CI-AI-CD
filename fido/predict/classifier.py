"""S2 — Failure-Mode Classifier (research component #1).

Tier A ships here as a deterministic, fully-auditable feature scorer with the
SAME input/output contract as a trained model: ChangeRecord -> calibrated-ish
multi-class probabilities + per-entity attribution.  `train.py`-style GBDT can
be dropped in behind `ModelContract` (see load_model); sklearn path is guarded.

Tier B (LLM semantic pass) is implemented behind `LLMJudge` — disabled unless
FIDO_LLM_CMD is set; cost is debited to the ledger (never free).
"""
from __future__ import annotations

import math
import os
import subprocess
from collections import OrderedDict

from fido.change.extractor import CLASSES

DEFAULT_PRIOR = {c: 1.0 for c in CLASSES}

# Tier-A weight table (documented heuristics; replace with learned weights).
W = {
    "indexed_write": 2.6, "unbounded_copy": 2.8, "bounds_check_removed": 2.4,
    "null_check_removed": 1.0, "alloc_call": 0.7, "free_call": 0.9,
    "int_arith_accumulator": 2.4, "int_typed_target": 1.2, "shift_op": 1.5,
    "div_op": 1.1, "mul_op": 0.7, "iterator_op": 1.9, "lock_op": 2.2,
    "atomic_op": 1.8, "condition_changed": 1.3, "function_call_added": 0.3,
    "type_narrowing_int": 2.6,
}
BASE = {"MEM": 0.15, "UNINIT": 0.05, "INT_UB": 0.15, "LIFETIME": 0.05,
        "CONC": 0.03, "LOGIC": 0.25}


class ModelContract:
    def predict(self, change_record) -> dict:
        raise NotImplementedError


class HeuristicScorer(ModelContract):
    """Deterministic scorer. commit_probs = softmax over summed evidence."""

    name = "heuristic-tierA"

    def predict(self, cr) -> dict:
        commit_score = dict(BASE)
        per_entity = []
        for e in cr.entities:
            s = dict(BASE)
            for op, _ in e.ast_ops:
                for c, w in _op_weights(op).items():
                    s[c] = s.get(c, 0.0) + w
                    commit_score[c] = commit_score.get(c, 0.0) + w * 0.8
            top2 = sorted(s.items(), key=lambda kv: -kv[1])[:2]
            per_entity.append({"entity": f"{e.file}::{e.name}",
                               "probs": _softmax(s), "top_class": top2[0][0],
                               "evidence": [o for o, _ in e.ast_ops]})
        probs = _softmax(commit_score)
        ordered = OrderedDict(sorted(probs.items(), key=lambda kv: -kv[1]))
        margin = list(ordered.values())[0] - list(ordered.values())[1]
        return {"commit_probs": ordered,
                "confidence": "high" if margin > 0.15 else "medium" if margin > 0.05 else "low",
                "tier": self.name,
                "entity_attribution": per_entity}


def _op_weights(op):
    from fido.change.extractor import OP_CLASS_WEIGHTS
    return OP_CLASS_WEIGHTS.get(op, {})


def _softmax(d: dict, temp: float = 1.0) -> dict:
    mx = max(d.values())
    exps = {k: math.exp((v - mx) / temp) for k, v in d.items()}
    z = sum(exps.values())
    return {k: round(v / z, 4) for k, v in exps.items()}


class GBDTModel(ModelContract):
    """Drop-in slot for a trained sklearn GBDT over ChangeRecord features.
    Loaded from joblib file set via FIDO_MODEL_FILE; feature extraction must
    match fido/predict/features.py (not shipped in MVP — contract documented)."""

    name = "gbdt"

    def __init__(self, path: str):
        import joblib  # guarded: only needed if a model file is provided
        self.model = joblib.load(path)

    def predict(self, cr) -> dict:
        raise NotImplementedError(
            "GBDT path requires fido/predict/features.py — see README. "
            "MVP ships HeuristicScorer with identical output contract.")


class LLMJudge:
    """Tier B: optional. Invoked only when Tier-A margin < threshold or the
    decision is expensive (e.g., would schedule an MSan build). Cost debited."""

    def __init__(self, ledger=None):
        self.cmd = os.environ.get("FIDO_LLM_CMD")
        self.ledger = ledger

    def available(self) -> bool:
        return bool(self.cmd)

    def judge(self, cr, tier_a: dict, reason: str):
        if not self.available():
            return None
        prompt = json_dumps({"change": cr.to_dict(), "tier_a": tier_a, "why": reason})
        try:
            out = subprocess.run([self.cmd], input=prompt, capture_output=True,
                                 text=True, timeout=60).stdout
            if self.ledger:
                self.ledger.debit_tokens("triage-llm", len(prompt) // 4, "tierB judge")
            import json as _j
            return _j.loads(out)
        except Exception:
            return None


def json_dumps(o) -> str:
    import json
    return json.dumps(o)


def load_model() -> ModelContract:
    path = os.environ.get("FIDO_MODEL_FILE")
    if path:
        return GBDTModel(path)
    return HeuristicScorer()
