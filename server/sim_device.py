# ============================================================
# 智巡模拟真机设备（sim_device.py）
# ------------------------------------------------------------
# 作用：在本地模拟一台符合「真机接入协议」的巡检设备
#       （WebSocket server），无需真实机器人即可跑通
#       连接 → 巡逻 → 拍照 → AI 识别 → 报告 全链路。
#
# 用法（server 目录下）：
#   uv run sim_device.py                          # 纯净画面，不注入异常
#   uv run sim_device.py --anomaly litter --every 3
#       # 每 3 帧有 1 帧画面里画上散落垃圾（真实多模态模型可识别）
#   uv run sim_device.py --anomaly cigarette --every 2 --port 9601
#
# 协议：JSON over WebSocket，见 docs/device-protocol.md
#   平台→设备  { t:'cmd', id, type:'hello|goto|turn|patrol|capture|return|stop', args }
#   设备→平台  { t:'hello|telemetry|frame|ack|event', ... }
#
# 移动推演：恒速直线 + 平滑转向，每 tick 推位姿/电量遥测；
# 摄像头帧：Pillow 合成 1280x720 模拟画面（含位姿/电量 OSD 水印），
#           可按配置注入异常视觉元素（垃圾/烟头）供 AI 真实识别。
# 依赖：websockets pillow（uv 管理）
# ============================================================
import argparse
import asyncio
import base64
import io
import json
import math
import random
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import websockets

# ---------- 可调参数 ----------
SPEED = 2.2          # 巡航速度 m/s
TURN_SPEED = 90      # 转向速度 度/s
TICK = 0.08          # 推演周期 s
BATTERY_DRAIN = 0.18 # 每米电量消耗 %
FRAME_W, FRAME_H = 1280, 720

FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"

# 检查点关键词 → 画面主体（无匹配画普通路面锥桶）
def subject_kind(label: str) -> str:
    label = label or ""
    for key, kind in [("垃圾桶", "bin"), ("长椅", "bench"), ("货架", "shelf"),
                      ("消防栓", "hydrant"), ("出口", "exit"), ("摄像头", "camera"),
                      ("草坪", "lawn")]:
        if key in label:
            return kind
    return "cone"


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def draw_frame(pose, battery, label, inject, anomaly, seq_no) -> Image.Image:
    """合成一帧模拟摄像头画面。inject=True 时画异常视觉元素（供 AI 真实识别）。"""
    img = Image.new("RGB", (FRAME_W, FRAME_H), "#cfe8ff")
    d = ImageDraw.Draw(img)
    horizon = 250

    # 天空 + 太阳 + 云
    d.rectangle([0, 0, FRAME_W, horizon], fill="#bfe0ff")
    d.ellipse([1050, 40, 1130, 120], fill="#ffe680")
    d.ellipse([150, 60, 260, 105], fill="#ffffff")
    d.ellipse([220, 75, 330, 115], fill="#f4faff")

    # 草地（带简单草纹理）
    d.rectangle([0, horizon, FRAME_W, FRAME_H], fill="#7fae62")
    rng = random.Random(seq_no * 7 + 3)
    for _ in range(240):
        x, y = rng.randint(0, FRAME_W), rng.randint(horizon + 8, FRAME_H - 30)
        d.line([x, y, x, y - 7], fill="#6d9c52", width=2)

    # 灰色巡逻路面（横向带）
    d.rectangle([0, 470, FRAME_W, 620], fill="#9a9a98")
    d.rectangle([0, 470, FRAME_W, 480], fill="#b8b8b5")
    for x in range(40, FRAME_W, 160):
        d.rectangle([x, 540, x + 70, 552], fill="#d9d9d6")

    # 检查点主体（画面中景）
    kind = subject_kind(label)
    cx, ground = 620, 600
    if kind == "bin":          # 垃圾桶：深绿桶身 + 盖 + 轮
        d.rectangle([cx - 70, ground - 200, cx + 70, ground], fill="#2f6b3a", outline="#1e4a26", width=4)
        d.rectangle([cx - 84, ground - 224, cx + 84, ground - 196], fill="#3d7d49", outline="#1e4a26", width=3)
        d.ellipse([cx - 66, ground - 14, cx - 40, ground + 12], fill="#333")
        d.ellipse([cx + 40, ground - 14, cx + 66, ground + 12], fill="#333")
        d.text((cx - 30, ground - 150), "可回收", font=_font(26), fill="#cfe8cf")
    elif kind == "bench":      # 长椅：棕横条 + 腿
        for i, yy in enumerate((ground - 170, ground - 130, ground - 90)):
            d.rectangle([cx - 150, yy, cx + 150, yy + 26], fill="#a0672f", outline="#6e4620", width=3)
        d.rectangle([cx - 140, ground - 90, cx - 112, ground], fill="#6e4620")
        d.rectangle([cx + 112, ground - 90, cx + 140, ground], fill="#6e4620")
    elif kind == "shelf":      # 货架：橙多层 + 纸箱
        d.rectangle([cx - 160, ground - 260, cx + 160, ground], fill="#8d6e63", outline="#5d463d", width=5)
        for yy in (ground - 180, ground - 100):
            d.rectangle([cx - 150, yy, cx + 150, yy + 8], fill="#5d463d")
            d.rectangle([cx - 120, yy - 52, cx - 40, yy], fill="#d9a05b", outline="#a8763e", width=3)
            d.rectangle([cx + 20, yy - 46, cx + 120, yy], fill="#e8c58a", outline="#a8763e", width=3)
    elif kind == "hydrant":    # 消防栓：红柱 + 顶帽
        d.rectangle([cx - 34, ground - 190, cx + 34, ground], fill="#c0392b", outline="#7d1f14", width=4)
        d.ellipse([cx - 40, ground - 216, cx + 40, ground - 176], fill="#d94a3a", outline="#7d1f14", width=3)
        d.rectangle([cx - 52, ground - 140, cx - 34, ground - 110], fill="#c0392b")
        d.rectangle([cx + 34, ground - 140, cx + 52, ground - 110], fill="#c0392b")
    elif kind == "exit":       # 安全出口：绿牌 + 门框
        d.rectangle([cx - 130, ground - 280, cx + 130, ground - 40], fill="#5b6770", outline="#39434a", width=5)
        d.rectangle([cx - 110, ground - 260, cx + 110, ground - 60], fill="#2b3338")
        d.rectangle([cx - 90, ground - 240, cx + 90, ground - 190], fill="#27ae60")
        d.text((cx - 60, ground - 236), "安全出口", font=_font(34), fill="#ffffff")
    elif kind == "camera":     # 摄像头：立杆 + 云台
        d.rectangle([cx - 10, ground - 300, cx + 10, ground], fill="#5b6770")
        d.rectangle([cx - 46, ground - 330, cx + 46, ground - 284], fill="#155eab", outline="#0c3a6b", width=4)
        d.ellipse([cx + 18, ground - 322, cx + 44, ground - 296], fill="#222")
    elif kind == "lawn":       # 草坪：圆形绿地
        d.ellipse([cx - 220, ground - 150, cx + 220, ground + 60], fill="#5da75f", outline="#3f7a42", width=5)
        for _ in range(60):
            x, y = rng.randint(cx - 190, cx + 190), rng.randint(ground - 120, ground + 30)
            d.line([x, y, x, y - 9], fill="#478a4b", width=2)
    else:                      # 默认：交通锥
        d.polygon([(cx, ground - 150), (cx - 55, ground), (cx + 55, ground)], fill="#e67e22", outline="#a3540e")
        d.rectangle([cx - 70, ground - 8, cx + 70, ground + 8], fill="#e67e22")

    # ---------- 异常视觉元素（画在主体旁的地面上，供 AI 识别） ----------
    if inject:
        ax, ay = cx + 150, ground + 12
        if anomaly == "litter":   # 垃圾散落：白色纸团 ×3 + 香蕉皮 + 塑料瓶
            for ox, oy, r in ((0, 0, 30), (64, 14, 24), (128, 2, 27)):
                pts = []
                for i in range(9):
                    ang = i / 9 * 2 * math.pi
                    rr = r * (0.72 + rng.random() * 0.5)
                    pts.append((ax + ox + math.cos(ang) * rr * 1.3, ay + oy + math.sin(ang) * rr * 0.62))
                d.polygon(pts, fill="#f2f2ee", outline="#c9c9c2")
            d.arc([ax + 190, ay - 26, ax + 268, ay + 30], 200, 60, fill="#f5d020", width=16)
            d.rectangle([ax - 130, ay - 12, ax - 66, ay + 14], fill="#a8d8ea", outline="#7db4c9", width=3)
        elif anomaly == "cigarette":   # 烟头 ×3：白色烟身 + 橙色过滤头
            for ox, oy, ang in ((-60, 0, 12), (30, 18, -20), (110, -6, 30)):
                cw, ch = 34, 14
                rect = [ax + ox - cw, ay + oy - ch, ax + ox + cw, ay + oy + ch]
                d.rectangle(rect, fill="#f5f5f0", outline="#c9c9c2")
                hx0 = rect[0] + cw * 2 - 16
                d.rectangle([hx0, rect[1], rect[2], rect[3]], fill="#e67e22")
            d.ellipse([ax - 16, ay + 44, ax + 10, ay + 66], fill="#454545")
            d.ellipse([ax - 12, ay + 48, ax + 4, ay + 60], fill="#ff8c42")

    # ---------- OSD（取景框 / 水印 / 位姿电量时间） ----------
    m = 18
    d.rectangle([m, m, FRAME_W - m, m + 40], fill=(0, 0, 0))
    d.text((m + 14, m + 8), f"SIM DEVICE · 模拟摄像头帧 #{seq_no}", font=_font(22), fill="#e8e8e8")
    d.ellipse([FRAME_W - 160, m + 10, FRAME_W - 140, m + 30], fill="#ff4d4d")
    d.text((FRAME_W - 132, m + 8), "REC", font=_font(22), fill="#ff4d4d")
    for (x0, y0, x1, y1) in [(m, 70, m + 46, 116), (FRAME_W - m - 46, 70, FRAME_W - m, 116),
                             (m, FRAME_H - 116, m + 46, FRAME_H - 70),
                             (FRAME_W - m - 46, FRAME_H - 116, FRAME_W - m, FRAME_H - 70)]:
        d.line([x0, y0, x1, y0], fill="#ffffff", width=4)
        d.line([x0, y0, x0, y1], fill="#ffffff", width=4)
        d.line([x1, y1, x1, y0], fill="#ffffff", width=4)
        d.line([x0, y1, x1, y1], fill="#ffffff", width=4)
    d.rectangle([m, FRAME_H - 64, FRAME_W - m, FRAME_H - m], fill=(0, 0, 0))
    ts = datetime.now().strftime("%H:%M:%S")
    d.text((m + 14, FRAME_H - 56),
           f"位姿 ({pose['x']:.1f}, {pose['y']:.1f}) 朝向 {pose['yaw']:.0f}°   电量 {battery:.0f}%   {ts}   {label or '巡航画面'}",
           font=_font(22), fill="#e8e8e8")
    return img


class SimDevice:
    """模拟设备状态机：一次只执行一个任务，新命令自动取消旧任务（含急停）。"""

    def __init__(self, anomaly: str, every: int, seed: int):
        self.anomaly = anomaly
        self.every = max(1, every)
        self.rng = random.Random(seed)
        self.pose = {"x": 6.0, "y": 5.0, "yaw": 0}   # 出厂位姿（与园区 dock 对齐由平台下发坐标）
        self.battery = 96.0
        self.status = "idle"
        self.frame_seq = 0
        self.task = None
        self.ws = None

    async def send(self, obj: dict):
        if self.ws is None:
            return
        try:
            await self.ws.send(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    async def telemetry_status(self):
        await self.send({"t": "telemetry", "k": "status", "status": self.status})

    # ---------- 消息入口 ----------
    async def handle(self, ws):
        # 新平台连接 = 新会话：复位到出厂位姿（模拟设备演示一致性；取消遗留任务）
        self.pose = {"x": 6.0, "y": 5.0, "yaw": 0}
        self.battery = 96.0
        self.status = "idle"
        if self.task and not self.task.done():
            self.task.cancel()
        self.ws = ws
        peer = getattr(ws, "remote_address", ("?", 0))
        print(f"[sim_device] 平台已连接：{peer[0]}:{peer[1]}（设备复位）", flush=True)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("t") != "cmd":
                    continue
                if self.task and not self.task.done():
                    self.task.cancel()
                    try:
                        await self.task
                    except (asyncio.CancelledError, Exception):
                        pass
                self.task = asyncio.create_task(self.exec_cmd(msg))
        except websockets.ConnectionClosed:
            pass
        finally:
            print("[sim_device] 平台断开连接", flush=True)
            self.ws = None
            self.status = "idle"

    async def exec_cmd(self, msg: dict):
        ctype, args = msg.get("type"), msg.get("args") or {}
        try:
            if ctype == "hello":
                await self.send({"t": "hello", "device": {
                    "id": "sim-agv-01", "name": "模拟真机 AGV（sim_device）",
                    "model": "SmartPatrol SimBot", "version": "1.0",
                    "capabilities": ["goto", "turn", "patrol", "capture", "return", "stop"],
                }})
                await self.send({"t": "telemetry", "k": "pose", "pose": dict(self.pose)})
                await self.send({"t": "telemetry", "k": "battery", "value": round(self.battery, 1)})
                await self.telemetry_status()
            elif ctype == "goto":
                await self.do_goto(float(args.get("x", 0)), float(args.get("y", 0)))
            elif ctype == "turn":
                await self.do_turn(float(args.get("yawDeg", 0)))
            elif ctype == "capture":
                await self.do_capture("手动拍照")
            elif ctype == "return":
                await self.do_goto(float(args.get("x", 0)), float(args.get("y", 0)))
                await self.send({"t": "event", "k": "notice", "text": "已返回停靠点，接入充电桩"})
            elif ctype == "patrol":
                await self.do_patrol(args)
            elif ctype == "stop":
                self.status = "idle"
                await self.telemetry_status()
            else:
                await self.send({"t": "ack", "cmdId": msg.get("id"), "ok": False,
                                 "text": f"未知命令 {ctype}"})
        except asyncio.CancelledError:
            self.status = "idle"
            await self.telemetry_status()
        except Exception as e:  # noqa: BLE001
            await self.send({"t": "ack", "cmdId": msg.get("id"), "ok": False,
                             "text": f"设备内部错误：{e}"})

    # ---------- 移动原语 ----------
    async def do_turn(self, target_yaw: float):
        delta = ((target_yaw - self.pose["yaw"] + 180) % 360) - 180
        steps = max(1, int(abs(delta) / (TURN_SPEED * TICK)))
        step = delta / steps
        for _ in range(steps):
            await asyncio.sleep(TICK)
            self.pose["yaw"] = (self.pose["yaw"] + step + 360) % 360
            await self.send({"t": "telemetry", "k": "pose", "pose": dict(self.pose)})
        self.pose["yaw"] = target_yaw % 360
        await self.send({"t": "telemetry", "k": "pose", "pose": dict(self.pose)})

    async def do_goto(self, x: float, y: float):
        sx, sy = self.pose["x"], self.pose["y"]
        dx, dy = x - sx, y - sy
        dist = math.hypot(dx, dy)
        if dist < 0.05:
            return
        yaw = math.degrees(math.atan2(dy, dx))
        await self.do_turn(yaw)
        self.status = "moving"
        await self.telemetry_status()
        moved = 0.0
        while moved < dist:
            await asyncio.sleep(TICK)
            moved = min(dist, moved + SPEED * TICK)
            k = moved / dist
            self.pose["x"] = sx + dx * k
            self.pose["y"] = sy + dy * k
            self.battery = max(15.0, self.battery - BATTERY_DRAIN * SPEED * TICK)
            await self.send({"t": "telemetry", "k": "pose", "pose": dict(self.pose)})
            await self.send({"t": "telemetry", "k": "battery", "value": round(self.battery, 1)})
        self.status = "idle"
        await self.telemetry_status()

    # ---------- 拍照 ----------
    async def do_capture(self, label: str):
        self.frame_seq += 1
        inject = (self.anomaly != "none") and (self.frame_seq % self.every == 0)
        img = draw_frame(dict(self.pose), self.battery, label, inject, self.anomaly, self.frame_seq)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        await self.send({
            "t": "frame", "reqId": f"f{self.frame_seq}",
            "image": base64.b64encode(buf.getvalue()).decode(),
            "pose": dict(self.pose), "ts": time.time(), "label": label,
        })
        print(f"[sim_device] 拍照 #{self.frame_seq}（{'注入' if inject else '正常'}画面）已发送", flush=True)

    # ---------- 巡逻任务 ----------
    async def do_patrol(self, args: dict):
        mode = args.get("mode", "point")
        checkpoints = args.get("checkpoints") or []
        print(f"[sim_device] 收到巡逻任务：mode={mode}，检查点 {len(checkpoints)} 个", flush=True)
        await self.send({"t": "ack", "cmdId": None, "ok": True,
                         "text": f"任务已接收（{mode} / {len(checkpoints)} 点）"})
        for i, cp in enumerate(checkpoints):
            await self.do_goto(float(cp.get("x", 0)), float(cp.get("y", 0)))
            label = cp.get("label") or f"检查点 {i + 1}"
            await self.send({"t": "event", "k": "arrive",
                             "text": f"🛑 停靠{label}，开始拍照检查（{i + 1}/{len(checkpoints)}）"})
            if mode == "sweep":   # 环视：原地转四朝向各拍一张
                for yaw in (0, 90, 180, 270):
                    await self.do_turn(yaw)
                    await asyncio.sleep(0.15)
                    await self.do_capture(f"{label}·环视")
            else:                 # quick / point：到点拍一张
                await asyncio.sleep(0.3)
                await self.do_capture(label)
            await asyncio.sleep(0.25)
        await self.send({"t": "event", "k": "patrol-done",
                         "text": f"真机巡逻完成（{len(checkpoints)} 个检查点）"})
        print("[sim_device] 巡逻任务完成", flush=True)


async def main():
    ap = argparse.ArgumentParser(description="智巡模拟真机设备（WebSocket）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9601)
    ap.add_argument("--anomaly", choices=["none", "litter", "cigarette"], default="none",
                    help="注入的异常画面类型（none=纯净画面）")
    ap.add_argument("--every", type=int, default=3, help="每 N 帧注入 1 帧异常画面")
    ap.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")
    args = ap.parse_args()

    device = SimDevice(args.anomaly, args.every, args.seed if args.seed is not None else random.randint(0, 9999))
    print(f"[sim_device] 模拟真机启动：ws://{args.host}:{args.port}  "
          f"异常注入={args.anomaly}（每 {args.every} 帧 1 帧）")

    async with websockets.serve(device.handle, args.host, args.port):
        await asyncio.Future()   # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[sim_device] 已退出")
