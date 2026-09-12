# CI-AI-CD — Change-Conditioned Failure-Mode Steering for Budgeted CI Testing

This repository contains (1) the systematic literature analysis that derives and validates a
research gap, and (2) a working reference implementation of a system designed to fill that gap.

| Document | Content |
|---|---|
| `research/RESEARCH_REPORT.md` | 12-phase literature analysis (8 domains, capability matrix, 6 candidate gaps, red-team validation, problem statement, methodology) |
| `research/SYSTEM_ARCHITECTURE.md` | The system architecture designed against the validated gap (FIDO) |
| `fido/` | **Working reference implementation** of that architecture (this README) |
| `eval/replay.py` | Budget-fair historical-commit replay harness (the experiment engine) |

## The gap being filled

From the red-team-validated report: existing work selects *existing* tests per change (Ekstazi,
predictive test selection), directs *one* technique — fuzzing — at changed code (AFLGo, AFLChurn,
CIDFuzz, WAFLGO), or steers generation toward sanitizer checks globally, never per-change
(ParmeSan, SAVIOR). No peer-reviewed, evaluated system predicts the **failure-mode class** of a
semantic change and uses it to steer **detector selection, oracle choice, and input-generation
strategy under a CI compute budget**. This implementation is the reference design for that
system, with the two research components (classifier, planner) isolated from off-the-shelf
executors so the contribution is ablatable and falsifiable.

## Pipeline → code map

```
Historical Commit / Push
  │
  ▼
AST/Entity-Level Diff + Changed-Symbol Dependency Context     fido/change/extractor.py
  │        L0 textual diff → L1 entity diff → L2 affected set (callers)
  │        → L3 risk lexicon → L4 history (churn) → L5 coverage map
  ▼
Semantic Change Analysis                                      (same module: ChangeRecord)
  │        incl. cross-diff-side ops (type narrowing, removed bounds/null checks)
  ▼
Failure-Mode Classification                                   fido/predict/classifier.py
  │        Tier-A deterministic scorer (Tier-B LLM hook: FIDO_LLM_CMD, cost-debited)
  │        → calibrated class probs + per-entity attribution
  ▼
Budgeted Strategy Planner                                     fido/plan/planner.py
  │        floors/caps/knapsack; sanitizer plan w/ cost gates + unavailability
  │        constraints; policies P0 fixed / P1 prior / P2 greedy / P4 probe-then-commit
  ├── Regression Testing (RTS + class-conditioned sanitizer hardening)   fido/exec/rts.py
  ├── Change-Directed Fuzzing (real exec; AFLGo adapter hook)            fido/exec/fuzz.py
  ├── Generated Boundary / Unit Tests (class-shaped, execution-validated) fido/exec/gen.py
  ├── Selective Concolic (deep-guard trigger-gated, QSYM adapter hook)   fido/exec/concolic.py
  └── Differential / Metamorphic (O0-vs-O2 corpus replay)                fido/exec/diffbuild.py
  │
  ▼
Sandboxed Execution (rlimits + wall timeout; Docker per-arm in production)  fido/exec/runner.py
  │        every CPU-second and LLM token metered                        fido/ledger.py
  ▼
Failure Detection + Change Attribution                        fido/triage/triage.py
  │        normalize → attribute (stack frames + entity line ranges) →
  │        dedup (stack hashing) → intent filter (UB vs intentional wraparound)
  ▼
AI-Assisted Triage (LLM hook; heuristics in MVP)              fido/triage/triage.py
  ▼
Per-Commit CI Report (markdown + JSON run record)             fido/report/report.py
  └────────► Learning loop: EWMA yield model + auto-label candidates      fido/learn/loop.py
```

## Quickstart

```bash
# 1. unit tests (no external deps)
python3 -m tests.run_all

# 2. create the demo project (history contains a real bug-inducing commit)
bash scripts/setup_demo.sh

# 3. run the pipeline against the BIC
python3 -m fido run /tmp/fido-demo/calcstat HEAD --budget 900 --policy p4

# 4. replay the whole history with a fixed budget (the core experiment primitive)
python3 -m eval.replay /tmp/fido-demo/calcstat --budget 300 --policy p4
```

Expected results are documented with real output in `docs/replay_walkthrough.md` and
`docs/example_report_bic.md`. In brief: the BIC is caught by two steered arms (fuzzer →
OOB write at `main.c:10`; *generated* boundary input `2147483647 2147483647` → signed
overflow at `main.c:11`), both attributed high; clean commits and the fix commit produce
zero findings; the hash commit's UB is flagged `suspected_intentional (hash idiom)` by the
source-aware intent filter; the magic-guard commit fires the deep-guard trigger (concolic
required) instead of wasting fuzzing budget.

## What is real vs. adapter (honesty table)

| Component | Status in this repo |
|---|---|
| ASan/UBSan builds, execution, sanitizer parsing | **Real** (gcc 12; sanitizer findings are genuine executions) |
| RTS selection + hardened reruns of selected tests | **Real** (coverage-map selection; sanitizers at -O1) |
| Boundary-input generation from predicted class | **Real but rule-based** (macro-aware; LLM codegen hook behind `FIDO_LLM_CMD`) |
| Differential O0-vs-O2 replay | **Real** (existing corpus inputs; catches optimizer-elided UB) |
| MiniFuzzer | **Real but demo-grade** (integer-stream grammar; structure-aware for the demo class). Production path: `FIDO_AFLGO_CMD` adapter for AFLGo/WAFLGO |
| Concolic arm | **Trigger implemented** (deep-guard evidence: magic constants, multi-char compares, checksums); engine adapter pending (`FIDO_CONCOLIC_CMD`) |
| MSan/TSan | **Capability-probed, never assumed** — this sandbox lacks clang, so the planner constraint-propagates them as unavailable (by design: sanitizers are incompatible; MSan needs instrumented deps) |
| Tier-B LLM judge / triage | **Hooked, disabled by default**, tokens debited to the ledger when enabled |
| Yield model | **EWMA implementation + run records**; bandit policy (P3) specified, not trained (needs replay corpora) |

## Known limitations (all deliberate, documented scope cuts)

1. S1 uses dependency-free heuristics (line regexes + function-range scan), not tree-sitter/GumTree —
   the ChangeRecord contract is the stable interface; production swaps the module, not the pipeline.
2. Tier-A weights are documented heuristics, not learned — the point of the MVP is the *contract*
   (probs + per-entity attribution) that a trained GBDT/LLM must fill; learning requires the labeled
   BIC corpora listed in `research/RESEARCH_REPORT.md` §12.
3. Fuzzing targeting is input-shape bias; real distance-guided targeting arrives with the AFLGo adapter.
4. The demo target is a 60-line C program: it proves wiring and the causal chain, not scale. Scale
   claims require the experiment plan (below).
5. Attribution for frameless sanitizer reports relies on changed-entity line ranges; imprecise for
   macros and headers (recorded as `medium` instead of guessed).

## Research positioning: what a paper would measure

The implementation exists to make these measurable (full methodology in `research/RESEARCH_REPORT.md`):

- **E1 (prediction):** per-class recall/precision of failure-mode prediction vs churn/JIT baselines on
  labeled BIC datasets (WAFLGO-30, vetted OSS-Fuzz regression bugs).
- **E2 (steering):** bugs-per-CPU-hour of {P0, P1, P2, P4} × {10min, 1h, 8h, 24h} × ≥20 seeds vs
  WAFLGO / CIDFuzz / fixed-portfolio / predictive-TS baselines.
- **E3 (sanitizer pre-selection):** time-to-first-relevant-violation, class-matched vs fixed portfolios.
- **E4 (ablation):** −steering, −Tier-B, −individual arms — isolates marginal value of each component.
- **E5 (budget sensitivity):** the P0-vs-P4 crossover curve — answers the Fuzzing'24 open question.

Kill criterion retained from the roadmap: if E1 cannot beat the churn baseline, the harness carries
over intact to the fallback gap (budget-sensitivity study of change-directed testing).
