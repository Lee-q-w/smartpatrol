# 智巡 SmartPatrol 测试报告

> 版本：2026-10-27 · 全部测试为可重复执行的自动化脚本，数据来自实际运行结果
> 复跑环境：Windows 11 · Node 24 · Python 3.10（uv）· Edge headless

## 一、测试体系

测试分四层，自下而上覆盖"引擎逻辑 → 接口契约 → 用户路径 → 视觉布局"：

| 层 | 对象 | 工具 | 说明 |
|---|---|---|---|
| 引擎冒烟 | 仿真/回放/真机适配器逻辑 | Node 直跑（无浏览器） | 验证任务推进、事件流、状态机 |
| 后端验证 | FastAPI 四接口 | 脚本式单测（TestClient + mock 模型服务） | 识别/报告/助手/配置 |
| 浏览器端到端 | 真实页面完整用户路径 | Edge headless + CDP 协议 | 真实输入事件点击真实按钮，零 mock |
| 布局断言 | 五视图 × 两档分辨率 | CDP 几何测量 | 无溢出 / 等比缩放 / 零滚动 |

## 二、测试结果总览

| # | 测试组 | 用例数 | 结果 | 复跑命令 |
|---|---|---|---|---|
| 1 | 仿真引擎冒烟（三巡逻模式 × 两场景 × 复检闭环 × 轮次隔离） | 38 | ✅ 38/38 | `node .temp/sim-smoke.mjs` |
| 2 | 回放引擎冒烟（播放/暂停/seek/停止/重播） | 27 | ✅ 27/27 | `node .temp/replay-smoke.mjs` |
| 3 | 真机链路冒烟（连接/巡逻/拍照识别/证据帧/急停） | 14 | ✅ 14/14 | `node .temp/real-adapter-smoke.mjs` |
| 4 | 识别链路（mock 模型服务全链路） | — | ✅ 通过 | `cd server && uv run python test_recognize.py` |
| 5 | 报告导出 PDF | — | ✅ 通过 | `uv run python test_report_pdf.py` |
| 6 | 工单处置 PDF（含处置进度列） | — | ✅ 通过 | `uv run python test_handle_pdf.py` |
| 7 | AI 助手接口（意图解析/上下文/白名单） | — | ✅ 通过 | `uv run python test_agent.py` |
| 8 | 模型配置 API（保存/掩码/试连） | — | ✅ 通过 | `uv run python test_config_api.py` |
| 9 | 浏览器端到端 CDP：首页 | 18 项断言 | ✅ 18/18 | `node .temp/cdp-home-check.mjs` |
| 10 | CDP：工单闭环 | — | ✅ 通过 | `node .temp/cdp-ticket-check.mjs` |
| 11 | CDP：值守大屏 | — | ✅ 通过 | `node .temp/cdp-screen-check.mjs` |
| 12 | CDP：模型配置 | — | ✅ 通过 | `node .temp/cdp-config-check.mjs` |
| 13 | CDP：AI 助手 | — | ✅ 通过 | `node .temp/cdp-assistant-check.mjs` |
| 14 | CDP：AI 识别中心 | — | ✅ 通过 | `node .temp/cdp-ai-check.mjs` |
| 15 | CDP：PDF 导出 | — | ✅ 通过 | `node .temp/cdp-pdf-check.mjs` |
| 16 | CDP：真机模式（真实模型链路） | — | ✅ 通过 | `node .temp/cdp-real-check.mjs` |
| 17 | CDP：地图工作台（建图→保存→巡检页使用） | — | ✅ 通过 | `node .temp/cdp-workbench-check.mjs` |
| 18 | 布局断言（1600×900 / 1280×800） | 16 | ✅ 16/16 | `node .temp/cdp-layout-check.mjs` |
| 19 | 生产构建冒烟（vite preview） | 5 | ✅ 5/5 | `node .temp/cdp-prod-smoke.mjs` |
| 20 | 子路径部署冒烟（模拟 GitHub Pages） | 4 | ✅ 4/4 | `node .temp/cdp-subpath-smoke.mjs` |

> 说明：CDP 冒烟脚本依赖本地 dev 服务（`pnpm dev`，端口 5199）与后端（`uv run python main.py`，端口 8788）先启动；脚本存放于开发机 `.temp/` 目录（不入库），核心验证思路与断言已在上表注明，任何环境可按同思路重建。CI（GitHub Actions）持续运行前端构建与后端 4-8 项验证。

## 三、AI 识别质量验证（真实模型）

除功能测试外，对 AI 判读质量做了三向对照验证（同一 VLM、同一提示词体系）：

| 用例 | 画面 | 期望 | 实际 |
|---|---|---|---|
| 正例 | 注入垃圾散落异常的模拟帧 | 识别为垃圾分类违规 | ✅ found=true，把握 72%，证据描述与画面吻合 |
| 反例 1 | 无异常模拟帧 | 不误报 | ✅ found=false |
| 反例 2 | 无异常模拟帧（不同点位） | 不误报 | ✅ found=false |

开发过程中发现并修复的三个 AI 工程问题（均有回归验证）：

1. **推理型模型兼容**：先思考后作答的模型耗尽小 token 预算导致 content 为空、解析失败。修复：token 放宽至 2000 + reasoning_content 兜底解析。回归：3 次真实识别调用全部成功。
2. **误报控制**：干净画面中路侧交通锥曾被误判"通道占用"。修复：提示词增加正常设施豁免规则。回归：两帧干净画面零误报。
3. **证据净化**：模型会把画面水印文字带入证据描述。修复：服务端出口统一剥离杂讯字样。回归：证据文案干净。

## 四、质量红线

全部 CDP 端到端链路以**零浏览器控制台报错**为通过的硬性条件；布局断言要求**无横向滚动、无未预期的纵向滚动、画布等比 contain**。

> AI生成
