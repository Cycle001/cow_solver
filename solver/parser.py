"""
图像解析 - 检测棋盘并提取颜色矩阵
"""

import numpy as np
from PIL import Image
from collections import Counter

from .utils import is_gray, color_distance


def _scan_transitions(arr, line_idx, axis='col'):
    """
    沿指定行/列扫描灰-彩边界点
    """
    h, w = arr.shape[:2]
    prev_gray = None
    transitions = []

    if axis == 'col':
        for j in range(w):
            gray = is_gray(arr[line_idx, j])
            if prev_gray is not None and gray != prev_gray:
                transitions.append(j)
            prev_gray = gray
    else:
        for i in range(h):
            gray = is_gray(arr[i, line_idx])
            if prev_gray is not None and gray != prev_gray:
                transitions.append(i)
            prev_gray = gray

    return transitions


def _extract_cells(transitions, min_cell=20):
    """从灰-彩边界中提取彩色格子区域 [(start, end), ...]"""
    if len(transitions) < 2:
        return []

    # 过滤间隔太小的噪声
    filtered = [transitions[0]]
    for t in transitions[1:]:
        if t - filtered[-1] >= 3:
            filtered.append(t)

    cells = []
    for i in range(0, len(filtered) - 1, 2):
        start = filtered[i]
        end = filtered[i + 1]
        if end - start >= min_cell:
            cells.append((start, end))

    return cells


def _score_cells(cells, axis='row'):
    """给一组格子评分：格子大小均匀度 + 总覆盖连续性"""
    if not cells:
        return -999
    sizes = [e - s for s, e in cells]
    mean_size = np.mean(sizes)
    if mean_size == 0:
        return -999
    # 方差越小越好
    size_var = np.var(sizes) / (mean_size ** 2 + 1e-6)
    # 格子间隔应该均匀
    gaps = [cells[i+1][0] - cells[i][1] for i in range(len(cells)-1)]
    if gaps:
        gap_var = np.var(gaps) / (np.mean(gaps) ** 2 + 1e-6)
    else:
        gap_var = 0
    # 格子数不能太多（避免检测到非棋盘区域）
    n_bonus = min(len(cells), 15)  # 不奖励太多格子
    return n_bonus - size_var * 100 - gap_var * 100


def _detect_grid(arr):
    """
    自动检测棋盘网格
    策略：扫描多条线，收集所有可能的格子结果，选最优组合
    """
    h, w = arr.shape[:2]

    # --- 收集列检测结果 ---
    col_all = {}
    for row_idx in range(h // 4, 3 * h // 4, max(h // 20, 5)):
        transitions = _scan_transitions(arr, row_idx, 'col')
        cells = _extract_cells(transitions)
        nc = len(cells)
        if nc >= 4:
            if nc not in col_all:
                col_all[nc] = cells
            elif _score_cells(cells) > _score_cells(col_all[nc]):
                col_all[nc] = cells

    # --- 收集行检测结果 ---
    row_all = {}
    for col_idx in range(w // 4, 3 * w // 4, max(w // 20, 5)):
        transitions = _scan_transitions(arr, col_idx, 'row')
        cells = _extract_cells(transitions)
        nr = len(cells)
        if nr >= 4:
            if nr not in row_all:
                row_all[nr] = cells
            elif _score_cells(cells) > _score_cells(row_all[nr]):
                row_all[nr] = cells

    if not col_all or not row_all:
        return [], [], 0

    # --- 找最佳行数 ---
    # 行数应该等于列数（正方形棋盘）
    # 列数通常检测更准确（水平方向干扰少）
    col_n = max(col_all.keys())  # 列数取检测到的最大值

    # 在行中找与列数相同的，如果没有就找最接近的
    if col_n in row_all:
        best_row_cells = row_all[col_n]
        best_col_cells = col_all[col_n]
        n = col_n
    else:
        # 找最接近col_n的行数
        closest_row_n = min(row_all.keys(), key=lambda x: abs(x - col_n))
        n = min(closest_row_n, col_n)
        best_row_cells = row_all[closest_row_n][:n]
        best_col_cells = col_all[col_n][:n]

    # 如果行数比列数多，取最后的n行（棋盘在图片下方）
    if len(best_row_cells) > n:
        best_row_cells = best_row_cells[-n:]
    if len(best_col_cells) > n:
        best_col_cells = best_col_cells[-n:]

    return best_row_cells, best_col_cells, n


def _assign_colors_exact_or_nearest(color_samples, n_colors, debug=False):
    """
    智能颜色分配策略：
    1. 先尝试精确匹配（四舍五入到整数后相同）
    2. 如果唯一色少于n_colors，说明采样有噪声，用层次聚类
    3. 如果唯一色多于n_colors，合并最近的
    """
    colors = np.array(color_samples, dtype=np.float64)
    n_samples = len(colors)

    # 四舍五入取整
    colors_int = np.round(colors).astype(int)

    # 统计唯一颜色
    unique_ints, inverse, counts = np.unique(colors_int, axis=0, return_inverse=True, return_counts=True)

    if debug:
        print(f"  唯一颜色种类: {len(unique_ints)}")
        for i, (uc, cnt) in enumerate(zip(unique_ints, counts)):
            print(f"    RGB=({uc[0]}, {uc[1]}, {uc[2]}) -> {cnt}格")

    n_unique = len(unique_ints)

    if n_unique == n_colors:
        # 完美情况：唯一颜色数等于目标数
        # 但分布可能不均匀，直接用精确匹配
        labels = inverse
        return labels, unique_ints.astype(float)

    elif n_unique < n_colors:
        # 需要拆分某些大类
        # 使用K-Means对大类内部做子聚类
        labels = inverse.copy()

        while len(np.unique(labels)) < n_colors:
            # 找最大的类别
            current_counts = Counter(labels)
            biggest = max(current_counts, key=current_counts.get)

            if current_counts[biggest] <= 1:
                break  # 无法继续拆分

            # 对最大类别做2类K-Means
            big_mask = labels == biggest
            big_colors = colors[big_mask]
            big_indices = np.where(big_mask)[0]

            if len(big_colors) < 2:
                break

            # 2-means
            rng = np.random.RandomState(42)
            c1_idx = rng.randint(len(big_colors))
            c2_idx = rng.randint(len(big_colors))
            while c2_idx == c1_idx:
                c2_idx = rng.randint(len(big_colors))
            center1 = big_colors[c1_idx].copy()
            center2 = big_colors[c2_idx].copy()

            for _ in range(100):
                d1 = np.sum((big_colors - center1) ** 2, axis=1)
                d2 = np.sum((big_colors - center2) ** 2, axis=1)
                sub_labels = (d1 > d2).astype(int)

                mask1 = sub_labels == 0
                mask2 = sub_labels == 1
                if np.sum(mask1) > 0:
                    center1 = big_colors[mask1].mean(axis=0)
                if np.sum(mask2) > 0:
                    center2 = big_colors[mask2].mean(axis=0)

            # 分配新标签
            new_label = max(labels) + 1
            for local_i, global_i in enumerate(big_indices):
                if sub_labels[local_i] == 1:
                    labels[global_i] = new_label

        # 重新映射标签为0..n_colors-1
        unique_labels = sorted(set(labels))
        label_map = {old: new for new, old in enumerate(unique_labels)}
        labels = np.array([label_map[l] for l in labels])

        # 计算中心
        centers = np.zeros((n_colors, 3))
        for k in range(n_colors):
            mask = labels == k
            if np.sum(mask) > 0:
                centers[k] = colors[mask].mean(axis=0)

        return labels, centers

    else:
        # n_unique > n_colors: 需要合并
        # 使用层次聚类（自底向上合并最近的两个）
        # 用唯一颜色作为聚类单元
        cluster_colors = {i: [unique_ints[i]] for i in range(n_unique)}
        cluster_sizes = {i: int(counts[i]) for i in range(n_unique)}
        next_id = n_unique

        while len(cluster_colors) > n_colors:
            # 找最近的两个簇
            min_dist = float('inf')
            merge_pair = None
            keys = list(cluster_colors.keys())

            for a in range(len(keys)):
                for b in range(a + 1, len(keys)):
                    ka, kb = keys[a], keys[b]
                    ca = np.mean(cluster_colors[ka], axis=0)
                    cb = np.mean(cluster_colors[kb], axis=0)
                    dist = color_distance(ca, cb)
                    if dist < min_dist:
                        min_dist = dist
                        merge_pair = (ka, kb)

            if merge_pair is None:
                break

            ka, kb = merge_pair
            cluster_colors[next_id] = cluster_colors[ka] + cluster_colors[kb]
            cluster_sizes[next_id] = cluster_sizes[ka] + cluster_sizes[kb]
            del cluster_colors[ka]
            del cluster_colors[kb]
            del cluster_sizes[ka]
            del cluster_sizes[kb]
            next_id += 1

        # 分配标签
        labels = np.zeros(n_samples, dtype=int)
        for cluster_id, color_list in cluster_colors.items():
            for color in color_list:
                mask = np.all(colors_int == color, axis=1)
                labels[mask] = cluster_id

        # 重新映射为0..n_colors-1
        unique_labels = sorted(set(labels))
        label_map = {old: new for new, old in enumerate(unique_labels)}
        labels = np.array([label_map[l] for l in labels])

        centers = np.zeros((n_colors, 3))
        for k in range(n_colors):
            mask = labels == k
            if np.sum(mask) > 0:
                centers[k] = colors[mask].mean(axis=0)

        return labels, centers


def parse_board(img_path, debug=False):
    """
    从图片解析棋盘
    返回: (board, board_coords, centers) 或 (None, None, None)
    """
    img = Image.open(img_path).convert('RGB')
    arr = np.array(img)

    if debug:
        print(f"图片大小: {arr.shape[1]}x{arr.shape[0]}")

    # 检测网格
    row_cells, col_cells, n = _detect_grid(arr)

    if n == 0:
        print("错误: 无法检测到棋盘网格")
        return None, None, None

    if debug:
        print(f"检测到 {n}x{n} 棋盘")

    # 采样每个格子中心的颜色
    color_samples = []
    for i in range(n):
        for j in range(n):
            r_start, r_end = row_cells[i]
            c_start, c_end = col_cells[j]
            margin_r = (r_end - r_start) * 0.2
            margin_c = (c_end - c_start) * 0.2
            y1 = int(r_start + margin_r)
            y2 = int(r_end - margin_r)
            x1 = int(c_start + margin_c)
            x2 = int(c_end - margin_c)
            cell = arr[y1:y2, x1:x2]
            mean_color = cell.mean(axis=(0, 1))
            color_samples.append(mean_color)

    colors_arr = np.array(color_samples, dtype=np.float64)

    # 智能颜色分配
    labels, centers = _assign_colors_exact_or_nearest(color_samples, n, debug=debug)

    board = np.array(labels).reshape(n, n)

    if debug:
        counts = Counter(board.flatten())
        print(f"颜色分布: {dict(sorted(counts.items()))}")
        print("颜色矩阵:")
        for row in board:
            print(' '.join(f'{x:2d}' for x in row))

    board_coords = (row_cells, col_cells)
    return board, board_coords, centers
