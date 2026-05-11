"""
求解算法: 回溯 + 剪枝
"""


def solve(board, debug=False):
    """
    回溯+剪枝求解（返回第一个解）
    约束：每行1牛、每列1牛、每色1牛、不相邻
    返回：[(row, col), ...] 或 None
    """
    n = len(board)
    solution = [None] * n
    used_cols = set()
    used_colors = set()

    def can_place(row, col):
        if col in used_cols:
            return False
        color = board[row][col]
        if color in used_colors:
            return False
        for r in range(row):
            c = solution[r]
            if c is not None and abs(row - r) <= 1 and abs(col - c) <= 1:
                return False
        return True

    def backtrack(row):
        if row == n:
            return True
        for col in range(n):
            if can_place(row, col):
                color = board[row][col]
                solution[row] = col
                used_cols.add(col)
                used_colors.add(color)
                if backtrack(row + 1):
                    return True
                solution[row] = None
                used_cols.remove(col)
                used_colors.remove(color)
        return False

    if backtrack(0):
        return [(r, solution[r]) for r in range(n)]
    return None


def solve_all(board, debug=False):
    """
    回溯+剪枝求解，返回所有解。
    约束：每行1牛、每列1牛、每色1牛、不相邻
    返回：[[(row, col), ...], ...] 解的列表（可能为空）
    """
    n = len(board)
    solution = [None] * n
    used_cols = set()
    used_colors = set()
    all_solutions = []

    def can_place(row, col):
        if col in used_cols:
            return False
        color = board[row][col]
        if color in used_colors:
            return False
        for r in range(row):
            c = solution[r]
            if c is not None and abs(row - r) <= 1 and abs(col - c) <= 1:
                return False
        return True

    def backtrack(row):
        if row == n:
            all_solutions.append([(r, solution[r]) for r in range(n)])
            return
        for col in range(n):
            if can_place(row, col):
                color = board[row][col]
                solution[row] = col
                used_cols.add(col)
                used_colors.add(color)
                backtrack(row + 1)
                solution[row] = None
                used_cols.remove(col)
                used_colors.remove(color)

    backtrack(0)

    if debug:
        print(f"共找到 {len(all_solutions)} 个解")
        for i, sol in enumerate(all_solutions):
            print(f"  解{i + 1}: {sol}")

    return all_solutions
