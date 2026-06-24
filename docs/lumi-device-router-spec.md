
# Lumi 设备统一层设计

## 问题背景

当前智能家居系统存在多个数据源：
- HA (Home Assistant) — 通过 xiaomi_home/xiaomi_miio 集成
- Miloco — 通过小米账号直连
- 其他集成（未来可能增加）

同一物理设备可能在多个系统中存在，导致：
1. 设备列表冗余
2. 操作入口分散
3. 状态不一致
4. 自动化触发源不明确

## 解决方案：设备统一层

### 核心概念

**统一设备对象 (Unified Device)**

每个物理设备在 Lumi 中只有一个统一对象，聚合所有数据源的能力。

```python
class UnifiedDevice:
    id: str                      # 统一ID（小米 did 或 UUID）
    name: str                    # 显示名称
    model: str                   # 设备型号
    manufacturer: str            # 制造商
    
    sources: Dict[str, DeviceSource]  # 数据源映射
    # {
    #   "ha": DeviceSource(entities=[...], available=True),
    #   "miloco": DeviceSource(device={...}, available=True)
    # }
    
    capabilities: Dict[str, Capability]  # 能力清单
    # {
    #   "power": Capability(type="switch", sources=["ha", "miloco"], preferred="ha"),
    #   "mode": Capability(type="select", sources=["miloco"], preferred="miloco"),
    #   ...
    # }
    
    preferred_source: str        # 默认数据源
    last_updated: datetime
    health_status: str           # online / offline / partial
```

### 能力发现与合并

```python
def discover_capabilities(device: UnifiedDevice) -> Dict[str, Capability]:
    """
    从各数据源提取设备能力，合并去重
    """
    capabilities = {}
    
    for source_name, source in device.sources.items():
        for cap in source.get_capabilities():
            if cap.name in capabilities:
                # 已存在，合并数据源
                capabilities[cap.name].sources.append(source_name)
                # 优先级：HA > Miloco > 其他
                if source_name == "ha":
                    capabilities[cap.name].preferred = "ha"
            else:
                capabilities[cap.name] = cap
                capabilities[cap.name].preferred = source_name
    
    return capabilities
```

### 智能路由策略

```python
class DeviceRouter:
    """
    设备操作路由器 — 选择最优数据源执行命令
    """
    
    ROUTING_RULES = {
        # 操作类型 -> 优先数据源
        "power": "ha",           # 开关操作优先 HA（有历史记录）
        "mode": "miloco",        # 模式切换优先 Miloco（响应快）
        "status": "miloco",      # 状态查询优先 Miloco（实时）
        "automation": "ha",      # 自动化触发必须走 HA
        "perception": "miloco",  # 感知类（摄像头）走 Miloco
    }
    
    def route(self, device: UnifiedDevice, action: str, params: dict) -> Result:
        # 1. 查找该操作对应的 capability
        cap = device.capabilities.get(action)
        if not cap:
            raise CapabilityNotFound(action)
        
        # 2. 确定数据源
        preferred = self.ROUTING_RULES.get(action, cap.preferred)
        
        # 3. 检查数据源可用性
        if not device.sources[preferred].available:
            # 切换到备用数据源
            for alt_source in cap.sources:
                if alt_source != preferred and device.sources[alt_source].available:
                    preferred = alt_source
                    break
            else:
                raise NoAvailableSource()
        
        # 4. 执行操作
        return self.execute(device.sources[preferred], action, params)
    
    def execute(self, source: DeviceSource, action: str, params: dict) -> Result:
        if source.type == "ha":
            return self.call_ha(source.entities[action], params)
        elif source.type == "miloco":
            return self.call_miloco(source.device["did"], action, params)
```

### 状态同步

```python
class StateSynchronizer:
    """
    多源状态同步 — 保持设备状态一致性
    """
    
    async def sync_device_state(self, device: UnifiedDevice):
        """
        从最优数据源拉取状态，同步到其他数据源
        """
        # 1. 从 Miloco 获取实时状态（最快）
        miloco_state = await self.fetch_miloco_state(device.id)
        
        # 2. 更新设备对象
        device.update_state(miloco_state)
        
        # 3. 如果 HA 有对应实体，推送状态（用于自动化触发）
        if device.sources.get("ha"):
            await self.push_to_ha(device.sources["ha"], miloco_state)
```

### API 设计

```
GET  /api/devices                    # 列出所有统一设备
GET  /api/devices/{did}              # 获取设备详情（含所有数据源）
POST /api/devices/{did}/command      # 执行设备命令（自动路由）
GET  /api/devices/{did}/state        # 获取设备状态（从最优源）
GET  /api/devices/{did}/history      # 获取历史记录（HA 提供）
POST /api/devices/sync               # 手动触发全量同步
```

### 前端集成

Miloco Web 扩展：

1. **设备列表页** — 显示统一设备，标注数据源
2. **设备详情页** — 显示能力清单，可切换数据源
3. **操作日志** — 记录每次路由决策

### 实现优先级

**P0 - 核心功能**
1. 设备发现与匹配（HA + Miloco）
2. 能力提取与合并
3. 基础路由（优先 HA）

**P1 - 增强功能**
4. 自动切换备用数据源
5. 状态同步
6. 历史记录聚合

**P2 - 高级功能**
7. 路由策略可配置
8. 数据源健康监控
9. 自动发现新设备

---

## 示例场景

### 场景 1：空气净化器控制

```
设备：小米空气净化器 MA2

数据源：
  - HA: fan.zhimi_airpurifier_ma2, sensor.pm2_5, ...
  - Miloco: did=1176980410, model=zhimi.airpurifier.ma2

能力合并：
  - power: HA(fan.turn_on/off) / Miloco(set_property) → 优先 HA
  - mode: HA(select) / Miloco(set_property) → 优先 HA
  - pm25: HA(sensor) / Miloco(get_property) → 优先 Miloco（实时）

路由示例：
  1. 用户说"开启净化器"
     → DeviceRouter.route("power", {"state": "on"})
     → 选择 HA（有历史记录）
     → HA fan.turn_on
  
  2. 用户问"PM2.5 多少"
     → DeviceRouter.route("pm25", {})
     → 选择 Miloco（实时）
     → Miloco get_property
```

### 场景 2：摄像头感知

```
设备：小米摄像机 C700

数据源：
  - HA: switch.xxx, binary_sensor.xxx, ... (无视频流)
  - Miloco: did=1176980410, 有感知引擎

能力合并：
  - power: HA / Miloco → 优先 HA
  - stream: 仅 Miloco → 只能用 Miloco
  - perception: 仅 Miloco → 只能用 Miloco

路由示例：
  1. 用户说"打开摄像头"
     → DeviceRouter.route("power", {"state": "on"})
     → 选择 HA
     → HA switch.turn_on
  
  2. 用户看实时画面
     → DeviceRouter.route("stream", {})
     → 只有 Miloco 支持
     → Miloco perception engine
```
