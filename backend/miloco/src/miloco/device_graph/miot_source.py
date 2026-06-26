"""Lumi — MIoT 数据源。

从 Miloco 的 MiotService 拉取设备列表，转换为 MIoTDeviceRef 列表。
"""

from __future__ import annotations

import logging

from miloco.device_graph.schema import MIoTDeviceRef

logger = logging.getLogger(__name__)


class MIoTSource:
    """从 MiotService 拉取设备信息。"""

    async def list_devices(self) -> list[MIoTDeviceRef]:
        """从 MiotService 拉取设备列表。"""
        try:
            from miloco.manager import get_manager
            mgr = get_manager()
            devices = await mgr.miot_service.get_miot_device_list()
            result = []
            for d in devices:
                # DeviceInfo 字段：did, model, name, room, online 等
                result.append(MIoTDeviceRef(
                    did=getattr(d, "did", "") or "",
                    model=getattr(d, "model", None),
                    name=getattr(d, "name", None),
                    room=getattr(d, "room", None),
                    online=getattr(d, "online", None),
                ))
            logger.debug("MIoT source: 拉取 %d 设备", len(result))
            return result
        except Exception as e:
            logger.warning("MIoT source 拉取失败: %s", e)
            return []
