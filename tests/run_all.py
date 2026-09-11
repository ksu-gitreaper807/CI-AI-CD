"""Unit tests — plain asserts, no external deps. Run: python3 -m tests.run_all"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEMO = "/tmp/fido-demo/calcstat"

def t_planner_respects_budget_and_floors():
    from fido.plan.planner import allocate, available_arms, CLASSES
    probs = {c: 1/6 for c in CLASSES}
    arms = available_arms({"unavailable": {"msan": True, "tsan": True}})
    for policy in ("p0", "p1", "p2", "p4"):
        a = allocate(300, probs, arms, policy=policy)
        assert sum(a.values()) <= 300 + 1e-6, (policy, a)
        if policy in ("p2", "p4"):
            assert a.get("rts", 0) >= 90 - 1e-6, (policy, a)   # safety floor
    return True

def t_sanitizer_plan_fallback_and_gating():
    from fido.plan.planner import sanitizer_plan
    env = {"unavailable": {"msan": True}}
    p = sanitizer_plan({"MEM": 0.6, "UNINIT": 0.1}, env)
    assert p["MEM"] == "asan" or p["MEM"].startswith("asan"), p
    assert "unavailable" in p["UNINIT"], p                      # constraint propagated, visible
    env2 = {"unavailable": {}}
    p2 = sanitizer_plan({"MEM": 0.1, "UNINIT": 0.2}, env2)
    assert "skipped" in p2["UNINIT"], p2                        # msan cost gate below threshold
    return True

def t_triage_classifies_and_attributes():
    from fido.triage.triage import classify_finding, attribute, dedup, intent_check
    asan = {"arm": "fuzz", "kind": "sanitizer", "marker": "ERROR: AddressSanitizer",
            "stderr_tail": "ERROR: AddressSanitizer: stack-buffer-overflow\n"
                "    #0 0x55 in main /tmp/x/src/main.c:10\n"}
    ubsan = {"arm": "gen", "kind": "sanitizer", "marker": "runtime error:",
             "stderr_tail": "src/main.c:11:20: runtime error: signed integer overflow: "
                            "2147483647 + 2147483647 cannot be represented in type 'int'\n"}
    assert classify_finding(asan) == "MEM"
    assert classify_finding(ubsan) == "INT_UB"

    class FakeCR:  # minimal stand-in
        class E: pass
        entities = []
    e = FakeCR.E(); e.file = "src/main.c"; e.name = "main"; e.ast_ops = []
    FakeCR.entities = [e]
    att = attribute(asan, FakeCR)
    assert att["level"] == "high" and att["entity"] == "main.c::main", att
    att2 = attribute(ubsan, FakeCR)
    assert att2["level"] in ("medium", "high"), att2
    assert intent_check(ubsan, "INT_UB") == "suspected_genuine"
    assert intent_check({"stderr_tail": "h1 ^= h2 * 0x9e3779b9"}, "INT_UB") != "suspected_genuine"
    d = dedup([dict(asan), dict(asan)])
    assert len(d) == 1, d   # duplicate merged out of the report
    return True

def t_classifier_probs_normalized():
    from fido.predict.classifier import HeuristicScorer
    from fido.change.extractor import ChangeRecord, Entity
    cr = ChangeRecord(repo="x", commit="y", parent="z")
    e = Entity(name="f", file="a.c", op="modified")
    e.ast_ops = [("indexed_write", 1), ("bounds_check_removed", 1), ("int_arith_accumulator", 1)]
    cr.entities = [e]
    out = HeuristicScorer().predict(cr)
    s = sum(out["commit_probs"].values())
    assert abs(s - 1.0) < 0.01, s
    assert out["entity_attribution"][0]["top_class"] in out["commit_probs"]
    return True

def t_gen_produces_boundary_probes():
    from fido.exec.gen import generate_inputs
    from fido.change.extractor import ChangeRecord, Entity
    cr = ChangeRecord(repo=DEMO, commit="HEAD", parent="HEAD~1")
    e = Entity(name="main", file="src/main.c", op="modified")
    e.ast_ops = [("int_arith_accumulator", 1), ("indexed_write", 1)]
    cr.entities = [e]
    probes = generate_inputs(cr)
    kinds = {name for name, _, _ in probes}
    assert any(k.startswith("int_boundary") for k in kinds), probes
    assert any(k.startswith("oob_") for k in kinds), probes
    return True

def t_deep_guard_trigger():
    from fido.exec.concolic import triggered
    from fido.change.extractor import ChangeRecord, Entity
    cr = ChangeRecord(repo="x", commit="y", parent="z")
    e = Entity(name="f", file="a.c", op="modified")
    e.added_lines = [(10, "if (x == 0xDEADBEEF) {")]
    e.ast_ops = []
    cr.entities = [e]
    assert triggered(cr)[0] is True
    e.added_lines = [(10, "x = y + 1;")]
    assert triggered(cr)[0] is False
    return True

TESTS = [v for k, v in sorted(globals().items()) if k.startswith("t_")]

if __name__ == "__main__":
    fails = 0
    for t in TESTS:
        try:
            t(); print(f"PASS {t.__name__}")
        except Exception as ex:
            fails += 1; print(f"FAIL {t.__name__}: {ex}")
    sys.exit(1 if fails else 0)
