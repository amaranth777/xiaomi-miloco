"""Lumi — Home Assistant 数据源。

从 HA REST API 拉取 entities，转换为 HAEntityRef 列表。
"""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

from miloco.device_graph.schema import HAEntityRef

logger = logging.getLogger(__name__)


def _read_token(token_file: str) -> str:
    """从文件读取 HA token，支持 ~ 展开。"""
    path = Path(token_file).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"HA token 文件不存在: {path}")
    return path.read_text(encoding="utf-8").strip()


def _ha_request(base_url: str, token: str, path: str) -> Any:
    """发送 HA API 请求，强制绕过代理。"""
    # 绕过 Clash 等本地代理
    env_backup = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        if key in os.environ:
            env_backup[key] = os.environ.pop(key)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    try:
        url = f"{base_url.rstrip('/')}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            return json.loads(resp.read())
    finally:
        # 恢复环境变量
        for key, val in env_backup.items():
            os.environ[key] = val


class HASource:
    """从 Home Assistant 拉取 entity 状态。"""

    def __init__(self, base_url: str, token_file: str) -> None:
        self.base_url = base_url
        self.token_file = token_file
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token is None:
            self._token = _read_token(self.token_file)
        return self._token

    def fetch_all_entities(self) -> list[HAEntityRef]:
        """拉取所有 HA entity 状态，返回 HAEntityRef 列表。"""
        try:
            token = self._get_token()
            states = _ha_request(self.base_url, token, "/api/states")
            entities = []
            for s in states:
                entity_id = s.get("entity_id", "")
                domain = entity_id.split(".")[0] if "." in entity_id else ""
                attrs = s.get("attributes", {})
                entities.append(HAEntityRef(
                    entity_id=entity_id,
                    domain=domain,
                    friendly_name=attrs.get("friendly_name"),
                    state=s.get("state"),
                    attributes=attrs,
                    last_updated=s.get("last_updated"),
                ))
            logger.debug("HA source: 拉取 %d entities", len(entities))
            return entities
        except Exception as e:
            logger.warning("HA source 拉取失败: %s", e)
            return []

    def fetch_entity(self, entity_id: str) -> HAEntityRef | None:
        """拉取单个 entity。"""
        try:
            token = self._get_token()
            s = _ha_request(self.base_url, token, f"/api/states/{entity_id}")
            attrs = s.get("attributes", {})
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            return HAEntityRef(
                entity_id=entity_id,
                domain=domain,
                friendly_name=attrs.get("friendly_name"),
                state=s.get("state"),
                attributes=attrs,
                last_updated=s.get("last_updated"),
            )
        except Exception as e:
            logger.warning("HA source 拉取 %s 失败: %s", entity_id, e)
            return None
