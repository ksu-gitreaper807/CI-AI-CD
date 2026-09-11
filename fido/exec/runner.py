"""Sandboxed, budget-metered process runner.

MVP isolation: rlimits (CPU, address space) + wall-clock timeout in a child
process. Production deployment swaps this for Docker/gVisor/VM per-arm; the
interface (cmd, stdin) -> (rc, stdout, stderr, elapsed) is what matters.
"""
from __future__ import annotations

import resource
import subprocess
import time


def run(cmd: list, stdin_data: bytes = b"", timeout_s: float = 5.0,
        cpu_s: float = 5.0, mem_mb: int | None = None):
    # NOTE: RLIMIT_AS is opt-in: sanitizer runtimes reserve terabytes of VIRTUAL
    # address space by design, so a small RLIMIT_AS kills ASan/MSan immediately.
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_s), int(cpu_s) + 1))
        if mem_mb:
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input=stdin_data, capture_output=True,
                           timeout=timeout_s, preexec_fn=limit)
        return p.returncode, p.stdout, p.stderr, time.time() - t0
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or b"", (e.stderr or b"") + b"[fido: wall-timeout]", time.time() - t0
    except MemoryError:
        return 137, b"", b"[fido: memory limit]", time.time() - t0


def sanitize_markers(stderr: bytes) -> str | None:
    s = stderr.decode("utf-8", "replace")
    for marker in ("ERROR: AddressSanitizer", "ERROR: LeakSanitizer",
                   "WARNING: ThreadSanitizer", "ERROR: MemorySanitizer",
                   "runtime error:"):
        if marker in s:
            return marker
    return None
