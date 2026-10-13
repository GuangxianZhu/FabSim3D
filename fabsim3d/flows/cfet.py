"""Complementary FET (CFET): the PMOS nanosheets stacked on top of the NMOS.

One stack holds both transistors of the inverter: two n-type sheets at the
bottom, a middle dielectric isolation (MDI), two p-type sheets on top.  They
share one gate (= Vin).  A deep contact ties the two drains (= Vout), the
top source goes up to VDD and the bottom source is reached from the back of
the wafer (backside power delivery, GND).

【中文说明】这个文件描述“CFET (互补场效应晶体管) 堆叠工艺”的完整流程，是本程序里最先进的一代。

它在整个程序里的位置：
  - flows/ 目录下每个文件代表一代工艺。文件里有“数据”(工艺步骤列表 STEPS：标题、说明、参数、
    动画阶段、小测验) 和“小函数”(告诉程序往 3D 晶圆模型里加什么方块、刻掉什么)。
  - 最后的 FLOW 把这些打包，主程序读取它来播放动画、计算反相器的电学特性。
  - CFET 是在 GAA 纳米片工艺 (gaa.py) 的基础上发展的，所以很多步骤直接借用 gaa.py。

CFET 的核心思路：
  - 以前 (平面、FinFET、GAA) 反相器的 NMOS 和 PMOS 是“左右并排”放的；
  - CFET 把 PMOS 直接“叠”在 NMOS 正上方：下层 2 片 NMOS 纳米片，中间一层绝缘的
    “中间介质隔离 (MDI)”，上层 2 片 PMOS 纳米片。一个反相器只占一个晶体管的面积；
  - 两个晶体管共用一个栅 (= 输入 Vin)；
  - 一个“深接触孔”把上下两个漏极连在一起 (= 输出 Vout)；
  - 上层源极接 VDD (从正面引出)，下层源极接 GND，从晶圆“背面”引出 (背面供电)。

坐标约定：
  - x：屏幕左右，纳米片沿 x 延伸，电流沿 x 从源流到漏；本文件里源在左 (x≈5.5)，漏在右 (x≈14.5)，
    共用栅在中间 GC = 10；
  - y：伸进屏幕的深度方向，也是剖面方向，默认在 y = 3.5 处切开看；
  - z：向上；z = 0 是最上面一片纳米片的顶面 (相当于原来硅表面的位置)，负数在下面；
  - 单位是“显示单位”，竖直方向被大大夸张了，方便看清每一层。
"""
# 让类型标注可以写得更新式，对程序逻辑没有影响。
from __future__ import annotations

# replace(旧对象, 字段=新值)：复制一个已有对象只改几个字段，用来借用其他工艺的步骤。
from dataclasses import replace
from typing import List

from ..geometry import Solid, rect_complement
# process_core 是“工艺引擎”：Step/Phase/Flow 描述流程，其余大多是“动作”(淀积、刻蚀、磨平……)；
# Wafer = 晶圆模型，Ctx = 上下文 (参数 + 布局)，PhaseAnim = 一个动画阶段要播放的变化。
from ..process_core import (ACT_Y, DOMAIN, SPACER_W, Flow, Phase, PhaseAnim, Step, Wafer, Ctx,
                            add_solids, anneal, cmp, convert, deposit, gate_span, litho, pattern,
                            quiz, recess, recolor, replace_layer, spacer_span, strip)
from . import finfet, gaa, locos, sti
# _modern：先进工艺共用的步骤 (高k金属栅、接触孔、铜互连……)。
from ._modern import (EPI_NOTE, M1_TOP, channel_rects, contact_step, copper_m1_step, done_step,
                      hkmg_step, ild0_step, rmg_remove_step, side_slabs)

# 把其他工艺的步骤列表做成“名字 → 步骤”的字典，方便按名字借用 (字典推导式)。
_S = {s.key: s for s in sti.STEPS}      # STI 工艺
_L = {s.key: s for s in locos.STEPS}    # LOCOS 工艺
_G = {s.key: s for s in gaa.STEPS}      # GAA 工艺

# z stack (display units), bottom to top
# 竖直方向各层的高度 (下表面, 上表面)，从下往上：
SUB_TOP = -1.1                          # 衬底顶面
N_SHEETS = [(-1.0, -0.9), (-0.8, -0.7)]  # 下层 2 片硅：将来的 NMOS 沟道
P_SHEETS = [(-0.3, -0.2), (-0.1, 0.0)]   # 上层 2 片硅：将来的 PMOS 沟道
MDI = (-0.6, -0.4)                       # 中间那层高 Ge SiGe，将来换成绝缘的 MDI，隔开上下两管
# 普通 SiGe 牺牲层，共 5 层：每片硅下面一层，外加 MDI 正下方一层。最后全部刻掉，让栅填进去。
SIGE = [(-1.1, -1.0), (-0.9, -0.8), (-0.7, -0.6), (-0.4, -0.3), (-0.2, -0.1)]
# 下层 (NMOS) 的 3 道缝隙 和 上层 (PMOS) 的 2 道缝隙；[:3] 取前 3 个，[3:] 取第 4 个及以后。
N_GAPS, P_GAPS = SIGE[:3], SIGE[3:]
STACK_Y = (2.7, 4.3)    # 叠层在 y 方向的范围 (包住剖面 y = 3.5)
STACK_X = (3.0, 17.0)   # 叠层在 x 方向的范围：只有一条叠层，两个晶体管都在里面
GC = 10.0                       # shared gate centre  (共用栅中心的 x 坐标)
TRENCH_Z = -1.45        # 叠层刻蚀的沟槽底
STI_TOP = -1.15         # STI 回刻后的顶面 (略低于叠层底部，让整条叠层露出)
GATE_TOP = 0.55         # 栅顶
N_EPI_TOP = -0.62               # bottom (n) epi stops below the MDI  (下层 N 型源漏只长到 MDI 下面)
ISO_TOP = -0.38                 # S/D isolation between the two epi levels  (上下源漏之间的隔离氧化物顶面)
EPI_TOP = 0.15          # 上层 P 型源漏外延的顶面
BS_BOT = -2.0                   # backside dielectric bottom after wafer thinning  (减薄后背面介质的底)
BS_RAIL = (-2.35, -2.0)  # 背面 GND 金属电源轨的 z 范围 (在背面介质下面)


def cfet_layout(p):
    """【中文】CFET 的俯视平面布局 (代替通用的 layout)。返回一个字典，里面有：
      gl：画出来的栅长 (根据用户设定的栅长 p.l_um 换算，并限制在 0.6~1.8 之间)；
      gn/gp：NMOS/PMOS 栅的 x 范围 —— 在 CFET 里是同一个 (共用栅)；
      act_n/act_p/stacks：都是同一条叠层 (上下两管在同一位置)；
      nwell：面积为 0 (CFET 不需要 N 阱)；
      gates_n：栅的平面形状 (横跨叠层的栅条 + 往上延伸出去放栅接触孔的一块)；
      contacts：接触孔位置 (p_src = 上层源极/VDD，out = 深接触孔/输出，g = 栅接触)；
      metal：第一层金属线 (VDD、VOUT、VIN) 的位置；
      iso：叠层以外的区域 (填 STI)；spacer_bands：侧墙沿 y 分段的底部高度。
    """
    gl = min(max(0.45 + 0.3 * p.l_um, 0.6), 1.8)
    g = (GC - gl / 2, GC + gl / 2)
    stack = (STACK_X[0], STACK_X[1], *STACK_Y)   # *STACK_Y：把元组展开成两个数接在后面
    gates = [(g[0], g[1], 1.1, ACT_Y[1]), (GC - 0.5, GC + 0.5, ACT_Y[1], 7.6)]
    contacts = {"p_src": (5.0, 6.1, 2.6, 4.4), "out": (13.9, 15.0, 2.6, 4.4),
                "g": (GC - 0.3, GC + 0.3, 6.8, 7.35)}
    metal = {"VDD": (4.6, 6.5, 0.3, 4.9), "VOUT": (13.5, 16.6, 2.2, 4.8),
             "VIN": (GC - 0.5, GC + 2.4, 6.6, 7.6)}
    return dict(
        gl=gl, gn=g, gp=g, gnc=GC, gpc=GC, act_n=stack, act_p=stack, stacks=[stack],
        nwell=(0.0, 0.0, 0.0, 0.0), pside=DOMAIN,
        gates_n=gates, gates_p=[], gate_keys=[("gate", "gn")],
        contacts=contacts, metal=metal, iso=rect_complement(DOMAIN, [stack]),
        spacer_bands=[(1.1, STACK_Y[0], STI_TOP), (STACK_Y[0], STACK_Y[1], 0.0), (STACK_Y[1], 6.5, STI_TOP)],
    )


def _stacks(c):
    """【中文】返回叠层矩形列表 (这里只有一条)。c 是上下文 (参数 + 布局)。"""
    return c.lay["stacks"]


def _wafer(c):
    """【中文】初始硅片：一整块长方体，从 z=-3 到 SUB_TOP。Solid.box(x0,x1,y0,y1,z0,z1)。"""
    return [Solid.box(0, 20, 0, 8, -3.0, SUB_TOP)]


def _layers(zs):
    """【中文】给定若干 (z下, z上)，生成覆盖整片晶圆的外延薄层。
    这是“返回函数的函数”：先记住 zs，引擎在动画时才调用里面的 fn(c) 生成方块。"""
    def fn(c):
        out = []
        for z0, z1 in zs:
            s = Solid.box(0, 20, 0, 8, z0, z1)
            s.anchor = z0   # 生长动画从层底往上长
            out.append(s)
        return out
    return fn


def _sd(c):
    """【中文】源漏区域：叠层里、栅+侧墙以外的左右两段 (左边是源，右边是漏)。
    上下两层晶体管的源漏在同一个平面位置，只是高度不同。"""
    g = spacer_span(c, "gn")
    return [(STACK_X[0], g[0], *STACK_Y), (g[1], STACK_X[1], *STACK_Y)]


def _inner_zones(c):
    """【中文】侧墙正下方的两条带：这里的 SiGe 会被换成内侧墙 (隔开栅金属和源漏)。"""
    g = gate_span(c, "gn")
    return [(g[0] - SPACER_W, g[0], *STACK_Y), (g[1], g[1] + SPACER_W, *STACK_Y)]


def _box_on(rects, z0, z1, widen=0.1):
    """【中文】在 rects(c) 给出的每个矩形上放一块从 z0 到 z1 的方块，y 方向两边各加宽 widen。
    用于画上下两层源漏外延 (外延会往外鼓出一点)。"""
    def fn(c):
        out = []
        for r in rects(c):
            s = Solid.box(r[0], r[1], r[2] - widen, r[3] + widen, z0, z1)
            s.anchor = z0
            out.append(s)
        return out
    return fn


def _rename_gate(w: Wafer, c: Ctx, a: PhaseAnim):
    """【中文】一个自定义“动作”：把刻好的多晶硅层 "poly" 改名为 "gate"。
    后面的共用步骤 (去除伪栅) 按名字 "gate" 来找伪栅，所以这里要改名。
    动作函数都长这样：接收 (晶圆 w, 上下文 c, 动画 a)，直接修改晶圆。"""
    lay = w.remove("poly")
    if lay:
        w.layer("gate", lay.material).solids = lay.solids


def _top_of_stack(c):
    """Top of the stack inside the gate: covered by the p work-function metal.

    【中文】栅里面、叠层顶上的那块区域：这里铺的是 P 型功函数金属 (因为最上面是 PMOS)。"""
    return [(r[0], r[1], *STACK_Y) for r in channel_rects(c, "n")]


def _gaps(gaps, inset=0.0, thickness=None):
    """【中文】SiGe 刻掉后，片与片之间的缝隙里的薄膜 (只在栅下面)。和 gaa.gap_films 类似：
      thickness 为 None：缝隙上下各缩进 inset 后整块填满 (功函数金属)；
      否则：缝隙上下两个表面各贴一层 thickness 厚的膜 (高 k 介质 HfO2)。"""
    def fn(c):
        out = []
        for r in channel_rects(c, "n"):
            for z0, z1 in gaps:
                # A if 条件 else B：条件成立取 A，否则取 B。
                zs = [(z0 + inset, z1 - inset)] if thickness is None else [(z0, z0 + thickness), (z1 - thickness, z1)]
                out += [Solid.box(r[0], r[1], STACK_Y[0], STACK_Y[1], a, b) for a, b in zs]
        return out
    return fn


def _hk_extra(c):
    """【中文】HfO2 额外部分：所有缝隙的上下壁 + 叠层两侧的竖直薄膜 → 四片纳米片都被四面包住。"""
    return (_gaps(SIGE, thickness=0.02)(c)
            + side_slabs(channel_rects(c, "n"), [STACK_Y], STI_TOP, 0.0, 0.0, 0.03))


def _wfn_extra(c):
    """Bottom (NMOS) level: n work-function metal fills the gaps and wraps the sides.

    【中文】下层 (NMOS)：N 型功函数金属填满下层的缝隙，并包住侧面，只到 MDI 底部为止。"""
    return (_gaps(N_GAPS, inset=0.02)(c)
            + side_slabs(channel_rects(c, "n"), [STACK_Y], STI_TOP + 0.03, MDI[0], 0.03, 0.05))


def _wfp_extra(c):
    """【中文】上层 (PMOS)：P 型功函数金属填满上层的缝隙，并包住从 MDI 底部到顶的侧面。
    上下两管用不同的功函数金属，阈值电压才能分别对 NMOS、PMOS 合适。"""
    return (_gaps(P_GAPS, inset=0.02)(c)
            + side_slabs(channel_rects(c, "n"), [STACK_Y], MDI[0], 0.0, 0.03, 0.05))


def _deep_contact(c):
    """【中文】深接触孔的位置 = 输出 (out) 接触孔：它要穿过上层漏极一直打到下层漏极。"""
    return [c.lay["contacts"]["out"]]


def _contact_silicide(c):
    """【中文】接触孔底部的金属硅化物 (降低接触电阻)：
    一块在上层源极 (VDD) 顶面 EPI_TOP 处，一块在深接触孔底部、下层漏极顶面 N_EPI_TOP 处。"""
    ct = c.lay["contacts"]
    r, o = ct["p_src"], ct["out"]
    return [Solid.box(r[0], r[1], r[2], r[3], EPI_TOP - 0.03, EPI_TOP + 0.02),
            Solid.box(o[0], o[1], o[2], o[3], N_EPI_TOP - 0.03, N_EPI_TOP + 0.02)]


def _backside(w: Wafer, c: Ctx, a: PhaseAnim):
    """Flip, thin the substrate away and replace it by a backside dielectric.

    【中文】背面供电的第一步 (自定义动作)：晶圆翻过来，把衬底硅几乎全部磨掉/刻掉，换成介质。
    做法：取出衬底层 → 衬底的方块作为“被刻掉的幽灵”播放消失动画 (ghosts) →
    对每块衬底，保留 BS_BOT 以上的部分，换成氧化物 (背面介质层 "bsd") 并播放生长动画。
    """
    sub = w.remove("sub")
    if not sub:     # 如果没有衬底层 (已经处理过)，什么也不做
        return
    a.ghosts += [("p_sub", s, "etch") for s in sub.solids]
    diel = []
    for s in sub.solids:
        if s.is_box and s.zmax > BS_BOT:
            d = Solid.box(s.xmin, s.xmax, s.y0, s.y1, max(s.zmin, BS_BOT), s.zmax)
            d.anchor = s.zmax
            diel.append(d)
    w.layer("bsd", "ild_ox").solids = diel
    a.grow.extend(diel)


def _bs_contact(c):
    """【中文】背面接触孔：从背面介质底 BS_BOT 往上打到 STI 顶，正对着下层 NMOS 的源极
    (和正面 VDD 接触孔在同一个 x/y 位置，因为上下两管的源极正好上下对齐)。"""
    r = c.lay["contacts"]["p_src"]
    s = Solid.box(r[0], r[1], r[2], r[3], BS_BOT, STI_TOP)
    s.anchor = BS_BOT
    return [s]


def _bs_rail(c):
    """【中文】背面 GND 电源轨：晶圆背面一块宽宽的金属，连着背面接触孔，提供地 (0 V)。"""
    s = Solid.box(0.4, 8.0, 0.3, 7.7, *BS_RAIL)
    s.anchor = BS_RAIL[1]
    return [s]


def cfet_channels(lay):
    """【中文】告诉载流子仿真沟道在哪：下层 2 片标 "n" (电子)，上层 2 片标 "p" (空穴)。
    方块比纳米片稍大一点，方便显示。box = lambda ...：给一个一行小函数起名叫 box。"""
    g = lay["gn"]
    box = lambda z0, z1: Solid.box(g[0] - 0.05, g[1] + 0.05, STACK_Y[0] - 0.02, STACK_Y[1] + 0.02, z0, z1)
    return ([("n", box(z0 - 0.01, z1 + 0.01)) for z0, z1 in N_SHEETS]
            + [("p", box(z0 - 0.01, z1 + 0.01)) for z0, z1 in P_SHEETS])


def cfet_carriers(lay, ym):
    """Electrons come up from the backside GND rail through the bottom NMOS into
    the shared drain contact; holes run through the top PMOS from VDD to the
    same contact.  Metal-1 paths carry electrons as in the planar flows.

    【中文】3D 载流子动画的路线 (每条路线是一串 (x, y, z) 点，粒子沿着点移动)：
      "n"：电子从下层源极 (背面接上来) 穿过下层 NMOS 纳米片，流到漏极后沿深接触孔往上；
      "p"：空穴从 VDD 往下到上层源极，穿过上层 PMOS 纳米片，到漏极后往上；
      "gnd"：背面电源轨里从远处流到背面接触孔；
      "on"/"op"/"vdd"：第一层金属里的路线 (输出线、电源线)。
    ym 是当前剖面的 y 位置；xs/xd 是源/漏的 x，zn/zp 是下/上层沟道高度，zm 是金属层高度。
    """
    g = lay["gn"]
    xs, xd = 5.55, 14.45
    zn, zp = -0.75, -0.05
    zm = 1.55
    xo = 16.2
    return {
        "n": [(xs, ym, -1.45), (xs, ym, zn), (g[0], ym, zn), (g[1], ym, zn), (xd - 0.25, ym, zn),
              (xd - 0.25, ym, 1.45)],
        "p": [(xs, ym, 1.45), (xs, ym, zp), (g[0], ym, zp), (g[1], ym, zp), (xd + 0.25, ym, zp),
              (xd + 0.25, ym, 1.45)],
        "gnd": [(1.0, 4.7, -2.18), (xs, ym, -2.18), (xs, ym, -1.45)],
        "on": [(xd - 0.25, ym, 1.45), (xd - 0.25, ym, zm), (xo, ym, zm)],
        "op": [(xo, ym, zm + 0.08), (xd + 0.25, ym, zm + 0.08), (xd + 0.25, ym, 1.45)],
        "vdd": [(xs, ym, 1.45), (xs, ym, zm), (xs, 0.7, zm)],
    }


# ============================================================================
# 工艺步骤列表 STEPS (按顺序播放)。Step(...) 的参数依次是：
#   key、title (中, 英)、desc (中, 英)、params 参数表、phases 动画阶段、quiz 小测验 (可省)。
# replace(_G["xxx"], ...) = 沿用 GAA 工艺的 xxx 步骤，只改括号里写的部分。
# lambda c: "..." 是一行小函数，显示参数时才调用。
# ============================================================================
STEPS = [
    # 第 1 步 (借用 GAA)：准备 P 型硅片，只换掉说明文字和小测验。
    replace(_G["wafer"],
            desc=("CFET (互补场效应晶体管) 把 PMOS 直接叠在 NMOS 上面：一个反相器只占一个晶体管的面积。"
                  "目前 (2024 年起) 由 imec、Intel、台积电等在研发，预计用于 1 nm 级以后的节点。",
                  "A CFET (complementary FET) stacks the PMOS directly on top of the NMOS, so an inverter "
                  "takes the footprint of one transistor. It is in research at imec, Intel and TSMC (from "
                  "2024) and is expected beyond the ~1 nm class."),
            quiz=quiz("CFET 节省面积的方法是？", "How does a CFET save area?",
                      [("把 PMOS 叠在 NMOS 正上方", "It stacks the PMOS right on top of the NMOS"),
                       ("把晶体管做得更薄", "Thinner transistors"), ("去掉 PMOS", "It drops the PMOS"),
                       ("用更大的硅片", "Bigger wafers")], 0,
                      "平面、FinFET、GAA 中 NMOS 和 PMOS 并排放置；CFET 把它们竖着叠起来，单元面积约减少 40-50%。",
                      "Planar, FinFET and GAA place NMOS and PMOS side by side; stacking them cuts cell area by ~40-50 %."),
            phases=[Phase("准备硅片", "Wafer preparation", 1.0, [replace_layer("sub", "p_sub", _wafer)])]),

    # 第 2 步：上下两层超晶格外延 (CFET 特有)。从下往上依次长：
    #   SiGe / Si / SiGe / Si (下层 2 片 NMOS) → SiGe + 高 Ge 的 SiGe (将来变 MDI) →
    #   SiGe / Si / SiGe / Si (上层 2 片 PMOS)。
    # 为什么中间用“高 Ge”SiGe：Ge 越多刻得越快，可以先单独把它挖掉换成绝缘体 (MDI)，
    # 而普通 SiGe 和硅片暂时不受影响。MDI 的作用是把上下两个晶体管在电学上隔开。
    Step("cfet_sl", ("上下两层超晶格外延", "Two-level superlattice epitaxy"),
         ("依次外延：下层 2 片硅 (将来的 NMOS)，中间一层高 Ge 含量的 SiGe (将来换成中间介质隔离 MDI)，"
          "上层 2 片硅 (将来的 PMOS)，每片硅之间都夹着普通 SiGe 牺牲层。",
          "Epitaxy in order: two Si sheets for the bottom NMOS, a high-Ge SiGe layer (later replaced by "
          "the middle dielectric isolation, MDI), then two Si sheets for the top PMOS, with ordinary SiGe "
          "sacrificial layers between all sheets."),
         [("下层", "Bottom", lambda c: "2 × Si (NMOS)"),
          ("中间层", "Middle", lambda c: "SiGe, Ge ≈ 50 % → MDI"),
          ("上层", "Top", lambda c: "2 × Si (PMOS)"),
          ("片厚", "Sheet thickness", lambda c: f"{c.p.tsi_nm:.1f} nm")],
         [Phase("下层：SiGe / Si × 2 (NMOS)", "Bottom: SiGe / Si × 2 (NMOS)", 1.6,
                [add_solids("sige", "sige", _layers(SIGE[:2])), add_solids("sheet_n", "si_fin", _layers(N_SHEETS))]),
          Phase("中间：SiGe + 高 Ge 隔离层", "Middle: SiGe + high-Ge isolation layer", 1.4,
                [add_solids("sige", "sige", _layers([SIGE[2]])), add_solids("mdi", "sige_hi", _layers([MDI]))]),
          Phase("上层：SiGe / Si × 2 (PMOS)", "Top: SiGe / Si × 2 (PMOS)", 1.6,
                [add_solids("sige", "sige", _layers(SIGE[3:])), add_solids("sheet_p", "si_fin", _layers(P_SHEETS))])],
         quiz("中间那层高 Ge 的 SiGe 将来变成什么？", "What does the high-Ge SiGe layer become?",
              [("把上下两个晶体管隔开的介质层", "A dielectric that isolates the top and bottom transistors"),
               ("沟道", "A channel"), ("栅极", "The gate"), ("金属线", "A wire")], 0,
              "Ge 含量更高的 SiGe 可以比普通 SiGe 刻得更快，先被单独挖掉再填入介质，形成 MDI。",
              "Higher-Ge SiGe etches faster than ordinary SiGe, so it is removed first and refilled with dielectric (MDI).")),

    # 第 3、4 步 (借用)：垫氧化层 + 氮化硅硬掩膜 (保护要留下的叠层，并作 CMP 停止层)。
    replace(_L["padox"], params=[("厚度", "Thickness", lambda c: "≈ 5 nm")]),
    replace(_S["nitride"],
            desc=("淀积 Si3N4 硬掩膜。", "A Si3N4 hard mask is deposited.")),
    # 第 5 步 (借用 GAA)：EUV 光刻出叠层图形 —— CFET 只要一条叠层，两个晶体管都在里面。
    replace(_G["stack_litho"],
            desc=("EUV 光刻定义唯一的一条叠层：反相器的两个晶体管都在这一条叠层里。",
                  "EUV defines a single stack: both transistors of the inverter live in it.")),
    # 第 6 步：高叠层刻蚀。打开硬掩膜、去胶，再把叠层以外的所有层 (两层硅片、SiGe、MDI、
    # 一段衬底) 一起往下刻到 TRENCH_Z。叠层几乎是 GAA 的两倍高，要刻得笔直更难。
    Step("stack_etch", ("高叠层刻蚀", "Tall stack etch"),
         ("把总共 9 层的 Si/SiGe 叠层一次刻穿。叠层几乎是 GAA 的两倍高，侧壁要保持笔直难度更大。",
          "All nine Si/SiGe layers are etched through in one go. The stack is almost twice as tall as for "
          "GAA, so keeping the sidewalls vertical is harder."),
         [("刻蚀", "Etch", lambda c: "HBr / Cl2 RIE"),
          ("层数", "Layers", lambda c: "4 × Si + 4 × SiGe + MDI")],
         [Phase("刻蚀硬掩膜", "Etch the hard mask", 1.2,
                [pattern("nitride", _stacks, mask="ACTIVE"), pattern("padox", _stacks, particles=False, mask="ACTIVE")]),
          Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")]),
          Phase("刻蚀高叠层", "Etch the tall stack", 2.4,
                [recess(["sheet_n", "sheet_p", "sige", "mdi", "sub"], lambda c: c.lay["iso"], TRENCH_Z)])]),

    # 第 7 步：STI 隔离。填氧化物 → CMP 磨平 → 去硬掩膜 → 回刻到叠层底部以下，让整条叠层露出。
    # CFET 不用做 N 阱：上下两管靠 MDI 绝缘层隔开，而不是靠 PN 结。所以这里没有阱注入步骤。
    Step("stack_sti", ("STI 填充 + CMP + 回刻", "STI fill, CMP and recess"),
         ("填氧化物、CMP、去硬掩膜，再把 STI 回刻到叠层底部以下。注意 CFET 不需要做 N 阱："
          "NMOS 和 PMOS 都是悬空的不掺杂纳米片，由 MDI 和栅隔开，而不是靠 PN 结隔离。",
          "Oxide fill, CMP, hard-mask strip and an STI recess below the stack. Note that a CFET needs no "
          "n-well: both devices are undoped suspended sheets separated by the MDI and the gate, not by "
          "PN junctions."),
         [("填充", "Fill", lambda c: "FCVD SiO2"),
          ("阱", "Wells", lambda c: "不需要 / none")],
         [Phase("氧化物填充", "Oxide fill", 1.6,
                [deposit("sti", "sti_ox", top=0.45, particles=("depo", (0.8, 0.85, 0.95, 1)))]),
          Phase("CMP 停在氮化硅上", "CMP onto the nitride", 1.8, [cmp(["sti"], 0.18)]),
          Phase("去硬掩膜", "Strip the hard mask", 1.2, [strip("nitride"), strip("padox")]),
          Phase("STI 回刻", "Recess the STI", 1.6, [cmp(["sti"], STI_TOP, pad=False)])],
         quiz("为什么 CFET 可以不做 N 阱？", "Why can a CFET skip the n-well?",
              [("上下两管是悬空的纳米片，用介质而不是 PN 结隔离", "Both devices are suspended sheets isolated by dielectric, not PN junctions"),
               ("PMOS 不需要电子", "PMOS needs no electrons"), ("N 阱太贵", "Wells are too expensive"),
               ("其实需要", "It actually needs one")], 0,
              "传统 CMOS 的 PMOS 要放在 N 阱里，靠反偏 PN 结和 NMOS 隔开；CFET 的上下两管之间是 MDI 介质。",
              "Classic CMOS puts the PMOS in an n-well isolated by a reverse-biased junction; in a CFET the MDI dielectric does that.")),

    # 第 8 步：伪栅 (占位用的多晶硅栅，最后换成金属栅)。上下两管共用这一个栅 = 输入 Vin。
    Step("cfet_dummy_gate", ("伪栅 (上下共用)", "Dummy gate (shared)"),
         ("淀积伪栅氧化层和多晶硅并磨平。CFET 反相器里 NMOS 和 PMOS 共用一个栅：它就是输入 Vin。",
          "Dummy oxide and poly are deposited and planarised. In a CFET inverter the NMOS and PMOS share "
          "one gate: it is the input Vin."),
         [("多晶硅", "Poly", lambda c: "CMP 平坦化")],
         [Phase("牺牲氧化层", "Sacrificial oxide", 1.0, [deposit("gox", "gate_ox", thickness=0.03, region=_stacks)]),
          Phase("淀积伪栅多晶硅并磨平", "Deposit and planarise dummy poly", 1.6,
                [deposit("poly", "poly_dummy", top=GATE_TOP, particles=("depo", (0.9, 0.6, 0.45, 1)))])]),
    # 第 9 步 (借用 GAA)：伪栅光刻，画出横跨叠层的栅条。
    replace(_G["gate_litho"]),
    # 第 10 步 (借用 STI，重写阶段)：刻蚀多晶硅只留下栅条 (只有一个共用栅 gates_n)，
    # 去掉暴露的氧化层，去胶；最后的 _rename_gate 把 "poly" 层改名为 "gate"。
    replace(_S["gate_etch"], title=("伪栅刻蚀", "Dummy-gate etch"),
            phases=[Phase("刻蚀多晶硅", "Etch polysilicon", 1.8,
                          [pattern("poly", lambda c: c.lay["gates_n"], mask="POLY")]),
                    Phase("去除暴露的氧化层", "Remove the exposed oxide", 1.0,
                          [pattern("gox", lambda c: c.lay["gates_n"], particles=False, mask="POLY")]),
                    Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist"), _rename_gate])]),
    # 第 11、12 步 (借用)：侧墙淀积 + 刻蚀 (栅两边的绝缘小墙)；quiz=None 表示不出题。
    replace(_S["spacer_dep"], quiz=None),
    replace(_S["spacer_etch"]),

    # 第 13 步：源漏凹槽 + MDI + 内侧墙。
    # 阶段 1：把侧墙外 (源漏位置) 的整个叠层刻到 STI 顶，露出各层端面；
    # 阶段 2：高 Ge 层被选择性挖掉、换成介质 → MDI (程序里用 recolor 直接把它改成氧化物颜色)；
    # 阶段 3：侧墙下的 SiGe 换成内侧墙，防止将来的栅金属和源漏离得太近 (寄生电容/短路)。
    Step("cfet_inner", ("源漏凹槽 + MDI + 内侧墙", "S/D recess + MDI + inner spacers"),
         ("刻穿侧墙外的叠层；把高 Ge 层挖掉换成介质，形成中间介质隔离 (MDI)；"
          "再把侧墙下的 SiGe 换成内侧墙。",
          "The stack outside the spacers is etched through; the high-Ge layer is replaced by dielectric "
          "to form the middle dielectric isolation (MDI); the SiGe under the spacers becomes inner spacers."),
         [("MDI", "MDI", lambda c: "SiN / SiO2, ≈ 20 nm"),
          ("内侧墙", "Inner spacer", lambda c: "SiN, ALD")],
         [Phase("刻穿侧墙外的叠层", "Etch through the stack outside the spacers", 1.8,
                [recess(["sheet_n", "sheet_p", "sige", "mdi", "sub"], _sd, STI_TOP)]),
          Phase("高 Ge 层 → 中间介质隔离", "High-Ge layer → middle dielectric isolation", 1.6,
                [recolor("mdi", "mdi_ox")]),
          Phase("内侧墙", "Inner spacers", 1.6, [convert("sige", "inner", "spacer", _inner_zones)])],
         quiz("MDI 层的作用是？", "What is the MDI for?",
              [("把上层 PMOS 和下层 NMOS 在电学上隔开", "It electrically isolates the top PMOS from the bottom NMOS"),
               ("作为沟道", "Channel"), ("导热", "Heat removal"), ("作为栅", "Gate")], 0,
              "没有 MDI，上下两个晶体管的沟道和源漏就会连在一起。",
              "Without the MDI the channels and S/D of the two devices would touch.")),

    # 第 14 步：下层 NMOS 源漏外延。只从下层两片硅的端面长掺磷硅 (N 型)，高度停在 MDI 以下
    # (N_EPI_TOP)。上层端面暂时被保护膜盖住，不让它长。
    # 为什么分两次：同一根竖直的源漏柱子，下半段要 N 型、上半段要 P 型。
    Step("cfet_epi_n", ("下层 NMOS 源漏外延 (SiP)", "Bottom NMOS S/D epitaxy (SiP)"),
         ("先只让下层两片纳米片的端面外延生长 SiP，并控制高度停在 MDI 以下；上层的端面此时被一层保护膜盖住 (图中未画)。",
          "First SiP grows only from the ends of the two bottom sheets and is stopped below the MDI; the "
          "top sheet ends are covered by a protective liner meanwhile (not drawn)."),
         [("外延", "Epitaxy", lambda c: "Si:P"),
          ("高度", "Height", lambda c: "止于 MDI 以下 / below the MDI")],
         [Phase("下层 SiP 外延", "Bottom SiP epitaxy", 2.0,
                [add_solids("nsd", "n_epi", _box_on(_sd, STI_TOP, N_EPI_TOP), particles=("depo", (1.0, 0.4, 0.4, 1)))])],
         quiz("上下两层源漏为什么要分两次外延？", "Why are the two S/D levels grown separately?",
              [("下层要 N 型、上层要 P 型，掺杂和材料都不同", "Bottom needs n-type, top p-type: different doping and material"),
               ("机器太小", "The tool is too small"), ("为了省时间", "To save time"), ("没有必要", "No need")], 0,
              "同一列源漏上下两段要做成相反的掺杂，这是 CFET 工艺最难的地方之一。",
              "One vertical S/D column must hold opposite doping at two heights, one of the hardest parts of CFET.")),
    # 第 15 步：源漏隔离介质。在下层源漏上面盖一层氧化物 (到 ISO_TOP)，
    # 把上下两层源漏隔开，否则 N 型和 P 型源漏会直接接触 (短路)。
    Step("cfet_sd_iso", ("源漏隔离介质", "S/D isolation dielectric"),
         ("在下层源漏上方淀积氧化物并回刻到 MDI 的高度，把上下两层源漏隔开。",
          "Oxide is deposited on the bottom S/D and etched back to the MDI level, separating the two S/D levels."),
         [("材料", "Material", lambda c: "SiO2, 回刻 / etched back")],
         [Phase("淀积 + 回刻隔离氧化物", "Deposit + etch back the isolation oxide", 1.8,
                [deposit("sdiso", "mdi_ox", top=ISO_TOP, region=lambda c: [(r[0], r[1], r[2] - 0.1, r[3] + 0.1) for r in _sd(c)])])]),
    # 第 16 步：上层 PMOS 源漏外延。去掉保护膜，从上层两片硅的端面长掺硼 SiGe (P 型)，
    # 从 ISO_TOP 长到 EPI_TOP；最后退火激活掺杂。
    Step("cfet_epi_p", ("上层 PMOS 源漏外延 (SiGe:B)", "Top PMOS S/D epitaxy (SiGe:B)"),
         ("去掉上层保护膜，从上层两片纳米片的端面外延生长掺硼 SiGe。",
          "The liner on the top sheets is removed and B-doped SiGe grows from the ends of the top two sheets."),
         [("外延", "Epitaxy", lambda c: "SiGe:B")],
         [Phase("上层 SiGe:B 外延", "Top SiGe:B epitaxy", 2.0,
                [add_solids("psd", "p_epi", _box_on(_sd, ISO_TOP, EPI_TOP), particles=("depo", (0.4, 0.5, 1.0, 1))),
                 anneal(650, 600, (1.0, 0.7, 0.4))])]),

    # 第 17 步 (共用)：淀积 ILD0 绝缘氧化物并磨平到栅顶，把源漏埋起来。
    ild0_step(GATE_TOP),
    # 第 18 步 (共用 + 额外阶段)：挖掉伪栅，再选择性刻掉所有 SiGe → 4 片纳米片悬空，中间夹着 MDI。
    rmg_remove_step(["gate"], title=("去除伪栅 + 纳米片释放", "Dummy-gate removal + sheet release"),
                    desc=("掏空伪栅，再刻掉全部 SiGe：上下四片纳米片悬空，中间夹着 MDI。",
                          "The dummy gate is removed and all SiGe is etched: four suspended sheets with the MDI between them."),
                    extra_phase=Phase("选择性刻蚀 SiGe", "Selective SiGe etch", 2.2, [strip("sige")])),
    # 第 19 步 (共用)：高 k 介质 + 金属栅。难点：同一个栅槽里，下层要 N 型功函数金属、上层要 P 型。
    # wfn_region=lambda c: [] 表示 N 型金属不铺在栅顶 (栅顶是上层 PMOS)；
    # wfp_region=_top_of_stack 表示 P 型金属铺在叠层顶上。
    hkmg_step(GATE_TOP, extra_hk=_hk_extra, extra_wfn=_wfn_extra, extra_wfp=_wfp_extra,
              desc=("HfO2 包住全部四片纳米片。难点在功函数金属：下层 NMOS 要 N 型金属，上层 PMOS 要 P 型金属，"
                    "但它们在同一个栅槽里。做法是先全部填 N 型金属，再把上层的刻掉换成 P 型 (图中直接画出结果)。",
                    "HfO2 wraps all four sheets. The difficulty is the work-function metal: the bottom NMOS needs "
                    "an n-type metal and the top PMOS a p-type one, in the same trench. The n metal fills "
                    "everything first, then the top part is etched back and replaced with p metal (the result "
                    "is drawn)."),
              extra_params=[("功函数金属", "WF metals", lambda c: "下 TiAl / 上 TiN")],
              wfn_region=lambda c: [], wfp_region=_top_of_stack),
    # 第 20 步 (共用 + 额外阶段)：接触孔。额外的“深接触孔”阶段：在输出位置把上层 P 型漏极
    # 和隔离氧化物一直刻到下层 N 型漏极顶面 (N_EPI_TOP)，填金属后两个漏极就连在一起 = 输出 Vout。
    contact_step(silicide_fn=_contact_silicide,
                 extra_phases=[Phase("深接触孔：穿过上层漏极到下层漏极", "Deep contact: through the top drain to the bottom drain", 1.6,
                                     [recess(["psd", "sdiso"], _deep_contact, N_EPI_TOP)])],
                 desc=("VDD 接触孔停在上层 PMOS 的源极上；输出 Vout 用一个“深接触孔”从上层漏极一直打到下层漏极，"
                       "把两个漏极连在一起；栅接触孔落在共用栅上。下层的源极 (GND) 从晶圆背面引出。",
                       "The VDD contact lands on the top PMOS source; the output Vout uses a deep contact that "
                       "goes through the top drain down to the bottom drain, tying the two drains together; the "
                       "gate contact lands on the shared gate. The bottom source (GND) will be reached from the "
                       "back of the wafer.")),
    # 第 21 步 (共用)：第一层铜互连 M1。
    copper_m1_step(),
    # 第 22 步：背面供电 (BSPDN)。
    # 为什么：下层 NMOS 的源极被埋在最下面，从正面很难接上；而且正面金属层又挤又细、电阻大。
    # 做法：把晶圆翻过来 → 磨掉衬底硅换成介质 (_backside) → 从背面打孔到下层源极 (_bs_contact)
    #       → 做背面 GND 金属轨 (_bs_rail)。电源走背面，正面布线全给信号用。
    Step("bspdn", ("背面供电：减薄 + 背面接触 + GND 轨", "Backside power: thinning, contact, GND rail"),
         ("把晶圆正面键合到一片载片上翻过来，从背面把衬底硅几乎全部磨掉，换成介质。然后从背面打孔连到"
          "下层 NMOS 的源极，再做背面金属 GND 电源轨。电源线放在背面，正面的布线空间全部留给信号。",
          "The wafer is bonded face-down to a carrier and flipped; the substrate is ground and etched away "
          "almost completely and replaced by dielectric. A contact is then opened from the back to the "
          "bottom NMOS source and a backside metal GND rail is formed. With power on the back, all "
          "front-side wiring is free for signals."),
         [("键合", "Bonding", lambda c: "晶圆-载片键合 / wafer-to-carrier"),
          ("减薄", "Thinning", lambda c: "研磨 + CMP + 选择性刻蚀"),
          ("背面金属", "Backside metal", lambda c: "Cu / W 电源轨")],
         [Phase("翻转、减薄：去掉衬底硅", "Flip and thin: substrate removed", 2.4, [_backside]),
          Phase("背面接触孔到下层源极", "Backside contact to the bottom source", 1.6,
                [add_solids("bsc", "plug", _bs_contact)]),
          Phase("背面 GND 电源轨", "Backside GND rail", 1.6, [add_solids("bsm", "bs_metal", _bs_rail)])],
         quiz("背面供电 (BSPDN) 的主要好处是？", "Main benefit of backside power delivery?",
              [("电源线又短又粗、压降小，正面布线全给信号", "Short, thick power lines with low IR drop; the front is free for signals"),
               ("晶圆更便宜", "Cheaper wafers"), ("不需要光刻", "No lithography"), ("晶体管更快开关", "Faster switching by itself")], 0,
              "正面十几层金属里电源线占了大量空间且电阻大；放到背面后可以做得很粗，直接连到晶体管。",
              "Power lines took much of the front stack and had high resistance; on the back they can be thick and connect directly.")),
    # 最后一步：完成，提示用户去看剖面和载流子动画。
    done_step(("CFET 反相器完成：一个反相器只占一个晶体管的面积。剖面中可以看到下层两片 NMOS 纳米片 (电子) "
               "和上层两片 PMOS 纳米片 (空穴) 共用一个栅；输出由深接触孔连接两个漏极，GND 来自背面。"
               "打开 3D 载流子仿真，拖动 Vin 看上下两层轮流导通。",
               "The CFET inverter is done in the footprint of a single transistor. The cross-section shows the "
               "two bottom NMOS sheets (electrons) and two top PMOS sheets (holes) sharing one gate; a deep "
               "contact joins the drains for the output and GND comes from the back. Turn on the 3D carrier "
               "view and drag Vin to see the two levels take turns conducting.")),
]

# 3D 画面里的区域文字标签：(层名, 中文, 英文, x, z)。
REGION_LABELS = [
    ("bsd", "背面介质", "backside dielectric", 15.5, -1.7),
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("sti", "STI", "STI", 1.6, -1.3),
    ("nsd", "n+ SiP", "n+ SiP", 8.3, -0.9),
    ("psd", "p+ SiGe", "p+ SiGe", 8.3, -0.1),
    ("gfill", "共用栅", "shared gate", GC, 0.85),
    ("cu", "Cu", "Cu", 15.0, 1.95),
    ("bsm", "GND 背面电源轨", "GND backside rail", 4.2, -2.6),
]

# 端子标签：(名字, x, y) 或 (名字, x, y, z)。GND 带了 z = -2.75，因为它在晶圆背面下方。
TERMINAL_LABELS = [
    ("VDD", 5.55, 1.0), ("Vout", 15.0, 3.5), ("Vin", GC + 1.2, 7.1), ("GND", 1.6, 1.0, -2.75),
]

# 仿真模式里标出上下两管的文字：((中, 英), x, y, z, 颜色 RGBA)。
DEVICE_LABELS = [
    (("← PMOS (上层)", "← PMOS (top)"), 18.9, 3.6, -0.15, (0.6, 0.7, 1, 1)),
    (("← NMOS (下层)", "← NMOS (bottom)"), 18.9, 3.6, -0.85, (1, 0.6, 0.6, 1)),
]

# 打包成完整的 CFET 工艺流程，主程序通过它来显示和运行。
FLOW = Flow(
    key="cfet",
    name=("CFET 堆叠工艺", "CFET (stacked)"),
    short=("CFET 2nm 后", "CFET <2nm"),
    node=("2 nm 以后：PMOS 叠在 NMOS 上 (CFET) + 背面供电",
          "Beyond 2 nm: PMOS stacked on NMOS (CFET) + backside power"),
    steps=STEPS,
    # 物理特性开关：短沟道效应、高k金属栅、全环绕栅、CFET 堆叠。
    features=frozenset({"sce", "hkmg", "gaa", "cfet"}),
    region_labels=REGION_LABELS,
    terminal_labels=TERMINAL_LABELS,
    device_labels=DEVICE_LABELS,
    layout_fn=cfet_layout,
    sliders=gaa.GAA_SLIDERS,        # 参数滑块沿用 GAA 的
    channel_fn=cfet_channels,
    carrier_fn=cfet_carriers,       # 载流子路线用本文件的 (因为结构是上下叠的)
    carrier_ys=[STACK_Y],
    # 典型默认参数 (含义同 gaa.py)：栅长 14 nm，宽度更小 (每管只有 2 片)，电源电压 0.65 V 等。
    defaults=dict(tox_nm=0.8, na_cm3=1e16, nwell_dose_cm2=2e13, l_um=0.014, wn_um=0.14, wp_um=0.14,
                  vdd=0.65, cload_ff=0.25, mu_n=250.0, mu_p=170.0, wf_n_ev=4.45, wf_p_ev=4.77, tsi_nm=5.0,
                  lambda_um=0.0015),
)
