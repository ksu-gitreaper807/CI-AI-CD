# System Architecture: Change-Conditioned Failure-Mode Steering for Budgeted CI Testing

**Working name:** FIDO — *Failure-mode-Informed Dynamic Orchestration* (name placeholder)
**Fills gap:** G2×G1 from `RESEARCH_REPORT.md` — *no peer-reviewed, evaluated system predicts the failure-mode class of a semantic change and uses it to steer detector (sanitizer) selection, oracle choice, and input-generation strategy under a CI compute budget.*

**Design principle #1 — Two research components, everything else off-the-shelf.**
The contribution lives in exactly two boxes: (1) the **failure-mode classifier** and (2) the **budgeted planner**. All executors wrap existing tools (Ekstazi-class RTS, AFLGo/WAFLGO-class directed fuzzing, QSYM-class concolic, LLM test generation with validation, EMI-class differential builds). Every boundary between components is a logged data contract, so any run can be replayed and every decision audited.

**Design principle #2 — Soft steering, not hard switching.**
The classifier outputs a *probability distribution* over failure classes; the planner converts it into a *budget split*, never a binary technique on/off. Wrong predictions degrade gracefully (floors and caps guarantee baseline coverage) instead of catastrophically (a missed class still gets its floor). This is what makes the system safe to evaluate against fixed portfolios.

**Design principle #3 — Budget is a first-class citizen.**
Build time, instrumentation cost, LLM tokens, and execution CPU-seconds are all metered in one currency (CPU-seconds, with token→second conversion). This is what existing change-directed fuzzing lacks (Fuzzing'24 open problem) and what makes defect-discovery-per-compute measurable.

---

## 1. Bird's-eye view

```
                       ┌──────────────────────────────────────────────────────────┐
                       │                     CI TRIGGER LAYER                     │
                       │  push / PR webhook → snapshot commit → budget B granted  │
                       └───────────────────────────┬──────────────────────────────┘
                                                   ▼
┌──────────────────────────┐   ┌──────────────────────────┐   ┌──────────────────────────────┐
│ S1. CHANGE EXTRACTION    │   │ S2. FAILURE-MODE         │   │ S3. BUDGETED PLANNER         │
│ textual diff             │   │    CLASSIFIER  ◄────┐    │   │    (research component #2)   │
│ entity/AST diff          │──►│    (research comp.#1)│    │◄──│ yield model + allocation     │
│ affected-set (call graph)│   │ P(class|change,repo) │────┘   │ policy (bandit/knapsack)     │
│ history + coverage feats │   │ + confidence + per-  │        │ → Plan JSON                  │
└──────────────────────────┘   │   entity attribution │        └──────────────┬───────────────┘
                               └──────────────────────┘                       ▼
                       ┌──────────────────────────────────────────────────────────────┐
                       │ S4. EXECUTION FABRIC (sandboxed, budget-metered)             │
                       │  build cache ─ sanitizer-variant builds                      │
                       │  ├─ A1 RTS / regression suite (Ekstazi/ML-selected subset)   │
                       │  ├─ A2 directed fuzzing (class-matched sanitizer build)      │
                       │  ├─ A3 validated test generation (LLM + execution filter)    │
                       │  ├─ A4 selective concolic (QSYM-class, deep-guard trigger)   │
                       │  └─ A5 differential/metamorphic builds (O-level / sanitizer) │
                       └───────────────────────────┬──────────────────────────────────┘
                                                   ▼
                       ┌──────────────────────────────────────────────────────────────┐
                       │ S5. FINDINGS: normalize → attribute to change → dedup →      │
                       │     intent-filter (UB vs intentional) → severity             │
                       └───────────────────────────┬──────────────────────────────────┘
                                                   ▼
                       ┌──────────────────────────┐    ┌─────────────────────────────┐
                       │ S6. CI REPORT (PR check) │    │ S7. LEARNING LOOP           │
                       │ predictions, plan, costs,│───►│ update yield model (bandit), │
                       │ findings + evidence      │    │ recalibrate classifier on    │
                       └──────────────────────────┘    │ confirmed BICs (auto-label)  │
                                                       └─────────────────────────────┘
```

---

## 2. Component S1 — Change Extraction (the substrate)

**Purpose:** turn a `git push` into a structured **ChangeRecord** rich enough to predict failure modes — this is where the "semantic" qualifier is earned. Textual diffs are the input, not the output.

### 2.1 Representation ladder (each level feeds the next)

| Level | What is computed | Tooling | Why it matters |
|---|---|---|---|
| L0 | Textual patch (unified diff), file list, hunk locations | git | baseline; raw material |
| L1 | Entity diff: added/removed/modified functions, methods, classes; AST edit ops (condition changed, new branch, call-site changed, constant literal changed, pointer arithmetic changed…) | tree-sitter for 1st-pass; GumTree-class AST diff for supported languages | SEMCIA showed textual impact sets carry 23–49% false-positive dependencies; entity diff is the fix |
| L2 | Affected-set: direct/transitive callers & callees of changed entities; virtual overriders; callback/function-pointer registrations; template instantiations | LLVM `callgraph` / CodeQL / ctags+heuristics | WAFLGO's own future-work request: *semantic* identification of affected code beyond changed lines |
| L3 | Type & API risk features per changed entity: integer widths of assigned/compared expressions, presence of `malloc/free/new/delete`, array indexing patterns, `strcpy/memcpy/sprintf/alloca/VLA`, unchecked allocation, casts, iterator usage near container mutation, lock acquire/release pairs, atomics | tree-sitter queries + lightweight clang AST pass on changed TUs | these are the direct lexical precursors of each failure class |
| L4 | History features: churn (1w/1m/6m), prior BIC count of touched files, bug-density of module, author/reviewer experience, fix-recency | git log mining (Kamei JIT feature families) | proven change-risk signal; the *churn* signal AFLChurn uses is the weakest member of this family |
| L5 | Test-coverage map: which existing tests cover each changed entity (from last full-coverage run, Ekstazi-style per-class dependencies) | coverage DB updated nightly | input to Arm A1 (RTS) and to the "uncovered changed code" escalation signal |

### 2.2 ChangeRecord contract (abridged JSON)

```json
{
  "commit": "sha", "parent": "sha", "budget_cpu_s": 1800,
  "entities": [
    {
      "id": "src/parser/expr.c::eval_expr",
      "op": "modified",
      "ast_ops": ["branch_added", "comparison_operand_changed", "call_added:parse_int"],
      "affected": {"callers": [...], "callees": [...], "overriders": []},
      "risk_lex": {"int_ops_unsafe": 3, "ptr_arith": 1, "unbounded_copy": 0,
                    "iter_mutate_proximity": false, "locks_touched": 0},
      "covered_by_tests": ["test_eval_basic", "test_eval_edge"]
    }
  ],
  "history": {"churn_1m": 14, "prior_bics": 2, "author_exp": 0.6, "module_bug_density": 0.11},
  "build": {"system": "cmake", "buildable_variants": ["asan","ubsan","tsan","plain"],
             "build_cache_hit": {"asan": true, "msan": false}}
}
```

**Engineering notes.** (a) All feature extraction must complete in <10 s wall time for typical commits — it runs before any budget is spent on testing. (b) The coverage DB (L5) is the only cross-commit state; everything else is derivable from the repo. (c) If AST diff fails (unsupported language/macro soup), degrade to L0+L3-lite and record `degraded=true` — the planner must know feature quality.

---

## 3. Component S2 — Failure-Mode Classifier *(research component #1)*

### 3.1 Taxonomy (multi-label, aligned 1:1 with detector capabilities)

| Class | Includes | Natural detectors |
|---|---|---|
| `MEM` | OOB read/write, UAF, double-free, dangling pointers, stack overflow | ASan |
| `UNINIT` | uninitialized reads | MSan (expensive, all-deps build) |
| `INT_UB` | signed overflow, div-by-zero, invalid shift, lossy truncation, pointer overflow | UBSan (+`implicit-conversion`), IOC-style checks |
| `LIFETIME` | invalid iterators/references after mutation, vptr misuse, use-after-move | UBSan `vptr`, ASan, container-debug builds |
| `CONC` | data races, deadlocks, atomicity violations, ordering | TSan |
| `LOGIC` | wrong outputs, violated invariants, oracle failures (no sanitizer will fire) | generated/existing tests with oracles, metamorphic relations |

Multi-label because a real commit risks several classes at once (e.g., a rewrite of an integer parser can be `INT_UB`+`MEM`).

### 3.2 Model: two tiers with confidence-gated escalation

**Tier A — deterministic workhorse (always runs, ~ms, free):**
gradient-boosted trees (XGBoost/LightGBM) over ChangeRecord features (L1–L4). Handles cold start via cross-project training; interpretable feature importances; trivially reproducible. Output: calibrated probabilities (isotonic), per-entity and aggregated to commit.

**Tier B — LLM semantic pass (runs only when Tier A is uncertain or stakes are high):**
frozen code LLM prompted with (patch hunk + callee signatures + type context) → JSON {class probabilities, per-entity rationales}. Used when: `max_a P(a) < τ_uncertain` (e.g., 0.55), OR predicted-class expected cost is high (e.g., would trigger an MSan build), OR change touches safety-critical module list. Token cost is converted to CPU-seconds and debited from budget — the planner treats the LLM as an arm-like expense, which is the honest way to account for it.

**Why two tiers:** the LLM-fuzzing literature's central reliability lesson is that probabilistic outputs need deterministic scaffolding ("no stable interface between probabilistic model outputs and checkable fuzzing evidence"). Tier A is the scaffold; Tier B is bounded, logged, and auditable.

### 3.3 Training data & labels

- **Positive labels:** bug-inducing commits (BICs). Sources: WAFLGO's 30-bug dataset (manual BIC IDs); OSS-Fuzz regression bugs (AFLChurn's 20-bug set + tracker mining); SZZ-mined candidates from large C/C++ projects, **manually vetted for eval** (training can tolerate noise; evaluation cannot — ghost commits make ~25% of BICs untraceable, so SZZ-only eval would be indefensible).
- **Label class assignment:** from the *fix* evidence — sanitizer report type of the fixing report (ASan heap-buffer-overflow → `MEM`), crash type, issue tags. Rule-based with human spot-check; report κ agreement.
- **Negatives:** random clean commits + "near-miss" commits (adjacent refactors) to prevent trivial learns.
- **Augmentation:** LAVA-style synthetic bug injection at controlled class ratios for low-data classes (`UNINIT`, `CONC`).
- **Contamination control:** hold out post-LLM-cutoff bugs (LIBRO protocol).

### 3.4 Output contract

```json
{ "commit_probs": {"MEM": 0.62, "INT_UB": 0.31, "UNINIT": 0.02, "LIFETIME": 0.05,
                    "CONC": 0.00, "LOGIC": 0.20},
  "tier": "A+B", "confidence": "medium",
  "entity_attribution": [
     {"entity": "src/parser/expr.c::eval_expr", "top_class": "INT_UB", "p": 0.71,
      "evidence": ["signed add of parsed ints", "no overflow guard"]}],
  "calibration_version": "iso-v3" }
```

`entity_attribution` is not decoration: it *sets the fuzzing targets* (Arm A2) — predicted-class-ranked changed entities become the DGF target list, which is precisely the semantic-targeting WAFLGO lists as future work.

### 3.5 How this is evaluated (RQ1 hook)

Per-class top-1/top-3 recall & precision vs baselines: churn signal (AFLChurn-style), Kamei JIT feature model (risk-only, degenerate to single class), majority class, and Tier-A-only vs A+B. Cross-project validation (leave-one-project-out) + in-project time-split. Report calibration curves — an uncalibrated probability poisons the planner.

---

## 4. Component S3 — Budgeted Planner *(research component #2)*

### 4.1 Formalization

Given budget `B` (CPU-s, *inclusive* of build and LLM costs), change context `x` (ChangeRecord + class distribution `p`), arms `a ∈ A`, choose budgets `b_a` to:

```
maximize   Σ_a  Ê[Y_a(b_a ; x, p)]            (expected confirmed, change-attributed findings)
subject to Σ_a (b_a + ĉ_build(a) + ĉ_llm(a)) ≤ B
           b_a = 0  ∨  b_min(a) ≤ b_a ≤ b_max(a)      (floor/cap constraints)
           b_RTS ≥ floor_RTS                           (safety: regression suite always runs a slice)
```

`Y_a(·)` are modeled as concave (diminishing returns) — a 2-parameter log curve per (arm × repo × class): `Y = α · log(1 + b/β)` with α (yield rate) learned per repo from replay + online updates, β (saturation) from arm characteristics. Budgets discretized into slots (e.g., 120 s) for tractable search; with ≤6 arms and ≤15 slots the knapsack is solved exactly in microseconds, or approximately by greedy for the online variant.

### 4.2 Arms and their class-conditioning

| Arm | Technique (off-the-shelf core) | Steered by prediction how |
|---|---|---|
| **A1 Regression suite** | Ekstazi/STARTS-class RTS or ML-selected subset | Always ≥ floor. Budget shrinks when `p` concentrates on sanitizer-detectable classes (existing tests rarely exercise UB) |
| **A2 Directed fuzzing** | AFLGo/WAFLGO-class DGF on class-matched build; targets = predicted-class-ranked changed entities | Sanitizer build per argmax classes (`MEM`→ASan, `INT_UB`→UBSan+integer, `LIFETIME`→UBSan vptr/ASan, `UNINIT`→MSan only if `p>τ_MSan` because build cost is brutal, `CONC`→TSan short slot); energy schedule reweighted toward entities with high per-entity `p` |
| **A3 Validated test generation** | CodaMosa/TestPilot-class LLM generation + execution validation | Prompted with patch + entity attribution: "target boundary conditions of *this* changed function; assert on documented invariants"; for `INT_UB`: integer-edge inputs (INT_MAX, 0, negatives); for `LOGIC`: oracle-mining from existing tests (DSpot-style assertion addition). Validity filter: compile → run ×5 → keep only deterministic, coverage-positive tests (flakiness filter per Meta/LLM-flakiness findings) |
| **A4 Selective concolic** | QSYM-class hybrid | Triggered, not scheduled: only when L1/L3 features indicate deep guards (rare constants, checksum-like comparisons, nested magic bytes) in changed entities; gets a small probe slot then expands only if solvable-progress detected |
| **A5 Differential/metamorphic** | Build variants (O0 vs O2; sanitized vs plain) + replay existing test inputs; compare stdout/exit/sanitizer presence | Motivated by sanitizer-eliding optimizations (PLDI'23): catches UB that sanitizers miss under optimization. Cheap (reuses existing inputs); activated when L3 flags optimizer-sensitive patterns (UB-prone idioms) or `INT_UB`/`LIFETIME` probability non-trivial |

### 4.3 Policy stack (each is an ablation point)

| Policy | Mechanism | Role |
|---|---|---|
| P0 fixed portfolio | equal/hand-tuned splits, all builds | **baseline** |
| P1 prior-split | split ∝ calibrated class priors × static arm-class utility matrix | naive steering baseline |
| P2 greedy knapsack | myopic optimization of §4.1 with replay-learned yields | deterministic, explainable, deployable day 1 |
| P3 contextual bandit | LinUCB / Thompson sampling; context = ChangeRecord features; reward = confirmed findings / CPU-s; arms = (technique, sanitizer-config) slot allocations | learns repo-specific quirks over time |
| P4 two-phase probe-then-commit | Phase 1 (≈25% B): RTS + short probes of top-2 arms; observe early signals (crash found, patch-coverage rate of A2, generated-test validity rate, concolic progress); Phase 2: reallocate remaining 75% under updated posterior | handles prediction errors in-run; the "steering" is closed-loop |

**Early-signal escalation rules (P4, hard-wired safety net):** if after probe phase directed fuzzing has <X% patch coverage of changed entities → swap in A3/A4 or extend seeds from corpus; if any arm finds a crash → allow emergency budget extension from unallocated reserve (crashes are the highest-value events; ClusterFuzz-style triage follows).

### 4.4 Cost ledger

Everything that consumes CI resources is debited: builds (per-variant, amortized by cache hit-rate), instrumentation (AFLGo distance maps — cached keyed by target-set hash across commits), fuzzing slots, test executions, LLM tokens (fixed conversion), triage. The ledger is part of the report and of every experimental record — without it, "per unit compute" claims are unverifiable.

### 4.5 How this is evaluated (RQ2/RQ3 hooks)

Equal-budget paired replays; arms-off ablations (drop A3; drop A5; drop steering = P0); budgets ∈ {10 min, 1 h, 8 h, 24 h} × ≥20 seeds; primary metric unique confirmed bugs / CPU-hour; secondary: TTD, % BICs detected, per-class detection recall, safety violations vs retest-all. The crossover hypothesis (steering wins most at small budgets, converges to portfolio at large budgets) is itself a publishable finding either way it lands.

---

## 5. Component S4 — Execution Fabric (engineering, deliberately boring)

**Build layer.** Per-variant images (base + ASan / UBSan / MSan-prebuilt-deps / TSan / plain) built ahead of time per project; per-commit compile via ccache/sccache keyed by (commit, flags). MSan is special-cased: requires instrumented dependency tree — maintained as a prebaked image per supported project, otherwise MSan is marked `unavailable` and the planner must never allocate to it (constraint propagation, not hope).

**Fuzzing layer.** Persistent corpus per project (carried across commits — the single biggest lever for CI-time fuzzing productivity); seeds = project corpus + regression-triggering inputs from past findings; AFLGo distance instrumentation cached by target-set hash so consecutive commits on the same module reuse maps (attacks the "distance computation too expensive for CI" problem directly).

**Test layer.** Selected regression subset from the coverage DB; generated tests go through compile → run×5 → flake-check → coverage-delta check before counting.

**Differential layer.** Reuses existing test inputs and fuzzing corpus against the O0/O2/plain-vs-sanitized builds; comparison = (exit code, stdout hash, sanitizer trigger). Zero new input generation cost; catches the optimizer-elision class.

**Isolation & accounting.** One container per arm; cgroup v2 CPU accounting = the budget currency; all artifacts (crashes, logs, coverage profiles, generated tests) persisted with the commit SHA for replay.

---

## 6. Component S5 — Findings, Attribution, Triage

1. **Normalize** every anomaly into one schema: `{type: sanitizer|crash|test_fail|diff_violation, class, stack, artifact}`. The `class` field uses the *same taxonomy* as S2 — closing the loop (a `MEM` prediction that yields an ASan finding confirms both predictor and planner).
2. **Change attribution** (the "is this MY bug" question): crash path must touch changed/affected entities — via patch-coverage counters (changed-code edge coverage from the instrumented builds) or AFLGo target-hit maps; for test failures, blame the changed entities in the failure stack. Findings in untouched code are down-weighted (pre-existing bugs → report separately, still valuable, but excluded from the *steering* reward signal).
3. **Dedup**: stack-frame hashing (ClusterFuzz-style) + crash input minimization (Lithium-style delta debugging) before reporting.
4. **Intent filter for `INT_UB`** (the Dietz/IOC lesson — intentional wraparound is everywhere): heuristic idiom checks (hash-mixing patterns, `(a > b) == (a - b > 0)` idioms) + optional LLM judgment, always labeled "suspected intentional" rather than silently dropped — misclassification risk is reported honestly.
5. **Severity**: exploitability heuristics + module criticality + reachability from public entry points.

---

## 7. Components S6/S7 — Report & Learning Loop

**Report (PR check / CI annotation):**
```
Predicted classes: MEM 0.62 | INT_UB 0.31 | LOGIC 0.20   (tier A+B, calibrated)
Plan: RTS 120s · DGF+ASan 600s · DGF+UBSan 300s · GenTests 240s · DiffO0/O2 180s
Spent: 1410/1800 CPU-s (build cache saved ~900s)
Findings: 1 confirmed (ASan heap-buffer-overflow @ parser/expr.c:214 — path covers
          changed eval_expr; attribution: high) · 1 suspected-intentional (UBSan shift)
```

**Learning loop (S7):**
- **Yield model update (P3/P4):** every run emits `(context, allocation, costs, findings)`; bandit posteriors update per repo. Transfer prior from cross-project replays so new repos don't start blind.
- **Classifier auto-relabeling:** when a finding is later confirmed as a real bug by maintainers (fix commit references the report), the commit is added as a labeled BIC of the finding's class → periodic classifier fine-tune + recalibration. This is how the system *accumulates project-specific failure-mode knowledge* — the G5 gap — as a by-product rather than a separate system.
- **Drift handling:** rolling-window recalibration; report prediction-vs-reality confusion per month (the "moving target" phenomenon from McIntosh–Kamei applies to failure modes too).

---

## 8. Repository layout (buildable shape)

```
fido/
├── change/            # S1: tree-sitter entity diff, AST pass, history miner, coverage DB
├── predict/           # S2: Tier-A GBDT, Tier-B LLM client, calibration
├── plan/              # S3: cost ledger, yield models, P0–P4 policies, constraint solver
├── exec/
│   ├── builds/        # variant build orchestration + caches
│   ├── rts/           # A1 wrapper (Ekstazi/STARTS/predictive selection adapters)
│   ├── fuzz/          # A2 wrapper (AFLGo/WAFLGO adapters, corpus manager)
│   ├── gen/           # A3 wrapper (generation prompt templates, validation filter)
│   ├── concolic/      # A4 wrapper (QSYM adapter, deep-guard trigger)
│   └── diff/          # A5 wrapper (variant runner, output comparator)
├── triage/            # S5: normalize, attribute, dedup, intent filter
├── report/            # S6
├── learn/             # S7: bandit state, auto-labeling, recalibration jobs
└── eval/
    ├── replay/        # budget-fair historical-commit replay harness (the experiment engine)
    ├── datasets/      # WAFLGO-30, OSS-Fuzz regression sets, labeled BIC corpora (indices only)
    └── analysis/      # RQ1–RQ4 notebooks/statistics
```

**MVP path (8–10 weeks, degrades gracefully):**
1. Replay harness + WAFLGO-30 + FuzzBench integration. (No research value without this; build it first.)
2. Tier-A classifier on L1+L4 features with rule-labeled classes.
3. Planner P2 + two arms only: A1 (RTS via make/test subset) and A2 (directed fuzzing, ASan & UBSan builds).
4. Run RQ2's core comparison: steering vs P0-fixed vs WAFLGO alone at 10-min and 1-h budgets.
5. Add arms/one at a time (A5 differential next — cheapest high-precision win; A3 generation after; A4 concolic last, trigger-gated).

---

## 9. Why this architecture beats the gap (mapping design → evidence)

| Gap requirement (from report) | Architecture answer | Evidence anchor |
|---|---|---|
| Predict *failure-mode class* of a change | S2 two-tier classifier, class taxonomy aligned to detectors, per-entity attribution | JIT predicts risk-only; SEMCIA proves semantic features carry signal; LIBRO proves failure-description-conditioned generation works |
| Steer *sanitizer selection* | Class-matched builds in A2; MSan gated by cost-aware threshold; unavailable-variant constraint propagation | Sanitizers incompatible, 2–46× overhead spread (Sand/Expozzer/ReZZan) — the decision is real and costly |
| Steer *oracle choice* | A3 oracles for `LOGIC`, A5 differential for optimizer-elided UB, sanitizer oracles for memory/int classes | Don't-Look-UB (PLDI'23) shows sanitizer-only oracles are leaky; metamorphic/differential literature |
| Steer *input generation* | Entity-attribution-ranked DGF targets; class-shaped generated boundary tests; persistent corpus | WAFLGO: reaching ≠ exercising, semantic targeting = their stated future work |
| Under a *CI compute budget* | Single cost ledger incl. builds & LLM; P2 knapsack; P4 probe-then-commit | Fuzzing'24 registered reports: DGF impractical at CI budgets — open problem |
| *Measurable, defensible* contribution | Both research components behind logged contracts; full ablation ladder (P0..P4, arm-off, tier-off) | Defect-discovery-per-compute framing from Google-scale CI study |

**Novel mechanics vs nearest prior work:** WAFLGO/CIDFuzz steer *targets* only (changed lines), with one fixed oracle portfolio and no budget model — S2/S3 add the class dimension and the budget dimension. SAVIOR/ParmeSan steer *toward bug checks* but globally, not per-change. Predictive TS allocates budget across *existing tests* only. The composition — semantic change → class distribution → budgeted heterogeneous portfolio → attributed findings → learning loop — is the claimed contribution, and every link is logged so the claim is falsifiable.

---

## 10. Risk register (architecture-level mitigations)

| Risk | Mitigation |
|---|---|
| Classifier wrong → budget misallocated | Soft allocation (probabilities, floors, caps); P4 in-run escalation; never zero-out RTS |
| Build/instrumentation overhead eats budget | Aggressive caching (ccache, distance-map cache, prebaked MSan images); planner debits estimated build cost *before* allocating; skip variants whose build cost > expected yield |
| LLM cost/nondeterminism | Tier-B only on uncertainty; temperature 0 + self-consistency vote; tokens debited in CPU-s; full prompt/response logs |
| Finding flood / false positives | Dedup + attribution + intent filter before reporting; FP rate is a tracked metric, reported per run |
| Label noise poisons S7 auto-labeling | Auto-labels only from maintainer-confirmed fixes; eval sets always human-vetted; periodic calibration audit |
| Fuzzing variance drowns signal | ≥20 seeds, FuzzBench statistical protocol, budget-matched comparisons, report CIs |
| Language generality creep | C/C++ first (the UB domain justifying the whole premise); the architecture's S1 isolates language specifics behind tree-sitter adapters |

---

## 11. Minimal experiment matrix (what proves the thesis)

1. **E1 (RQ1):** Tier-A vs +Tier-B vs churn vs JIT-features on held-out BICs — per-class recall/precision, calibration error.
2. **E2 (RQ2):** {P0 fixed, P1 prior, P2 knapsack, P4 probe-commit} × {10 min, 1 h, 8 h, 24 h} × 20 seeds on WAFLGO-30 + OSS-Fuzz regression set — bugs/CPU-hour, TTD, %BIC detected.
3. **E3 (RQ3):** class-matched single-sanitizer vs ASan-first-sequential vs full-parallel portfolio at equal budget — TTD per class, violations/CPU-s.
4. **E4 (ablation):** −A3, −A5, −steering (P0), −TierB — isolates each component's marginal value.
5. **E5 (budget sensitivity):** the P0-vs-P4 crossover curve — answers the Fuzzing'24 open question directly.

If E1 fails (classifier ≤ churn), the honest fallback is G4 (budget-sensitivity study of change-directed testing) — the replay harness, ledger, and E2/E5 infrastructure carry over intact. That fallback property is a deliberate architectural feature: the experiment engine is the most reusable artifact of the system.
