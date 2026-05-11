"""
自动求解后台线程

包含 AutoSolverState（状态管理）和 _auto_solver_thread（主循环）
"""

import os
import tempfile
import threading
import time
import traceback

import numpy as np
from PIL import Image

from solver import parse_board, solve_all


def _check_deps():
    """检查并导入桌面自动化依赖"""
    missing = []
    try:
        import mss  # noqa: F401
    except ImportError:
        missing.append("mss")
    if missing:
        raise ImportError(f"缺少依赖库: {', '.join(missing)}。请运行: pip install {' '.join(missing)}")


class AutoSolverState:
    """自动求解器状态管理"""

    def __init__(self):
        self.lock = threading.Lock()
        # 状态：idle / running / paused / completed / error
        self.status = "idle"
        self.error = ""
        self.level_completed = 0  # 已完成的关卡数
        self.total_placed = 0
        self.log = []  # 操作日志 [(timestamp, message), ...]
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始不暂停
        self._thread = None
        # 放置牛的子线程（独立于主求解线程）
        self._placing_thread = None
        self._placing_lock = threading.Lock()  # 保护 _placing_done / _placing_stop
        self._placing_done = threading.Event()  # 放置线程完成信号
        self._placing_stop = threading.Event()  # 通知放置线程提前终止
        # 用户参数
        self.region_left = 0
        self.region_top = 0
        self.region_width = 0
        self.region_height = 0
        self.click_delay = 100  # 毫秒
        self.load_wait = 3.0
        self.transition_wait = 3.0

    def reset(self):
        with self.lock:
            self.status = "idle"
            self.error = ""
            self.level_completed = 0
            self.total_placed = 0
            self.log = []

    def add_log(self, msg):
        with self.lock:
            self.log.append((time.time(), msg))
            if len(self.log) > 200:
                self.log = self.log[-100:]

    def _add_log_nolock(self, msg):
        """在已持有 self.lock 的上下文中追加日志（不再加锁，避免死锁）"""
        self.log.append((time.time(), msg))
        if len(self.log) > 200:
            self.log = self.log[-100:]

    def get_log(self, after=0):
        with self.lock:
            return [(t, m) for t, m in self.log if t > after]

    def set_status(self, status, error=""):
        with self.lock:
            self.status = status
            if error:
                self.error = error


# 全局单例
auto_solver = AutoSolverState()


def _auto_solver_thread(params):
    """
    自动求解主循环（在后台线程中运行）
    流程：
    1. 截图 -> 2. 求解 -> 3. 放置牛 -> 4. 等待转场 -> 回到 1
    """
    import mss
    import ctypes

    region = {
        "top": params["region_top"],
        "left": params["region_left"],
        "width": params["region_width"],
        "height": params["region_height"],
    }
    click_delay = 100  # 双击间隔（毫秒），固定值
    load_wait = params.get("load_wait", 3.0)
    transition_wait = params.get("transition_wait", 3.0)
    max_levels = params.get("max_levels", 9999)

    # 获取虚拟桌面尺寸（mss 坐标空间：物理像素），用于鼠标绝对坐标转换。
    # 使用 mss 虚拟桌面尺寸而非 GetSystemMetrics（后者返回逻辑分辨率），
    # 确保与 mss.grab() 返回的区域坐标在同一坐标系中。
    try:
        with mss.MSS() as sct_tmp:
            vd = sct_tmp.monitors[0]
            vd_width = vd["width"]
            vd_height = vd["height"]
    except Exception:
        # 降级方案：使用 GetSystemMetrics（适用于 DPI 100% 场景）
        vd_width = ctypes.windll.user32.GetSystemMetrics(0)
        vd_height = ctypes.windll.user32.GetSystemMetrics(1)

    def wait_and_check_pause(seconds):
        """
        等待指定秒数（可被 stop 中断），等待结束后处理暂停。
        若被停止返回 True，否则返回 False。
        """
        auto_solver._stop_event.wait(seconds)
        if auto_solver._stop_event.is_set():
            return True
        # 如果当前处于暂停状态，设置状态并等待继续
        if not auto_solver._pause_event.is_set():
            prev_status = auto_solver.status
            auto_solver.set_status("paused")
            # 等待继续或停止
            while not auto_solver._pause_event.is_set():
                auto_solver._stop_event.wait(0.2)
                if auto_solver._stop_event.is_set():
                    return True
            # 继续后恢复之前的状态
            auto_solver.set_status(prev_status)
        return False

    try:
        auto_solver.set_status("running")
        auto_solver.add_log("自动求解已启动")

        level_num = 1
        while level_num <= max_levels:
            # 检查停止信号
            if auto_solver._stop_event.is_set():
                auto_solver.add_log("⏹ 自动求解已停止")
                auto_solver.set_status("idle")
                return

            # 等待暂停解除（循环开头的暂停检测，0秒等待）
            if wait_and_check_pause(0):
                auto_solver.add_log("⏹ 自动求解已停止")
                auto_solver.set_status("idle")
                return

            auto_solver.add_log(f"--- 第 {level_num} 关 ---")

            # 首关等待游戏加载
            if level_num == 1:
                auto_solver.add_log("等待游戏加载...")
                auto_solver.set_status("waiting_load")
                if wait_and_check_pause(load_wait):
                    auto_solver.add_log("⏹ 自动求解已停止")
                    auto_solver.set_status("idle")
                    return

            # 第2关起等待转场
            if level_num > 1:
                auto_solver.add_log("等待转场动画...")
                auto_solver.set_status("waiting_transition")
                if wait_and_check_pause(transition_wait):
                    auto_solver.add_log("⏹ 自动求解已停止")
                    auto_solver.set_status("idle")
                    return

            # 1. 截图
            auto_solver.add_log("正在截图...")
            auto_solver.set_status("capturing")
            try:
                with mss.MSS() as sct:
                    screenshot = sct.grab(region)
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            except Exception as e:
                auto_solver.add_log(f"截图失败: {e}")
                auto_solver.set_status("error", f"截图失败: {e}")
                return

            # 保存截图到临时文件
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    img.save(tmp, format="PNG")
                    tmp_path = tmp.name

                # 2. 求解（找到所有解）
                auto_solver.add_log("正在求解...")
                auto_solver.set_status("solving")

                board, board_coords, _ = parse_board(tmp_path, debug=False)

                if board is None:
                    auto_solver.add_log("无法检测到棋盘，等待后重试...")
                    auto_solver.add_log(f"--- 重试第 {level_num} 关 ---")
                    if wait_and_check_pause(2.0):
                        auto_solver.add_log("⏹ 自动求解已停止")
                        auto_solver.set_status("idle")
                        return
                    continue

                all_solutions = solve_all(board, debug=False)

                if not all_solutions:
                    auto_solver.add_log("当前关卡无解，可能识别有误，等待后重试...")
                    auto_solver.add_log(f"--- 重试第 {level_num} 关 ---")
                    if wait_and_check_pause(2.0):
                        auto_solver.add_log("⏹ 自动求解已停止")
                        auto_solver.set_status("idle")
                        return
                    continue

                num_solutions = len(all_solutions)
                if num_solutions == 1:
                    auto_solver.add_log(f"找到 1 种解，开始放置...")
                else:
                    auto_solver.add_log(f"找到 {num_solutions} 种解，开始尝试第 1 种...")

                # 3. 尝试每种解
                row_cells, col_cells = board_coords

                for sol_idx, cow_positions in enumerate(all_solutions):
                    # 检查停止信号
                    if auto_solver._stop_event.is_set():
                        auto_solver.add_log("自动求解已停止")
                        auto_solver.set_status("idle")
                        return

                    if num_solutions > 1:
                        auto_solver.add_log(f">>> 尝试第 {sol_idx + 1}/{num_solutions} 种解 <<<")

                    # 3a. 在独立线程中放置牛（不阻塞主求解线程）
                    auto_solver.set_status("placing")
                    n = len(cow_positions)

                    # 预先计算每个牛的屏幕坐标
                    place_targets = []
                    for row, col in cow_positions:
                        screen_x = region["left"] + (col_cells[col][0] + col_cells[col][1]) / 2
                        screen_y = region["top"] + (row_cells[row][0] + row_cells[row][1]) / 2
                        place_targets.append((screen_x, screen_y))

                    # 重置放置线程信号
                    auto_solver._placing_done.clear()
                    auto_solver._placing_stop.clear()

                    # 在独立线程中执行点击放置
                    def _placing_worker(targets, click_delay_ms, total_count):
                        """在独立线程中逐个放置牛（使用 Win32 API，兼容多显示器 + 高 DPI）"""
                        import ctypes as _ct

                        # Win32 API 常量和函数
                        MOUSEEVENTF_LEFTDOWN   = 0x0002
                        MOUSEEVENTF_LEFTUP     = 0x0004
                        MOUSEEVENTF_ABSOLUTE   = 0x8000
                        MOUSEEVENTF_VIRTUALDESK = 0x4000  # 关键：使用虚拟桌面坐标系，兼容多显示器
                        _user32 = _ct.windll.user32

                        def _set_cursor(x, y, duration=0.15):
                            """移动鼠标（Win32 SetCursorPos，使用虚拟桌面物理坐标）"""
                            _user32.SetCursorPos(int(x), int(y))
                            if duration > 0:
                                time.sleep(duration)

                        def _do_double_click(x, y, interval_s):
                            """
                            使用 mouse_event + MOUSEEVENTF_VIRTUALDESK 发送双击。
                            坐标使用 mss 虚拟桌面物理像素，与 mss.grab() 坐标系一致，
                            解决高 DPI + 多显示器下坐标偏移问题。
                            """
                            flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
                            abs_x = int(x * 65535 / vd_width)
                            abs_y = int(y * 65535 / vd_height)
                            # 第一次点击
                            _user32.mouse_event(MOUSEEVENTF_LEFTDOWN | flags, abs_x, abs_y, 0, 0)
                            time.sleep(0.01)
                            _user32.mouse_event(MOUSEEVENTF_LEFTUP | flags, abs_x, abs_y, 0, 0)
                            # 间隔（用户指定的双击间隔）
                            time.sleep(interval_s)
                            # 第二次点击
                            _user32.mouse_event(MOUSEEVENTF_LEFTDOWN | flags, abs_x, abs_y, 0, 0)
                            time.sleep(0.01)
                            _user32.mouse_event(MOUSEEVENTF_LEFTUP | flags, abs_x, abs_y, 0, 0)

                        click_interval = click_delay_ms / 1000.0  # 用户指定的双击间隔（毫秒→秒）
                        click_delay_s = click_interval  # 两次双击之间的间隔 = 用户设定值
                        for i, (sx, sy) in enumerate(targets):
                            if auto_solver._placing_stop.is_set():
                                break
                            auto_solver.add_log(f"放置第 {i + 1}/{total_count} 头牛")
                            _set_cursor(sx, sy, duration=0.15)
                            time.sleep(0.05)
                            _do_double_click(sx, sy, click_interval)
                            time.sleep(click_delay_s)
                            with auto_solver._placing_lock:
                                auto_solver.total_placed += 1
                        auto_solver._placing_done.set()

                    auto_solver._placing_thread = threading.Thread(
                        target=_placing_worker,
                        args=(place_targets, click_delay, n),
                        daemon=True
                    )
                    auto_solver._placing_thread.start()

                    # 等待放置完成，同时响应暂停/停止
                    while not auto_solver._placing_done.is_set():
                        auto_solver._placing_done.wait(0.1)
                        # 检查全局停止信号
                        if auto_solver._stop_event.is_set():
                            # 通知放置线程尽快停下
                            auto_solver._placing_stop.set()
                            # 等待放置线程退出
                            auto_solver._placing_thread.join(timeout=2.0)
                            auto_solver.add_log("⏹ 自动求解已停止")
                            auto_solver.set_status("idle")
                            return
                        # 处理暂停
                        if not auto_solver._pause_event.is_set():
                            prev_status = auto_solver.status
                            auto_solver.set_status("paused")
                            # 放置线程继续执行（已在运行中无法安全中断鼠标操作）
                            # 等待继续或停止
                            while not auto_solver._pause_event.is_set():
                                auto_solver._stop_event.wait(0.2)
                                if auto_solver._stop_event.is_set():
                                    auto_solver._placing_stop.set()
                                    auto_solver._placing_thread.join(timeout=2.0)
                                    auto_solver.add_log("⏹ 自动求解已停止")
                                    auto_solver.set_status("idle")
                                    return
                            auto_solver.set_status("placing")

                    # 3b. 等待观察：检查是否通关
                    # 游戏通过后会出现转场/过关动画，没通过则画面不变
                    # 策略：等待一段时间后截图，与之前的截图对比判断是否发生了变化
                    auto_solver.add_log("等待游戏响应...")
                    auto_solver.set_status("waiting_transition")
                    if wait_and_check_pause(2.0):
                        auto_solver.add_log("⏹ 自动求解已停止")
                        auto_solver.set_status("idle")
                        return

                    # 再次截图对比
                    try:
                        with mss.MSS() as sct:
                            new_screenshot = sct.grab(region)
                            new_img = Image.frombytes("RGB", new_screenshot.size, new_screenshot.bgra, "raw", "BGRX")

                        # 简单判断：两张图的平均像素差异
                        arr_old = np.array(img)
                        arr_new = np.array(new_img)
                        diff = np.mean(np.abs(arr_old.astype(float) - arr_new.astype(float)))

                        if diff > 30:
                            # 画面发生了显著变化 → 通关！
                            auto_solver.level_completed += 1
                            if num_solutions > 1:
                                auto_solver.add_log(f"第 {level_num} 关完成！（使用了第 {sol_idx + 1} 种解）已通过 {auto_solver.level_completed} 关")
                            else:
                                auto_solver.add_log(f"第 {level_num} 关完成！已通过 {auto_solver.level_completed} 关")
                            level_num += 1  # 成功后进入下一关
                            break

                        else:
                            # 画面没变化 → 当前解不正确
                            if num_solutions > 1 and sol_idx + 1 < num_solutions:
                                auto_solver.add_log(f"当前解未通关，准备尝试下一种解...")
                            else:
                                # 最后一种解也失败了，可能是识别问题
                                auto_solver.add_log("所有解均未通关，等待后重新识别棋盘...")
                                auto_solver.add_log(f"--- 重试第 {level_num} 关 ---")
                                # 重新截图尝试当前关
                                if wait_and_check_pause(2.0):
                                    auto_solver.add_log("⏹ 自动求解已停止")
                                    auto_solver.set_status("idle")
                                    return
                                continue

                    except Exception as e:
                        auto_solver.add_log(f"对比截图失败: {e}，假设通关并继续...")
                        auto_solver.level_completed += 1
                        auto_solver.add_log(f"第 {level_num} 关完成！已通过 {auto_solver.level_completed} 关")
                        level_num += 1  # 成功后进入下一关
                        break

                else:
                    # for 循环未被 break → 所有解都没通关，继续当前关
                    pass

            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        # 达到最大关卡数
        auto_solver.add_log(f"已完成设定的 {max_levels} 关！共放置 {auto_solver.total_placed} 头牛")
        auto_solver.set_status("completed")

    except Exception as e:
        traceback.print_exc()
        auto_solver.add_log(f"错误: {str(e)}")
        auto_solver.set_status("error", str(e))
