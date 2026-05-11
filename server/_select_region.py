"""
tkinter 屏幕区域框选工具（内部模块）

支持多显示器 + 高 DPI 缩放。坐标系策略：
- mss 返回物理像素（截图和 monitor 尺寸）
- tkinter 窗口使用逻辑像素（与进程 DPI 感知相关）
- 返回的坐标统一为 mss 物理像素空间，与 mss.grab() 和 SetCursorPos 一致
"""

from PIL import Image, ImageTk, ImageEnhance


def _select_region_on_screen(monitor_index=1):
    """
    在指定显示器上弹出 tkinter 覆盖窗口，让用户拖拽框选区域。
    返回 dict: {"left", "top", "width", "height"} 或 None（用户取消）。

    坐标统一为 mss 物理像素空间，兼容多显示器 + 高 DPI。
    """
    import tkinter as tk
    import mss

    # 1. 获取目标显示器的截图（mss 物理像素空间）
    with mss.MSS() as sct:
        if monitor_index < 0 or monitor_index >= len(sct.monitors):
            raise ValueError(f"无效的显示器索引: {monitor_index}")
        mon = sct.monitors[monitor_index]
        screenshot = sct.grab(mon)
        bg_img_phys = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    phys_w, phys_h = bg_img_phys.size      # 物理像素（mss 截图实际尺寸）
    mss_w, mss_h = mon["width"], mon["height"]  # mss 报告的显示器尺寸

    # 2. 检测 DPI 缩放：物理像素 / mss 报告尺寸
    #    高 DPI 下 mss 报告的是逻辑尺寸，物理像素 > 逻辑尺寸
    dpi_scale_x = max(1.0, phys_w / max(mss_w, 1))
    dpi_scale_y = max(1.0, phys_h / max(mss_h, 1))

    # 3. 计算逻辑坐标（用于 tkinter 窗口定位）
    logic_w = max(1, int(phys_w / dpi_scale_x))
    logic_h = max(1, int(phys_h / dpi_scale_y))
    logic_left = int(mon["left"] / dpi_scale_x)
    logic_top = int(mon["top"] / dpi_scale_y)

    # 4. 准备显示的背景图（缩放到逻辑尺寸，与 tkinter canvas 坐标系对齐）
    if bg_img_phys.size != (logic_w, logic_h):
        bg_img = bg_img_phys.resize((logic_w, logic_h), Image.LANCZOS)
    else:
        bg_img = bg_img_phys

    # 保存物理像素的显示器偏移（用于最终坐标转换）
    phys_left = mon["left"]
    phys_top = mon["top"]

    result = {}
    cancelled = [False]

    # 5. 创建无边框全屏覆盖窗口
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{logic_w}x{logic_h}+{logic_left}+{logic_top}")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 1.0)
    root.configure(bg="black")

    # 暗化背景
    darkened = ImageEnhance.Brightness(bg_img).enhance(0.4)

    canvas = tk.Canvas(root, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill=tk.BOTH, expand=True)

    bg_photo = ImageTk.PhotoImage(darkened)
    canvas._bg_photo = bg_photo
    canvas.create_image(0, 0, anchor="nw", image=bg_photo)

    # 提示文字
    canvas.create_text(
        logic_w // 2, int(logic_h * 0.06),
        anchor="n",
        text="按住鼠标左键拖拽框选区域，按 ESC 取消",
        fill="white", font=("Microsoft YaHei", 16, "bold"))

    # 框选状态
    start_x = [0]
    start_y = [0]
    rect_id = [None]
    label_id = [None]
    size_label_id = [None]
    selecting = [False]

    def _canvas_to_phys(cx, cy):
        """将 tkinter canvas 逻辑坐标转换为 mss 物理像素空间坐标"""
        px = int(cx * dpi_scale_x) + phys_left
        py = int(cy * dpi_scale_y) + phys_top
        return px, py

    def on_press(event):
        selecting[0] = True
        start_x[0] = event.x
        start_y[0] = event.y

    def on_drag(event):
        if not selecting[0]:
            return
        for rid in (rect_id[0], label_id[0], size_label_id[0]):
            if rid:
                canvas.delete(rid)
        x1, y1 = min(start_x[0], event.x), min(start_y[0], event.y)
        x2, y2 = max(start_x[0], event.x), max(start_y[0], event.y)
        w, h = x2 - x1, y2 - y1

        rect_id[0] = canvas.create_rectangle(x1, y1, x2, y2,
                                              outline="#00FF00", width=2)

        # 显示物理像素空间坐标（虚拟桌面全局坐标）
        px1, py1 = _canvas_to_phys(x1, y1)
        label_id[0] = canvas.create_text(
            x1, y1 - 6, anchor="sw",
            text=f"({px1}, {py1})",
            fill="#00FF00", font=("Consolas", 11))

        # 显示区域物理像素尺寸
        pw = int((x2 - x1) * dpi_scale_x)
        ph = int((y2 - y1) * dpi_scale_y)
        size_label_id[0] = canvas.create_text(
            (x1 + x2) / 2, (y1 + y2) / 2, anchor="center",
            text=f"{pw} x {ph}",
            fill="#00FF00", font=("Consolas", 16, "bold"))

    def on_release(event):
        if not selecting[0]:
            return
        selecting[0] = False
        x1 = min(start_x[0], event.x)
        y1 = min(start_y[0], event.y)
        x2 = max(start_x[0], event.x)
        y2 = max(start_y[0], event.y)

        # 转换为物理像素空间
        px1, py1 = _canvas_to_phys(x1, y1)
        px2, py2 = _canvas_to_phys(x2, y2)
        pw = px2 - px1
        ph = py2 - py1

        min_phys = int(20 * max(dpi_scale_x, dpi_scale_y))
        if pw < min_phys or ph < min_phys:
            for rid in (rect_id[0], label_id[0], size_label_id[0]):
                if rid:
                    canvas.delete(rid)
            return

        result.update({"left": px1, "top": py1, "width": pw, "height": ph})
        root.destroy()

    def on_escape(event):
        if event.keysym == "Escape":
            cancelled[0] = True
            root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    root.focus_force()
    root.mainloop()

    if cancelled[0] or not result:
        return None
    return result
