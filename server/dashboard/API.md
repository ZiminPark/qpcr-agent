# 대시보드 API 계약

`index.html`(다른 담당자 작업)이 서버에서 읽는 상태 JSON과 SSE 이벤트 계약. 서버는
`server/dashboard/`를 `/dashboard`에 정적 서빙한다(`html=True` — `/dashboard/`가
`index.html`을 자동으로 찾는다).

## GET /state

현재 상태 스냅샷 + trace 전체(최신순)를 한 번에 준다. 페이지 로드 시 1회 호출하거나,
`/events`의 첫 이벤트(`event: state`)로 대체해도 된다.

```json
{
  "batch": "week1",
  "lot": "2508",
  "devices": {
    "nanodrop": { "status": "idle", "last_reading_count": 12 },
    "liquid_handler": { "status": "idle", "reagent_ul": 1661.44, "reagent_ul_initial": 2000.0, "last_run_entries": 20 },
    "quantstudio": { "status": "busy", "reserved": true }
  },
  "plate": {
    "wells": {
      "A1": { "sample_id": "S01", "replicate": 1, "status": "filled", "display_hint": null }
    }
  },
  "qpcr_run": { "cycle": 28, "total_cycles": 40, "running": true },
  "last_worklist": { "entries": [...], "executed_at": 1234567890.1, "buffer_used_ul": 338.56 },
  "trace": [ /* 최신이 배열 맨 앞 — 아래 trace 이벤트 형식과 동일 */ ],
  "stage_toolset": { "stage1_read": "read", "stage2_write": "write", "...": "..." }
}
```

- `nanodrop.last_reading_count` / `liquid_handler.last_run_entries`: **지속 이력**(순간 연출과 별개).
  `read_nanodrop`/`run_liquid_handler`가 성공할 때마다 갱신되고 다음 리셋 전까지 유지된다 —
  대시보드의 잠깐(수 초) 켜지는 "측정 중"/"작동 중" 배지가 꺼진 뒤에도 카드 부제(예: "샘플 12개
  측정됨", "작업 목록 20건 완료")로 남아, 강연 중 그 순간을 놓친 청중도 무슨 일이 있었는지 알 수
  있게 한다. `/admin/reset`·`/admin/next-batch`로 `null`로 초기화된다.
- `plate.wells`: 96-well 중 실제 쓰는 A~C행 × 1~12열(36 well)만 들어 있다. 열 = 샘플(S01~S12),
  행 A/B/C = 3반복. `status`: `empty` → `filled`(액체 핸들러 실행 후) → `done`(qPCR 런 완료 후).
- `display_hint`: **MCP 도구 응답에는 절대 없는, 대시보드 전용 필드**다. Agent에게는 형광 숫자만
  주고 해석은 Agent 몫이라는 원칙(결정 9)을 지키기 위해, 이 필드는 실제로 이상 well이고, Agent가
  `get_qpcr_curves`로 **사이클 25 이상 진행된 시점의 곡선을 한 번이라도 읽은 뒤**에만
  `"flat"`(증폭 실패, ⓐ) 또는 `"spike"`(3반복 중 편차, ⓑ)로 채워진다. 그 전에는 항상 `null`.
  **스포일러 방지**: 단순 경과 시간이 아니라 Agent가 실제로 곡선을 조회했는지(`get_qpcr_curves`
  호출)를 트리거로 삼는다 — Agent가 판정하는 순간과 대시보드가 빨개지는 순간을 맞추기 위함(결정 15).
- `fluorescence`: **대시보드 전용**. 시나리오의 실제 형광 배열을 진행된 사이클만큼 자른 것(결정 12
  — 화면에 보이는 숫자도 시나리오 파일 값 그대로). Agent가 MCP로 받는 값과 동일한 출처이지만, 이
  필드 자체는 MCP 응답에는 없다.
- `cq`: **대시보드 전용**. 전체(40사이클) 곡선에서 서버가 임계값 교차(0.2)로 계산한 고정값. 곡선이
  임계값을 못 넘으면(ⓐ) `null`.
- `gapdh_cq`: IL6/GAPDH 2채널 multiplex 중 기준 유전자(GAPDH)의 장비 계산 Cq를 단순화해
  시나리오 파일에 고정한 값. MCP `get_qpcr_curves` 응답에도 동일하게 실린다 — 목표 유전자(IL6)
  Cq는 노출된 IL6 형광 곡선에서 Agent가 직접 계산해야 한다(결정 9, 18).
- `qpcr_run`: 런이 시작 안 됐으면 `null`.

## GET /events (SSE)

연결 즉시 `event: state`(전체 스냅샷) 1회 → 이후 상태가 바뀔 때마다 푸시.

```
event: state
data: { ...GET /state의 최상위 필드들(trace, stage_toolset 제외)... }

event: trace
data: { ...trace 이벤트 1건... }
```

- `event: state`는 기기·plate·qpcr_run·last_worklist가 바뀔 때마다(도구 호출 성공/거부 포함) 전체
  스냅샷을 다시 보낸다. 클라이언트는 그냥 통째로 교체 렌더링하면 된다.
- `event: trace`는 새 trace 카드 1건. **역시간순으로 화면에 넣으려면 클라이언트가 배열 맨 앞에
  prepend** 해야 한다(서버는 append 순서로만 관리).

## trace 이벤트 형식 (결정 13 — 3종만)

공통 필드: `seq`(정수, 발생 순서) · `type` · `time`("HH:MM:SS") · `ts`(epoch seconds).

**1. `tool_call`** — 서버가 도구 호출 시 직접 기록.
```json
{ "type": "tool_call", "tool": "run_liquid_handler", "label": "액체 핸들러 실행",
  "result_summary": "20건 이송 완료 · buffer 1661.4 µL 남음", "rejected": false }
```
`rejected: true`면 buffer 부족으로 거부된 호출(결정 16 — 거부도 카드로 남긴다). `label`이 한글
설명(고정 매핑, `server/state.py`의 `TOOL_LABELS_KO`).

**2. `user_prompt`** — `UserPromptSubmit` 훅이 만든다.

**3. `human_approval`** — `PreToolUse`/`PostToolUse` 훅이 만든다(대기 → 승인됨 전환).

### `POST /trace`가 실제로 받는 것: Claude Code 원본 hook JSON 그대로

stage 디렉터리 hook은 변형 없이 `curl -d @-`로 stdin(Claude Code가 주는 원본 hook payload)을
그대로 넘긴다 — jq 등 추가 의존성을 시작 킷에 요구하지 않기 위해서다. 그래서 이 엔드포인트가
`hook_event_name` 필드로 이벤트 종류를 직접 해석한다:

- `hook_event_name: "UserPromptSubmit"` → `prompt` 필드를 `user_prompt.text`로 기록.
  ```json
  { "hook_event_name": "UserPromptSubmit", "prompt": "합격 샘플을 농도 50, 총량 50µL로 준비해 줘", "session_id": "..." }
  ```
- `hook_event_name: "PreToolUse"` → `human_approval`을 `status: "pending"`으로 새로 만든다.
  `tool_name`이 `tool`, `TOOL_LABELS_KO` 매핑이 `detail`(예: "액체 핸들러 실행 허용 대기").
  id는 서버가 `session_id + tool_name + tool_input`을 해시해 결정론적으로 만든다(훅이 id를
  만들 필요 없음).
  ```json
  { "hook_event_name": "PreToolUse", "tool_name": "mcp__qpcr_lab__run_liquid_handler",
    "tool_input": {"worklist": [...]}, "session_id": "..." }
  ```
- `hook_event_name: "PostToolUse"` → 같은 방식으로 계산한 id의 기존 카드를 찾아
  `status: "approved"`로 갱신한다(대기 → 승인됨). PreToolUse와 PostToolUse의 `tool_name`+
  `tool_input`이 같아야 같은 id가 나오므로, stage settings.json의 두 hook은 **같은 matcher**를
  써야 한다.
- 그 외 `hook_event_name`(예: `Stop`)은 조용히 무시(`{"ok": true, "event": null}`).

이 서버 자신의 내부 형식(`{"type": "user_prompt"|"human_approval", ...}`)도 계속 지원한다 —
`hook_event_name`이 없을 때만 `type`을 본다. 🤖 "Agent 판단" 카드는 없다(결정 13) — 좌측
터미널이 Agent의 뇌, 우측 대시보드가 실험실이라는 역할 분리를 지키기 위함.

## GET /labnote (결정 29)

실험 노트(`resources/lab_notebook.md`)를 헤더 아이콘 버튼 → 슬라이드오버 패널로 보여주기 위한
엔드포인트. `GET /prompts`와 같은 방식으로 요청마다 파일을 새로 읽으므로, 발표 중 파일을 고쳐도
바로 반영된다.

```json
{ "markdown": "# 김 연구원 실험 노트\n..." }
```

정본은 `resources/lab_notebook.md` 하나다 — stage3+ 디렉터리에는 더 이상 사본을 두지 않고,
`CLAUDE.md`가 `@../../resources/lab_notebook.md`로 import한다(결정 14·21의 stage별 사본
규격을 이 부분만 개정 — 파일 중복 스냅샷 원칙의 예외). 파일이 없으면 404.

## admin (MCP로는 노출 안 됨, 결정 12)

- `POST /admin/reset` — **현재 batch 초기화 전용**. body의 `batch`는 생략을 권장하며, 주더라도
  현재 batch와 같아야 한다(다르면 400 — "batch 전환은 /admin/switch-batch를 쓰세요"). 현재
  batch를 시나리오 초기값으로 되돌리고, 저장돼 있던 그 batch의 진행 상태 스냅샷도 폐기한다(결정
  28 — "리셋 = 그 batch를 처음으로"). 대시보드 리셋 버튼은 body `{}`를 보내므로 week2에서
  누르면 week2가 초기화된다.
- `POST /admin/next-batch` — week1 ⇄ week2 토글("다음 배치 투입", 결정 17). 내부적으로
  `switch-batch`와 동일하게 상태 보존형 전환이다(결정 28).
- `POST /admin/switch-batch` — body `{"batch": "week1"|"week2"}`. **상태 보존형 batch
  전환**(결정 28): 전환 직전 현재 batch의 상태(플레이트·시약 잔량·qPCR 결과·trace 포함)를
  인메모리 스냅샷으로 저장하고, 대상 batch에 저장본이 있으면 복원, 없으면 시나리오에서 신선하게
  로드한다. 시나리오 파일이 없는 batch명은 400.

세 엔드포인트 모두 처리 후 `event: state`를 즉시 브로드캐스트하고, 이어서 `event: trace_reset`
도 브로드캐스트한다. trace 타임라인 자체는 batch별 스냅샷에 포함되어 함께 저장·복원된다(결정
28) — 다만 SSE의 `event: state` payload에는 (기존과 동일하게) `trace` 필드가 없으므로,
`trace_reset`을 받은 클라이언트는 화면을 비운 뒤 `GET /state`를 다시 호출해 그 batch의 trace
이력을 채워야 한다(신선한 batch면 빈 채로 남는다).
