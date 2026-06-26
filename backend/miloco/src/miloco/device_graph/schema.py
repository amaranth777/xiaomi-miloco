"""Lumi Unified Device Graph — 数据模型。

统一设备图的核心 schema，融合来自 HA、MIoT、Miloco 感知三个来源的设备信息。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ─── 来源引用 ─────────────────────────────────────────────────────────────────


class HAEntityRef(BaseModel):
    """HA entity 引用。"""

    entity_id: str
    domain: str
    friendly_name: str | None = None
    state: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_updated: str | None = None


class MIoTDeviceRef(BaseModel):
    """MIoT 设备引用。"""

    did: str
    model: str | None = None
    name: str | None = None
    room: str | None = None
    online: bool | None = None


class PerceptionRef(BaseModel):
    """Miloco 感知设备引用。"""

    device_id: str
    name: str | None = None
    room: str | None = None


# ─── 状态与能力 ───────────────────────────────────────────────────────────────


class DeviceState(BaseModel):
    """单个状态值，保留来源信息。"""

    value: Any
    source: Literal["ha", "miot", "miloco", "manual"]
    updated_at: str | None = None
    confidence: float = 1.0


class DeviceCapability(BaseModel):
    """设备能力（可执行的动作）。"""

    via: list[Literal["ha", "miot"]] = Field(default_factory=list)
    forbidden: bool = False
    requires_precheck: bool = False
    requires_explicit_intent: bool = False


# ─── 统一设备 ─────────────────────────────────────────────────────────────────


class UnifiedDevice(BaseModel):
    """统一设备图中的单个设备。"""

    canonical_id: str = Field(description="全局唯一 canonical 标识，如 litter_box")
    name: str
    room: str | None = None
    category: str | None = None

    sources: list[Literal["ha", "miot", "miloco"]] = Field(default_factory=list)
    ha_entities: list[HAEntityRef] = Field(default_factory=list)
    miot: MIoTDeviceRef | None = None
    perception: PerceptionRef | None = None

    states: dict[str, DeviceState] = Field(default_factory=dict)
    capabilities: dict[str, DeviceCapability] = Field(default_factory=dict)
    policies: dict[str, Any] = Field(default_factory=dict)

    confidence: float = 1.0


# ─── API 响应模型 ─────────────────────────────────────────────────────────────


class DeviceGraphResponse(BaseModel):
    """GET /api/device_graph 响应。"""

    devices: list[UnifiedDevice]
    total: int
    sources_active: list[str] = Field(default_factory=list)


class DeviceAlert(BaseModel):
    level: Literal["info", "warning", "error"]
    device: str
    message: str


class DeviceGraphSummaryResponse(BaseModel):
    """GET /api/device_graph/summary 响应（给 Hermes 用的自然语言摘要）。"""

    summary: str
    alerts: list[DeviceAlert] = Field(default_factory=list)
    device_count: int = 0
    sources_active: list[str] = Field(default_factory=list)
