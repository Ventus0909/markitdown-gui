# -*- coding: utf-8 -*-
"""生成程序图标 icon.ico（现代风格：蓝紫渐变 + 白色文档 + 对勾）。"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
ACCENT = (59, 130, 246)      # #3B82F6
VIOLET = (99, 102, 241)      # #6366F1
GREY = (203, 213, 225)       # #CBD5E1


def make_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 渐变圆角背景
    radius = 56
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=radius, fill=255)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        r = round(ACCENT[0] + (VIOLET[0] - ACCENT[0]) * t)
        g = round(ACCENT[1] + (VIOLET[1] - ACCENT[1]) * t)
        b = round(ACCENT[2] + (VIOLET[2] - ACCENT[2]) * t)
        d.line((0, y, SIZE, y), fill=(r, g, b, 255))
    img.putalpha(mask)

    # 中央白色文档（圆角）
    doc = (70, 46, 200, 186)
    d.rounded_rectangle(doc, radius=18, fill="white")

    # 文档顶部标题条
    d.rounded_rectangle((88, 68, 160, 82), radius=7, fill=GREY)
    # 正文文字行
    d.rounded_rectangle((88, 96, 182, 108), radius=6, fill=GREY)
    d.rounded_rectangle((88, 122, 152, 134), radius=6, fill=GREY)
    # 底部短行
    d.rounded_rectangle((88, 148, 132, 160), radius=6, fill=GREY)

    # 右下角对勾（表示转换成功），用渐变紫色
    d.line([(100, 168), (118, 186), (164, 140)],
           fill=ACCENT, width=16, joint="curve")

    return img


def main():
    out = Path(__file__).resolve().parent / "icon.ico"
    img = make_icon()
    img.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"图标已生成：{out}")


if __name__ == "__main__":
    main()
