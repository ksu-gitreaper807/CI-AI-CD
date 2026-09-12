# Replay Walkthrough — FIDO on the demo repository

The demo project (`scripts/setup_demo.sh`) has a six-commit history containing a real
bug-inducing commit (BIC), its fix, an intentional-wraparound gray zone, and a
magic-guarded defect. Replaying every commit with an equal 300s budget
(`python3 -m eval.replay /tmp/fido-demo/calcstat --budget 300 --policy p4`) produces:

| commit | change | top predicted class | findings (change-attributed) | high-attribution | budget spent |
|---|---|---|---|---|---|
| 60a599eb | add variance (clean) | LOGIC 0.46 | none | 0 | 1.9s |
| b0f88df | **bug-inducing commit** (unbounded write + int narrowing) | **INT_UB 0.41** | **MEM + INT_UB** | **2** | 0.26s |
| 11cea94 | fix commit (restore bounds + long long) | LOGIC 0.46 | none (detection turns off after the fix) | 0 | 1.9s |
| a7cc262 | hash combine (signed-shift UB inside a hash idiom) | LOGIC 0.58 / INT_UB 0.27 | INT_UB, intent = *suspected intentional (hash idiom)* | 1 | 0.18s |
| d41eb12 | magic-value backdoor (deep guard; dormant UB behind `0x5F3759DF`) | LOGIC 0.46 | none + **deep-guard trigger fired** | 0 | 0.06s |


## What each row demonstrates

1. **Clean commits produce no findings.** The variance and fix commits run the full
   pipeline (RTS + fuzzing + generation + differential) and report nothing — the
   false-positive rate of the end-to-end system on this history is zero.
2. **The BIC is caught by two different arms, both steered by the prediction.**
   The commit changed `long long total` to `int total` (a *type narrowing* on an added
   line — the overflowing `total += x` line itself is unchanged, so purely line-based
   tools see nothing) and removed the input bound. The classifier puts INT_UB on top;
   the plan steers UBSan/ASan builds and boundary generation. Result: the fuzzer finds
   the OOB write (`main.c:10`) and a *generated* boundary input (`2147483647 2147483647`)
   finds the signed overflow (`main.c:11`). Both attributed **high** (changed entity +
   line range).
3. **The fix commit switches detection off again** — the same executors now find
   nothing, demonstrating the findings are change-attributed, not ambient.
4. **The intent filter discriminates real UB from idiom-context UB.** The hash commit's
   signed-shift overflow is flagged `suspected_intentional (hash idiom)` — the filter
   reads the *source context at the offending commit* (`0x9e3779b9` boost-style combine),
   while the BIC's overflow in accumulator code stays `suspected_genuine`. This encodes
   the IOC finding (Dietz et al., TOSEM 2015) that intentional wraparound is common and
   naive UB reporting drowns developers in false alarms.
5. **Argmax prediction is imperfect but distribution-level steering absorbs it.** On the
   hash commit, LOGIC edges out INT_UB in the argmax; the planner nevertheless allocates
   to INT_UB-sensitive arms because it consumes the full calibrated distribution — and
   the UB is found. This is a deliberate design property (soft steering, floors and
   caps), not luck.
6. **The deep-guard trigger documents what mutation fuzzing cannot reach.** The magic
   commit plants UB reachable only through input `0x5F3759DF` (1597463007) — outside
   the fuzzer's reachable value set by construction. The trigger fires statically and
   the report states that a concolic engine is required; with `FIDO_CONCOLIC_CMD`
   configured, that arm would be scheduled. This is the honest demonstration of the
   concolic allocation gap the architecture (Arm A4) exists to fill.
7. **Spent column:** all rows are far under budget on this 60-line target — budget
   *differentiation* between policies cannot be demonstrated on a target where every
   arm costs <2s. That measurement requires the E2 experiment plan on real subjects
   (`research/RESEARCH_REPORT.md` §12); what this replay demonstrates is the causal
   chain and its switches, at real sanitizer-level execution.

## Honest limitations visible in this walkthrough

- Prediction-level false positives exist (variance commit: top class LOGIC with no
  findings — harmless here because steering is soft, but per-class precision on real
  histories is exactly what E1 must measure before any deployment claim).
- The demo's fuzzer is a grammar-biased integer generator; on real targets the AFLGo
  adapter (`FIDO_AFLGO_CMD`) replaces it.
- Diff extraction is heuristic (regex lexicon + function-range scan); the doc comment
  false-positive suppression (`strip_comments`, float-line guard) is exactly the kind of
  precision engineering that tree-sitter/GumTree would replace in production.
