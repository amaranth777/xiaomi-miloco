# Lumi（露米）统一家庭智能体架构设计

日期：2026-06-23

> 原名 miloco-hermes-ha，后定名 Lumi（露米）

## 1. 目标

构建一个私有定制版家庭智能体平台，将 Miloco、Home Assistant、Hermes Agent 和 toptoken 模型供应层整合起来。

核心目标不是“Miloco 替代 HA”，也不是“HA 替代 Miloco”，而是：

> Miloco 做感知和家庭语义，Home Assistant 做设备状态/控制总线，Hermes 做统一智能体大脑，toptoken 做模型供应。

项目代号建议：

```text
miloco-hermes-ha
```

---

## 2. 总体架构

```text
┌────────────────────────────────────────────────────┐
│                    用户交互层                       │
│ WeChat / Telegram / Web Dashboard / Voice          │
└───────────────────────┬────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────┐
│                 Hermes Agent Runtime               │
│ - 微信通知                                          │
│ - 对话理解                                          │
│ - 工具调用                                          │
│ - 任务调度 / cron                                  │
│ - 家庭策略 / 安全守卫                               │
└───────────────┬───────────────────────┬────────────┘
                │                       │
                ▼                       ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│     Miloco Hermes Bridge    │   │      Home Assistant API      │
│ POST /miloco/webhook        │   │ REST / WebSocket / Services  │
│ - 接收 Miloco 事件           │   │ - 状态读取                   │
│ - 调 Hermes                 │   │ - 服务调用                   │
│ - 写入审计日志               │   │ - 事件订阅                   │
└───────────────┬─────────────┘   └───────────────┬─────────────┘
                │                                 │
                ▼                                 ▼
┌────────────────────────────────────────────────────┐
│                Unified Device Graph                │
│ - 合并 HA entities                                 │
│ - 合并 MIoT devices                                │
│ - 合并 Miloco perception devices                   │
│ - 统一房间、设备、状态、能力、策略                  │
└───────────────┬───────────────────────┬────────────┘
                │                       │
                ▼                       ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│        Miloco Backend       │   │        Home Assistant        │
│ - 摄像头感知                 │   │ - 设备状态                   │
│ - 人物/宠物识别              │   │ - 自动化                     │
│ - 家庭事件                   │   │ - 历史记录                   │
│ - 家庭档案/任务              │   │ - 多品牌设备                 │
└───────────────┬─────────────┘   └─────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────┐
│                 Model Provider Layer               │
│ toptoken / Gemini / GPT / Claude / Local models    │
│ - perception model                                 │
│ - reasoning model                                  │
└────────────────────────────────────────────────────┘
```

---

## 3. 核心原则

### 3.1 不舍弃任何一边

HA 和 Miloco/MIoT 都是数据源：

```text
HA      = 状态、历史、自动化、服务调用
MIoT    = 小米原生能力、摄像头流、设备规格
Miloco  = 感知、身份、家庭事件、任务
Hermes  = 分析、决策、通知、执行
```

最终不是两套设备，而是一套统一设备图。

### 3.2 分析统一，控制分流

分析时：

```text
HA 状态 + MIoT 信息 + Miloco 感知事件 → 统一交给 Hermes 分析
```

控制时：

```text
普通设备控制 → 优先 HA
摄像头/MIoT 特殊能力 → MIoT
高风险动作 → 策略层拦截
```

### 3.3 模型不写死

Miloco 的模型层拆成两类：

```text
perception model = 高频感知，便宜多模态模型
reasoning model  = 低频决策，交给 Hermes 当前默认模型
```

示例：

```json
{
  "model": {
    "perception": {
      "model": "gemini-2.5-flash",
      "base_url": "https://toptoken.one/v1",
      "api_key_file": "/home/amaranth/.hermes/toptoken_key"
    },
    "reasoning": {
      "use_hermes_default": true
    }
  }
}
```

---

## 4. 模块设计

### 4.1 Unified Device Graph

新增目录：

```text
backend/miloco/src/miloco/device_graph/
```

建议结构：

```text
device_graph/
├── schema.py             # 统一设备模型
├── ha_source.py          # 从 HA 拉 entities/events
├── miot_source.py        # 从 Miloco/MIoT 拉 devices/spec/cameras
├── perception_source.py  # 从 Miloco perception 拉感知设备
├── fusion.py             # 融合逻辑
├── policy.py             # 设备安全策略
├── router.py             # /api/device_graph
└── service.py            # 对外服务层
```

### 4.2 统一设备模型

```python
class UnifiedDevice(BaseModel):
    canonical_id: str
    name: str
    room: str | None = None
    category: str | None = None

    sources: list[str] = []
    ha_entities: list[HAEntityRef] = []
    miot: MIoTDeviceRef | None = None
    perception: PerceptionRef | None = None

    states: dict[str, DeviceState] = {}
    capabilities: dict[str, DeviceCapability] = {}
    policies: dict[str, Any] = {}

    confidence: float = 1.0
```

状态不覆盖，保留来源：

```python
class DeviceState(BaseModel):
    value: Any
    source: Literal["ha", "miot", "miloco", "manual"]
    updated_at: str | None = None
    confidence: float = 1.0
```

---

## 5. 设备融合逻辑

融合优先级：

```text
1. 用户手动 alias
2. MIoT model / did 片段匹配 HA entity_id
3. friendly_name / device_name 匹配
4. room + category 匹配
5. 模糊匹配，低置信度
```

示例：

```text
HA:
sensor.petjc_cn_821633016_pro_garbage_state_p_3_7

MIoT:
model/did:
petjc_cn_821633016_pro

=> 融合为 canonical_id = litter_box
```

手动映射配置：

```json
{
  "device_graph": {
    "aliases": [
      {
        "canonical_id": "litter_box",
        "name": "猫砂盆",
        "room": "客厅",
        "miot_match": "petjc_cn_821633016_pro",
        "ha_entities": [
          "sensor.petjc_cn_821633016_pro_litter_remind_p_3_8",
          "sensor.petjc_cn_821633016_pro_garbage_state_p_3_7",
          "select.petjc_cn_821633016_pro_work_mode_p_3_1"
        ],
        "policies": {
          "forbidden_actions": ["empty"],
          "allowed_actions": ["clean", "off"],
          "requires_precheck": true
        }
      }
    ]
  }
}
```

---

## 6. Home Assistant 集成

新增配置：

```json
{
  "homeassistant": {
    "enabled": true,
    "base_url": "http://192.168.5.184:8123",
    "token_file": "/home/amaranth/.hermes/ha_token",
    "sync_interval_seconds": 30,
    "use_websocket_events": true,
    "no_proxy": true
  }
}
```

注意：本机存在 Clash 代理，Python 请求 HA 必须绕过代理：

```python
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)
os.environ["NO_PROXY"] = "*"
```

### 6.1 HA 数据源

HA source 负责：

```text
GET /api/states
GET /api/config
POST /api/services/{domain}/{service}
WebSocket subscribe_events state_changed
```

生成：

```python
HAEntityRef(
    entity_id="sensor.xxx",
    domain="sensor",
    friendly_name="猫砂盆集便仓",
    state="Full",
    attributes={...}
)
```

### 6.2 HA 控制能力

统一控制请求：

```python
class DeviceCommand(BaseModel):
    canonical_id: str
    action: str
    params: dict[str, Any] = {}
```

映射到 HA：

```text
light.turn_on
switch.turn_off
fan.turn_on
humidifier.turn_on
select.select_option
```

猫砂盆示例：

```json
{
  "canonical_id": "litter_box",
  "action": "set_mode",
  "params": {
    "mode": "Clean"
  }
}
```

转成：

```http
POST /api/services/select/select_option
{
  "entity_id": "select.petjc_cn_821633016_pro_work_mode_p_3_1",
  "option": "Clean"
}
```

如果是：

```json
{
  "mode": "Empty"
}
```

策略层直接拒绝。

---

## 7. Miloco / MIoT 集成

保留 Miloco 原能力：

```text
get_miot_device_list()
get_miot_camera_list()
get_miot_cameras_img()
get_device_spec()
control_device()
```

新增适配器：

```python
class MIoTSource:
    async def list_devices() -> list[DeviceInfo]
    async def list_cameras() -> list[CameraInfo]
    async def get_specs(did: str) -> dict
```

它不和 HA 冲突，而是给 Unified Device Graph 补充：

```text
- 小米 did
- model
- room
- camera capability
- MIoT 原生 action
- 局域网在线状态
```

---

## 8. Miloco 感知层

Miloco 的感知设备入口：

```python
PerceptionService.get_devices()
```

作为第三个 source 注入设备图：

```text
source = miloco_perception
```

感知事件：

```python
PerceptionEvent(
    source_device_id="camera_living_room",
    room="客厅",
    labels=["cat", "person"],
    summary="猫经过客厅",
    timestamp="..."
)
```

进入分析上下文时，和 HA/MIoT 状态合并：

```text
客厅摄像头 01:35 看到猫
猫砂盆集便仓 Full
猫砂盆模式 Off
余砂 3690g
=> 建议人工清理集便仓，不执行 Empty
```

---

## 9. Hermes Runtime 集成

新增：

```text
miloco-hermes-bridge/
```

或放在 Miloco 后端：

```text
backend/miloco/src/miloco/hermes_bridge/
```

服务：

```http
POST /miloco/webhook
```

兼容原 OpenClaw webhook。

请求：

```json
{
  "action": "agent",
  "payload": {
    "message": "...",
    "sessionKey": "agent:main:miloco-rule",
    "timeoutMs": 30000
  }
}
```

返回：

```json
{
  "runId": "hermes-20260623-xxxx",
  "status": "completed"
}
```

### 9.1 Hermes Bridge 职责

```text
1. 接收 Miloco agent turn
2. 拉取 Unified Device Graph
3. 构造 Hermes prompt
4. 调 Hermes CLI/API
5. 必要时发微信
6. 必要时调用 HA 控制
7. 写审计日志
```

### 9.2 Prompt 输入结构

不要把原始状态一股脑塞进去，而是生成摘要：

```text
你是家庭智能管家。

当前家庭状态：
- 猫砂盆：Off，集便仓 Full，余砂 3690g。安全策略：禁止 Empty。
- 空气净化器：关闭，PM2.5 正常。
- 加湿器：关闭，室内湿度 68%。
- 摄像头：01:35 看到猫，00:37 看到人。
- 天气：雨，22.4°C。

事件：
客厅摄像头检测到猫经过。

请判断是否需要通知或执行动作。
```

---

## 10. 策略与安全层

新增：

```text
backend/miloco/src/miloco/device_graph/policy.py
```

策略示例：

```json
{
  "policies": {
    "litter_box": {
      "forbidden_actions": ["empty"],
      "allowed_actions": ["clean", "off"],
      "requires_precheck": true,
      "requires_explicit_user_intent": ["empty"]
    }
  }
}
```

核心原则：

```text
分析可以自由
执行必须受策略约束
```

---

## 11. API 设计

### 11.1 设备图

```http
GET /api/device_graph
```

返回：

```json
{
  "devices": [
    {
      "canonical_id": "litter_box",
      "name": "猫砂盆",
      "room": "客厅",
      "sources": ["ha", "miot"],
      "states": {
        "work_mode": {
          "value": "Off",
          "source": "ha"
        },
        "garbage": {
          "value": "Full",
          "source": "ha"
        }
      },
      "capabilities": {
        "clean": {
          "via": ["ha", "miot"]
        },
        "empty": {
          "via": ["ha", "miot"],
          "forbidden": true
        }
      }
    }
  ]
}
```

### 11.2 设备摘要

```http
GET /api/device_graph/summary
```

给 Hermes 用，返回自然语言/结构化摘要：

```json
{
  "summary": "猫砂盆 Off，集便仓已满，余砂 3690g；室内 25.7°C，湿度 68%；摄像头最近看到猫。",
  "alerts": [
    {
      "level": "warning",
      "device": "litter_box",
      "message": "集便仓已满"
    }
  ]
}
```

### 11.3 统一控制

```http
POST /api/device_graph/command
```

请求：

```json
{
  "canonical_id": "litter_box",
  "action": "clean"
}
```

执行流程：

```text
策略检查
→ 选择控制通道
→ 调 HA 或 MIoT
→ 写审计日志
→ 返回结果
```

---

## 12. 数据流

### 12.1 状态同步流

```text
HA /api/states
      ↓
HA Source
      ↓
Device Graph Fusion
      ↑
MIoT Device List
      ↑
Miloco Perception Devices
```

### 12.2 感知事件流

```text
摄像头
  ↓
Miloco perception
  ↓
PerceptionEvent
  ↓
Device Graph enrich
  ↓
Hermes Bridge
  ↓
Hermes 判断
  ↓
微信通知 / HA 控制
```

### 12.3 用户对话流

```text
用户微信：家里怎么样？
  ↓
Hermes
  ↓
GET /api/device_graph/summary
  ↓
综合 HA + MIoT + Miloco
  ↓
管家风格回复
```

---

## 13. 部署设计

建议 systemd user services：

```text
miloco-backend.service
miloco-hermes-bridge.service
```

目录：

```text
~/xiaomi-miloco/
~/.openclaw/miloco/config.json
~/.hermes/ha_token
~/.hermes/toptoken_key
~/.hermes/logs/
```

安装脚本：

```text
scripts/install-miloco-hermes-ha.sh
```

执行：

```bash
python -m venv .venv
pip install -e backend/miloco
pip install -e cli
pnpm -C web install
pnpm -C web build
systemctl --user enable --now miloco-backend
systemctl --user enable --now miloco-hermes-bridge
```

---

## 14. 分阶段实施

### Phase 1：只读融合

目标：不控制设备，只合并状态。

实现：

```text
HA Source
MIoT Source
Device Graph schema
GET /api/device_graph
GET /api/device_graph/summary
```

验证：

```text
能看到猫砂盆、空气净化器、加湿器、摄像头事件统一展示
```

### Phase 2：Hermes Bridge

目标：Miloco 事件能发给 Hermes，Hermes 能微信汇报。

实现：

```text
POST /miloco/webhook
Hermes prompt builder
send_message 微信
```

验证：

```text
手动 POST 假事件 → 微信收到管家风格通知
```

### Phase 3：安全控制

目标：通过统一设备图执行安全动作。

实现：

```text
POST /api/device_graph/command
policy.py
HA service call
MIoT fallback
```

验证：

```text
开关挂灯成功
猫砂盆 Empty 被拒绝
猫砂盆 clean 需要先读状态
```

### Phase 4：感知闭环

目标：摄像头事件 + HA 状态联合判断。

示例：

```text
看到猫进厕所
+ 猫砂盆模式 Off
+ 集便仓未满
=> 不通知

看到猫砂盆集便仓 Full
+ 摄像头最近猫频繁经过
=> 微信提醒清理
```

### Phase 5：打包私有版

目标：一键安装、一键更新、一键重启。

```text
install.sh
systemd units
config template
doctor command
logs command
```

---

## 15. 最终效果

```text
Miloco 看见了什么
HA 知道设备现在怎样
MIoT 知道小米设备原生能力
Hermes 判断该不该管
微信负责优雅汇报
HA/MIoT 负责安全执行
```

最终形成：

```text
多源数据 → 统一设备图 → 统一分析 → 策略控制 → 多通道执行
```
