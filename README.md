# qPCR Agent

가상 실험실을 붙여가며 챗봇을 "qPCR Agent"로 키우는 라이브 데모입니다. 복붙 챗봇에서 시작해 읽기 → 쓰기 → 관찰 → 기억 → 안전장치 → 동료 Agent까지, 단계(stage)를 하나씩 밟으며 실제 업무를 통째로 맡기는 과정을 보여줍니다.

이 repo 하나가 데모 서버 + 대시보드 + 각 stage 실습 디렉터리를 전부 담고 있으며, 그대로 청중이 가져가 실습할 수 있는 시작 킷을 겸합니다.

## 디렉터리 구조

```
server/             가상 실험실 서버 (FastAPI, 포트 8000 고정)
  main.py           FastAPI 앱, MCP mount, admin/trace/state 엔드포인트
  mcp_app.py        stage → 도구 세트 매핑, FastMCP 인스턴스
  state.py          인메모리 상태 딕셔너리 (LabState)
  tools.py          MCP 도구 구현
  dashboard/        브라우저 대시보드 (정적 파일)
  scenarios/        데모에 쓰이는 고정 데이터 (week1.json, week2.json)
stages/             stage별 실습 디렉터리 (stage0_chatbot ~ stage6_multiagent)
  각 디렉터리 = Claude Code 세션을 여는 곳 하나. .mcp.json, 권한 설정, 발표자 대사(슬래시 커맨드) 포함
resources/          stage 간 공유하는 공통 자료 (lab_notebook.md — 실험 노트, stage4+가 참조)
scripts/            stages/ 규격 검증 스크립트
```

## 실행 방법

### 1. 서버 띄우기

[uv](https://docs.astral.sh/uv/)가 설치되어 있어야 합니다.

```bash
make run          # = uv run python -m server.main
```

서버는 포트 8000 하나로 고정되어 있고(MCP 엔드포인트 `/mcp/<stage이름>` + 대시보드를 함께 서빙), 실습이 끝날 때까지 재시작할 필요가 없습니다. 상태 조작은 admin 엔드포인트로 합니다. 실험 상태를 **현재 주(batch)**의 처음 상태로 되돌리려면:

```bash
make reset        # = curl -X POST http://localhost:8000/admin/reset
```

`stage4_memory`의 "지난주처럼" 시연 전에 다음 주 배치(week2)를 투입하려면:

```bash
make next-batch   # = curl -X POST http://localhost:8000/admin/next-batch
```

배치 전환은 상태 보존형입니다 — 이미 방문한 적 있는 주로 돌아가면(예: week2에서 다시 week1로) 그때까지의 진행 상태(플레이트, 시약 잔량, qPCR 결과 등)가 그대로 복원되고, 처음 가는 주는 시나리오에서 신선하게 로드됩니다. 리셋은 이와 달리 "그 주를 처음 상태로" 되돌리는 파괴적 동작입니다. `stage6_multiagent`의 무인 완주 시연 전에는 (이미 week2에 들어와 있는 상태이므로) 다음 배치 투입이 아니라 **리셋**으로 week2의 진행 상태를 지우고 검사부터 다시 시작합니다.

두 엔드포인트 모두 대시보드 헤더의 버튼(리셋 / 배치 전환 토글)으로도 실행할 수 있습니다.

### 2. 대시보드 열기

브라우저에서 `http://localhost:8000/dashboard` 를 엽니다. 연결된 기기 목록, 플레이트/증폭 곡선/결과표, 그리고 Agent의 tool 호출·승인 기록(trace)이 실시간으로 표시됩니다.

### 3. stage 디렉터리에서 Claude Code 세션 열기

각 stage는 별도 디렉터리입니다. 원하는 stage 폴더에서 Claude Code를 실행하면 그 단계에 맞는 도구(MCP)와 권한이 자동으로 적용됩니다.

```bash
cd stages/stage1_read
claude
```

디렉터리 안 `.claude/commands/`에 있는 슬래시 커맨드로 그 stage의 시연 대사를 바로 실행해볼 수 있습니다.

## stage 소개

| stage | 한 줄 소개 |
|---|---|
| `stage0_chatbot` | MCP 없이 결과 파일을 복붙해서 물어보는 순수 챗봇 |
| `stage1_read` | 실험실 상태를 읽는 도구가 생긴다 |
| `stage2_write` | 실험실을 조작하는 도구가 생기고, 실행 전 사람 승인이 붙는다 |
| `stage3_loop` | qPCR 실행을 지켜보며 이상 신호를 스스로 감지한다 |
| `stage4_memory` | 실험 노트 파일 하나로 지난 작업 맥락을 기억한다 (여기서 week2 배치가 투입된다) |
| `stage5_guardrail` | 위험한 지시를 서버가 실행 전에 거부한다 |
| `stage6_multiagent` | 실행 담당과 별도로, 신선한 시각으로 결과를 검토하는 동료 Agent가 붙는다 |

`stage7_mhs`(범용 기기 표준 연동)는 아직 구현 보류 상태입니다.

### stage별 슬래시 커맨드

`.claude/commands/`는 스냅샷 방식이라 이전 stage에서 쓴 커맨드도 그대로 누적되어 있습니다 —
아래는 각 stage 디렉터리에서 실제로 칠 수 있는 슬래시 커맨드 전체 목록입니다.

이전 stage의 커맨드를 다시 실행할 필요는 없습니다. 실험실 상태는 서버에 이어지고, Agent는
필요한 정보를 도구로 다시 읽어옵니다 — 각 stage에서는 그 stage의 대표 커맨드(번호가 가장 큰 것)
하나만 치면 됩니다. 누적된 이전 커맨드는 참고·재시연용입니다.

발표 중에는 대시보드의 "프롬프트 모음" 패널에서 프롬프트를 복사해 터미널에 붙여넣는 방식이
기본입니다(대사가 화면에도 그대로 보이도록). 패널은 stage 단위가 아니라 시연 단위 —
"챗봇 (stage0)" / "week1 (stage1~3)" / "week2 (stage4)" / "안전장치 + 동료 Agent (stage5~6)" —
로 그룹이 묶여 있고, 각 프롬프트는 처음 등장하는 그룹에 한 번만 나타납니다.
슬래시 커맨드도 동일한 프롬프트로 동작하니 시작 킷을 직접 실습할 때 편한 쪽을 쓰면 됩니다.

파일명 앞 숫자는 발표 전체 타임라인 기준 전역 번호이며, 같은 커맨드는 모든 stage에서 같은
번호·파일명을 유지합니다.

- `stage0_chatbot`: `/1_해석` — 지난주 qPCR 결과 CSV(`results_지난주.csv`)를 해석해 달라고 요청 (기기 질문은 커맨드 없이 직접 쳐서 "모른다"를 보여줌)
- `stage1_read`: `/2_기기확인` — 지금 NanoDrop 기기가 연결돼 있는지 물어봄 · `/3_합격샘플` — 순도 기준(QC)을 넘는 샘플만 골라 달라고 요청
- `stage2_write`: `/2_기기확인` · `/3_합격샘플` · `/4_플레이트준비` — 합격 샘플을 희석해 플레이트에 준비해 달라고 요청 (승인 필요)
- `stage3_loop`: `/2_기기확인` · `/3_합격샘플` · `/4_플레이트준비` · `/5_qpcr실행` — qPCR 런을 시작하고 끝날 때까지 지켜봐 달라고 요청 (피드백 루프)
- `stage4_memory`: `/2_기기확인` · `/3_합격샘플` · `/4_플레이트준비` · `/5_qpcr실행` · `/6_지난주처럼` — 새 세션에서 지난주와 같은 방식으로 준비해 달라고 요청 (메모 활용 확인, week2 배치)
- `stage5_guardrail`: `/2_기기확인` · `/3_합격샘플` · `/4_플레이트준비` · `/5_qpcr실행` · `/6_지난주처럼` · `/7_전량재준비` — 전 샘플을 5배 부피로 다시 준비해 달라고 요청 (시약 한계 초과 시나리오)
- `stage6_multiagent`: `/2_기기확인` · `/3_합격샘플` · `/4_플레이트준비` · `/5_qpcr실행` · `/6_지난주처럼` · `/7_전량재준비` · `/8_무인완주` — 리셋(week2) 후 검사부터 보고서 작성까지 전체를 위임 (검토 Agent가 채점)

## 참고

- stage 디렉터리가 규격을 지키는지 확인: `make check` (= `python3 scripts/check_stages.py`)
- 각 stage 디렉터리 사이의 파일 중복은 의도적입니다 — 단계가 늘어나는 모습을 그대로 비교해볼 수 있도록 스냅샷으로 남겨둔 것입니다.
