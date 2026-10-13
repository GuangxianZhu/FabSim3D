"""~3 nm gate-all-around (GAA) nanosheet CMOS.

A Si/SiGe superlattice is grown, etched into stacks, and after the dummy
gate is removed the SiGe is etched away selectively: the Si sheets hang
between the source and drain and the high-k / metal gate fills in around
every sheet.  Sheets run along x; one stack per transistor, centred on the
default cut plane (y = 3.5) so the cross-section shows the sheets.

【中文说明】这个文件描述的是“约 3 nm 代 GAA (全环绕栅) 纳米片 CMOS 工艺”的完整流程。

它在整个程序里的位置：
  - 程序里每一代工艺 (LOCOS、STI、FinFET、GAA、CFET……) 都有一个这样的文件，放在 flows/ 目录下。
  - 每个文件主要由两部分组成：
      1) “数据”：一长串工艺步骤 STEPS，每一步写明标题、说明文字、参数表、动画阶段、小测验；
      2) “小函数”：告诉程序在某一步要往 3D 晶圆模型里加什么方块、刻掉什么、换什么颜色。
  - 文件最后的 FLOW 把这些东西打包成一个 Flow 对象，主程序读取它，就能一步步播放动画、
    并计算最终反相器的电学特性。

GAA 的核心思路 (物理上)：
  - 先在硅片上交替长出 “SiGe / Si / SiGe / Si …” 的薄层 (叫“超晶格”)；
  - 把这叠薄层刻成长条；
  - 最后把 SiGe 全部选择性地刻掉，硅层就像几块悬空的木板，只靠两端的源漏撑着；
  - 栅极材料 (高 k 介质 + 金属) 再钻进片与片之间的缝隙，从上下左右四面把每一片都包住。
  四面包住 = 栅对沟道的控制最强，晶体管可以做得更短而不漏电。

坐标约定 (本文件里的数字都按这个理解)：
  - x：屏幕左右方向，纳米片沿 x 方向延伸 (电流从源极沿 x 流到漏极)；
  - y：伸进屏幕的“深度”方向，也是剖面 (切开看截面) 的方向，默认在 y = 3.5 处切开；
  - z：向上；z = 0 是原始硅表面，负数在硅表面以下；
  - 单位是“显示单位”，不是真实纳米；为了看得清，竖直方向 (z) 被大大夸张了。
"""
# 下面这行让类型标注 (例如 List[Solid]) 可以写得更新式，对程序逻辑没有影响。
from __future__ import annotations

# replace(旧对象, 某字段=新值)：复制一个已有对象，只改其中几个字段。
# 本文件用它“借用”其他工艺里已经写好的步骤，只改标题/说明等，而不必整步重写。
from dataclasses import replace
from typing import List

# Solid = 3D 模型里的一块实体 (这里基本都是长方体)；rect_* 是平面矩形的运算 (取补集、取交集)。
from ..geometry import Solid, rect_complement, rect_intersect
# process_core 是“工艺引擎”：Step/Phase/Flow 用来描述流程；deposit(淀积)、recess(往下刻)、
# strip(整层去除)、cmp(磨平)、litho(光刻) 等是“动作”，每个动作会修改晶圆模型并产生动画。
from ..process_core import (DOMAIN, Flow, Phase, Step, add_solids, anneal, cmp, convert, deposit,
                            implant_solids, layout, litho, pattern, quiz, recess, replace_layer, sci,
                            spacer_span, strip, vt_text, SPACER_W, gate_span)
# 引入其他几代工艺的文件，以便复用它们的步骤 (GAA 是在它们的基础上发展来的)。
from . import finfet, locos, sti
# _modern 里是先进工艺共用的步骤 (高k金属栅、接触孔、铜互连等)，GAA/FinFET/CFET 都会用。
from ._modern import (EPI_NOTE, channel_rects, contact_step, copper_m1_step, done_step, hkmg_step,
                      ild0_step, rmg_remove_step, side_slabs)

# 把其他工艺的步骤列表做成“字典”：用步骤名字 (key) 就能取出那一步，例如 _S["nitride"]。
# 写法 {s.key: s for s in ...} 叫“字典推导式”：对列表里每个 s，生成一对 “名字 → 步骤”。
_S = {s.key: s for s in sti.STEPS}      # STI 工艺的步骤
_L = {s.key: s for s in locos.STEPS}    # LOCOS 工艺的步骤
_F = {s.key: s for s in finfet.STEPS}   # FinFET 工艺的步骤

# ---- 竖直方向 (z) 的各层高度，单位是显示单位，(下表面, 上表面) ----
# 三片硅纳米片 (将来的沟道)，从下到上；最上面一片的顶面正好在原硅表面 z = 0。
SHEETS = [(-0.5, -0.4), (-0.3, -0.2), (-0.1, 0.0)]      # Si channels, bottom to top
# 三层 SiGe 牺牲层，各自在对应硅片的正下方；最后会被刻掉，留出给栅金属填充的缝隙。
SIGE = [(-0.6, -0.5), (-0.4, -0.3), (-0.2, -0.1)]       # sacrificial SiGe below each sheet
SUB_TOP = -0.6      # 衬底 (原始硅片) 顶面：超晶格就长在它上面
STACK_Y = (2.7, 4.3)  # 纳米片叠层在 y (深度) 方向的范围，正好包住默认剖面 y = 3.5
TRENCH_Z = -0.95    # 叠层刻蚀时沟槽刻到的深度 (比叠层底部再深一点)
STI_TOP = -0.65     # STI 隔离氧化物回刻后的顶面：略低于叠层底部，让整个叠层露出来
GATE_TOP = 0.55     # 栅 (伪栅、金属栅) 的顶面高度
EPI_TOP = 0.15      # 源漏外延长到的顶面高度
WELL_BOT = -1.8     # N 阱的底部深度


def gaa_layout(p):
    """Build the top-view layout for the GAA flow.

    【中文】生成 GAA 工艺的“俯视平面布局”(哪里是有源区、栅、接触孔……)。
    先调用通用的 layout(p) 得到平面工艺的布局，再改成 GAA 需要的样子：
      - stacks：每个晶体管一条纳米片叠层，x 范围沿用原来的有源区，y 范围换成 STACK_Y；
      - iso：叠层以外的所有区域 (将来填 STI 隔离氧化物)；
      - spacer_bands：侧墙沿 y 分成三段，各自的底部高度不同 (叠层上方底在 z=0，其他地方在 STI 顶)。
    参数 p 是用户在界面上调节的工艺参数 (栅长等)。
    """
    lay = layout(p)
    # (a[0], a[1], *STACK_Y)：取有源区的 x 起止，再把 STACK_Y 的两个数“展开”接在后面，
    # 得到矩形 (x0, x1, y0, y1)。星号 * 的作用就是把一个元组拆开放进去。
    lay["stacks"] = [(a[0], a[1], *STACK_Y) for a in (lay["act_n"], lay["act_p"])]
    lay["iso"] = rect_complement(DOMAIN, lay["stacks"])
    lay["spacer_bands"] = [(1.1, STACK_Y[0], STI_TOP), (STACK_Y[0], STACK_Y[1], 0.0),
                           (STACK_Y[1], 6.5, STI_TOP)]
    return lay


def _stacks(c):
    """【中文】返回所有纳米片叠层的矩形；c 是“上下文”(当前参数 + 布局)，很多函数都以它为参数。"""
    return c.lay["stacks"]


def _wafer(c):
    """【中文】初始硅片：一整块长方体，x 0~20、y 0~8，从 z=-3 到衬底顶面 SUB_TOP。"""
    # Solid.box(x0, x1, y0, y1, z0, z1) 生成一个长方体。
    return [Solid.box(0, 20, 0, 8, -3.0, SUB_TOP)]


def _layers(zs):
    """【中文】给定若干 (z下, z上)，生成覆盖整片晶圆的薄层 (用于外延生长的动画)。

    这是“返回函数的函数”：_layers(...) 先记住 zs，返回里面的 fn；
    引擎到了动画那一步才会调用 fn(c) 真正生成方块。本文件很多地方都用这种写法。
    """
    def fn(c):
        out = []
        for z0, z1 in zs:
            s = Solid.box(0, 20, 0, 8, z0, z1)
            s.anchor = z0   # anchor：生长动画从这个高度开始“长”出来 (从层底往上长)
            out.append(s)
        return out
    return fn


def _well_solids(c) -> List[Solid]:
    """【中文】N 阱的形状：只在纳米片下方的衬底里，纳米片本身不掺杂。

    第一块：N 阱区域里，从 WELL_BOT 到沟槽底 TRENCH_Z 的一大块；
    其余：每条叠层与 N 阱重叠的部分，从沟槽底到衬底顶 SUB_TOP (叠层“脚下”那段硅)。
    """
    nw = c.lay["nwell"]
    out = [Solid.box(nw[0], nw[1], nw[2], nw[3], WELL_BOT, TRENCH_Z)]
    for st in c.lay["stacks"]:
        r = rect_intersect(st, nw)
        if r:   # 有重叠才加 (没有重叠时 rect_intersect 返回 None)
            out.append(Solid.box(r[0], r[1], r[2], r[3], TRENCH_Z, SUB_TOP))
    return out


def _sd_rects(c, key):
    """【中文】源极/漏极所在的两块矩形：有源区里、栅+侧墙以外的左右两段。

    key 是 "n" 或 "p"，分别对应 NMOS、PMOS。spacer_span 给出“栅加上两侧侧墙”的 x 范围。
    """
    act = c.lay["act_" + key]
    g = spacer_span(c, "g" + key)
    return [(act[0], g[0], *STACK_Y), (g[1], act[1], *STACK_Y)]


def _inner_zones(c):
    """Under the spacers, where the SiGe is recessed and replaced by inner spacers.

    【中文】侧墙正下方的区域 (栅两侧各一条宽 SPACER_W 的带)：这里的 SiGe 会被横向挖掉一点，
    再填入氮化物，变成“内侧墙”。NMOS 和 PMOS 的栅各有左右两条。
    """
    out = []
    for key in ("gn", "gp"):
        g = gate_span(c, key)
        out += [(g[0] - SPACER_W, g[0], *STACK_Y), (g[1], g[1] + SPACER_W, *STACK_Y)]
    return out


def _epi(key):
    """【中文】源漏外延块的形状：在源漏区域从 STI 顶长到 EPI_TOP，y 方向比叠层两边各宽 0.1
    (真实外延会往外鼓出一点)。key = "n" 或 "p"。"""
    def fn(c):
        out = []
        for r in _sd_rects(c, key):
            s = Solid.box(r[0], r[1], r[2] - 0.1, r[3] + 0.1, STI_TOP, EPI_TOP)
            s.anchor = STI_TOP
            out.append(s)
        return out
    return fn


def gap_films(gaps, key=None, inset=0.0, thickness=None):
    """Films inside the gaps left by the released SiGe, under the gate.
    thickness=None fills the gap minus `inset` on both faces; otherwise two
    films of `thickness` line the top and bottom faces.

    【中文】SiGe 被刻掉后，片与片之间留下缝隙；这个函数生成“缝隙里的薄膜”(只在栅下面)。
      - thickness 不给 (None)：把缝隙上下各缩进 inset 后整块填满 (用于功函数金属填缝)；
      - thickness 给了：在缝隙的上表面和下表面各贴一层这么厚的膜 (用于高 k 介质 HfO2 贴壁)。
    key 选择只做 NMOS ("n") 或 PMOS ("p") 的栅，None 表示两个都做。
    这个函数没有下划线开头，CFET 等其他文件也可以用。
    """
    def fn(c):
        out = []
        for r in channel_rects(c, key):
            for z0, z1 in gaps:
                if thickness is None:
                    zs = [(z0 + inset, z1 - inset)]
                else:
                    zs = [(z0, z0 + thickness), (z1 - thickness, z1)]
                for a, b in zs:
                    out.append(Solid.box(r[0], r[1], STACK_Y[0], STACK_Y[1], a, b))
        return out
    return fn


def _wrap(key, offset, t, z0):
    """【中文】叠层左右两个侧面 (朝 y 方向) 上的竖直薄膜，从 z0 到 0，厚 t，离侧壁 offset。
    用来画栅材料“包住叠层侧面”的部分。lambda 是一种一行写完的小函数。"""
    return lambda c: side_slabs(channel_rects(c, key), [STACK_Y], z0, 0.0, offset, t)


def _hk_extra(c):
    """【中文】高 k 介质 (HfO2) 除了正常淀积以外额外要画的部分：
    缝隙上下壁各 0.02 厚的膜 + 叠层侧面 0.03 厚的膜 → 每片纳米片四面都被 HfO2 包住。"""
    return gap_films(SIGE, thickness=0.02)(c) + _wrap(None, 0.0, 0.03, STI_TOP)(c)


def _wf_extra(key):
    """【中文】功函数金属额外要画的部分：填满缝隙 (留出 HfO2 的 0.02) + 贴在 HfO2 外侧的侧面膜。
    功函数金属决定晶体管的阈值电压，NMOS 和 PMOS 用不同的金属，所以按 key 分开。"""
    return lambda c: gap_films(SIGE, key, inset=0.02)(c) + _wrap(key, 0.03, 0.05, STI_TOP + 0.03)(c)


def _contact_silicide(c):
    """【中文】接触孔底部的金属硅化物 (降低金属和源漏之间的接触电阻)。
    只给源漏接触做，名字以 "g_" 开头的是栅接触，跳过。"""
    return [Solid.box(r[0], r[1], r[2], r[3], EPI_TOP - 0.03, EPI_TOP + 0.02)
            for k, r in c.lay["contacts"].items() if not k.startswith("g_")]


def sheet_channels(lay):
    """【中文】告诉“载流子仿真/电学显示”沟道在哪里：每个晶体管 3 片纳米片，各返回一个
    ("n" 或 "p", 方块)。方块比真实纳米片稍微大一点点 (0.01~0.05)，方便显示时盖住硅片。"""
    out = []
    for key in ("n", "p"):
        g = lay["g" + key]
        for z0, z1 in SHEETS:
            out.append((key, Solid.box(g[0] - 0.05, g[1] + 0.05, STACK_Y[0] - 0.02, STACK_Y[1] + 0.02,
                                       z0 - 0.01, z1 + 0.01)))
    return out


def sheet_text(c) -> str:
    """【中文】参数表里显示的“有效宽度”文字。
    一片纳米片的电流沿它的周长流动：上下两面 (2 × 片宽 30 nm) 加左右两侧 (2 × 片厚)，
    即 2 × (片厚 + 30)；共 3 片，所以 Weff ≈ 3 × 2 × (片厚 + 30) nm，再换算成 µm。
    f"..." 是“格式化字符串”，大括号里的表达式会被算出来填进去，:.0f 表示保留 0 位小数。"""
    return f"3 × 2 × ({c.p.tsi_nm:.0f} + 30) nm ≈ {3 * 2 * (c.p.tsi_nm + 30) / 1e3:.2f} µm"


# ============================================================================
# 工艺步骤列表 STEPS：程序按这个顺序一步步播放。
# 每个 Step(...) 的参数依次是：
#   key (内部名字)、title (中文, 英文标题)、desc (中文, 英文说明)、
#   params (参数表：每行 (中文名, 英文名, 计算显示值的小函数))、
#   phases (动画阶段：每个 Phase(中文, 英文, 秒数, [动作…]))、
#   quiz (小测验，可省略)、最后可选的掩膜名字。
# 写法 lambda c: "<100>" 是一个“小函数”，界面显示参数时才调用它得到文字。
# replace(_S["xxx"], ...) 表示“沿用 STI 工艺里的 xxx 步骤，只改括号里写出的部分”。
# ============================================================================
STEPS = [
    # 第 1 步：准备 P 型硅片。所有工艺都从一片干净的单晶硅片开始。
    Step("wafer", ("P 型硅衬底", "p-type silicon wafer"),
         ("300 mm <100> P 型硅片。GAA (全环绕栅) 晶体管把沟道做成几片水平悬空的硅纳米片，"
          "栅从上、下、左、右四面把每一片完全包住。三星 3 nm (2022) 和台积电 2 nm 开始量产。",
          "A 300 mm <100> p-type wafer. A gate-all-around (GAA) transistor uses a few horizontal, "
          "suspended silicon nanosheets as the channel, and the gate surrounds every sheet on all four "
          "sides. Samsung 3 nm (2022) and TSMC 2 nm brought it to production."),
         [("晶向", "Orientation", lambda c: "<100>"),
          ("硅片直径", "Wafer diameter", lambda c: "300 mm")],
         [Phase("准备硅片", "Wafer preparation", 1.0, [replace_layer("sub", "p_sub", _wafer)])],
         quiz("GAA 比 FinFET 多控制了沟道的哪一面？", "Which side of the channel does GAA add over a FinFET?",
              [("底面 (栅从四面包围)", "The bottom (gate on all four sides)"), ("没有区别", "No difference"),
               ("只控制顶面", "Only the top"), ("源漏端面", "The S/D ends")], 0,
              "FinFET 的鳍底连着衬底，栅只能包三面；纳米片悬空后，栅可以从下面也包住它。",
              "A fin's bottom is tied to the substrate so the gate wraps only three sides; a suspended sheet is wrapped from below too.")),

    # 第 2 步：Si / SiGe 超晶格外延。
    # 物理上：一层 SiGe、一层 Si 交替地“长”上去 (外延 = 延续下面晶体的排列方式生长)，共三对。
    # 为什么要这样：硅层将来是沟道；SiGe 像“临时支架”先把硅片撑住，最后再被选择性刻掉，
    # 腾出缝隙让栅钻进去。SiGe 和 Si 晶格很接近，所以能长成完美单晶；又能被选择性刻蚀。
    # 下面的 [Phase(...) for i in range(3)] 是“列表推导式”：i 取 0、1、2，生成 3 个动画阶段，
    # 每个阶段先长第 i 层 SiGe，再长第 i 片硅。
    Step("superlattice", ("Si / SiGe 超晶格外延", "Si / SiGe superlattice epitaxy"),
         ("在硅片上交替外延生长 SiGe 和 Si，各约 5-10 nm，共三对。硅层将来是沟道纳米片，"
          "SiGe 是“牺牲层”：它暂时撑住硅片，最后会被选择性地刻掉，给栅留出空间。",
          "SiGe and Si are grown alternately, each 5-10 nm, three pairs in all. The Si layers will be the "
          "channel nanosheets; the SiGe is sacrificial: it holds the sheets up for now and will be etched "
          "away selectively to make room for the gate."),
         [("方法", "Method", lambda c: "RPCVD 外延, 600 °C"),
          ("SiGe", "SiGe", lambda c: "Ge ≈ 25-30 %"),
          ("纳米片厚度", "Sheet thickness", lambda c: f"{c.p.tsi_nm:.1f} nm")],
         [Phase(f"外延第 {i + 1} 对 SiGe / Si", f"Epitaxy, SiGe / Si pair {i + 1}", 1.2,
                [add_solids("sige", "sige", _layers([SIGE[i]])), add_solids("sheet", "si_fin", _layers([SHEETS[i]]))])
          for i in range(3)],
         quiz("为什么牺牲层要用 SiGe？", "Why is the sacrificial layer SiGe?",
              [("与 Si 晶格匹配可以外延，又能被选择性地刻掉", "It grows epitaxially on Si yet can be etched away selectively"),
               ("SiGe 导电更好", "SiGe conducts better"), ("SiGe 更便宜", "SiGe is cheaper"),
               ("SiGe 是绝缘体", "SiGe is an insulator")], 0,
              "SiGe 晶格和 Si 接近，能长出完美的单晶叠层；某些刻蚀液对 SiGe 的刻蚀速率是 Si 的上百倍。",
              "SiGe is close enough to Si to grow perfect crystal stacks, and some etchants attack it 100× faster than Si.")),

    # 第 3 步 (借用 LOCOS 工艺)：长一层很薄的“垫氧化层”，缓冲上面氮化硅对硅的应力。这里只改厚度。
    replace(_L["padox"], params=[("厚度", "Thickness", lambda c: "≈ 5 nm")]),
    # 第 4 步 (借用 STI 工艺)：淀积氮化硅 (Si3N4) 硬掩膜。
    # 作用 1：刻叠层时保护要留下的部分；作用 2：之后 CMP 磨氧化物时作为“停止层”。
    replace(_S["nitride"],
            desc=("淀积 Si3N4 硬掩膜，用来刻出纳米片“叠层鳍”，之后作 STI CMP 停止层。",
                  "A Si3N4 hard mask for etching the nanosheet stacks; later the STI CMP stop.")),

    # 第 5 步：叠层光刻。用 EUV 光把“叠层长条”的图形印到光刻胶上 (像用光拍照片一样转印图案)。
    # 为什么用 EUV：图形只有几十纳米宽，波长越短越能印出细小的图形。
    # litho(_stacks, mask="ACTIVE")：在 _stacks 给出的位置留下光刻胶，掩膜名叫 ACTIVE (有源区)。
    Step("stack_litho", ("叠层图形光刻 (EUV)", "Stack patterning (EUV)"),
         ("用 EUV (13.5 nm 极紫外光) 一次曝光出纳米片叠层的图形。和鳍相比，纳米片更宽 (约 15-45 nm)，"
          "宽度可以连续设计，不再是一个个“量子化”的鳍。",
          "EUV (13.5 nm) prints the nanosheet stacks in one exposure. Sheets are wider than fins "
          "(~15-45 nm) and their width can be chosen continuously instead of in whole fins."),
         [("掩膜", "Mask", lambda c: "ACTIVE / RX (EUV)"),
          ("光源", "Source", lambda c: "EUV 13.5 nm, NA 0.33"),
          ("片宽", "Sheet width", lambda c: "≈ 30 nm")],
         litho(_stacks, mask="ACTIVE"),
         quiz("EUV 光刻的波长是多少？", "What is the EUV wavelength?",
              [("13.5 nm", "13.5 nm"), ("193 nm", "193 nm"), ("248 nm", "248 nm"), ("365 nm", "365 nm")], 0,
              "EUV 由锡等离子体发出，只能在真空中用多层膜反射镜传输。",
              "EUV comes from a tin plasma and must travel in vacuum via multilayer mirrors."),
         ("有源区", "ACTIVE")),

    # 第 6 步：叠层刻蚀。先把硬掩膜按光刻胶图形刻开，去掉光刻胶，
    # 再用“各向异性”(只往下、不往旁边) 的等离子刻蚀，把叠层以外 (lay["iso"]) 的
    # Si、SiGe 和一段衬底一起刻到 TRENCH_Z，留下一条条竖立的“叠层鳍”。
    Step("stack_etch", ("叠层刻蚀", "Stack etch"),
         ("刻穿硬掩膜后，各向异性刻蚀把整个 Si/SiGe 叠层连同下面一段硅一起刻成条状“叠层鳍”。",
          "After the hard mask is opened, an anisotropic etch cuts the whole Si/SiGe stack and some "
          "silicon below it into stack-shaped fins."),
         [("刻蚀", "Etch", lambda c: "HBr / Cl2 RIE"),
          ("叠层数", "Sheets", lambda c: "3")],
         [Phase("刻蚀硬掩膜", "Etch the hard mask", 1.4,
                [pattern("nitride", _stacks, mask="ACTIVE"), pattern("padox", _stacks, particles=False, mask="ACTIVE")]),
          Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")]),
          Phase("刻蚀 Si/SiGe 叠层", "Etch the Si/SiGe stack", 2.2,
                [recess(["sheet", "sige", "sub"], lambda c: c.lay["iso"], TRENCH_Z)])],
         quiz("叠层刻蚀最难的地方是？", "What is hardest about the stack etch?",
              [("Si 和 SiGe 要刻得一样快，侧壁才会笔直", "Si and SiGe must etch at the same rate for straight sidewalls"),
               ("需要很高温度", "It needs very high temperature"), ("要用湿法", "It must be wet"),
               ("不需要掩膜", "It needs no mask")], 0,
              "如果某一层刻得快，侧壁就会出现锯齿，后面的栅和内侧墙都会受影响。",
              "If one layer etches faster the sidewall becomes jagged, upsetting the gate and inner spacers.")),

    # 第 7 步：STI (浅沟槽隔离)。在沟槽里填满氧化物 (绝缘体)，把相邻晶体管电学上隔开。
    # 四个阶段：填氧化物 → CMP 磨平 (停在氮化硅上) → 去掉氮化硅/垫氧 → 把氧化物回刻到 STI_TOP。
    # 为什么回刻到叠层底部以下：整条叠层都要露出来，栅才能从侧面和下面包住每一片。
    Step("stack_sti", ("STI 填充 + CMP + 回刻", "STI fill, CMP and recess"),
         ("填氧化物、CMP 停在氮化硅上，去掉硬掩膜后把 STI 回刻到叠层底部以下，整个纳米片叠层露出来。",
          "Oxide fill, CMP onto the nitride, hard-mask strip, then the STI is recessed below the stack so "
          "the whole nanosheet stack stands free."),
         [("填充", "Fill", lambda c: "FCVD SiO2"),
          ("回刻后", "After recess", lambda c: "叠层完全露出 / stack fully exposed")],
         [Phase("氧化物填充", "Oxide fill", 1.6,
                [deposit("sti", "sti_ox", top=0.45, particles=("depo", (0.8, 0.85, 0.95, 1)))]),
          Phase("CMP 停在氮化硅上", "CMP onto the nitride", 1.8, [cmp(["sti"], 0.18)]),
          Phase("去硬掩膜", "Strip the hard mask", 1.2, [strip("nitride"), strip("padox")]),
          Phase("STI 回刻，叠层露出", "Recess the STI, expose the stack", 1.6, [cmp(["sti"], STI_TOP, pad=False)])],
         quiz("STI 为什么要回刻到叠层底部以下？", "Why recess the STI below the stack?",
              [("让栅能从侧面和下面包住每一片", "So the gate can reach the sides and bottom of every sheet"),
               ("为了好看", "Looks nicer"), ("减少电容", "Less capacitance"), ("为了掺杂", "For doping")], 0,
              "叠层必须完全露出，后面的伪栅、内侧墙和金属栅才能包住所有纳米片。",
              "The stack must be fully exposed so the dummy gate, inner spacers and metal gate can surround every sheet.")),

    # 第 8 步 (借用 STI 工艺)：N 阱光刻。用光刻胶盖住 NMOS 区，只露出要做 PMOS 的区域。
    replace(_S["nwell_litho"], title=("N 阱光刻", "N-well lithography")),
    # 第 9 步：阱注入。把磷离子打进 PMOS 下方的衬底，形成 N 阱 (PMOS 需要坐在 N 型区域里)。
    # 纳米片本身不掺杂 (栅四面包围，已经足够控制沟道，不掺杂还能减少杂质对电子的散射)。
    # 第一个阶段注入离子 (黄色)，第二个阶段去胶 + 退火：退火让离子“安顿”到晶格里，变成真正的 N 阱。
    Step("gaa_well", ("阱注入 (纳米片下方)", "Well implant (below the sheets)"),
         ("阱只做在纳米片下方的衬底里，并加一层“底部隔离”注入，防止电流从最下面那片纳米片下方的衬底漏走。"
          "纳米片本身不掺杂。",
          "The well only goes into the substrate below the sheets, with a bottom-isolation implant that "
          "stops current leaking through the substrate under the lowest sheet. The sheets stay undoped."),
         [("离子", "Species", lambda c: "P+ (阱) / B (底部隔离)"),
          ("剂量", "Dose", lambda c: sci(c.p.nwell_dose_cm2, "cm^-2")),
          ("→ PMOS Vtp", "→ PMOS Vtp", lambda c: vt_text(c, "p"))],
         [Phase("磷离子注入 (衬底)", "Phosphorus implant (substrate)", 2.0,
                [implant_solids("nimp", "n_implant", _well_solids, (1.0, 0.85, 0.2, 1), species="P",
                                dose=lambda c: c.p.nwell_dose_cm2, energy_kev=350,
                                region=lambda c: [c.lay["nwell"]])]),
          Phase("去胶 + 退火", "Strip resist + anneal", 1.6,
                [strip("resist"), replace_layer("nwell", "n_well", _well_solids, anchor=0.0, requires="nimp"),
                 strip("nimp", "fade"), anneal(950, 10, (1.0, 0.4, 0.1))])],
         quiz("GAA 的热预算为什么特别紧？", "Why is the GAA thermal budget so tight?",
              [("高温会让 Ge 扩散进 Si 纳米片，层界面变模糊", "Heat makes Ge diffuse into the Si sheets and blurs the layers"),
               ("硅片会熔化", "The wafer would melt"), ("光刻胶怕热", "Resist hates heat"), ("没有原因", "No reason")], 0,
              "Si/SiGe 界面一旦互扩散，后面的选择性刻蚀就分不清哪层该留、哪层该去。",
              "Once Si and SiGe intermix, the selective etch can no longer tell which layer to keep.")),

    # 第 10 步：伪栅 (假栅)。先用多晶硅做一个“占位”的栅，等源漏这些高温步骤做完后再换成真正的金属栅
    # (“后栅工艺”)。原因：高 k 介质和金属栅怕高温，所以最后才放进去。
    Step("gaa_dummy_gate", ("伪栅：氧化层 + 多晶硅", "Dummy gate: oxide + poly"),
         ("在叠层上长牺牲氧化层，淀积多晶硅把叠层完全埋住并磨平。",
          "A sacrificial oxide is formed on the stacks and polysilicon buries them, then it is planarised."),
         [("多晶硅", "Poly", lambda c: "≈ 100 nm, CMP 平坦化")],
         [Phase("牺牲氧化层", "Sacrificial oxide", 1.0,
                [deposit("gox", "gate_ox", thickness=0.03, region=_stacks)]),
          Phase("淀积伪栅多晶硅并磨平", "Deposit and planarise dummy poly", 1.6,
                [deposit("poly", "poly_dummy", top=GATE_TOP, particles=("depo", (0.9, 0.6, 0.45, 1)))])]),

    # 第 11 步 (借用 FinFET)：伪栅光刻，画出横跨叠层的栅线条；栅线条的宽度就是栅长 Lg。
    replace(_F["gate_litho"],
            title=("伪栅光刻 (横跨叠层)", "Dummy-gate lithography (across the stacks)"),
            desc=("用 EUV 定义横跨叠层的伪栅线，栅长约 12-16 nm。",
                  "EUV defines the dummy gate lines across the stacks; the gate length is ~12-16 nm."),
            params=[("掩膜", "Mask", lambda c: "POLY (EUV)"),
                    ("栅长 Lg", "Gate length Lg", lambda c: f"{c.p.l_um * 1e3:.0f} nm"),
                    ("栅间距 CPP", "Gate pitch CPP", lambda c: "≈ 45-50 nm")]),
    # 第 12 步 (借用 STI)：刻蚀多晶硅，只留下栅线条。
    replace(_S["gate_etch"], title=("伪栅刻蚀", "Dummy-gate etch")),
    # 第 13、14 步 (借用 STI)：淀积并刻蚀“侧墙”—— 栅两侧的绝缘小墙，让源漏离栅保持一点距离。
    # quiz=None 表示这一步不出测验题。
    replace(_S["spacer_dep"], quiz=None),
    replace(_S["spacer_etch"]),

    # 第 15 步：源漏凹槽 + 内侧墙 (GAA 特有)。
    # 阶段 1：把侧墙外面 (将来源漏的位置) 的整个叠层刻掉，露出每层 Si/SiGe 的端面。
    # 阶段 2：从端面把 SiGe 横向刻进去一小段 (侧墙正下方)，再填入氮化物 = “内侧墙”。
    # 为什么需要内侧墙：之后 SiGe 会被换成栅金属，如果没有内侧墙，片与片之间的栅金属
    # 离源漏只有几纳米，会产生很大的寄生电容甚至短路。
    # convert("sige", "inner", "spacer", _inner_zones)：把 _inner_zones 范围内的 SiGe
    # 转成名叫 "inner" 的新层，材料改成侧墙材料。
    Step("inner_spacer", ("源漏凹槽 + 内侧墙", "S/D recess + inner spacers"),
         ("把侧墙外的整个叠层刻到底，露出 Si/SiGe 的端面。然后从侧面把 SiGe 横向回刻一小段，"
          "再用氮化物填回去，形成“内侧墙”：它把将来的金属栅和源漏隔开，减小寄生电容。",
          "The whole stack outside the spacers is etched down, exposing the Si/SiGe ends. The SiGe is "
          "then recessed sideways a little and refilled with nitride to form inner spacers, which keep "
          "the future metal gate away from the source/drain and cut parasitic capacitance."),
         [("凹槽深度", "Recess depth", lambda c: "穿透叠层 / through the stack"),
          ("SiGe 横向回刻", "Lateral SiGe recess", lambda c: "≈ 5-8 nm"),
          ("内侧墙", "Inner spacer", lambda c: "SiN / SiOCN, ALD")],
         [Phase("刻穿侧墙外的叠层", "Etch through the stack outside the spacers", 1.8,
                [recess(["sheet", "sige", "sub", "nwell"], lambda c: _sd_rects(c, "n") + _sd_rects(c, "p"),
                        STI_TOP)]),
          Phase("SiGe 横向回刻 + 内侧墙填充", "Lateral SiGe recess + inner-spacer fill", 2.0,
                [convert("sige", "inner", "spacer", _inner_zones)])],
         quiz("内侧墙的作用是？", "What do inner spacers do?",
              [("隔开金属栅和源漏，减小寄生电容和漏电", "Separate the metal gate from the S/D, cutting parasitics and leakage"),
               ("导电", "Conduct current"), ("掺杂沟道", "Dope the channel"), ("支撑硅片", "Support the wafer")], 0,
              "纳米片之间的栅金属离源漏只有几纳米，没有内侧墙就会产生很大的栅-源漏电容甚至短路。",
              "Between the sheets the gate metal is only nm from the S/D; without inner spacers the capacitance (or a short) would be large.")),

    # 第 16 步：源漏外延。从每片硅的端面长出高掺杂的源漏：NMOS 用掺磷硅 (电子多)，
    # PMOS 用掺硼 SiGe (空穴多，而且 SiGe 会挤压沟道、让空穴跑得更快)。
    # 三片纳米片的两端被同一块外延连在一起 → 三片“并联”，电流加倍再加倍。
    # 最后的 anneal(...) 是一次退火，激活掺杂原子。
    Step("gaa_epi", ("源漏外延 (SiP / SiGe:B)", "S/D epitaxy (SiP / SiGe:B)"),
         ("从每一片纳米片的端面外延生长源漏：NMOS 用掺磷 Si，PMOS 用掺硼 SiGe。各片外延合并成一块，"
          "把三片纳米片在两端并联起来。" + EPI_NOTE[0],
          "Source/drain epi grows from the end of every sheet: P-doped Si for NMOS, B-doped SiGe for PMOS. "
          "The growth merges into one block that ties the three sheets together at each end. " + EPI_NOTE[1]),
         [("NMOS", "NMOS", lambda c: "Si:P"),
          ("PMOS", "PMOS", lambda c: "SiGe:B")],
         [Phase("NMOS：SiP 外延", "NMOS: SiP epitaxy", 1.8,
                [add_solids("nsd", "n_epi", _epi("n"), particles=("depo", (1.0, 0.4, 0.4, 1)))]),
          Phase("PMOS：SiGe:B 外延", "PMOS: SiGe:B epitaxy", 1.8,
                [add_solids("psd", "p_epi", _epi("p"), particles=("depo", (0.4, 0.5, 1.0, 1))),
                 anneal(650, 600, (1.0, 0.7, 0.4))])],
         quiz("三片纳米片在电路上是怎样连接的？", "How are the three sheets connected electrically?",
              [("并联：两端共用源漏", "In parallel: they share the source and drain"),
               ("串联", "In series"), ("互不相连", "Not connected"), ("只用最上面一片", "Only the top one is used")], 0,
              "源漏外延把各片两端连在一起，电流分三路同时流过，有效宽度是三片之和。",
              "The S/D epi joins the sheet ends, so current flows through all three in parallel and the widths add.")),

    # 第 17 步 (共用步骤)：淀积 ILD0 (第 0 层层间绝缘氧化物) 并磨平到伪栅顶，把源漏埋起来保护好。
    ild0_step(GATE_TOP),
    # 第 18 步 (共用步骤 + GAA 特有的额外阶段)：去除伪栅，然后“纳米片释放”。
    # 用只刻 SiGe、几乎不刻 Si 的选择性刻蚀把栅下剩余的 SiGe 全挖掉 → 硅片悬空。
    # 这就是最开始要长 SiGe 牺牲层的原因。strip("sige") 把整个 SiGe 层从模型里去掉。
    rmg_remove_step(["gate_n", "gate_p"],
                    title=("去除伪栅 + 纳米片释放", "Dummy-gate removal + sheet release"),
                    desc=("掏空伪栅后，栅槽里露出叠层。再用对 SiGe 选择比极高的刻蚀把剩下的 SiGe 全部挖掉："
                          "硅纳米片像几块悬空的木板一样，只靠两端的源漏支撑，片与片之间留出空隙。",
                          "With the dummy gate gone the stack is exposed in the trench. A highly SiGe-selective "
                          "etch then removes the remaining SiGe: the silicon sheets hang like planks held only "
                          "by the source/drain at their ends, with gaps between them."),
                    extra_phase=Phase("选择性刻蚀 SiGe：纳米片悬空", "Selective SiGe etch: sheets released", 2.2,
                                      [strip("sige")])),
    # 第 19 步 (共用步骤)：高 k 介质 + 金属栅 (HKMG)。
    # ALD (原子层淀积) 一次只长一层原子，气体能钻进几纳米的缝隙，所以能把每片都包住。
    # extra_hk / extra_wfn / extra_wfp 是上面定义的函数，负责画出缝隙里和侧面上的那部分膜。
    hkmg_step(GATE_TOP, extra_hk=_hk_extra, extra_wfn=_wf_extra("n"), extra_wfp=_wf_extra("p"),
              desc=("ALD 的气体能钻进片与片之间几纳米的缝隙：HfO2 先包住每一片的上下左右四面，"
                    "功函数金属再把缝隙填满，最后钨填满栅槽并 CMP。栅从四面包住每一片纳米片——“全环绕栅”。",
                    "ALD precursors creep into the few-nm gaps: HfO2 coats every sheet on all four sides, the "
                    "work-function metal fills the gaps, then tungsten fills the trench and CMP. The gate now "
                    "surrounds every sheet: gate-all-around."),
              extra_params=[("包围方式", "Gate wrap", lambda c: "四面 (全环绕) / all 4 sides")]),
    # 第 20 步 (共用步骤)：接触孔。在绝缘层上开孔直达源漏/栅，底部做硅化物降低电阻，再用钨填满。
    contact_step(silicide_fn=_contact_silicide),
    # 第 21 步 (共用步骤)：第一层铜互连 (M1)，把各个接触孔按反相器电路连起来。
    copper_m1_step(),
    # 最后一步：完成，提示用户去看剖面、电学特性和载流子仿真。
    done_step(("GAA 纳米片反相器完成。把剖面放在 y = 3.5 可以看到三片纳米片被金属栅上下夹住。"
               "在“电学特性”里对比 FinFET：栅长更短 (15 nm)，DIBL 却更小、亚阈值摆幅接近 60 mV/dec 的理论极限。"
               "打开 3D 载流子仿真看电子在纳米片中流动。",
               "The GAA nanosheet inverter is done. With the cut at y = 3.5 you can see the three sheets "
               "sandwiched by the metal gate. Compared with the FinFET the gate is shorter (15 nm) yet DIBL "
               "is smaller and the swing approaches the 60 mV/dec limit. Turn on the 3D carrier view to see "
               "electrons flowing in the sheets."),
              extra_params=[("纳米片 / 有效宽度", "Sheets / Weff", sheet_text)]),
]

# 3D 画面里的文字标签：(层名, 中文, 英文, x 位置, z 位置)。某层存在时才在该位置显示标签。
REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.8),
    ("nsd", "SiP", "SiP", 4.1, 0.0),
    ("psd", "SiGe", "SiGe", 12.4, 0.0),
    ("gfill", "金属栅", "metal gate", 5.25, 0.85),
    ("cu", "Cu", "Cu", 10.25, 1.95),
]

# “参数”面板里的滑块：沿用 FinFET 的那组，只把“鳍厚”滑块换成“纳米片厚度”(范围 3~15 nm)。
# 写法 A if 条件 else B：条件成立取 A，否则取 B。这里对每个滑块 s：名字是 tsi_nm 就换掉，否则原样保留。
GAA_SLIDERS = [s if s[0] != "tsi_nm" else ("tsi_nm", "p_tsheet", 3.0, 15.0, False)
               for s in finfet.MULTIGATE_SLIDERS]

# 把上面所有东西打包成一条完整的工艺流程，主程序通过它来显示和运行 GAA 工艺。
FLOW = Flow(
    key="gaa",                                          # 内部名字
    name=("GAA 纳米片工艺", "GAA nanosheet"),            # 显示名字 (中, 英)
    short=("GAA 3nm", "GAA 3nm"),                       # 选择列表里的短名字
    node=("约 3-2 nm 代：硅纳米片堆叠，栅四面全环绕 (GAA)",
          "~3-2 nm: stacked Si nanosheets, gate all around"),
    steps=STEPS,
    # features：告诉电学计算部分这一代有哪些物理效应/结构：
    # sce = 短沟道效应，hkmg = 高k金属栅，gaa = 全环绕栅。frozenset 是“不能修改的集合”。
    features=frozenset({"sce", "hkmg", "gaa"}),
    region_labels=REGION_LABELS,
    terminal_labels=locos.TERMINAL_LABELS,              # 端子标签 (VDD、Vin、Vout、GND) 沿用 LOCOS 的
    layout_fn=gaa_layout,                               # 用本文件的布局函数代替默认布局
    sliders=GAA_SLIDERS,
    channel_fn=sheet_channels,                          # 沟道位置 (给载流子仿真用)
    carrier_ys=[STACK_Y],                               # 载流子只在这个 y 范围 (硅片内) 里运动
    # 这一代工艺的典型默认参数：tox 栅氧等效厚度 (nm)、l_um 栅长 (µm，0.015 = 15 nm)、
    # wn/wp 有效宽度、vdd 电源电压 (V)、cload_ff 负载电容 (fF)、mu_n/mu_p 电子/空穴迁移率、
    # wf_n/wf_p 功函数 (eV)、tsi_nm 纳米片厚度、lambda_um 沟道长度调制参数。
    # dict(a=1, b=2) 是创建“字典”(名字 → 值) 的另一种写法。
    defaults=dict(tox_nm=0.8, na_cm3=1e16, nwell_dose_cm2=2e13, l_um=0.015, wn_um=0.21, wp_um=0.21,
                  vdd=0.7, cload_ff=0.4, mu_n=250.0, mu_p=170.0, wf_n_ev=4.45, wf_p_ev=4.77, tsi_nm=5.0,
                  lambda_um=0.0015),
)
