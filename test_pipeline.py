import numpy as np
import rppg_poc
def synth(bpm, seconds=30.0, fps=30.0, amp=0.005, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, seconds, 1.0 / fps)
    pulse = np.sin(2 * np.pi * (bpm / 60.0) * t)
    skin = np.array([160.0, 110.0, 95.0])
    ac = np.array([0.33, 0.77, 0.53])
    rgb = skin[None, :] * (1.0 + amp * ac[None, :] * pulse[:, None])
    rgb += skin[None, :] * noise * rng.standard_normal(rgb.shape)
    rgb *= 1.0 + 0.02 * np.sin(2 * np.pi * 0.05 * t)[:, None]
    return t, rgb
def test_clean():
    for bpm in (54.0, 72.0, 108.0):
        t, rgb = synth(bpm)
        res = rppg_poc.analyze(t, rgb)
        assert res is not None
        assert abs(res["bpm"] - bpm) < 2.0, (bpm, res["bpm"])
        assert res["snr_db"] > 0.0, (bpm, res["snr_db"])
def test_noisy():
    t, rgb = synth(72.0, noise=0.002, seed=1)
    res = rppg_poc.analyze(t, rgb)
    assert abs(res["bpm"] - 72.0) < 3.0, res["bpm"]
def test_no_pulse():
    t, rgb = synth(72.0, amp=0.0, noise=0.002, seed=2)
    res = rppg_poc.analyze(t, rgb)
    assert res["snr_db"] < rppg_poc.SNR_MIN_DB, res["snr_db"]
def test_jittered_timestamps():
    rng = np.random.default_rng(3)
    t, rgb = synth(66.0)
    t = t + rng.normal(0.0, 0.004, t.shape)
    t.sort()
    res = rppg_poc.analyze(t, rgb)
    assert abs(res["bpm"] - 66.0) < 3.0, res["bpm"]
if __name__ == "__main__":
    test_clean()
    test_noisy()
    test_no_pulse()
    test_jittered_timestamps()
    print("pipeline ok")
