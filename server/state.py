"""Virtual Lab 서버의 인메모리 상태 딕셔너리.

여기서 만드는 숫자는 하나도 없다 — 시나리오 JSON(server/scenarios/*.json)에서
읽은 값을 그대로 담고, qPCR 런 진행률만 서버 실제 시각(time.time())으로 계산한다.
난수는 어디에도 쓰지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
PLATE_ROWS = ["A", "B", "C"]  # 3반복(triplicate)만 쓴다. 96-well 중 A~C행, 1~12열.
CQ_THRESHOLD = 0.2  # 형광이 이 값을 넘는 사이클을 Cq로 본다(임계값 교차, 결정 18 결과표용).
DISPLAY_HINT_MIN_CYCLE = 25  # 이상 형태가 데이터상 뚜렷해지는 최소 사이클(결정 11, 15).

TOOL_LABELS_KO = {
    "read_nanodrop": "NanoDrop 측정값 읽기",
    "check_devices": "기기 상태 확인",
    "run_liquid_handler": "액체 핸들러 실행",
    "reserve_quantstudio": "QuantStudio 예약",
    "start_qpcr": "qPCR 시작",
    "get_qpcr_curves": "곡선 읽기",
}


def _load_scenario(batch: str) -> dict[str, Any]:
    path = SCENARIOS_DIR / f"{batch}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class LabState:
    """기기 상태 + trace를 들고 있는 단일 객체. MCP 도구와 대시보드가 같은 객체를 본다."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue] = set()
        self._trace_seq = 0
        self.reset("week1")

    # ---- 초기화/배치 전환 (admin 전용, MCP로는 미노출) ----

    def reset(self, batch: str) -> None:
        scenario = _load_scenario(batch)
        self.batch = scenario["batch"]
        self.lot = scenario["lot"]
        self.samples: list[dict] = scenario["samples"]
        self.qpcr_config = scenario["qpcr"]
        self.plate_wells_data: dict[str, dict] = scenario["plate_wells"]

        self.qc_pass: dict[str, bool] = {
            s["id"]: s["purity_a260_280"] >= 1.8 for s in self.samples
        }

        self.devices = {
            "nanodrop": {"status": "idle", "last_reading_count": None},
            "liquid_handler": {
                "status": "idle",
                "reagent_ul": scenario["reagent_ul_initial"],
                "reagent_ul_initial": scenario["reagent_ul_initial"],
            },
            "quantstudio": {"status": "idle", "reserved": False},
        }

        self.plate = {
            well_id: {
                "sample_id": w["sample_id"],
                "replicate": w["replicate"],
                "status": "empty",
            }
            for well_id, w in self.plate_wells_data.items()
        }

        self.last_worklist: dict | None = None
        self.qpcr_run: dict | None = None
        self.trace: list[dict] = []
        self._trace_seq = 0
        # Agent가 get_qpcr_curves로 사이클 25 이후 곡선을 실제로 읽은 적이 있는가.
        # display_hint는 이 플래그가 서기 전까지는 절대 켜지지 않는다(스포일러 방지, 결정 15).
        self.curves_seen_late = False

    def next_batch(self) -> str:
        """다음 배치 투입 (결정 17) — week1 -> week2. MCP로는 미노출."""
        nxt = "week2" if self.batch == "week1" else "week1"
        self.reset(nxt)
        return self.batch

    # ---- trace ----

    def add_trace(self, kind: str, **fields: Any) -> dict:
        self._trace_seq += 1
        event = {
            "seq": self._trace_seq,
            "type": kind,
            "time": time.strftime("%H:%M:%S"),
            "ts": time.time(),
            **fields,
        }
        self.trace.append(event)
        self._broadcast({"event": "trace", "data": event})
        return event

    def update_trace(self, trace_id: str, **fields: Any) -> dict | None:
        """id가 같은 기존 카드를 갱신 (사람 승인: 대기 -> 승인됨).

        ts/time은 원래 발생 시각을 유지한다 — 갱신 시각으로 덮어쓰면 trace 타임라인의
        "위→아래 단조 감소" 순서(결정 15)가 깨지기 때문. status/detail 등만 바꾼다.
        """
        for event in self.trace:
            if event.get("id") == trace_id:
                event.update(fields)
                self._broadcast({"event": "trace", "data": event})
                return event
        return None

    def add_tool_trace(self, tool: str, result_summary: str, rejected: bool = False) -> dict:
        return self.add_trace(
            "tool_call",
            tool=tool,
            label=TOOL_LABELS_KO.get(tool, tool),
            result_summary=result_summary,
            rejected=rejected,
        )

    # ---- qPCR 진행률 (경과시간 기반, 난수 없음) ----

    def _qpcr_elapsed_cycle(self) -> int:
        if not self.qpcr_run:
            return 0
        elapsed = time.time() - self.qpcr_run["started_at"]
        total = self.qpcr_run["total_cycles"]
        cycle_seconds = self.qpcr_run["cycle_seconds"]
        cycle = int(elapsed // cycle_seconds)
        return max(0, min(total, cycle))

    def mark_curves_seen(self, cycle: int) -> None:
        """get_qpcr_curves 호출 시점의 사이클을 알려준다 — 25사이클 이상이면 플래그를 켠다.

        display_hint가 '경과 시간'이 아니라 'Agent가 실제로 곡선을 읽은 시점'을 따르게
        하기 위한 훅(결정 15). 이 값은 MCP 도구 응답에는 포함되지 않는다.
        """
        if cycle >= DISPLAY_HINT_MIN_CYCLE:
            self.curves_seen_late = True

    def _cq_for_well(self, well_id: str) -> float | None:
        """전체(40사이클) 형광 곡선에서 임계값(CQ_THRESHOLD) 교차 지점을 선형 보간해 Cq를 구한다.

        결과 표시용 순수 계산이다 — 곡선이 임계값을 못 넘으면(증폭 실패, ⓐ) None.
        """
        curve = self.plate_wells_data[well_id]["fluorescence"]
        prev = None
        for i, v in enumerate(curve):
            if v >= CQ_THRESHOLD:
                if prev is None:
                    return float(i)
                frac = (CQ_THRESHOLD - prev) / (v - prev) if v != prev else 0.0
                return round((i - 1) + frac, 2)
            prev = v
        return None

    def _sync_qpcr_completion(self) -> None:
        if not self.qpcr_run:
            return
        cycle = self._qpcr_elapsed_cycle()
        if cycle >= self.qpcr_run["total_cycles"] and not self.qpcr_run.get("completed_at"):
            self.qpcr_run["completed_at"] = time.time()
            self.devices["quantstudio"]["status"] = "idle"
            for well in self.plate.values():
                if well["status"] == "filled":
                    well["status"] = "done"

    # ---- 대시보드/관리자용 스냅샷 ----

    def snapshot(self) -> dict:
        self._sync_qpcr_completion()
        cycle = self._qpcr_elapsed_cycle()
        qpcr_view = None
        if self.qpcr_run:
            qpcr_view = {
                "cycle": cycle,
                "total_cycles": self.qpcr_run["total_cycles"],
                "running": self.qpcr_run.get("completed_at") is None,
            }
        wells = {}
        for well_id, w in self.plate_wells_data.items():
            display_hint = None
            # 대시보드 전용 힌트 — MCP 도구 응답에는 절대 포함하지 않는다 (해석은 Agent 몫).
            # Agent가 사이클 25 이후 get_qpcr_curves로 실제로 곡선을 읽은 뒤에만 노출한다
            # (스포일러 방지, 결정 15) — 단순 경과 시간이 아니라 curves_seen_late 플래그를 본다.
            if self.qpcr_run and self.curves_seen_late and w.get("anomaly"):
                display_hint = w["anomaly"]
            wells[well_id] = {
                **self.plate[well_id],
                "display_hint": display_hint,
                # 대시보드 전용(결정 12): 곡선/Cq는 화면에만 실제 숫자를 보여주기 위한 것으로,
                # MCP get_qpcr_curves 응답과는 별도다. fluorescence는 진행 중인 사이클까지만.
                "fluorescence": w["fluorescence"][:cycle] if self.qpcr_run else [],
                "cq": self._cq_for_well(well_id),
                "gapdh_cq": w.get("gapdh_cq"),
            }
        return {
            "batch": self.batch,
            "lot": self.lot,
            "devices": self.devices,
            "plate": {"wells": wells},
            "qpcr_run": qpcr_view,
            "last_worklist": self.last_worklist,
        }

    def trace_newest_first(self) -> list[dict]:
        return list(reversed(self.trace))

    # ---- SSE pub/sub ----

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, message: dict) -> None:
        for q in list(self._subscribers):
            q.put_nowait(message)

    def broadcast_state(self) -> None:
        self._broadcast({"event": "state", "data": self.snapshot()})

    def broadcast_trace_reset(self) -> None:
        """reset()/next_batch() 뒤 대시보드에 trace 타임라인을 통째로 비우라고 알린다."""
        self._broadcast({"event": "trace_reset", "data": {}})

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock


lab_state = LabState()
