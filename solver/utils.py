"""
求解器工具函数
"""

import numpy as np


def is_gray(pixel, tol=15):
    """判断像素是否为灰色（R≈G≈B）"""
    r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
    return abs(r - g) < tol and abs(g - b) < tol and abs(r - b) < tol


def color_distance(c1, c2):
    """加权颜色距离（人眼对绿色更敏感）"""
    r1, g1, b1 = c1[0], c1[1], c1[2]
    r2, g2, b2 = c2[0], c2[1], c2[2]
    return np.sqrt(2.0 * (r1 - r2) ** 2 + 4.0 * (g1 - g2) ** 2 + 3.0 * (b1 - b2) ** 2)
