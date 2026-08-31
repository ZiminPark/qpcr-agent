# qPCR Agent — 발표 데모

가상 실험실 데모. 챗봇에 도구를 단계별로 붙여 qPCR Agent로 키우는 라이브 시연이다.

## 정본 문서

- `CONTEXT.local.md` — 용어집. stage 이름·도메인 명사는 반드시 여기 표기를 따른다
- `docs/demo-spec-decisions.md` — 구현 스펙 결정 로그. 여기 적힌 결정과 어긋나는 구현·제안 금지, 결정을 바꾸면 이 파일부터 갱신
- `docs/demo-scenario.md` — 발표 시나리오 압축본 (stage별 대사·장면)
- 발표 기획 원본: Obsidian `writings/Thermo Fisher Korea - Agentic AI 가상 실험실 유즈케이스 - 강연 기획.md`

## 작업 규칙

- **난이도 원칙**: 화면·대사·데이터에 노출되는 텍스트는 IT 담당자 눈높이. 실험 전문용어는 Cq·GAPDH·well 급 필수 소수만. 제안이 복잡해지는 방향이면 먼저 깎아서 낼 것
- **결정론**: 서버 코드에 난수 금지. 데모에 등장하는 모든 숫자는 `server/scenarios/` 파일에 있다
- **stage 디렉터리는 스냅샷**: `stages/` 간 파일 중복은 의도적(단계 증분을 diff로 보여주기 위함). 공통화·심볼릭 링크로 "정리"하지 말 것

## 실행

- 서버: 단일 프로세스, 포트 8000 고정 (MCP `/mcp/<stage이름>` + 대시보드). uv 사용
- 발표 중 서버는 재시작하지 않는다. 상태 초기화는 `/admin/reset`

