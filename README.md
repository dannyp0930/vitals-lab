# rPPG Phase 0 — 자체 검증

노트북 웹캠으로 심박수를 추정하고 그 값이 신뢰할 만한지 확인하기 위한 실험 코드다. 제품 코드가 아니다.

## 환경

이 PC에는 conda가 없고 Python 3.14만 설치되어 있다. pyVHR은 Python 3.9를 요구하고 GPL 계열이라 평가 용도로도 설치 비용 대비 이득이 없다고 판단해 건너뛰었다. 처음부터 POS 자체 구현(3-2)으로 진행했다.

의존성은 상용 배포가 가능한 라이선스만 사용한다.

| 패키지 | 버전 | 라이선스 |
|---|---|---|
| numpy | 2.5.2 | BSD-3 |
| scipy | 1.18.1 | BSD-3 |
| opencv-python | 5.0.0.93 | Apache-2.0 |
| mediapipe | 1.0.1 | Apache-2.0 |
| matplotlib | 3.11.1 | PSF 계열 (검증 스크립트 전용, 런타임 아님) |

### 설치

```bash
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install numpy scipy opencv-python mediapipe matplotlib
```

MediaPipe 1.0.x는 구 `mp.solutions.face_mesh` API를 제거했다. Tasks API(`FaceLandmarker`)를 쓰며 모델 파일이 별도로 필요하다.

```bash
curl -sSL -o models/face_landmarker.task https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
```

## 파일

| 파일 | 역할 |
|---|---|
| `rppg_poc.py` | 실시간 웹캠 심박수 측정. POS 자체 구현. Stage 단위 함수는 다른 스크립트에서 import해 재사용한다 |
| `test_pipeline.py` | 합성 신호로 Stage 3~5 검증. 웹캠 없이 실행 가능 |
| `camera_test.py` | 카메라 설정별 신호 품질 비교 |
| `verify.py` | 세션 로그와 Apple Watch 값을 짝지어 Bland-Altman 플롯 생성 |
| `logs/` | 세션 CSV, 카메라 실험 결과, 대조값, 플롯 |

## 하네스

Claude Code가 구현하고 Codex가 리뷰·커밋 계획을 맡는 구조를 `healthviewer-demo-api`에서 옮겨왔다. 규칙 문서는 아래와 같다.

| 파일 | 내용 |
|---|---|
| `HANDOFF.md` | 프로젝트 사양. 목적, 파이프라인, 게이트, 범위 밖 항목. **사용자 소유이며 도구가 고치지 않는다** |
| `CLAUDE.md` | Claude 규칙. 작업 등급, 검증 명령, 커밋 게이트, 파일 소유 |
| `AGENTS.md` | Codex 규칙. 리뷰 기준, 커밋 계획 계약 |
| `.claude/skills/round/SKILL.md` | 구현 → 검증 → Codex 리뷰 → 수정 라운드 절차. 상한 2라운드 |
| `.claude/agents/capture-verifier.md` | 웹캠 실측 전문 에이전트 |
| `.codex/agents/*.toml` | Codex 리뷰어·커밋 계획자 정의 |

**Codex를 호출하려면 이 저장소가 전역 `~/.codex/config.toml`에 신뢰 등록되어 있어야 한다.** 등록 전에는 전역 설정 모델로 떨어져 400으로 죽는다. 저장소 디렉터리에서 `codex`를 대화형으로 한 번 실행하면 신뢰 여부를 묻고 등록된다.

```bash
codex
```

## 실행

파이프라인 자체 검증(웹캠 불필요):

```bash
.venv/Scripts/python.exe test_pipeline.py
```

실시간 측정. `q`로 종료하며 종료 시 `logs/session_<시각>_<태그>.csv`가 남는다.

```bash
.venv/Scripts/python.exe rppg_poc.py --tag rest_1
```

주요 인자는 `--tag`, `--cam`, `--width/--height/--fps`, `--fourcc`, `--no-auto`(자동보정 끄기 시도), `--snr-min`(유효 판정 임계값)이다.

카메라 파라미터 실험. 설정마다 25초씩 얼굴을 촬영하므로 그동안 가만히 있어야 한다.

```bash
.venv/Scripts/python.exe camera_test.py --seconds 25
```

Apple Watch 대조. 세션별 rPPG 중앙값을 보여주고 대조값을 물어본 뒤 플롯을 만든다. 입력한 값은 `logs/refs.csv`에 저장되어 재실행 시 다시 묻지 않는다. 짝지어진 측정이 2개 이상 필요하다.

```bash
.venv/Scripts/python.exe verify.py
```

## 파이프라인

```
Stage 0  open_camera          640x480 / 30fps / YUY2, 자동보정 토글
Stage 1  detect_landmarks     MediaPipe FaceLandmarker (VIDEO 모드, 468 랜드마크)
         roi_polygons         이마 + 좌우 볼, convexHull로 폴리곤화
Stage 2  roi_mean_rgb         ROI ∩ YCrCb 피부 마스크 내 RGB 공간평균
         resample_uniform     프레임 타임스탬프 지터를 균일 격자로 보간
Stage 3  pos                  POS (Wang et al. 2016), 1.6초 윈도우 overlap-add
Stage 4  postprocess          선형 디트렌드 → Butterworth 4차 0.7~4.0Hz filtfilt
Stage 5  estimate_bpm         Welch PSD (nfft 8192) → 대역 내 최대 피크 → BPM, SNR
```

POS 투영은 `S1 = Cn_g - Cn_b`, `S2 = Cn_g + Cn_b - 2*Cn_r`, `h = S1 + (std(S1)/std(S2))*S2`이고 윈도우마다 평균을 뺀 뒤 누적한다.

SNR은 대역(0.7~4.0Hz) 안에서 피크 주파수와 그 2배 하모닉 주변 ±0.2Hz의 전력을 신호로, 나머지를 노이즈로 보고 dB로 계산한다. 이 값이 `--snr-min`(기본 -2 dB) 미만이면 화면에 `-- BPM`으로 표시하고 CSV의 `valid` 열이 0이 된다. **사진 공격 판정이 이 임계값에 걸려 있으므로 실측 후 조정이 필요하다.**

조정 대상 상수는 `rppg_poc.py` 상단에 모여 있다. `BUFFER_SEC`, `MIN_SEC`, `POS_WIN_SEC`, `BAND_LOW/HIGH`, `SNR_HALF_BW`, `SNR_MIN_DB`, ROI 랜드마크 인덱스가 여기 있다.

## 이 환경에서 확인한 카메라 특성

`cv2.VideoCapture` 백엔드별로 실제 반영 여부를 직접 확인했다.

| 항목 | DirectShow | Media Foundation |
|---|---|---|
| FOURCC 요청 | MJPG를 요청해도 항상 YUY2 반환 | 읽기 불가 |
| `CAP_PROP_AUTO_WB` | set/read 모두 동작 (0으로 꺼짐 확인) | set 실패 |
| `CAP_PROP_AUTO_EXPOSURE` | set은 True를 반환하나 read가 -1.0이라 검증 불가 | read 0.0 |

기본 백엔드로 DirectShow를 쓴다. **이 웹캠은 항상 비압축 YUY2로 전달하므로 영상 압축(함정 2)은 문제가 되지 않는다.** MJPG/YUY2 비교 실험은 이 하드웨어에서 불가능하다.

자동 노출은 OpenCV만으로는 실제로 꺼졌는지 확인할 수 없다. `camera_test.py`가 설정 후의 속성값을 그대로 CSV에 기록하니 반영 여부를 눈으로 확인하고, 안 되면 Windows 카메라 앱이나 제조사 유틸리티로 수동 고정한 뒤 같은 실험을 다시 돌린다.

## 검증 절차

1. **Apple Watch 대조** — 운동 앱(실외 걷기)을 켜야 초 단위로 갱신된다. 기본 상태는 갱신 주기가 몇 분이라 시점이 맞지 않는다. 태그를 나눠 여러 세션을 찍고 `verify.py`로 짝짓는다.
2. **계단 오르내리기** — 운동 직후 BPM이 올라갔다가 서서히 떨어지는지 본다. 태그를 `post_exercise_0min`, `post_exercise_2min` 식으로 나눈다.
3. **손목 맥박 15초 × 4** — ±5bpm 수준의 조악한 대조. 명백한 오류 검출용.
4. **인쇄/화면 사진 들이대기** — 심박수가 나오면 실패다. `--tag photo_attack`으로 찍고 SNR 분포를 실제 얼굴 세션과 비교해 `SNR_MIN_DB`를 정한다.

측정 조건은 안정 60초 / 운동 직후 60초, 실내등 / 창가 자연광 / 어두운 방, 정지 / 미세움직임 / 말하기 조합으로 태그를 붙인다.

## 관찰 사항

- 얼굴 검출률은 640x480에서 121/121 프레임이었다. 카메라 단독 캡처는 28.3fps지만 랜드마크 추론이 들어간 실제 루프에서는 22.2fps로 떨어진다. 나이퀴스트 한계(11Hz)가 대역 상한 4Hz보다 충분히 높아 문제는 없으나, 프레임 간격이 일정하지 않으므로 `resample_uniform`의 보간이 필수다.
- 헤드리스로 30초 버퍼를 채워 돌린 첫 실측에서 90.1 BPM, SNR 2.87 dB가 나왔다. 피험자가 실제로 정지 상태였는지 통제되지 않은 측정이므로 값 자체는 아직 아무것도 증명하지 않는다. 파이프라인이 끝까지 돌아간다는 것만 확인된 상태다.
- 피부 마스크 적용 후 ROI 픽셀 수가 1671개였다. 얼굴이 프레임에서 작으면 공간평균의 노이즈 억제 효과가 떨어지므로(함정 4) 얼굴이 화면을 더 채우도록 앉는 편이 낫다. 픽셀 수가 `MIN_ROI_PIXELS`(200) 미만이면 해당 프레임은 버린다.
- `test_pipeline.py`는 합성 신호에서 진폭 0.5%, 저주파 조명 변동 2%를 섞은 조건으로 54/72/108 BPM을 2 BPM 이내로 복원한다. 맥동 성분이 없고 노이즈만 있는 경우 SNR이 임계값 아래로 떨어지는 것도 함께 확인한다.

## 게이트

- [ ] 심박수가 화면에 뜨고 Apple Watch와 5bpm 이내로 일치
- [ ] 인쇄한 사진에서는 심박수 미검출
- [ ] 카메라 설정 변경에 따른 신호 품질 차이를 정량적으로 설명 가능
- [ ] 이 작업이 재미있었는가

## 참고

- POS: Wang et al., 2016, *Algorithmic Principles of Remote PPG*
- CHROM: de Haan & Jeanne, 2013 (POS가 막히면 대안)
