# FIDO — Version 1 Scope (2nd-Year CSE Edition)

**Distilled from:** `research/RESEARCH_REPORT.md`, `research/SYSTEM_ARCHITECTURE.md`, the `fido/`
reference implementation, and the `calcstat` demo on branch `arena/01a080aa-ci-ai-cd`.

**What this document is.** The source branch grew into a research-paper-grade system (a 12-phase
literature survey, a validated research gap, five executor "arms," a budgeted knapsack/bandit
planner, a learning loop, and a factorial evaluation plan against WAFLGO/CIDFuzz baselines). This
document **reduces that scope** to something a motivated 2nd-year CSE student can build, debug, and
explain in a term — **without throwing away the central idea**.

**The central idea we are keeping (verbatim intent from the source):**
> *Predict the likely failure-mode class of a semantic code change, and use that prediction to steer
> which testing/analysis tool runs — instead of blindly running a fixed set of checks.*

**Two shaping decisions from the project owner (v1 requirements, not options):**

1. **AI is an integral part of the system** — not a deferred extra. An LLM performs the failure-mode
   classification, generates targeted adversarial test inputs, and triages/explains the findings.
   (This promotes the source's "Tier-B LLM" hooks from optional to core.)
2. **FIDO is an intermediate gatekeeper server that sits between the developer and the real Git
   repository.** The developer pushes to FIDO, not straight to the upstream repo. FIDO runs its
   AI inference and its sandboxed checks **on the server, before the push is allowed through**; only
   pushes that pass policy are forwarded to the upstream repo.

So the spine becomes:
`developer push → FIDO server intercepts → diff + structure analysis → AI failure-mode inference →
AI-targeted checks run in a sandbox → gate (allow/block) → report → forward to upstream if allowed`.

---

## 1. Simple project objective (2–3 sentences)

FIDO v1 is an **AI-powered Git push-gateway server** for C/C++ projects. A developer configures FIDO
as their Git remote; when they push, FIDO intercepts the push, extracts the commit's diff and the
**structure of the changed code**, and asks an LLM (grounded by a deterministic structural analysis)
to classify the change into a small set of **failure-mode categories** and to generate adversarial
test inputs targeted at that risk. FIDO then builds the code and runs only the relevant checks —
compiler warnings, AddressSanitizer, UndefinedBehaviorSanitizer, and the project's existing tests —
**inside a sandbox on the server**, and either **blocks the push** (returning a structured report) or
**forwards it to the upstream repository**. The point is to demonstrate that
**AI-driven, program-structure-aware change analysis can gate CI more intelligently than a fixed
"run everything after the fact" pipeline**.

---

## 2. Minimum viable architecture

The source's seven-stage pipeline (S1–S7) is wrapped in a **server/gatekeeper shell** and its two
"research components" (classifier + planner) are realized as an **AI inference step + a small rule
table**. The whole pipeline runs **server-side, pre-push, in a sandbox**.

```
   Developer's machine                         FIDO GATEKEEPER SERVER
   ┌────────────────┐   git push (to FIDO)   ┌──────────────────────────────────────────────┐
   │  git push       │ ─────────────────────► │ 0. INTERCEPT (bare repo + pre-receive hook)  │
   │  origin=fido    │                        │    receives refs; checks out pushed commits  │
   └────────────────┘                         └───────────────────┬──────────────────────────┘
            ▲                                                      │
            │  allow → forward push        ┌───────────────────────▼──────────────────────────┐
            │  block → reject + report     │ 1. CHANGE EXTRACTION (structure-aware)            │
            │                              │    git diff → changed files/hunks; tree-sitter →  │
            │                              │    which function each changed line belongs to    │
            │                              └───────────────────────┬──────────────────────────┘
            │                              ┌───────────────────────▼──────────────────────────┐
            │                              │ 2. STRUCTURAL PATTERN DETECTION                   │
            │                              │    small fixed set of AST change patterns (§3.1)  │
            │                              └───────────────────────┬──────────────────────────┘
            │                              ┌───────────────────────▼──────────────────────────┐
            │                              │ 3. AI FAILURE-MODE INFERENCE  ★AI★                │
            │                              │    LLM(change context + patterns) → class +       │
            │                              │    rationale + targeted adversarial inputs;        │
            │                              │    rule table = deterministic fallback/guardrail  │
            │                              └───────────────────────┬──────────────────────────┘
            │                              ┌───────────────────────▼──────────────────────────┐
            │                              │ 4. TOOL SELECTION + SANDBOXED RUN                 │
            │                              │    class → tool set; CMake build variants +       │
            │                              │    checks run inside a locked-down container      │
            │                              │    (no network, CPU/mem/time limits)              │
            │                              └───────────────────────┬──────────────────────────┘
            │                              ┌───────────────────────▼──────────────────────────┐
            │                              │ 5. FINDINGS + AI TRIAGE + REPORT  ★AI★            │
            │                              │    parse output; attribute to changed lines;      │
            │                              │    LLM explains + flags intentional-vs-genuine UB │
            │                              └───────────────────────┬──────────────────────────┘
            │                              ┌───────────────────────▼──────────────────────────┐
            └──────────────────────────────│ 6. GATE: policy(findings) → allow | block        │
                                           │    allow → `git push` to real upstream            │
                                           └───────────────────────────────────────────────────┘
```

**Where the AI lives (three integral roles — all grounded, none free-floating):**

- **★ Classification (stage 3).** The LLM receives a compact, structured *change context* built by
  the deterministic stages (changed function source, added/removed lines, detected patterns, callee
  signatures in the file) and returns JSON: `{class probabilities, per-function rationale}`. Because
  it is conditioned on the structural analysis, it is auditable and reproducible (temperature 0).
- **★ Adversarial input generation (feeds stage 4).** Given the predicted class and the changed code,
  the LLM proposes concrete test inputs aimed at that failure mode (e.g., a value that overflows the
  narrowed accumulator, or more inputs than the removed bound allowed). **Every generated input is
  validated by actually running it in the sandbox** — the LLM never decides an outcome, it only
  proposes inputs the sanitizers judge.
- **★ Triage/explanation (stage 5).** The LLM turns raw ASan/UBSan/test output into a human-readable
  finding, and makes the "suspected-intentional vs genuine UB" judgment the source describes — always
  labeled as a suspicion, never silently dropping a finding.

**Design principles carried over from the source (they still hold at small scale):**

1. **The contribution is the conditioning signal, not new tooling.** Every check FIDO runs already
   exists (gcc, ASan, UBSan, the project's tests). The *AI + structure* deciding what to run is the
   contribution. (Source: SYSTEM_ARCHITECTURE.md, "Design principle #1.")
2. **Graceful degradation / never zero-out the baseline.** If the LLM is unavailable, times out, or
   is low-confidence, FIDO **falls back to the deterministic rule table** and still runs the
   compiler-warning + existing-test floor. The gate must never silently pass because AI was down.
   (Source: "floors and caps guarantee baseline coverage.")
3. **Everything is auditable and sandboxed.** The report shows the change context sent to the LLM, its
   raw response, which rule/AI decision fired, and which tools ran — and all execution happens inside
   an isolated, resource-limited sandbox (source `fido/exec/runner.py`: rlimits + wall timeout;
   "Docker per-arm in production").

---

## 3. Version 1 features (small and realistic)

### 3.1 Change patterns detected (start with 4, all from the source's own examples)

The deterministic structural layer that *grounds* the AI. The source's `ChangeRecord` "risk lexicon"
(L3) lists ~15 AST-edit ops; v1 keeps a minimal subset with clear structural signatures:

| # | Change pattern | Structural signature (added/removed AST) | Example from source demo |
|---|---|---|---|
| P1 | **Relational boundary operator changed / bounds check removed** | a loop/if guard against a `MAX/SIZE/LIMIT`-style bound removed, or operator flips (`<`→`<=`) | `while (n < MAX_VALUES && …)` → `while (…)` |
| P2 | **Integer arithmetic type/accumulator change** | accumulator narrowed (`long long`→`int`) or new `+=`/`*`/`<<` on an int target | `long long total` → `int total` |
| P3 | **Validation / null / bounds check removed** | a removed `if (… == NULL)` / `if (… < bound)` / early-return guard | removed `if (n < 2) return 0.0;` |
| P4 | **Pointer / array-index operation introduced or modified** | new/changed `arr[idx] = …`, `*p`, `memcpy/strcpy`, `malloc/free` in a hunk | `values[n++] = x;` under an unbounded loop |

> **Optional 5th pattern (P5 — weakened conditional):** an `if/while` made strictly less restrictive.
> Include only if P1–P4 land early.

These patterns are recorded (file, function, line range, evidence text) and passed to the AI as
structured context — the shrunk, honest version of the source's per-entity `ast_ops` list.

### 3.2 Failure-mode classes (3, down from the source's 6)

Source taxonomy: `MEM, UNINIT, INT_UB, LIFETIME, CONC, LOGIC`. V1 keeps the three the available
detectors can actually catch on a small program:

| Class | Meaning | Natural detector (off-the-shelf) |
|---|---|---|
| `MEM` | Out-of-bounds read/write, bad pointer/array access | **AddressSanitizer (ASan)** |
| `INT_UB` | Signed overflow, div-by-zero, invalid shift, lossy truncation | **UndefinedBehaviorSanitizer (UBSan)** |
| `LOGIC` | Wrong output vs. expected (no sanitizer fires) | **Existing unit tests** |

`UNINIT` (MSan), `LIFETIME` (C++), `CONC` (TSan + threads) are **deferred** (§4). The source already
marks MSan/TSan "unavailable" in its own environment, so this cut follows the source.

### 3.3 AI failure-mode inference + rule-based fallback (the "steering")

The AI is primary; a rule table is the deterministic guardrail. Both produce the same contract
(class + rationale), so they are interchangeable and comparable.

- **AI path (primary).** Prompt = change context (§3.1 patterns + changed function source + diff).
  Output = strict JSON `{"MEM":p, "INT_UB":p, "LOGIC":p, "rationale": "...", "suggested_inputs":[...]}`
  at temperature 0. Low-confidence (max prob < threshold) → escalate to running *both* matched
  sanitizers rather than guessing.
- **Rule-table fallback (guardrail / offline / CI-for-FIDO-itself).** The static map below; used when
  the LLM is unavailable or to unit-test the pipeline deterministically:

| Detected pattern | Risk class | Tools selected (in addition to the always-on floor) |
|---|---|---|
| P1 bounds/boundary change | `MEM` (+`INT_UB` if it feeds an index) | ASan build + existing tests + AI/prepared boundary inputs |
| P2 integer arithmetic change | `INT_UB` | UBSan build + existing tests + AI/prepared large-value inputs |
| P3 validation removed | `MEM` or `INT_UB` (by what was guarded) | ASan and/or UBSan, matched to the guard's target |
| P4 pointer/array op | `MEM` | ASan build + existing tests |
| (no risky pattern) | `NONE` | **floor only**: compiler warnings + existing unit tests |

**Always-on floor:** compile `-Wall -Wextra` and run the existing tests on *every* commit, regardless
of AI output — this is what makes it safe to let the AI drive.

### 3.4 The gatekeeper server + sandbox (the new v1 core)

- **Interception.** A **bare Git repository on the FIDO server with a `pre-receive` hook** is the
  simplest realistic "intermediate server": the developer sets FIDO as a remote and pushes to it; the
  hook receives the refs, checks out the pushed commits, and runs the pipeline **before deciding to
  accept**. (No need to build a full HTTP Git server for v1.)
- **Sandboxed execution.** Each build/run happens inside a **Docker container** with `--network none`,
  CPU/memory/PID limits, a wall-clock timeout, and a read-only mount of the checked-out commit — the
  concrete realization of the source's `runner.py` (rlimits + timeout) and its "Docker per-arm"
  note. A lighter `rlimit`-only subprocess mode is an acceptable documented fallback if Docker is
  unavailable in the grading environment.
- **The gate (push policy).** After triage, a configurable policy decides:
  - **block** if there is a **high-attribution** sanitizer finding (`MEM`/`INT_UB` inside changed
    lines) — the `pre-receive` hook exits non-zero and the push is rejected with the report;
  - **block or warn** on failing existing tests (`LOGIC`);
  - **allow** otherwise → FIDO **forwards the push to the real upstream** (`git push` mirror).
  Default = block-on-high-severity; an **advisory mode** (always allow, just report) is a config flag.

### 3.5 Executors kept in v1

- **Compiler-warning check** — `-Wall -Wextra` (optionally `-Wconversion`); keep warnings inside
  changed line ranges.
- **Sanitizer build + run** — CMake variant with `-fsanitize=address` or
  `-fsanitize=undefined -fno-sanitize-recover=all`, run on existing test inputs **plus the
  AI-generated (execution-validated) adversarial inputs**. Shrunk, honest version of the source's
  "generated boundary tests" arm — the AI proposes inputs, the sandbox judges them.
- **Existing unit-test runner** — run the whole (small) suite via CTest or a JSON manifest; the
  source's RTS arm without coverage-map selection.

### 3.6 Report (the deliverable per push)

Markdown + JSON (matching `docs/example_report_bic.md`), returned to the developer as the push
result, with five sections:
1. **What changed** — files, functions, detected structural patterns with evidence.
2. **What the AI concluded** — predicted class(es), the LLM's rationale, and the exact change context
   it was given (so the decision is auditable).
3. **What tools were selected and why** — the class→tool mapping plus the always-on floor.
4. **What the tools found** — each finding as `{tool, class, file:line, message}`, attributed to a
   changed line range (high if inside a changed hunk, else "pre-existing/low"), with the AI's triage
   note (incl. suspected-intentional-vs-genuine UB).
5. **Gate decision** — allow/block, which rule triggered it, and whether it was forwarded upstream.

---

## 4. Explicitly removed or deferred features

Everything below is present or specified in the source and is deliberately moved to future work.
**Note:** unlike the previous scope, the **LLM/AI is now core, not deferred** — only the *heavier*
research pieces are cut.

| Removed / deferred (source location) | Why it is not needed for Version 1 |
|---|---|
| **Trained ML classifier** (Tier-A GBDT, isotonic calibration) — `fido/predict/classifier.py` | The AI (LLM) + structural grounding covers classification for v1; a trained GBDT needs a labeled BIC corpus the project does not have. Future work. |
| **Budgeted planner: knapsack + bandit policies P0–P4, cost ledger, yield model** — `fido/plan/planner.py`, `fido/ledger.py` | With 3 tools on small programs, a class→tool rule (plus AI) is enough. CPU-second budgeting/optimization is future work. |
| **Directed/greybox fuzzing** (MiniFuzzer + AFLGo/WAFLGO adapters) — `fido/exec/fuzz.py` | A real directed fuzzer is a research project; v1 uses **AI-generated + hand-prepared** adversarial inputs instead. |
| **Concolic / symbolic execution** (QSYM adapter) — `fido/exec/concolic.py` | 10³–10⁵× overhead (source L10); needs a heavy engine; out of scope. |
| **Differential O0-vs-O2 build oracle** — `fido/exec/diffbuild.py` | Adds a second build matrix; defer to keep executors to three. |
| **History/churn (L4) & coverage DB (L5); call-graph affected-set (L2)** — `fido/change/extractor.py` | Cross-commit state / call-graph tooling; v1 works from the current diff and attributes to the changed function only. |
| **MSan / TSan (UNINIT, CONC classes)** | Need clang + instrumented deps / threaded targets; source marks them "unavailable." |
| **SZZ / bug-inducing-commit mining, large-scale GitHub mining, multi-repo datasets** (WAFLGO-30, OSS-Fuzz) — `eval/` | Power a research evaluation, not a prototype; v1 uses ~6 crafted commits (§7). |
| **Learning loop: EWMA yield + auto-labeling** — `fido/learn/loop.py` | Needs replay corpora + confirmed-bug feedback; no place in a term project. |
| **Replay harness + factorial experiment + A12 / Mann–Whitney / Holm stats** — `eval/replay.py`, RESEARCH §12 | Graduate-level methodology; v1 uses a qualitative correctness table (§7). |
| **Full HTTP Git server / multi-user auth / distributed CI** | The `pre-receive` hook on a bare repo delivers the gatekeeper behavior for one project without building a Git host. Multi-tenant hosting is future work. |
| **Production GitHub Actions integration** | v1's gate lives in the FIDO server itself; a GitHub App/Action is future work. |

---

## 5. Realistic implementation stack

| Layer | Choice | Rationale |
|---|---|---|
| Orchestration language | **Python 3** | Matches the existing `fido/` code; great for subprocess/JSON/HTTP glue. |
| Target language(s) | **C first, C++ optional** | The UB domain justifying the premise (source: "C/C++ first"). |
| **Gatekeeper server** | **Bare Git repo + `pre-receive` hook** (hook shells out to `python -m fido gate`) | Simplest genuine "intermediate server that gates the push"; no Git-host to build. Optional thin HTTP wrapper later. |
| **Sandbox** | **Docker** (`--network none`, `--memory`, `--cpus`, `--pids-limit`, timeout, read-only mount); `rlimit`+subprocess fallback | Concrete form of source `runner.py` / "Docker per-arm." Student-friendly and genuinely isolating. |
| **AI / LLM** | **Provider-agnostic client behind one interface** (`LLMClient.classify()`, `.generate_inputs()`, `.triage()`), JSON mode, temperature 0; a hosted API **or** a local model (e.g., via Ollama) | Keeps AI integral but swappable; temperature 0 + JSON schema keeps it auditable. Extends the source's `FIDO_LLM_CMD` hook. |
| AI fallback | **Deterministic rule table (§3.3)** when the LLM is unreachable/low-confidence | Graceful degradation; also lets FIDO's own tests run offline/deterministically. |
| Change extraction | **`git` via `subprocess`** + **`tree-sitter` (C/C++ grammar)** | Real AST access for "structure-aware" patterns, far lighter than clang/LLVM. Regex-on-changed-lines (source `extractor.py`) is a documented fallback. |
| Build system for targets | **CMake only** | One ubiquitous system; sanitizer variants via `CMAKE_C_FLAGS`. (Source currently compiles with gcc directly — moving the demo to CMake is a small v1 simplification.) |
| Detectors | **gcc/g++** `-Wall -Wextra`, `-fsanitize=address`, `-fsanitize=undefined -fno-sanitize-recover=all` | Already used/probed by `fido/exec/builds.py`. |
| Existing-test execution | **CTest** or a JSON `{stdin, expected_regex}` manifest (like source `tests/manifest.json`) | Reuses the demo test format. |
| Report | **Markdown + JSON** template | Matches `fido/report/report.py` / `docs/example_report_bic.md`. |
| FIDO's own tests | **pytest** | Each milestone in §6 is independently testable. |

**Dependencies stay modest:** Python stdlib + `tree-sitter` (+grammar) + one LLM client + `pytest`,
plus system tools (git, cmake, gcc, docker). No ML training libs, no fuzzers, no symbolic engines.

**Honest note on the LLM.** An LLM adds a network/cost dependency and some non-determinism; v1 tames
this with temperature 0, a strict JSON schema, execution-validation of anything the LLM suggests, and
the rule-table fallback. The AI **decides what to test and explains results; it never decides pass/fail
— the sandboxed tools do.**

---

## 6. Step-by-step implementation roadmap (small, independently testable milestones)

**M0 — Scaffold + CMake demo target.** Port the source's `calcstat` to a **CMake** project with a
CTest/manifest suite and a Git history of a few commits.
*Done when:* `cmake -S . -B build && cmake --build build && ctest` passes on the clean commit.

**M1 — Change extraction (structure-aware).** Repo + commit → `ChangeRecord`-lite: changed files,
hunks, and the function each changed line belongs to (tree-sitter). Keep source field names.
*Done when:* tests assert the correct changed function(s) and line ranges on a known commit.

**M2 — Structural pattern detection (P1–P4).** Implement the four detectors.
*Done when:* one crafted diff per pattern + a "no pattern" diff each yield the expected patterns.

**M3 — Sandbox executor.** A `run_in_sandbox(cmd, files, limits)` helper (Docker; rlimit fallback):
no network, CPU/mem/time caps, captured stdout/stderr/exit.
*Done when:* a deliberately infinite-loop / fork-bomb / network-calling program is contained and
killed within limits; a normal program returns its output.

**M4 — Executors on the sandbox.** (a) `-Wall -Wextra` build + warning parse; (b) ASan/UBSan CMake
build + run; (c) existing-test runner — all via M3.
*Done when:* on the bug-inducing commit the ASan build reports the OOB write and the UBSan build the
signed overflow, both inside the sandbox.

**M5 — AI classification (★AI★).** `LLMClient.classify(change_context)` → JSON class + rationale;
low-confidence escalation; **rule-table fallback** when the LLM is off.
*Done when:* with the LLM on, the bug-inducing commit → `MEM`+`INT_UB` with a sensible rationale;
with the LLM forced off, the fallback produces the same classes deterministically.

**M6 — AI adversarial input generation (★AI★).** `LLMClient.generate_inputs(class, changed_code)` →
candidate inputs; **each is executed in the sandbox** and kept only if it runs.
*Done when:* for the integer-overflow commit the AI proposes an input that makes UBSan fire; if it
doesn't, the prepared-input fallback does.

**M7 — Findings + AI triage + attribution.** Normalize tool output to
`{tool, class, file:line, message}`; attribute to changed ranges; `LLMClient.triage()` adds the
human-readable note + intentional-vs-genuine UB flag.
*Done when:* OOB + overflow attributed **high** to changed `main`; an injected untouched-code warning
attributed **low**; the hash-idiom commit's UB flagged "suspected intentional."

**M8 — Gatekeeper server + gate policy.** Bare repo + `pre-receive` hook calling `python -m fido gate`;
policy blocks on high-severity, else forwards to a configured upstream.
*Done when:* pushing the bug-inducing commit to FIDO is **rejected** with the report; pushing the fix
is **accepted and mirrored** to the upstream repo.

**M9 — Structured report + end-to-end demo.** Render the five report sections (§3.6); a script drives
the full push→gate→report→forward flow over the demo history.
*Done when:* the demo commit set (§7) each produces the expected classification, tool selection,
findings, and gate decision.

**M10 (optional stretch) — Thin HTTP status page / GitHub App.** A small web view of past pushes and
reports, or a GitHub App wrapper. Clearly optional.

---

## 7. Evaluation / demo plan (small, deliberate)

Reuse and lightly extend the source's `calcstat` demo (`scripts/setup_demo.sh`) — it already contains
a **real bug-inducing commit** and a matched fix. Prepare ~6 commits, each pushed **through the FIDO
gateway** so the gate decision is part of the demo.

| Commit (pushed) | Pattern → class | Expected FIDO behavior | Finding & gate |
|---|---|---|---|
| C1 initial (bounded, `long long`) | none → `NONE` | floor only | no findings → **allow → forwarded** |
| C2 add `variance` (guarded) | new fn, no risky pattern → `LOGIC`/`NONE` | floor + tests | tests pass → **allow** |
| **C3 bug-inducing** (drop bound + narrow `total`) | P1+P2 → `MEM`+`INT_UB` | AI picks **ASan+UBSan**, generates overflow/overflow-count inputs | ASan OOB + UBSan overflow, attributed **high** → **BLOCK** with report |
| C4 the fix | none → `NONE` | floor only | no findings → **allow → forwarded** (no false alarm on a fix) |
| C5 remove a validation guard (crafted) | P3 → `MEM`/`INT_UB` | AI selects the matched sanitizer | sanitizer fires only on the exercised path → **block** |
| C6 pure refactor/rename (behavior-preserving) | none → `NONE` | floor only | tests pass, no findings → **allow** (false-positive control) |

**What the demo shows (the thesis, at small scale):**
1. **AI-driven correct steering** — FIDO/AI picks the sanitizer matching the structural change.
2. **The gate works** — risky pushes are blocked *before* reaching the upstream repo; safe ones pass.
3. **No wasted work / no false alarms** — clean/fix/refactor commits run only the cheap floor and are
   allowed.
4. **Attribution & explanation** — findings are tied to changed lines and explained by the AI triage.

**Simple quantitative summary (no advanced statistics):**
- **Steering accuracy:** how often the selected tool set is the minimal correct set (target: 6/6).
- **Gate accuracy:** blocks all buggy commits (C3, C5), allows all safe ones (C1, C2, C4, C6).
- **AI-vs-fallback agreement:** run each commit with the LLM on and off; report where they agree (a
  cheap, honest way to show the AI is grounded, not hallucinating).
- **Work avoided (illustrative):** FIDO's selected tool-runs vs. a "run-everything" baseline — a small
  table, **not** a benchmarked bugs-per-CPU-hour claim.

This deliberately avoids the source's factorial `{policy}×{budget}×{≥20 seeds}` design and its
A12/Mann–Whitney/Holm statistics.

---

## 8. Optional future extensions (clearly separated from the core project)

1. **More patterns & classes** — P5 (weakened conditional), then `LIFETIME` (C++ iterator/use-after-move).
2. **Differential build oracle (A5)** — `-O0` vs `-O2` to catch optimizer-elided UB ("Don't Look UB").
3. **Real directed fuzzing** — replace AI/prepared inputs with a fuzzer via `FIDO_AFLGO_CMD`.
4. **Trained classifier** — swap/augment the LLM with a GBDT behind `ModelContract` on a labeled corpus.
5. **Budget-aware planner** — re-introduce the cost ledger + P1/P2 allocation once arms multiply.
6. **Call-graph affected-set (L2) + history/coverage (L4/L5)** — cross-function targeting/attribution.
7. **Learning loop** — EWMA yield + auto-labeling from confirmed fixes (source `learn/loop.py`).
8. **Full multi-user Git host / GitHub App** — beyond the single-project `pre-receive` gateway.
9. **Research evaluation** — replay harness, BIC datasets, factorial/statistical methodology
   (RESEARCH §12) — the path from prototype to paper.

---

## Appendix — Traceability to the source branch

| V1 element | Source it is distilled from |
|---|---|
| Central "change → failure-mode → steer tool" spine | README pipeline; SYSTEM_ARCHITECTURE §1; RESEARCH gap **G2 (+G1)** |
| **Gatekeeper server / pre-push trigger** | SYSTEM_ARCHITECTURE §1 "CI TRIGGER LAYER: push/PR webhook → snapshot commit" — v1 **reframes** this as a pre-receive gateway that *gates* the push (the gating-before-upstream framing is new) |
| **Sandboxed execution** | `fido/exec/runner.py` (rlimits + wall timeout); "Docker per-arm in production" |
| **AI classification (★)** | `fido/predict/classifier.py` Tier-B LLM (`LLMJudge`, `FIDO_LLM_CMD`) — promoted from optional to core |
| **AI adversarial input generation (★)** | `fido/exec/gen.py` (LLM codegen hook behind `FIDO_LLM_CMD`); LIBRO precedent |
| **AI triage / intentional-UB flag (★)** | `fido/triage/triage.py` (intent filter; AI-assisted triage hook) |
| Failure-mode classes `MEM/INT_UB/LOGIC` | SYSTEM_ARCHITECTURE §3.1 taxonomy (subset of 6) |
| Structural patterns P1–P5 | `fido/change/extractor.py` risk lexicon (L3) `ADD_OPS`/`REMOVE_OPS` |
| Rule-table fallback (replaces knapsack planner) | `fido/plan/planner.py` (`UTILITY`, `SANITIZER_FOR_CLASS`) |
| ASan/UBSan variants via CMake | `fido/exec/builds.py` (`SAN_FLAGS`, sanitizer probe) — v1 adds CMake |
| Existing-test / adversarial-input runners | `fido/exec/rts.py`, `fido/exec/gen.py` |
| Findings + attribution + report | `fido/triage/triage.py`, `fido/report/report.py`, `docs/example_report_bic.md` |
| `calcstat` demo commits | `scripts/setup_demo.sh` |
| Everything in §4 "deferred" | `fido/exec/{fuzz,concolic,diffbuild}.py`, `fido/learn/loop.py`, `fido/ledger.py`, `eval/replay.py`, RESEARCH §12–§15 |

**Honest notes on what the source does *not* already support:** (1) the source has **no gatekeeper
server** — its top layer is a conceptual CI-trigger box; the pre-receive-gateway-that-blocks-pushes is
a v1 design decision. (2) The source **compiles with gcc directly, not CMake** — adopting CMake is a
v1 recommendation. (3) The LLM hooks (`FIDO_LLM_CMD`) exist but are **disabled by default** in the
source; v1 makes AI a required, first-class stage (with a deterministic fallback so it stays testable).
(4) MSan/TSan (and thus `UNINIT`/`CONC`) are marked *unavailable* in the source, so v1's omission
follows the source.
