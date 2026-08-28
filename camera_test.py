import argparse
import csv
import os
import time
import cv2
import numpy as np
import rppg_poc as rp
CONFIGS = [
    ("640x480_auto_on", 640, 480, 30, "YUY2", True),
    ("640x480_auto_off", 640, 480, 30, "YUY2", False),
    ("1280x720_auto_on", 1280, 720, 30, "YUY2", True),
    ("1280x720_auto_off", 1280, 720, 30, "YUY2", False),
    ("640x480_mjpg_request", 640, 480, 30, "MJPG", False),
    ("640x480_15fps", 640, 480, 15, "YUY2", False),
]
def capture(cfg, seconds, cam_index, preview):
    name, w, h, fps, fourcc, auto = cfg
    cap = rp.open_camera(cam_index, w, h, fps, fourcc, auto=auto)
    report = rp.camera_report(cap)
    landmarker = rp.make_landmarker()
    times = []
    rgbs = []
    frames = 0
    misses = 0
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            ok, frame = cap.read()
            if not ok:
                continue
            frames += 1
            now = time.time()
            rgb_frame = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            lms = rp.detect_landmarks(landmarker, rgb_frame, int((now - t0) * 1000))
            if lms is None:
                misses += 1
            else:
                polys = rp.roi_polygons(lms, frame.shape[1], frame.shape[0])
                mean_rgb, _ = rp.roi_mean_rgb(frame, polys)
                if mean_rgb is not None:
                    times.append(now)
                    rgbs.append(mean_rgb)
                    cv2.polylines(frame, polys, True, (0, 200, 255), 1)
            if preview:
                left = seconds - (now - t0)
                cv2.putText(frame, "{}  {:.0f}s left".format(name, left), (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.imshow("camera_test", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cap.release()
        landmarker.close()
    return report, np.array(times), np.array(rgbs), frames, misses
def green_ac_ratio(rgbs):
    g = rgbs[:, 1]
    return float(np.std(g) / (np.mean(g) + 1e-9))
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=25.0)
    p.add_argument("--cam", type=int, default=rp.CAM_INDEX)
    p.add_argument("--rest", type=float, default=3.0)
    p.add_argument("--out", default=os.path.join(rp.BASE_DIR, "logs", "camera_test.csv"))
    p.add_argument("--no-preview", action="store_true")
    p.add_argument("--only", default="")
    args = p.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    configs = [c for c in CONFIGS if args.only in c[0]]
    rows = []
    print("hold still, face filling frame. {} configs x {:.0f}s".format(len(configs), args.seconds))
    for cfg in configs:
        print("--- {} ---".format(cfg[0]))
        report, times, rgbs, frames, misses = capture(cfg, args.seconds, args.cam, not args.no_preview)
        if len(times) < 100:
            print("  too few valid frames ({}), skipped".format(len(times)))
            continue
        res = rp.analyze(times, rgbs)
        row = {
            "config": cfg[0],
            "codec_actual": report["codec"],
            "w": report["width"],
            "h": report["height"],
            "auto_exposure_prop": report["auto_exposure"],
            "auto_wb_prop": report["auto_wb"],
            "exposure_prop": report["exposure"],
            "gain_prop": report["gain"],
            "frames": frames,
            "face_miss": misses,
            "fps_measured": round(res["fps"], 2) if res else "",
            "bpm": round(res["bpm"], 2) if res else "",
            "snr_db": round(res["snr_db"], 2) if res else "",
            "green_cv": round(green_ac_ratio(rgbs), 6),
        }
        rows.append(row)
        print("  codec={codec_actual} {w}x{h} fps={fps_measured} bpm={bpm} snr={snr_db}dB green_cv={green_cv}".format(**row))
        if args.rest > 0:
            time.sleep(args.rest)
    cv2.destroyAllWindows()
    if rows:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print("saved: {}".format(args.out))
        best = max(rows, key=lambda r: r["snr_db"] if r["snr_db"] != "" else -99)
        print("best SNR: {} ({} dB)".format(best["config"], best["snr_db"]))
if __name__ == "__main__":
    main()
