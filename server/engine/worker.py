"""
自动求解主循环

逻辑：
1. 检测棋盘
2. 若检测到棋盘 → 求解并放置牛 → 关卡+1 → 提示进入下一关
3. 若未检测到棋盘 → 提示用户点击下一关/关闭广告 → 5秒倒计时 → 重试
4. 无限循环，直到用户停止
"""

import os
import tempfile
import threading
import time
import traceback

from PIL import Image
from typing import List, Tuple, Optional, Any, Dict

from solver import parse_board, solve_all
from exceptions import BoardNotFoundException
from .state import AutoSolverState
from ..automation.screenshot import ScreenCapturer
from ..automation.mouse import MouseController
from config import TIMING as _TIMING_CFG


class AutoSolverWorker:
    """自动求解主循环（无限循环，直到用户停止）"""

    def __init__(self, state: AutoSolverState) -> None:
        self.state = state
        self._mouse = MouseController()
        self._capturer = ScreenCapturer()

    # =====================================================================
    # 主入口
    # =====================================================================

    def run(self, params: Dict[str, Any]) -> None:
        """主循环入口（在后台线程中运行）"""
        import mss  # noqa: F401

        region = {
            "top": params["region_top"],
            "left": params["region_left"],
            "width": params["region_width"],
            "height": params["region_height"],
        }
        click_delay: float = _TIMING_CFG.click_delay_ms / 1000.0
        retry_wait: float = _TIMING_CFG.retry_wait_s

        def log(msg: str) -> None:
            self.state.add_log(msg)

        def set_status(status: str, error: str = "") -> None:
            self.state.set_status(status, error)

        try:
            set_status("running")
            log("自动求解已启动")
            log(f"流程: 截图→识别棋盘→求解→放置→提示下一关")
            log(f"无棋盘时: 提示手动操作 → 等待 {retry_wait:.0f} 秒 → 重试")

            level_num = 1

            while True:
                if self._should_stop(log, set_status):
                    return

                if self._wait_pausable(0):
                    log("⏹ 自动求解已停止")
                    set_status("idle")
                    return

                log(f"=== 第 {level_num} 关 ===")

                # =========================================================
                # 等待棋盘出现（循环重试直到检测成功）
                # =========================================================
                board = None
                board_coords = None
                retry_count = 0

                while board is None:
                    if self._should_stop(log, set_status):
                        return

                    set_status("capturing")
                    attempt = retry_count + 1
                    log(f"正在截图... 第{attempt}次检测（第{level_num}关）")
                    img = self._capturer.capture_region(region)

                    if img is None:
                        retry_count += 1
                        log("截图失败，等待后重试...")
                        if self._wait_pausable(3):
                            log("⏹ 自动求解已停止")
                            set_status("idle")
                            return
                        continue

                    # 解析棋盘（无棋盘时 parse_board 抛出 BoardNotFoundException）
                    tmp_path: Optional[str] = None
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            img.save(tmp, format="PNG")
                            tmp_path = tmp.name
                        board, board_coords, _ = parse_board(tmp_path, debug=False)
                    except BoardNotFoundException:
                        board = None
                        board_coords = None
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass

                    if board is not None:
                        log("检测到棋盘!")
                        break

                    # 无棋盘 — 提示用户操作
                    retry_count += 1
                    log("────────────────────────")
                    log(f"第{attempt}次检测未发现棋盘（已尝试{retry_count}次）")
                    log("请进行以下操作之一：")
                    log("  1. 点击「下一关」按钮进入新关卡")
                    log("  2. 点击 × 关闭可能存在的广告弹窗")
                    log(f"将在 {retry_wait:.0f} 秒后自动重试...")
                    set_status("waiting_transition")

                    # 倒计时日志
                    for sec in range(int(retry_wait), 0, -1):
                        log(f"  ⏳ {sec} 秒后重新检测...")
                        if self._should_stop(log, set_status):
                            return
                        if not self.state._pause_event.is_set():
                            prev_status = self.state.status
                            set_status("paused")
                            while not self.state._pause_event.is_set():
                                if self._should_stop(log, set_status):
                                    return
                                time.sleep(0.2)
                            set_status(prev_status)
                        else:
                            time.sleep(1.0)

                    log("  ⏳ 重新检测中...")

                # =========================================================
                # 求解
                # =========================================================
                log("正在求解...")
                set_status("solving")

                all_solutions = solve_all(board, debug=False)

                if not all_solutions:
                    log("当前关卡无解，可能识别有误")
                    log(f"等待 {retry_wait:.0f} 秒后重新识别...")
                    if self._wait_pausable(retry_wait):
                        log("⏹ 自动求解已停止")
                        set_status("idle")
                        return
                    continue  # 不增加 level_num

                num_solutions = len(all_solutions)
                if num_solutions == 1:
                    log("找到 1 种解，开始放置...")
                else:
                    log(f"找到 {num_solutions} 种解，开始尝试第 1 种...")

                row_cells, col_cells = board_coords

                # =========================================================
                # 尝试每种解
                # =========================================================
                solved = False
                for sol_idx, cow_positions in enumerate(all_solutions):
                    if self._should_stop(log, set_status):
                        return

                    if num_solutions > 1:
                        log(f">>> 尝试第 {sol_idx + 1}/{num_solutions} 种解 <<<")

                    place_targets: List[Tuple[float, float]] = []
                    for row, col in cow_positions:
                        sx = region["left"] + (col_cells[col][0] + col_cells[col][1]) / 2
                        sy = region["top"] + (row_cells[row][0] + row_cells[row][1]) / 2
                        place_targets.append((sx, sy))

                    set_status("placing")
                    n = len(cow_positions)
                    self.state._placing_done.clear()
                    self.state._placing_stop.clear()

                    placing_thread = threading.Thread(
                        target=self._placing_worker,
                        args=(place_targets, click_delay, n),
                        daemon=True
                    )
                    self.state._placing_thread = placing_thread
                    placing_thread.start()

                    if self._wait_placing(log, set_status):
                        return

                    log("牛已放置完成")
                    self.state.level_completed += 1
                    solved = True
                    break

                if solved:
                    log(f"第 {level_num} 关完成！已通过 {self.state.level_completed} 关")
                    log("────────────────────────")
                    log("请手动进入下一关")
                    log("────────────────────────")
                    level_num += 1
                else:
                    log("所有解均无效，等待后重新识别棋盘...")
                    if self._wait_pausable(retry_wait):
                        log("⏹ 自动求解已停止")
                        set_status("idle")
                        return

        except Exception as e:
            traceback.print_exc()
            log(f"错误: {str(e)}")
            set_status("error", str(e))

    # =====================================================================
    # 辅助方法
    # =====================================================================

    def _should_stop(self, log, set_status) -> bool:
        if self.state._stop_event.is_set():
            log("⏹ 自动求解已停止")
            set_status("idle")
            return True
        return False

    def _wait_pausable(self, seconds: float) -> bool:
        """
        等待指定秒数（可被 stop 中断）。

        Returns:
            True 如果被停止，否则 False
        """
        s = self.state
        s._stop_event.wait(seconds)
        if s._stop_event.is_set():
            return True
        if not s._pause_event.is_set():
            prev_status = s.status
            s.set_status("paused")
            while not s._pause_event.is_set():
                s._stop_event.wait(_TIMING_CFG.poll_interval_s)
                if s._stop_event.is_set():
                    return True
            s.set_status(prev_status)
        return False

    def _wait_placing(self, log, set_status) -> bool:
        """等待放置线程完成，同时响应暂停/停止"""
        s = self.state
        while not s._placing_done.is_set():
            s._placing_done.wait(0.1)
            if s._stop_event.is_set():
                s._placing_stop.set()
                if s._placing_thread and s._placing_thread.is_alive():
                    s._placing_thread.join(timeout=2.0)
                log("⏹ 自动求解已停止")
                set_status("idle")
                return True
            if not s._pause_event.is_set():
                prev_status = s.status
                s.set_status("paused")
                while not s._pause_event.is_set():
                    s._stop_event.wait(_TIMING_CFG.poll_interval_s)
                    if s._stop_event.is_set():
                        s._placing_stop.set()
                        if s._placing_thread and s._placing_thread.is_alive():
                            s._placing_thread.join(timeout=2.0)
                        log("⏹ 自动求解已停止")
                        set_status("idle")
                        return True
                s.set_status("placing")
        return False

    # =====================================================================
    # 放置牛的线程
    # =====================================================================

    def _placing_worker(
        self,
        targets: List[Tuple[float, float]],
        click_delay_ms: float,
        total_count: int,
    ) -> None:
        """在独立线程中逐个放置牛，不阻塞主线程"""
        click_interval = click_delay_ms / 1000.0
        click_delay_s = click_interval

        for i, (sx, sy) in enumerate(targets):
            if self.state._placing_stop.is_set():
                break
            self.state.add_log(f"放置第 {i + 1}/{total_count} 头牛")
            self._mouse.smooth_move_and_double_click(
                int(sx), int(sy),
                interval_s=click_interval,
                duration=_TIMING_CFG.smooth_move_duration_s,
            )
            time.sleep(click_delay_s)
            with self.state._placing_lock:
                self.state.total_placed += 1

        self.state._placing_done.set()
