"""
自动求解接口
"""

import io
import base64
import threading
import time
import traceback

from flask import Blueprint, jsonify, request, Response

from .auto_thread import auto_solver, _check_deps, _auto_solver_thread
from ._select_region import _select_region_on_screen

auto_bp = Blueprint("auto", __name__)


# ============================================================
# 显示器管理 & 区域框选
# ============================================================

@auto_bp.route("/monitors", methods=["GET"])
def auto_monitors():
    """获取所有显示器的信息，供前端选择截图区域使用"""
    try:
        _check_deps()
        import mss
        with mss.MSS() as sct:
            monitors = []
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
        return jsonify({"success": True, "monitors": monitors})
    except ImportError as e:
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})


@auto_bp.route("/select-region", methods=["POST"])
def auto_select_region():
    """
    在指定显示器上弹出框选窗口，让用户拖拽选择截图区域。
    请求体 JSON: { "monitor_index": 1 }
    响应体 JSON: { "success": true, "region": { left, top, width, height } }
    注意：此接口会阻塞直到用户完成框选或取消。
    """
    try:
        _check_deps()
        params = request.get_json(force=True)
        monitor_index = int(params.get("monitor_index", 1))

        region = _select_region_on_screen(monitor_index)

        # 等待 tkinter 窗口完全销毁，避免后续截图预览截到黑色窗口残留
        if region is not None:
            time.sleep(0.3)

        if region is None:
            return jsonify({"success": False, "message": "用户取消了框选"})

        return jsonify({"success": True, "region": region})
    except ImportError as e:
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"框选失败: {str(e)}"})


@auto_bp.route("/preview-region", methods=["POST"])
def auto_preview_region():
    """
    根据区域参数截取一张预览图返回给前端，让用户确认截图区域是否正确。
    请求体 JSON: { left, top, width, height }
    响应体 JSON: { success: true, image: "<base64>" }
    """
    try:
        _check_deps()
        import mss
        from PIL import Image

        params = request.get_json(force=True)
        region = {
            "left": int(params.get("left", 0)),
            "top": int(params.get("top", 0)),
            "width": int(params.get("width", 600)),
            "height": int(params.get("height", 600)),
        }

        if region["width"] <= 0 or region["height"] <= 0:
            return jsonify({"success": False, "message": "区域宽高必须大于 0"})

        with mss.MSS() as sct:
            screenshot = sct.grab(region)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return jsonify({"success": True, "image": img_b64})
    except ImportError as e:
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"截图预览失败: {str(e)}"})


# ============================================================
# 自动求解控制接口
# ============================================================

@auto_bp.route("/start", methods=["POST"])
def auto_start():
    """
    启动自动求解。
    请求体 JSON: {
        region_left, region_top, region_width, region_height,
        click_delay, load_wait, transition_wait, max_levels
    }
    """
    try:
        # 检查依赖
        _check_deps()

        with auto_solver.lock:
            if auto_solver.status in ("running", "paused"):
                return jsonify({"success": False, "message": "自动求解正在运行中"})

        params = request.get_json(force=True)
        region_left = int(params.get("region_left", 0))
        region_top = int(params.get("region_top", 0))
        region_width = int(params.get("region_width", 0))
        region_height = int(params.get("region_height", 0))

        if region_width <= 0 or region_height <= 0:
            return jsonify({"success": False, "message": "截图区域宽高必须大于 0"})

        auto_solver.reset()
        with auto_solver.lock:
            auto_solver.region_left = region_left
            auto_solver.region_top = region_top
            auto_solver.region_width = region_width
            auto_solver.region_height = region_height

        # 停止事件重置
        auto_solver._stop_event.clear()
        auto_solver._pause_event.set()

        # 启动后台线程
        auto_solver._thread = threading.Thread(
            target=_auto_solver_thread,
            args=(params,),
            daemon=True
        )
        auto_solver._thread.start()

        return jsonify({"success": True, "message": "自动求解已启动"})

    except ImportError as e:
        return jsonify({"success": False, "message": str(e)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"启动失败: {str(e)}"})


@auto_bp.route("/pause", methods=["POST"])
def auto_pause():
    """暂停/继续自动求解"""
    _active = ("running", "capturing", "solving", "placing",
               "waiting_load", "waiting_transition")
    with auto_solver.lock:
        if auto_solver.status in _active:
            auto_solver._pause_event.clear()
            auto_solver.status = "paused"
            auto_solver._add_log_nolock("⏸ 已暂停")
            return jsonify({"success": True, "message": "已暂停", "status": "paused"})
        elif auto_solver.status == "paused":
            auto_solver._pause_event.set()
            auto_solver.status = "running"
            auto_solver._add_log_nolock("▶ 继续执行")
            return jsonify({"success": True, "message": "继续执行", "status": "running"})
        else:
            return jsonify({"success": False, "message": "当前没有运行中的自动求解"})


@auto_bp.route("/stop", methods=["POST"])
def auto_stop():
    """停止自动求解"""
    _active = ("running", "capturing", "solving", "placing",
               "waiting_load", "waiting_transition", "paused")
    with auto_solver.lock:
        if auto_solver.status in _active:
            auto_solver._stop_event.set()
            auto_solver._pause_event.set()  # 解除暂停以便线程能退出
            # 同时通知放置子线程尽快停下
            auto_solver._placing_stop.set()
            auto_solver._add_log_nolock("⏹ 正在停止...")
            return jsonify({"success": True, "message": "正在停止..."})
        else:
            return jsonify({"success": False, "message": "当前没有运行中的自动求解"})


@auto_bp.route("/status", methods=["GET"])
def auto_status():
    """获取自动求解状态"""
    with auto_solver.lock:
        # 如果线程已结束但状态还是 running，更新为 idle
        if (auto_solver._thread and not auto_solver._thread.is_alive()
                and auto_solver.status in ("running", "waiting_load", "waiting_transition",
                                             "capturing", "solving", "placing")):
            auto_solver.status = "idle"

        return jsonify({
            "status": auto_solver.status,
            "error": auto_solver.error,
            "level_completed": auto_solver.level_completed,
            "total_placed": auto_solver.total_placed,
            "log": auto_solver.log,
        })


@auto_bp.route("/log-stream", methods=["GET"])
def auto_log_stream():
    """SSE 日志流，实时推送操作状态"""
    def generate():
        last_time = time.time()
        try:
            while True:
                entries = auto_solver.get_log(after=last_time)
                if entries:
                    for t, msg in entries:
                        last_time = t
                        yield f"data: {msg}\n\n"
                time.sleep(0.3)
        except GeneratorExit:
            # 客户端断开连接，正常退出
            pass
    return Response(generate(), mimetype="text/event-stream")
