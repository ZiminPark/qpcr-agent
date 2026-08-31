"""Virtual Lab 서버 — 단일 FastAPI 프로세스, 포트 8000.

MCP(streamable HTTP)를 stage별 경로(/mcp/<stage이름>)에 mount하고, 같은 프로세스에서
대시보드 정적 파일 + SSE 상태 푸시 + admin 엔드포인트를 함께 서빙한다 (결정 2, 7, 23).
"""
from __future__ import annotations

import hashlib
import json
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .mcp_app import STAGE_TOOLSET, TOOLSET_APPS, TOOLSET_SERVERS
from .state import TOOL_LABELS_KO, lab_state

PORT = 8000  # 결정 23: .mcp.json 8개가 참조하므로 설정화하지 않고 상수로 고정한다.
DASHBOARD_DIR = Path(__file__).parent / "dashboard"
STAGES_DIR = Path(__file__).parent.parent / "stages"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        for srv in TOOLSET_SERVERS.values():
            await stack.enter_async_context(srv.session_manager.run())
        yield


app = FastAPI(title="qPCR Agent Virtual Lab", lifespan=lifespan)


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/")


@app.get("/favicon.ico")
def favicon() -> Response:
    # 브라우저의 자동 요청이 404 로그를 남기지 않게 빈 응답을 준다.
    return Response(status_code=204)


for stage_name, toolset in STAGE_TOOLSET.items():
    app.mount(f"/mcp/{stage_name}", TOOLSET_APPS[toolset])


@app.get("/mcp/stage7_mhs")
@app.post("/mcp/stage7_mhs")
def stage7_not_implemented() -> JSONResponse:
    return JSONResponse(
        {"error": "stage7_mhs는 구현 보류 상태입니다 (결정 24). stage0~6 완성 후 스펙 재개."},
        status_code=501,
    )


# ---- admin (MCP로는 미노출, 결정 12) ----


@app.post("/admin/reset")
async def admin_reset(request: Request) -> dict:
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    batch = (body or {}).get("batch", "week1")
    async with lab_state.lock:
        lab_state.reset(batch)
    lab_state.broadcast_state()
    lab_state.broadcast_trace_reset()
    return {"ok": True, "batch": lab_state.batch}


@app.post("/admin/next-batch")
async def admin_next_batch() -> dict:
    async with lab_state.lock:
        batch = lab_state.next_batch()
    lab_state.broadcast_state()
    lab_state.broadcast_trace_reset()
    return {"ok": True, "batch": batch}


# ---- trace (hook -> POST /trace, 결정 13) ----
#
# stage 디렉터리의 hook은 Claude Code가 stdin으로 주는 원본 hook JSON을 변형 없이 그대로
# `curl -d @-`로 넘긴다(시작 킷에 jq 등 추가 의존성을 요구하지 않기 위함). 그래서 이 엔드포인트가
# 두 가지 형태를 모두 이해한다: 이 서버 자체의 내부 형식({"type": ...})과, Claude Code hook의
# 원본 형식({"hook_event_name": "UserPromptSubmit"|"PreToolUse"|"PostToolUse", ...}).


def _bare_tool_name(tool_name: str) -> str:
    """'mcp__qpcr_lab__run_liquid_handler' -> 'run_liquid_handler'."""
    parts = (tool_name or "").split("__")
    return parts[-1] if parts else tool_name


def _hook_approval_id(body: dict) -> str:
    """PreToolUse/PostToolUse 훅 페이로드에서 같은 호출을 가리키는 결정론적 id를 만든다.

    session_id + tool_name + tool_input이 같으면(=같은 호출) 두 훅이 같은 id를 내므로,
    PostToolUse가 도착했을 때 PreToolUse가 만든 '승인 대기' 카드를 그대로 찾아 갱신할 수 있다.
    """
    session_id = body.get("session_id", "")
    tool_name = body.get("tool_name", "")
    tool_input = body.get("tool_input", {})
    raw = f"{session_id}:{tool_name}:{json.dumps(tool_input, sort_keys=True, ensure_ascii=False)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@app.post("/trace")
async def post_trace(request: Request) -> dict:
    body = await request.json()
    kind = body.get("type")

    if kind is None:
        hook_event = body.get("hook_event_name")
        if hook_event == "UserPromptSubmit":
            event = lab_state.add_trace("user_prompt", text=body.get("prompt", ""))
            return {"ok": True, "event": event}
        if hook_event == "PreToolUse":
            tool = body.get("tool_name", "")
            label = TOOL_LABELS_KO.get(_bare_tool_name(tool), tool)
            event = lab_state.add_trace(
                "human_approval",
                id=_hook_approval_id(body),
                status="pending",
                tool=tool,
                detail=f"{label} 허용 대기",
            )
            return {"ok": True, "event": event}
        if hook_event == "PostToolUse":
            tool = body.get("tool_name", "")
            label = TOOL_LABELS_KO.get(_bare_tool_name(tool), tool)
            updated = lab_state.update_trace(
                _hook_approval_id(body), status="approved", detail=f"{label} 허용됨"
            )
            return {"ok": True, "event": updated}
        if hook_event:
            # 관심 없는 다른 hook 이벤트(Stop 등)는 조용히 무시한다.
            return {"ok": True, "event": None}

    if kind == "user_prompt":
        text = body.get("text", "")
        event = lab_state.add_trace("user_prompt", text=text)
        return {"ok": True, "event": event}
    if kind == "human_approval":
        trace_id = body.get("id")
        status = body.get("status", "pending")
        tool = body.get("tool")
        detail = body.get("detail", "")
        if trace_id and status != "pending":
            extra = {"detail": detail} if detail else {}
            updated = lab_state.update_trace(trace_id, status=status, **extra)
            if updated:
                return {"ok": True, "event": updated}
        event = lab_state.add_trace(
            "human_approval", id=trace_id, status=status, tool=tool, detail=detail
        )
        return {"ok": True, "event": event}
    raise HTTPException(status_code=400, detail=f"알 수 없는 trace type: {kind!r}")


# ---- 프롬프트 모음 (결정 26) ----
#
# 정본은 각 stage의 `.claude/commands/*.md` 파일이다. 여기서는 그 파일을 읽어 대시보드
# 패널에 내려줄 뿐, 별도로 프롬프트 사본을 두지 않는다(대본 이원화 방지). 요청마다 새로
# 읽으므로 발표 중 파일을 고쳐도 바로 반영된다.


def _parse_command_md(text: str) -> tuple[str, str]:
    """frontmatter(description) + 본문으로 나눈다. frontmatter 없으면 description은 빈 문자열."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front = text[3:end]
            body = text[end + 4 :].lstrip("\n")
            description = ""
            for line in front.splitlines():
                line = line.strip()
                if line.startswith("description:"):
                    description = line[len("description:") :].strip()
                    break
            return description, body.strip()
    return "", text.strip()


@app.get("/prompts")
def get_prompts() -> dict:
    stages: list[dict] = []
    if not STAGES_DIR.exists():
        return {"stages": stages}
    seen: set[str] = set()
    for stage_dir in sorted(STAGES_DIR.iterdir()):
        if not stage_dir.is_dir():
            continue
        commands_dir = stage_dir / ".claude" / "commands"
        if not commands_dir.is_dir():
            continue
        items = []
        for md_path in sorted(commands_dir.glob("*.md")):
            # 커맨드는 stage 간 누적 스냅샷이므로, 패널에는 그 stage에서 처음 등장하는
            # 프롬프트(= 그 stage에서 실행할 대사)만 올린다. 이전 stage 것은 이미 그 그룹에 있다.
            if md_path.stem in seen:
                continue
            seen.add(md_path.stem)
            text = md_path.read_text(encoding="utf-8")
            description, body = _parse_command_md(text)
            items.append({"name": md_path.stem, "description": description, "body": body})
        if items:
            stages.append({"stage": stage_dir.name, "items": items})
    return {"stages": stages}


# ---- 상태/이벤트 (대시보드용) ----


@app.get("/state")
def get_state() -> dict:
    snapshot = lab_state.snapshot()
    snapshot["trace"] = lab_state.trace_newest_first()
    snapshot["stage_toolset"] = STAGE_TOOLSET
    return snapshot


@app.get("/events")
async def sse_events() -> StreamingResponse:
    async def stream():
        queue = lab_state.subscribe()
        try:
            initial = {"event": "state", "data": lab_state.snapshot()}
            yield f"event: {initial['event']}\ndata: {json.dumps(initial['data'], ensure_ascii=False)}\n\n"
            while True:
                message = await queue.get()
                yield f"event: {message['event']}\ndata: {json.dumps(message['data'], ensure_ascii=False)}\n\n"
        finally:
            lab_state.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


# ---- 대시보드 정적 서빙 (index.html은 다른 담당자가 만든다, 결정 7) ----

app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
