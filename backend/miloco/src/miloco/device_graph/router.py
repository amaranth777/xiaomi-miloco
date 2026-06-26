"""Lumi — 设备图 API Router。

Phase 1 只读端点：
  GET /api/device_graph          — 完整设备图
  GET /api/device_graph/summary  — 给 Hermes 用的自然语言摘要
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from miloco.device_graph.schema import DeviceGraphResponse, DeviceGraphSummaryResponse
from miloco.device_graph.service import get_device_graph_service
from miloco.middleware.auth_middleware import verify_token

router = APIRouter(
    prefix="/device_graph",
    tags=["device_graph"],
    dependencies=[Depends(verify_token)],
)


@router.get("", response_model=DeviceGraphResponse)
async def get_device_graph() -> DeviceGraphResponse:
    """返回完整统一设备图（融合 HA + MIoT）。"""
    try:
        svc = get_device_graph_service()
        return await svc.get_device_graph()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/summary", response_model=DeviceGraphSummaryResponse)
async def get_device_graph_summary() -> DeviceGraphSummaryResponse:
    """返回设备图的自然语言摘要 + 告警列表，供 Hermes 直接注入 prompt。"""
    try:
        svc = get_device_graph_service()
        return await svc.get_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
