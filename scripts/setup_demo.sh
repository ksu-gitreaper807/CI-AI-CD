#!/usr/bin/env bash
# Creates /tmp/fido-demo/calcstat — a tiny C project whose history contains a
# REAL bug-inducing commit (unbounded array write = MEM; int accumulation of
# user input = INT_UB). The regression suite is deliberately blind to both.
set -euo pipefail
ROOT=/tmp/fido-demo/calcstat
rm -rf /tmp/fido-demo && mkdir -p "$ROOT/src" "$ROOT/include" "$ROOT/tests/inputs"

git -C "$ROOT" init -q
git -C "$ROOT" config user.email demo@fido && git -C "$ROOT" config user.name demo

cat > "$ROOT/include/stats.h" <<'EOF'
#ifndef STATS_H
#define STATS_H
double mean(const int *v, int n);
double variance(const int *v, int n);
#endif
EOF

# ---- commit 1: initial safe version ---------------------------------------
cat > "$ROOT/src/main.c" <<'EOF'
#include <stdio.h>
#include "stats.h"
#define MAX_VALUES 64
int main(void) {
    int values[MAX_VALUES];
    int n = 0;
    long long total = 0;
    int x;
    while (n < MAX_VALUES && scanf("%d", &x) == 1) {
        values[n++] = x;
        total += x;
    }
    if (n == 0) { printf("no input\n"); return 1; }
    printf("count=%d sum=%lld mean=%.2f\n", n, total, mean(values, n));
    return 0;
}
EOF
cat > "$ROOT/src/stats.c" <<'EOF'
#include "stats.h"
double mean(const int *v, int n) {
    if (n <= 0) return 0.0;
    long long s = 0;
    for (int i = 0; i < n; i++) s += v[i];
    return (double)s / n;
}
EOF
echo "3
4
5" > "$ROOT/tests/inputs/small.txt"
echo "1
2" > "$ROOT/tests/inputs/tiny.txt"
cat > "$ROOT/tests/manifest.json" <<'EOF'
[
  {"name": "test_small",   "stdin": "tests/inputs/small.txt", "expect_regex": "count=3 sum=12 mean=4\\.00"},
  {"name": "test_tiny",    "stdin": "tests/inputs/tiny.txt",  "expect_regex": "count=2 sum=3 mean=1\\.50"}
]
EOF
cat > "$ROOT/tests/coverage_map.json" <<'EOF'
{
  "test_small": ["src/main.c", "src/stats.c"],
  "test_tiny":  ["src/main.c", "src/stats.c"]
}
EOF
GIT_AUTHOR_DATE="2026-05-02T10:00:00" GIT_COMMITTER_DATE="2026-05-02T10:00:00" \
  git -C "$ROOT" add -A && GIT_AUTHOR_DATE="2026-05-02T10:00:00" GIT_COMMITTER_DATE="2026-05-02T10:00:00" \
  git -C "$ROOT" commit -qm "initial calcstat: bounded input, long long accumulation"

# ---- commit 2: add variance (clean) ----------------------------------------
cat > "$ROOT/src/stats.c" <<'EOF'
#include "stats.h"
double mean(const int *v, int n) {
    if (n <= 0) return 0.0;
    long long s = 0;
    for (int i = 0; i < n; i++) s += v[i];
    return (double)s / n;
}
double variance(const int *v, int n) {
    if (n < 2) return 0.0;              /* guard: division by (n-1) */
    long long s = 0;
    for (int i = 0; i < n; i++) s += v[i];
    double m = (double)s / n;
    double acc = 0.0;
    for (int i = 0; i < n; i++) acc += ((double)v[i] - m) * ((double)v[i] - m);
    return acc / (n - 1);
}
EOF
python3 - "$ROOT" <<'PY'
import sys, json, os
root = sys.argv[1]
p = os.path.join(root, "src/main.c")
s = open(p).read()
s = s.replace('printf("count=%d sum=%lld mean=%.2f\\n", n, total, mean(values, n));',
              'printf("count=%d sum=%lld mean=%.2f var=%.2f\\n", n, total, mean(values, n), variance(values, n));')
open(p, "w").write(s)
m = os.path.join(root, "tests/manifest.json")
data = json.load(open(m))
for t in data:
    t["expect_regex"] = t["expect_regex"] + r"\s.*var="
json.dump(data, open(m, "w"), indent=2)
PY
GIT_AUTHOR_DATE="2026-06-15T10:00:00" GIT_COMMITTER_DATE="2026-06-15T10:00:00" \
  git -C "$ROOT" add -A && GIT_AUTHOR_DATE="2026-06-15T10:00:00" GIT_COMMITTER_DATE="2026-06-15T10:00:00" \
  git -C "$ROOT" commit -qm "add variance with n<2 guard"

# ---- commit 3: THE BUG-INDUCING COMMIT (both bugs) --------------------------
cat > "$ROOT/src/main.c" <<'EOF'
#include <stdio.h>
#include "stats.h"
#define MAX_VALUES 64
int main(void) {
    int values[MAX_VALUES];
    int n = 0;
    int total = 0;
    int x;
    while (scanf("%d", &x) == 1) {
        values[n++] = x;
        total += x;
    }
    if (n == 0) { printf("no input\n"); return 1; }
    printf("count=%d sum=%d mean=%.2f var=%.2f\n", n, total, mean(values, n), variance(values, n));
    return 0;
}
EOF
GIT_AUTHOR_DATE="2026-08-20T10:00:00" GIT_COMMITTER_DATE="2026-08-20T10:00:00" \
  git -C "$ROOT" add -A && GIT_AUTHOR_DATE="2026-08-20T10:00:00" GIT_COMMITTER_DATE="2026-08-20T10:00:00" \
  git -C "$ROOT" commit -qm "optimize accumulation, lift artificial input limits"

git -C "$ROOT" log --oneline
echo "demo repo ready at $ROOT"
