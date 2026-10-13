"""Locate a font with CJK glyphs on Windows / macOS / Linux.

【这个文件是做什么的】
程序界面上要显示中文（例如“下一步”、“栅氧厚度”）。Panda3D 自带的默认字体只有英文字母，
画不出汉字，汉字会变成方块或干脆不显示。所以我们需要在电脑上找到一个“含有中日韩
（CJK = Chinese/Japanese/Korean）字形”的字体文件，把它的路径交给界面代码去加载。

本文件只做一件事：按顺序检查一串常见的中文字体文件路径，返回第一个真实存在的那个。
界面代码（app.py 等）会调用这里的 find_cjk_font() 来拿到字体路径。
"""
# import = “导入”：把别人写好的工具模块拿来用。
# os 模块：和操作系统打交道，例如读环境变量、判断文件是否存在。
import os
# pathlib.Path：用“对象”的方式表示文件路径，可以方便地拼接路径、列出文件夹内容。
from pathlib import Path

# __file__ 是 Python 自动提供的变量，表示“当前这个 .py 文件的路径”。
# .resolve() 把它变成完整的绝对路径；.parent 是“所在文件夹”，再 .parent 是“上一级文件夹”。
# 本文件位于 项目根目录/fabsim3d/fonts.py，所以 _HERE 就是“项目根目录”。
# 名字前面的下划线 _ 是一种约定，表示“这是本文件内部用的，外面别直接用”。
_HERE = Path(__file__).resolve().parent.parent

# CANDIDATES = “候选名单”：一个列表（list，用方括号 [] 包起来的一串东西），
# 里面按优先顺序写着可能存在的中文字体文件路径。后面会从头到尾挨个检查。
CANDIDATES = [
    # bundled with the project (drop any CJK .ttf/.otf/.ttc into ./fonts)
    # 【优先级最高】项目自带的字体：如果项目根目录下有 fonts 文件夹，就把里面的字体文件都列进来。
    # 这一行语法较多，拆开解释：
    #   - (_HERE / "fonts")：Path 对象可以用 / 号拼接路径，得到“项目根目录/fonts”。
    #   - .glob("*.[ot]t[fc]")：按通配符找文件。[ot] 表示这一位是 o 或 t，[fc] 表示 f 或 c，
    #     所以能匹配 .otf / .ttf / .ttc / .otc 这几种字体扩展名。
    #   - str(p) for p in ...：这是“生成器表达式”，意思是“对找到的每个文件 p，都转成字符串”。
    #   - sorted(...)：按字母顺序排好，保证每次结果一致。
    #   - A if 条件 else B：条件成立用 A，否则用 B。这里：fonts 文件夹存在才去找，不存在就用空列表 []。
    #   - 最前面的 * 号：“展开”，把得到的那一串路径逐个摊开放进 CANDIDATES 列表里，
    #     而不是把整个列表当作一个元素塞进去。
    *(sorted(str(p) for p in (_HERE / "fonts").glob("*.[ot]t[fc]")) if (_HERE / "fonts").is_dir() else []),
    # Windows
    # Windows 系统自带的中文字体（微软雅黑、黑体、宋体、等线）。
    # 字符串前面的 r 表示“原始字符串”：里面的反斜杠 \ 就按字面意思处理，
    # 不会被当成转义符（Windows 路径里全是 \，所以要加 r）。
    r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyh.ttf", r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\Deng.ttf",
    # macOS
    # 苹果电脑自带的中文字体（苹方、华文黑体、冬青黑体等）。
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    # Linux 系统上常见的开源中文字体（思源黑体 Noto CJK、文泉驿）。不同发行版放的位置不同，所以列了好几个。
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
]


# def = 定义一个“函数”（一段可以反复调用的代码）。
# "-> str | None" 是“类型提示”：告诉读代码的人，这个函数返回一个字符串，或者返回 None（表示“什么都没有”）。
def find_cjk_font() -> str | None:
    """找到一个能显示中文的字体文件，返回它的路径；一个都找不到就返回 None。

    为什么需要：界面要显示汉字，必须有中文字体。查找顺序是：
      1. 用户通过环境变量手动指定的字体（最优先，方便用户自己选）；
      2. CANDIDATES 名单里第一个真实存在的文件。
    """
    # 环境变量：在启动程序前由用户在系统里设置的“键=值”配置。
    # os.environ.get("名字") 读取它，没设置就得到 None。
    # A or B：如果 A 有值就用 A，否则用 B。这里先看 FABSIM3D_FONT，没有再看旧名字 CMOS3D_FONT。
    env = os.environ.get("FABSIM3D_FONT") or os.environ.get("CMOS3D_FONT")
    # 只有用户确实设置了、并且那个文件真的存在，才采用它。
    if env and os.path.exists(env):
        return env
    # for 循环：把 CANDIDATES 里的路径一个个拿出来，依次放进变量 c 里检查。
    for c in CANDIDATES:
        # 找到第一个存在的文件就立刻返回（后面的就不看了）。
        if c and os.path.exists(c):
            return c
    # 全部检查完都没找到：返回 None，调用方会退回到默认字体（汉字可能显示不出来）。
    return None
