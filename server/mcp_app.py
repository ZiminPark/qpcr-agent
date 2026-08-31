"""stage -> 도구 세트 매핑과, 도구 세트별 MCP(streamable HTTP) 앱을 만든다.

결정 4: 서버가 stage 이름 전체를 받고 내부 매핑 테이블로 도구 세트를 결정한다.
결정 10: read ⊂ write ⊂ qpcr ⊂ mhs. 같은 세트를 쓰는 stage는 같은 mount를 공유한다.
stage7_mhs는 구현 보류(결정 24) — 매핑에는 없고 별도로 안내한다.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from . import tools
from .state import lab_state

# stage 이름 -> 도구 세트 이름. stage0_chatbot은 MCP 접속 자체를 안 하므로 여기 없다.
STAGE_TOOLSET: dict[str, str] = {
    "stage1_read": "read",
    "stage2_write": "write",
    "stage3_memory": "write",
    "stage4_loop": "qpcr",
    "stage5_guardrail": "qpcr",
    "stage6_multiagent": "qpcr",
}

# stage7_mhs는 구현 보류(결정 24). 안내용으로만 이름을 남겨 둔다.
DEFERRED_STAGES = {"stage7_mhs"}


def _build_read_server() -> MCPServer:
    srv = MCPServer(name="qpcr-agent-read", instructions="가상 실험실 read 도구 세트")

    @srv.tool(name="read_nanodrop", description="NanoDrop으로 측정한 샘플 12개의 농도·순도를 읽는다.")
    def read_nanodrop() -> dict:
        return tools.read_nanodrop(lab_state)

    @srv.tool(name="check_devices", description="NanoDrop/액체 핸들러/QuantStudio의 현재 상태를 확인한다.")
    def check_devices() -> dict:
        return tools.check_devices(lab_state)

    return srv


def _build_write_server() -> MCPServer:
    srv = MCPServer(name="qpcr-agent-write", instructions="가상 실험실 read+write 도구 세트")

    @srv.tool(name="read_nanodrop", description="NanoDrop으로 측정한 샘플 12개의 농도·순도를 읽는다.")
    def read_nanodrop() -> dict:
        return tools.read_nanodrop(lab_state)

    @srv.tool(name="check_devices", description="NanoDrop/액체 핸들러/QuantStudio의 현재 상태를 확인한다.")
    def check_devices() -> dict:
        return tools.check_devices(lab_state)

    @srv.tool(
        name="run_liquid_handler",
        description=(
            "작업 목록을 액체 핸들러로 실행해 플레이트에 샘플을 채운다. "
            'worklist는 [{"sample_id","source":"sample|buffer","volume_ul"}] 형식. '
            "buffer 잔량이 부족하면 실행 전에 전체가 거부된다(부분 실행 없음)."
        ),
    )
    def run_liquid_handler(worklist: list[dict]) -> dict:
        return tools.run_liquid_handler(lab_state, worklist)

    @srv.tool(name="reserve_quantstudio", description="QuantStudio(qPCR 기기)를 예약한다.")
    def reserve_quantstudio() -> dict:
        return tools.reserve_quantstudio(lab_state)

    return srv


def _build_qpcr_server() -> MCPServer:
    srv = MCPServer(name="qpcr-agent-qpcr", instructions="가상 실험실 read+write+qpcr 도구 세트")

    @srv.tool(name="read_nanodrop", description="NanoDrop으로 측정한 샘플 12개의 농도·순도를 읽는다.")
    def read_nanodrop() -> dict:
        return tools.read_nanodrop(lab_state)

    @srv.tool(name="check_devices", description="NanoDrop/액체 핸들러/QuantStudio의 현재 상태를 확인한다.")
    def check_devices() -> dict:
        return tools.check_devices(lab_state)

    @srv.tool(
        name="run_liquid_handler",
        description=(
            "작업 목록을 액체 핸들러로 실행해 플레이트에 샘플을 채운다. "
            'worklist는 [{"sample_id","source":"sample|buffer","volume_ul"}] 형식. '
            "buffer 잔량이 부족하면 실행 전에 전체가 거부된다(부분 실행 없음)."
        ),
    )
    def run_liquid_handler(worklist: list[dict]) -> dict:
        return tools.run_liquid_handler(lab_state, worklist)

    @srv.tool(name="reserve_quantstudio", description="QuantStudio(qPCR 기기)를 예약한다.")
    def reserve_quantstudio() -> dict:
        return tools.reserve_quantstudio(lab_state)

    @srv.tool(name="start_qpcr", description="예약된 QuantStudio에서 qPCR 런을 시작한다 (40사이클).")
    def start_qpcr() -> dict:
        return tools.start_qpcr(lab_state)

    @srv.tool(
        name="get_qpcr_curves",
        description=(
            "진행 중이거나 끝난 qPCR 런의 well별 형광 곡선을 현재까지의 사이클만큼 읽는다. "
            "well마다 기준 유전자(GAPDH) Cq(gapdh_cq)도 함께 온다 — 목표 유전자(IL6) Cq는 "
            "형광 곡선에서 직접 계산해야 한다. 플레이트에 실제로 올라간 well만 돌아온다."
        ),
    )
    def get_qpcr_curves() -> dict:
        return tools.get_qpcr_curves(lab_state)

    return srv


TOOLSET_SERVERS: dict[str, MCPServer] = {
    "read": _build_read_server(),
    "write": _build_write_server(),
    "qpcr": _build_qpcr_server(),
}

# 도구 세트 이름 -> streamable HTTP 앱. 같은 세트를 쓰는 stage는 같은 앱 인스턴스를 여러 경로에 mount한다.
TOOLSET_APPS: dict[str, Starlette] = {
    name: srv.streamable_http_app(streamable_http_path="/")
    for name, srv in TOOLSET_SERVERS.items()
}
