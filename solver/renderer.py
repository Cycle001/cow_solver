"""
图像标注 - 在结果图上标记牛的位置
"""

import os
from PIL import Image, ImageDraw, ImageFont


def draw_result(img_path, cow_positions, board_coords, output_path='result.png', debug=False):
    """在原图上标记牛的位置：圆圈 + emoji"""
    img = Image.open(img_path).convert('RGBA')
    draw = ImageDraw.Draw(img)

    row_cells, col_cells = board_coords

    for row, col in cow_positions:
        r_start, r_end = row_cells[row]
        c_start, c_end = col_cells[col]

        x = (c_start + c_end) / 2
        y = (r_start + r_end) / 2
        cell_w = c_end - c_start
        cell_h = r_end - r_start
        radius = min(cell_w, cell_h) * 0.38

        # 白色外圈
        draw.ellipse(
            [x - radius - 3, y - radius - 3, x + radius + 3, y + radius + 3],
            outline=(255, 255, 255, 255), width=5
        )
        # 黑色内圈
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            outline=(0, 0, 0, 255), width=3
        )

        # 尝试画 emoji
        try:
            font_size = int(min(cell_w, cell_h) * 0.55)
            font = None
            for fp in ["C:/Windows/Fonts/seguiemj.ttf",
                       "C:/Windows/Fonts/Segoe UI Emoji.ttf"]:
                if os.path.exists(fp):
                    try:
                        font = ImageFont.truetype(fp, font_size)
                        break
                    except Exception:
                        continue
            if font is None:
                font = ImageFont.load_default()

            emoji = "\U0001F404"
            bbox = draw.textbbox((0, 0), emoji, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text((x - tw / 2, y - th / 2), emoji, fill='black', font=font)
        except Exception as e:
            if debug:
                print(f"emoji绘制失败({e})，使用实心圆")
            draw.ellipse(
                [x - radius * 0.6, y - radius * 0.6, x + radius * 0.6, y + radius * 0.6],
                fill=(255, 50, 50, 255)
            )

    img.convert('RGB').save(output_path)
    if debug:
        print(f"结果已保存到: {output_path}")
    return output_path
