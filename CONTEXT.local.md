# CONTEXT.local.md — qPCR Agent 데모 용어집

발표 기획 원본: Obsidian `Thermo Fisher Korea - Agentic AI 가상 실험실 유즈케이스 - 강연 기획.md`

## 용어

- **Stage**: 발표의 구현 증분 하나. Claude Code 세션을 여는 디렉터리 하나와 1:1 대응하며, 기법 라벨 하나를 가르친다. 정식 이름은 `stageN_이름` 형식: `stage0_chatbot`, `stage1_read`, `stage2_write`, `stage3_memory`, `stage4_loop`, `stage5_guardrail`, `stage6_multiagent`, `stage7_mhs`. 서버·대시보드·디렉터리·대화에서 모두 이 이름을 쓴다.
- **Virtual Lab 서버**: 가상 실험 기기(NanoDrop, 액체 핸들러, QuantStudio, MHS 챕터의 원심분리기·HPLC)를 시뮬레이션하는 단일 Python 프로세스. MCP(streamable HTTP)와 브라우저 대시보드를 함께 서빙한다.
- **상태 딕셔너리 (state dictionary)**: Virtual Lab 서버가 인메모리로 들고 있는 기기 상태 단일 객체. MCP 도구와 대시보드가 같은 객체를 본다. Janelia의 shared memory state dictionary의 축소 재현.
- **도구 세트 (toolset)**: 서버가 한 stage에 노출하는 MCP 도구 목록. stage 이름 → 도구 세트 매핑 테이블은 서버가 소유한다. 여러 stage가 같은 도구 세트를 공유할 수 있다 (예: stage3_memory는 stage2_write와 동일).
- **최종 무인 완주 데모**: 별도 stage가 아니다. `stage6_multiagent`에서 실행하는 전체 런.
- **시작 킷**: 청중에게 공유하는 실습 자산. 별도 repo가 아니라 이 repo 자체가 시작 킷을 겸한다.

## 도메인 용어 (화면·대사 표기 기준)

원칙: 화면과 대사는 일상어 우선, 실험실 용어는 첫 등장에 괄호 병기 1회. 코드·데이터 필드는 영문. 서버는 숫자만 만들고 해석은 전부 Agent 몫.

- **샘플 (sample)**: 이름(S01~S12) + 농도 + 순도. 주 12개가 한 배치.
- **합격 기준 (QC)**: 순도(A260/A280) 1.8 이상이면 합격.
- **작업 목록 (worklist)**: "어디서 → 어디로 → 몇 µL" 목록. 2단계 승인 화면의 주인공. 실제 업계 용어.
- **플레이트 (plate)**: 96-well 판. 샘플 하나가 3칸을 차지(3반복, triplicate). 주 1장, stage6만 3장.
- **well**: 플레이트의 칸 하나. 결과는 well마다 곡선 1개 + Cq 1개.
- **Cq**: 형광이 기준선을 넘는 사이클 번호. 작을수록 원본이 많았다는 뜻. 0단계 복붙 해석의 소품이라 용어 그대로 쓴다.
- **이상 well**: 2종만 — ⓐ 곡선이 안 뜸(증폭 실패), ⓑ 3반복 중 1개 튐(Cq 편차).
- **시약 잔량 (reagent_ml)**: buffer 잔량 숫자 하나. stage5 사고 데모용.
- **GAPDH / IL6**: 데이터 구조가 아니라 결과표의 열 이름 두 개로만 등장 (기준 유전자 / 목표 유전자).
