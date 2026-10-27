# 智巡 SmartPatrol

[![CI](https://github.com/Lee-q-w/smartpatrol/actions/workflows/ci.yml/badge.svg)](https://github.com/Lee-q-w/smartpatrol/actions/workflows/ci.yml)
[![在线演示](https://img.shields.io/badge/%E5%9C%A8%E7%BA%BF%E6%BC%94%E7%A4%BA-GitHub%20Pages-2D5F8A)](https://lee-q-w.github.io/smartpatrol/)

> 虚实结合的园区智能巡检平台 —— 仿真、回放、真机三数据源统一协议，发现 → 处置 → 报告全流程闭环。

第九届传智杯 AI WEB 网页开发挑战赛参赛作品 · aptapt 团队 · 三江学院

## 项目介绍

传统园区巡检依赖人工：垃圾堆积发现慢、处置流转靠微信群、巡检结果无沉淀。**智巡 SmartPatrol** 把巡检搬进一个 Web 平台：

- **发现**：巡逻车自主巡查 / 摄像头上传照片，AI 识别异常（垃圾分类违规、未熄烟头、植被缺水等），标注位置、证据与把握程度
- **处置**：异常一键派单，pending → processing → resolved 工单闭环，可重开返工、全程留痕
- **报告**：一键导出 PDF 巡检报告（含异常详情与处置进度），归档或移交物业

**虚实结合**是本项目最大特点：仿真引擎、历史回放、真实设备三种数据源走同一套巡检协议、同一套界面，适配器自动切换——开发调试不用等真机，演示复盘有真实记录，真机接入即插即用。

## 技术架构

```
┌────────────────────────── 浏览器（Vue 3 SPA）──────────────────────────┐
│  门户首页 / 实时巡检 / 地图工作台 / AI 识别中心 / 值守大屏 / AI 助手   │
│                    Canvas 2.5D 园区地图 · Element Plus                  │
└──────────────┬─────────────────────────────────────────┬──────────────┘
        useDataSource（三数据源统一接入层）
               │                                           │
   ┌───────────┼─────────────┬──────────────┐              │ HTTP
   │  SimAdapter │ ReplayAdapter │ RealAdapter │             │ (识别/报告/助手)
   │  仿真引擎    │ 历史回放       │ 真机设备    │             │
   └─────────────┴───────────────┴─────────────┘      FastAPI 薄后端 :8788
   （前端内置，零依赖可离线运行）                        ├ AI 照片识别（OpenAI 兼容接口）
   统一协议 core/protocol.js                            ├ PDF 报告生成（ReportLab）
   patrol / recheck / handle / stop / …                 └ 巡检助手意图解析
                                                        WebSocket :9601 真机设备接入
```

- **前端**：Vue 3（Composition API）+ Vite + Element Plus，地图自研 Canvas 2.5D 渲染，离线优先、可静态部署
- **后端**：FastAPI 薄服务（仅 AI 识别 / PDF 报告 / 助手对话 / 模型配置四个接口），前端核心逻辑不依赖后端
- **设备接入**：WebSocket 设备协议（详见 `docs/device-protocol.md`），附 `server/sim_device.py` 模拟真机可本地联调

## 功能特性

| 模块 | 说明 |
|---|---|
| 门户首页 | 动态问候条 + 四大模块入口 + 状态概览 + 最新情报流 |
| 实时巡检 | 一键全面体检 / 分区详查 / 顶视拍照复核，命令流实时汇报 |
| 工单闭环 | 派单 → 处理中 → 完成 / 重开，统计与证据弹窗联动 |
| 地图工作台 | 拖拽自建巡检场地（分区 / 设备 / 停靠点 / 路线），保存即用 |
| AI 识别中心 | 照片上传智能判读、回填场景异常库、页面内模型配置 |
| AI 巡检助手 | 普通话下指令即执行（意图解析 + 动作白名单），后端离线自动降级本地规则 |
| 值守大屏 | 全屏指挥中心：统计卡、语义染色情报流、时钟 |
| 回放模式 | 历史巡逻记录回放，支持暂停 / 拖动进度条 / 续播 |

## 安装运行指南

### 环境要求

- Node.js ≥ 18，包管理器 pnpm（`npm i -g pnpm`）
- Python ≥ 3.10，依赖管理 uv（仅后端需要，`pip install uv` 或系统包管理器安装）
- 浏览器：Chrome / Edge / Firefox 任一现代浏览器

### 1）前端（必需）

```bash
pnpm install          # 安装依赖（vue / element-plus 等，见 package.json）
pnpm dev              # 开发模式，默认 http://localhost:5199
pnpm build            # 生产构建，产物在 dist/，任意静态服务器可部署
```

> 前端核心功能（仿真巡检 / 回放 / 工作台）不依赖后端，开箱即用。

### 2）AI 识别后端（需要 AI 功能时）

```bash
cd server
uv sync               # 按 pyproject.toml + uv.lock 安装依赖
uv run python main.py # 启动，默认 http://localhost:8788
```

启动后到页面「AI 识别中心 → 模型配置」填入 API Key 即可（见下方环境配置）。

### 3）模拟真机（可选，真机模式联调）

```bash
cd server
uv run python sim_device.py   # WebSocket 设备模拟器，默认 ws://localhost:9601
```

页面顶栏切「真机」模式，连接 `ws://localhost:9601` 即可体验完整真机链路。

## 环境配置说明

### 模型 API 配置（环境变量模板）

AI 功能通过 OpenAI 兼容接口对接大模型。配置方式二选一：

**方式 A · 页面配置（推荐）**：打开「AI 识别中心 → 模型配置」，填写 Base URL / API Key / 模型名，保存即生效（保存前自动试连校验）。

**方式 B · 配置文件**：复制 `server/config.example.json` 为 `server/config.local.json` 并填写：

```json
{
  "base_url": "https://your-provider.example.com/v1",
  "api_key": "sk-your-key-here",
  "model": "agnes-3.0-flash",
  "port": 8788
}
```

> ⚠️ `config.local.json` 含真实 Key，已被 `.gitignore` 排除，**严禁提交**。仓库内只保留 example 模板。

### 依赖清单

| 端 | 清单文件 | 主要依赖 |
|---|---|---|
| 前端 | `package.json` / `pnpm-lock.yaml` | vue 3、element-plus、vite |
| 后端 | `server/pyproject.toml` / `server/uv.lock` | fastapi、uvicorn、httpx、reportlab、pillow、websockets |

后端单测：`cd server && uv run pytest`（识别 / 报告 / 助手 / 配置四组用例）。

## 目录结构

```
smartpatrol-app/
├── src/
│   ├── core/protocol.js          # 统一巡检协议（三数据源共用命令与事件）
│   ├── adapters/                 # Sim / Replay / Real 三适配器
│   ├── composables/useDataSource.js  # 数据源统一接入层
│   ├── scenes/                   # 场景数据模型（园区 / 仓库 / 自建）
│   ├── App.vue                   # 实时巡检主视图 + 值守大屏
│   ├── HomeView.vue              # 门户首页
│   ├── MapWorkbench.vue          # 地图工作台
│   ├── AICenter.vue              # AI 识别中心
│   ├── AIAssistant.vue           # AI 巡检助手
│   ├── ParkMap.vue               # Canvas 2.5D 地图渲染
│   └── EvidenceDialog.vue        # 证据弹窗
├── server/                       # FastAPI 薄后端 + 模拟设备 + 单测
├── docs/device-protocol.md       # 真机设备接入协议文档
└── public/frames/                # 异常证据示例帧
```

## 团队信息

**aptapt 团队 · 三江学院**

- 队长：李沁文（网络空间安全专业，负责总体架构与前后端开发）
- 队员：苗楚晗、张子妍

## 许可与说明

本作品为传智杯参赛作品，仅供评审与学习交流使用。

> AI生成