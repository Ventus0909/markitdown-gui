# 办公文档转 Markdown（MarkItDown GUI）

基于 [microsoft/markitdown](https://github.com/microsoft/markitdown) 的图形化转换工具，
把 Word、Excel、PPT、PDF、图片、音频等常见格式一键转换为 Markdown。

## 功能

- 拖拽文件或点击「选择文件」添加，支持一次批量转换多个文件
- 输出目录默认与源文件同目录，可自定义
- 自定义输出文件名（多文件时自动追加序号避免覆盖）
- 文件级转换进度条（多文件按文件数推进，单文件显示动画）
- 文档内嵌图片自动提取为独立文件（保存到 `<原文件名>_images/` 目录），
  Markdown 中用相对路径引用，不再内嵌 base64
- 不支持的格式 / 缺少依赖 / 转换失败，均会给出中文提示
- 「打开生成的 md」「打开输出目录」快捷按钮

## 使用

双击 `dist\MarkItDownGUI\MarkItDownGUI.exe` 启动，拖入文件后点「开始转换」即可。
生成结果：`<文件名>.md` + `<文件名>_images/`（图片目录，如有图片）。

## 构建

环境要求：Windows + Python 3.10+

```bat
:: 1. 安装依赖（含全部可选转换依赖）
uv venv --python 3.12 .venv
uv pip install -e "packages/markitdown[all]"

:: 2. 一键打包（生成图标 + PyInstaller onedir 打包）
build_exe.bat
```

产物位于 `dist\MarkItDownGUI\`，分发时整体拷贝该文件夹。

## 文件说明

| 文件 / 目录 | 说明 |
|---|---|
| `markitdown_gui.py` | GUI 主程序（tkinter + tkinterdnd2） |
| `make_icon.py` | 程序图标生成脚本（PIL） |
| `icon.ico` | 程序图标 |
| `build_exe.bat` | 一键打包脚本 |
| `test_gui_progress.py` | 自动化回归测试 |
| `packages/markitdown` | 上游 markitdown 包源码 |

## 注意

- 音频转文字（mp3 / wav 等）需要系统安装 [ffmpeg](https://ffmpeg.org/)
- 首次转换会加载文件识别模型（magika），稍慢属正常
- 打包前请确保没有正在运行的 `MarkItDownGUI.exe`，否则会因文件占用打包失败
