"""
Flask 应用创建与启动
"""

import atexit

from flask import Flask

from .auto_thread import auto_solver
from .routes_manual import manual_bp
from .routes_auto import auto_bp


def create_app():
    """创建并配置 Flask 应用"""
    app = Flask(__name__)

    # 注册蓝图
    app.register_blueprint(manual_bp)               # /, /solve
    app.register_blueprint(auto_bp, url_prefix="/auto")  # /auto/*

    # 退出清理
    def _cleanup():
        """确保服务器退出时停止所有后台线程"""
        auto_solver._stop_event.set()
        auto_solver._pause_event.set()
        auto_solver._placing_stop.set()
        if auto_solver._placing_thread and auto_solver._placing_thread.is_alive():
            auto_solver._placing_thread.join(timeout=2.0)
        if auto_solver._thread and auto_solver._thread.is_alive():
            auto_solver._thread.join(timeout=3.0)

    atexit.register(_cleanup)

    return app


def main():
    """启动入口"""
    app = create_app()
    print("=" * 50)
    print("  小牛游戏求解器 - Web 界面")
    print("=" * 50)
    print("\n访问 http://localhost:5000")
    print("按 Ctrl+C 停止服务器\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
