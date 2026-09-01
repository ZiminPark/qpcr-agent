# qPCR Agent

가상 실험실을 붙여가며 챗봇을 "qPCR Agent"로 키우는 라이브 데모입니다. 이 repo 하나에 데모 서버 + 대시보드 + stage별 실습 디렉터리가 모두 들어 있습니다.

## 준비물

```bash
./scripts/setup.sh    # uv, Claude Code가 없으면 설치
```

## 실행

```bash
make run          # 서버 실행 (포트 8000)
```

브라우저에서 `http://localhost:8000/dashboard` 를 엽니다. 실험실 상태와 Agent의 tool 호출 기록이 실시간으로 보입니다.

원하는 stage 디렉터리에서 Claude Code 세션을 열면 그 단계의 도구와 권한이 자동 적용됩니다:

```bash
cd stages/stage1_read
claude
```

각 stage의 시연 프롬프트는 대시보드의 "프롬프트 모음" 패널에서 복사하거나, stage 디렉터리 안의 슬래시 커맨드(`.claude/commands/`)로 실행할 수 있습니다. stage마다 번호가 가장 큰 커맨드 하나만 치면 됩니다.

## stage 소개

| stage | 한 줄 소개 |
|---|---|
| `stage0_chatbot` | MCP 없이 결과 파일을 복붙해서 물어보는 순수 챗봇 |
| `stage1_read` | 실험실 상태를 읽는 도구가 생긴다 |
| `stage2_write` | 실험실을 조작하는 도구가 생기고, 실행 전 사람 승인이 붙는다 |
| `stage3_loop` | qPCR 실행을 지켜보며 이상 신호를 스스로 감지한다 |
| `stage4_memory` | 실험 노트 파일 하나로 지난 작업 맥락을 기억한다 |
| `stage5_guardrail` | 위험한 지시를 서버가 실행 전에 거부한다 |
| `stage6_multiagent` | 실행 담당과 별도로, 신선한 시각으로 결과를 검토하는 동료 Agent가 붙는다 |
