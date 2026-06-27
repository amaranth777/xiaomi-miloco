"""按需启用 deep_sort —— mark_human_presence 升降级逻辑单测。

不全量构造 PerceptionEngine（依赖模型/IO），以未绑定方法 + fake self（SimpleNamespace）
直接驱动 mark_human_presence，验证 per-device 动态模式切换：
  1. 检测到人 → 升级 deep_sort + 清缓存 + 重置无人计数
  2. 连续 N 窗无人 → 降级 real + 清缓存 + 清 ReID 引用
  3. 未达阈值不降级
  4. dynamic_deep_sort=False / mock 基础模式 → no-op（保持原行为）
"""
from __future__ import annotations

from types import SimpleNamespace

from miloco.perception.engine.api import PerceptionEngine


def _fake_engine(
    *,
    tracking_mode: str = "real",
    dynamic: bool = True,
    downgrade_windows: int = 6,
) -> SimpleNamespace:
    """mark_human_presence 仅访问以下属性。"""
    return SimpleNamespace(
        _tracking_mode=tracking_mode,
        _device_modes={},
        _no_human_windows={},
        _tracking_services={},
        _deep_sort_trackers={},
        _config=SimpleNamespace(
            identity=SimpleNamespace(
                dynamic_deep_sort=dynamic,
                deep_sort_downgrade_windows=downgrade_windows,
            ),
        ),
    )


def test_human_present_upgrades_to_deep_sort():
    eng = _fake_engine()
    # 预置一个 real 缓存实例，升级时应被清掉
    eng._tracking_services["camA"] = object()

    PerceptionEngine.mark_human_presence(eng, "camA", True)

    assert eng._device_modes["camA"] == "deep_sort"
    assert "camA" not in eng._tracking_services  # 缓存清掉，下窗重建
    assert eng._no_human_windows["camA"] == 0


def test_human_present_idempotent_when_already_deep_sort():
    eng = _fake_engine()
    eng._device_modes["camA"] = "deep_sort"
    svc = object()
    eng._tracking_services["camA"] = svc

    PerceptionEngine.mark_human_presence(eng, "camA", True)

    # 已是 deep_sort：不重复清缓存（避免无谓重建）
    assert eng._device_modes["camA"] == "deep_sort"
    assert eng._tracking_services["camA"] is svc
    assert eng._no_human_windows["camA"] == 0


def test_no_human_below_threshold_does_not_downgrade():
    eng = _fake_engine(downgrade_windows=3)
    eng._device_modes["camA"] = "deep_sort"
    eng._tracking_services["camA"] = object()

    # 连续 2 窗无人（阈值 3）
    PerceptionEngine.mark_human_presence(eng, "camA", False)
    PerceptionEngine.mark_human_presence(eng, "camA", False)

    assert eng._device_modes["camA"] == "deep_sort"  # 未降级
    assert eng._no_human_windows["camA"] == 2
    assert "camA" in eng._tracking_services  # 缓存仍在


def test_no_human_reaches_threshold_downgrades_to_real():
    eng = _fake_engine(downgrade_windows=3)
    eng._device_modes["camA"] = "deep_sort"
    eng._tracking_services["camA"] = object()
    # 模拟 ReID 共享 dict 里有该 device 的 tracker 引用
    from miloco.perception.engine.identity.tier_u import cam_id_from_device_id
    eng._deep_sort_trackers[cam_id_from_device_id("camA")] = object()

    PerceptionEngine.mark_human_presence(eng, "camA", False)
    PerceptionEngine.mark_human_presence(eng, "camA", False)
    PerceptionEngine.mark_human_presence(eng, "camA", False)  # 达阈值

    assert eng._device_modes["camA"] == "real"  # 降级
    assert "camA" not in eng._tracking_services  # 缓存清掉
    # ReID 引用清掉，释放
    assert cam_id_from_device_id("camA") not in eng._deep_sort_trackers
    assert eng._no_human_windows["camA"] == 0  # 计数重置


def test_human_resets_counter_then_no_downgrade():
    eng = _fake_engine(downgrade_windows=3)
    eng._device_modes["camA"] = "deep_sort"
    eng._tracking_services["camA"] = object()

    PerceptionEngine.mark_human_presence(eng, "camA", False)  # 1
    PerceptionEngine.mark_human_presence(eng, "camA", False)  # 2
    PerceptionEngine.mark_human_presence(eng, "camA", True)   # 人回来，计数清零
    PerceptionEngine.mark_human_presence(eng, "camA", False)  # 1（重新计）

    assert eng._device_modes["camA"] == "deep_sort"  # 没降级
    assert eng._no_human_windows["camA"] == 1


def test_dynamic_disabled_is_noop():
    eng = _fake_engine(dynamic=False)

    PerceptionEngine.mark_human_presence(eng, "camA", True)

    # 完全 no-op：不写 _device_modes / _no_human_windows
    assert eng._device_modes == {}
    assert eng._no_human_windows == {}


def test_mock_base_mode_is_noop():
    eng = _fake_engine(tracking_mode="mock")

    PerceptionEngine.mark_human_presence(eng, "camA", True)

    assert eng._device_modes == {}
    assert eng._no_human_windows == {}


def test_per_device_independent():
    """两个 device 模式互不影响。"""
    eng = _fake_engine(downgrade_windows=2)

    PerceptionEngine.mark_human_presence(eng, "camA", True)   # A 升级
    PerceptionEngine.mark_human_presence(eng, "camB", False)  # B 无人

    assert eng._device_modes["camA"] == "deep_sort"
    assert eng._device_modes.get("camB", "real") == "real"
    assert eng._no_human_windows.get("camA", 0) == 0
    assert eng._no_human_windows["camB"] == 1
