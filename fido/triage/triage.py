"""S5 — Failure normalization, change attribution, dedup, intent filter.

Attribution answers 'is this MY bug': finding frames are matched against
changed entities (high: file+function hit; medium: file hit; low: neither).
Intent filter encodes the IOC lesson (Dietz et al., TOSEM'15): intentional
wraparound is common, so INT_UB findings are checked for hash-idiom patterns
and labeled 'suspected intentional' rather than silently dropped.
"""
from __future__ import annotations

import hashlib
import re

CLASSES = ["MEM", "UNINIT", "INT_UB", "LIFETIME", "CONC", "LOGIC"]

ASAN_RX = re.compile(r"ERROR: AddressSanitizer: ([\w\-]+)")
FRAME_RX = re.compile(r"#\d+\s+0x[0-9a-f]+\s+in\s+(\S+)\s+(\S+?):(\d+)")
UBSAN_RX = re.compile(r"(\S+?):(\d+):(\d+):\s+runtime error:\s+(.+)")
INTENT_HASH_IDIOM = re.compile(r"0x9e3779b9|\^=|hash|\bh1\b|\bh2\b|>>>\s|mix\(")

SEVERITY = {"MEM": 3, "CONC": 3, "LIFETIME": 2, "INT_UB": 2, "UNINIT": 2, "LOGIC": 1}


def classify_finding(f: dict) -> str:
    text = (f.get("marker") or "") + (f.get("stderr_tail") or "")
    if "AddressSanitizer" in text:
        return "MEM"
    if "MemorySanitizer" in text:
        return "UNINIT"
    if "ThreadSanitizer" in text:
        return "CONC"
    if "runtime error" in text:
        # memory-safety-shaped UB first (OOB index/pointer arithmetic/load-store)
        if re.search(r"out of bounds|index .* out of bounds|"
                     r"(load|store) of address|member (call|access) on address|"
                     r"applying non-zero offset|null pointer", text):
            return "MEM"
        if re.search(r"signed integer overflow|unsigned integer overflow|shift|"
                     r"division by zero|out of range|implicit conversion|"
                     r"pointer-overflow|misaligned", text):
            return "INT_UB"
        if re.search(r"member call on address|vptr|downcast", text):
            return "LIFETIME"
    if f.get("kind") == "diff_violation":
        return "INT_UB"  # optimizer-sensitive = UB until proven otherwise
    if f.get("kind") == "test_fail":
        return "LOGIC"
    return "LOGIC"


def _frames(f: dict) -> list:
    frames = FRAME_RX.findall(f.get("stderr_tail", ""))
    if not frames and f.get("stderr_tail"):
        m = UBSAN_RX.search(f["stderr_tail"])
        if m:
            frames = [(f"<ubsan>", m.group(1), m.group(2))]
    return frames


def _line_in_changed_entity(path: str, line: str, cr) -> str | None:
    """Return changed entity whose [start,end] range covers `line` (basename path match)."""
    try:
        ln = int(line)
    except (TypeError, ValueError):
        return None
    short = path.split("/")[-1]
    for e in cr.entities:
        if e.file.split("/")[-1] == short and getattr(e, "start_line", None) and \
                e.start_line <= ln <= (e.end_line or e.start_line):
            return e.name
    return None


def attribute(f: dict, cr) -> dict:
    frames = _frames(f)
    changed_files = {e.file for e in cr.entities}
    changed_funcs = {e.name for e in cr.entities if not e.name.startswith("<toplevel")}
    # frameless reports (UBSan single-location): match by changed-entity line range
    m = UBSAN_RX.search(f.get("stderr_tail", ""))
    if m:
        ent = _line_in_changed_entity(m.group(1), m.group(2), cr)
        if ent:
            return {"level": "high", "entity": f"{m.group(1).split('/')[-1]}::{ent}",
                    "line": m.group(2)}
    for func, path, line in frames:
        short = path.split("/")[-1]
        func_clean = func.split("(")[0]
        file_hit = any(cf.split("/")[-1] == short for cf in changed_files)
        if file_hit and func_clean in changed_funcs:
            return {"level": "high", "entity": f"{short}::{func_clean}", "line": line}
    for func, path, line in frames:
        if any(cf.split("/")[-1] == path.split("/")[-1] for cf in changed_files):
            return {"level": "medium", "entity": path.split("/")[-1], "line": line}
    return {"level": "low", "entity": frames[0][1] if frames else "unknown",
            "line": frames[0][2] if frames else "?"}


def dedup(findings: list) -> list:
    seen, out = set(), []
    for f in findings:
        frames = _frames(f)
        key_frames = tuple(sorted((fn.split("/")[-1], ln) for fn, ln, _ in frames[:2])) or \
                     (f.get("test") or f.get("input_ref") or f.get("label") or "?",)
        key = (classify_finding(f), key_frames)
        if key in seen:
            f["duplicate_of_prior"] = True
            continue
        seen.add(key)
        out.append(f)
    return out


def intent_check(f: dict, cls: str) -> str:
    if cls != "INT_UB":
        return "n/a"
    src_context = (f.get("stderr_tail") or "") + (f.get("input") or "")
    if INTENT_HASH_IDIOM.search(src_context):
        return "suspected_intentional (hash idiom)"
    return "suspected_genuine"


def triage(raw_findings: list, cr) -> list:
    out = []
    for f in dedup(raw_findings):
        cls = classify_finding(f)
        att = attribute(f, cr)
        out.append({
            "class": cls,
            "severity": SEVERITY[cls],
            "attribution": att,
            "intent": intent_check(f, cls),
            "arm": f.get("arm"),
            "kind": f.get("kind"),
            "evidence": (f.get("stderr_tail") or "")[-600:],
            "input": f.get("input", f.get("input_ref", f.get("test", ""))),
            "raw_label": f.get("label", ""),
        })
    out.sort(key=lambda x: (-x["severity"], {"high": 0, "medium": 1, "low": 2}[x["attribution"]["level"]]))
    for i, f in enumerate(out, 1):
        f["id"] = f"F{i}"
    return out


def stack_hash(f: dict) -> str:
    frames = _frames(f)
    return hashlib.sha1(repr(frames[:3]).encode()).hexdigest()[:12]
