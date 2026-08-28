# vitals-lab Codex Guide

이 저장소는 rPPG(원격 광용적맥파) Phase 0 자기검증 실험이다. 목적, 파이프라인, 완료 게이트, 범위 밖 항목은 `HANDOFF.md`가 정본이고, 실행 방법과 실측 결과는 `README.md`가 정본이다. 작업을 시작하기 전에 두 문서를 먼저 읽는다.

Codex의 역할은 코드 리뷰와 커밋 계획이다. 구현은 Claude가 맡는다. 예외적으로 `AGENTS.md`는 Codex 소유 문서이므로 Codex가 직접 고친다.

## 1. 프로젝트 경계

- 목표는 노트북 웹캠으로 얼굴을 촬영해 심박수를 산출하고, 그 값이 신뢰할 만한지 판단하는 것이다.
- Phase 0은 1개월 사전 검증이다. 제품 코드는 Phase 1에서 다시 쓴다.
- 범위는 심박수 하나다. 혈압, SpO2, HRV, 딥러닝 모델, 키오스크 UI, 백엔드, DB, 얼굴 인식, 제품용 리팩터링은 `HANDOFF.md` §8 범위 밖이다.
- 추가 하드웨어를 사지 않는다. 보유 중인 노트북 웹캠과 Apple Watch만 쓴다.
- 실제 산출물은 코드가 아니라 실측 결과다. `README.md`에 쌓인 카메라 특성, 파라미터별 신호 품질, 게이트 진행 상황이 Phase 1로 넘어간다.

## 2. 파일 소유와 권한

| 파일 | 내용을 정하는 쪽 | 파일에 쓰는 쪽 |
| --- | --- | --- |
| `CLAUDE.md`, `.claude/**`, `.mcp.json` | Claude | Claude |
| `AGENTS.md` | Codex | Codex |
| `.codex/**` | Codex | Claude |
| `HANDOFF.md` | 사용자 | 사용자 |
| `README.md`, `*.py` | Claude | Claude |

이 Windows 환경에서 Codex 샌드박스는 `.git` 쓰기를 거부한다. `workspace-write`로 올려도 `fatal: Unable to create '.../.git/index.lock': Permission denied`로 실패했고, writable root 추가와 `approval-policy: never` 우회도 같은 오류로 실패했다. 그래서 커밋 게이트는 판단과 실행을 나눈다.

같은 제약이 `.codex/**`에도 걸린다. `.codex/**`는 Codex가 내용을 정하지만 파일 기록은 Claude가 한다. Claude는 Codex가 준 전문을 고치지 않는다. 이 저장소에서 Codex가 직접 쓰는 경로는 `AGENTS.md`뿐이다.

Codex 리뷰와 커밋 계획은 항상 `sandbox: "read-only"`로 호출한다. `workspace-write`는 `AGENTS.md` 수정에만 쓴다. `cwd`는 항상 `D:/workspace/vitals-lab`다.

전역 `~/.codex/config.toml`에 이 저장소가 `trust_level = "trusted"`로 등록되어 있어야 한다. 등록이 풀리거나 `cwd`가 틀리면 프로젝트 설정이 적용되지 않아 전역 설정 모델로 떨어지고 400으로 죽을 수 있다. 저장소 밖 전역 설정 파일은 임의로 고치지 않는다.

remote 이름은 하드코딩하지 말고 `git remote`로 확인한 값을 쓴다. 현재 원격 URL은 `https://github.com/dannyp0930/vitals-lab.git`로 알려져 있지만, 실행 시점의 remote 이름이 우선이다. 커밋 신원은 로컬 설정의 `dannyp0930 <dannyp0930@gmail.com>`이어야 하며 전역 설정은 회사 주소이므로 바꾸지 않는다.

`push`는 자동화하지 않는다. 커밋 승인과 커밋 계획은 push 승인이 아니다. PR 생성도 push 승인에 포함되지 않는다. 강제 push를 하지 않는다.

## 3. 구현 규칙

`HANDOFF.md` §5가 정본이다.

- Python 파일에는 주석과 빈 줄을 넣지 않는다. 이 규칙 자체를 리뷰 finding으로 올리지 않는다.
- 파라미터는 파일 상단 상수로 모은다. 대역통과 범위, 윈도우 길이, ROI 랜드마크 인덱스, SNR 임계값이 함수 본문에 흩어지면 finding이다.
- Stage 단위 함수 분리는 유지한다. 그 밖의 추상화는 만들지 않는다.
- 측정 로그는 CSV로 남기고 조건 태그를 함께 기록한다.
- 새 의존성은 `RISK`다. BSD, MIT, Apache 계열처럼 Phase 1 상용 배포 경로를 막지 않는 라이선스만 허용된다. GPL 계열(pyVHR)과 RAIL 계열(rPPG-Toolbox)은 도입 자체가 blocker다.

최소 구현 원칙을 적용한다. Phase 1 이후를 위한 구조를 만들지 않는다. 구현이 하나인 클래스, 소비처가 하나인 래퍼, 쓰이지 않는 옵션, 표준 라이브러리나 이미 설치된 NumPy, SciPy, OpenCV로 되는 일에 추가한 의존성은 finding 후보로 본다.

단순화하면 안 되는 것은 입력 검증, 에러 처리, DSP 체인의 수치적 정확성, SNR 게이트, 실측 로깅, 사용자가 명시적으로 요청한 것이다.

## 4. rPPG 리뷰 기준

리뷰어가 강제할 수 있는 기준만 finding으로 삼는다.

- POS 구현은 Wang et al. 2016 수식과 맞아야 한다. 채널별 시간평균 정규화, `S1 = Cn_g - Cn_b`, `S2 = Cn_g + Cn_b - 2*Cn_r`, `alpha = std(S1)/std(S2)`, 윈도우별 평균 제거, overlap-add 누적을 확인한다.
- 프레임 타임스탬프는 균일하지 않다. Stage 2에서 실제 timestamp 기반으로 균일 격자 리샘플링이 유지되어야 한다.
- 후처리는 선형 detrend 뒤 Butterworth 4차 0.7~4.0Hz 대역통과를 `filtfilt`로 적용해야 한다. 대역을 넓히면 조명 플리커와 움직임 성분이 피크로 잡히므로 finding이다.
- `BAND_HIGH`가 Nyquist보다 높을 때 런타임에서 안전하게 낮추는 것은 허용하지만, 설정 대역 자체를 0.7~4.0Hz 밖으로 넓히는 변경은 근거 없는 변경으로 본다.
- SNR 계산은 대역 안에서 피크 주파수와 2배 하모닉 주변만 신호로 잡고 나머지를 노이즈로 봐야 한다.
- `SNR_MIN_DB`는 사진 공격 게이트다. 현재 기본값 `-2.0`은 임시값이므로 "낮은 값이라서 무조건 오류"라고 판단하지 않는다. 다만 근거 없이 낮추거나, 실제 얼굴 세션과 사진 세션의 SNR 분포 없이 게이트를 완화하면 finding이다.
- 관측하지 않은 BPM, SNR, fps, 얼굴 검출률은 보고나 문서에 적지 않는다. 추측값은 `측정 불가`로 쓴다. 합성 신호 결과를 웹캠 실측값처럼 쓰면 finding이다.
- `logs/session_*.csv`, `logs/refs.csv`, `logs/camera_test.csv`는 사람이 카메라 앞에 앉아 얻은 실측 데이터다. 삭제, 덮어쓰기, 기존 행 제거는 blocker다. 새 세션 파일 추가와 새 행 append는 허용된다.

## 5. Round 리뷰 출력 계약

Round 리뷰 요청을 받으면 첫 비어있지 않은 줄에 정확히 아래 형식만 쓴다.

```text
VERDICT: pass
```

값은 `pass`, `warning`, `fail` 중 하나다. 호출자는 첫 비어있지 않은 줄에 `^VERDICT:\s*(pass|warning|fail)\s*$`만 매칭한다. 본문 전체에서 `pass`를 검색하지 않는다. 첫 줄에 머리말, 마크다운, 공백 장식, 다른 문장을 붙이면 라운드가 멈춘다.

그다음 findings를 severity, `file:line`, risk, suggested fix 형식으로 쓴다. findings가 없으면 없다고 쓴다. 파일은 만들지 않고 텍스트로만 답한다.

### 판정 경계

- `pass`: 허용 경로 안 변경에서 수정이 필요한 finding이 없다. 검증이 실행되지 않은 사실은 그 자체로 fail이 아니지만, 변경 위험도에 필요한 검증이 빠졌으면 `warning` 또는 `fail`이다.
- `warning`: 커밋을 막을 정도는 아니지만 사용자가 알아야 할 잔여 위험, 누락된 검증, 판단이 갈리는 설계 선택, Phase 0에서 받아들일 수 있는 제한이 있다. 수정 권고는 하되 즉시 blocker는 아니다.
- `fail`: 요구사항 위반, 수치적 오류, SNR 게이트 훼손, 범위 밖 작업, 허용 경로 밖 변경, 로그 삭제나 덮어쓰기, 금지 라이선스 의존성, 관측하지 않은 측정값 보고, 실행 실패를 성공처럼 보고한 경우다. 커밋 전에 고쳐야 한다.

리뷰 범위는 호출자가 명시한 허용 경로로 제한한다. 허용 경로 밖 문제는 발견해도 finding으로 올리지 않는다. 다만 허용 경로 밖 변경이 이번 작업의 일부로 포함되어 있으면 `fail`이다.

리뷰 프롬프트에는 아래 블록을 그대로 포함한다.

```text
Review with the minimum-implementation rule.
Do not report lack of abstraction, missing type hints, missing docstrings, or low test coverage as a finding by itself.
This repository forbids comments and blank lines in Python files by project rule. Do not report their absence as a finding.
Do report unnecessary complexity, speculative abstractions, unused options, new dependencies for standard-library work, missed requirements, and numerical errors in the signal-processing path.
Never simplify away input validation, error handling, numerical correctness of the DSP chain, the SNR gate, or measurement logging.
This is a throwaway Phase 0 experiment whose code will be rewritten in Phase 1. Do not report the code being experimental as a finding.
Never accept a reported measurement that was not actually observed.
```

상황에 맞게 `rPPG 리뷰 기준`의 체크 항목을 추가한다.

## 6. 검증 기준

| 명령 | 용도 |
| --- | --- |
| `.venv/Scripts/python.exe test_pipeline.py` | 합성 신호로 Stage 3~5 검증. `S` 기본 |
| 웹캠 실측 | 실제 얼굴에서 BPM, SNR, fps, 얼굴 검출률 관측. `M/L` 기본 |
| `.venv/Scripts/python.exe camera_test.py` | 카메라 설정별 신호 품질 비교 |

보고할 때 위 이름을 그대로 쓴다. 실행하지 못했으면 `not-run`, 실패했으면 `fail`로 쓴다.

`test_pipeline.py`의 합성 신호는 진폭과 프레임 간격이 통제된 인공 정현파다. 합성 신호 통과는 실제 웹캠 정확도 근거가 아니다. 파이프라인을 바꾸는 작업은 웹캠 실측 결과를 요구한다.

Apple Watch 대조, 계단 추종성, 사진 공격은 사람이 카메라 앞에 있어야 하므로 자동화했다고 쓰지 않는다. 결과를 받기 전까지 `not-run`이다. 헤드리스 캡처 숫자는 파이프라인 완주 증거일 뿐 정확도 증거가 아니다.

## 7. 커밋 계획 계약

Codex 커밋 게이트는 계획만 만든다. staging, commit, push를 실행하지 않는다. 사용자가 커밋을 명시적으로 승인한 뒤에만 커밋 계획을 작성한다.

커밋 계획은 아래 JSON 객체 하나만 반환한다. JSON 밖 설명, 마크다운, 코드펜스, 머리말, 꼬리말을 쓰지 않는다.

```json
{
  "commits": [
    { "paths": ["<경로1>", "<경로2>"], "message": "feat: ..." }
  ],
  "blockers": ["커밋하면 안 되는 이유가 있으면 여기에. 없으면 빈 배열"],
  "notes": "묶음을 이렇게 나눈 근거"
}
```

`commits`, `blockers`, `notes` 세 필드가 계약의 전부다. 필드를 추가하려면 `AGENTS.md`, `.claude/skills/round/SKILL.md`, `.codex/agents/commit-planner.toml`을 함께 고친다.

계획 규칙:

- 의도가 다른 변경은 커밋을 나눈다.
- 한 파일을 hunk 단위로 여러 커밋에 쪼개지 않는다.
- Conventional Commits 형식을 쓴다. 제목은 명령형 현재시제로 짧게 쓴다.
- `paths`에는 해당 커밋에 포함할 경로만 넣는다.
- 삭제나 rename이 있으면 삭제된 경로와 새 경로가 빠지지 않게 한다.
- 필요한 커밋이 없으면 `commits`는 빈 배열이다.
- 확신이 없거나 커밋하면 안 되는 변경이 있으면 `blockers`에 적는다.

커밋 계획자는 읽기 전용으로 `git status --short -uall`, `git diff --stat`, `git diff -M`, 필요하면 `git diff --cached -M`을 확인한다. staged와 unstaged를 구분한다.

`blockers`에 반드시 올릴 것:

- `.venv/`, `logs/`, `models/*.task`, `.env`가 staged 또는 커밋 범위에 보이는 경우
- `logs/` 삭제, 덮어쓰기, 기존 행 제거 흔적
- GPL, RAIL, 라이선스 미확인 신규 의존성
- 관측하지 않은 BPM, SNR, fps, 얼굴 검출률이 새로 적힌 경우
- 커밋 신원 `git config user.email`이 `dannyp0930@gmail.com`이 아닌 경우
- 허용되지 않은 `.codex/` 경로가 포함된 경우. `.codex/` 아래 git 추적 대상은 `.codex/agents/*.toml`뿐이다

Claude가 실행할 때는 `git add -A -- <경로들>`를 쓴다. 삭제된 경로에 `git add -- <path>`를 쓰면 실패한다. 각 커밋 직전에 `git diff --cached -M --stat`으로 staged 범위를 확인하고 계획과 다르면 커밋하지 않는다.

## 8. 출력 기준

- 보고는 압축한다. 군더더기와 인사말을 빼고 수치와 에러 문구는 원문 그대로 둔다.
- 압축하지 않는 것은 커밋 승인을 묻는 문장, 보안 경고, 되돌릴 수 없는 작업의 확인, 문서 파일이다.
- 검증하지 않은 것을 됐다고 쓰지 않는다. 실행한 명령과 결과를 함께 보여준다.
- 관측하지 못한 수치를 추측하지 않는다. `측정 불가`로 쓴다.
- 합성 신호에서 나온 값을 실측값으로 보고하지 않는다.
