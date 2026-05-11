#!/usr/bin/env python3
"""
将 assets/raw/ 下的多个尺寸图标合并为一个多分辨率 .ico 文件。
放入同一目录下的 .png 或 .ico 文件，按尺寸自动收集。
输出：assets/app.ico
"""
import os
from PIL import Image

SRC = os.path.join(os.path.dirname(__file__), "raw")
DST = os.path.join(os.path.dirname(__file__), "app.ico")

sizes = []
for fname in sorted(os.listdir(SRC)):
    path = os.path.join(SRC, fname)
    if not fname.lower().endswith((".png", ".ico")):
        continue
    try:
        img = Image.open(path).convert("RGBA")
        sizes.append(img)
        print(f"  ✓ {fname}  ({img.width}x{img.height})")
    except Exception as e:
        print(f"  ✗ {fname}  跳过: {e}")

if not sizes:
    print("错误: 未找到任何图标文件，请将 png/ico 放入 assets/raw/")
    exit(1)

# 找到最大的那张作为内部引用
largest = max(sizes, key=lambda im: im.width * im.height)
largest.save(DST, format="ICO", sizes=[(im.width, im.height) for im in sizes])
print(f"\n已生成: {DST}")
print(f"包含 {len(sizes)} 个尺寸: {', '.join(f'{im.width}x{im.height}' for im in sizes)}")
