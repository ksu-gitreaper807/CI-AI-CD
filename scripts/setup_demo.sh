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


# ---- commit 4: THE FIX (restore bounds + 64-bit accumulation) ---------------
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
    printf("count=%d sum=%lld mean=%.2f var=%.2f\n", n, total, mean(values, n), variance(values, n));
    return 0;
}
EOF
GIT_AUTHOR_DATE="2026-09-01T10:00:00" GIT_COMMITTER_DATE="2026-09-01T10:00:00" \
  git -C "$ROOT" add -A && GIT_AUTHOR_DATE="2026-09-01T10:00:00" GIT_COMMITTER_DATE="2026-09-01T10:00:00" \
  git -C "$ROOT" commit -qm "restore input bounds and 64-bit accumulation (fixes regression)"

# ---- commit 5: hash combine (INT_UB via signed shift, hash-idiom context) ----
cat > "$ROOT/src/stats.c" <<'EOF'
#include "stats.h"
double mean(const int *v, int n) {
    if (n <= 0) return 0.0;
    long long s = 0;
    for (int i = 0; i < n; i++) s += v[i];
    return (double)s / n;
}
double variance(const int *v, int n) {
    if (n < 2) return 0.0;
    long long s = 0;
    for (int i = 0; i < n; i++) s += v[i];
    double m = (double)s / n;
    double acc = 0.0;
    for (int i = 0; i < n; i++) acc += ((double)v[i] - m) * ((double)v[i] - m);
    return acc / (n - 1);
}
int hash_combine(int h, int value) {
    h ^= value + 0x9e3779b9 + (h << 6) + (h >> 2);   /* boost-style hash combine */
    return h;
}
unsigned int hash_values(const int *v, int n) {
    int h = 17;
    for (int i = 0; i < n; i++) h = hash_combine(h, v[i]);
    return (unsigned int) h;
}
EOF
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
    printf("count=%d sum=%lld mean=%.2f var=%.2f hash=%u\n",
           n, total, mean(values, n), variance(values, n), hash_values(values, n));
    return 0;
}
EOF
cat > "$ROOT/tests/manifest.json" <<'EOF'
[
  {"name": "test_small", "stdin": "tests/inputs/small.txt", "expect_regex": "count=3 sum=12 mean=4\\.00\\s.*var=[0-9.]+.*hash=[0-9]+"},
  {"name": "test_tiny",  "stdin": "tests/inputs/tiny.txt",  "expect_regex": "count=2 sum=3 mean=1\\.50\\s.*var=[0-9.]+.*hash=[0-9]+"}
]
EOF
GIT_AUTHOR_DATE="2026-09-05T10:00:00" GIT_COMMITTER_DATE="2026-09-05T10:00:00" \
  git -C "$ROOT" add -A && GIT_AUTHOR_DATE="2026-09-05T10:00:00" GIT_COMMITTER_DATE="2026-09-05T10:00:00" \
  git -C "$ROOT" commit -qm "add deterministic content hash for checksums"

# ---- commit 6: magic-guarded mode (deep-guard trigger; dormant UB) -----------
python3 - "$ROOT" <<'PY2'
import sys, os
root = sys.argv[1]
p = os.path.join(root, "src/main.c")
s = open(p).read()
anchor = "        values[n++] = x;"
nl = chr(10)
guard = ("        if (x == 0x5F3759DF) {" + nl +
         "            int secret = x + 2147483647;" + nl +
         '            printf("secret mode unlocked: %d' + chr(92) + 'n", secret);' + nl +
         "            continue;" + nl +
         "        }" + nl)
s = s.replace(anchor, guard + anchor, 1)
open(p, "w").write(s)
PY2
GIT_AUTHOR_DATE="2026-09-10T10:00:00" GIT_COMMITTER_DATE="2026-09-10T10:00:00" \
  git -C "$ROOT" add -A && GIT_AUTHOR_DATE="2026-09-10T10:00:00" GIT_COMMITTER_DATE="2026-09-10T10:00:00" \
  git -C "$ROOT" commit -qm "add magic-value developer backdoor for secret mode"

git -C "$ROOT" log --oneline
echo "demo repo ready at $ROOT"
