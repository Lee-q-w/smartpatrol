# 智巡真机接入协议 v1.0

> 智巡 SmartPatrol —— 虚实结合的通用巡检平台
> 本文档面向真机/设备端开发者：按本协议实现 WebSocket 服务，即可接入平台实时巡检。

## 1. 总览

```
┌─────────────┐  WebSocket(JSON)  ┌──────────────┐  HTTP(multipart)  ┌─────────────────┐
│  智巡平台    │◄────────────────►│  巡检设备      │                    │ AI 识别中心后端   │
│  (浏览器)    │  命令下行/遥测上行  │ (真机或模拟器) │  拍照帧 base64 ──► │ FastAPI :8788    │
│ RealAdapter │                   │ sim_device.py │◄── 结构化识别结果 ──│ 多模态大模型      │
└─────────────┘                   └──────────────┘                    └─────────────────┘
```

- 平台端适配器：`src/adapters/RealAdapter.js`（浏览器 WebSocket 客户端）
- 参考实现：`server/sim_device.py`（模拟真机，可直接运行验证全链路）

**默认地址**：`ws://127.0.0.1:9601`（可在平台「真机」模式连接面板修改）

## 2. 坐标与单位约定

| 项目 | 约定 |
|------|------|
| 坐标系 | 世界坐标，**单位：米**；原点在地图左上角，**x 向东（右）、y 向南（下）** |
| 朝向 yaw | 角度制（°），0° = 朝东，90° = 朝南（与数学 atan2 一致） |
| 电量 | 0 ~ 100，浮点 |
| 时间 | Unix 秒（浮点） |

设备位姿将**直接投影**到平台数字孪生地图（虚实同图）。`Scene JSON` 的 `dock`（停靠点）坐标会随 `patrol`/`return` 命令下发，设备无需维护地图。

## 3. 命令（平台 → 设备）

统一信封：`{ "t": "cmd", "id": "r-3", "type": "...", "args": { ... } }`

| type | args | 说明 |
|------|------|------|
| `hello` | `{}` | 平台连接后首先发送，请求设备自报信息 |
| `goto` | `{x, y}` | 移动到世界坐标点（自动转向） |
| `turn` | `{yawDeg}` | 原地转向指定朝向 |
| `patrol` | `{mode, checkpoints, dock}` | 巡逻任务，见 3.1 |
| `capture` | `{}` | 立即拍一帧并回传 |
| `return` | `{x, y}` | 返回停靠点（坐标随命令下发） |
| `stop` | `{}` | **急停**：取消当前任务、回到待命 |

### 3.1 巡逻任务 `patrol`

```json
{
  "t": "cmd", "id": "r-5", "type": "patrol",
  "args": {
    "mode": "point",
    "dock": { "x": 6.0, "y": 5.0 },
    "checkpoints": [
      { "placeId": "bin-3", "label": "3号垃圾桶", "x": 42.0, "y": 18.5, "zone": "zone-c" }
    ]
  }
}
```

- `mode`：`quick` 沿线快速巡查（检查点为路线沿途抽点）/ `point` 定点详查（逐点停靠拍 1 张）/ `sweep` 环视检查（逐点转四朝向各拍 1 张）
- `checkpoints`：平台根据场景（分区 ∩ 设备点位）**运行时推导**；label 为人类可读名称（如「3号垃圾桶」），建议在画面 OSD 与到达事件中使用
- 执行约定：逐点 `goto` → 到点拍照（`point`/`quick` 拍 1 张；`sweep` 转 0/90/180/270° 各拍 1 张）→ 全部完成后发送 `patrol-done` 事件

## 4. 设备消息（设备 → 平台）

统一为 JSON，`t` 为消息类型：

| t | 字段 | 说明 |
|---|------|------|
| `hello` | `device: {id, name, model, version, capabilities[]}` | 设备自报信息；capabilities 如 `["goto","turn","patrol","capture","return","stop"]` |
| `telemetry` | `k: "pose"`, `pose: {x,y,yaw}` | 位姿遥测（建议 ≥10Hz，移动期间持续推送） |
| `telemetry` | `k: "battery"`, `value: 95.5` | 电量遥测 |
| `telemetry` | `k: "status"`, `status: "idle"/"moving"/"working"` | 设备状态（working 用于拍照/检查中） |
| `frame` | `reqId, image(base64 JPEG), pose, ts, label` | 拍照帧。**平台收到后自动送 AI 识别**，识别确认的异常进入地图/报告/证据 |
| `ack` | `cmdId, ok: true/false, text` | 命令接收/拒绝回执（ok=false 时 text 说明原因） |
| `event` | `k: "arrive"/"patrol-done"/"notice"`, `text` | 设备侧事件，text 直接显示在平台命令流 |

### 4.1 拍照帧要求

- JPEG，建议 1280×720，原始 ≤ 300KB（base64 后 ≤ 400KB）
- 可识别类型（与 AI 提示词约定）：`cigarette` 未熄烟头 / `dry` 植被缺水 / `litter` 垃圾分类违规 / `goods` 货物堆放违规 / `blocked` 通道占用
- 建议画面含 OSD 水印（位姿/电量/时间），便于溯源；**水印内容不参与识别**

## 5. AI 识别链路（平台侧自动完成，设备无需实现）

```
设备 frame → RealAdapter → POST http://127.0.0.1:8788/api/recognize (multipart: file)
           → 多模态模型 → {found, type, label, confidence, evidence}
           → found=true：异常落图（拍照位姿前方 0.8m）、命令流播报、进入报告与证据系统
           → found=false：命令流播报「未发现异常」
```

- 识别结果为**确认态**（AI 直接确认），无「初判→复核」阶段，因此真机模式不需要无人机复核
- AI 识别中心后端未启动/模型未配置时，帧不入库并在命令流提示（可手动重拍）

## 6. 真机接入步骤（设备端开发者清单）

1. 实现 WebSocket 服务端（任意语言），默认监听 `9601` 端口
2. 处理 `hello` 命令，回 `hello` 设备信息（第 4 节）
3. 实现移动原语：`goto` / `turn` / `return` / `stop`，移动期间以 ≥10Hz 推 `pose` 遥测、状态变化时推 `status`
4. 实现 `capture`：拍一帧 JPEG → base64 → 回 `frame` 消息（附当前位姿）
5. 实现 `patrol`：按 3.1 约定逐检查点执行（可用 `goto`+`capture` 组合）
6. 打开平台 → 数据源切「真机」→ 输入设备地址 → 连接 → 下发巡逻任务

**最小可用实现** = `hello` + `telemetry(pose)` + `frame` + `patrol`（内部组合 goto/capture）。其余命令可按能力裁剪（在 `capabilities` 中声明）。

## 7. 模拟设备（server/sim_device.py）

无真机时，用模拟设备验证全链路（移动推演 + Pillow 合成摄像头画面）：

```bash
cd server
uv run sim_device.py                              # 纯净画面，不注入异常
uv run sim_device.py --anomaly litter --every 3   # 每 3 帧注入 1 帧垃圾散落画面（真实模型可识别）
uv run sim_device.py --anomaly cigarette --every 2 --port 9601
```

- `--anomaly`：`none` / `litter`（垃圾散落）/ `cigarette`（烟头）
- `--every N`：每 N 帧注入 1 帧异常画面（配合 AI 识别可演示「真机拍照 → AI 确认 → 进报告」闭环）
- 启动后平台切「真机」模式 → 连接 `ws://127.0.0.1:9601` 即可

## 8. 版本

- v1.0（2026-10-23）：初版。hello/telemetry/frame/ack/event + goto/turn/patrol/capture/return/stop

> AI生成
