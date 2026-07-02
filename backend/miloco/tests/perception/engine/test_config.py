"""GateConfig hold_duration_sec 默认值与 0 关闭语义。"""

from miloco.perception.engine.config import GateConfig


def test_gate_config_default_hold_duration_sec():
    # 本部署固定 360.0s（家庭场景需更长滞回，接受更多 omni 调用换取不误判断线）。
    # 上游默认 90.0s，见 upstream commit 历史；本仓库有意覆盖，勿随上游同步改回。
    assert GateConfig().hold_duration_sec == 360.0


def test_gate_config_hold_duration_sec_zero_allowed():
    cfg = GateConfig(hold_duration_sec=0.0)
    assert cfg.hold_duration_sec == 0.0


def test_gate_config_hold_duration_sec_custom():
    cfg = GateConfig(hold_duration_sec=120.0)
    assert cfg.hold_duration_sec == 120.0
