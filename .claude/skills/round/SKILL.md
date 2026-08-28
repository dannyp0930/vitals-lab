---
name: round
description: Claude가 구현하고 Codex가 리뷰하는 자동 라운드를 진행한다. 사용자가 목표를 한 번 말하면 구현, 검증, Codex 리뷰, 수정을 라운드 단위로 반복하고 커밋 승인 지점에서만 사용자에게 돌아온다. '라운드로 진행해줘', '리뷰까지 받아줘', '코덱스 리뷰 받으면서 해줘' 같은 요청과 S/M/L 규모 작업에 사용한다. XS 단순 문구 수정에는 사용하지 않는다.
---

# Cross-Tool Round

Claude가 구현하고 Codex가 리뷰하는 라운드를 자동으로 돌린다. 사용자는 최초 목표와 커밋 승인에만 개입한다.

규칙의 단일 출처는 `CLAUDE.md`다. 충돌하면 그 문서를 따른다.

이 스킬은 `healthviewer-demo-api`에서 실측으로 다듬은 절차를 옮긴 축소판이다. **Codex 호출과 판정 추출 규칙은 그대로 두었다.** 그 규칙들은 실제로 깨져 보고 고친 것이라 임의로 줄이지 않는다. 줄인 것은 라운드 상한과 기본 등급 둘뿐이며 근거는 아래 "이 저장소에서 줄인 것"에 있다.

## 이 저장소에서 줄인 것

| 항목 | 원본 | 여기 | 근거 |
| --- | --- | --- | --- |
| 라운드 상한 | 3 | **2** | 대상이 파이썬 4파일 실험 코드다. 원본 실측에서 재검토 라운드가 첫 리뷰의 2.3배였다(244,477 → 569,519 input). 상한을 늘리는 비용이 선형이 아니다 |
| 기본 등급 | `M` | **`S`** | 대부분의 작업이 상수 조정과 함수 하나 수정이다 |

**상한을 없애지 않는다.** 사용자가 "무제한"이나 "될 때까지"를 요청하면 그대로 따르지 않고 상한을 제안한 뒤 확인받는다. 리뷰어는 언제나 지적할 것을 찾을 수 있어서 `pass`가 존재한다는 보장이 없다.

## 사용 기준

| 등급   | 진입 |
| ------ | ---- |
| `XS`   | 사용하지 않는다. 라운드 비용이 변경보다 크다. 직접 고친다 |
| `S`    | **기본.** 리뷰 1회만. 수정 반복 없음 |
| `M`    | 최대 2라운드 |
| `L`    | 최대 2라운드. 단 첫 `warning`에서 계속 진행할지 사용자에게 물을 수 있다 |
| `RISK` | **자동 진입 금지.** 범위와 되돌리기 계획을 먼저 보고하고 사용자 확인을 받는다. 확인 후에도 수정 반복은 하지 않는다 |

등급 판정 기준은 `CLAUDE.md`를 따른다. 애매하면 낮게 잡되, 신규 의존성·되돌리기 명령·`logs/` 삭제·`.venv/` 재생성·시스템 설정 변경·`HANDOFF.md` §8 범위 밖 작업이 걸리면 `RISK`로 올린다.

등급을 규칙보다 낮게 잡을 때는 근거를 closeout의 "미확정 가정"에 반드시 남기고 리뷰 질문에도 올린다. 규칙이 조용히 무력화되지 않게 한다.

## 라운드 절차

1. 목표에서 등급을 판정한다. `RISK`면 여기서 멈추고 사용자에게 확인받는다.
2. 허용 경로와 금지 경로를 확정한다. 라운드 카운터를 1로 둔다. 이전 findings 목록을 빈 배열로 둔다.
3. 구현한다. `CLAUDE.md`의 최소 구현 원칙과 이 저장소의 코딩 규칙(주석·빈 줄 금지, 상수 상단 집중, Stage 함수 분리 유지)을 따른다. `commit`은 하지 않는다.
4. 등급에 맞는 검증을 실행한다. 아래 "검증" 절을 따른다. 실행하지 못했으면 `not-run`, 실패했으면 `fail`로 기록한다.
5. Codex 리뷰를 요청한다. 아래 "Codex 호출" 절의 형식을 그대로 쓴다.
6. 판정에 따라 분기한다.
   - `pass` → 8로 간다.
   - `warning` 또는 `fail` → 7로 간다.
   - 판정을 추출하지 못했으면 **멈춘다.** 추측하지 않고 응답 원문을 사용자에게 보여준다. CLI 경로면 stdout과 stderr를 함께 보여준다.
7. 중단 조건을 검사한다. **현재 카운터가 상한 이상이면** 수정 반복 없이 남은 findings를 그대로 8로 넘긴다. 다른 중단 조건에 걸려도 마찬가지다. 아무것도 걸리지 않으면 findings를 수정하고 카운터를 1 올린 뒤 4로 돌아간다.
8. closeout을 보고하고 커밋 승인을 요청한다. 승인 없이 커밋하지 않는다. 여기서 멈춘다.
9. 사용자가 이번 턴에서 명시적으로 커밋을 승인하면 아래 "커밋 게이트" 절에 따라 Codex에 넘긴다. 승인이 없으면 9를 실행하지 않는다.

## 검증

| 등급 | 명령 |
| --- | --- |
| `XS` / `S` | `.venv/Scripts/python.exe test_pipeline.py` |
| `M` / `L` | 위 + 웹캠 실측 |
| `RISK` | 위 전체 + 조건별 실측 비교 |

- 보고할 때 위 명령 이름을 그대로 쓴다.
- 실행하지 못했으면 `not-run`, 실패했으면 `fail`로 쓴다. 성공으로 반올림하지 않는다.

### 합성 신호 통과를 동작 확인으로 쓰지 않는다

`test_pipeline.py`가 쓰는 신호는 진폭이 정확하고 프레임 간격이 균일한 인공 정현파다. 실제 웹캠에는 조명 플리커, 자동노출 보정, 영상 압축, 머리 움직임, 프레임 드롭이 함께 들어온다. **합성 신호에서 72 BPM을 복원했다는 사실은 실제 얼굴에서 나온다는 근거가 아니다.**

파이프라인을 바꾸는 작업은 실제로 웹캠을 돌린다. 절차는 `capture-verifier` 에이전트에 있다. 관측할 것은 BPM, SNR, 실측 fps, 얼굴 검출률, 버퍼 채움 시간이다.

### 사람이 있어야 하는 검증은 자동화하지 않는다

Apple Watch 대조, 계단 오르내리기 추종성, 사진 공격 sanity check는 사람이 카메라 앞에 앉아 있어야 한다. **이 검증들을 도구가 대신 수행했다고 쓰지 않는다.** 사용자에게 실행을 요청하고, 결과를 받기 전까지는 `not-run`이다.

헤드리스 캡처는 사용자가 카메라 앞에 있는지, 정지 상태인지 통제하지 못한다. **그렇게 얻은 숫자는 파이프라인이 완주했다는 증거일 뿐 정확도의 증거가 아니다.** 보고에 그 구분을 적는다.

### 실측 데이터를 건드리지 않는다

`logs/`의 CSV는 사람이 카메라 앞에 앉은 시간이 들어 있어 다시 만들 수 없다. 라운드 중에 지우거나 덮어쓰지 않는다. 필요하면 새 태그로 새 세션을 만든다.

## 커밋 게이트

절차 8에서 사용자가 커밋을 승인한 뒤에만 실행한다.

**커밋 게이트는 판단과 실행을 나눈다.** Codex 샌드박스가 `.git`에 쓰지 못하기 때문이다. 근거는 아래 절에 있다.

| 단계 | 주체 | sandbox | 하는 일 |
| --- | --- | --- | --- |
| 판단 | Codex | `read-only` | 커밋 묶음별 경로와 Conventional Commits 메시지를 JSON으로 반환 |
| 실행 | Claude | 해당 없음 | 그 계획대로 `git add -A`와 `git commit`을 실행 |

커밋 범위 확정, 산출물 점검, 메시지 정리는 **여전히 Codex의 역할이다.** Claude는 계획을 바꾸지 않고 그대로 실행한다. **Codex 계획 없이 Claude가 임의로 커밋하지 않는다.** 계획을 받지 못했으면 closeout만 남기고 멈춘다.

**이 구조에서 `workspace-write` 사용처는 하나뿐이다.** 리뷰도 커밋 계획도 `read-only`이므로 Codex가 파일을 고칠 경로가 남지 않는다. 예외는 **`AGENTS.md`** 하나다.

### 커밋 계획 요청 프롬프트에 담을 것

- closeout 5개 전문
- **커밋 범위 분리 지시.** working tree에 여러 의도의 변경이 섞여 있으면 묶음별로 나누라고 명시한다. 이 정보를 빼면 전부 한 묶음이 된다
- **파일 하나를 hunk 단위로 쪼개지 말라는 지시.** 한 파일에 두 의도가 섞여 있어도 파일 단위로만 나눈다
- 계획을 아래 JSON 형식으로만 답하라는 지시. 파일은 만들지 말고 `git` 명령도 실행하지 말라고 적는다

```json
{
  "commits": [
    { "paths": ["<경로1>", "<경로2>"], "message": "feat: ..." }
  ],
  "blockers": ["커밋하면 안 되는 이유가 있으면 여기에. 없으면 빈 배열"],
  "notes": "묶음을 이렇게 나눈 근거"
}
```

`blockers`가 비어 있지 않으면 **커밋하지 않는다.** 사용자에게 원문을 올린다.

`notes`는 묶음 판단의 근거다. Claude가 계획을 그대로 실행하는 구조라 근거가 없으면 잘못된 묶음을 발견할 수단이 없다. **세 필드가 계약의 전부다.** 필드를 추가하려면 `AGENTS.md`, `.claude/skills/round/SKILL.md`, `.codex/agents/commit-planner.toml` 셋을 함께 고친다.

### Claude가 실행할 때 지킬 것

- **`git add -A -- <경로들>`를 쓴다.** 삭제된 경로에 `git add -- <path>`를 쓰면 `fatal: pathspec ... did not match any files`로 실패한다. `git mv`로 rename만 staged된 뒤 본문을 고친 경우에도 `-A`가 없으면 본문 변경이 통째로 빠진다. 둘 다 원본 저장소에서 실제로 겪었다
- 각 커밋 직전에 `git diff --cached -M --stat`으로 staged 범위를 확인한다. 계획과 다르면 커밋하지 않고 차이를 보고한다
- `.venv/`, `logs/`, `models/*.task`, `.env`가 staged에 보이면 커밋하지 않고 보고한다
- `.codex/` 아래는 **`.codex/agents/*.toml`만 추적 대상이다.** 그 밖의 `.codex/` 경로가 staged에 보이면 커밋하지 않고 보고한다. `.gitignore`가 이미 막지만 예외 규칙이 잘못 넓어졌을 때를 잡는다
- 커밋 후 브랜치와 커밋 해시를 사용자에게 보고한다
- 커밋 전에 `git config user.email`이 개인 주소(`dannyp0930@gmail.com`)인지 확인한다. **로컬 설정이 지워지면 조용히 전역의 회사 주소로 커밋된다**
- **`push`는 하지 않는다.** 커밋 승인은 push 승인이 아니다. 아래 "push 승인" 절을 본다

### Windows에서 Codex 샌드박스가 `.git`에 쓰지 못한다

원본 저장소 `healthviewer-demo-api`에서 실측한 사실이다. **같은 Windows 환경이므로 여기에도 적용된다고 보고 설계했다.** 이 저장소에서 다시 확인하지는 않았다.

`sandbox: "workspace-write"`를 넘겨도 staging이 실패했다.

```text
fatal: Unable to create '.../.git/index.lock': Permission denied
```

stale lock이 아니라 `.git` 디렉터리 쓰기 자체가 거부됐다. 같은 시점에 Claude 쪽 셸에서는 `.git`에 파일을 만들고 지우는 것이 성공했으므로 OS ACL 문제가 아니다.

우회를 두 가지 시도했고 둘 다 실패했다.

| 시도 | 결과 |
| --- | --- |
| `config`에 `sandbox_workspace_write.writable_roots = ["<저장소>\\.git"]` 추가 | 같은 `Permission denied` |
| `approval-policy: "never"`로 escalation 요청 자체를 제거 | 같은 `Permission denied` |

**따라서 Codex가 `git`을 실행하는 설계를 버린다.** 위 판단·실행 분리가 그 결론이다.

**`danger-full-access`로 올려서 우회하지 않는다.** 권한 우회 플래그를 새로 켜는 것은 이 스킬의 금지 항목이다.

### Codex는 `.codex/**`에도 쓰지 못한다

`.git`과 같은 제약이 `.codex/`에도 걸린다. **소유권 규칙이 "`.codex/**`는 Codex 소유"인데 Codex가 그 경로에 쓸 수 없다.** 이것도 원본 저장소 실측이다.

CLI `workspace-write`에서 저장소 루트 쓰기는 성공했고 `.codex/` 아래만 거부됐다.

```text
New-Item : 'agents' 경로에 대한 액세스가 거부되었습니다.
    + CategoryInfo : PermissionDenied: (...\.codex\agents:String) [New-Item], UnauthorizedAccessException
```

MCP 경로에서는 셸 쓰기가 경로와 무관하게 다른 형태로 죽는다.

```text
execution error: Io(Custom { kind: Other, error: "windows sandbox: missing field `code` at line 1 column 146" })
```

**따라서 `.codex/**`도 커밋과 같은 분리를 쓴다.** Codex가 파일 전문을 텍스트로 작성하고 Claude가 그대로 기록한다. Claude는 내용을 고치지 않는다.

`AGENTS.md` 수정은 MCP `workspace-write`로 성공했다. 저장소 루트의 기존 파일이라 두 제약에 걸리지 않는다.

### remote 이름을 확인하고 쓴다

이 저장소의 remote는 **`origin`**(`https://github.com/dannyp0930/vitals-lab.git`)이다. 그래도 프롬프트에 하드코딩하지 말고 `git remote`를 먼저 읽어 확인한 이름을 적는다. remote 이름은 clone마다 다르다. 형제 저장소 `healthviewer`는 remote 이름이 `github`이므로 오갈 때 혼동하면 push가 실패한다.

커밋 신원도 다르다. **이 저장소는 로컬 설정으로 개인 주소를 쓰고 전역 설정은 회사 주소다.** 전역 설정을 바꾸지 않는다.

### push 승인

**"커밋해"는 push 승인이 아니다.** 기본은 커밋까지만이다. 다만 사용자가 이번 턴에 커밋과 push를 함께 명시적으로 승인하는 경우가 있다(예: "커밋하고 푸시하자"). 그때는 다음을 지킨다.

1. `git remote`로 실제 remote 이름을 확인한다.
2. upstream이 없는 새 브랜치면 `-u`가 필요하다는 것을 프롬프트에 적는다. `git rev-parse --abbrev-ref --symbolic-full-name '@{u}'`가 `no upstream configured`로 실패하면 새 브랜치다.
3. 커밋 게이트 프롬프트에 push 명령과 "사용자가 이번 턴에 push를 명시적으로 승인했다"를 함께 적는다.
4. **PR 생성은 push 승인에 포함되지 않는다.** 프롬프트에 PR을 만들지 말라고 명시한다.

push 승인이 모호하면 실행하지 않고 되묻는다. 커밋만 승인된 상태에서 push를 프롬프트에 넣지 않는다.

### 승인 판정

- **"커밋해"는 커밋만 승인한 것이다. `push`는 포함되지 않는다.**
- 승인 표현이 모호하면 실행하지 않고 되묻는다. 커밋 범위가 예상과 다르면 실행 전에 범위를 먼저 확인받는다.
- 등급이 `RISK`면 절차 8의 승인만으로 진행하지 않는다. 커밋 범위를 다시 보여주고 한 번 더 확인받는다.
- `.claude/settings.json`의 허용 항목은 안전 가드가 아니다. 실제 통제는 사용자 승인 하나뿐이므로, 승인이 없으면 호출 자체를 만들지 않는다.

## Codex 호출

두 경로가 있다. **MCP를 기본으로 쓰고, 연결되지 않았을 때만 CLI로 내려간다.** 다만 토큰 관찰값이 필요하면 CLI를 쓴다. MCP는 토큰을 주지 않는다.

Codex를 부르는 용도는 넷이다. **어느 것도 Codex가 `git`을 실행하지 않는다.**

| 용도 | sandbox | 경로 | 비고 |
| --- | --- | --- | --- |
| 리뷰 (절차 5) | `read-only` | MCP 기본, CLI 대체 | 토큰 관찰이 필요하면 CLI |
| 커밋 계획 (절차 9) | `read-only` | MCP 기본, CLI 대체 | 계획 JSON만 받는다. 실행은 Claude |
| `AGENTS.md` 수정 | `workspace-write` | MCP 기본, CLI 대체 | `AGENTS.md`에만 |
| `.codex/**` 내용 작성 | `read-only` | MCP 기본, CLI 대체 | 파일 전문을 텍스트로 받는다. 기록은 Claude |

`.mcp.json`에 `codex` 서버가 `codex mcp-server`로 등록되어 있다. `codex mcp-server`는 `codex mcp`와 다르다. `codex mcp`는 Codex가 외부 MCP를 쓰는 쪽을 관리하는 명령이고, 우리가 쓰는 것은 Codex 자신을 서버로 띄우는 `codex mcp-server`다.

### MCP 경로 (리뷰 기본)

`mcp__codex__codex` tool을 호출한다.

| 파라미터 | 값 | 비고 |
| --- | --- | --- |
| `prompt` | 프롬프트 전문 | 필수 |
| `sandbox` | `read-only` 또는 `workspace-write` | **생략 금지** |
| `cwd` | `D:/workspace/vitals-lab` | **생략 금지** |

**`sandbox`를 생략하면 쓰기가 허용된다.** 리뷰 호출에서 빠뜨리면 리뷰어가 파일을 고칠 수 있고, 조용히 그렇게 된다. **리뷰와 커밋 계획은 항상 `read-only`다.**

`sandbox: "read-only"`는 원본 저장소 실측에서 새 파일 생성과 기존 파일 수정을 모두 막았다. 리뷰어가 조용히 코드를 고칠 경로는 없다.

**라운드마다 새 스레드를 쓴다.** `mcp__codex__codex-reply`로 대화를 이어가면 캐시가 살아 비용이 줄 수 있지만, 리뷰어가 이미 본 것을 다시 보지 않고 넘길 수 있고 그러면 수정이 실제로 반영됐는지 확인하지 못한다.

`codex-reply`는 **같은 라운드 안의 좁은 복구용으로만** 남긴다. 판정 추출이 실패했을 때 출력 형식만 다시 요구하는 경우 같은 것이다.

### 프로젝트 설정은 신뢰 등록된 저장소에서만 적용된다

**전역 `~/.codex/config.toml`에 이 저장소가 신뢰 등록되어 있지 않으면 프로젝트 설정이 무시되고 전역 설정으로 떨어진다.** 원본 저장소에서 실측으로 확인했다.

```text
codex exec --json --sandbox read-only  (cwd = 신뢰 등록된 저장소)   → exit 0
codex exec --json --sandbox read-only  (cwd = 등록 안 된 저장소)    → exit 1
```

등록되지 않은 쪽은 전역 모델을 쓰고, 그 모델이 설치된 CLI 버전에서 지원되지 않아 400으로 죽었다.

```json
{
  "type": "error",
  "status": 400,
  "error": {
    "message": "The '<전역 설정 모델>' model requires a newer version of Codex."
  }
}
```

등록은 전역 `~/.codex/config.toml`에 아래 형태로 들어 있다.

```toml
[projects.'D:\workspace\vitals-lab']
trust_level = "trusted"
```

**2026-08-28 기준 이 저장소는 `[projects.'d:\workspace\vitals-lab']`로 등록되어 있다.** 등록이 풀리면 Codex 호출이 400으로 죽으므로, 400을 만나면 이 등록부터 확인한다.

**이 파일은 전역 설정이고 사용자 홈에 있다.** 저장소 밖 파일을 도구가 임의로 고치지 않는다. 등록이 필요하면 사용자에게 알리고 승인을 받는다. 보통은 그 디렉터리에서 `codex`를 대화형으로 한 번 실행하면 신뢰 여부를 묻고 등록된다.

`cwd`가 저장소 밖일 때도 같은 증상이 난다. 둘 다 원인은 "프로젝트 설정이 적용되지 않음"이다.

모델명을 문서나 프롬프트에 그대로 적지 않는다.

### CLI 경로 (MCP를 쓸 수 없을 때, 그리고 비용 측정용)

두 경우에 쓴다.

1. **MCP tool을 호출할 수 없을 때.**
2. **토큰 관찰값이 필요할 때.** MCP 경로는 토큰을 주지 않는다.

`claude mcp get codex`의 상태 표시를 판단 근거로 삼지 않는다. 원본 실측에서 그 명령이 `⏸ Pending approval`을 보고하는 동안에도 tool 호출이 정상 동작했다. **tool이 호출 가능한지가 유일한 판단 기준이다.**

**저장소 루트에서 실행한다.** 프롬프트는 파일로 쓰고 stdin 리다이렉트로 넘긴다. 파이프를 쓰지 않는다.

```bash
codex exec --json --sandbox read-only - < <프롬프트파일> > <출력파일> 2> <에러파일>
```

- `--json`은 필수다. 이것 없이는 판정을 안정적으로 뽑을 수 없다.
- `--sandbox read-only`는 필수다.
- stderr를 반드시 분리한다. 정상 실행에서도 `ERROR codex_models_manager::cache: failed to load models cache` 같은 줄이 stderr로 나온다. 이 줄은 실패 신호가 아니다. exit code로 판단한다.
- **프롬프트 파일, stdout 파일, stderr 파일 세 개 모두 저장소 밖 scratchpad에 만든다.** 저장소 안에 만들면 리뷰 산출물이 working tree에 섞여서 다음 라운드의 diff를 오염시킨다. 상대경로 `cd`를 쓰지 말고 절대경로를 쓴다.

### 판정 추출 규칙

두 경로 모두 **첫 비어있지 않은 줄에 고정한 `^VERDICT:\s*(pass|warning|fail)\s*$` 매칭**으로 판정을 뽑는다.

**본문 전체에서 `pass`를 검색하지 않는다.** 리뷰 본문에는 `test_pipeline.py = pass`처럼 판정과 무관한 `pass`가 들어있다. 전체 검색은 `warning`이나 `fail` 응답을 `pass`로 오판해 라운드를 조기 종료시킨다. 첫 줄 고정 매칭이 이 오판을 막는 유일한 장치다.

그래서 리뷰 프롬프트에 "첫 줄에 정확히 `VERDICT: pass|warning|fail` 형식으로 쓰라"를 반드시 넣는다. 이 지시가 빠지면 추출이 매번 실패한다.

매칭에 실패하면 추출 실패로 보고 절차 6에 따라 멈춘다.

#### MCP 경로

tool 결과의 `structuredContent.content`가 판정 소스다.

```json
{
  "content": [{ "type": "text", "text": "VERDICT: fail\n..." }],
  "structuredContent": {
    "threadId": "019fcf82-...",
    "content": "VERDICT: fail\n..."
  }
}
```

**MCP 경로에서는 토큰 관찰값을 얻을 수 없다.** 서버는 `token_count` 이벤트로 토큰을 보내지만 그것은 MCP notification이고 tool 결과에는 담기지 않는다. **MCP 경로로 돈 라운드는 closeout의 토큰 줄을 `측정 불가`로 쓴다.** 숫자를 추측해 적지 않는다.

#### CLI 경로

**stdout raw text를 파싱하지 않는다.** JSONL만 쓴다.

```jsonl
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"..."}}
{"type":"turn.completed","usage":{"input_tokens":25156,"cached_input_tokens":2432,"output_tokens":170,"reasoning_output_tokens":134}}
```

추출 절차:

1. stdout을 줄 단위로 읽고 `JSON.parse`에 성공하는 줄만 남긴다. 실패하는 줄은 버린다.
2. `type === "item.completed" && item.type === "agent_message"`인 항목의 `item.text`를 모은다. 여러 개면 마지막 것을 판정 소스로 쓴다.
3. 그 텍스트에 위 첫 줄 고정 매칭을 적용한다.
4. `type === "turn.completed"`의 `usage`에서 `input_tokens`와 `cached_input_tokens`를 closeout에 기록한다.

### 리뷰 프롬프트에 담을 것

```text
원본 사용자 요청: <원문>
작업 등급: <XS|S|M|L|RISK>
라운드: <n>/<max>
허용 경로: <목록>
금지 경로: <목록>
실행한 검증: test_pipeline.py = pass|fail|not-run
웹캠 실측: <BPM, SNR, fps, 얼굴 검출률, 조건 태그, 또는 not-run>
이전 라운드 findings: <있으면 원문, 없으면 "없음">
```

diff는 프롬프트에 싣지 않는다. Codex가 같은 저장소에서 직접 읽게 한다.

**범위를 반드시 허용 경로로 제한한다.**

```bash
git status --short -uall -- <허용경로...>
git diff --stat -- <허용경로...>
git diff -- <허용경로...>
```

- `git status --short -uall`을 반드시 포함시킨다. `git diff`만으로는 untracked 파일이 빠지고 새로 만든 파일이 리뷰에서 누락된다.
- 프롬프트에 "허용 경로 밖의 파일은 리뷰하지 말고, 발견해도 findings로 올리지 말라"를 넣는다.
- `.venv/`와 `logs/`는 `.gitignore` 대상이라 diff에 안 잡히지만, 혹시 보이면 무시하라고 적는다.

리뷰 기준은 아래 블록을 그대로 넣는다.

```text
Review with the minimum-implementation rule.
Do not report lack of abstraction, missing type hints, missing docstrings, or low test coverage as a finding by itself.
This repository forbids comments and blank lines in Python files by project rule. Do not report their absence as a finding.
Do report unnecessary complexity, speculative abstractions, unused options, new dependencies for standard-library work, missed requirements, and numerical errors in the signal-processing path.
Never simplify away input validation, error handling, numerical correctness of the DSP chain, the SNR gate, or measurement logging.
This is a throwaway Phase 0 experiment whose code will be rewritten in Phase 1. Do not report the code being experimental as a finding.
Never accept a reported measurement that was not actually observed.
```

마지막으로 출력 형식을 지정한다. 첫 줄에 `VERDICT: pass|warning|fail`을 두고, 이어서 findings를 severity, file:line, risk, suggested fix로 쓰게 한다. 파일은 만들지 말고 텍스트로만 답하게 한다.

### 이 저장소에서 특히 물어볼 것

리뷰 프롬프트에 상황에 맞게 골라 넣는다.

- POS 구현이 논문 수식과 맞는지. 정규화, 투영 행렬, `alpha = std(S1)/std(S2)`, overlap-add 누적
- 대역통과 범위가 0.7~4.0Hz에서 넓어지지 않았는지. 필터 차수와 `filtfilt` 사용
- 프레임 타임스탬프 지터가 균일 격자로 리샘플링되는지
- SNR 계산이 피크와 하모닉만 신호로 잡는지. `SNR_MIN_DB`가 근거 없이 낮아지지 않았는지
- 신규 의존성이 BSD/MIT/Apache 계열인지
- 관측하지 않은 수치가 보고나 문서에 적히지 않았는지
- `logs/` 삭제나 덮어쓰기가 없는지
- `HANDOFF.md` §8 범위 밖 작업이 섞이지 않았는지

## 중단 조건

| 조건 | 동작 |
| --- | --- |
| 판정 `pass` | 종료 |
| 라운드 카운터 >= 상한 | 중단. 남은 findings를 그대로 보고 |
| 같은 finding이 2회 나옴 | 즉시 중단. 재시도가 효율적이지 않다는 신호다 |
| 등급이 `S` | 리뷰 1회 후 종료 |
| 등급이 `RISK` | 수정 반복 없음 |
| 판정 추출 실패 | 중단. 원문 노출 |
| 검증이 `fail`이고 원인 불명 | 중단. 사용자에게 올린다 |

같은 finding 판정은 파일 경로와 지적 내용으로 비교한다. 표현이 조금 달라도 같은 지점을 가리키면 같은 것으로 본다.

라운드 상한 기본값은 2다. 카운터는 1에서 시작하므로 상한 2는 **Codex 리뷰를 최대 2회** 실행한다는 뜻이다. 절차 7의 검사는 `카운터 >= 상한`이며 `>`가 아니다.

### 반복이 끝난 뒤 findings가 남았을 때

중단 조건에 걸려 멈췄는데 findings가 남아 있으면 성격을 두 갈래로 나눈다.

- **사실 오류, 신호 처리의 수치적 결함, 보안 결함, 규칙 위반처럼 명백히 틀린 것**은 고친다. 알면서 틀린 내용을 남기지 않는다. 다만 **고친 뒤 재리뷰를 하지 않으므로 closeout에 "수정했으나 재리뷰 없음"을 반드시 명시한다.**
- **판단이 갈리는 것, 설계 취향, 추가 조사가 필요한 것**은 고치지 않고 findings 원문을 그대로 closeout에 올린다.

`S` 등급에서도 이 규칙이 적용된다. `S`는 리뷰를 1회만 하라는 뜻이고 명백한 오류를 방치하라는 뜻이 아니다.

## 비용

- **Codex 호출에는 비용 상한 플래그가 없다.** 라운드당 목표 비용은 목표일 뿐 강제가 아니다.
- 실질적인 비용 가드는 **라운드 수 상한과 사용자 승인 두 개뿐이다.** 이 사실을 사용자에게 숨기지 않는다.
- 원본 저장소 `healthviewer-demo-api` 실측에서 리뷰 1회가 input 11만~57만 토큰이었다. **그 숫자를 이 저장소의 값으로 보고하지 않는다.** 대상 코드베이스가 다르다.
- **이 저장소의 관측값은 [references/measurements.md](references/measurements.md)에 있다.** 라운드마다 관측한 값을 그 문서에 행으로 추가한다.
- **커밋 1회에 계획 호출이 붙으므로 라운드당 Codex 호출은 실질 2회다.** `blockers`가 나오면 재요청까지 3회다.
- 관측하지 못하면 `측정 불가`로 쓴다.

## 보고 문체

`.claude/output-styles/caveman-ponytail.md` §1이 정본이다. 라운드 중 chat에 쓰는 것도 전부 그 규칙을 따른다. **규칙을 이 문서에 중복해 적지 않는다.**

## Closeout

```text
1. 원본 요청
2. 변경 파일
3. 검증 결과: test_pipeline.py = pass/fail/not-run
   웹캠 실측: BPM, SNR, fps, 얼굴 검출률, 조건 태그, 또는 not-run
4. 미확정 가정 (등급을 규칙보다 낮게 잡았으면 그 근거를 여기 쓴다)
5. 리뷰 질문
---
라운드: n회 / Codex 판정: pass|warning|fail
관찰 토큰: 라운드별 input n (cached n), output n
```

## 금지

- **Codex 커밋 계획 없이 `git commit`.** Claude는 실행만 하고 무엇을 커밋할지 스스로 정하지 않는다.
- Codex 커밋 계획을 임의로 고쳐서 실행하는 것. 계획과 다르게 커밋해야 할 이유가 보이면 커밋하지 않고 사용자에게 올린다.
- 사용자 승인 없는 커밋 계획 요청.
- `blockers`가 비어 있지 않은데 커밋하는 것.
- `git reset --hard`, `git restore`, `git checkout -- <file>`. 되돌리기는 `RISK`다.
- `logs/` 삭제나 덮어쓰기. 다시 만들 수 없는 실측 데이터다.
- `push` 자동화. 커밋 승인은 push 승인이 아니다.
- PR 생성. push 승인에 포함되지 않는다.
- 강제 push.
- 커밋 신원 확인 없이 커밋하는 것. 로컬 설정이 지워지면 회사 주소로 커밋된다.
- Codex stdout raw text 파싱. CLI 경로는 `--json` JSONL, MCP 경로는 `structuredContent.content`만 쓴다.
- 리뷰나 커밋 계획을 `workspace-write` 이상으로 호출. `workspace-write`는 `AGENTS.md` 수정에만 쓴다.
- Codex가 작성한 `.codex/**` 파일 내용을 Claude가 고쳐서 기록하는 것.
- **MCP 호출에서 `sandbox` 생략.**
- **MCP 호출에서 `cwd` 생략.**
- 관측하지 못한 토큰 수치를 추측해 closeout에 적는 것. `측정 불가`로 쓴다.
- 원본 저장소의 실측값을 이 저장소의 값으로 보고하는 것.
- **합성 신호 통과만으로 웹캠에서 동작한다고 보고하는 것.**
- **사람이 카메라 앞에 있어야 하는 검증을 도구가 수행했다고 보고하는 것.**
- **관측하지 않은 BPM·SNR·fps를 보고나 문서에 적는 것.** 이 저장소에서 가장 위험한 실패다.
- `RISK` 등급 자동 진행.
- 권한 우회 플래그를 새로 켜는 것.
- 판정을 추출하지 못했을 때 `pass`로 간주하고 넘어가는 것.
