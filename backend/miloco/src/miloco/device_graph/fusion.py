"""Lumi — 设备融合逻辑。

把 HA entities 和 MIoT devices 融合成 UnifiedDevice 列表。
融合优先级（见架构文档 §5）：
  1. 用户手动 alias（config.json device_graph.aliases）
  2. MIoT model/did 片段匹配 HA entity_id
  3. friendly_name / device_name 匹配
  4. room + category 匹配（未实现，留空）
  5. 未匹配的 HA entity 按 domain 分组兜底
"""

from __future__ import annotations

import logging
from typing import Any

from miloco.device_graph.schema import (
    DeviceCapability,
    DeviceState,
    HAEntityRef,
    MIoTDeviceRef,
    UnifiedDevice,
)

logger = logging.getLogger(__name__)

# 已知 domain → category 映射
_DOMAIN_CATEGORY: dict[str, str] = {
    "light": "light",
    "switch": "switch",
    "sensor": "sensor",
    "binary_sensor": "sensor",
    "climate": "climate",
    "fan": "fan",
    "humidifier": "humidifier",
    "air_purifier": "air_purifier",
    "camera": "camera",
    "select": "select",
    "button": "button",
    "automation": "automation",
    "script": "script",
    "media_player": "media_player",
}

# domain → 默认 capabilities 模板
_DOMAIN_CAPABILITIES: dict[str, dict[str, DeviceCapability]] = {
    "light": {
        "turn_on": DeviceCapability(via=["ha"]),
        "turn_off": DeviceCapability(via=["ha"]),
    },
    "switch": {
        "turn_on": DeviceCapability(via=["ha"]),
        "turn_off": DeviceCapability(via=["ha"]),
    },
    "fan": {
        "turn_on": DeviceCapability(via=["ha"]),
        "turn_off": DeviceCapability(via=["ha"]),
    },
    "humidifier": {
        "turn_on": DeviceCapability(via=["ha"]),
        "turn_off": DeviceCapability(via=["ha"]),
    },
    "climate": {
        "turn_on": DeviceCapability(via=["ha"]),
        "turn_off": DeviceCapability(via=["ha"]),
        "set_temperature": DeviceCapability(via=["ha"]),
    },
    "select": {
        "select_option": DeviceCapability(via=["ha"]),
    },
    "media_player": {
        "play": DeviceCapability(via=["ha"]),
        "pause": DeviceCapability(via=["ha"]),
    },
}


def _load_aliases() -> list[dict[str, Any]]:
    """从 config.json 读取 device_graph.aliases。"""
    try:
        from miloco.config import get_settings
        from miloco.utils.paths import config_file
        import json
        path = config_file()
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("device_graph", {}).get("aliases", [])
    except Exception as e:
        logger.debug("加载 device_graph aliases 失败: %s", e)
        return []


def _apply_alias_policies(
    device: UnifiedDevice,
    alias: dict[str, Any],
) -> UnifiedDevice:
    """把 alias 里的 policies / capabilities 合并到设备。"""
    policies = alias.get("policies", {})
    if policies:
        device.policies.update(policies)

    forbidden_actions: list[str] = policies.get("forbidden_actions", [])
    allowed_actions: list[str] = policies.get("allowed_actions", [])
    requires_precheck: bool = policies.get("requires_precheck", False)

    for action in forbidden_actions:
        device.capabilities[action] = DeviceCapability(
            via=["ha", "miot"],
            forbidden=True,
        )
    for action in allowed_actions:
        if action not in device.capabilities:
            device.capabilities[action] = DeviceCapability(
                via=["ha", "miot"],
                requires_precheck=requires_precheck,
            )
        else:
            device.capabilities[action].requires_precheck = requires_precheck

    return device


def _entity_to_states(entities: list[HAEntityRef]) -> dict[str, DeviceState]:
    """把 entity 列表转为 key→DeviceState 字典。"""
    states: dict[str, DeviceState] = {}
    for e in entities:
        # 用 entity_id 最后一段作为 state key（去掉 device prefix）
        parts = e.entity_id.split(".")
        suffix = parts[-1] if len(parts) > 1 else e.entity_id
        # 去掉常见 model prefix（如 petjc_cn_821633016_pro_）
        # 取最后两个下划线段作为语义 key
        tokens = suffix.rsplit("_", 3)
        key = "_".join(tokens[-2:]) if len(tokens) >= 3 else suffix

        states[key] = DeviceState(
            value=e.state,
            source="ha",
            updated_at=e.last_updated,
        )
    return states


class DeviceGraphFusion:
    """融合 HA + MIoT 数据为统一设备图。"""

    def fuse(
        self,
        ha_entities: list[HAEntityRef],
        miot_devices: list[MIoTDeviceRef],
    ) -> list[UnifiedDevice]:
        aliases = _load_aliases()
        devices: list[UnifiedDevice] = []
        used_entity_ids: set[str] = set()

        # ── Step 1: 按 alias 配置融合 ─────────────────────────────────────
        for alias in aliases:
            canonical_id = alias.get("canonical_id", "")
            if not canonical_id:
                continue

            # 收集 alias 指定的 HA entities
            alias_entity_ids: list[str] = alias.get("ha_entities", [])
            matched_entities = [e for e in ha_entities if e.entity_id in alias_entity_ids]
            used_entity_ids.update(alias_entity_ids)

            # 匹配 MIoT 设备（did 或 model 包含 miot_match 字符串）
            miot_match: str = alias.get("miot_match", "")
            matched_miot: MIoTDeviceRef | None = None
            if miot_match:
                for d in miot_devices:
                    if miot_match in (d.did or "") or miot_match in (d.model or ""):
                        matched_miot = d
                        break

            sources = []
            if matched_entities:
                sources.append("ha")
            if matched_miot:
                sources.append("miot")

            # 主 domain（取第一个 entity 的）
            main_domain = matched_entities[0].domain if matched_entities else ""
            caps = dict(_DOMAIN_CAPABILITIES.get(main_domain, {}))

            device = UnifiedDevice(
                canonical_id=canonical_id,
                name=alias.get("name", canonical_id),
                room=alias.get("room") or (matched_miot.room if matched_miot else None),
                category=alias.get("category") or _DOMAIN_CATEGORY.get(main_domain),
                sources=sources,
                ha_entities=matched_entities,
                miot=matched_miot,
                states=_entity_to_states(matched_entities),
                capabilities=caps,
            )
            device = _apply_alias_policies(device, alias)
            devices.append(device)

        # ── Step 2: MIoT did 片段匹配未归类的 HA entities ────────────────
        remaining_ha = [e for e in ha_entities if e.entity_id not in used_entity_ids]
        for miot_dev in miot_devices:
            model_fragment = (miot_dev.model or "").split(".")[-1] if miot_dev.model else ""
            did_fragment = miot_dev.did or ""
            matched = [
                e for e in remaining_ha
                if (model_fragment and model_fragment in e.entity_id)
                or (did_fragment and did_fragment in e.entity_id)
            ]
            if not matched:
                continue
            for e in matched:
                used_entity_ids.add(e.entity_id)

            canonical_id = f"miot_{miot_dev.did or miot_dev.model or 'unknown'}"
            main_domain = matched[0].domain if matched else ""
            device = UnifiedDevice(
                canonical_id=canonical_id,
                name=miot_dev.name or canonical_id,
                room=miot_dev.room,
                category=_DOMAIN_CATEGORY.get(main_domain),
                sources=["ha", "miot"],
                ha_entities=matched,
                miot=miot_dev,
                states=_entity_to_states(matched),
                capabilities=dict(_DOMAIN_CAPABILITIES.get(main_domain, {})),
                confidence=0.8,
            )
            devices.append(device)

        # ── Step 3: 剩余 HA entities 按 entity_id 前缀分组 ───────────────
        still_remaining = [e for e in ha_entities if e.entity_id not in used_entity_ids]
        # 按 domain + model_prefix 分组（entity_id 去掉 domain 后取第一个"段"）
        groups: dict[str, list[HAEntityRef]] = {}
        for e in still_remaining:
            parts = e.entity_id.split(".")
            if len(parts) < 2:
                key = e.entity_id
            else:
                suffix = parts[1]
                # 取前缀：model_id 通常是 brand_type_did 格式，前两段作为 group key
                tokens = suffix.split("_")
                key = "_".join(tokens[:3]) if len(tokens) >= 3 else suffix
            groups.setdefault(key, []).append(e)

        for group_key, group_entities in groups.items():
            main_domain = group_entities[0].domain if group_entities else ""
            name = (
                group_entities[0].attributes.get("friendly_name")
                or group_key
            )
            device = UnifiedDevice(
                canonical_id=f"ha_{group_key}",
                name=name,
                category=_DOMAIN_CATEGORY.get(main_domain),
                sources=["ha"],
                ha_entities=group_entities,
                states=_entity_to_states(group_entities),
                capabilities=dict(_DOMAIN_CAPABILITIES.get(main_domain, {})),
                confidence=0.5,
            )
            devices.append(device)

        logger.info(
            "设备融合完成: %d 设备（alias=%d, miot_match=%d, fallback=%d）",
            len(devices),
            len(aliases),
            len([d for d in devices if "miot" in d.sources and d.canonical_id.startswith("miot_")]),
            len([d for d in devices if d.confidence == 0.5]),
        )
        return devices
