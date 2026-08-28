# HANDOFF — rPPG Phase 0 자기검증

> Claude Code 세션 시작 시 이 문서를 읽고 작업을 이어간다.
> 작성일 2026-08-28

---

## 0. 이 작업이 무엇인가

네오티스의 비접촉 생체신호 측정 키오스크 솔루션을 자체 개발할 수 있는지 판단하기 위한 **1개월짜리 사전 검증**이다. 제품 코드가 아니라 실험용 코드다.

현재 회사는 지비소프트 솔루션을 리브랜딩해 납품 중이며(LG전자·롯데건설·DL E&C 등), 이를 자체 기술로 대체하는 것이 장기 목표다. 이 Phase 0은 그 첫 단계로, **개발자 본인이 rPPG 영역을 감당할 수 있는지 확인**하는 것이 목적이다.

## 1. Phase 0 목표

노트북 웹캠으로 얼굴을 촬영해 심박수를 화면에 띄운다. 그리고 그 값이 신뢰할 만한지 확인한다.

**추가 하드웨어 구매 없이 진행한다.** 보유 중인 노트북 웹캠과 Apple Watch만 사용한다.

## 2. 기술 배경 요약

rPPG(remote photoplethysmography)는 얼굴 피부의 미세한 색 변화로 혈류를 검출한다. 심장 박동 → 혈액량 변화 → 헤모글로빈 흡광 변화 → 픽셀 밝기 변화의 연쇄다.

**핵심 난점**: 혈류에 의한 밝기 변화폭이 전체 피부 밝기의 **0.1~1%** 에 불과하다. 조명 흔들림, 머리 움직임, 센서 노이즈, 영상 압축이 전부 이보다 크다. 파이프라인 전체가 이 노이즈를 제거하기 위해 존재한다.

**파이프라인 6단계**

```
Stage 0  영상 획득          30fps+, 비압축 선호, 자동보정 OFF
Stage 1  얼굴 검출 + ROI     MediaPipe FaceMesh → 이마/볼
Stage 2  시간 신호 추출      ROI RGB 공간평균 → 시계열
Stage 3  신호 분리 ★         POS 알고리즘 (여기가 핵심)
Stage 4  후처리              디트렌드 + 대역통과 0.7~4.0Hz
Stage 5  지표 산출           Welch PSD → 최대 피크 → BPM
```

## 3. 작업 순서

### 3-1. 기성 라이브러리로 먼저 확인 (우선)

**직접 구현하지 않는다.** pyVHR 또는 rPPG-Toolbox를 설치해 웹캠으로 심박수가 뜨는 것을 먼저 본다.

```
conda create -n rppg python=3.9
conda activate rppg
pip install pyVHR
```

pyVHR은 의존성 충돌이 잦다. **30분 이상 설치에 막히면 즉시 다음 대안으로 넘어간다.**

1. rPPG-Toolbox (`ubicomplab/rPPG-Toolbox`)
2. MediaPipe + OpenCV + SciPy만 설치하고 3-2로 직행

이 단계 라이브러리는 **평가·학습 용도로만** 사용한다. pyVHR은 GPL 계열, rPPG-Toolbox는 RAIL 계열로 추정되어 상용 배포 불가다. 제품용 구현은 Phase 1에서 별도로 작성한다.

### 3-2. POS 직접 구현

라이브러리로 감을 잡은 뒤 자체 구현한다. 코드량 200줄 내외.

**의존성은 상용 자유 라이브러리로만 구성한다**: NumPy, SciPy, OpenCV, MediaPipe (모두 BSD/Apache 계열).

구현할 것:

```
webcam capture (OpenCV VideoCapture)
  → MediaPipe FaceMesh 468 랜드마크
  → 이마 + 좌우 볼 ROI 폴리곤 정의
  → ROI 내 피부 픽셀 RGB 공간평균 → 프레임당 스칼라 3개
  → 30초 링버퍼 유지
  → POS 알고리즘으로 BVP 추출
  → scipy.signal detrend + butter bandpass (0.7~4.0Hz, 4차, filtfilt)
  → scipy.signal.welch → 최대 피크 주파수 × 60 = BPM
  → matplotlib 또는 OpenCV 오버레이로 실시간 파형 + BPM 표시
```

**POS 알고리즘 요지** (Wang et al., 2016, "Algorithmic principles of remote PPG")

RGB 시계열을 슬라이딩 윈도우로 처리한다. 각 윈도우에서 시간축 평균으로 정규화한 뒤, 피부톤 방향에 직교하는 평면에 투영한다.

```
Cn = C / mean(C)           채널별 시간평균 정규화
S1 = Cn_g - Cn_b
S2 = Cn_g + Cn_b - 2*Cn_r
h  = S1 + (std(S1)/std(S2)) * S2
```

윈도우별 h를 overlap-add로 누적해 최종 BVP를 만든다. 정확한 수식과 윈도우 길이는 원논문을 참조해 구현한다.

### 3-3. 자가 검증

측정기 없이 가능한 검증 4종:

| 방법 | 확인 내용 |
|---|---|
| Apple Watch 대조 | **운동 앱(실외 걷기)을 켜야 초 단위 연속 측정됨.** 기본 상태는 몇 분 주기라 시점이 안 맞음 |
| 계단 오르내리기 | 운동 직후 BPM이 올라가고 서서히 떨어지는가 (추종성) |
| 손목 맥박 15초×4 | ±5bpm 수준의 조악한 대조. 명백한 오류 검출용 |
| **인쇄/화면 사진 들이대기** | **심박수가 나오면 실패.** 신호가 아니라 노이즈를 잡고 있다는 뜻. 가장 확실한 sanity check |

Bland-Altman 플롯으로 오차 분포를 시각화한다.

측정 시나리오: 안정 60초 / 운동 직후 60초 / 실내등·창가 자연광·어두운 방 / 정지·미세움직임·말하기

### 3-4. 카메라 파라미터 실험

동일 코드로 카메라 설정만 바꿔가며 신호 품질(SNR, PSD 피크 선명도)을 비교한다.

- 자동 노출 / AGC / AWB **ON vs OFF**
- 해상도, fps 변경
- 압축 포맷 (MJPEG vs YUY2, 가능한 경우)

**Windows**: DirectShow 속성 다이얼로그, OBS Virtual Camera, 또는 제조사 유틸리티로 수동 고정
**Linux**: `v4l2-ctl --set-ctrl=exposure_auto=1,white_balance_temperature_auto=0`

OpenCV의 `CAP_PROP_AUTO_EXPOSURE` 등은 백엔드에 따라 동작 여부가 다르므로 실제 반영되는지 확인이 필요하다.

## 4. 알려진 함정

첫 시도에 값이 안 나오는 경우 대부분 아래 중 하나다.

1. **카메라 자동보정이 켜져 있다** — AGC/AWB/자동노출은 "밝아지면 어둡게 조정"하므로 잡으려는 신호를 능동적으로 상쇄한다. 최우선 확인 대상
2. **영상 압축** — MJPEG/H.264는 DCT 양자화에서 0.1% 변화를 노이즈로 버린다
3. **조명 플리커** — 60Hz 전원 형광등은 120Hz로 깜빡여 저주파 비트를 만든다. 창가 자연광이 훨씬 유리
4. **ROI 픽셀 부족** — 얼굴이 화면에서 작으면 공간평균의 노이즈 억제 효과가 떨어진다. 얼굴이 프레임을 충분히 채우게
5. **버퍼 길이 부족** — 주파수 분해능을 위해 최소 20~30초 누적 필요
6. **움직임** — 측정 중 정지 상태 유지

## 5. 코딩 규칙

- **주석과 빈 줄을 넣지 않는다.**
- 실험 코드이므로 과도한 추상화를 하지 않는다. 단, Stage 단위 함수 분리는 유지한다 (Phase 1에서 인터페이스로 승격 예정)
- 파라미터(대역통과 범위, 윈도우 길이, ROI 정의)는 상수로 모아 실험 중 조정이 쉽도록 한다
- 측정 로그를 CSV로 남긴다 (timestamp, BPM, SQI, 조건 태그) — 나중에 비교 분석용

## 6. 산출물

1. `rppg_poc.py` — 실시간 웹캠 심박수 측정 (POS 자체 구현)
2. `verify.py` — Apple Watch 값 입력받아 Bland-Altman 플롯 생성
3. `camera_test.py` — 카메라 파라미터별 신호 품질 비교
4. `README.md` — 실행 방법, 실험 결과, 관찰 사항

## 7. 게이트 (완료 판정)

- [ ] 내 심박수가 화면에 뜨고 Apple Watch와 5bpm 이내로 일치하는가
- [ ] 인쇄한 사진에서는 심박수가 검출되지 않는가
- [ ] 카메라 설정 변경에 따른 신호 품질 차이를 정량적으로 설명할 수 있는가
- [ ] 이 작업이 재미있었는가

마지막 항목이 농담이 아니다. 이후 단계는 이보다 지루하고 길다.

## 8. 범위 밖 (하지 말 것)

- 딥러닝 모델 도입 — Phase 4 영역
- 혈압·SpO2·HRV 산출 — Phase 0 범위 아님. 심박수만
- 키오스크 UI, 백엔드, DB — Phase 2 영역
- 얼굴 인식/신원 확인 — Phase 2 영역
- 제품용 리팩터링 — Phase 1 영역

## 9. 참고

- POS: Wang et al., 2016, Algorithmic principles of remote PPG
- CHROM: de Haan & Jeanne, 2013 (POS가 막히면 대안)
- pyVHR: `phuselab/pyVHR`
- rPPG-Toolbox: `ubicomplab/rPPG-Toolbox`
- 상세 기술 분석: `rPPG_엔진_기술분석.md`
- 전체 로드맵: `rPPG_자체개발_로드맵.md`

---

**첫 작업**: 3-1의 라이브러리 설치를 시도하고, 30분 내 심박수가 화면에 뜨지 않으면 3-2 직접 구현으로 전환한다.
