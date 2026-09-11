"""FIDO cost ledger — single currency for all CI resource consumption.

Everything that consumes CI resources is debited here: builds, instrumentation,
test execution, fuzzing slots, generation tokens. The ledger is written into
every run record, because "defect discovery per unit compute" claims are
unverifiable without it (see RESEARCH_REPORT.md L15 / §4.4).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


# LLM token -> CPU-second conversion used for budget accounting.
# Deliberately crude and configurable; the point is that inference is NOT free.
TOKENS_PER_CPU_S = 50_000.0


@dataclass
class Ledger:
    budget_s: float
    entries: list = field(default_factory=list)

    def start(self) -> None:
        self._t0 = time.time()

    def debit(self, arm: str, kind: str, seconds: float, note: str = "") -> None:
        """kind in {build, exec, instrument, llm, triage}."""
        self.entries.append({"arm": arm, "kind": kind, "seconds": round(seconds, 3),
                             "note": note})

    def debit_tokens(self, arm: str, tokens: int, note: str = "") -> None:
        self.debit(arm, "llm", tokens / TOKENS_PER_CPU_S, note)

    @property
    def spent(self) -> float:
        return round(sum(e["seconds"] for e in self.entries), 3)

    @property
    def remaining(self) -> float:
        return max(0.0, round(self.budget_s - self.spent, 3))

    def by_arm(self) -> dict:
        out: dict[str, float] = {}
        for e in self.entries:
            out[e["arm"]] = round(out.get(e["arm"], 0.0) + e["seconds"], 3)
        return out

    def summary(self) -> str:
        parts = [f"{arm}: {s}s" for arm, s in sorted(self.by_arm().items())]
        return f"{self.spent}/{self.budget_s}s spent [{', '.join(parts) or 'nothing'}]"


class ArmClock:
    """Measures actual wall-clock seconds an arm consumed (proxy for CPU-s on
    an idle runner; production deployment meters cgroup CPU time)."""

    def __init__(self, ledger: Ledger, arm: str):
        self.ledger = ledger
        self.arm = arm
        self._t = None

    def __enter__(self):
        self._t = time.time()
        return self

    def __exit__(self, *exc):
        self.ledger.debit(self.arm, "exec", time.time() - self._t)
