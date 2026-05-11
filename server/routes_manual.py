"""
手动求解接口
"""

import os
import sys
import io
import base64
import tempfile
import traceback

from flask import Blueprint, jsonify, request, send_file, send_from_directory

from solver import parse_board, solve, solve_all, draw_result

manual_bp = Blueprint("manual", __name__)

# 前端目录（兼容 PyInstaller 打包和开发模式）
if getattr(sys, "frozen", False):
    # PyInstaller 打包：frontend/ 由 --add-data 复制到 sys._MEIPASS
    _FRONTEND_DIR = os.path.join(sys._MEIPASS, "frontend")
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _FRONTEND_DIR = os.path.join(_BASE_DIR, "frontend")


@manual_bp.route("/")
def index():
    """返回前端页面"""
    return send_from_directory(_FRONTEND_DIR, "index.html")


@manual_bp.route("/css/<path:filename>")
def serve_css(filename):
    """返回 CSS 静态资源"""
    return send_from_directory(os.path.join(_FRONTEND_DIR, "css"), filename)


@manual_bp.route("/js/<path:filename>")
def serve_js(filename):
    """返回 JS 静态资源"""
    return send_from_directory(os.path.join(_FRONTEND_DIR, "js"), filename)


@manual_bp.route("/solve", methods=["POST"])
def handle_solve():
    """
    接收前端传来的 base64 图片，调用求解器，返回结果图片的 base64。
    请求体 JSON: { "image": "<base64编码的图片数据>" }
    响应体 JSON: { "success": true/false, "image": "<base64结果图>", "message": "..." }
    """
    try:
        data = request.get_json()
        if not data or "image" not in data:
            return jsonify({"success": False, "message": "未收到图片数据"}), 400

        image_b64 = data["image"]
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]

        image_bytes = base64.b64decode(image_b64)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            board, board_coords, centers = parse_board(tmp_path, debug=False)

            if board is None:
                return jsonify({"success": False, "message": "无法检测到棋盘，请确认截图包含完整的游戏棋盘"})

            cow_positions = solve(board, debug=False)

            if cow_positions is None:
                return jsonify({"success": False, "message": "未找到解，请确认截图清晰且游戏状态有效"})

            # 查找所有解
            all_solutions = solve_all(board, debug=False)
            total_solutions = len(all_solutions)

            result_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            result_tmp.close()
            draw_result(tmp_path, cow_positions, board_coords, result_tmp.name, debug=False)

            with open(result_tmp.name, "rb") as f:
                result_b64 = base64.b64encode(f.read()).decode("utf-8")

            os.unlink(result_tmp.name)

            msg = f"找到 {len(cow_positions)} 头牛！"
            if total_solutions > 1:
                msg += f"（共 {total_solutions} 种解法）"

            return jsonify({
                "success": True,
                "image": result_b64,
                "total_solutions": total_solutions,
                "message": msg
            })

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500
