"""Lumi — 设备图 Service 层。

统一对外提供 get_device_graph() 和 get_summary() 接口。
"""

from __future__ import annotations

import logging

from miloco.device_graph.fusion import DeviceGraphFusion
from miloco.device_graph.ha_source import HASource
from miloco.device_graph.miot_source import MIoTSource
from miloco.device_graph.schema import (
    DeviceAlert,
    DeviceGraphResponse,
    DeviceGraphSummaryResponse,
    UnifiedDevice,
)

logger = logging.getLogger(__name__)


class DeviceGraphService:
    """设备图服务——聚合 HA + MIoT，对外提供统一接口。"""

    def __init__(self, ha_source: HASource, miot_source: MIoTSource) -> None:
        self._ha = ha_source
        self._miot = miot_source
        self._fusion = DeviceGraphFusion()

    async def get_device_graph(self) -> DeviceGraphResponse:
        """拉取并融合全量设备图。"""
        sources_active: list[str] = []

        ha_entities = self._ha.fetch_all_entities()
        if ha_entities:
            sources_active.append("ha")

        miot_devices = await self._miot.list_devices()
        if miot_devices:
            sources_active.append("miot")

        devices = self._fusion.fuse(ha_entities, miot_devices)
        return DeviceGraphResponse(
            devices=devices,
            total=len(devices),
            sources_active=sources_active,
        )

    async def get_summary(self) -> DeviceGraphSummaryResponse:
        """生成给 Hermes 用的自然语言摘要 + 告警列表。"""
        graph = await self.get_device_graph()
        devices = graph.devices

        lines: list[str] = []
        alerts: list[DeviceAlert] = []

        for dev in devices:
            # 跳过低置信度的兜底设备（太多会淹没摘要）
            if dev.confidence < 0.6 and not dev.policies:
                continue

            parts: list[str] = [f"{dev.name}"]
            state_snippets: list[str] = []

            for key, state in dev.states.items():
                val = state.value
                if val is None or val == "unavailable" or val == "unknown":
                    continue
                state_snippets.append(f"{key}={val}")

            if state_snippets:
                parts.append("、".join(state_snippets[:4]))  # 最多 4 个状态

            lines.append("；".join(parts))

            # 告警逻辑（每设备每类告警只发一条，避免多 state key 重复）
            has_offline = False
            for key, state in dev.states.items():
                val = str(state.value or "").lower()
                if val in ("full", "error", "fault"):
                    alerts.append(DeviceAlert(
                        level="warning",
                        device=dev.canonical_id,
                        message=f"{dev.name} {key}={state.value}",
                    ))
                elif val in ("offline", "unavailable") and not has_offline:
                    has_offline = True
                    alerts.append(DeviceAlert(
                        level="info",
                        device=dev.canonical_id,
                        message=f"{dev.name} 离线",
                    ))

        summary = "；".join(lines) if lines else "暂无设备数据。"

        return DeviceGraphSummaryResponse(
            summary=summary,
            alerts=alerts,
            device_count=len(devices),
            sources_active=graph.sources_active,
        )


# ─── 单例 ─────────────────────────────────────────────────────────────────────

_service: DeviceGraphService | None = None


def get_device_graph_service() -> DeviceGraphService:
    global _service
    if _service is None:
        from miloco.config import get_settings
        settings = get_settings()
        ha_cfg = settings.ha
        ha_source = HASource(
            base_url=ha_cfg.base_url,
            token_file=ha_cfg.token_file,
        )
        miot_source = MIoTSource()
        _service = DeviceGraphService(ha_source, miot_source)
    return _service
