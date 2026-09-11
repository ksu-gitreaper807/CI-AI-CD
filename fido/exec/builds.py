"""Build orchestration: sanitizer-variant builds with caching + capability probe."""
from __future__ import annotations

import hashlib
import os
import subprocess
import time

SAN_FLAGS = {
    "asan":  ["-fsanitize=address"],
    "ubsan": ["-fsanitize=undefined", "-fno-sanitize-recover=all"],
    "a+u":   ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"],
    "tsan":  ["-fsanitize=thread"],
    "msan":  ["-fsanitize=memory"],
    "plain": [],
}


def _cc() -> str:
    return os.environ.get("FIDO_CC", "gcc")


def probe_sanitizers() -> dict:
    """Compile-and-run a probe per sanitizer; unavailable variants propagate to
    the planner as hard constraints (never allocated, never 'hoped for')."""
    probe_c = "int main(void){return 0;}\n"
    out = {}
    tmp = "/tmp/fido_probe.c"
    with open(tmp, "w") as f:
        f.write(probe_c)
    for name in ("asan", "ubsan", "tsan", "msan"):
        flags = SAN_FLAGS["a+u"] if name in ("asan", "ubsan") else SAN_FLAGS[name]
        exe = f"/tmp/fido_probe_{name}"
        try:
            r = subprocess.run([_cc(), *flags, tmp, "-o", exe], capture_output=True, timeout=30)
            if r.returncode != 0:
                out[name] = False
                continue
            r2 = subprocess.run([exe], capture_output=True, timeout=15)
            out[name] = (r2.returncode == 0)
        except Exception:
            out[name] = False
    out["plain"] = True
    return out


def build(repo: str, commit: str, variant: str, cache_dir: str, ledger=None) -> str:
    """Compile the project at `commit` with the given variant's flags.
    Returns path to built binary. Cache key: (commit, variant). Source blobs
    are materialized from git (working tree may be at another commit). MVP
    assumes src/*.c + include/ layout — production needs per-build-system
    adapters. Sanitizer variant 'sanitized' = ASan+UBSan combined."""
    cc = _cc()
    key = hashlib.sha1(f"{repo}:{commit}:{variant}".encode()).hexdigest()[:16]
    exe = os.path.join(cache_dir, f"bin_{key}")
    if os.path.exists(exe):
        return exe
    bdir = os.path.join(cache_dir, f"src_{key}")
    srcs, inc = _materialize(repo, commit, bdir)
    if not srcs:
        raise RuntimeError(f"no C sources found at {commit} in {repo}")
    cmd = [cc, "-O1" if variant not in ("O0", "O2") else "-" + variant,
           "-g", "-fno-omit-frame-pointer", "-std=c11", "-I", inc]
    if variant == "sanitized":
        cmd += SAN_FLAGS["a+u"]
    elif variant in SAN_FLAGS:
        cmd += SAN_FLAGS[variant]
    args = cmd + srcs + ["-o", exe, "-lm"]
    t0 = time.time()
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"build failed ({variant}):\n{r.stderr[-2000:]}")
    if ledger:
        ledger.debit(f"build:{variant}", "build", time.time() - t0, f"{len(srcs)} TUs")
    return exe


def _materialize(repo: str, commit: str, bdir: str):
    os.makedirs(os.path.join(bdir, "src"), exist_ok=True)
    os.makedirs(os.path.join(bdir, "include"), exist_ok=True)
    out = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", commit],
                         capture_output=True, text=True, check=True).stdout
    srcs, inc = [], os.path.join(bdir, "include")
    for p in out.splitlines():
        if not (p.startswith("src/") and p.endswith(".c")) and \
           not (p.startswith("include/") and p.endswith(".h")):
            continue
        blob = subprocess.run(["git", "-C", repo, "show", f"{commit}:{p}"],
                              capture_output=True, check=True).stdout
        dst = os.path.join(bdir, p)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(blob)
        if p.endswith(".c"):
            srcs.append(dst)
    return srcs, inc
