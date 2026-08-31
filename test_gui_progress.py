# -*- coding: utf-8 -*-
"""自动化验证：转换后状态恢复 + 输出文件名自定义。"""
import base64
import shutil
import sys
import tempfile
import time
from pathlib import Path

from tkinterdnd2 import TkinterDnD
import markitdown_gui


def _run(files, out_name, out_dir):
    """创建 GUI、添加文件、触发转换，驱动事件循环直到完成。返回 app。"""
    root = TkinterDnD.Tk()
    app = markitdown_gui.MarkItDownApp(root)
    app.out_dir_var.set(str(out_dir))
    if out_name is not None:
        app.out_name_var.set(out_name)
    app.add_paths([str(f) for f in files])
    app.start_convert()
    deadline = time.time() + 60
    while app.busy and time.time() < deadline:
        root.update()
        time.sleep(0.05)
    root.destroy()
    return app


def main():
    tmp = Path(tempfile.mkdtemp(prefix="mid_gui_test_"))
    try:
        # 准备源文件（txt 由 PlainTextConverter 处理）
        for n in ("a.txt", "b.txt"):
            (tmp / n).write_text(f"# {n}\n\n内容。\n", encoding="utf-8")
        a, b = tmp / "a.txt", tmp / "b.txt"

        results = []

        # 场景1：两个文件，无自定义名 → a.md / b.md
        app = _run([a, b], None, tmp / "out1")
        ok1 = (
            not app.busy
            and app.ok_count == 2
            and (tmp / "out1" / "a.md").exists()
            and (tmp / "out1" / "b.md").exists()
        )
        results.append(("多文件·默认名", ok1))

        # 场景2：两个文件，自定义名 → 合并_1.md / 合并_2.md
        app = _run([a, b], "合并", tmp / "out2")
        ok2 = (
            not app.busy
            and app.ok_count == 2
            and (tmp / "out2" / "合并_1.md").exists()
            and (tmp / "out2" / "合并_2.md").exists()
        )
        results.append(("多文件·自定义名+序号", ok2))

        # 场景3：单文件，自定义名 → 我的笔记.md
        app = _run([a], "我的笔记", tmp / "out3")
        ok3 = (
            not app.busy
            and app.ok_count == 1
            and (tmp / "out3" / "我的笔记.md").exists()
        )
        results.append(("单文件·自定义名", ok3))

        # 场景4：单文件，无自定义名 → a.md
        app = _run([a], None, tmp / "out4")
        ok4 = (
            not app.busy
            and app.ok_count == 1
            and (tmp / "out4" / "a.md").exists()
        )
        results.append(("单文件·默认名", ok4))

        # 场景5：单文件，自定义名带 .md 后缀 → 直接使用
        app = _run([a], "笔记.md", tmp / "out5")
        ok5 = (
            not app.busy
            and app.ok_count == 1
            and (tmp / "out5" / "笔记.md").exists()
        )
        results.append(("自定义名带.md后缀", ok5))

        # 场景6：把 base64 图片提取为独立文件（目录名=原文件名_images）
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        md_in = f"![](data:image/png;base64,{png_b64})\n\n正文。"
        new_md = markitdown_gui._extract_images(md_in, tmp / "imgdoc.txt", tmp / "out6")
        imgs = list((tmp / "out6" / "imgdoc_images").glob("image_*.png"))
        ok6 = (
            "imgdoc_images/image_1.png" in new_md
            and "data:image/png;base64" not in new_md
            and len(imgs) == 1
            and imgs[0].read_bytes() == base64.b64decode(png_b64)
        )
        results.append(("图片提取为独立文件", ok6))

        # 场景7：端到端——带 data URI 图片的 HTML 转换后提取出真实图片（验证 0KB bug 修复）
        html = (
            '<html><body><img src="data:image/png;base64,'
            f'{png_b64}" alt="pic"><p>hi</p></body></html>'
        )
        (tmp / "imgdoc.html").write_text(html, encoding="utf-8")
        app = _run([tmp / "imgdoc.html"], None, tmp / "out7")
        md7 = tmp / "out7" / "imgdoc.md"
        imgs7 = list((tmp / "out7" / "imgdoc_images").glob("*.png"))
        ok7 = (
            not app.busy
            and app.ok_count == 1
            and md7.exists()
            and len(imgs7) == 1
            and imgs7[0].read_bytes() == base64.b64decode(png_b64)
            and "data:image/png;base64" not in md7.read_text(encoding="utf-8")
        )
        results.append(("HTML含图端到端提取", ok7))

        print("=" * 44)
        passed = 0
        for label, ok in results:
            print(f"[{'PASS' if ok else 'FAIL'}] {label}")
            passed += int(ok)
        print(f"总计：{passed}/{len(results)} 通过")
        return 0 if passed == len(results) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
