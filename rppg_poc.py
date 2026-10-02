import argparse
import csv
import os
import time
from collections import deque
from functools import lru_cache
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from scipy import signal
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "face_landmarker.task")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CAM_INDEX = 0
FRAME_W = 640
FRAME_H = 480
CAM_FPS = 30
FOURCC = "YUY2"
BUFFER_SEC = 30.0
MIN_SEC = 12.0
UPDATE_SEC = 1.0
POS_WIN_SEC = 1.6
BAND_LOW = 0.7
BAND_HIGH = 4.0
FILTER_ORDER = 4
NFFT = 8192
SNR_HALF_BW = 0.2
SNR_MIN_DB = 2.0
SKIN_CR = (133, 173)
SKIN_CB = (77, 127)
MIN_ROI_PIXELS = 200
WAVE_SAMPLES = 300
FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
MSG_FONT_SIZE = 34
MSG_Y = 215
BAR_X = 40
BAR_H = 18
BAR_GAP = 14
MSG_NO_FACE = "화면을 바라봐 주세요"
MSG_MEASURING = "측정 중입니다"
MSG_WAIT = "잠시만 기다려 주세요"
MSG_DONE = "측정이 완료되었습니다"
COLOR_NO_FACE = (60, 160, 255)
COLOR_MEASURING = (255, 255, 255)
COLOR_WAIT = (0, 200, 255)
COLOR_DONE = (0, 220, 0)
FOREHEAD_IDX = [10, 67, 69, 104, 108, 109, 151, 297, 299, 333, 338, 337, 336, 9, 107, 66]
LEFT_CHEEK_IDX = [50, 101, 118, 117, 123, 116, 111, 205, 187, 207, 206, 203, 36]
RIGHT_CHEEK_IDX = [280, 330, 347, 346, 352, 345, 340, 425, 411, 427, 426, 423, 266]
ROI_SETS = [FOREHEAD_IDX, LEFT_CHEEK_IDX, RIGHT_CHEEK_IDX]
def open_camera(index=CAM_INDEX, width=FRAME_W, height=FRAME_H, fps=CAM_FPS, fourcc=FOURCC, auto=True):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError("camera {} not available".format(index))
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75 if auto else 0.25)
    cap.set(cv2.CAP_PROP_AUTO_WB, 1 if auto else 0)
    for _ in range(5):
        cap.read()
    return cap
def camera_report(cap):
    cc = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec = "".join(chr((cc >> (8 * i)) & 0xFF) for i in range(4)) if cc else "?"
    return {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps_prop": cap.get(cv2.CAP_PROP_FPS),
        "codec": codec,
        "auto_exposure": cap.get(cv2.CAP_PROP_AUTO_EXPOSURE),
        "auto_wb": cap.get(cv2.CAP_PROP_AUTO_WB),
        "exposure": cap.get(cv2.CAP_PROP_EXPOSURE),
        "gain": cap.get(cv2.CAP_PROP_GAIN),
    }
def make_landmarker(model_path=MODEL_PATH):
    if not os.path.exists(model_path):
        raise RuntimeError("missing model file: {}".format(model_path))
    opts = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_faces=1,
    )
    return mp_vision.FaceLandmarker.create_from_options(opts)
def detect_landmarks(landmarker, frame_rgb, timestamp_ms):
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
    result = landmarker.detect_for_video(image, timestamp_ms)
    if not result.face_landmarks:
        return None
    return result.face_landmarks[0]
def roi_polygons(landmarks, width, height):
    polys = []
    for idx_set in ROI_SETS:
        pts = np.array([[landmarks[i].x * width, landmarks[i].y * height] for i in idx_set], dtype=np.float32)
        polys.append(cv2.convexHull(pts).astype(np.int32))
    return polys
def roi_mean_rgb(frame_bgr, polys):
    mask = np.zeros(frame_bgr.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, polys, 255)
    ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
    skin = cv2.inRange(ycrcb, (0, SKIN_CR[0], SKIN_CB[0]), (255, SKIN_CR[1], SKIN_CB[1]))
    combined = cv2.bitwise_and(mask, skin)
    if int(cv2.countNonZero(combined)) < MIN_ROI_PIXELS:
        combined = mask
    n = int(cv2.countNonZero(combined))
    if n < MIN_ROI_PIXELS:
        return None, 0
    b, g, r, _ = cv2.mean(frame_bgr, mask=combined)
    return np.array([r, g, b], dtype=np.float64), n
def resample_uniform(t, rgb):
    t = np.asarray(t, dtype=np.float64)
    span = t[-1] - t[0]
    if span <= 0:
        return None, 0.0
    fps = (len(t) - 1) / span
    grid = np.linspace(t[0], t[-1], len(t))
    out = np.stack([np.interp(grid, t, rgb[:, i]) for i in range(3)], axis=1)
    return out, fps
def pos(rgb, fps):
    n = len(rgb)
    win = int(round(POS_WIN_SEC * fps))
    if win < 8 or n < win:
        return None
    h = np.zeros(n, dtype=np.float64)
    proj = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    for m in range(0, n - win + 1):
        block = rgb[m:m + win].T
        mu = block.mean(axis=1, keepdims=True)
        mu[mu == 0] = 1e-9
        cn = block / mu
        s = proj @ cn
        sd2 = s[1].std()
        alpha = s[0].std() / sd2 if sd2 > 1e-12 else 0.0
        seg = s[0] + alpha * s[1]
        h[m:m + win] += seg - seg.mean()
    return h
def postprocess(sig_in, fps):
    x = signal.detrend(sig_in, type="linear")
    nyq = fps / 2.0
    high = min(BAND_HIGH, nyq * 0.95)
    if high <= BAND_LOW:
        return None
    b, a = signal.butter(FILTER_ORDER, [BAND_LOW / nyq, high / nyq], btype="bandpass")
    if len(x) <= 3 * max(len(a), len(b)):
        return None
    return signal.filtfilt(b, a, x)
def estimate_bpm(sig_in, fps):
    freqs, psd = signal.welch(sig_in, fs=fps, nperseg=len(sig_in), nfft=NFFT, detrend="constant")
    band = (freqs >= BAND_LOW) & (freqs <= BAND_HIGH)
    if not band.any():
        return None, None, (freqs, psd)
    idx = int(np.argmax(np.where(band, psd, 0.0)))
    f0 = freqs[idx]
    sig_mask = np.zeros_like(freqs, dtype=bool)
    for k in (1, 2):
        sig_mask |= np.abs(freqs - k * f0) <= SNR_HALF_BW
    sig_mask &= band
    noise_mask = band & ~sig_mask
    sig_pow = float(psd[sig_mask].sum())
    noise_pow = float(psd[noise_mask].sum())
    snr_db = 10.0 * np.log10(sig_pow / noise_pow) if noise_pow > 0 and sig_pow > 0 else -99.0
    return f0 * 60.0, snr_db, (freqs, psd)
def analyze(times, rgbs):
    rgb_u, fps = resample_uniform(times, rgbs)
    if rgb_u is None or fps < 5.0:
        return None
    bvp = pos(rgb_u, fps)
    if bvp is None:
        return None
    filtered = postprocess(bvp, fps)
    if filtered is None:
        return None
    bpm, snr_db, spectrum = estimate_bpm(filtered, fps)
    if bpm is None:
        return None
    return {"bpm": bpm, "snr_db": snr_db, "fps": fps, "wave": filtered, "spectrum": spectrum}
def draw_wave(frame, wave, x, y, w, h):
    if wave is None or len(wave) < 4:
        return
    seg = np.asarray(wave[-WAVE_SAMPLES:], dtype=np.float64)
    rng = seg.max() - seg.min()
    if rng <= 0:
        return
    norm = (seg - seg.min()) / rng
    xs = np.linspace(x, x + w, len(norm)).astype(np.int32)
    ys = (y + h - norm * h).astype(np.int32)
    cv2.polylines(frame, [np.stack([xs, ys], axis=1)], False, (0, 255, 0), 1)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 80, 80), 1)
@lru_cache(maxsize=16)
def text_image(text, size, color_bgr):
    font = ImageFont.truetype(FONT_PATH, size) if os.path.exists(FONT_PATH) else ImageFont.load_default()
    box = font.getbbox(text)
    img = Image.new("RGBA", (box[2] - box[0] + 4, box[3] - box[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - box[0], 2 - box[1]), text, font=font, fill=(color_bgr[2], color_bgr[1], color_bgr[0], 255))
    arr = np.array(img)
    return cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2BGR), arr[:, :, 3:4].astype(np.float32) / 255.0
def draw_message(frame, text, size, color_bgr, y):
    bgr, alpha = text_image(text, size, color_bgr)
    h, w = bgr.shape[:2]
    x = (frame.shape[1] - w) // 2
    if x < 0 or y < 0 or x + w > frame.shape[1] or y + h > frame.shape[0]:
        return
    roi = frame[y:y + h, x:x + w].astype(np.float32)
    frame[y:y + h, x:x + w] = (roi * (1.0 - alpha) + bgr.astype(np.float32) * alpha).astype(np.uint8)
def draw_progress(frame, ratio, x, y, w, h, color_bgr):
    cv2.rectangle(frame, (x, y), (x + w, y + h), (90, 90, 90), 1)
    fill = int(w * min(1.0, max(0.0, ratio)))
    if fill > 0:
        cv2.rectangle(frame, (x, y), (x + fill, y + h), color_bgr, -1)
def geom_stats(geom):
    if not geom:
        return 0.0, 0.0
    g = np.asarray(geom, dtype=np.float64)
    roi_px = float(np.median(g[:, 3]))
    motion_px = float(np.hypot(g[:, 1].std(), g[:, 2].std())) if len(g) > 1 else 0.0
    return roi_px, motion_px
def run(args):
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "session_{}_{}.csv".format(time.strftime("%Y%m%d_%H%M%S"), args.tag))
    log_file = open(log_path, "w", newline="", encoding="utf-8")
    writer = csv.writer(log_file)
    writer.writerow(["timestamp", "elapsed_s", "bpm", "snr_db", "fps", "roi_px", "motion_px", "valid", "tag"])
    cap = open_camera(args.cam, args.width, args.height, args.fps, args.fourcc, auto=not args.no_auto)
    print(camera_report(cap))
    landmarker = make_landmarker()
    buf = deque()
    geom = deque()
    t0 = time.time()
    last_update = 0.0
    state = {"bpm": None, "snr_db": None, "fps": 0.0, "wave": None}
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            now = time.time()
            frame = cv2.flip(frame, 1)
            rgb_frame = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            lms = detect_landmarks(landmarker, rgb_frame, int((now - t0) * 1000))
            face_ok = lms is not None
            if face_ok:
                polys = roi_polygons(lms, frame.shape[1], frame.shape[0])
                mean_rgb, roi_n = roi_mean_rgb(frame, polys)
                cv2.polylines(frame, polys, True, (0, 200, 255), 1)
                if mean_rgb is not None:
                    buf.append((now, mean_rgb[0], mean_rgb[1], mean_rgb[2]))
                    pts = np.concatenate(polys, axis=0).reshape(-1, 2)
                    geom.append((now, float(pts[:, 0].mean()), float(pts[:, 1].mean()), float(roi_n)))
            while buf and now - buf[0][0] > BUFFER_SEC:
                buf.popleft()
            while geom and now - geom[0][0] > BUFFER_SEC:
                geom.popleft()
            filled = (buf[-1][0] - buf[0][0]) if len(buf) > 1 else 0.0
            if filled >= MIN_SEC and now - last_update >= UPDATE_SEC:
                last_update = now
                arr = np.array(buf, dtype=np.float64)
                res = analyze(arr[:, 0], arr[:, 1:4])
                if res is not None:
                    state.update(res)
                    valid = res["snr_db"] >= args.snr_min
                    roi_px, motion_px = geom_stats(geom)
                    writer.writerow([
                        "{:.3f}".format(now),
                        "{:.2f}".format(now - t0),
                        "{:.2f}".format(res["bpm"]),
                        "{:.2f}".format(res["snr_db"]),
                        "{:.2f}".format(res["fps"]),
                        "{:.0f}".format(roi_px),
                        "{:.2f}".format(motion_px),
                        int(valid),
                        args.tag,
                    ])
                    log_file.flush()
            valid = state["snr_db"] is not None and state["snr_db"] >= args.snr_min
            bpm_text = "{:.1f} BPM".format(state["bpm"]) if (state["bpm"] is not None and valid) else "-- BPM"
            color = (0, 255, 0) if valid else (0, 0, 255)
            cv2.putText(frame, bpm_text, (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 2)
            snr_text = "SNR {:.1f} dB".format(state["snr_db"]) if state["snr_db"] is not None else "SNR --"
            cv2.putText(frame, snr_text, (12, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)
            status = "fps {:.1f}  buf {:.0f}/{:.0f}s  face {}  tag {}".format(state["fps"], filled, BUFFER_SEC, "Y" if face_ok else "N", args.tag)
            cv2.putText(frame, status, (12, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
            draw_wave(frame, state["wave"], 12, 110, frame.shape[1] - 24, 90)
            if not face_ok:
                msg, msg_color = MSG_NO_FACE, COLOR_NO_FACE
            elif valid:
                msg, msg_color = MSG_DONE, COLOR_DONE
            elif filled >= BUFFER_SEC:
                msg, msg_color = MSG_WAIT, COLOR_WAIT
            else:
                msg, msg_color = MSG_MEASURING, COLOR_MEASURING
            draw_message(frame, msg, MSG_FONT_SIZE, msg_color, MSG_Y)
            draw_progress(frame, filled / BUFFER_SEC, BAR_X, MSG_Y + MSG_FONT_SIZE + BAR_GAP, frame.shape[1] - 2 * BAR_X, BAR_H, msg_color)
            cv2.imshow("rppg_poc", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        log_file.close()
        print("log saved: {}".format(log_path))
def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="default")
    p.add_argument("--cam", type=int, default=CAM_INDEX)
    p.add_argument("--width", type=int, default=FRAME_W)
    p.add_argument("--height", type=int, default=FRAME_H)
    p.add_argument("--fps", type=int, default=CAM_FPS)
    p.add_argument("--fourcc", default=FOURCC)
    p.add_argument("--no-auto", action="store_true")
    p.add_argument("--snr-min", type=float, default=SNR_MIN_DB)
    return p
if __name__ == "__main__":
    run(build_parser().parse_args())
