"""S1 — Change Extraction: git push -> ChangeRecord.

Implements the representation ladder from SYSTEM_ARCHITECTURE.md §2 with
dependency-free heuristics for C/C++:
  L0 textual diff (git)
  L1 entity diff  (function-level; AST-edit-op heuristics on +/- lines)
  L2 affected set (call-site grep of changed function names)
  L3 risk lexicon (per-entity lexical precursors of each failure class)
  L4 history      (churn via git log; prior-BICs requires labels -> 0 unknown)
  L5 coverage map (tests touching changed files; from repo's tests/coverage_map.json)

KNOWN LIMITATIONS (documented, honest): heuristics, not tree-sitter/GumTree;
production swaps this module out behind the same ChangeRecord contract.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field


# ---------------------------------------------------------------- L1/L3 tables

# AST-edit-op heuristics. Each: (op_name, regex applied to added/removed lines)
ADD_OPS = [
    ("indexed_write",        re.compile(r"\w+\s*\[[^\]]*\]\s*(\+\+|--)?\s*=[^=]")),
    ("indexed_read",         re.compile(r"\w+\s*\[[^\]]+\]")),
    ("unbounded_copy",       re.compile(r"\b(memcpy|strcpy|strcat|sprintf|gets|alloca)\b")),
    ("int_arith_accumulator",re.compile(r"\b\w+\s*(\+=|-=)\b")),
    ("shift_op",             re.compile(r"(<<|>>)=?\s*\w")),
    ("div_op",               re.compile(r"[^/](/|%=)[^/=]")),
    ("mul_op",               re.compile(r"[^/*](\*{1})[^/=]")),
    ("lock_op",              re.compile(r"\b(pthread_mutex_\w+|mtx_\w+|lock_guard)\b")),
    ("atomic_op",            re.compile(r"\b(atomic_\w+|std::atomic|__sync_\w+)\b")),
    ("iterator_op",          re.compile(r"\b(begin\(\)|end\(\)|erase|insert|push_back)\b")),
    ("alloc_call",           re.compile(r"\b(malloc|calloc|realloc|new\s+\w)")),
    ("free_call",            re.compile(r"\b(free|delete\s)")),
    ("condition_changed",    re.compile(r"\b(if|while|for)\b|\?")),
    ("function_call_added",  re.compile(r"=\s*\w+\s*\(|^\s*\w+\s*\(")),
    ("type_narrowing_int",   None),   # cross-side, computed above (no line regex)
]
REMOVE_OPS = [
    ("bounds_check_removed", re.compile(r"<\s*\w*(MAX|LIMIT|SIZE|CAP|BOUND|LEN)\w*")),
    ("null_check_removed",   re.compile(r"if\s*\(.*==\s*NULL|!=\s*NULL|nullptr")),
    ("condition_changed",    re.compile(r"\b(if|while|for)\b")),
]
def strip_comments(line: str, state: dict) -> str:
    """Minimal C comment stripper with cross-line block-comment state.
    Prevents English words in comments (if/for/shift...) from becoming
    false AST-edit-op evidence. String literals are preserved verbatim."""
    out, i = [], 0
    while i < len(line):
        if state.get("block"):
            j = line.find("*/", i)
            if j == -1:
                return "".join(out)
            state["block"] = False
            i = j + 2
            continue
        if line.startswith("//", i):
            break
        if line.startswith("/*", i):
            state["block"] = True
            i += 2
            continue
        if line[i] == '"':
            j = i + 1
            while j < len(line) and line[j] != '"':
                j += 2 if line[j] == "\\" else 1
            out.append(line[i:min(j + 1, len(line))]); i = j + 1
            continue
        out.append(line[i]); i += 1
    return "".join(out)


# class-weight matrix for the Tier-A scorer (fido/predict). Rows: ops -> classes.
OP_CLASS_WEIGHTS = {
    "indexed_write":        {"MEM": 3.0},
    "unbounded_copy":       {"MEM": 3.0},
    "bounds_check_removed": {"MEM": 2.5, "LOGIC": 0.5},
    "null_check_removed":   {"MEM": 1.0},
    "alloc_call":           {"MEM": 0.8, "UNINIT": 0.6},
    "free_call":            {"MEM": 0.8, "LIFETIME": 1.2},
    "int_arith_accumulator":{"INT_UB": 2.2},
    "shift_op":             {"INT_UB": 1.6},
    "div_op":               {"INT_UB": 1.2},
    "mul_op":               {"INT_UB": 0.8},
    "iterator_op":          {"LIFETIME": 2.0},
    "lock_op":              {"CONC": 2.2},
    "atomic_op":            {"CONC": 1.8},
    "condition_changed":    {"LOGIC": 1.6},
    "type_narrowing_int":   {"INT_UB": 3.0},
}
CLASSES = ["MEM", "UNINIT", "INT_UB", "LIFETIME", "CONC", "LOGIC"]


def run_git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True, check=True).stdout


@dataclass
class Entity:
    name: str
    file: str
    op: str                       # added | modified
    start_line: int = 0
    end_line: int = 0
    added_lines: list = field(default_factory=list)
    removed_lines: list = field(default_factory=list)
    ast_ops: list = field(default_factory=list)
    risk: dict = field(default_factory=dict)
    called_by: list = field(default_factory=list)


@dataclass
class ChangeRecord:
    repo: str
    commit: str
    parent: str
    entities: list = field(default_factory=list)
    touched_files: list = field(default_factory=list)
    history: dict = field(default_factory=dict)
    coverage_map: dict = field(default_factory=dict)
    degraded: bool = False

    def to_dict(self) -> dict:
        return {
            "commit": self.commit, "parent": self.parent,
            "touched_files": self.touched_files,
            "entities": [{"name": e.name, "file": e.file, "op": e.op,
                          "ast_ops": [o for o, _ in e.ast_ops],
                          "risk": e.risk, "called_by": e.called_by} for e in self.entities],
            "history": self.history,
            "degraded": self.degraded,
        }


# ------------------------------------------------------------------ L1 parsing

FUNC_DEF = re.compile(
    r"^(?:static\s+|inline\s+|extern\s+)*(?:[\w\*]+\s+)+\**(\w+)\s*\([^;{)]*\)\s*\{?\s*$")


def functions_of_file(text: str) -> list:
    """Return [(func_name, start_line, end_line)] for C-ish files (heur. brace scan)."""
    out, depth, cur, start = [], 0, None, 0
    for i, line in enumerate(text.splitlines(), 1):
        if cur is None:
            m = FUNC_DEF.match(line)
            if m:
                cur, start = m.group(1), i
                depth = line.count("{") - line.count("}")
                if depth > 0:
                    continue
                if "{" in line and "}" in line and line.count("}") >= line.count("{"):
                    out.append((cur, start, i)); cur = None
                continue
        else:
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                out.append((cur, start, i)); cur, depth = None, 0
    return out


def enclosing_function(funcs: list, lineno: int):
    for name, a, b in funcs:
        if a <= lineno <= b:
            return name
    return None


def parse_diff(repo: str, commit: str, parent: str) -> dict:
    """Return {file: {'added': [(lineno, text)], 'removed': [(lineno, text)]}}."""
    diff = run_git(repo, "diff", f"{parent}..{commit}", "--unified=3", "--")
    files: dict = {}
    cur_file, new_ln = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[6:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_ln = int(m.group(1)) if m else 0
        elif cur_file and line.startswith("+") and not line.startswith("+++"):
            files.setdefault(cur_file, {"added": [], "removed": []})["added"].append((new_ln, line[1:]))
            new_ln += 1
        elif cur_file and line.startswith("-") and not line.startswith("---"):
            files.setdefault(cur_file, {"added": [], "removed": []})["removed"].append((new_ln, line[1:]))
        elif line.startswith(" "):
            new_ln += 1
    return files


# --------------------------------------------------------------------- main API

def extract(repo: str, commit: str) -> ChangeRecord:
    parent = run_git(repo, "rev-parse", f"{commit}^").strip()
    files = parse_diff(repo, commit, parent)
    cr = ChangeRecord(repo=repo, commit=run_git(repo, "rev-parse", commit).strip(),
                      parent=parent, touched_files=sorted(files))

    for path, hunks in files.items():
        if not re.search(r"\.(c|cc|cpp|h|hpp)$", path):
            continue
        try:
            src = run_git(repo, "show", f"{commit}:{path}")
        except subprocess.CalledProcessError:
            cr.degraded = True
            continue
        funcs = functions_of_file(src)
        buckets: dict = {}
        added_set = set(hunks["added"])
        for lineno, text in hunks["added"] + hunks["removed"]:
            fname = enclosing_function(funcs, lineno)
            buckets.setdefault(fname, {"added": [], "removed": []})
            buckets[fname]["added" if (lineno, text) in added_set else "removed"].append(text)

        func_ranges = {n: (a, b) for n, a, b in funcs}
        cstate = {"block": False}
        for fname, hb in buckets.items():
            hb = {"added": [strip_comments(t, cstate) for t in hb["added"]],
                  "removed": [strip_comments(t, cstate) for t in hb["removed"]]}
            a, b = func_ranges.get(fname, (0, 0))
            ent = Entity(name=fname or f"<toplevel>@{path}", file=path,
                         op="modified" if fname else "added",
                         start_line=a, end_line=b)
            ent.added_lines = hb["added"]; ent.removed_lines = hb["removed"]
            ops = []
            FLOATISH = re.compile(r"\b(double|float)\b")
            INT_OPS = {"int_arith_accumulator", "mul_op", "shift_op", "div_op"}
            for text in hb["added"]:
                float_line = bool(FLOATISH.search(text))
                for op, rx in ADD_OPS:
                    if rx is not None and rx.search(text):
                        if float_line and op in INT_OPS:
                            continue   # FP guard: double/float arithmetic is not int UB
                        ops.append(op)
            for text in hb["removed"]:
                for op, rx in REMOVE_OPS:
                    if rx.search(text):
                        ops.append(op)
            # accumulator needs an int-typed target in the file
            for op in list(ops):
                if op == "int_arith_accumulator":
                    m = re.search(r"(\w+)\s*\+=", "".join(hb["added"]))
                    if m and re.search(rf"\bint\s+{re.escape(m.group(1))}\b", src):
                        ops.append("int_typed_target")
                    else:
                        ops.remove(op)
            # cross-side type narrowing: added 'int X' where removed had 'long ... X'
            added_text = "\n".join(hb["added"])
            removed_text = "\n".join(hb["removed"])
            for m2 in re.finditer(r"\b(?:unsigned\s+|signed\s+)?int\s+(\w+)\s*[=;\[]", added_text):
                if re.search(rf"\b(?:long\s+long|long|size_t|ssize_t|int64_t|uint64_t)\s+{re.escape(m2.group(1))}\b",
                             removed_text):
                    ops.append("type_narrowing_int")
            dedup = list(dict.fromkeys(ops))
            ent.ast_ops = [(o, 1) for o in dedup]
            ent.risk = {c: sum(OP_CLASS_WEIGHTS.get(o, {}).get(c, 0) for o in dedup)
                        for c in CLASSES}
            ent.risk = {c: v for c, v in ent.risk.items() if v > 0}
            cr.entities.append(ent)

    # L2: affected set — who calls the changed functions
    all_src = {}
    for path in run_git(repo, "ls-files").splitlines():
        if re.search(r"\.(c|cc|cpp|h|hpp)$", path):
            try:
                all_src[path] = run_git(repo, "show", f"{commit}:{path}")
            except subprocess.CalledProcessError:
                pass
    for ent in cr.entities:
        if ent.name == "<toplevel>@%s" % ent.file:
            continue
        rx = re.compile(rf"\b{re.escape(ent.name)}\s*\(")
        for path, text in all_src.items():
            if path != ent.file and rx.search(text):
                ent.called_by.append(path)

    # L4: history features (churn over 90d on touched files)
    churn = 0
    for path in cr.touched_files:
        try:
            n = run_git(repo, "log", "--since=90.days", "--oneline", "--", path)
            churn += len(n.strip().splitlines()) if n.strip() else 0
        except subprocess.CalledProcessError:
            pass
    cr.history = {"churn_90d": churn, "prior_bics": 0}  # prior_bics needs labels

    # L5: coverage map, if the project ships one
    try:
        cr.coverage_map = json.loads(run_git(repo, "show", f"{commit}:tests/coverage_map.json"))
    except Exception:
        cr.coverage_map = {}
    return cr
