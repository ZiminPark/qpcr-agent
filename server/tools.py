"""MCP 도구의 실제 동작. FastAPI/MCP 배선과 분리해 두어 도구 세트 여러 개가 같은 로직을 공유한다.

서버는 숫자만 준다 — 합격 판정, 희석량 계산, 이상 well 판단은 전부 Agent 몫(결정 9).
유일한 예외는 buffer 잔량 safety limit(결정 16): 실행 전에 부족분을 계산해 거부한다.
"""
from __future__ import annotations

import time
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from .state import LabState, PLATE_ROWS


def read_nanodrop(state: LabState) -> dict:
    state.devices["nanodrop"]["last_reading_count"] = len(state.samples)
    result = {
        "samples": [
            {
                "sample_id": s["id"],
                "concentration_ng_ul": s["concentration_ng_ul"],
                "purity_a260_280": s["purity_a260_280"],
            }
            for s in state.samples
        ]
    }
    state.add_tool_trace("read_nanodrop", f"샘플 {len(state.samples)}건 측정값")
    state.broadcast_state()
    return result


def check_devices(state: LabState) -> dict:
    state._sync_qpcr_completion()
    cycle = state._qpcr_elapsed_cycle()
    devices = {
        "nanodrop": dict(state.devices["nanodrop"]),
        "liquid_handler": dict(state.devices["liquid_handler"]),
        "quantstudio": {
            **state.devices["quantstudio"],
            "cycle": cycle if state.qpcr_run else 0,
            "total_cycles": state.qpcr_config["total_cycles"],
        },
    }
    qs = devices["quantstudio"]["status"]
    summary = f"nanodrop={devices['nanodrop']['status']}, 액체 핸들러={devices['liquid_handler']['status']}, QuantStudio={qs}"
    state.add_tool_trace("check_devices", summary)
    state.broadcast_state()
    return {"devices": devices}


def _find_sample_wells(state: LabState, sample_id: str) -> list[str]:
    return [
        well_id
        for well_id, w in state.plate_wells_data.items()
        if w["sample_id"] == sample_id
    ]


def run_liquid_handler(state: LabState, worklist: list[dict[str, Any]]) -> dict:
    """worklist 항목: {"sample_id": "S01", "source": "sample"|"buffer", "volume_ul": 41.7}"""
    if not worklist:
        raise ToolError("작업 목록이 비어 있습니다.")

    buffer_requested = 0.0
    sample_ids: set[str] = set()
    for item in worklist:
        try:
            sample_id = str(item["sample_id"])
            source = str(item["source"])
            volume_ul = float(item["volume_ul"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ToolError(
                '작업 목록 항목 형식이 잘못됐습니다. {"sample_id","source":"sample|buffer","volume_ul"} 형식이어야 합니다.'
            ) from exc
        if source not in ("sample", "buffer"):
            raise ToolError(f"source는 'sample' 또는 'buffer'여야 합니다: {source!r}")
        if volume_ul <= 0:
            raise ToolError(f"volume_ul은 0보다 커야 합니다: {volume_ul}")
        sample_ids.add(sample_id)
        if source == "buffer":
            buffer_requested += volume_ul

    available = state.devices["liquid_handler"]["reagent_ul"]
    if buffer_requested > available:
        reason = (
            f"buffer 잔량 부족: 요청 {buffer_requested:.1f} µL > 잔량 {available:.1f} µL. "
            "작업 목록 부피를 줄이거나 buffer를 보충한 뒤 다시 시도하세요."
        )
        state.add_tool_trace(
            "run_liquid_handler",
            f"거부됨 · 요청 {buffer_requested:.1f}µL > 잔량 {available:.1f}µL",
            rejected=True,
        )
        state.broadcast_state()
        raise ToolError(reason)

    # 여기서부터는 전량 실행 (부분 실행 없음, 결정 16)
    state.devices["liquid_handler"]["reagent_ul"] = round(available - buffer_requested, 2)
    state.devices["liquid_handler"]["last_run_entries"] = len(worklist)  # 대시보드 부제용 지속 이력
    filled_wells: list[str] = []
    for sample_id in sample_ids:
        for well_id in _find_sample_wells(state, sample_id):
            state.plate[well_id]["status"] = "filled"
            filled_wells.append(well_id)

    state.last_worklist = {
        "entries": worklist,
        "executed_at": time.time(),
        "buffer_used_ul": round(buffer_requested, 2),
    }
    remaining = state.devices["liquid_handler"]["reagent_ul"]
    state.add_tool_trace(
        "run_liquid_handler",
        f"{len(worklist)}건 이송 완료 · buffer {remaining:.1f} µL 남음",
    )
    state.broadcast_state()
    return {
        "ok": True,
        "entries_executed": len(worklist),
        "wells_filled": sorted(filled_wells),
        "buffer_used_ul": round(buffer_requested, 2),
        "reagent_ul_remaining": remaining,
    }


def reserve_quantstudio(state: LabState) -> dict:
    state.devices["quantstudio"]["reserved"] = True
    state.devices["quantstudio"]["status"] = "reserved"
    state.add_tool_trace("reserve_quantstudio", "예약됨")
    state.broadcast_state()
    return {"ok": True, "status": "reserved"}


def start_qpcr(state: LabState) -> dict:
    if state.qpcr_run and state.qpcr_run.get("completed_at") is None:
        raise ToolError("이미 qPCR 런이 진행 중입니다.")
    total_cycles = state.qpcr_config["total_cycles"]
    cycle_seconds = state.qpcr_config["cycle_seconds"]
    state.qpcr_run = {
        "started_at": time.time(),
        "total_cycles": total_cycles,
        "cycle_seconds": cycle_seconds,
        "completed_at": None,
    }
    state.devices["quantstudio"]["status"] = "busy"
    state.add_tool_trace(
        "start_qpcr",
        f"시작됨 ({total_cycles}사이클 예정, 데모 압축 약 {total_cycles*cycle_seconds}초)",
    )
    state.broadcast_state()
    return {
        "ok": True,
        "total_cycles": total_cycles,
        "cycle_seconds": cycle_seconds,
        "demo_time_compressed": True,
    }


def get_qpcr_curves(state: LabState) -> dict:
    if not state.qpcr_run:
        raise ToolError("qPCR이 시작되지 않았습니다. start_qpcr을 먼저 호출하세요.")
    state._sync_qpcr_completion()
    cycle = state._qpcr_elapsed_cycle()
    total = state.qpcr_run["total_cycles"]
    state.mark_curves_seen(cycle)
    wells = []
    for well_id, w in state.plate_wells_data.items():
        # QC 탈락 샘플(결정 19)은 애초에 플레이트에 안 올렸으므로 액체 핸들러가 채우지
        # 않은 well(status=empty)은 곡선을 내주지 않는다 — 플레이트에 없는 결과를 만들지 않기 위함.
        if state.plate[well_id]["status"] == "empty":
            continue
        wells.append(
            {
                "well": well_id,
                "sample_id": w["sample_id"],
                "replicate": w["replicate"],
                "fluorescence": w["fluorescence"][:cycle],
                "gapdh_cq": w.get("gapdh_cq"),
            }
        )
    state.add_tool_trace(
        "get_qpcr_curves", f"{len(wells)} wells · 사이클 {cycle}/{total}"
    )
    state.broadcast_state()
    return {"cycle": cycle, "total_cycles": total, "wells": wells}
