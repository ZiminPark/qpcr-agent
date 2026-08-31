# 발표 데모 구현 스펙 결정 로그

그릴링 세션(2026-08-31)에서 정한 순서대로. 근거는 발표 기획 문서와 대화 기록 참조.

1. **repo 범위**: 이 repo 하나에 발표 자산 전부(서버, 대시보드, stage 디렉터리, 시나리오, MHS, 시작 킷)를 담는다. 이 repo가 청중 공유용 시작 킷을 겸하므로 공개 곤란한 내용물은 만들지 않는다.
2. **서버 구성**: Python 단일 프로세스. MCP는 streamable HTTP, 같은 프로세스에서 대시보드도 서빙. 기기 상태는 인메모리 상태 딕셔너리 하나. 서버는 발표 내내 상시 실행, stage 전환은 새 Claude Code 세션.
3. **stage 이름**: `stageN_이름` 형식 8개 (chatbot/read/write/memory/loop/guardrail/multiagent/mhs). 최종 무인 완주는 stage6에서 실행.
4. **stage → 도구 세트**: 서버가 stage 이름 전체를 받고 내부 매핑 테이블로 도구 세트를 결정 (A안). `stage0_chatbot`은 MCP 접속 자체를 안 한다. safety limit은 상시 켜져 있다 — stage5는 서버가 바뀌는 단계가 아니라 위반을 처음 시도하는 단계.
5. **MCP 표면**: tools만 쓴다. resources/prompts는 쓰지 않는다. 발표자 대본 프롬프트는 각 stage 디렉터리의 `.claude/commands/` 슬래시 커맨드로 해결.
6. **디렉터리 구조**: `server/`(devices/, dashboard/, scenarios/) + `stages/stageN_이름/` + README(시작 킷 가이드 겸용).
7. **웹 프레임워크**: FastAPI + 공식 MCP SDK(FastMCP). 도구 세트별 FastMCP 인스턴스를 `/mcp/<stage이름>` 경로에 mount (같은 세트는 공유 mount). session manager lifespan을 FastAPI lifespan에 연결할 것.
8. **대시보드**: 빌드 스텝 없는 vanilla JS 한 장 + SSE push + CDN 차트 라이브러리. 가독성 우선(큰 글씨), 장식 없음.
9. **도메인 모델**: 명사 6개(샘플/합격 기준/작업 목록/플레이트/well/시약 잔량)만. 서버는 숫자만 만들고 해석은 Agent 몫. GAPDH·IL6은 결과표 열 이름으로만. 상세는 CONTEXT.local.md 용어집.
10. **도구 인벤토리**: read(read_nanodrop, check_devices) ⊂ write(+run_liquid_handler, reserve_quantstudio) ⊂ qpcr(+start_qpcr, get_qpcr_curves) ⊂ mhs(+discover_devices, read_device, run_device). 도구 세트는 발표 진도에 맞춰 Agent 능력을 잠그는 장치이기도 하다. 보고서 도구는 없음(Agent가 파일로 직접 씀). stage1에 check_devices를 추가해 0단계 불편 두 개를 모두 회수.
11. **qPCR 런 시간**: 40사이클 × 2초 = 80초. 사이클 속도는 서버 설정값. 이상 well은 ~25사이클부터 판별 가능하게 설계.
12. **결정론**: 난수·시드 없이 모든 숫자를 시나리오 파일에 박음 (`week_normal.json`, `week_x3.json`). 샘플 12개 중 2개 QC 탈락, 이상 well ⓐⓑ 각 1개. 리셋은 `/admin/reset` + 대시보드 버튼, MCP로는 미노출. stage 간 상태는 이어간다 (발표 전체가 연속된 한 실험).
13. **trace 파이프라인**: 이벤트 3종만 — Tool 호출(서버가 직접 기록 + 한글 설명 매핑), 사용자 프롬프트(`UserPromptSubmit` hook → `POST /trace`), 사람 승인(`PreToolUse` hook "승인 대기" → 서버 도착 시 "승인됨"). 각 이벤트에 발생 시각 필드 포함(서버 실제 시각 기록). 🤖 Agent 판단 카드는 뺀다 — 좌(터미널)=Agent의 뇌, 우(대시보드)=실험실이라는 분업 유지.
14. **stage 디렉터리 규격**: `.mcp.json`(1~7) / `.claude/settings.json`(hooks + 읽기 allow·쓰기 확인) / `.claude/commands/`(대본) / stage0에 `results_week34.csv` / stage3+에 `CLAUDE.md`(@lab_notebook.md import 한 줄) + `lab_notebook.md` / stage6+에 `.claude/agents/qc-reviewer.md`. stage 간 파일 중복은 의도적(스냅샷·diff 가능성). 정합성은 `scripts/check_stages.py`로 검증.
15. **대시보드 레이아웃** (mock: `server/dashboard/mock.html`): 세로 3단 — 기기 카드 줄(= 연결된 기기 목록, MHS에서 카드가 늘어남) / 메인 뷰(플레이트↔곡선 자동 전환, 발표 중 무조작) / trace 타임라인. 섹션 헤더는 박스 밖으로 분리(20px, 위 마진 28px); 메인 뷰 헤더는 제목만("증폭 곡선"/"플레이트"), 상세 정보(사이클 진행 등)·전환 컨트롤은 박스 안 서브 행 — 모드 전환 시 제목과 상세를 각각 갱신. 곡선은 정상 회색·이상만 빨강, 이상 표시는 Agent 판정 이후에만(스포일러 방지). trace는 카드형·크기 균일, 타이틀 줄(이벤트 종류 한글 + 오른쪽에 시:분:초 타임스탬프, tabular-nums), **역시간순(최신 위)** — 새 카드가 헤더 바로 밑 고정 위치에 나타나 스크롤 없이 최신 이벤트가 보이도록. 타임스탬프는 위→아래 단조 감소해야 함(순서 검증 겸용). 최신 항목 크게(23px/17px/14px) 강조는 폐기.
16. **stage5 guardrail**: safety limit은 시약 잔량 하나만. 거부는 실행 전·부분 실행 없음. 에러 응답에 이유+숫자(requested/available)를 담아 Agent가 계획을 수정할 수 있게 함. 거부도 trace 카드로 표시. buffer 초기값은 정상 소모량의 ~1.5배 (정상 통과, 5배 지시는 확실히 거부).
17. **stage6 multi-agent**: 병렬 worker 증설이 아니라 "종류가 다른 Agent의 등장"에 집중. 역할 3종/플레이트 1장 — orchestrator(메인 세션, 위임·보고서), worker(범용 Task subagent, 읽기+쓰기), qc-reviewer(정의 파일 1개, 읽기 전용·신선한 컨텍스트). QuantStudio 1대 유지, week_x3 폐기. 시나리오에 배치 2개(week1: stage0~5, week2: stage6 무인 완주·이상 well ⓑ 포함) + "다음 배치 투입" admin 조작. 병렬성은 슬라이드 한 줄 언급만. 기획서 6단계 서사 수정 반영 완료(2026-08-31).
18. **결과·보고서 형식**: 결과 CSV는 샘플당 1행, 3반복을 열로 펼침(IL6_cq_1..3, GAPDH_cq_1..3) — ⓑ 이상이 표에서 바로 보임. 0단계 소품과 qPCR 결과가 같은 형식. 보고서는 Agent가 마크다운 직접 작성: 결론/샘플별 결과(fold change)/합격·탈락/특이사항 4절. 완료 기준 체크리스트는 lab_notebook.md의 랩 규칙으로.
19. **희석 스펙**: 랩 규칙 "투입 농도 50 ng/µL, 샘플당 최종 50 µL" (lab_notebook.md 소유). 계산은 C1V1=C2V2 하나. worklist = 샘플당 2건(원액+buffer) × QC 통과 10샘플 = 20건. 샘플 농도는 60~200 ng/µL(희석만, 농축 없음). 부피 단위는 µL로 통일 — buffer 잔량 525 µL(정상 소모 ~350 µL의 1.5배), 5배 지시(~1,750 µL)는 거부.
20. **대시보드 결과 표시**: 메인 뷰 3모드 자동 전환 — 플레이트 → (런 중) 곡선 → (런 완료) 결과표. 보고서 패널은 v1 제외 (필요해지면 PostToolUse hook으로 추가).
21. **lab_notebook.md**: "김 연구원이 자기 보려고 쓴 메모" 톤 — 전문용어 없이 일상어(3칸 나눠 담기, 비교 기준 GAPDH, 농도 50·총량 50µL, 순도 1.8 불합격), 보고서 쓰는 법(결론→표→불합격 목록, 이유 필수), 지난주 메모(lot #2408, S07·S11 불합격). v1에서 읽기 전용. 청중이 3초에 훑는 소품.
22. **콘텐츠 난이도 원칙**: 청중·화면에 노출되는 모든 텍스트는 IT 담당자 기준. 실험 전문용어는 데모 대사에 필요한 것(Cq, GAPDH, well 등 소수)만 남기고 일상어로.
23. **Python 툴체인**: uv + 의존성 3개(fastapi, uvicorn, mcp). 포트 8000 상수 고정 (.mcp.json 8개가 참조하므로 설정화하지 않음).
24. **stage7 MHS는 구현 보류**: stage0~6 완성 후 스펙 재개. 방향성 메모 — manifest(자연어 description + procedures params max = 제조사 선언 safety limit), 원심분리기는 조작까지·HPLC는 발견만, 범용 read_device/run_device는 신규 기기 전용(기존 기기는 전용 도구 = custom 연동의 은유).
