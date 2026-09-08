# Research Report: AI-Assisted, Change-Aware CI/CD Testing
## Systematic Literature Analysis and Research Problem Formulation

**Prepared:** 2026-09-08 | **Method:** evidence-first literature mapping across 8 domains → limitations → intersections → gap formulation → red-team validation → problem statement. Claims carry inline citations; inferences are explicitly labeled **[INFERRED]**. Papers are tagged [Foundational], [Influential], or [Recent].

---

## 0. Executive Summary

The proposed direction — an AI-assisted, change-aware CI/CD testing framework — decomposes into eight well-developed research domains. The red-team search found that several sub-capabilities of the original idea **already exist and are published**: change-directed fuzzing (Katch FSE'13; AFLGo CCS'17; AFLChurn CCS'21; CIDFuzz IET-Soft'23; WAFLGO USENIX-Sec'24), sanitizer-guided fuzzing (ParmeSan USENIX-Sec'20; SAVIOR S&P'20), LLM-based test generation (TestPilot ICSE'24; CodaMosa ICSE'23; LIBRO ICSE'23), and ML-based predictive test selection deployed in industry (Machalica et al. ICSE-SEIP'19). Therefore the idea as stated is **not novel**.

What the evidence supports as genuinely weakly explored is the **decision problem between techniques**: every surveyed system either (a) selects among *existing* tests, (b) directs *one* technique (fuzzing) at changed code, or (c) generates tests with *no awareness of the change*. No peer-reviewed system found in this survey classifies the *likely failure-mode class* of a semantic code change and uses that prediction to *steer the choice of sanitizer, oracle, and input-generation strategy* under a CI compute budget. The recommended research problem (Gap G2/G1 composite) targets exactly this, is experimentally measurable, and has public datasets and strong single-technique baselines (WAFLGO, CIDFuzz, AFLChurn, predictive test selection) against which it can be evaluated. **Novelty confidence: Medium** (integration-heavy; the measurable innovation must be the change→failure-mode conditioning signal, not the pipeline plumbing).

---

## 1. Initial Research Direction

> "An AI-assisted, change-aware CI/CD testing framework that analyzes pushed code changes, identifies likely failure modes, and adaptively selects or generates testing strategies for edge cases, undefined behavior, fuzzing, regression testing, and other relevant program-analysis techniques."

### Phase 1 — Decomposition into research domains
- **Domain A** — Automated software testing (test generation, RTS, prioritization, minimization, adaptive testing)
- **Domain B** — AI/LLM-based software testing
- **Domain C** — Fuzzing (coverage-guided, directed, grammar/structure-aware, ML/LLM-assisted)
- **Domain D** — Undefined behavior & runtime error detection in C/C++ (sanitizers, dynamic/static analysis)
- **Domain E** — Change-aware / diff-aware analysis (impact analysis, risk prediction, bug-inducing commits)
- **Domain F** — Symbolic & concolic execution
- **Domain G** — Differential & metamorphic testing
- **Domain H** — Mining software repositories (bug history, defect prediction)

---

## 2. Literature Landscape

### 2.1 Domain A — Automated software testing & CI regression testing

**Cluster A1: Regression test selection (RTS) and its safety/precision trade-off.**
- **[A1] Ekstazi** — "Practical Regression Test Selection with Dynamic File Dependencies," Bell, Kaiser, Mok, ISSTA 2014. [Influential]. Selects tests by per-class file dependencies tracked dynamically. Deployed and validated on 985 revisions / 22 projects in follow-ups ([Cornell static-RTS study](https://www.cs.cornell.edu/~legunsen/pubs/LegunsenETAL16StaticRTSStudy.pdf)). Solves: cheap (class-level) selection with low safety violations vs. finer-grained analysis ([Ekstazi overview](https://www.researchgate.net/publication/308869790_Ekstazi_Lightweight_Test_Selection)). Does NOT solve: no test *generation*, no semantic reasoning about the change, selection only among existing tests.
- **[A2] STARTS / static RTS study** — Legunsen et al., "An Extensive Study of Static Regression Test Selection in Modern Software," ISSTA 2017 ([PDF](https://www.cs.cornell.edu/~legunsen/pubs/LegunsenETAL16StaticRTSStudy.pdf)). Class-level static RTS comparable to Ekstazi in speed but "at the risk of being unsafe sometimes"; method-level RTS "performs rather poorly" (safety violations up to 10.6% avg); reflection breaks static call graphs. Explicit limitation: "any RTS technique can be simply made faster by not selecting to run some tests, but then it risks missing regressions."
- **[A3] Empirical comparison of four Java RTS tools** — J. Syst. Softw. 2021 ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0164121221002582)). Found: average fault-detection ability of RTS-selected suites was **8.75% lower** than the full suite; tools differ significantly in safety/precision violations. This is direct evidence that selection alone loses fault-detection power.
- **[INFERRED LIMITATION]** All RTS families (static, dynamic, hybrid — see also the survey discussion in [1](https://www.sciencedirect.com/science/article/abs/pii/S0164121221002582)) operate on *existing* tests and dependency graphs; none reasons about *what kind of new adversarial inputs* a change deserves.

**Cluster A2: ML-based / predictive test selection & prioritization in CI (industrial).**
- **[A4] Predictive Test Selection** — Machalica, Samylkin, Porth, Chandra (Meta/Facebook), ICSE-SEIP 2019 ([arXiv:1810.05286](https://arxiv.org/pdf/1810.05286)). [Influential]. Gradient-boosted classifier over change×test features predicts failures; halves infrastructure cost while catching >95% of individual failures and >99.9% of faulty changes. Limitations (author-discussed): flaky-test labels contaminate training; model selects only from existing tests; recall ceiling <100% is an accepted risk.
- **[A5] Targeted Test Selection (T-TS)** — 2025, industrial deployment ([arXiv:2509.10279](https://arxiv.org/html/2509.10279v1)). Selects 15% of tests, detects >95% of failures on live industrial data; no coverage maps needed (commit-level features + hierarchical distance). Still: selection among existing tests only; inference budget <1 min per change.
- **[A6] RETECS** — Spieker, Gotlieb, Marijan, Mossige, ISSTA 2017 ([PDF](https://hspieker.de/files/Spieker_et_al._-_2017_-_Reinforcement_Learning_for_Automatic_Test_Case_Prioritization_and_Selection_in_Continuous_Integration.pdf)). [Influential]. Reinforcement learning for adaptive test prioritization/selection; reward from failure history, execution recency, duration; three industrial case studies. Limitation: "adapts only within fixed parameters and a single environment" (as characterized by follow-up work), and again — existing tests only.
- **[A7] DeepOrder** — deep-learning RTP for CI ([arXiv:2110.07443](https://arxiv.org/pdf/2110.07443)); shows limited test history decreases fault-detection effectiveness of prioritization. **[A8]** Comparative ML study of TCP under CI time budgets ([ResearchGate](https://www.researchgate.net/publication/360186507_Comparative_Study_of_Machine_Learning_Test_Case_Prioritization_for_Continuous_Integration_Testing)): different ML models win at different history lengths/budgets — configuration sensitivity is a recurring issue.

**Cluster A3: Industrial-scale CI testing reality.**
- **[A9] Taming Google-Scale Continuous Testing** — Memon et al., ICSE-SEIP 2017 ([PDF](https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/45861.pdf)). [Influential]. Google cannot regression-test each change; only **1.23% of test executions find a breakage/fix**; flakiness prevents "rerun recent failures" heuristics; goal stated as improving "the ratio of change (fault or fix) detection per unit of compute resource spent." This paper articulates the *defect-discovery-per-compute* objective that the present research problem adopts.
- **[A10] Flaky tests** — large-scale longitudinal study, OOPSLA 2020 ([jonbell.net](https://jonbell.net/publications/oopsla20flaky)): 684 potentially flaky tests in 55 projects; flakiness is pervasive and undermines selection/reliability. Apple: "Modeling and ranking flaky tests at Apple," ICSE-SEIP 2020.
- **[A11] Test amplification (DSpot)** — Danglot et al. survey, 2019; DSpot amplifies developer tests (assertion addition, input mutation) ([overview](https://arxiv.org/html/2108.12249)). Relevant because it is the closest thing to "improving existing tests," but amplification is **not change-conditioned**.

### 2.2 Domain B — AI / LLM-based software testing

**Cluster B1: LLM unit-test generation — capable but unreliable, function-level not change-level.**
- **[B1] TestPilot** — Schäfer et al., ICSE 2024 ([repo](https://github.com/githubnext/testpilot)). [Recent]. LLM (Codex-class) generates Java package tests, validated via build+run, iterating on error messages. Evaluation on 25 npm/Java repos reported strong coverage gains. Limitations: needs compilable context; refinement depends on system-specific error messages (reproduction issues documented in the repo); operates per *function/class*, not per *commit*.
- **[B2] CodaMosa** — Lemieux, Inala, Lahiri, Sen, ICSE 2023 (cited as `lemieux2023codamosa` in the [LLM test-gen survey](https://arxiv.org/html/2511.21382v2)). [Recent]. Hybrid: invokes LLM to generate seeds when search-based generation stalls ("coverage stagnation"), escaping local optima. Limitation: coverage-driven trigger, no change conditioning, no failure-mode reasoning.
- **[B3] LIBRO** — Kang, Yoon, Yoo, ICSE 2023 ([arXiv:2209.11515](https://arxiv.org/abs/2209.11515)). [Recent]. LLM generates *bug-reproducing tests from natural-language bug reports*; succeeds for 33% (251/750) of Defects4J bugs (32% on post-training-cutoff reports). Important precedent: **LLMs can produce executing, failure-revealing tests when conditioned on a failure description** — but the conditioning input is a bug report, *not a code change*.
  - Follow-up robustness study ([arXiv:2510.05365](https://arxiv.org/html/2510.05365)): performance drops >60% under identifier mutations; benchmark-quality issues documented.
- **[B4] Industrial LLM ATG at Meta** — Alshahwan et al. (2024/2025): generated Kotlin tests, 76% of compiled tests passed reliably across five executions after flakiness filtering (reported in the flakiness study below).
- **[B5] Flakiness of LLM-generated tests (DBMS/C++)** — [arXiv:2601.08998](https://arxiv.org/html/2601.08998v1) (2026): "LLMs struggle to produce compilable C++ code"; "the prevalence of flaky tests was often higher than in existing tests"; compilation success collapses on large closed-source C++ (SAP HANA). Direct evidence of reliability limits for the "AI generates tests" component in C/C++.
- **[B6] LLM unit-test-generation surveys** — [arXiv:2511.21382](https://arxiv.org/html/2511.21382v2) (2025): prompt engineering dominates (89% of studies); "symbol not found" errors up to 43.6% of compilation failures; "context management dilemma... remains an open problem"; coverage drops on complex logic. [arXiv:2511.20403](https://arxiv.org/pdf/2511.20403): pipelines for end-to-end assessment; zero-shot compilation success ~9.8% vs human 100% in their setting.
- **Answer to Phase-1 question (does AI understand changes?):** **[INFERRED, strongly supported]** surveyed LLM test generation is conditioned on *whole functions, classes, bug reports, or documentation* — no surveyed system generates tests conditioned on the *semantic delta of a commit* and its likely failure modes.

### 2.3 Domain C — Fuzzing

**Cluster C1: Change-directed / patch-directed fuzzing (the critical red-team cluster).**
- **[C1] KATCH** — Marinescu & Cadar, FSE 2013 ([PDF](https://srg.doc.ic.ac.uk/files/papers/katch-fse-13.pdf)). [Foundational for change-aware testing]. Symbolic execution (on KLEE) + patch-distance heuristics (greedy exploration, informed path regeneration, definition switching) to reach patch code; applied to six years of patches in 19 GNU programs; "find bugs at the moment they are introduced." Limitations: symbolic execution scale; authors call for full SDLC integration.
- **[C2] AFLGo** — Böhme, Pham, Nguyen, Roychoudhury, "Directed Greybox Fuzzing," CCS 2017 ([PDF](https://mboehme.github.io/paper/CCS17.pdf)). [Influential]. Simulated-annealing power schedule over inter-procedural *distance-to-target*; explicitly demonstrated **patch testing** (outperformed Katch in patch coverage and bug finding) and integrated into OSS-Fuzz toolchain. Limitations (shown in later work): harmonic-mean aggregation of many targets "overlooks certain targets"; reaching a target ≠ exercising it ("after reaching the target, AFLGo does not pay much attention to testing the affected code" — [WAFLGO](https://www.usenix.org/system/files/sec24summer-prepub-301-xiang-yi.pdf)).
- **[C3] Regression Greybox Fuzzing / AFLChurn** — Zhu, Böhme et al., CCS 2021 ([PDF](https://mboehme.github.io/paper/CCS21.pdf)). [Influential]. Motivating stat: **~77% of OSS-Fuzz bug reports are regressions** (bug-introducing commit identifiable), rising to 92% for mature projects. Fuzzer allocates energy to code that changed recently/often ("churn"), not to a specific commit; 3+ CPU-years on FuzzBench; finds regressions ~1.5× faster than AFL. Limitation: churn is a weak proxy — not semantic, not per-commit.
- **[C4] CIDFuzz** — IET Software 2023 ([via awesome-directed-fuzzing](https://github.com/strongcourage/awesome-directed-fuzzing)). CI-oriented: change points become taint sources; static distance computation; resource allocation by seed coverage. Time to cover change points reduced 39.6% vs AFL, 41.6% vs AFLGo. Limitations: single technique (fuzzing); change points identified syntactically; small evaluation (4 projects).
- **[C5] WAFLGO** — Xiang et al., USENIX Security 2024 ([PDF](https://www.usenix.org/system/files/sec24summer-prepub-301-xiang-yi.pdf)). [Recent, strongest baseline]. Commit-directed DGF with "critical code" guidance (path-feasibility + fault-relevant code) to *thoroughly exercise affected code*, not merely reach change sites; dataset of 30 real bugs with manually identified bug-inducing commits; 7 new bugs incl. 4 CVEs; 8× faster than AFLChurn. Limitations (authors/discussion): target identification is still syntactic/dependency-based; explicitly lists "semantic knowledge... for more accurate identification of affected code" as future work; evaluation budgets are hours, not CI minutes.
- **[C6] Open problems acknowledged in 2024** — two Fuzzing'24 registered reports: "Effective Fuzzing within CI/CD Pipelines" (distance computation "often expensive, making the techniques impractical for short CI/CD runs") and "Directed or Undirected: Investigating Fuzzing Strategies in a CI/CD Setup" ([listings](https://github.com/strongcourage/awesome-directed-fuzzing)). **Evidence that CI-budget change-directed fuzzing is an active, unresolved question as of 2024.**
- Adjacent: **FuzzGuard** (USENIX-Sec'20, deep-learning reachability filtering, up to 17.1× AFLGo speedup), **BEACON** (S&P'22, provable path pruning), **TOFU**, **AFLRUN**, **Locus** (arXiv'25, agentic predicate synthesis) — all improve *directed* fuzzing efficiency but none are change-conditioned except via target list.

**Cluster C2: Coverage-guided + ML/LLM-assisted fuzzing.**
- **[C7] Fuzz4All** — Xia, Paltenghi, Tian, Pradel, Zhang, ICSE 2024 ([arXiv:2308.04748](https://arxiv.org/html/2308.04748v3)). LLM as universal fuzzer front-end with autoprompting; targets evolving languages. Author-acknowledged limitation: LLM inference bottleneck → **43% fewer inputs** than traditional fuzzers; hallucination risk; coverage not commit-aware.
- **[C8] LLM fuzzing ecosystem** — TitanFuzz (ICSE'23, DL-library fuzzing), FuzzGPT (valid fuzz-driver rates only **17–27%**), ChatAFL (CCS'24, protocol fuzzing with LLM), ISC4DGF (LLM-generated initial corpora for DGF, 35.6× faster target reach) — synthesized in [LLM4Fuzz vision paper](https://www.alphaxiv.org/abs/2503.00795) and [MDPI review 2026](https://www.mdpi.com/2076-3417/16/10/5160). Recurring limitations (from the MDPI review, §7): "absence of reliable semantic filters that connect generated artifacts to target behavior"; "LLM-based fuzzing adds a priced inference loop to a testing technique whose strength normally comes from cheap, high-frequency execution"; GPU/CPU architectural mismatch; weak reproducibility.
- **[C9] DNN+CGF survey** — Inf. Softw. Technol. 2025 ([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0950584925001363)): "semantically invalid seeds, high computational overhead, and limited cross-domain adaptability remain unresolved"; names LLM-powered fuzzing and neurosymbolic integration as the two transformative directions (both *open*).

### 2.4 Domain D — Undefined behavior & runtime error detection (C/C++)

**Cluster D1: Sanitizer capabilities and their structural limits.**
- **[D1] Sanitizer tool set** — ASan/UBSan/MSan/TSan: compiler-instrumented dynamic oracles ([Clang UBSan docs](https://releases.llvm.org/15.0.0/tools/clang/docs/UndefinedBehaviorSanitizer.html)). UBSan covers signed overflow, integer div-by-zero, invalid shifts, null deref, misaligned pointer use, vptr/lifetime checks, pointer overflow, VLA bounds; **not** all UB (e.g., float-div-by-zero excluded since IEEE-defined; no uninitialized-memory read detection — that is MSan, which requires recompiling *all* dependencies). Teaching/reference sources confirm: "no one tool catches everything" ([e.g., Cambridge lecture notes](https://www.cl.cam.ac.uk/~nk480/C1819/lecture5.pdf)).
- **[D2] Execution-conditionality (the core limitation)** — sanitizers only fire on *executed* paths. AFLChurn's OSS-Fuzz analysis shows the fuzzer+sanitizer portfolio still misses regressions for hours–days (CCS'21, above). **[INFERRED]**: sanitizer effectiveness = sanitizer coverage × input reachability; the input-generation problem is the bottleneck, which is exactly what change-aware input generation addresses.
- **[D3] Overhead and portfolio cost** — measured in [Sand (arXiv:2402.16497)](https://arxiv.org/html/2402.16497v1): ASan slows fuzzing ~3.6×, UBSan ~2×, MSan ~46×; sanitizers are mutually incompatible (shadow-memory conflict), so a *portfolio* multiplies cost ([Expozzer](https://par.nsf.gov/servlets/purl/10302100) lists incompatibility, overhead, false positives, non-exploitability as four inherent limits). [ReZZan, ASE 2022](https://www.comp.nus.edu.sg/~gregory/papers/rezzan.pdf): ASan at 2.36× in fork-mode fuzzing. **Implication [INFERRED]: choosing *which* sanitizer(s) to run per change is a real, quantifiable decision problem — nobody in the surveyed literature makes it change-conditioned.**
- **[D4] Optimizer–sanitizer interaction** — "Don't Look UB: Exposing Sanitizer-Eliding Compiler Optimizations," PLDI 2023 ([PDF](https://download.vusec.net/papers/dontlookub_pldi23.pdf)): at -O1, sanitizers failed to detect all three motivating bugs because optimizations elide sanitizer checks; UB is "the premier source of software vulnerabilities." Evidence that naive "compile with sanitizer + run tests" can silently miss real UB.
- **[D5] UB prevalence & intent ambiguity** — Dietz, Li, Regehr, Adve, "Understanding Integer Overflow in C/C++," TOSEM 2015 ([PDF](https://wdtz.org/files/tosem15.pdf)). IOC dynamic checker: 35% of top Debian packages triggered integer overflows; **16% invoked undefined integer behavior** using only the package's own test suite; intentional wraparound is common (>200 sites in SPEC CINT2000). Consequence for any automated UB detector: classification of *bug vs intentional* needs context — a failure-mode classifier must be calibrated per class.
- **[D6] Sanitizer-guided fuzzing (fuzzing×UB intersection)** — **ParmeSan**, USENIX Security 2020 ([paper](https://www.usenix.org/system/files/sec20-osterlund.pdf)): uses sanitizer instrumentation points as *fuzzing targets* (bug-coverage oriented, sanitizer-agnostic, DFA-based); finds bugs 37% faster than Angora, 288% faster than AFLGo. **SAVIOR**, IEEE S&P 2020 ([arXiv:1906.07327](https://arxiv.org/abs/1906.07327)): *bug-driven* hybrid testing — prioritizes concolic seeds by bug potential, models 6 UB categories as SMT constraints ("bug-guided verification"), 43.4% faster than Driller, 44.3% faster than QSYM; 481 UBSan violations on well-fuzzed programs within 24h, 243 real. **These solve "which inputs reach bug checks" globally, not per-change.** (CI/change-conditioned combination not found.)

### 2.5 Domain E — Change-aware / diff-aware analysis

- **[E1] GumTree** — Falleri et al., ASE 2014 ([HAL PDF](https://hal.science/hal-01054552/document)). [Foundational]. Fine-grained AST differencing with move detection; the standard substrate for semantic-ish diffs (scalability variants continue: HyperDiff, IEEE/ACM 2024).
- **[E2] SEMCIA** — Hanam et al., ICSME 2019 ([PDF](https://www.cs.ubc.ca/~rtholmes/papers/icsme_2019_hanam.pdf)). [Influential]. Semantic (not syntactic) change-impact relations for JavaScript; Unix-diff-based impact sets contain **23–49% false-positive dependencies** vs AST-diff criterion; semantic splitting reduced impact-set size 19–91%. Crucial evidence that *syntactic* change analysis is noisy and *semantic* change analysis measurably improves precision — yet SEMCIA targets developer *comprehension*, not test selection/generation.
- **[E3] SZZ** — Śliwerski, Zimmermann, Zeller, IWPSE 2005. [Foundational]. Maps bug-fix commits to bug-inducing commits (BICs) via blame. Known unfixable-ish problems: **ghost commits** (fix commits that add-only lines are untraceable) — quantified in Rezk et al., TSE 2021 ([PDF](https://rebels.cs.uwaterloo.ca/papers/tse2021_rezk.pdf)) — and cross-file/ghost cases make "nearly one-quarter of bug-inducing commits inherently untraceable" ([AgentSZZ, arXiv 2026](https://arxiv.org/html/2604.02665); recall of best variants ~0.552 on Linux kernel).
- **[E4] JIT defect prediction** — Kamei et al., "A Large-Scale Empirical Study of Just-in-Time Quality Assurance," IEEE TSE 2013: change-level risk from Size/Diffusion/History/Author/Reviewer features (68% accuracy, 64% recall). Longitudinal follow-up: McIntosh & Kamei, TSE 2016 ("are fix-inducing changes a moving target?" — yes, models decay). **Extrinsic-bug problem** ([arXiv:2103.15180](https://arxiv.org/pdf/2103.15180)): bugs without identifiable BICs degrade JIT feature importance; JIT predicts *riskiness*, not *failure mode*.
- **[E5] Entity-level semantic diff tooling** — emerging industry tooling (e.g., [`sem`](https://github.com/Ataraxy-Labs/sem): tree-sitter entity-level diffs, impact, co-change pairs, "built for coding agents") shows the plumbing for semantic diff is commercially available — **[INFERRED]** the research question is what *decision logic* to put on top, not whether diffs can be computed.

### 2.6 Domain F — Symbolic & concolic execution

- **[F1] KLEE** — Cadar, Dunbar, Engler, OSDI 2008. [Foundational]. Symbolic execution for real C programs with constraint caching; the substrate of Katch.
- **[F2] SAGE** — Godefroid et al., whitebox fuzzing, CACM 2012. [Foundational]. Generational search; deployed at Microsoft; mitigates path explosion via generational search and constraint solving.
- **[F3] QSYM** — Yun et al., USENIX Security 2018 ([PDF](https://www.usenix.org/system/files/conference/usenixsecurity18/sec18-yun.pdf)). [Influential]. Fast concolic engine tailored to hybrid fuzzing (dynamic binary translation, instruction-level selective symbolic execution, optimistic solving). Documents the scale problem: KLEE ~3,000× slower than native; angr >321,000× slower *even without path explosion* (emulation overhead, per the Georgia Tech dissertation building on QSYM). Hybrid fuzzers "still suffer from scaling to non-trivial, real-world applications."
- **[F4] Hybrid/compositional variants** — Munch ([arXiv:1711.09362](https://arxiv.org/pdf/1711.09362)) and Wildfire ([arXiv:1903.02981](https://arxiv.org/pdf/1903.02981)): fuzzing + *targeted* symbolic execution outperforms either alone; Wildfire shows AFL+KLEE fail on format-structured inputs (bzip2) that compositional targeting solves. **[INFERRED]**: concolic execution is *occasionally* the right per-change tool (deep guards, magic constants) but its cost profile forbids running it always — an allocation problem.
- AI-prioritized path exploration: only early-stage evidence found (K-Scheduler-style graph heuristics; Locus arXiv'25 synthesizes predicates as intermediate milestones). No mature, change-conditioned path prioritization. **[INFERRED, uncertain]**

### 2.7 Domain G — Differential & metamorphic testing

- **[G1] CSmith** — Yang et al., PLDI 2011. [Foundational]. Random well-defined C program generation + differential compilation oracle (GCC/LLVM); "pioneered random generation of well-defined C programs" (per OOPSLA'16 related work). Limits: feature subset, no UB oracle.
- **[G2] EMI** — Le, Sun, Su, PLDI 2014 ([ACM DL](https://dl.acm.org/doi/10.1145/2594291.2594334)). [Influential]. Equivalence-Modulo-Inputs: mutate unexecuted code under profiling inputs; variants must behave identically; 147 confirmed GCC/LLVM bugs. Follow-up "live code mutation" (OOPSLA 2016, [ACM DL](https://dl.acm.org/doi/abs/10.1145/2983990.2984038)) mutates live regions too.
- **[G3] CLSmith** — Lidbury et al., PLDI 2015 (cited in RVISmith-related work above): OpenCL compiler differential testing with dead-by-construction code insertion.
- **[G4] Metamorphic testing** — Chen et al., "Metamorphic Testing: A Review of Challenges and Opportunities," ACM Computing Surveys 2018 ([survey](https://www.researchgate.net/publication/296477118_A_Survey_on_Metamorphic_Testing)). [Influential]. Alleviates the oracle problem; requires domain MRs (the bottleneck). LLM-MR-generation is now active: e.g., **MetaFOE** ([arXiv:2606.14164](https://arxiv.org/html/2606.14164)) uses LLMs to generate metamorphic fuzz oracles for C libraries (AP ~77% for MR generation; valid meta-drivers cover 18.7% more edges; but "meta-driver-induced false positives" documented). Compiler-difference testing as a *UB amplifier* (optimizer behavior differs across -O levels on UB) is documented from the UB side by [Don't Look UB, PLDI'23](https://download.vusec.net/papers/dontlookub_pldi23.pdf).
- **[INFERRED]**: no surveyed work couples metamorphic/differential oracles to *changes* (e.g., run changed code at multiple optimization levels / against multiple builds in CI as a change-conditioned oracle) beyond what sanitizer-elision research implies is possible.

### 2.8 Domain H — Mining software repositories

- **[H1] SZZ lineage** (above, E3) — BIC identification as *input data* for defect prediction.
- **[H2] Historical bugs → testing effort.** JIT defect prediction (E4) routes review effort, not test generation. Predictive test selection (A4) uses historical outcomes but only re-weights existing tests. AFLChurn (C3) uses churn (a weak history signal). **No surveyed system mines *failure-mode patterns* of a project's past BICs and conditions test generation on them.** **[INFERRED]** — searched specifically; closest are JIT prediction (no generation) and LIBRO (bug *reports*, not BIC patterns).

---

## 3. Research Evolution (how the field got here)

1. **~2005–2013 — Foundations.** SZZ links bugs to commits (2005). RTS matures (Ekstazi ISSTA'14). Random program generation + differential oracles crack compiler validation (CSmith PLDI'11). Symbolic execution scales to real programs (KLEE OSDI'08; SAGE). KATCH (FSE'13) is the first serious *patch-directed* tester (symbolic).
2. **2014–2018 — Scaling and industrialization.** ML enters CI testing: JIT defect prediction (TSE'13), RTS at Facebook (FSE'14), RETECS RL prioritization (ISSTA'17), Google's TAP analysis (ICSE-SEIP'17), predictive test selection (ICSE-SEIP'19). Fuzzing becomes the dominant dynamic analysis: AFLGo makes DGF general-purpose and OSS-Fuzz-integrated (CCS'17); sanitizers become the standard oracle; QSYM makes hybrid fuzzing practical (USENIX-Sec'18).
3. **2019–2022 — Bug-awareness and sanitizer-awareness.** Regression greybox fuzzing reframes fuzzing around *changes* (AFLChurn CCS'21: ~77% of OSS-Fuzz bugs are regressions). Sanitizer-guided and bug-driven testing appear (ParmeSan USENIX-Sec'20; SAVIOR S&P'20). AST-diff semantics improves impact precision (SEMCIA ICSME'19). Predictive test selection deploys at scale (ICSE-SEIP'19).
4. **2023–2026 — LLM era + tightening change-awareness.** LLM test generation (CodaMosa/TestPilot/LIBRO, ICSE'23–'24), LLM fuzzing (Fuzz4All ICSE'24, ChatAFL CCS'24), LLM bug-reproduction (LIBRO). Change-directed fuzzing gets its strongest results (CIDFuzz'23; WAFLGO USENIX-Sec'24 with a 30-bug BIC dataset). Sanitizer-elision shows "just add sanitizers" is leaky (PLDI'23). CI/CD-fuzzing budgets explicitly named as open (Fuzzing'24 registered reports). LLM-flakiness and compile-validity quantified as unresolved (2025–2026 studies). Agentic AI in CI/CD appears as reference architectures with weak evaluation (arXiv 2508.11867).

**Evolution takeaway:** each generation solved *one axis* — change-directedness (fuzzing line), failure-mode-awareness (sanitizer-guided line), generation capability (LLM line), or selection efficiency (ML-RTS line). The axes have **not been combined**, and each line's own "future work" section asks for a combination (WAFLGO: semantic affected-code identification; MDPI fuzzing review: reliable semantic filters; LLM surveys: context management; RTS line: beyond selection).

---

## 4. Capability Matrix

Legend: ● = explicit evidence in paper/tooling; ◐ = strongly supported by methodology or partial; ○ = absent; ? = unknown / not clearly evaluated. Limitations column is abbreviated (full analysis §5).

| Paper (ID) | AI/LLM | Diff/commit-aware | Semantic analysis | Test generation | Fuzzing | UB detection | Symbolic/concolic | Adaptive strategy selection | CI/CD integration |
|---|---|---|---|---|---|---|---|---|---|
| Ekstazi (A1) | ○ | ● | ○ (file/class deps) | ○ | ○ | ○ | ○ | ○ | ● (production) |
| Static RTS study (A2) | ○ | ● | ○ | ○ | ○ | ○ | ○ | ○ | ◐ |
| Predictive Test Selection (A4) | ● (GBDT) | ● (change features) | ○ | ○ | ○ | ○ | ○ | ◐ (selects tests, one technique) | ● (production) |
| RETECS (A6) | ● (RL) | ◐ (cycle history) | ○ | ○ | ○ | ○ | ○ | ◐ (prioritize/select tests) | ● |
| Taming Google-scale (A9) | ○ | ◐ | ○ | ○ | ○ | ○ | ○ | ◐ | ● |
| TestPilot (B1) | ● | ○ | ◐ (build/run feedback) | ● (unit) | ○ | ○ | ○ | ◐ (retry loop) | ○ |
| CodaMosa (B2) | ● | ○ | ◐ (coverage) | ● | ◐ (SBST) | ○ | ○ | ◐ (LLM-on-stall) | ○ |
| LIBRO (B3) | ● | ○ (bug report, not diff) | ◐ | ● (repro tests) | ○ | ○ | ○ | ◐ (ranked validation) | ○ |
| KATCH (C1) | ○ | ● (patch) | ◐ (heuristics) | ● (inputs) | ○ | ◐ (KLEE checks) | ● | ○ | ◐ (envisioned) |
| AFLGo (C2) | ○ | ● (targets from patch) | ○ (distance only) | ● (inputs) | ● | ○ (oracle only) | ○ | ◐ (energy sched.) | ◐ (OSS-Fuzz toolchain) |
| AFLChurn (C3) | ○ | ◐ (churn, not commit) | ○ | ● (inputs) | ● | ◐ (portfolio) | ○ | ◐ | ◐ (FuzzBench) |
| CIDFuzz (C4) | ○ | ● (change points) | ◐ (taint-based) | ● (inputs) | ● | ◐ | ○ | ○ | ● (CI framing) |
| WAFLGO (C5) | ○ | ● (BIC commits) | ◐ (critical-code analysis) | ● (inputs) | ● | ◐ | ○ | ◐ (input gen strategy) | ◐ (stated goal) |
| ParmeSan (D6/P) | ○ | ○ | ◐ (sanitizer targets) | ● | ● | ● (defines targets) | ○ | ◐ (sanitizer-agnostic retargeting) | ○ |
| SAVIOR (D6/S) | ○ | ○ | ◐ (bug labels) | ● | ● + concolic | ● (6 UB classes, SMT) | ● | ◐ (bug-driven sched.) | ○ |
| Sand (D3) | ○ | ○ | ◐ (exec patterns) | ● | ● | ● (oracle) | ○ | ◐ (selective sanitization) | ○ |
| QSYM (F3) | ○ | ○ | ○ | ● | ● + concolic | ○ | ● | ◐ | ○ |
| Fuzz4All (C7) | ● | ○ | ◐ (autoprompt docs) | ● | ● | ◐ (tool oracles) | ○ | ○ | ○ |
| CSmith (G1) | ○ | ○ | ● (avoid UB) | ● (programs) | ○ | ◐ (differential) | ○ | ○ | ○ |
| EMI (G2) | ○ | ○ | ● (EMI equivalence) | ● (variants) | ○ | ◐ (differential) | ◐ (profiling) | ○ | ○ |
| Metamorphic survey + MetaFOE (G4) | ◐ (MetaFOE ●) | ○ | ◐ | ● | ◐ | ○ | ○ | ○ | ○ |
| JIT defect prediction (E4) | ◐ | ● (change features) | ○ | ○ | ○ | ○ | ○ | ○ (review routing) | ◐ |
| SEMCIA (E2) | ○ | ● | ● | ○ | ○ | ○ | ◐ (dep. analysis) | ○ | ○ |
| AgentSZZ (E3) | ● (agent) | ● | ◐ | ○ | ○ | ○ | ○ | ◐ (tool selection) | ○ |
| AI-augmented CI/CD ref arch (RT) | ● | ◐ | ○ | ○ | ○ | ○ | ○ | ◐ (triage/retry policies) | ● |

**Matrix reading (evidence-based):**
- Column "Diff/commit-aware" ∩ "AI/LLM": only AgentSZZ (for attribution, not testing) and predictive test selection (statistical, not semantic). ● appears nowhere in the *generation/fuzzing* rows.
- Column "UB detection" ∩ "Diff/commit-aware": no row has both ● except CIDFuzz/WAFLGO weakly (◐ via oracle portfolio).
- Column "Adaptive strategy selection" is never ● in the strong sense (choosing *among heterogeneous techniques* per change); ● only for test-selection/prioritization within one family.
- Uncertainty preserved: where a paper might internally do more than its text supports, marked ? / ◐, not assumed.

---

## 5. Limitations Matrix (recurring limitations, with labels)

| # | Limitation | Evidence type | Source(s) |
|---|---|---|---|
| L1 | RTS trades safety for speed; even "safe" selection loses ~8.75% fault-detection ability | Explicit | A2, A3 |
| L2 | ML test selection selects only among *existing* tests; cannot create adversarial inputs for novel code paths | Explicit (method) | A4, A5, A6 |
| L3 | LLM-generated tests: low compile validity (≤ ~10–50% depending on setting/language; worse for C++), high flakiness, symbol-context failures | Explicit | B5, B6, B4 |
| L4 | LLM test generation is not conditioned on the change delta; conditions on functions/bug reports/docs | Explicit (method) | B1–B3 |
| L5 | Directed fuzzing: distance/feature computation too expensive for short CI windows; reaching targets ≠ exercising them | Explicit | C6, C5 discussion |
| L6 | Directed fuzzing target identification is syntactic (changed lines/BBs), missing affected-but-unchanged code; authors call for semantic identification | Explicit (future work) | C5 |
| L7 | Fuzzing explores unrelated regions under fixed budgets; churn is a weak change proxy | Explicit + INFERRED | C3, C2 |
| L8 | Sanitizers: incompatible, 2–46× overhead, FP-prone, cover only *executed* paths, and can be *optimized away* | Explicit | D1, D3, D4 |
| L9 | UB-vs-intent ambiguity (intentional wraparound) → automated UB reports need context calibration | Explicit | D5 |
| L10 | Concolic execution too slow for routine use (10³–10⁵× overhead); needs allocation/triggering, not always-on | Explicit | F3 |
| L11 | Semantic change impact analysis exists but was built for comprehension; syntactic impact sets have 23–49% FP deps | Explicit | E2 |
| L12 | BIC attribution is unreliable (ghost commits; recall ~0.55 on kernel) → history-conditioned testing inherits label noise | Explicit | E3 |
| L13 | JIT risk prediction predicts *risky vs not*, not *failure-mode class*; models decay ("moving target"); extrinsic bugs unmodeled | Explicit | E4 |
| L14 | LLM fuzzing: semantic-invalid inputs, GPU/CPU mismatch, weak reproducibility; "no stable interface between probabilistic outputs and checkable evidence" | Explicit | C8 |
| L15 | Agentic CI/CD AI exists as architectures/vendor claims, not as peer-reviewed defect-discovery-per-cost results | Explicit + INFERRED | RT section 8 |
| L16 | No surveyed system couples semantic change analysis to failure-mode-class prediction to steer technique/sanitizer/oracle choice | INFERRED (from absence across §2 after targeted counter-searches in §8) | — |

**Phase 5 pattern verification against literature:**
- "AI generates tests but does not choose the appropriate technique for the change" — **verified** (L2/L4; B1–B6 all technique-fixed).
- "Fuzzing wastes resources on regions unrelated to a commit" — **verified** (C2/C3 motivation + OSS-Fuzz 77%-regression analysis; DGF line exists precisely because of this, but budget problem remains, L5).
- "Sanitizers require execution paths that trigger the issue" — **verified** (D2/D4; plus optimizer elision).
- "Regression testing selects existing tests but does not generate adversarial tests" — **verified** (L2; A1–A11).
- "Change analysis identifies affected code but does not reason about likely semantic failure modes" — **verified** (L6/L11/L13).

---

## 6. Intersection Analysis

For each pair, status, extent, integration depth, end-to-end operation, and remaining limitations:

| Intersection | Studied? | Extent & integration depth | Key works | Remaining limitations |
|---|---|---|---|---|
| **AI + Change Analysis** | Yes (statistical/ML) | Mature for *risk scoring*; superficial for *semantics*. Features are file-level/author/history; no failure-mode semantics | A4, E4, E3(AgentSZZ), L13 | Predicts "risky", not "what kind of bug"; no action policy beyond review/test-weighting |
| **Change Analysis + Fuzzing** | Yes, actively | Deep technical line: KATCH→AFLGo→AFLChurn→CIDFuzz→WAFLGO; Fuzzing'24 registered reports on CI budgets | C1–C6 | Single technique; syntactic targeting; budget impracticality (L5, L6); no UB-class reasoning |
| **AI + Fuzzing** | Yes, very active | LLM seed/harness/driver generation, DGF corpora (Fuzz4All, ChatAFL, ISC4DGF, Locus); surveys exist | C7–C9 | Validity/reliability (L14), cost (inference loop), never change-conditioned, no CI evaluation |
| **Fuzzing + UB Detection** | Yes | Sanitizer-guided/bug-driven fuzzing is established (ParmeSan, SAVIOR); decoupled sanitization (Sand); bug coverage orientation | D6, D3 | Sanitizer portfolio chosen globally/a priori; incompatible sanitizers force choices — but no *per-change* sanitizer decision |
| **Change Analysis + UB Detection** | **Thin** | Only reachability-level: change points as taint/distance targets (CIDFuzz, WAFLGO). Nothing found predicting *UB class* from the change and adapting detector/harness | C4, C5 | The decision "this diff smells like an integer-overflow risk → run UBSan-directed generation + IOC-style checks" is unoccupied |
| **AI + Regression Testing** | Yes | ML selection/prioritization deployed in industry (Meta, Salesforce, T-TS) | A4–A8 | Existing-tests-only; safety losses (L1); no generation, no heterogeneous techniques |
| **Historical Bugs + Test Generation** | Thin | LIBRO: bug *reports* → repro tests (works, 33%); AFLChurn: churn proxy; JIT: review routing. No closed loop BIC-pattern → test strategy | B3, C3, E4 | Label noise (L12); no surveyed system accumulates project-specific failure-mode knowledge and spends it in CI |
| **AI + CI/CD Test Orchestration** | Emerging / weak evidence | Reference architectures, vendor tools, triage/retry agents (flaky-test quarantine) | arXiv:2508.11867; vendor blogs (§8) | No peer-reviewed, budgeted, defect-per-cost evaluation of *technique selection*; integration ≠ contribution (Critical Rule 4) |
| **Semantic Diff + Adaptive Test Selection** | Thin | RTS uses file/class/graph deps (Ekstazi/STARTS); SEMCIA proves semantic diffs reduce FP impact sets — for comprehension only | A1–A2, E1–E2 | Nobody consumes semantic diffs for *adaptive strategy selection*; plumbing exists (GumTree, `sem`), decision layer missing |

---

## 7. Candidate Research Gaps (formulated from evidence)

> Formatted per the required template. Each is stated as: existing research addresses A; other research addresses B; C remains limited; therefore investigate D.

---

**GAP ID: G1 — Budgeted, change-conditioned *technique selection* for CI testing**

**DESCRIPTION:** Existing research successfully addresses (A) selecting *which existing tests* to run per change (predictive TS, RTS) and (B) directing *one* technique (fuzzing) at changed code (AFLGo/WAFLGO/CIDFuzz). However, evidence suggests C — the selection *among heterogeneous techniques* (regression suite, generated unit tests, directed fuzzing with sanitizer X, concolic execution, metamorphic/differential oracles) under an explicit per-commit compute budget, optimized for defect-discovery-per-cost — remains uninvestigated as a decision problem with rigorous evaluation; CI-fuzzing budget behavior was itself named an open question in 2024 (Fuzzing'24 registered reports; L5).

**SUPPORTING LITERATURE:** A4 (selection-only), C2/C5 (fuzzing-only), A9 (Google: objective is detection per unit compute), C6 (budget open problem), F3 (concolic too costly to run always), D3 (sanitizer portfolio cost).

**CONTRADICTING LITERATURE:** arXiv:2508.11867 proposes agentic CI/CD decision points (but evaluates triage/retry policies on a case study, not technique selection with defect-per-cost measurement); vendor platforms (e.g., VirtuosoQA) market "strategy selection agents" without peer-reviewed evidence — noted, not treated as refutation of an academic gap.

**NOVELTY RISK: Medium** (industry is clearly moving here; the *evaluated decision problem* appears open). **FEASIBILITY: High.** **MEASURABILITY: High** (unique bugs/CPU-hour, TTD, selection safety).

**POTENTIAL CONTRIBUTION:** First formalized and empirically evaluated per-commit testing-technique allocation problem with public datasets and strong baselines.

**WHY THIS GAP MATTERS:** CI compute is finite (Google: 1.23% of executions find breakages); every surveyed technique excels on a different failure subspace; allocating wrongly wastes the budget exactly when changes need it.

---

**GAP ID: G2 — Failure-mode-aware steering of input generation and detectors from semantic change analysis**

**DESCRIPTION:** Existing research addresses (A) reaching changed code with inputs (change-directed fuzzing) and (B) steering fuzzing toward sanitizer bug-checks globally (ParmeSan, SAVIOR). However, C — predicting the *likely failure-mode class* (memory-safety, integer UB, C++ lifetime, concurrency, oracle/logic) of a specific semantic change and using that prediction to jointly choose detector(s) (sanitizer set), oracle(s), and input-generation strategy — is unoccupied: CIDFuzz/WAFLGO classify nothing (targets are changed lines/BBs), ParmeSan/SAVIOR classify nothing per-change, SEMCIA/JIT predict risk or impact, not failure class.

**SUPPORTING LITERATURE:** L6 (WAFLGO future work asks for semantic affected-code identification), L8/L9 (sanitizer portfolio choices are costly and context-dependent; intent ambiguity), L11 (semantic diff reduces FP impact sets), L13 (JIT predicts risk not mode), L16.

**CONTRADICTING LITERATURE:** SAVIOR models 6 UB categories as SMT constraints — but to *verify* reachable candidates, not to *predict* which class a change risks; AgentSZZ uses LLM agents for attribution, not testing. No refuting end-to-end system found.

**NOVELTY RISK: Medium.** **FEASIBILITY: Medium-High.** **MEASURABILITY: High** (per-class recall/precision of prediction; downstream TTD and bugs/CPU-hour on the WAFLGO 30-bug BIC dataset and OSS-Fuzz regression bugs).

**POTENTIAL CONTRIBUTION:** A change→failure-mode prediction model and its *causal, measurable* effect on defect detection efficiency; ties three previously separate lines (semantic diff, JIT-style prediction, sanitizer-guided generation).

**WHY THIS GAP MATTERS:** Wrong detector = wasted CI minutes and missed bugs; sanitizer choices are mutually exclusive at scale (D3); UB intent ambiguity (D5) demands change context — all three point at conditioning signals currently unused.

---

**GAP ID: G3 — Commit-conditioned generation of *new* adversarial tests (edge/boundary/UB) for changed code**

**DESCRIPTION:** A: LLM+SBST generate tests with coverage/bug-report conditioning (CodaMosa, TestPilot, LIBRO); B: RTS selects existing tests per change. C: generation conditioned on the *change delta* — "write tests that expose what this commit could break, including boundary/UB behavior in changed code" — with validity control, is unexplored; current LLM generation is function/doc-conditioned and unreliable for C++ (B5/B6).

**SUPPORTING LITERATURE:** L4, B3 (proof-of-concept that conditioning on a failure *description* yields executing tests), L3 (reliability limits = the technical challenge), A3 (selection alone loses detection power).

**CONTRADICTING LITERATURE:** Test amplification (DSpot) mutates existing tests, but is not change-conditioned; no found system does commit-conditioned adversarial test generation in CI.

**NOVELTY RISK: Medium-High** (LLM-for-testing is crowded; risk that someone publishes commit-conditioned generation soon). **FEASIBILITY: Medium** (C/C++ validity is hard). **MEASURABILITY: High** (regression-bug detection rate on BIC benchmarks, compile/validity rates, oracle correctness).

**POTENTIAL CONTRIBUTION:** Change-delta prompting/context extraction + validation loop that measurably raises BIC-detection over function-level generation.

**WHY THIS GAP MATTERS:** Selected existing suites demonstrably miss faults that new inputs would catch (A3; OSS-Fuzz regression stats); generation is the only way to produce *new* adversarial behavior for novel code.

---

**GAP ID: G4 — CI-budget realism in change-directed fuzzing (measurement & technique design)**

**DESCRIPTION:** A: DGF finds change-introduced bugs in hours-scale campaigns (WAFLGO: 8× vs AFLChurn); B: CI windows are minutes-scale. C: whether distance/feature computation and directed strategies remain net-beneficial at CI budgets is explicitly unresolved (Fuzzing'24 registered reports) and unmeasured across budget regimes.

**SUPPORTING LITERATURE:** C5, C6, C3 (campaign-scale evidence only), L5.

**CONTRADICTING LITERATURE:** CIDFuzz reports CI-applicable improvements (time-to-cover change points) — but measures *coverage time*, not bug discovery under budgets, on 4 projects.

**NOVELTY RISK: Low-Medium.** **FEASIBILITY: High.** **MEASURABILITY: High.**

**POTENTIAL CONTRIBUTION:** First controlled budget-sensitivity study of change-directed testing (10 min–24 h) + lightweight targeting designs (incremental distance computation, caching between runs).

**WHY THIS GAP MATTERS:** Determines whether the entire change-directed-fuzzing line is practically deployable in CI, which is the premise of the original idea.

---

**GAP ID: G5 — History-conditioned targeted testing: accumulating project-specific failure-mode knowledge**

**DESCRIPTION:** A: BIC mining (SZZ lineage) and JIT prediction exist; B: predictive TS consumes outcome history. C: no surveyed system *accumulates* a project's failure-mode patterns (which change shapes introduced which bug classes) and *conditions test generation/steering* on them, closing the loop; label noise (ghost commits, recall ~0.55) is the key technical obstacle.

**SUPPORTING LITERATURE:** E3, E4, C3 (churn as crude proxy), L12, B3 (reports→tests feasibility).

**CONTRADICTING LITERATURE:** AFLChurn already exploits history (churn) — but unlearned and coarse; nothing found that learned failure-mode-conditioned strategies from BIC data.

**NOVELTY RISK: Medium.** **FEASIBILITY: Medium** (label noise, needs multi-project data). **MEASURABILITY: Medium** (depends on BIC label quality).

**POTENTIAL CONTRIBUTION:** Project-adaptive testing that improves with history; measurable against churn and JIT baselines.

---

**GAP ID: G6 — Cross-technique failure triage and attribution in CI**

**DESCRIPTION:** A: fuzzing produces crashes; sanitizers produce UB reports; tests produce failures. C: unified triage/attribution (is this crash caused by the change? which class? deduplicate across detectors?) is unsolved and LLMs are plausible but unvalidated here; commercial and reference-architectures claim it without peer review.

**SUPPORTING LITERATURE:** RT section 8; D3 (sanitizer FPs); L15.

**NOVELTY RISK: Medium-High** (active area). **FEASIBILITY: Medium.** **MEASURABILITY: Medium** (triage precision/time, but ground truth is costly).

**WHY THIS GAP MATTERS:** Triage cost gates adoption of every other technique; but it is downstream of G1/G2 and weaker as a standalone thesis.

---

## 8. Gap Validation / Red-Team: attempting to invalidate the original idea and each gap

**Red-team verdict on the ORIGINAL idea:** partially pre-existing. (1) *Change-aware testing in CI* — solved for selection (Ekstazi, predictive TS). (2) *Identifying likely failure modes of changes* — partially exists as *risk* prediction (JIT), not failure-class prediction. (3) *Adaptive selection of testing strategies incl. fuzzing/UB techniques* — not found in peer-reviewed, evaluated form; the single-technique components all exist (WAFLGO, ParmeSan, SAVIOR, CodaMosa). (4) *End-to-end orchestration* — reference architectures exist with weak evaluation (arXiv:2508.11867; vendor tools). Conclusion: the idea as a *platform* is not novel; defensible novelty must live in a specific measurable mechanism (see G1/G2).

**Per-gap invalidation attempts:**
- **G1:** searched for "adaptive test strategy selection", "AI CI/CD test orchestration", agentic CI/CD papers. Found: vendor marketing (VirtuosoQA — claims unmeasured), reference architecture (arXiv:2508.11867 — evaluates flaky-test triage and trust tiers, not technique allocation vs. defect-per-cost), and ML selection literature (single technique family). **G1 survives, scoped to evaluated technique-mix allocation.** Risk: could be dismissed as "integration" unless the allocation policy is the measured contribution (Critical Rule 4 respected by measuring defect-per-cost against best fixed portfolios).
- **G2:** searched "failure mode prediction commits", "sanitizer selection", "UB prediction code changes", "directed fuzzing commit". Found: JIT risk (not class), SAVIOR (UB modeling at verification time), WAFLGO (change targets, no class reasoning), CIDFuzz (reachability only). **G2 survives.** Contradicting check: ParmeSan's sanitizer-agnostic retargeting shows sanitizer choice matters but is *manual/global*, strengthening rather than refuting the gap.
- **G3:** searched "LLM test generation change/commit", "commit-aware test generation". Found: function/report-conditioned generation only. **G3 survives but with medium-high crowding risk.**
- **G4:** Fuzzing'24 registered reports *directly state* the open question. **G4 survives; risk is low novelty ceiling (empirical study + engineering).**
- **G5:** searched "history-based fuzzing", "bug pattern mining test generation". AFLChurn is the closest; it is not learned and not class-aware. **G5 survives; measurement risk from label noise (L12).**
- **G6:** exists commercially in some form (test-failure triage agents); peer-reviewed cross-detector triage not found but adjacent work is dense. **G6 demoted.**

**Eliminated weak gaps:** "nobody built my idea" (rejected by red-team), "novel integration platform" (rejected — integration alone), "AI triage" (G6, demoted), "LLM unit-test generation in CI" (crowded; reliability issues are documented but solving them is a benchmark-driven engineering race).

---

## 9. Selecting the Strongest Research Problem

Ranked table (1 = best; evidence strength / novelty / feasibility / measurability / data availability / compute needs / academic fit):

| Rank | Gap | Evidence | Novelty | Feasibility | Measurability | Datasets | Compute | Academic fit | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **G2** (+G1 as evaluation frame) | Strong (5 converging limitations L5,L6,L8,L11,L13) | Medium | Med-High | High | WAFLGO-30, OSS-Fuzz regressions, Magma, FuzzBench | Moderate (CPU-hours, small LLM) | High (clear RQs, baselines) | **RECOMMENDED** |
| 2 | G1 | Strong (A9, C6) | Medium | High | High | Same as G2 + RTS benchmarks | Moderate | High | Frame for G2; also standalone |
| 3 | G4 | Strong (explicit open question) | Low-Med | High | High | FuzzBench + WAFLGO-30 | Low-Moderate | Medium (study+tool paper) | Safe fallback |
| 4 | G3 | Medium (L3,L4 + LIBRO precedent) | Med-High | Medium | High | Defects4J/BugsInPy + BIC corpora | LLM inference | High | High-risk/high-reward |
| 5 | G5 | Medium | Medium | Medium | Medium | BIC corpora (noisy) | Moderate | Medium | Second-phase extension |
| 6 | G6 | Medium | Med-High | Medium | Medium | Custom | LLM | Medium | Demoted |

**Recommendations:**
- **Best research direction:** **G2×G1 composite** — *change-conditioned failure-mode prediction steering a budgeted portfolio of testing techniques, evaluated as defect-discovery-per-compute against the strongest single-technique change-aware baselines.* It is the only formulation that (i) inherits the strongest evidence, (ii) has a measurable technical innovation (the conditioning signal), not mere integration, (iii) ships with ready baselines and datasets (WAFLGO public dataset; FuzzBench; OSS-Fuzz regression bugs).
- **Second-best:** G1 standalone (formalize + measure the allocation problem; easier, slightly less "deep").
- **High-risk/high-reward:** G3 (commit-conditioned adversarial test generation; crowded space, big payoff if validity solved for C/C++).
- **Most feasible implementation direction:** G4 (CI-budget study of change-directed fuzzing; almost guaranteed publishable, bounded scope).

**Trade-off note:** G2 requires building a working multi-technique harness (engineering weight); G3 requires solving LLM reliability in C/C++ (research risk); G4 is safe but incremental. The recommended composite can *degrade gracefully*: if the prediction model underperforms, the budgeted-portfolio study (G1/G4) still yields publishable findings.

---

## 10. Research Questions

**Broad Research Question:**
> How can semantic analysis of pushed code changes be used to predict the failure modes a change risks introducing, and to adaptively allocate a budget-constrained portfolio of testing techniques — such that defect discovery per unit of CI compute significantly improves over state-of-the-practice change-aware pipelines?

**Specific Research Questions:**

**RQ1 — Prediction.** Can a classifier over semantic commit representations (AST diff + dependency context, optionally LLM-assisted) predict the dominant failure-mode class (memory-safety / integer-UB / C++-lifetime / concurrency / logic-oracle) of change-introduced defects better than change-risk baselines?
- IV: prediction model (semantic-diff classifier vs churn vs JIT features vs majority).
- DV: top-1/top-3 failure-class recall & precision on held-out BICs.
- Baseline: AFLChurn-style churn signal; Kamei JIT features; random.
- Evaluation: stratified cross-project validation on WAFLGO-30 + newly labeled OSS-Fuzz regression bugs; report per-class confusion.
- Expected evidence: semantic features materially beat churn at *class* level (motivated by SEMCIA's 23–49% FP reduction for semantic diffs and L13's "risk ≠ mode").

**RQ2 — Steering effect.** Does failure-mode-conditioned allocation of techniques (existing-suite RTS / directed fuzzing with class-matched sanitizer / concolic / generated unit tests) improve unique real bugs found per CPU-hour on change-introduced bugs versus (a) best fixed portfolio, (b) WAFLGO, (c) CIDFuzz, (d) predictive test selection alone?
- IV: allocation policy (conditioned vs fixed portfolios vs single techniques).
- DV: unique confirmed bugs per CPU-hour; time-to-detection; % of BICs detected within budget.
- Baselines: WAFLGO, CIDFuzz, AFLGo, AFLChurn, full-portfolio-always, predictive TS.
- Evaluation: equal-budget paired runs (≥20 seeds, FuzzBench-style), multiple budget levels (10 min / 1 h / 8 h / 24 h).
- Expected evidence: crossover — conditioned allocation wins at small budgets; marginal gain shrinks as budget → ∞ (which itself answers G4).

**RQ3 — Sanitizer pre-selection.** Does predicted-UB-class sanitizer selection reduce time-to-first-relevant-violation at equal compute vs. full-portfolio sequential/sandwiched execution?
- IV: sanitizer policy (predicted class vs ASan-first fixed order vs full parallel).
- DV: TTD per UB class; violations/CPU-hour; FP rate.
- Baseline: Sand-style decoupled full portfolio; IOC-style checker for integer UB.
- Expected evidence: 2–46× sanitizer overhead spread (D3) implies headroom; UBSan-cheap/MSan-expensive asymmetry makes prediction profitable for rare classes.

**RQ4 — History conditioning (stretch).** Do failure-mode patterns mined from a project's own BICs improve steering accuracy over cross-project priors?
- IV: conditioning source (project history vs generic prior vs none).
- DV: RQ1-style class prediction; downstream RQ2-style detection deltas.
- Baseline: churn, JIT.
- Expected evidence: project-specific gains exist but degrade with BIC label noise (L12) — quantifying that degradation is itself a contribution.

---

## 11. Final Problem Statement

### Version A — Academic concise (≈140 words)
> Continuous-integration pipelines allocate scarce compute across testing techniques chosen by convention: regression suites plus fixed sanitizer builds, occasionally fuzzing. Existing work selects which *existing* tests to run per change (regression test selection; predictive test selection) or directs *one* technique — fuzzing — at changed code (AFLGo, AFLChurn, CIDFuzz, WAFLGO), and sanitizer-guided fuzzers steer input generation toward bug checks irrespective of provenance (ParmeSan, SAVIOR). Across these lines, three capabilities remain disconnected: semantic analysis of the change, prediction of the *class* of defect a change risks introducing, and budget-aware selection among heterogeneous detectors and input generators. Consequently, CI compute is spent on techniques mismatched to the change, and change-introduced defects — which dominate fuzzing bug reports (~77% in OSS-Fuzz) — persist in production. This research investigates failure-mode-aware, change-conditioned selection and steering of CI testing techniques, measured as defect discovery per unit compute.

### Version B — Detailed proposal version (≈330 words)
> Modern CI/CD systems face a structural mismatch. The defects that matter most — those introduced by a code change — require different detection techniques than pre-existing faults: memory-safety regressions need sanitizer-instrumented executions with inputs that reach affected code; integer undefined behavior needs UBSan/IOC-class checks exercised on boundary conditions; concurrency defects need race detectors driven by interleaving-rich executions; logic regressions need generated or existing functional tests with oracles. The literature provides strong *components*: regression test selection and ML-based predictive test selection choose which existing tests to run per change; directed fuzzing concentrates input generation on changed code (Katch, AFLGo, AFLChurn, CIDFuzz, WAFLGO); sanitizer-guided and bug-driven fuzzers orient generation toward bug-checking sites (ParmeSan, SAVIOR); LLM-based systems generate unit and bug-reproducing tests (CodaMosa, TestPilot, LIBRO); and just-in-time defect prediction scores the *risk* of a change. However, these lines do not compose into a decision procedure. No evaluated system classifies which failure-mode class a semantic change risks introducing, and uses that classification to select among heterogeneous techniques and detectors under an explicit per-commit compute budget. The consequences are quantified in the literature: selection-only pipelines lose fault-detection ability; directed fuzzers miss affected code beyond syntactic targets; sanitizer portfolios are mutually exclusive and cost 2–46× runtime; LLM-generated tests are unreliable without execution-grounded validation; and industrial-scale data (Google, OSS-Fuzz) shows detection-per-compute is the binding constraint while ~77% of fuzzing bug reports are change-induced regressions. This research therefore investigates: (1) predicting the failure-mode class of a change from its semantic diff and project history; (2) a budgeted allocation policy steering regression selection, class-matched sanitizer builds, change-directed fuzzing, selective concolic execution, and validated test generation; and (3) measurement of defect discovery per unit compute against the strongest single-technique baselines on public bug-inducing-commit datasets. The expected contribution is both an empirical characterization of the allocation problem and a mechanism — change-conditioned failure-mode steering — that measurably improves early detection of change-introduced defects.

### Version C — Engineering / project version
> Build a CI job that, for every push: (1) extracts an AST-level diff (GumTree/tree-sitter) plus dependency context; (2) runs a small classifier (gradient boosting over structural features, optionally an LLM in the loop) that predicts failure-mode classes: memory-safety, integer-UB, C++-lifetime, concurrency, logic/oracle; (3) consults a budget policy that allocates the CI time budget across: the existing regression suite (selected via Ekstazi-style or ML selection), a change-directed fuzzer (AFLGo/WAFLGO-style) built with only the sanitizer(s) matching predicted classes, boundary/UB-targeted generated tests (LLM-generated, execution-validated), and — only when predicted deep-guard logic is present — concolic runs; (4) executes everything in sandboxed, containerized runners; (5) triages findings (crash + sanitizer report + failing generated test → deduplicated, change-attributed report). Evaluation harness: replay historical commits (bug-inducing and clean) from public datasets, measure unique bugs per CPU-hour and time-to-detection against WAFLGO/CIDFuzz/full-portfolio baselines. Implementation reality check: the classifier and budget policy are the research contribution; every executor is an off-the-shelf component wrapped in a common harness. MVP = classifier + (RTS vs UBSan-directed fuzzing) two-way allocation on the WAFLGO dataset.

---

## 12. Proposed Experimental Methodology

**Design:** paired, budget-controlled replays of historical commits (BICs and matched clean commits) across strategies; factorial over {policy} × {budget} × {seed} (≥20 seeds, FuzzBench-style statistics: A12 ranking / Mann-Whitney with holm correction).

**Baselines:** (B1) retest-all; (B2) RTS (Ekstazi/STARTS); (B3) predictive test selection; (B4) AFLGo; (B5) AFLChurn; (B6) CIDFuzz; (B7) WAFLGO (strongest); (B8) fixed full portfolio (all sanitizers parallel); (B9) CodaMosa/TestPilot-style generation without change conditioning; (B10) SAVIOR-style bug-driven hybrid without change conditioning.

**Benchmarks & datasets:**
- WAFLGO 30-bug dataset with manually identified BICs (public, USENIX-Sec'24 artifact).
- AFLGo/Katch patch-testing benchmarks (GNU diffutils/binutils/findutils; libbfd/libxml2 CVE commits).
- OSS-Fuzz regression bugs (20 bugs / 15 projects from the AFLChurn study; extendable from the OSS-Fuzz tracker; ~77% of reports are regressions).
- Magma / LAVA-M / CGC for ground-truth injected faults; FuzzBench for reproducible fuzzing campaigns.
- Defects4J + BugsInPy for the generated-test arm (multi-language check); optionally a C project BIC corpus labeled via SZZ+manual verification (ghost-commit caveats per Rezk et al.).
- Kamei JIT dataset for RQ1 baseline features.

**Metrics:** unique confirmed bugs per CPU-hour (primary); time-to-detection; % BICs detected within budget; changed-code coverage (patch coverage à la AFLGo); selection safety/precision violations (RTS terminology); per-class precision/recall of failure-mode prediction; generated-test compile/validity/flakiness rates; triage cost (duplicate rate, false-positive rate); FP UB reports (intentional-wraparound misclassification, calibrated against IOC-style intent analysis).

**Failure categories (ground-truth taxonomy):** memory-safety (OOB, UAF, double-free, dangling, uninitialized), integer UB (signed overflow, div-by-zero, invalid shift, truncation), C++ lifetime (invalid iterators/references, lifetime/vptr), concurrency (races, atomicity, ordering), logic/oracle (wrong output vs spec). Map each dataset bug to ≥1 category at labeling time; multi-label where necessary.

**Threats to validity (planned mitigations):**
- *Construct:* sanitizer reports ≠ bugs (intent ambiguity — human label verification; report intent-sensitive metrics); coverage ≠ detection (use bug-based primary metric).
- *Internal:* compute-fairness (equal CPU-seconds including setup/distance computation); seed variance (≥20 runs); LLM nondeterminism (fixed temperature + repeats).
- *External:* small BIC datasets (augment via SZZ + manual vetting; cross-project validation); C-only fuzzing results may not transfer (include Defects4J/BugsInPy arm).
- *Contamination:* LLM may have memorized OSS-Fuzz fixes — follow LIBRO's post-cutoff evaluation protocol.
- *Flakiness:* flaky generated tests and flaky failures confound detection counts — adopt iDFlakies-style flakiness filtering before counting.

---

## 13. Proposed System Architecture (only the components the gap justifies)

```
Git Push / PR
   │
   ▼
Diff Extraction ──────────────── AST/entity-level diff (GumTree-class) + changed-symbol dependency graph
   │
   ▼
Semantic Change Analysis ─────── changed functions, affected-but-unchanged callers/callees, data-flow hints
   │
   ▼
Failure-Mode Classification ──── [RESEARCH COMPONENT] P(class | semantic diff, history features)
   │                              classes: memory / integer-UB / C++-lifetime / concurrency / logic
   │
   ▼
Budgeted Strategy Planner ────── [RESEARCH COMPONENT] allocation of CPU-seconds across techniques
   │                              (contextual bandit or cost-aware decision policy; observable reward = confirmed findings)
   ├── Existing Regression Suite (RTS/ML selection)                 [off-the-shelf: Ekstazi/STARTS/predictive TS]
   ├── Directed Fuzzing on changed code + class-matched sanitizer   [off-the-shelf: AFLGo/WAFLGO + chosen -fsanitize set]
   ├── Generated Unit/Boundary Tests (execution-validated)          [off-the-shelf: CodaMosa/TestPilot-class + validity filter]
   ├── Selective Concolic (only for deep-guard logic predictions)   [off-the-shelf: QSYM-class; optional, budget-gated]
   └── Differential/Metamorphic Oracle (opt-level or build variants) [off-the-shelf: EMI/UBSan-elision-aware builds]
   │
   ▼
Sandboxed Execution (containers; per-technique time budgets; artifact capture)
   │
   ▼
Failure Detection & Change Attribution ── sanitizer report / crash stack → nearest BIC mapping (SZZ-class)
   │
   ▼
AI-Assisted Triage (dedup, severity, intent check for UB vs intentional wraparound)
   │
   ▼
CI/CD Report (per-commit: predicted classes, techniques run, budget spent, findings with evidence)
```

Component justification: the two RESEARCH COMPONENTS are precisely the validated gap (G2/G1). Everything else is deliberately off-the-shelf: the contribution is the conditioning signal and allocation policy, *not* a new fuzzer or a new test generator. Concolic and differential oracles are optional arms activated only under predicted conditions (cost profile per F3/D3), and their inclusion/omission is itself studied (ablation).

---

## 14. Novelty Assessment

**Known existing capabilities (verified, with sources):**
- Change-directed fuzzing of commits/patches: KATCH (FSE'13), AFLGo patch testing (CCS'17), AFLChurn (CCS'21), CIDFuzz ('23), WAFLGO (USENIX-Sec'24).
- Sanitizer-guided / bug-driven input generation: ParmeSan (USENIX-Sec'20), SAVIOR (S&P'20).
- ML selection/prioritization of existing tests in CI: predictive TS (ICSE-SEIP'19), RETECS (ISSTA'17), T-TS ('25); deployed at Meta/Salesforce/Google-scale.
- LLM test generation & bug reproduction: CodaMosa, TestPilot, LIBRO (ICSE'23–'24); LLM fuzzing front-ends (Fuzz4All ICSE'24, ChatAFL CCS'24).
- Change risk prediction: JIT defect prediction (TSE'13) and SZZ lineage.
- Agentic CI/CD frameworks: reference architectures (arXiv 2508.11867) and vendor platforms — claims unevaluated for defect-per-cost.

**Likely novel contribution (evidence-scoped):**
1. A *failure-mode-class predictor for code changes* (semantic-diff-conditioned), with per-class evaluation on BIC datasets — not found in any surveyed peer-reviewed work.
2. *Change-conditioned steering* of detector (sanitizer) selection and input-generation strategy — the sanitizer-guided-fuzzing and change-directed-fuzzing lines have never been connected; both lines' authors request it (WAFLGO future work; ParmeSan sanitizer-agnostic retargeting).
3. A *defect-discovery-per-compute* evaluation framework for change-aware testing portfolios at realistic CI budgets — named as an open question by Fuzzing'24 registered reports.

**Potential overlap to acknowledge in any paper:** WAFLGO/CIDFuzz (change-directed fuzzing component), SAVIOR (bug-class-constrained verification), Machalica et al. (selection policy shape), arXiv:2508.11867 (orchestration framing). Positioning must be "we add the missing conditioning and measure its causal effect," not "first change-aware or first AI testing framework."

**Novelty confidence: Medium.** The mechanism-level gap (failure-mode-conditioned steering + budgeted evaluation) appears unoccupied after targeted counter-searches; the platform-level idea is not. Medium—not high—because (a) the field is fast-moving and LLM-agent-for-CI papers appear monthly, and (b) parts of the contribution are integration-shaped and must be defended via the measurability of the conditioning signal.

---

## 15. Research Roadmap (concrete next steps)

**Phase 0 (weeks 1–6): Dataset & baselines.**
Reproduce WAFLGO and CIDFuzz on the 30-bug BIC dataset; import AFLChurn's OSS-Fuzz regression set; label failure-mode categories for every bug (≥2 annotators, report Cohen's κ); set up FuzzBench-based, budget-controlled replay harness.

**Phase 1 (months 2–4): RQ1 prediction.**
Build AST-diff feature extraction (GumTree/tree-sitter + reachability context); train failure-mode classifier (GBDT baseline; frozen LLM embedding variant); evaluate per-class recall vs churn/JIT baselines; ablate semantic vs syntactic features (SEMCIA-style comparison).

**Phase 2 (months 4–8): RQ2/RQ3 steering.**
Implement budget planner (start: cost-weighted heuristic; then contextual bandit over replays); wire executors (RTS, directed fuzzing w/ per-class sanitizer builds, validated test generation); run factorial budget experiments (10 min/1 h/8 h/24 h × ≥20 seeds); measure bugs/CPU-hour, TTD, safety.

**Phase 3 (months 8–12): stretch & robustness.**
RQ4 history conditioning on BIC-mined patterns (with ghost-commit noise quantification); contamination check with post-cutoff bugs (LIBRO protocol); flakiness filtering; cross-language arm (Defects4J/BugsInPy).

**Phase 4 (months 12–15): Write & release.**
Paper framing: "change-conditioned failure-mode steering for budgeted CI testing"; release harness, labels, and classifier as artifact (addresses the reproducibility weakness flagged across the LLM-fuzzing literature).

**Decision gates:** if RQ1 classifier cannot beat churn baseline (AUC delta < ~0.05), pivot to G4 (budget-sensitivity study) which remains publishable; if LLM-generated tests' validity is too low in C/C++, drop that arm rather than weaken the main claim.

---

## Appendix A — Compact paper records (schema per Phase 2; full schema for the 12 most decision-relevant papers, condensed for the rest)

**P-01 WAFLGO** | TITLE: Critical Code Guided Directed Greybox Fuzzing for Commits | YEAR: 2024 | AUTHORS: Xiang et al. | VENUE: USENIX Security | DOMAIN: C (Fuzzing × Change-aware) | SUBDOMAIN: commit-directed DGF | PROBLEM: fuzzers don't efficiently find bugs introduced by commits; reaching change sites ≠ exercising affected code | INPUT: commit diff, binary+source | METHOD: critical-code identification (path- + fault-relevant), new distance metric, guided input generation | OUTPUT: inputs reaching/exercising affected code; crash reports | EVAL: 30 real bugs w/ manually identified BICs; vs AFL/AFL++/FairFuzz/AFLChurn | METRICS: bug reproduction rate, time | RESULTS: outperforms AFLChurn by 5 more reproduced bugs, 8.0× speedup; 7 new bugs (4 CVEs) | SOLVES: thorough fuzzing of commit-affected code | DOES NOT SOLVE: failure-mode classification; technique/sanitizer choice; CI-minute budgets; semantic affected-code analysis (author-stated future work) | LIMITATIONS: syntactic target identification (author-acknowledged via future-work call); hour-scale campaigns | RELEVANCE: **High** — primary baseline. EVIDENCE: [USENIX PDF](https://www.usenix.org/system/files/sec24summer-prepub-301-xiang-yi.pdf).

**P-02 AFLChurn / Regression Greybox Fuzzing** | YEAR: 2021 | AUTHORS: Zhu, Böhme et al. | VENUE: CCS | DOMAIN: C (Fuzzing × History) | PROBLEM: OSS-Fuzz spends energy on long-stable code though ~77% of reports are regressions | METHOD: power schedule biased to recently/often-changed code ("churn") | EVAL: 3+ CPU-years, FuzzBench, 20 regression bugs / 15 projects | RESULTS: ~1.5× faster regression discovery vs AFL | DOES NOT SOLVE: per-commit targeting, semantics, other techniques | RELEVANCE: **High**. EVIDENCE: [PDF](https://mboehme.github.io/paper/CCS21.pdf).

**P-03 CIDFuzz** | YEAR: 2023 | VENUE: IET Software | DOMAIN: C (Fuzzing × CI) | METHOD: CI change points as taint sources; distance instrumentation; coverage-based resource allocation | RESULTS: 39.6%/41.6% less time to cover change points vs AFL/AFLGo | LIMITS: 4 projects; coverage-time (not bug) metric; single technique | RELEVANCE: **High**. EVIDENCE: [list](https://github.com/strongcourage/awesome-directed-fuzzing).

**P-04 AFLGo** | YEAR: 2017 | AUTHORS: Böhme, Pham, Nguyen, Roychoudhury | VENUE: CCS | METHOD: inter-procedural target distance + simulated annealing energy; patch testing + crash reproduction; OSS-Fuzz integration | RESULTS: outperforms Katch & AFL on patch testing | LIMITS: harmonic-mean target aggregation; reach≠exercise (per C5) | RELEVANCE: **High** (foundational baseline). EVIDENCE: [PDF](https://mboehme.github.io/paper/CCS17.pdf).

**P-05 KATCH** | YEAR: 2013 | AUTHORS: Marinescu, Cadar | VENUE: FSE | METHOD: symbolic execution + patch-distance heuristics | RESULTS: finds bugs at introduction time in GNU suites | LIMITS: symbolic-execution scalability | RELEVANCE: High (foundational). EVIDENCE: [PDF](https://srg.doc.ic.ac.uk/files/papers/katch-fse-13.pdf).

**P-06 SAVIOR** | YEAR: 2020 | VENUE: IEEE S&P | METHOD: bug-driven hybrid testing; 6 UB classes as SMT constraints; bug-potential seed prioritization | RESULTS: 43.4%/44.3% faster than Driller/QSYM; 243 real bugs on well-fuzzed targets in 24h | SOLVES: verifying reachable UB candidates; DOES NOT SOLVE: change conditioning | RELEVANCE: **High**. EVIDENCE: [arXiv](https://arxiv.org/abs/1906.07327).

**P-07 ParmeSan** | YEAR: 2020 | VENUE: USENIX Security | METHOD: sanitizer-instrumentation sites as DGF targets; sanitizer-agnostic retargeting | RESULTS: bugs 37% faster than Angora, 288% than AFLGo | LIMITS: global sanitizer choice, manual | RELEVANCE: High. EVIDENCE: [PDF](https://www.usenix.org/system/files/sec20-osterlund.pdf).

**P-08 Predictive Test Selection** | YEAR: 2019 | AUTHORS: Machalica et al. (Meta) | VENUE: ICSE-SEIP | METHOD: GBDT failure prediction per change×test | RESULTS: 2× cost cut; >95% failure / >99.9% faulty-change recall | LIMITS: existing tests only; flake label noise | RELEVANCE: High. EVIDENCE: [arXiv](https://arxiv.org/pdf/1810.05286).

**P-09 LIBRO** | YEAR: 2023 | AUTHORS: Kang, Yoon, Yoo | VENUE: ICSE | METHOD: LLM bug-report→reproducing test + validation/ranking | RESULTS: 33% of Defects4J bugs (32% post-cutoff) | SOLVES: feasibility of description-conditioned generation | DOES NOT SOLVE: change conditioning | RELEVANCE: High (design precedent). EVIDENCE: [arXiv](https://arxiv.org/abs/2209.11515).

**P-10 Fuzz4All** | YEAR: 2024 | AUTHORS: Xia, Paltenghi, Tian, Pradel, Zhang | VENUE: ICSE | METHOD: LLM autoprompted universal fuzzing | RESULTS: broad coverage gains across languages | LIMITS: 43% fewer inputs (GPU bottleneck); validity; not change-aware | RELEVANCE: Medium-High. EVIDENCE: [arXiv](https://arxiv.org/html/2308.04748v3).

**P-11 SEMCIA** | YEAR: 2019 | AUTHORS: Hanam et al. | VENUE: ICSME | METHOD: semantic change-impact relations for JS | RESULTS: 23–49% FP deps from Unix diff; 19–91% impact-set reduction | LIMITS: comprehension-focused, JS-only, no test action | RELEVANCE: High (motivates semantic diff features). EVIDENCE: [PDF](https://www.cs.ubc.ca/~rtholmes/papers/icsme_2019_hanam.pdf).

**P-12 Don't Look UB** | YEAR: 2023 | VENUE: PLDI | METHOD: differential oracle (sanitized vs unsanitized execution) to expose sanitizer-eliding optimizations | RESULTS: sanitizers miss bugs at -O1 (all 3 motivating bugs); optimizer removes UBSan checks | LIMITS: compiler-focused, not CI | RELEVANCE: High (justifies multi-build differential arm + "sanitizer ≠ silver bullet"). EVIDENCE: [PDF](https://download.vusec.net/papers/dontlookub_pldi23.pdf).

**Condensed records** (domain; one-line problem/method/limit):
- **Ekstazi** (A; ISSTA'14): dynamic file-dependency RTS; selects existing tests; no generation. — **STARTS/static RTS** (ISSTA'17): static RTS sometimes unsafe; method-level poor. — **RTS comparison** (JSS'21): 8.75% fault-detection loss from selection. — **RETECS** (ISSTA'17): RL prioritization; single-env adaptation. — **DeepOrder** (2021/22): DNN RTP; history-length sensitivity. — **T-TS** (2025): commit-feature TS; 15% tests, >95% failures; selection-only. — **Taming Google-scale CT** (ICSE-SEIP'17): 1.23% executions find breakages; compute-ratio objective. — **Flaky tests** (OOPSLA'20; Apple ICSE-SEIP'20): flakiness pervasive; undermines heuristics. — **DSpot/amplification** (survey '19): amplify existing tests; not change-conditioned.
- **TestPilot** (ICSE'24): LLM Java tests w/ build-run repair loop; function-level. — **CodaMosa** (ICSE'23): LLM seeds for stalled SBST; coverage-triggered. — **Meta ATG** (2024/25): LLM tests in production; flakiness filtering needed. — **LLM test-gen surveys** (2025): prompt-engineering dominance; context dilemma open. — **LLM-test flakiness/C++** (2026): C++ compilation struggle; higher flakiness than human tests.
- **FuzzGuard** (USENIX-Sec'20): DL-reachability input filtering for DGF (17.1×). — **BEACON** (S&P'22): provable path pruning. — **Sand** (2024): decoupled sanitization; overhead numbers. — **ReZZan** (ASE'22): low-overhead memory sanitizer. — **Expozzer**: dual-execution bug exposing; sanitizer limits list. — **AFL++** (2024): practical DGF platform. — **ChatAFL/TitanFuzz/FuzzGPT** (2022–24): LLM protocol/DL-library fuzzing; validity 17–27% (FuzzGPT drivers). — **ISC4DGF/Locus** (2024/25): LLM/agentic DGF seeding/predicates. — **LLM-fuzzing review** (2026): reliability, cost, reproducibility limits. — **DNN+CGF survey** (IST'25): unresolved invalid seeds & overhead.
- **QSYM** (USENIX-Sec'18): fast concolic for hybrid fuzzing; emulation-overhead diagnosis. — **KLEE** (OSDI'08), **SAGE** (CACM'12), **Driller** (NDSS'16): foundations. — **Munch/Wildfire** (2017–19): targeted hybrid; format-input failures of plain AFL/KLEE.
- **CSmith** (PLDI'11), **CLSmith** (PLDI'15), **EMI** (PLDI'14), **live mutation** (OOPSLA'16): differential program generation for compilers; UB-free generation hard. — **Metamorphic survey** (CSUR'18): oracle problem; MR authoring bottleneck. — **MetaFOE** (2026): LLM-generated metamorphic fuzz oracles; FP issues.
- **SZZ** (IWPSE'05) / **ghost commits** (TSE'21) / **AgentSZZ** (2026): BIC attribution; ~25% untraceable; LLM-agent tracing. — **Kamei JIT** (TSE'13) / **McIntosh-Kamei** (TSE'16) / **extrinsic bugs** (2021): change risk; decay; label noise. — **GumTree** (ASE'14): AST diffing substrate. — **IOC / integer overflow** (TOSEM'15): UB prevalence & intent. — **UBSan docs**: check taxonomy. — **AI-augmented CI/CD** (arXiv 2025): agentic reference architecture; weak evaluation. — **Sapienz/SapFix** (Meta, 2016–18): industrial SBST+repair; domain-specific (Android), not per-commit technique selection.

---

## Appendix B — Evidence discipline notes
- Every paper listed was located via web search in this session (URLs inline). Where author lists or venues could not be verified from the retrieved material, author names are omitted or marked, and claims are scoped to what retrieved sources state.
- Statements labeled **[INFERRED]** are analytical conclusions, not author claims.
- Unknowns: production status of AFLGo integration in OSS-Fuzz's daily pipeline; exact CI adoption rates of directed fuzzing in industry; LLM-based per-commit failure-mode classification (searched, not found — absence-of-evidence caveat applies).
