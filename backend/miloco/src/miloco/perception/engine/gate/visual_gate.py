"""Gate Layer — Visual Gate (frame differencing)."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from miloco.perception.engine.config import GateConfig


@dataclass(frozen=True)
class VisualEvalResult:
    """visual gate 评估输出。

    intra_max / cross_max 分开返回供诊断:跨窗对的时间差 ≈ window_duration,
    远大于窗内邻帧;若 cross_max 持续 >> intra_max,说明 ISP 长周期漂移
    (AGC/IR/AWB)主导,而非真实运动。
    """
    changed: bool
    max_score: float
    intra_max: float
    cross_max: float
    last_checked: NDArray[np.uint8] | None


def evaluate_visual(
    frames: list[NDArray[np.uint8]],
    config: GateConfig,
    input_fps: int = 1,
    prev_frame: NDArray[np.uint8] | None = None,
) -> VisualEvalResult:
    """Compare frames using grayscale pixel differencing.

    prev_frame: 上一窗口的比较基准（即上次调用返回的 last_checked，已预处理，
    仅参与比较，不进 packet）——把跨窗口边界的变化也纳入检测，避免"变化恰好
    发生在两个窗口之间"被漏掉。

    last_checked 是本窗口末次被检帧的预处理结果，调用方存下来作为
    下个窗口的 prev_frame。基准取"末次被检帧"而非"窗口末帧"。
    frames 为空时为 None（调用方应保留旧基准）。
    """
    if not frames:
        return VisualEvalResult(False, 0.0, 0.0, 0.0, None)

    # Select frames at check_fps intervals based on actual input fps
    interval = max(1, round(input_fps / config.check_fps))
    check_indices = list(range(0, len(frames), interval))
    if len(check_indices) < 2 and len(frames) >= 2:
        check_indices.append(len(frames) - 1)

    # 每帧只预处理一次;跳过空帧(解码异常兜底,cv2.resize 对空数组会抛错)
    processed = [_preprocess(frames[i]) for i in check_indices if frames[i].size > 0]
    if not processed:
        return VisualEvalResult(False, 0.0, 0.0, 0.0, None)
    last_checked = processed[-1]

    # 运动降权区掩膜(zones 为空 → None,行为与原来逐位相等)
    weight_mask = _build_weight_mask(config.motion_weight_zones)

    # cross_max: 上窗末帧 vs 本窗首帧的单一 score(仅 prev_frame 存在时)
    # intra_max: 本窗内邻帧对的 max
    cross_max = (
        _diff_processed(prev_frame, processed[0], weight_mask=weight_mask)
        if prev_frame is not None
        else 0.0
    )
    intra_max = 0.0
    for gray_a, gray_b in zip(processed, processed[1:]):
        intra_max = max(
            intra_max, _diff_processed(gray_a, gray_b, weight_mask=weight_mask)
        )

    max_score = max(cross_max, intra_max)
    # cold-start:无跨窗基准(prev_frame is None)时静止画面 cross=0/intra≈0 会被当无变化丢掉,
    # 导致开机已存在的场景永不被感知。把首个有基准帧的窗视作变化放行以建立基准(空帧窗已在
    # 上面提前 return,不会走到这里)。prev_frame 流式来自 gate_prev_frames dict,故每 device
    # 仅首窗触发、随 dict reset 自动复位。
    changed = bool(prev_frame is None or max_score >= config.change_threshold)
    return VisualEvalResult(
        changed=changed,
        max_score=max_score,
        intra_max=intra_max,
        cross_max=cross_max,
        last_checked=last_checked,
    )


_DIFF_SIZE = (448, 448)

# 运动降权掩膜缓存:key=repr(zones)。zones 不变就复用同一张 mask,不每窗重算 fillPoly。
_WEIGHT_MASK_CACHE: dict[str, NDArray[np.float32] | None] = {}


def _build_weight_mask(
    zones: list[dict] | None,
    size: tuple[int, int] = _DIFF_SIZE,
) -> NDArray[np.float32] | None:
    """把归一化多边形降权区列表渲染成一张 448×448 的 float32 权重图。

    默认权重 1.0;降权区(归一化坐标 ×448 → 像素)按各 zone 的 ``weight`` 填入。
    多个 zone 重叠处取最小值(更激进的降权优先)。``zones`` 为空 → None
    (表示无降权,_diff_processed 走与原来逐位相等的快路径)。

    结果按 ``repr(zones)`` 缓存,zones 不变则复用(list/dict 不可 hash,故用 repr 作 key)。
    """
    if not zones:
        return None

    key = repr(zones)
    if key in _WEIGHT_MASK_CACHE:
        return _WEIGHT_MASK_CACHE[key]

    w, h = size
    mask = np.ones((h, w), dtype=np.float32)
    for zone in zones:
        polygon = zone.get("polygon")
        if not polygon:
            continue
        weight = float(zone.get("weight", 1.0))
        # 归一化[0,1] → 像素坐标(原点左上);x×w, y×h
        pts = np.array(
            [[round(x * w), round(y * h)] for x, y in polygon],
            dtype=np.int32,
        )
        # 单独渲染该 zone 再与累计 mask 取 min,保证重叠处取更激进(更小)的降权
        zone_mask = np.ones((h, w), dtype=np.float32)
        cv2.fillPoly(zone_mask, [pts], float(weight))
        mask = np.minimum(mask, zone_mask)

    _WEIGHT_MASK_CACHE[key] = mask
    return mask


def _preprocess(frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Downscale to 448x448 grayscale for differencing.

    Downscale first (cheaper than cvtColor on 4K). INTER_AREA averages
    source-pixel regions, suppressing high-frequency aliasing/noise that
    INTER_LINEAR would propagate into the diff.
    """
    small = cv2.resize(frame, _DIFF_SIZE, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small


def _diff_processed(
    gray_a: NDArray[np.uint8],
    gray_b: NDArray[np.uint8],
    pixel_threshold: int = 25,
    weight_mask: NDArray[np.float32] | None = None,
) -> float:
    """Ratio of changed pixels between two preprocessed (448x448 gray) frames.

    ``weight_mask`` 不为 None 时,降权区内的变化像素按掩膜系数打折后再统计
    (抑制窗外环境噪声)。无 mask 时结果与原 ``count_nonzero / size`` 逐位相等。
    """
    diff = cv2.absdiff(gray_a, gray_b)
    if weight_mask is None:
        # 无降权:走原 count_nonzero 整数路径,与改造前逐位相等(float32 求和会丢精度)
        return np.count_nonzero(diff > pixel_threshold) / diff.size
    changed = (diff > pixel_threshold).astype(np.float32)  # 0/1 矩阵
    changed = changed * weight_mask  # 降权区的变化像素打折
    return float(changed.sum() / changed.size)


def compute_frame_diff(
    frame_a: NDArray[np.uint8],
    frame_b: NDArray[np.uint8],
    pixel_threshold: int = 25,
    weight_mask: NDArray[np.float32] | None = None,
) -> float:
    """Compute ratio of changed pixels between two raw frames.

    Frames are resized to 448x448 before comparison to avoid
    unnecessary computation on high-resolution inputs.
    """
    if frame_a.size == 0 or frame_b.size == 0:
        return 0.0
    return _diff_processed(
        _preprocess(frame_a), _preprocess(frame_b), pixel_threshold, weight_mask
    )
