import argparse
import csv
import glob
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rppg_poc as rp
REFS_PATH = os.path.join(rp.LOG_DIR, "refs.csv")
def load_sessions(pattern, valid_only, tail_sec):
    sessions = {}
    for path in sorted(glob.glob(pattern)):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        tag = rows[-1]["tag"]
        end = float(rows[-1]["elapsed_s"])
        vals = [
            float(r["bpm"])
            for r in rows
            if (not valid_only or r["valid"] == "1") and (tail_sec <= 0 or float(r["elapsed_s"]) >= end - tail_sec)
        ]
        if not vals:
            print("no usable rows: {}".format(os.path.basename(path)))
            continue
        key = "{}|{}".format(tag, os.path.basename(path))
        sessions[key] = {"tag": tag, "file": os.path.basename(path), "bpm": float(np.median(vals)), "n": len(vals), "spread": float(np.std(vals))}
    return sessions
def load_refs():
    if not os.path.exists(REFS_PATH):
        return {}
    with open(REFS_PATH, newline="", encoding="utf-8") as f:
        return {r["key"]: float(r["ref_bpm"]) for r in csv.DictReader(f) if r["ref_bpm"]}
def save_refs(refs):
    os.makedirs(rp.LOG_DIR, exist_ok=True)
    with open(REFS_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "ref_bpm"])
        for k, v in refs.items():
            w.writerow([k, v])
def bland_altman(est, ref, labels, out_path):
    est = np.asarray(est, dtype=float)
    ref = np.asarray(ref, dtype=float)
    diff = est - ref
    mean = (est + ref) / 2.0
    bias = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1)) if len(diff) > 1 else 0.0
    lo, hi = bias - 1.96 * sd, bias + 1.96 * sd
    mae = float(np.mean(np.abs(diff)))
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    ax = axes[0]
    ax.scatter(mean, diff, c="tab:blue")
    for m, d, lb in zip(mean, diff, labels):
        ax.annotate(lb, (m, d), fontsize=7, alpha=0.7)
    ax.axhline(bias, color="tab:red")
    ax.axhline(lo, color="gray", ls="--")
    ax.axhline(hi, color="gray", ls="--")
    ax.axhspan(-5, 5, color="tab:green", alpha=0.08)
    ax.set_xlabel("mean of rPPG and reference (BPM)")
    ax.set_ylabel("rPPG - reference (BPM)")
    ax.set_title("Bland-Altman  bias={:.2f}  LoA=[{:.2f}, {:.2f}]".format(bias, lo, hi))
    ax = axes[1]
    lim = [min(est.min(), ref.min()) - 5, max(est.max(), ref.max()) + 5]
    ax.plot(lim, lim, color="gray", ls="--")
    ax.scatter(ref, est, c="tab:orange")
    for r, e, lb in zip(ref, est, labels):
        ax.annotate(lb, (r, e), fontsize=7, alpha=0.7)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("reference BPM")
    ax.set_ylabel("rPPG BPM")
    ax.set_title("MAE={:.2f}  RMSE={:.2f}  n={}".format(mae, rmse, len(diff)))
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    return {"bias": bias, "sd": sd, "loa": (lo, hi), "mae": mae, "rmse": rmse, "within5": int(np.sum(np.abs(diff) <= 5))}
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pattern", default=os.path.join(rp.LOG_DIR, "session_*.csv"))
    p.add_argument("--tail-sec", type=float, default=0.0)
    p.add_argument("--all-rows", action="store_true")
    p.add_argument("--no-prompt", action="store_true")
    p.add_argument("--out", default=os.path.join(rp.LOG_DIR, "bland_altman.png"))
    args = p.parse_args()
    sessions = load_sessions(args.pattern, not args.all_rows, args.tail_sec)
    if not sessions:
        print("no sessions matched: {}".format(args.pattern))
        return
    refs = load_refs()
    for key, s in sessions.items():
        print("{}  rPPG median {:.1f} BPM (n={}, sd={:.1f})".format(key, s["bpm"], s["n"], s["spread"]))
        if key in refs:
            print("  reference: {:.1f}".format(refs[key]))
            continue
        if args.no_prompt:
            continue
        raw = input("  Apple Watch / manual BPM (blank to skip): ").strip()
        if raw:
            refs[key] = float(raw)
    save_refs(refs)
    keys = [k for k in sessions if k in refs]
    if len(keys) < 2:
        print("need at least 2 paired measurements for Bland-Altman (have {})".format(len(keys)))
        return
    est = [sessions[k]["bpm"] for k in keys]
    ref = [refs[k] for k in keys]
    labels = [sessions[k]["tag"] for k in keys]
    stats = bland_altman(est, ref, labels, args.out)
    print("bias {bias:+.2f}  sd {sd:.2f}  LoA [{loa[0]:.2f}, {loa[1]:.2f}]  MAE {mae:.2f}  RMSE {rmse:.2f}".format(**stats))
    print("within +/-5 BPM: {}/{}".format(stats["within5"], len(keys)))
    print("saved: {}".format(args.out))
if __name__ == "__main__":
    main()
