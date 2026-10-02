import argparse
import csv
import glob
import os
import statistics as st
import sys
import rppg_poc as rp
THRESHOLDS = (1.5, 2.0, 2.5, 3.0)
HI_SNR = 2.0
INVALID_SESSIONS = (
    "session_20260828_163250_photo_attack_screen.csv",
    "session_20260828_164122_photo_attack_still2.csv",
)
def load_sessions(log_dir):
    out = []
    for path in sorted(glob.glob(os.path.join(log_dir, "session_*.csv"))):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            out.append({"file": os.path.basename(path), "rows": [], "empty": True})
            continue
        name = os.path.basename(path)
        bpm = [float(r["bpm"]) for r in rows]
        snr = [float(r["snr_db"]) for r in rows]
        fps = [float(r["fps"]) for r in rows]
        hi = [float(r["bpm"]) for r in rows if float(r["snr_db"]) >= HI_SNR]
        q = st.quantiles(bpm, n=4) if len(bpm) > 3 else [min(bpm), st.median(bpm), max(bpm)]
        out.append({
            "file": name,
            "tag": rows[-1]["tag"],
            "rows": rows,
            "empty": False,
            "n": len(rows),
            "photo": "photo" in name,
            "invalid": name in INVALID_SESSIONS,
            "first_elapsed": float(rows[0]["elapsed_s"]),
            "last_elapsed": float(rows[-1]["elapsed_s"]),
            "t_start": float(rows[0]["timestamp"]),
            "t_end": float(rows[-1]["timestamp"]),
            "bpm_med": st.median(bpm),
            "bpm_q1": q[0],
            "bpm_q3": q[2],
            "bpm_min": min(bpm),
            "bpm_max": max(bpm),
            "snr_med": st.median(snr),
            "snr_min": min(snr),
            "snr_max": max(snr),
            "snr": snr,
            "fps_med": st.median(fps),
            "hi_n": len(hi),
            "hi_med": st.median(hi) if hi else None,
            "valid": sum(int(r["valid"]) for r in rows),
        })
    return out
def session_table(sessions):
    lines = ["| 태그 | 샘플 | BPM 중앙값 (IQR) | SNR 중앙값 | SNR 최대 | 비고 |", "|---|---|---|---|---|---|"]
    for s in sessions:
        if s["empty"]:
            lines.append("| `{}` | 0 | — | — | — | 빈 파일 |".format(s["file"]))
            continue
        note = "**무효.**" if s["invalid"] else ""
        lines.append("| `{}` | {} | {:.1f} ({:.1f}–{:.1f}) | {:.2f} | {:.2f} | {} |".format(
            s["tag"], s["n"], s["bpm_med"], s["bpm_q1"], s["bpm_q3"], s["snr_med"], s["snr_max"], note))
    return lines
def threshold_table(sessions):
    face = [x for s in sessions if not s["empty"] and not s["photo"] for x in s["snr"]]
    valid_photo = [x for s in sessions if not s["empty"] and s["photo"] and not s["invalid"] for x in s["snr"]]
    bad_photo = [x for s in sessions if not s["empty"] and s["photo"] and s["invalid"] for x in s["snr"]]
    lines = [
        "얼굴 세션 {}개 {}샘플, 유효 사진 {}샘플, 무효 사진 {}샘플".format(
            sum(1 for s in sessions if not s["empty"] and not s["photo"]), len(face), len(valid_photo), len(bad_photo)),
        "",
        "| 임계값 | 유효 사진 통과 | 무효 사진 통과 | 얼굴 통과 |",
        "|---|---|---|---|",
    ]
    for th in THRESHOLDS:
        lines.append("| {:.1f} dB | {}/{} | {}/{} | {}/{} |".format(
            th,
            sum(1 for x in valid_photo if x >= th), len(valid_photo),
            sum(1 for x in bad_photo if x >= th), len(bad_photo),
            sum(1 for x in face if x >= th), len(face)))
    per = sorted((s["snr_max"], s["tag"]) for s in sessions if not s["empty"] and not s["photo"])
    if per:
        lines += ["", "얼굴 세션별 SNR 최대: {:.2f} ~ {:.2f}".format(per[0][0], per[-1][0])]
        lines += ["3.04 dB 이상인 얼굴 세션: {}/{}".format(sum(1 for m, _ in per if m >= 3.04), len(per))]
    return lines
def hisnr_table(sessions):
    lines = ["| 태그 | SNR >= {:.1f} dB 샘플 | BPM 중앙값 |".format(HI_SNR), "|---|---|---|"]
    for s in sessions:
        if s["empty"] or s["photo"]:
            continue
        lines.append("| `{}` | {}/{} | {} |".format(
            s["tag"], s["hi_n"], s["n"], "{:.1f}".format(s["hi_med"]) if s["hi_med"] is not None else "none"))
    return lines
def length_line(sessions):
    parts = ["`{}` {:.1f}초".format(s["tag"], s["last_elapsed"]) for s in sessions if not s["empty"]]
    odd = ["`{}` 첫 분석 행 {:.2f}초".format(s["tag"], s["first_elapsed"]) for s in sessions if not s["empty"] and s["first_elapsed"] > 13.0]
    return ["세션 길이(마지막 `elapsed_s`): " + ", ".join(parts), "", "첫 분석 행이 12초 부근이 아닌 세션: " + (", ".join(odd) if odd else "없음")]
def refs_table(sessions, log_dir):
    path = os.path.join(log_dir, "refs.csv")
    if not os.path.exists(path):
        return ["refs.csv 없음"]
    with open(path, newline="", encoding="utf-8") as f:
        refs = {r["key"]: float(r["ref_bpm"]) for r in csv.DictReader(f) if r["ref_bpm"]}
    lines = ["| 세션 | rPPG (valid 행 중앙값) | 대조 | 차이 |", "|---|---|---|---|"]
    diffs = []
    for s in sessions:
        if s["empty"]:
            continue
        key = "{}|{}".format(s["tag"], s["file"])
        if key not in refs:
            continue
        vals = [float(r["bpm"]) for r in s["rows"] if r["valid"] == "1"]
        if not vals:
            continue
        est = st.median(vals)
        diffs.append(est - refs[key])
        lines.append("| `{}` | {:.1f} | {:.0f} | {:+.1f} |".format(s["tag"], est, refs[key], est - refs[key]))
    if len(diffs) > 1:
        sd = st.stdev(diffs)
        bias = st.fmean(diffs)
        lines += ["", "bias {:+.2f}  sd {:.2f}  LoA [{:.2f}, {:.2f}]  MAE {:.2f}  within +/-5 {}/{}".format(
            bias, sd, bias - 1.96 * sd, bias + 1.96 * sd,
            st.fmean([abs(d) for d in diffs]), sum(1 for d in diffs if abs(d) <= 5.0), len(diffs))]
    return lines
def camera_table(log_dir):
    path = os.path.join(log_dir, "camera_test.csv")
    if not os.path.exists(path):
        return ["camera_test.csv 없음"]
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cols = ["config", "codec_actual", "fps_measured", "frames", "face_miss", "bpm", "snr_db", "green_cv"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(r[c] for c in cols) + " |")
    snrs = [float(r["snr_db"]) for r in rows if r["snr_db"]]
    if snrs:
        lines += ["", "SNR 폭 {:.2f} ~ {:.2f} = {:.2f} dB".format(min(snrs), max(snrs), max(snrs) - min(snrs))]
    return lines
def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--logs", default=rp.LOG_DIR)
    args = p.parse_args()
    if not os.path.isdir(args.logs):
        raise SystemExit("missing log dir: {}".format(args.logs))
    sessions = load_sessions(args.logs)
    if not sessions:
        raise SystemExit("no session csv in {}".format(args.logs))
    blocks = [
        ("세션", session_table(sessions)),
        ("세션 길이", length_line(sessions)),
        ("SNR 임계값", threshold_table(sessions)),
        ("고SNR 구간 BPM", hisnr_table(sessions)),
        ("대조", refs_table(sessions, args.logs)),
        ("camera_test", camera_table(args.logs)),
    ]
    for title, lines in blocks:
        print("### " + title)
        print()
        print("\n".join(lines))
        print()
if __name__ == "__main__":
    main()
