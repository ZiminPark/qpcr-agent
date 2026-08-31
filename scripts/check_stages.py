#!/usr/bin/env python3
"""stages/ 디렉터리가 결정 14(docs/demo-spec-decisions.md) 규격을 지키는지 검증한다.

표준 라이브러리만 사용. 실행: python3 scripts/check_stages.py
실패하면 문제 목록을 찍고 exit code 1로 종료한다.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STAGES_DIR = REPO_ROOT / "stages"

# 정식 stage 이름 8개 (CONTEXT.local.md). stage7_mhs는 구현 보류(결정 24) — 존재하면 안 됨.
ALL_STAGE_NAMES = [
    "stage0_chatbot",
    "stage1_read",
    "stage2_write",
    "stage3_memory",
    "stage4_loop",
    "stage5_guardrail",
    "stage6_multiagent",
    "stage7_mhs",
]
IMPLEMENTED_STAGES = [n for n in ALL_STAGE_NAMES if n != "stage7_mhs"]
HELD_BACK_STAGES = ["stage7_mhs"]

MCP_URL_PREFIX = "http://localhost:8000/mcp/"
PORT = "8000"

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def check_stage_dirs() -> None:
    if not STAGES_DIR.is_dir():
        fail(f"stages/ 디렉터리가 없습니다: {STAGES_DIR}")
        return
    found = {p.name for p in STAGES_DIR.iterdir() if p.is_dir()}
    for name in IMPLEMENTED_STAGES:
        if name not in found:
            fail(f"stages/{name} 디렉터리가 없습니다")
    for name in HELD_BACK_STAGES:
        if name in found:
            fail(f"stages/{name} 디렉터리는 구현 보류 대상입니다 (결정 24) — 만들면 안 됩니다")
    # 정식 이름 목록 밖의 디렉터리(오타 등)도 알려준다
    unknown = found - set(ALL_STAGE_NAMES)
    for name in sorted(unknown):
        fail(f"stages/{name} 는 정식 stage 이름 목록에 없습니다 (CONTEXT.local.md 확인)")


def check_mcp_json(stage_dir: Path, stage_name: str) -> None:
    mcp_path = stage_dir / ".mcp.json"
    if stage_name == "stage0_chatbot":
        if mcp_path.exists():
            fail(f"{stage_name}/.mcp.json 이 존재합니다 — stage0은 MCP 접속을 하지 않습니다 (결정 5)")
        return

    if not mcp_path.exists():
        fail(f"{stage_name}/.mcp.json 이 없습니다 (결정 14)")
        return

    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"{stage_name}/.mcp.json JSON 파싱 실패: {e}")
        return

    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        fail(f"{stage_name}/.mcp.json 에 mcpServers 항목이 없습니다")
        return

    # 끝에 슬래시를 붙인 형태(예: /mcp/stage1_read/)도 허용한다 — 슬래시 없는 경로는 FastAPI가
    # 307로 리다이렉트하므로, 왕복을 없애기 위해 stage .mcp.json은 슬래시 붙은 URL을 쓴다.
    expected_url = f"{MCP_URL_PREFIX}{stage_name}"
    expected_url_slash = f"{expected_url}/"
    ok = False
    for server_name, server in servers.items():
        url = server.get("url", "")
        if url in (expected_url, expected_url_slash):
            ok = True
        elif f":{PORT}/mcp/" in url:
            fail(
                f"{stage_name}/.mcp.json 의 서버 '{server_name}' URL이 "
                f"'{expected_url_slash}' 이어야 하는데 '{url}' 입니다"
            )
        if server.get("type") != "http":
            fail(f"{stage_name}/.mcp.json 의 서버 '{server_name}' type은 'http'(streamable HTTP)여야 합니다")
    if not ok:
        fail(f"{stage_name}/.mcp.json 에 '{expected_url_slash}' 을 가리키는 서버가 없습니다")


def check_settings_json(stage_dir: Path, stage_name: str) -> None:
    settings_path = stage_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        fail(f"{stage_name}/.claude/settings.json 이 없습니다 (결정 14)")
        return
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"{stage_name}/.claude/settings.json JSON 파싱 실패: {e}")
        return

    hooks = data.get("hooks", {})
    if "UserPromptSubmit" not in hooks:
        fail(f"{stage_name}/.claude/settings.json 에 UserPromptSubmit hook이 없습니다 (결정 13)")

    # stage0·stage1은 쓰기 도구가 없으므로 PreToolUse hook·ask 목록 없어도 됨 (결정 10)
    has_write_tools = stage_name not in ("stage0_chatbot", "stage1_read")
    if has_write_tools:
        if "PreToolUse" not in hooks:
            fail(f"{stage_name}/.claude/settings.json 에 PreToolUse hook(승인 대기)이 없습니다 (결정 13)")
    # stage0은 MCP 접속 자체를 안 하므로 permissions 항목이 없어도 됨 (결정 4)
    if stage_name != "stage0_chatbot":
        perms = data.get("permissions", {})
        if not perms.get("allow"):
            fail(f"{stage_name}/.claude/settings.json 에 읽기 도구 allow 목록이 없습니다 (결정 2)")
        if has_write_tools and not perms.get("ask"):
            fail(f"{stage_name}/.claude/settings.json 에 쓰기 도구 ask 목록이 없습니다 (결정 2)")


def check_commands(stage_dir: Path, stage_name: str) -> None:
    cmd_dir = stage_dir / ".claude" / "commands"
    if not cmd_dir.is_dir() or not any(cmd_dir.glob("*.md")):
        fail(f"{stage_name}/.claude/commands/ 에 발표자 대본 슬래시 커맨드(.md)가 없습니다 (결정 5, 14)")


def check_stage0_csv(stage_dir: Path) -> None:
    csv_path = stage_dir / "results_week0.csv"
    if not csv_path.exists():
        fail("stage0_chatbot/results_week0.csv 가 없습니다 (결정 14)")
        return
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        fail("stage0_chatbot/results_week0.csv 가 비어 있습니다")
        return
    header = lines[0].split(",")
    expected_cols = {
        "sample",
        "IL6_cq_1", "IL6_cq_2", "IL6_cq_3",
        "GAPDH_cq_1", "GAPDH_cq_2", "GAPDH_cq_3",
    }
    if set(header) != expected_cols:
        fail(
            "stage0_chatbot/results_week0.csv 헤더가 결정 18 형식과 다릅니다: "
            f"{header}"
        )
    n_rows = len(lines) - 1
    if n_rows != 10:
        fail(
            "stage0_chatbot/results_week0.csv 샘플 행이 10개(S07·S11 불합격 제외, "
            f"lab_notebook.md '지난주 메모'와 일치)여야 하는데 {n_rows}개입니다"
        )
    sample_col = header.index("sample") if "sample" in header else None
    if sample_col is not None:
        sample_ids = {line.split(",")[sample_col] for line in lines[1:]}
        for excluded in ("S07", "S11"):
            if excluded in sample_ids:
                fail(
                    f"stage0_chatbot/results_week0.csv 에 {excluded}가 있습니다 — "
                    "lab_notebook.md '지난주 메모'는 이 샘플을 순도 미달 불합격으로 적어 두었으므로 "
                    "플레이트에 올라간 정상 측정값으로 있으면 안 됩니다 (결정 19)"
                )


def check_memory_files(stage_dir: Path, stage_name: str) -> None:
    claude_md = stage_dir / "CLAUDE.md"
    notebook = stage_dir / "lab_notebook.md"
    if not claude_md.exists():
        fail(f"{stage_name}/CLAUDE.md 가 없습니다 (결정 14)")
    else:
        content = claude_md.read_text(encoding="utf-8").strip()
        if content != "@lab_notebook.md":
            fail(
                f"{stage_name}/CLAUDE.md 는 '@lab_notebook.md' 한 줄 import여야 하는데 "
                f"'{content}' 입니다"
            )
    if not notebook.exists():
        fail(f"{stage_name}/lab_notebook.md 가 없습니다 (결정 14, 21)")


def check_qc_reviewer(stage_dir: Path) -> None:
    agent_path = stage_dir / ".claude" / "agents" / "qc-reviewer.md"
    if not agent_path.exists():
        fail("stage6_multiagent/.claude/agents/qc-reviewer.md 가 없습니다 (결정 14, 17)")
        return
    text = agent_path.read_text(encoding="utf-8")
    # 읽기 전용 도구만 허용하는지 (Write/Edit/Bash 등 쓰기 계열이 섞이면 안 됨)
    disallowed = ["Write", "Edit", "Bash", "NotebookEdit"]
    for tool in disallowed:
        if tool in text:
            fail(
                f"stage6_multiagent/.claude/agents/qc-reviewer.md 에 쓰기 계열 도구 "
                f"'{tool}' 가 언급되어 있습니다 — 읽기 전용이어야 합니다 (결정 17)"
            )


def main() -> int:
    check_stage_dirs()

    for name in IMPLEMENTED_STAGES:
        stage_dir = STAGES_DIR / name
        if not stage_dir.is_dir():
            continue  # 이미 위에서 보고함

        check_mcp_json(stage_dir, name)
        check_settings_json(stage_dir, name)
        check_commands(stage_dir, name)

        if name == "stage0_chatbot":
            check_stage0_csv(stage_dir)

        if name in ("stage3_memory", "stage4_loop", "stage5_guardrail", "stage6_multiagent"):
            check_memory_files(stage_dir, name)

        if name == "stage6_multiagent":
            check_qc_reviewer(stage_dir)

    if errors:
        print(f"FAIL — {len(errors)}건 문제 발견:\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK — stage 디렉터리 {len(IMPLEMENTED_STAGES)}개 모두 규격을 지킵니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
