# Fork 定制说明 / Fork Customizations

> 本仓库是 [XiaoMi/xiaomi-miloco](https://github.com/XiaoMi/xiaomi-miloco) 的个人 fork，
> 在上游基础上叠加了若干面向"单摄像头 + CPU 部署 + 自建 Lumi 中枢"场景的定制改造。
> 上游 README（README.md / README.zh.md）正文未改动，保持与 upstream 可对比/可合并。
>
> This is a personal fork of [XiaoMi/xiaomi-miloco](https://github.com/XiaoMi/xiaomi-miloco)
> with customizations for a single-camera, CPU-only, self-hosted "Lumi" setup.
> The upstream README is kept unmodified for easy comparison/merge.

---

## 改造清单

### 感知性能优化（独立于 Lumi，对通用 CPU 部署有价值）

| # | 改造 | commit | 说明 |
|---|------|--------|------|
| 1 | **deep_sort 按需启用** | f0c73d9 | 默认轻量 real 模式（仅检测），检测到人才动态升级 deep_sort（加载 ReID），连续 N 窗无人降级回 real 释放内存。`GateConfig`→实为 `IdentityConfig.dynamic_deep_sort`（总开关，默认 True）/ `deep_sort_downgrade_windows`（默认 6）。解决无 GPU 时 deep_sort 常驻 OOM 问题（峰值曾达 5.2GB）。 |
| 2 | **ReID backfill 按需化** | f0c73d9 | `get_reid_extractor(allow_fallback_load)`，dynamic 模式启动 backfill 不为补历史 emb 常驻加载 ReID ONNX。 |
| 3 | **视觉 gate 多边形区域运动降权** | 2a433a8 | `GateConfig.motion_weight_zones`：指定多边形区域内的像素变化按系数缩减后再参与 gate 判定。用于抑制窗外（树影/车流/光线）误触发，又不致盲（大面积变化如人影投玻璃仍能过阈）。cv2.fillPoly 实现，空配置 = 原行为。 |

> 1、3 两项对所有 CPU 部署用户都有普适价值，未来可考虑回馈上游 PR。

### Lumi 自建中枢相关（个人定制，与上游产品方向无关）

| 改造 | commit | 说明 |
|------|--------|------|
| Unified Device Graph 模块 | 98c8cb8 | `device_graph/`：融合 HA + MIoT 设备的统一设备图 |
| HA 集成配置 | 162b0e5 | settings 新增 Home Assistant 集成 |
| Lumi 设备图看板前端 | ae67dbb | `static/` 实时设备图 Web 看板 |
| 设备图告警去重 | a9568b5 | 每设备离线只发一条 alert（bug fix，普适） |
| 架构/路由设计文档 | 3fcf23c / 9c1faab | `docs/lumi-*.md` |

---

## 详细开发记录

完整的需求、技术调研、设计、测试、实机验证、未决项，见个人 home-reports 仓库
（不在本仓库）：`miloco/development.md`。

## 已知未决项

- **omni 视频多模态端点**：上游 omni 设计为对接 MiMo 等视频+音频多模态模型。
  本地若把 omni 指向不支持视频的端点（如纯文本/Anthropic 反代）会全部 404。
  需配置可用的视频多模态端点（MiMo / Gemini 类）。
- 上述感知优化（1/3）减少了无效触发与常驻内存，但单次处理速度仍受限于 CPU
  算力与 omni 端点可用性。

---

*维护者：amaranth · 最后更新：2026-06-27*
