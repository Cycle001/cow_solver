"""
小牛游戏求解器 - 核心求解包

用法：
    from solver import parse_board, solve, solve_all, draw_result
"""

from .parser import parse_board
from .solver import solve, solve_all
from .renderer import draw_result
