#!/usr/bin/env python3
"""
小牛游戏求解器 — 桌面应用入口

Flask 后端 + PyWebView 原生窗口（Windows 使用 Edge WebView2）
"""
import multiprocessing
import os
import sys
import threading
import time
import traceback
import socket

# PyInstaller 打包后需要 freeze_support
if getattr(sys, "frozen", False):
    multiprocessing.freeze_support()

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def get_free_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]

# 配置
HOST = "127.0.0.1"
PORT = get_free_port()
URL = f"http://{HOST}:{PORT}"


def _start_flask():
    """在后台线程启动 Flask，窗口关闭时自动退出"""
    from server.app import create_app
    app = create_app()
    try:
        app.run(host=HOST, port=PORT, debug=False, threaded=True, use_reloader=False)
    except Exception:
        # Flask 端口被占用等异常写日志
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)


def _wait_for_server(timeout=10):
    """等待 Flask 启动就绪"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    # 设置 DPI 感知，确保与系统设置一致
    try:
        import ctypes
        # 启用高 DPI 支持
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        # 如果在非 Windows 系统上运行，则忽略此错误
        pass
    
    # 1. 启动 Flask 后台线程
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()

    # 2. 等待 Flask 就绪
    if not _wait_for_server():
        print("错误: Flask 服务启动超时")
        sys.exit(1)

    # 3. 打开桌面窗口
    import webview
    window = webview.create_window(
        title="小牛游戏求解器",
        url=URL,
        width=1100,
        height=750,
        min_size=(900, 600),
        resizable=True,
    )
    webview.start()

    # 4. 窗口关闭后清理
    sys.exit(0)


if __name__ == "__main__":
    main()