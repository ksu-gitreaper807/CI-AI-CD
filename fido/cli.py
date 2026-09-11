"""CLI: python3 -m fido run <repo> <commit> --budget 900 --policy p4"""
import argparse
from fido.pipeline import run as run_pipeline


def main():
    ap = argparse.ArgumentParser(prog="fido")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("repo")
    r.add_argument("commit", default="HEAD", nargs="?")
    r.add_argument("--budget", type=float, default=900.0, help="CPU-second budget")
    r.add_argument("--policy", default="p4", choices=["p0", "p1", "p2", "p4"])
    r.add_argument("--out", default=None)
    a = ap.parse_args()
    run_pipeline(a.repo, a.commit, budget_s=a.budget, policy=a.policy, out_dir=a.out)


if __name__ == "__main__":
    main()
