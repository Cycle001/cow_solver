"""
自动求解服务 — 封装自动求解的全生命周期管理
"""

import io
import base64
import time
from typing import Any, Dict, Optional

from ..engine.state import AutoSolverState
from ..engine.worker import AutoSolverWorker
from .._select_region import _select_region_on_screen
from exceptions import DependencyException

import threading


# 自动求解进行中的状态集合
_ACTIVE_STATUSES = ("running", "capturing", "solving", "placing",
                    "waiting_load", "waiting_transition")

# 可停止的状态集合
_STOPPABLE_STATUSES = _ACTIVE_STATUSES + ("paused",)


class AutoService:
    """自动求解服务"""

    def __init__(self, state: AutoSolverState) -> None:
        self._state = state

    def check_deps(self) -> None:
        """检查运行自动求解所需的依赖"""
        missing = []
        try:
            import mss  # noqa: F401
        except ImportError:
            missing.append("mss")
        if missing:
            raise DependencyException(
                f"缺少依赖库: {', '.join(missing)}。"
                f"请运行: pip install {' '.join(missing)}"
            )

    def get_monitors(self) -> list:
        """获取所有显示器信息"""
        import mss
        monitors: list[dict[str, Any]] = []
        with mss.MSS() as sct:
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    name = "虚拟桌面 (全部)"
                else:
                    name = f"显示器 {i} ({mon['width']}x{mon['height']})"
                monitors.append({
                    "index": i,
                    "name": name,
                    "left": mon["left"],
                    "top": mon["top"],
                    "width": mon["width"],
                    "height": mon["height"],
                })
        return monitors

    def select_region(self, monitor_index: int = 1) -> Optional[dict]:
        """弹出框选窗口让用户选择截图区域"""
        region = _select_region_on_screen(monitor_index)
        if region is not None:
            time.sleep(0.3)  # 等待 tkinter 窗口完全销毁
        return region  # None 表示用户取消

    def preview_region(self, params: dict) -> str:
        """
        根据区域参数截图并返回 base64 预览图。

        Returns:
            base64 编码的 PNG 图片数据

        Raises:
            ValueError: 参数无效
            Exception: 截图失败
        """
        import mss
        from PIL import Image

        region = {
            "left":   int(params.get("left", 0)),
            "top":    int(params.get("top", 0)),
            "width":  int(params.get("width", 600)),
            "height": int(params.get("height", 600)),
        }

        if region["width"] <= 0 or region["height"] <= 0:
            raise ValueError("区域宽高必须大于 0")

        with mss.MSS() as sct:
            screenshot = sct.grab(region)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def start(self, params: dict) -> str:
        """启动自动求解"""
        s = self._state
        with s.lock:
            if s.status in ("running", "paused"):
                raise RuntimeError("自动求解正在运行中")

        region_left = int(params.get("region_left", 0))
        region_top = int(params.get("region_top", 0))
        region_width = int(params.get("region_width", 0))
        region_height = int(params.get("region_height", 0))

        if region_width <= 0 or region_height <= 0:
            raise ValueError("截图区域宽高必须大于 0")

        s.reset()
        with s.lock:
            s.region_left = region_left
            s.region_top = region_top
            s.region_width = region_width
            s.region_height = region_height

        s._stop_event.clear()
        s._pause_event.set()

        s._thread = threading.Thread(
            target=AutoSolverWorker(s).run,
            args=(params,),
            daemon=True,
        )
        s._thread.start()

        return "自动求解已启动"

    def pause(self) -> dict:
        """暂停/继续自动求解"""
        s = self._state
        with s.lock:
            if s.status in _ACTIVE_STATUSES:
                s._pause_event.clear()
                s.status = "paused"
                s._add_log_nolock("⏸ 已暂停")
                return {"message": "已暂停", "status": "paused"}
            elif s.status == "paused":
                s._pause_event.set()
                s.status = "running"
                s._add_log_nolock("▶ 继续执行")
                return {"message": "继续执行", "status": "running"}
            else:
                raise RuntimeError("当前没有运行中的自动求解")

    def stop(self) -> None:
        """停止自动求解"""
        s = self._state
        with s.lock:
            if s.status in _STOPPABLE_STATUSES:
                s._stop_event.set()
                s._pause_event.set()
                s._placing_stop.set()
                s._add_log_nolock("⏹ 正在停止...")
            else:
                raise RuntimeError("当前没有运行中的自动求解")

    def get_status(self) -> dict:
        """获取当前状态和统计数据"""
        s = self._state
        with s.lock:
            # 如果线程已结束但状态还是 running，更新为 idle
            if (s._thread and not s._thread.is_alive()
                    and s.status in ("running", "waiting_load", "waiting_transition",
                                     "capturing", "solving", "placing")):
                s.status = "idle"

            return {
                "status": s.status,
                "error": s.error,
                "level_completed": s.level_completed,
                "total_placed": s.total_placed,
                "log": s.log,
            }
