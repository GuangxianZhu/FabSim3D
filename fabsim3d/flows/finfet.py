"""~14 nm FinFET CMOS: fins, gate wrapped on three sides, epitaxial raised S/D.

The channel stands up out of the wafer as a thin fin; the gate covers its
top and both sidewalls, so the drain field can hardly reach into the channel.
Fins run along x (source -> drain); three fins per transistor sit side by
side in y.  Fin tops are at z = 0, the STI is recessed to FIN_REVEAL.

【中文说明 —— 这个文件是干什么的？】
本文件描述“FinFET (鳍式场效应晶体管) 工艺”这一整条工艺流程，大约对应 22 nm ~ 5 nm 时代
(界面上叫 14 nm)。它把一片硅片一步一步加工成一个 CMOS 反相器 (一个 NMOS + 一个 PMOS)。

为什么需要 FinFET？到 28 nm 时，平面晶体管的栅只能从“上面”一个面去控制沟道，
栅长太短后，漏极的电场会“伸进”沟道，晶体管关不干净 (漏电大、DIBL 大)。
FinFET 把沟道做成从硅片里立起来的一片薄薄的“鳍”，栅像马鞍一样从顶面和左右两个侧面
三面包住它，控制力大大增强，所以可以继续缩小。

程序里一条工艺流程 = 一份“数据清单” (下面的 STEPS 列表) + 几个小函数：
  * 每一步 (Step) 写明标题、说明、参数表、动画阶段 (Phase) 和小测验；
  * 阶段里的动作 (deposit 淀积、recess 刻蚀凹槽、cmp 研磨、anneal 退火 ……) 会修改 3D 硅片模型；
  * 小函数负责算出“鳍在哪里”“外延块长什么形状”等几何形状；
  * 文件最后的 FLOW 把这些打包，主程序在“工艺选择”菜单中列出它。
许多步骤借用 sti.py / locos.py 的老步骤，现代工艺共用的步骤 (ILD0、去伪栅、HKMG、接触孔、铜) 在 _modern.py。

【坐标约定】
  x = 屏幕左右方向，也是电流方向 (源 -> 漏)，鳍沿 x 方向延伸；NMOS 在左半边，PMOS 在右半边；
  y = 垂直于屏幕往里的方向 (剖面切开的方向)，每个晶体管的 3 条鳍沿 y 方向并排；
  z = 向上；鳍的顶面在 z = 0，鳍之间的 STI 氧化物顶面被回刻到 FIN_REVEAL (负数，低于鳍顶)。
  数字是“显示单位”，不是真实纳米；竖直方向 (z) 被放大了，好让薄膜看得清。
"""
# 让类型注解推迟解析 (初学者可忽略这一行)。
from __future__ import annotations

# replace(旧对象, 字段=新值)：复制一个已有的步骤，只改其中几个字段 (用来借用老工艺的步骤)。
from dataclasses import replace
# List 只用于类型标注，例如 "-> List[Solid]" 表示“这个函数返回一串 Solid”。
from typing import List

# “..” 表示上一级目录的包。Solid = 3D 实体块；rect_complement(大区域, 一堆矩形) = 大区域里扣掉这些矩形后
# 剩下的部分；rect_intersect(a, b) = 两个矩形重叠的部分 (不重叠就返回 None，即“没有”)。
from ..geometry import Solid, rect_complement, rect_intersect
# process_core 里是工艺动作的“积木” (淀积、刻蚀、注入、退火、CMP、光刻、出题 ……) 和流程数据结构；
# DOMAIN 是整个画面区域的矩形；sci/vt_text 是把数字格式化成界面文字的小工具。
from ..process_core import (DOMAIN, Flow, Phase, Step, add_solids, anneal, cmp, deposit, gate_span,
                            gates, implant_solids, layout, litho, pattern, quiz, recess, replace_layer,
                            sci, spacer_span, split_gates, strip, summarize_cached, vt_text)
# 同目录下的两条老工艺流程，用来借用它们的步骤和端子标签。
from . import locos, sti
# _modern.py：现代工艺共用的步骤生成函数和几何小工具。
from ._modern import (EPI_NOTE, M1_TOP, channel_rects, contact_step, copper_m1_step, done_step,
                      hkmg_step, ild0_step, rmg_remove_step, side_slabs)

# 把老工艺的步骤列表变成“按名字查找”的字典 (字典推导式：对每个步骤 s，存一条 s.key -> s)。
# 例如 _S["nitride"] = 0.25 µm STI 工艺的“淀积氮化硅”步骤，_L["padox"] = LOCOS 工艺的“垫氧化层”步骤。
_S = {s.key: s for s in sti.STEPS}
_L = {s.key: s for s in locos.STEPS}

# ---------------- 几何常数 (显示单位；中文注释说明各自的含义) ----------------
# 每条鳍在 y 方向上的宽度 (画面上为了看得见画宽了；真实鳍宽由参数 tsi_nm 决定，只有几纳米)。
FIN_W = 0.36
# 3 条鳍的中心线 y 坐标。一个晶体管有 3 条鳍并排，电流是 3 条鳍加起来。
FIN_YC = (2.3, 3.5, 4.7)
# 每条鳍占据的 y 范围 (y0, y1) = 中心 ± 半个鳍宽。这是“列表推导式”：对每个中心 y 算出一对数。
FIN_BANDS = [(y - FIN_W / 2, y + FIN_W / 2) for y in FIN_YC]
# 鳍之间的硅被刻到这么深 (z = -0.85)，鳍从这里“立起来”。
TRENCH_Z = -0.85         # silicon etched down to here between fins
# STI 氧化物回刻后顶面的高度：鳍从 -0.45 到 0 这一段露在外面，将来被栅包住、成为沟道 (即 Hfin)。
FIN_REVEAL = -0.45       # STI top after the recess: exposed fin height 0.45
# 鳍顶上的氮化硅硬掩膜的顶面高度；STI 填充后的 CMP 研磨停在这里。
NITRIDE_TOP = 0.18
# 伪栅多晶硅 CMP 后的顶面高度 (比鳍顶高，把鳍完全埋住)；后面 ILD0 也磨到这个高度。
GATE_TOP = 0.5
# 源漏处的鳍被刻低到这里，然后从这里开始外延生长源漏。
SD_RECESS = -0.25
# 外延源漏 (SiP / SiGe) 的顶面高度，高出鳍顶 → “抬高的源漏”。
EPI_TOP = 0.15
# N 阱的底部深度。
WELL_BOT = -1.8


def finfet_layout(p):
    """FinFET 专用的版图 (俯视图上各区域的矩形位置)。

    为什么需要它？平面工艺的版图 layout(p) 只有整块的“有源区”；FinFET 的有源区要再切成一条条鳍，
    而且鳍之外全是隔离区。这里先拿平面版图，再加上：
      lay["fins"]          —— 所有鳍的矩形 (NMOS 3 条 + PMOS 3 条)，每个是 (x0, x1, y0, y1)；
      lay["iso"]           —— 隔离区 = 整个画面扣掉鳍 (这些地方的硅会被刻低)；
      lay["spacer_bands"]  —— 栅侧墙沿 y 方向分段的底部高度：在鳍上是 0 (鳍顶)，
                              在鳍与鳍之间是 FIN_REVEAL (落在 STI 表面上)，这样侧墙才贴着地形。
    p 是工艺参数；返回一个字典 (dict)，用 lay["名字"] 取出各个区域。
    """
    lay = layout(p)
    fins = []
    for act in (lay["act_n"], lay["act_p"]):
        # 鳍在 x 方向和有源区一样长，在 y 方向占 FIN_BANDS 的三个窄条。“+=” 表示追加到列表末尾。
        fins += [(act[0], act[1], y0, y1) for y0, y1 in FIN_BANDS]
    lay["fins"] = fins
    lay["iso"] = rect_complement(DOMAIN, fins)
    # 栅 (以及侧墙) 在 y 方向从 1.1 延伸到 6.5，横跨 3 条鳍。下面从 gy0 开始往 y 增大方向走，
    # 依次记录“鳍间空隙 (底在 STI 上)”和“鳍 (底在鳍顶)”这样交替的分段。
    gy0, gy1 = 1.1, 6.5
    bands, y = [], gy0
    for y0, y1 in FIN_BANDS:
        bands += [(y, y0, FIN_REVEAL), (y0, y1, 0.0)]
        y = y1
    bands.append((y, gy1, FIN_REVEAL))
    lay["spacer_bands"] = bands
    return lay


def _fins(c):
    """返回所有鳍的矩形 —— 鳍光刻、刻蚀时就用它当“要保留的图形”。

    c 是上下文 (context)，c.lay 是上面 finfet_layout 算出的版图。
    """
    return c.lay["fins"]


def _well_solids(c) -> List[Solid]:
    """N 阱 (PMOS 所在的 N 型区域) 的 3D 形状。

    因为硅表面已经被刻成鳍，N 阱不再是一整块：
      * 下半部分：沟槽底 TRENCH_Z 以下的一整块 (WELL_BOT 到 TRENCH_Z)；
      * 上半部分：只有落在 N 阱区域里的那几条鳍 (TRENCH_Z 到 0)。
    这样注入的磷只出现在“硅”里，不会画到鳍之间的氧化物里去。
    """
    nw = c.lay["nwell"]
    out = [Solid.box(nw[0], nw[1], nw[2], nw[3], WELL_BOT, TRENCH_Z)]
    for f in c.lay["fins"]:
        r = rect_intersect(f, nw)
        if r:   # 如果这条鳍和 N 阱有重叠 (即它是 PMOS 的鳍)
            out.append(Solid.box(r[0], r[1], r[2], r[3], TRENCH_Z, 0.0))
    for s in out:
        s.anchor = 0.0
    return out


def _sd_fin_rects(c, key):
    """Fin segments outside gate + spacers of the n (key 'n') or p device.

    中文：返回 NMOS (key="n") 或 PMOS (key="p") 的鳍上，位于“栅 + 侧墙”两边的那几段 ——
    也就是源区和漏区的鳍段。外延源漏之前要把这些段刻低。
    结果 = 左右两段 × 3 条鳍 = 6 个矩形 (下面是一个两层 for 的列表推导式)。
    """
    act = c.lay["act_" + key]
    g = spacer_span(c, "g" + key)
    return [(x0, x1, y0, y1) for x0, x1 in ((act[0], g[0]), (g[1], act[1])) for y0, y1 in FIN_BANDS]


def _epi(key):
    """Merged epitaxial S/D: one block per side bridging the three fins.

    中文：外延源漏的形状。真实工艺中外延从每条鳍上分别长出来，长大后相邻的连成一片，
    所以这里直接画成每边一整块 (源一块、漏一块)，在 y 方向上横跨 3 条鳍 (两头各多出 0.12)。
    高度从 SD_RECESS (鳍被刻低处) 到 EPI_TOP (高出原鳍顶)。

    这是一个“返回函数的函数”：_epi("n") 并不马上算形状，而是造出一个只需要 c 的小函数 fn，
    等到动画真正运行、知道版图之后再调用。因为 add_solids 要的就是“输入 c、输出实体”的函数。
    """
    def fn(c):
        act = c.lay["act_" + key]
        g = spacer_span(c, "g" + key)
        y0, y1 = FIN_BANDS[0][0] - 0.12, FIN_BANDS[-1][1] + 0.12
        out = []
        for x0, x1 in ((act[0], g[0]), (g[1], act[1])):
            s = Solid.box(x0, x1, y0, y1, SD_RECESS, EPI_TOP)
            s.anchor = SD_RECESS
            out.append(s)
        return out
    return fn


def _hk_wrap(c):
    """高 k 介质 (HfO2) 包在鳍左右两个侧壁上的薄片。

    平面工艺的 hkmg_step 只会在顶面铺一层；FinFET 需要额外补上两侧壁这部分，
    才能画出“三面包围”。side_slabs 在每条鳍的两侧 (栅范围内) 造竖直的薄片，
    从 STI 表面 FIN_REVEAL 到鳍顶 0，紧贴鳍 (偏移 0)，厚 0.03。
    """
    return side_slabs(channel_rects(c), FIN_BANDS, FIN_REVEAL, 0.0, 0.0, 0.03)


def _wf_wrap(key):
    """功函数金属包在鳍侧壁上的薄片 (NMOS 用 key="n"，PMOS 用 key="p")。

    它在高 k 薄片的外面 (偏移 0.03)，厚 0.05。返回的是一个 lambda 小函数，原因同 _epi。
    """
    return lambda c: side_slabs(channel_rects(c, key), FIN_BANDS, FIN_REVEAL + 0.03, 0.0, 0.03, 0.05)


def _contact_silicide(c):
    """接触孔底部的硅化物薄层 (降低金属和源漏之间的接触电阻)。

    FinFET 的源漏顶面在 EPI_TOP (外延块顶)，所以硅化物贴着 EPI_TOP 做。
    只做源漏的接触孔；名字以 "g_" 开头的是栅的接触孔，栅已经是金属，不需要硅化物。
    """
    ct = c.lay["contacts"]
    return [Solid.box(r[0], r[1], r[2], r[3], EPI_TOP - 0.03, EPI_TOP + 0.02)
            for k, r in ct.items() if not k.startswith("g_")]


def fin_channels(lay):
    """Inversion layers: the whole fin under the gate (top + both sidewalls).

    中文：给“电学 / 载流子仿真”画面用的“反型层”(导电沟道) 形状。
    栅打开时，载流子在栅下面的整段鳍里流动 (顶面 + 两个侧面)，所以每条鳍在栅下方
    画一块从 FIN_REVEAL 到鳍顶的薄块。返回 [(“n”或“p”, 实体), ...]。
    """
    out = []
    for key in ("n", "p"):
        g = lay["g" + key]
        for y0, y1 in FIN_BANDS:
            out.append((key, Solid.box(g[0] - 0.05, g[1] + 0.05, y0 - 0.02, y1 + 0.02, FIN_REVEAL, 0.01)))
    return out


def fin_text(c) -> str:
    """生成显示用的“有效沟道宽度”文字，例如 “3 × (2×42 + 8) nm ≈ 0.28 µm”。

    一条鳍的导电宽度 = 两个侧面高度 (各约 42 nm) + 顶面宽度 (鳍宽 tsi_nm)，再乘以鳍数 3。
    f"..." 是格式化字符串：花括号 {} 里的表达式会被算出来填进去，":.0f" 表示保留 0 位小数。
    """
    weff = 2 * 42 + c.p.tsi_nm
    return (f"{len(FIN_YC)} × (2×42 + {c.p.tsi_nm:.0f}) nm ≈ {len(FIN_YC) * weff / 1e3:.2f} µm")


# ==========================================================================
# STEPS：整条 FinFET 工艺的步骤清单，按顺序执行 (界面上每按一次“下一步”走一项)。
# 写法有三种：replace(老步骤, 改几个字段) / 直接照搬老步骤 / Step(...) 全新步骤。
# Step 的参数依次是：步骤名、(中文标题, 英文标题)、(中文说明, 英文说明)、
#   参数表 [(中文名, 英文名, 计算显示值的函数)]、动画阶段 [Phase(...)]、小测验 quiz(...)，
#   有的还多一个 (中文, 英文) 掩膜标签。
# “lambda c: ...” 是一行写成的无名小函数：输入上下文 c，返回要显示的值 (随滑块实时变化)。
# Phase(中文名, 英文名, 动画秒数, [动作, ...]) 是一步里的一小段动画。
# ==========================================================================
STEPS = [
    # ---- 起始硅片：300 mm P 型硅片。鳍几乎不掺杂 (近本征)，原因见后面阱注入那一步的测验 ----
    replace(_L["wafer"],
            desc=("300 mm <100> P 型硅片。FinFET (鳍式场效应晶体管) 不再把沟道做在硅表面，"
                  "而是从硅片里“刻”出一排薄薄的竖直硅鳍，让栅从三面包住它。2011 年 Intel 22 nm 首次量产。",
                  "A 300 mm <100> p-type wafer. A FinFET no longer puts the channel in the wafer surface: "
                  "thin vertical silicon fins are carved out of the wafer and the gate wraps them on three "
                  "sides. Intel shipped the first ones at 22 nm in 2011."),
            params=[("晶向", "Orientation", lambda c: "<100>"),
                    ("硅片直径", "Wafer diameter", lambda c: "300 mm"),
                    ("鳍掺杂", "Fin doping", lambda c: sci(c.p.na_cm3, "cm^-3") + " (近本征)")]),
    # 垫氧化层：很薄的 SiO2，缓冲上面氮化硅对硅的应力 (照搬 LOCOS 工艺的这一步)。
    _L["padox"],
    # 氮化硅硬掩膜：先当刻鳍的掩膜 (比光刻胶更耐刻)，之后当 STI 研磨的停止层。
    replace(_S["nitride"],
            desc=("LPCVD 淀积 Si3N4 硬掩膜。它将定义鳍的图形，之后还是 STI CMP 的停止层。",
                  "An LPCVD Si3N4 hard mask. It will carry the fin pattern and later stop the STI CMP.")),

    # ---- 鳍光刻 (SADP 自对准双重图形) ----
    # 鳍太密，一次光刻做不出来，所以借“侧墙”把线条数量翻倍。程序里直接画出最终的鳍图形。
    # litho(要保留的图形, mask=掩膜名) 生成“涂胶 → 曝光 → 显影”几段光刻动画。
    Step("fin_litho", ("鳍图形 (SADP 自对准双重图形)", "Fin patterning (SADP)"),
         ("鳍的间距只有约 42 nm，比一次 193 nm 光刻能分辨的还小。做法是“自对准双重图形” (SADP)："
          "先光刻出较宽的芯轴，在芯轴两侧做侧墙，去掉芯轴后，侧墙就成了间距减半的鳍掩膜。图中直接画出最终的鳍掩膜。",
          "The fin pitch is only ~42 nm, finer than one 193 nm exposure can resolve. Self-aligned double "
          "patterning (SADP) prints wider mandrels, forms spacers on both sides and removes the mandrels; "
          "the spacers become a fin mask at half the pitch. The final fin mask is drawn here."),
         [("掩膜", "Mask", lambda c: "FIN (SADP)"),
          ("鳍间距", "Fin pitch", lambda c: "≈ 42 nm"),
          ("鳍宽 Wfin", "Fin width Wfin", lambda c: f"{c.p.tsi_nm:.1f} nm")],
         litho(_fins, mask="FIN"),
         quiz("SADP 能把图形间距缩小到多少？", "By how much does SADP shrink the pitch?",
              [("一半", "Half"), ("十分之一", "One tenth"), ("不变", "Unchanged"), ("两倍", "Doubled")], 0,
              "每个芯轴两侧各留下一条侧墙，线条数量翻倍，间距减半；重复一次 (SAQP) 可再减半。",
              "Each mandrel leaves two spacers, doubling the lines and halving the pitch; repeating it (SAQP) halves it again."),
         ("鳍", "FIN")),

    # ---- 刻蚀硅鳍：让鳍“立起来” ----
    # 先把图形转到氮化硅硬掩膜上 (pattern：只保留 _fins 处的薄膜)，去胶，
    # 再把鳍以外 (lay["iso"] 隔离区) 的硅垂直往下刻到 TRENCH_Z，留下的就是一排竖直的硅鳍。
    Step("fin_etch", ("刻蚀硅鳍", "Fin etch"),
         ("先把图形转移到氮化硅硬掩膜上，去胶后以硬掩膜为掩蔽，用 HBr/Cl2 等离子体垂直刻蚀硅，"
          "在硅片上留下一排排高约 100 nm、宽只有几纳米的硅鳍。鳍要又直又细，侧壁越陡，器件越一致。",
          "The pattern is transferred into the nitride hard mask; after the resist strip, HBr/Cl2 plasma "
          "etches the silicon vertically, leaving rows of fins ~100 nm tall and only a few nm wide. "
          "Straight, steep sidewalls make every device alike."),
         [("刻蚀", "Etch", lambda c: "HBr / Cl2 / O2 RIE"),
          ("鳍高", "Fin height", lambda c: "≈ 100 nm (露出 42 nm)"),
          ("鳍宽 Wfin", "Fin width Wfin", lambda c: f"{c.p.tsi_nm:.1f} nm")],
         [Phase("刻蚀氮化硅硬掩膜", "Etch the nitride hard mask", 1.4,
                [pattern("nitride", _fins, mask="FIN"), pattern("padox", _fins, particles=False, mask="FIN")]),
          Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")]),
          Phase("各向异性刻蚀硅：鳍立起来了", "Anisotropic Si etch: the fins stand up", 2.4,
                [recess(["sub"], lambda c: c.lay["iso"], TRENCH_Z)])],
         quiz("鳍越窄，对器件有什么好处？", "What does a narrower fin buy?",
              [("栅从两侧把整个鳍耗尽，短沟道效应更小", "Both side gates deplete the whole fin: fewer short-channel effects"),
               ("电阻更小", "Lower resistance"), ("更容易制造", "Easier to make"), ("Vt 更高", "Higher Vt")], 0,
              "静电长度 λ ∝ √(Wfin·EOT)：鳍越薄，λ 越小，栅对沟道的控制越强。可在“工艺参数”里拖动鳍宽试试。",
              "The scale length λ ∝ √(Wfin·EOT): thinner fins mean smaller λ and stronger gate control. Try the fin-width slider.")),

    # ---- STI 填充 + CMP：用氧化物把鳍之间的沟填满并磨平 ----
    # 鳍之间的氧化物就是 STI (浅沟槽隔离)，把相邻的鳍、相邻的晶体管隔开。
    # deposit(..., top=0.45) 表示把氧化物一直填到 z = 0.45；cmp(要磨的层, 高度) 再磨到氮化硅顶。
    Step("fin_sti", ("STI 填充 + CMP", "STI fill + CMP"),
         ("用可流动氧化物 (FCVD) 把鳍之间又窄又深的缝隙填满，再用 CMP 磨平、停在氮化硅上。",
          "Flowable CVD oxide fills the narrow, deep gaps between the fins; CMP then planarises it and "
          "stops on the nitride."),
         [("填充", "Fill", lambda c: "FCVD SiO2 + 蒸汽退火 / steam anneal"),
          ("CMP 停止层", "CMP stop", lambda c: "Si3N4")],
         [Phase("可流动氧化物填缝", "Flowable oxide gap-fill", 1.8,
                [deposit("sti", "sti_ox", top=0.45, particles=("depo", (0.8, 0.85, 0.95, 1)))]),
          Phase("CMP 停在氮化硅上", "CMP stops on the nitride", 2.2, [cmp(["sti"], NITRIDE_TOP)])],
         quiz("鳍间填充为什么改用“可流动”氧化物？", "Why use flowable oxide between the fins?",
              [("缝隙深宽比极高，普通 CVD 会留下空洞", "The gaps are so deep and narrow that normal CVD leaves voids"),
               ("更便宜", "Cheaper"), ("导电", "It conducts"), ("不需要退火", "No anneal needed")], 0,
              "FCVD 先以液态流进缝里，再经退火固化成 SiO2，能无空洞地填满深宽比 > 10 的缝隙。",
              "FCVD flows in as a liquid and is then cured into SiO2, filling aspect ratios above 10 without voids.")),

    # ---- 去硬掩膜 + 鳍露出 (STI 回刻) ----
    # 把鳍顶的氮化硅和垫氧去掉，再把 STI 氧化物往下刻到 FIN_REVEAL，鳍的上半段露出来。
    # 露出的这一段将被栅三面包住，就是晶体管的沟道；露得越高，每条鳍能通过的电流越大。
    # 这里用 cmp(..., pad=False) 来表现“整体往下降低到某个高度”。
    Step("fin_reveal", ("去硬掩膜 + 鳍露出 (STI 回刻)", "Hard-mask strip + fin reveal"),
         ("去掉氮化硅和垫氧后，把 STI 氧化物回刻约 40 nm，鳍的上半段露出来，这一段将来就是沟道。"
          "露出的鳍高 Hfin 决定了每个鳍的有效宽度 W = 2·Hfin + Wfin。",
          "After the nitride and pad oxide are stripped, the STI oxide is recessed by ~40 nm so the upper "
          "part of each fin is exposed: that part becomes the channel. The revealed height Hfin sets the "
          "effective width per fin, W = 2·Hfin + Wfin."),
         [("露出鳍高 Hfin", "Revealed Hfin", lambda c: "≈ 42 nm"),
          ("有效宽度 Wn", "Effective Wn", fin_text)],
         [Phase("去除氮化硅 + 垫氧", "Strip nitride + pad oxide", 1.4, [strip("nitride"), strip("padox")]),
          Phase("STI 回刻，露出鳍", "Recess the STI, reveal the fins", 2.0,
                [cmp(["sti"], FIN_REVEAL, pad=False)])],
         quiz("FinFET 的有效沟道宽度怎么算？", "How is the effective width of a FinFET computed?",
              [("鳍数 × (2·Hfin + Wfin)", "Number of fins × (2·Hfin + Wfin)"), ("只算鳍宽", "Fin width only"),
               ("等于栅长", "Equal to the gate length"), ("可以任意设计", "Any value you like")], 0,
              "电流沿鳍的两个侧面和顶面流动；宽度只能按整数个鳍“量子化”地增加。",
              "Current flows along both sidewalls and the top; the width can only grow in whole fins."),
         ),

    # ---- N 阱：PMOS 要做在 N 型硅里 ----
    # 先光刻只露出 PMOS 区，再注入磷。
    replace(_S["nwell_litho"], title=("N 阱光刻", "N-well lithography")),
    # implant_solids 把离子注入画成 _well_solids 给出的形状 (只进入硅，不进氧化物)；
    # 退火后用 replace_layer 把“刚注入的区域”换成正式的“N 阱”层，strip(..., "fade") 让临时层淡出消失。
    Step("fin_well", ("阱注入 + 穿通阻挡注入", "Well + punch-through-stop implants"),
         ("对 PMOS 区注入磷形成 N 阱。另外在鳍底部 (STI 表面附近) 做一次“穿通阻挡”注入，"
          "堵住鳍下方栅控制不到的漏电通道。鳍本身保持几乎不掺杂：Vt 由金属功函数决定。",
          "Phosphorus forms the n-well under the PMOS fins. A punch-through-stop implant near the fin "
          "bottom blocks the leakage path under the fin that the gate cannot reach. The fins themselves "
          "stay almost undoped: the metal work function will set Vt."),
         [("离子", "Species", lambda c: "P+ (阱) / As (PTS)"),
          ("剂量", "Dose", lambda c: sci(c.p.nwell_dose_cm2, "cm^-2")),
          ("→ PMOS Vtp", "→ PMOS Vtp", lambda c: vt_text(c, "p"))],
         [Phase("磷离子注入 (只进入硅)", "Phosphorus implant (into silicon only)", 2.2,
                [implant_solids("nimp", "n_implant", _well_solids, (1.0, 0.85, 0.2, 1), species="P",
                                dose=lambda c: c.p.nwell_dose_cm2, energy_kev=300,
                                region=lambda c: [c.lay["nwell"]])]),
          Phase("去胶 + 退火", "Strip resist + anneal", 1.6,
                [strip("resist"),
                 replace_layer("nwell", "n_well", _well_solids, anchor=0.0, requires="nimp"),
                 strip("nimp", "fade"), anneal(1000, 10, (1.0, 0.4, 0.1))])],
         quiz("为什么 FinFET 的鳍几乎不掺杂？", "Why are FinFET fins left almost undoped?",
              [("没有随机掺杂涨落、迁移率高，Vt 由功函数决定", "No random-dopant variation, higher mobility; the work function sets Vt"),
               ("掺不进去", "Dopants can't get in"), ("为了省钱", "To save money"), ("为了导热", "For heat")], 0,
              "几十个原子大小的沟道里，杂质原子数的随机起伏会让每个管子 Vt 都不同；不掺杂就没有这个问题。",
              "In a channel only tens of atoms wide, random dopant counts would scatter Vt; undoped fins avoid that.")),

    # ---- 伪栅：牺牲氧化层 + 多晶硅 (后栅工艺，和 28 nm 平面 HKMG 一样) ----
    # 为什么先做“假栅”？后面的源漏外延和退火都很热，高 k 介质和金属栅受不了；
    # 所以先用耐热的多晶硅占住栅的位置，最后再挖掉、换成真正的 HfO2 + 金属栅。
    # 这里多晶硅要把鳍整个埋住，并磨平到 GATE_TOP，因为凹凸不平的表面没法做精细光刻。
    Step("fin_dummy_gate", ("伪栅：氧化层 + 多晶硅", "Dummy gate: oxide + poly"),
         ("在鳍表面长一层牺牲氧化层，淀积多晶硅把鳍完全埋住并 CMP 磨平。这仍是“伪栅”，最后换成 HKMG。",
          "A sacrificial oxide is grown on the fins and polysilicon buries them completely, then CMP "
          "flattens it. This is again a dummy gate that will be replaced by HKMG."),
         [("牺牲氧化层", "Sacrificial oxide", lambda c: "≈ 2 nm"),
          ("多晶硅", "Poly", lambda c: "≈ 100 nm, CMP 平坦化")],
         [Phase("牺牲氧化层", "Sacrificial oxide", 1.0,
                [deposit("gox", "gate_ox", thickness=0.03, region=_fins), anneal(800, 30, (1.0, 0.5, 0.2))]),
          Phase("淀积伪栅多晶硅并磨平", "Deposit and planarise dummy poly", 1.6,
                [deposit("poly", "poly_dummy", top=GATE_TOP, particles=("depo", (0.9, 0.6, 0.45, 1)))])],
         quiz("多晶硅淀积后为什么要先 CMP？", "Why CMP the poly before patterning the gate?",
              [("鳍让表面高低不平，光刻需要平面", "The fins make the surface bumpy; lithography needs a flat surface"),
               ("为了掺杂", "For doping"), ("减少电阻", "Lower resistance"), ("为了好看", "Looks nicer")], 0,
              "栅光刻是最精细的一层，景深只有几十纳米，必须在平坦表面上进行。",
              "The gate layer is the finest one; its depth of focus is tens of nm, so the surface must be flat.")),

    # ---- 伪栅光刻 + 刻蚀：栅条沿 y 方向，横跨 (垂直于) 沿 x 方向的鳍 ----
    replace(_S["gate_litho"],
            title=("伪栅光刻 (垂直于鳍)", "Dummy-gate lithography (across the fins)"),
            desc=("用 POLY 掩膜定义横跨鳍的栅线。栅线和鳍相互垂直：每个交叉点就是一个“三面包围”的沟道。",
                  "The POLY mask defines gate lines running across the fins. Every crossing of a gate and a "
                  "fin is a channel wrapped on three sides."),
            params=[("掩膜", "Mask", lambda c: "POLY (SADP)"),
                    ("栅长 Lg", "Gate length Lg", lambda c: f"{c.p.l_um * 1e3:.0f} nm"),
                    ("栅间距 CPP", "Gate pitch CPP", lambda c: "≈ 70-90 nm")]),
    replace(_S["gate_etch"], title=("伪栅刻蚀", "Dummy-gate etch"),
            desc=("高深宽比刻蚀多晶硅，必须一直刻到鳍之间的 STI 表面，又不能伤到鳍。",
                  "A high-aspect-ratio poly etch must reach the STI between the fins without damaging the fins.")),
    # ---- 栅侧墙：在伪栅两侧做出绝缘“小墙”，把源漏和沟道隔开一小段距离 ----
    # quiz=None 表示这一步不出题 (None 在 Python 里就是“没有”)。
    replace(_S["spacer_dep"], quiz=None),
    replace(_S["spacer_etch"],
            desc=("各向异性回刻形成栅侧墙。在 FinFET 里还要把鳍侧壁上的侧墙材料清干净，否则会挡住后面的源漏外延。",
                  "An anisotropic etch-back forms the gate spacers. In a FinFET the film must also be cleared "
                  "from the fin sidewalls, or it would block the S/D epitaxy.")),

    # ---- NMOS 源漏：把鳍刻低，再外延长出掺磷的硅 (SiP) ----
    # 为什么不像老工艺那样直接注入？几纳米宽的鳍被离子一打就损坏、很难修复，而且体积太小、电阻大。
    # 外延 (在硅晶体上按原来的晶格继续“长”晶体) 可以边长边掺杂，长出又大又导电的“抬高源漏”，
    # 还能顺便给沟道加拉应力，让电子跑得更快。
    # 动画：recess 把源漏处的鳍刻低到 SD_RECESS → add_solids 长出 _epi("n") 形状的外延块。
    Step("fin_epi_n", ("NMOS 鳍凹槽 + SiP 外延源漏", "NMOS fin recess + SiP epitaxial S/D"),
         ("把 NMOS 侧墙外的鳍刻低，再选择性外延生长原位掺磷的硅 (SiP)。外延从每个鳍上长出，"
          "相邻鳍上的外延长大后合并成一整块“抬高的源漏”，接触面积大、电阻小，还能给沟道加拉应力。" + EPI_NOTE[0],
          "The NMOS fins outside the spacers are recessed and in-situ phosphorus-doped Si (SiP) is grown "
          "selectively. The epi grows from every fin and the neighbours merge into one raised S/D block: "
          "large contact area, low resistance, and tensile strain on the channel. " + EPI_NOTE[1]),
         [("外延", "Epitaxy", lambda c: "Si:P, P ≈ 3e21 cm^-3, 650 °C"),
          ("应力", "Strain", lambda c: "拉应力 / tensile")],
         [Phase("刻低 NMOS 源漏处的鳍", "Recess the NMOS S/D fins", 1.6,
                [recess(["sub"], lambda c: _sd_fin_rects(c, "n"), SD_RECESS)]),
          Phase("SiP 外延，相邻鳍合并", "SiP epitaxy, neighbours merge", 2.2,
                [add_solids("nsd", "n_epi", _epi("n"), particles=("depo", (1.0, 0.4, 0.4, 1))),
                 anneal(650, 600, (1.0, 0.7, 0.4))])],
         quiz("FinFET 的源漏为什么用外延而不是只靠离子注入？", "Why are FinFET S/D grown by epitaxy rather than just implanted?",
              [("细鳍注入会被打成非晶且难以恢复，外延能原位高掺杂并降低电阻", "Implants amorphise thin fins; epi gives in-situ heavy doping and low resistance"),
               ("外延更便宜", "Epi is cheaper"), ("注入机太大", "Implanters are too big"), ("没有原因", "No reason")], 0,
              "几纳米宽的鳍被注入打坏后很难再结晶；外延层边长边掺杂，体积也大，接触电阻更小。",
              "A few-nm fin can't recrystallise after implant damage; epi is doped as it grows and is bulkier, lowering resistance.")),

    # ---- PMOS 源漏：同样刻低鳍，外延长出掺硼的 SiGe ----
    # 锗原子比硅大，SiGe 晶格更大，从两头把沟道“挤紧”(压应力)，空穴迁移率提高。
    # 注意 NMOS 需要“拉”、PMOS 需要“挤”，所以两种管子要分开做、用不同的外延材料。
    Step("fin_epi_p", ("PMOS 鳍凹槽 + SiGe:B 外延源漏", "PMOS fin recess + SiGe:B epitaxial S/D"),
         ("PMOS 一侧同样刻低鳍，外延原位掺硼的 SiGe (Ge 可达 50% 以上)，对沟道施加压应力，提高空穴迁移率。"
          + EPI_NOTE[0],
          "The PMOS fins are recessed likewise and boron-doped SiGe (Ge above 50 %) is grown, compressing "
          "the channel to raise hole mobility. " + EPI_NOTE[1]),
         [("外延", "Epitaxy", lambda c: "SiGe:B, Ge ≈ 50 %"),
          ("应力", "Strain", lambda c: "压应力 / compressive"),
          ("µp", "µp", lambda c: f"{c.p.mu_p:.0f} cm²/Vs")],
         [Phase("刻低 PMOS 源漏处的鳍", "Recess the PMOS S/D fins", 1.6,
                [recess(["sub", "nwell"], lambda c: _sd_fin_rects(c, "p"), SD_RECESS)]),
          Phase("SiGe:B 外延", "SiGe:B epitaxy", 2.2,
                [add_solids("psd", "p_epi", _epi("p"), particles=("depo", (0.4, 0.5, 1.0, 1))),
                 anneal(650, 600, (1.0, 0.7, 0.4))])],
         quiz("NMOS 要拉应力、PMOS 要压应力，是因为？", "NMOS wants tension, PMOS compression, because…",
              [("应力改变能带，分别减小电子和空穴的有效质量", "Strain reshapes the bands, lightening electrons and holes respectively"),
               ("颜色不同", "Different colours"), ("工艺巧合", "Coincidence"), ("与应力无关", "Strain is irrelevant")], 0,
              "沿沟道方向的拉应力有利于电子，压应力有利于空穴，所以两种管子用不同的外延材料。",
              "Tensile strain along the channel helps electrons, compressive helps holes, hence two different epi materials.")),

    # ---- 以下步骤由 _modern.py 生成 (和 28 nm 平面 HKMG 工艺共用)，FinFET 只额外补充了“包鳍”的部分 ----
    # ILD0：淀积介质把一切埋住，CMP 磨到 GATE_TOP，刚好露出伪栅顶。
    ild0_step(GATE_TOP),
    # 去除伪栅：挖掉多晶硅和牺牲氧化层，栅槽里露出鳍的顶面和两个侧面。
    rmg_remove_step(["gate_n", "gate_p"],
                    desc=("刻掉伪栅多晶硅和牺牲氧化层。栅槽底部，鳍的顶面和两个侧面都露了出来。",
                          "The dummy poly and sacrificial oxide are etched out. At the bottom of the gate "
                          "trench the top and both sidewalls of each fin are now exposed.")),
    # HKMG：在栅槽里依次长 HfO2 高 k 介质、功函数金属，再用钨填满。
    # extra_hk / extra_wfn / extra_wfp 传入上面定义的函数，把鳍两侧壁上的薄膜也画出来 (三面包围)。
    # 高 k 让栅介质物理上更厚、漏电少，电学上却相当于很薄的氧化层；金属功函数决定 Vt。
    hkmg_step(GATE_TOP, extra_hk=_hk_wrap, extra_wfn=_wf_wrap("n"), extra_wfp=_wf_wrap("p"),
              desc=("ALD 的 HfO2 和功函数金属是“保形”的：它们像涂料一样均匀地包住鳍的顶面和两个侧面，"
                    "于是栅从三面控制沟道 (三栅)。最后用钨填满鳍之间和栅槽，CMP 磨平。Vt 由功函数决定，"
                    "可用不同厚度的功函数金属做出多种 Vt。",
                    "ALD HfO2 and the work-function metals are conformal: like paint they coat the top and both "
                    "sidewalls of each fin, so the gate controls the channel from three sides (tri-gate). "
                    "Tungsten fills the space between the fins and the trench, then CMP. The work function sets "
                    "Vt; different WF-metal thicknesses give several Vt flavours."),
              extra_params=[("包围方式", "Gate wrap", lambda c: "三面 (三栅) / 3 sides")]),
    # 接触孔：打孔到源、漏、栅上，孔底在源漏外延块上做硅化物 (_contact_silicide)，再填金属。
    contact_step(silicide_fn=_contact_silicide),
    # 第一层铜导线 (M1)：大马士革工艺 —— 先刻槽，再填铜、CMP 磨平，把各个端子连成反相器。
    copper_m1_step(),
    # 完成：总结 FinFET 相对平面管的优势，并提示学生去电学面板对比。
    done_step(("FinFET 反相器完成。在“电学特性 → Vt-L”里对比 28 nm 平面管：栅长更短 (20 nm) 而 DIBL 只有约 60 mV/V，"
               "亚阈值摆幅接近 70 mV/dec。打开 3D 载流子仿真：电子在鳍里流动，栅从三面控制它。"
               "在“工艺参数”里把鳍宽调大，DIBL 会迅速变差。",
               "The FinFET inverter is done. On Electrical → Vt-L compare with 28 nm planar: the gate is "
               "shorter (20 nm) yet DIBL is only ~60 mV/V and the swing is near 70 mV/dec. Turn on the 3D "
               "carrier view: electrons flow inside the fins under a gate that wraps three sides. Widen the "
               "fin on the Parameters tab and DIBL degrades quickly."),
              extra_params=[("鳍数 / 有效宽度", "Fins / Weff", fin_text)]),
]

# 3D 视图里的区域文字标签：(层名, 中文, 英文, 标签 x 位置, 标签 z 位置)。
REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.65),
    ("nsd", "SiP", "SiP", 4.1, 0.0),
    ("psd", "SiGe", "SiGe", 12.4, 0.0),
    ("gfill", "金属栅", "metal gate", 5.25, 0.8),
    ("cu", "Cu", "Cu", 10.25, 1.95),
]

# “工艺参数”面板的滑块：(参数名, 界面文字翻译键, 最小值, 最大值, 是否对数刻度)。
# 和平面工艺相比，多了鳍宽 tsi_nm 和 NMOS 功函数 wf_n_ev，而没有沟道掺杂 (鳍不掺杂，Vt 靠功函数调)。
# wn_um / wp_um 在这里表示“有效宽度” (鳍数 × 每条鳍的导电宽度)。
MULTIGATE_SLIDERS = [
    ("tox_nm", "p_eot", 0.5, 2.0, False),
    ("tsi_nm", "p_tfin", 3.0, 20.0, False),
    ("wf_n_ev", "p_wfn", 4.2, 4.7, False),
    ("l_um", "p_l_nm", 0.008, 0.06, False),
    ("wn_um", "p_wn_eff", 0.05, 1.0, False),
    ("wp_um", "p_wp_eff", 0.05, 1.0, False),
    ("vdd", "p_vdd", 0.4, 1.2, False),
    ("cload_ff", "p_cl_small", 0.05, 5.0, False),
]

# FLOW：把以上内容打包成一条完整工艺流程，供主程序使用。
# features：sce=短沟道效应，hkmg=高 k 金属栅，finfet=多栅 (电学模型据此改用鳍的公式)。
# layout_fn：用本文件的 finfet_layout 代替平面版图；channel_fn：载流子仿真里沟道的形状；
# carrier_ys：载流子动画只在这几条鳍的 y 范围内运动。
# defaults：典型参数初值 —— EOT 0.9 nm、鳍几乎不掺杂 (1e16)、栅长 20 nm、VDD 0.8 V、鳍宽 8 nm 等。
FLOW = Flow(
    key="finfet",
    name=("FinFET 工艺", "FinFET"),
    short=("FinFET 14nm", "FinFET 14nm"),
    node=("约 22-5 nm 代：立体硅鳍，栅三面包围沟道 + 外延源漏",
          "~22-5 nm: vertical fins wrapped on three sides + epitaxial S/D"),
    steps=STEPS,
    features=frozenset({"sce", "hkmg", "finfet"}),
    region_labels=REGION_LABELS,
    terminal_labels=locos.TERMINAL_LABELS,
    layout_fn=finfet_layout,
    sliders=MULTIGATE_SLIDERS,
    channel_fn=fin_channels,
    carrier_ys=FIN_BANDS,
    defaults=dict(tox_nm=0.9, na_cm3=1e16, nwell_dose_cm2=2e13, l_um=0.020, wn_um=0.28, wp_um=0.28,
                  vdd=0.8, cload_ff=0.5, mu_n=250.0, mu_p=200.0, wf_n_ev=4.48, wf_p_ev=4.74, tsi_nm=8.0,
                  lambda_um=0.002),
)
