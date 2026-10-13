"""Classic ~1 µm CMOS flow: single n-well, LOCOS isolation, Al metal 1.

【中文说明：这个文件是做什么的】
本文件描述“经典 LOCOS 工艺”：大约 1980-1990 年代、最小尺寸约 1 µm 时代制造 CMOS 芯片的完整步骤。
最终做出来的是一个 CMOS 反相器 (inverter，“非门”)：左边一个 NMOS 管、右边一个 PMOS 管，
输入 Vin 为低电平时输出 Vout 为高电平，反之亦然。它是所有数字电路最基本的单元。

本文件的写法是“数据 + 小函数”：
  * STEPS 是一个按顺序排列的步骤清单。每个 Step (步骤) 里写好了：
      标题、文字说明、参数表、动画阶段 (Phase)、一道小测验 (quiz)。
  * 每个 Phase 里有若干“动作” (action)，例如 deposit (淀积一层膜)、pattern (刻蚀)、
    implant (离子注入)、anneal (退火加热)。这些动作是一些小函数，真正去修改 3D 晶圆模型，
    并告诉动画该怎么播放 (长出来、淡出、发光、粒子飞舞等)。
  * 程序从第一步开始依次执行这些动作，就“造”出了 3D 晶圆，并逐步播放动画。
  * 这些小函数大多定义在 process_core.py 里，本文件只负责“按什么顺序、用什么参数”调用它们。

【坐标约定 (后面出现的数字都按这个理解)】
  x：左右方向，0 到 20。左半边 (约 0-10.5) 放 NMOS，右半边 (约 10.5-20) 是 N 阱，放 PMOS。
  y：伸进屏幕的方向 (纵深)，0 到 8。界面上的“剖面”是沿 y 方向移动的一刀切面。
  z：向上为正。硅片表面在 z = 0；z < 0 是硅里面，z > 0 是硅表面上方长出来/淀积上去的膜。
  单位是“显示单位”：水平方向大约相当于微米，竖直方向故意放大 (夸张) 了很多倍，
  否则几十纳米的薄膜在屏幕上根本看不见。

【文字都写两遍】
  形如 ("中文", "English") 的一对字符串是界面的中英文两种语言版本，程序按用户选择显示其中一个。
"""
# 下面这一行让 Python 推迟解析类型提示 (例如 "-> Solid")，属于技术细节，对初学者可以忽略。
from __future__ import annotations

# List 用于写“类型提示”，例如 List[Solid] 表示“一串 Solid 对象组成的列表”。只起说明作用。
from typing import List

# “..” 表示上一级文件夹 (fabsim3d)。geometry 模块负责几何形状：
#   Solid          一个 3D 实体 (剖面多边形沿 y 方向拉伸而成)
#   rect_complement 求“补集”：给定区域里，除去某些矩形后剩下的矩形
#   split_box      把一个方块按矩形切成“保留部分”和“去掉部分”
from ..geometry import Solid, rect_complement, split_box
# process_core 是“工艺引擎”，提供步骤/阶段的数据结构和各种动作函数 (淀积、刻蚀、注入……)。
# DOMAIN = 整个模拟区域 (x 0-20, y 0-8)；ACT_Y = 有源区在 y 方向的范围；SUB_DEPTH = 衬底画多深。
from ..process_core import (DOMAIN, ACT_Y, SUB_DEPTH, Ctx, Flow, Phase, PhaseAnim, Step, Wafer,
                            actives, anneal, contacts, gate_span, coat, deposit, develop, expose, gates, glow,
                            implant, litho, metal, nwe_text, pattern, quiz, recolor, replace_layer, sci,
                            sd_annealed, sd_rects, split_gates, strip, summarize_cached, vt_text)


def _locos_prism(a: float, b: float, y0: float, y1: float) -> Solid:
    """Build one field-oxide bar (with bird's beaks) between x = a and x = b.

    构造一条 LOCOS 场氧 (FOX) 的 3D 形状：在 x 方向从 a 到 b，沿 y 方向从 y0 拉伸到 y1。
    为什么形状这么特别？
      * 热氧化时，氧化层约 44% “长进”硅里面，56% 长在原硅表面之上，
        所以场氧顶部在表面之上 (top = 0.35)，底部陷进硅里 (bot = -0.25)。
      * 氧会从氮化硅边缘下方横向钻进去，形成两头尖尖的“鸟嘴” (bird's beak)：
        在 z = 0 处，氧化层的尖端会向有源区伸出 beak_out 这么远。
      * 如果某一边正好是整个模拟区域的边界，就不画鸟嘴，直接竖直截断。
    函数名前面的下划线 “_” 是 Python 的习惯写法，表示“仅在本文件内部使用”。
    """
    # 一行给四个变量赋值：场氧顶面高度、底面深度、鸟嘴向内收进的距离、鸟嘴尖向外伸出的距离。
    top, bot, beak_in, beak_out = 0.35, -0.25, 0.35, 0.25
    # pts 收集剖面多边形的顶点，每个点是 (x, z)，按逆时针顺序排列。
    pts = []
    # 左边：如果 a 就在区域最左边 (1e-6 是一个极小的容差，避免小数比较误差)，直接竖直截断；
    if a <= DOMAIN[0] + 1e-6:
        pts += [(a, bot)]
    # 否则画左鸟嘴：先是伸进有源区的尖端 (在硅表面 z=0)，再到底部内收的拐点。
    else:
        pts += [(a - beak_out, 0.0), (a + beak_in, bot)]
    # 右边同理：在区域最右边就竖直截断；否则画右侧鸟嘴 (底部拐点 → 尖端 → 顶部拐点)。
    if b >= DOMAIN[1] - 1e-6:
        pts += [(b, bot), (b, top)]
    else:
        pts += [(b - beak_in, bot), (b + beak_out, 0.0), (b - beak_in, top)]
    # 最后补上左上角的点，多边形闭合。
    if a <= DOMAIN[0] + 1e-6:
        pts += [(a, top)]
    else:
        pts += [(a + beak_in, top)]
    # 用这些顶点构造实体，并沿 y 方向从 y0 拉伸到 y1。
    s = Solid(pts, y0, y1)
    # anchor = 0.0：生长动画以硅表面 z=0 为基准，向上下两边“长”出来 (模拟氧化同时向上向下生长)。
    s.anchor = 0.0
    return s



def _fox_solids(c: Ctx) -> List[Solid]:
    """All field-oxide pieces of the wafer.

    返回整片晶圆上所有场氧块。参数 c 是“上下文” (Ctx)，里面有当前的工艺参数 c.p
    和版图坐标 c.lay (一个字典，记录各区域在哪里)。
    场氧要把每个有源区 (晶体管所在的矩形) 四面包围起来：
      * 左右方向：c.lay["fox_x"] 给出几段 x 范围，每段做成一条带鸟嘴的长条，沿 y 贯穿 0-8；
      * 前后方向：有源区只占 y 的 ACT_Y 范围 (1.5-6.5)，在它的前方 (y 0-1.5) 和后方 (y 6.5-8)
        也要补上场氧方块 (这里简化成没有鸟嘴的长方体，底 -0.25，顶 0.35)。
    """
    # “列表推导式”：[表达式 for 变量 in 序列] 会对序列里每个元素算一次表达式，把结果收集成一个新列表。
    # 这里对每一段 (a, b) 都生成一条场氧长条。
    out = [_locos_prism(a, b, 0.0, 8.0) for a, b in c.lay["fox_x"]]
    # 每个有源区 act 是一个矩形 (x0, x1, y0, y1)，act[0]、act[1] 是它的 x 起止。
    for act in actives(c):
        # Solid.box(x0, x1, y0, y1, z0, z1) 造一个长方体。前方的一块：
        out.append(Solid.box(act[0], act[1], 0.0, ACT_Y[0], -0.25, 0.35))
        # 后方的一块：
        out.append(Solid.box(act[0], act[1], ACT_Y[1], 8.0, -0.25, 0.35))
    # 所有场氧块都以硅表面为生长基准。
    for s in out:
        s.anchor = 0.0
    return out


def _locos(w: Wafer, c: Ctx, a: PhaseAnim):
    """The LOCOS oxidation action: grow field oxide, consume pad oxide in the field.

    这是一个“动作函数”，和 process_core 里的 deposit/strip 等动作格式相同：
      w = 晶圆模型 (Wafer，里面有一层层材料)，c = 上下文，a = 本阶段的动画记录 (PhaseAnim)。
    它做三件事：
      1. 新建 "fox" (field oxide，场氧) 这一层，放入所有场氧块，并让动画把它们“长”出来；
      2. 场区原来的薄垫氧化层被厚场氧“吞并”了，所以只保留有源区里的垫氧，其余部分淡出消失；
      3. 让画面发出橙色的光，表示这是在高温炉里进行的。
    """
    fox = _fox_solids(c)
    # w.layer("fox", "fox")：取出 (没有就新建) 名为 "fox"、材料为 "fox" 的一层，把形状放进去。
    w.layer("fox", "fox").solids = fox
    # 告诉动画：这些实体要以“生长”的方式出现。
    a.grow.extend(fox)
    # 看看晶圆上有没有垫氧层 (get 找不到时返回 None，下面的 if 就不执行)。
    pad = w.layers.get("padox")
    if pad:
        kept_all = []
        for s in pad.solids:
            # 按有源区切开：有源区内的保留，场区的去掉。
            kept, removed = split_box(s, actives(c))
            kept_all += kept
            # 被去掉的部分做成“幽灵” (ghost)：动画里逐渐淡出，而不是瞬间消失。
            a.ghosts += [("pad_ox", r, "fade") for r in removed]
        pad.solids = kept_all
    # 发光颜色 (红, 绿, 蓝)，数值 0-1：这里是橙红色，代表高温。
    a.glow = (1.0, 0.45, 0.15)



# ==========================================================================================
# 工艺步骤清单
# ------------------------------------------------------------------------------------------
# 每个 Step(...) 的参数依次是：
#   1. key       步骤的内部名字 (英文短词，程序用它查找步骤；别的文件也会按这个名字引用)
#   2. title     (中文标题, 英文标题)
#   3. desc      (中文说明, 英文说明)：界面上显示的详细介绍
#   4. params    参数表：每行是 (中文名, 英文名, 一个计算显示文字的函数)
#   5. phases    动画阶段列表：每个 Phase(中文名, 英文名, 播放秒数, [动作, 动作, ...])
#   6. quiz      小测验：quiz(中文题, 英文题, [(选项中文, 选项英文), ...], 正确选项编号(从0数), 中文解析, 英文解析)
#   7. (可选) 掩膜名称 (中文, 英文)：这一步用到的光刻掩膜 (mask)
#
# 关于 lambda：参数表里经常出现 “lambda c: "<100>"”。lambda 是一种“一行写完的小函数”：
#   lambda c: 表达式   等价于   def 无名函数(c): return 表达式
# 这里的 c 是上下文 Ctx。之所以写成函数而不是直接写文字，是因为很多数值 (如掺杂浓度、阈值电压)
# 要等用户在“参数”页拖动滑块后才知道，必须在显示时才现算。对于固定文字也统一写成 lambda，格式一致。
#
# 关于 litho(保留区域, mask=...)：它会展开成“涂光刻胶 → 掩膜对准曝光 → 显影”三个阶段。
#   “保留区域”是光刻胶要留下的地方 (被遮住、不曝光)，其余地方的胶在显影时被溶掉，露出下面的晶圆。
# ==========================================================================================
STEPS: List[Step] = [
    # ---- 第 1 步：起始硅片 ----
    # 物理上：拿一片轻掺硼的 P 型单晶硅片。P 型衬底本身就可以直接做 NMOS。
    # 3D 模型里：建立 "sub" (substrate，衬底) 这一层：x 0-20，y 0-8，z 从 -SUB_DEPTH (硅片内部) 到 0 (表面)。
    Step("wafer", ("P 型硅衬底", "p-type silicon wafer"),
         ("工艺从轻掺杂硼的 <100> 晶向 P 型单晶硅片开始。NMOS 直接做在 P 型衬底上，"
          "PMOS 之后要做在 N 阱里。<100> 晶向界面态密度低，适合 MOS 器件。",
          "We start from a lightly boron-doped <100> p-type single-crystal wafer. NMOS devices "
          "are built directly in the p-substrate; PMOS devices will sit in an n-well. <100> "
          "gives the lowest interface-trap density."),
         # 参数表。sci(数值, 单位) 把数字写成科学计数法文字，例如 5e16 → "5×10^16 cm^-3"。
         # c.p.na_cm3 是用户可调的衬底掺杂浓度 (每立方厘米多少个硼原子)。
         [("晶向", "Orientation", lambda c: "<100>"),
          ("衬底/沟道掺杂 Na (硼)", "Substrate/channel Na (B)", lambda c: sci(c.p.na_cm3, "cm^-3")),
          ("硅片直径", "Wafer diameter", lambda c: "200 mm")],
         # replace_layer：用新的形状替换 (或新建) 一层。这里新建衬底方块。
         [Phase("准备硅片 (RCA 清洗)", "Wafer preparation (RCA clean)", 1.0,
                [replace_layer("sub", "p_sub", lambda c: [Solid.box(0, 20, 0, 8, -SUB_DEPTH, 0)])])],
         quiz("为什么 CMOS 常用 <100> 晶向硅片？", "Why are <100> wafers preferred for CMOS?",
            [("硬度最高", "Highest hardness"), ("Si/SiO2 界面态密度最低", "Lowest Si/SiO2 interface-trap density"),
             ("最便宜", "Cheapest"), ("导热最好", "Best thermal conductivity")], 1,
            "<100> 面悬挂键少，界面态密度低，阈值电压更稳定、迁移率更高。",
            "The <100> surface has fewer dangling bonds, so interface traps are lowest.")),

    # ---- 第 2 步：垫氧化 ----
    # 物理上：在高温氧气里让硅表面长一层很薄的二氧化硅 (SiO2)。
    # 为什么需要它：后面要盖一层氮化硅 (Si3N4)，氮化硅和硅的热膨胀不同，直接贴在硅上会产生
    # 很大的应力，把硅晶格压出缺陷。薄薄的“垫氧”像一层软垫，起缓冲作用。
    # 3D 模型里：整片晶圆淀积 0.06 显示单位厚的 "padox" 层，同时播放 950°C 退火的发光效果。
    # anneal(温度°C, 时间秒, 颜色) 除了发光，还会把这次加热记录下来 (用于计算“热预算”)。
    Step("padox", ("垫氧化 (热氧化)", "Pad oxidation"),
         ("在 900-1000°C 干氧中生长一层约 20 nm 的薄 SiO2。这层“垫氧”用来缓冲后面"
          "氮化硅与硅之间的巨大应力，同时在离子注入时作为屏蔽层。",
          "A thin (~20 nm) SiO2 is grown in dry O2 at 900-1000 °C. This pad oxide buffers the "
          "stress between the later nitride and silicon and acts as a screen oxide for implants."),
         [("温度", "Temperature", lambda c: "950 °C, 干氧 / dry O2"),
          ("厚度", "Thickness", lambda c: "≈ 20 nm"),
          ("反应", "Reaction", lambda c: "Si + O2 → SiO2")],
         [Phase("热氧化生长 SiO2", "Thermal oxide growth", 1.5,
                [deposit("padox", "pad_ox", thickness=0.06), anneal(950, 1800, (1.0, 0.5, 0.2))])],
         quiz("热氧化时，SiO2 中约有多少厚度来自消耗的硅？", "During thermal oxidation, what fraction of the oxide thickness consumes silicon?",
            [("0%", "0%"), ("约 44%", "About 44%"), ("100%", "100%"), ("约 10%", "About 10%")], 1,
            "生长 1 nm SiO2 约消耗 0.44 nm 硅，所以氧化层有一部分“长进”硅里。",
            "Growing 1 nm of SiO2 consumes ~0.44 nm of Si, so the oxide partly grows into the wafer.")),

    # ---- 第 3 步：N 阱光刻 (第 1 块掩膜) ----
    # 物理上：涂光刻胶、透过掩膜用紫外光照射、显影，把将来做 N 阱的右半边“开窗”露出来。
    # 为什么：PMOS 必须做在 N 型硅里，而衬底是 P 型，所以要在右半边局部做一个 N 型区域 (N 阱)。
    #   光刻胶就是“模板”，决定下一步离子注入打到哪里。
    # 3D 模型里：litho 的“保留区域”是 c.lay["pside"] (左半边 P 型区，x 0-10.5)，
    #   所以胶留在左边、右边被打开。lambda c: [...] 返回一个只含一个矩形的列表。
    Step("nwell_litho", ("N 阱光刻 (掩膜 1)", "N-well lithography (mask 1)"),
         ("旋涂正性光刻胶，用 N 阱掩膜对准后紫外曝光。正胶曝光部分在显影液中溶解，"
          "露出将要做 N 阱的区域；其余区域仍被光刻胶保护。",
          "Positive photoresist is spun on, aligned to the N-well mask and exposed to UV. Exposed "
          "positive resist dissolves in the developer, opening the future N-well region."),
         [("光刻胶", "Resist", lambda c: "正胶 / positive, ~1 µm"),
          ("光源", "Source", lambda c: "i-line 365 nm"),
          ("掩膜", "Mask", lambda c: "#1 NWELL")],
         litho(lambda c: [c.lay["pside"]], mask="NWELL"),
         quiz("正性光刻胶被紫外光照射后会怎样？", "What happens to positive resist exposed to UV?",
            [("变硬并保留", "Hardens and stays"), ("在显影液中溶解", "Dissolves in developer"),
             ("变成金属", "Turns metallic"), ("不受影响", "Unaffected")], 1,
            "正胶曝光后分子链断裂、溶解度增大，显影时被去掉；负胶相反。",
            "UV breaks the positive resist chains so it dissolves; negative resist is the opposite."),
         # 第 7 个参数：本步使用的掩膜名称 (界面上显示)。
         ("N 阱", "NWELL")),

    # ---- 第 4 步：N 阱离子注入 ----
    # 物理上：把磷离子加速到很高能量“打”进硅里。光刻胶挡住左边，只有右边开窗处被掺成 N 型。
    # 为什么：形成 PMOS 需要的 N 型区。注入多少 (剂量) 决定 N 阱浓度，进而决定 PMOS 的阈值电压 Vtp
    #   (晶体管开始导通所需的栅电压)。剂量是用户可调参数 c.p.nwell_dose_cm2。
    # 3D 模型里：implant(层名, 材料, 注入区域, 注入深度底部 z=-0.3, 离子颜色, 离子种类, 剂量, 能量keV)。
    #   注入区域是 c.lay["nwell"] (x 10.5-20)。这时杂质还很浅，只到 z = -0.3。
    #   dose 也写成 lambda，这样用户改了剂量，计算出来的电学特性会跟着变。
    Step("nwell_implant", ("N 阱离子注入", "N-well ion implantation"),
         ("以光刻胶为掩蔽，注入磷离子 (P+)。离子在光刻胶中被挡住，只有窗口区域的硅被掺杂。"
          "注入剂量决定 N 阱浓度，进而决定 PMOS 的阈值电压。",
          "Phosphorus ions are implanted using the resist as a mask. Only the opened window is "
          "doped. The dose sets the well concentration and hence the PMOS threshold."),
         [("离子", "Species", lambda c: "P+ (磷 / phosphorus)"),
          ("剂量", "Dose", lambda c: sci(c.p.nwell_dose_cm2, "cm^-2")),
          ("能量", "Energy", lambda c: "≈ 150 keV"),
          ("推进后 Nd", "Nd after drive-in", lambda c: sci(c.p.nd_cm3, "cm^-3")),
          # vt_text(c, "p") 根据当前参数算出 PMOS 阈值电压并格式化成文字。
          ("→ PMOS Vtp", "→ PMOS Vtp", lambda c: vt_text(c, "p"))],
         [Phase("磷离子注入", "Phosphorus implant", 2.4,
                [implant("nimp", "n_implant", lambda c: [c.lay["nwell"]], -0.3, (1.0, 0.85, 0.2, 1),
                         species="P", dose=lambda c: c.p.nwell_dose_cm2, energy_kev=150)])],
         quiz("N 阱注入剂量升高，PMOS 的 |Vtp| 会？", "If the n-well dose increases, |Vtp| of the PMOS will…",
            [("增大", "Increase"), ("减小", "Decrease"), ("不变", "Stay the same"), ("变为 0", "Become zero")], 0,
            "阱浓度越高，耗尽电荷 Qdep 越大，需要更大的栅压才能反型，|Vtp| 增大。可在“参数”页验证。",
            "Higher Nd means larger depletion charge, so |Vtp| rises. Try it on the Parameters tab.")),

    # ---- 第 5 步：去胶 + 阱推进 ----
    # 物理上：先去掉光刻胶 (胶不耐高温)，再在约 1100°C 下长时间加热，让浅表的磷原子向深处扩散。
    # 为什么：注入只能打到很浅的地方，而 PMOS 需要一个足够深 (约 2 µm) 的 N 型“井”来容纳它；
    #   加热还能“激活”杂质 (让它们进入晶格位置才能导电) 并修复注入造成的晶格损伤。
    # 3D 模型里：
    #   strip("resist") 去掉光刻胶层；
    #   replace_layer 新建 "nwell" 层：x 10.5-20，深到 z = -1.8，以“生长”动画向下扩展。
    #     requires="nimp" 表示只有之前真的做过 N 阱注入才会出现 N 阱 (教学模式里可以故意跳过某步)。
    #   strip("nimp", "fade") 让原来那层浅注入淡出 (它已经“变成”了 N 阱)；
    #   anneal(1100, 6 * 3600, ...)：1100°C 加热 6 小时 (6×3600 秒)。
    Step("nwell_drive", ("去胶 + 阱推进退火", "Resist strip + well drive-in"),
         ("用氧等离子体/硫酸去除光刻胶，然后在约 1100°C 高温下长时间退火，"
          "使磷向深处扩散形成约 2 µm 深的 N 阱，并激活杂质、修复注入损伤。",
          "The resist is stripped (O2 plasma / piranha), then a long ~1100 °C anneal drives the "
          "phosphorus ~2 µm deep to form the well, activating dopants and repairing damage."),
         [("温度", "Temperature", lambda c: "1100 °C"),
          ("时间", "Time", lambda c: "≈ 6 h, N2"),
          ("阱深", "Well depth", lambda c: "≈ 2 µm")],
         [Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")]),
          Phase("高温推进：磷向下扩散", "High-temperature drive-in", 2.0,
                [replace_layer("nwell", "n_well", lambda c: [Solid.box(10.5, 20, 0, 8, -1.8, 0)],
                               anchor=0.0, mode="grow", requires="nimp"),
                 strip("nimp", "fade"),
                 anneal(1100, 6 * 3600, (1.0, 0.4, 0.1))])],
         quiz("阱推进退火的主要作用是？", "Main purpose of the drive-in anneal?",
            [("去除光刻胶", "Remove resist"), ("让杂质扩散到所需深度并激活", "Diffuse dopants deeper and activate them"),
             ("沉积金属", "Deposit metal"), ("刻蚀氧化层", "Etch oxide")], 1,
            "注入只在表面附近，高温推进让杂质扩散到所需深度。",
            "Implants are shallow; the high-temperature drive diffuses them to the target depth.")),

    # ---- 第 6 步：淀积氮化硅 ----
    # 物理上：用低压化学气相淀积 (LPCVD) 在整片晶圆上盖一层氮化硅 (Si3N4)。
    # 为什么：氧气几乎穿不过氮化硅。之后把它只留在有源区 (要做晶体管的地方) 上，
    #   再去高温氧化——被氮化硅盖住的地方不会长氧化层，没盖住的地方长出厚厚的隔离氧化层。
    # 3D 模型里：整片淀积 0.12 厚的 "nitride" 层 (叠在垫氧之上)，并播放绿色的淀积粒子动画。
    #   particles=("depo", 颜色) 指定粒子效果：depo = 从上方落下的淀积粒子。颜色 4 个数为 (红,绿,蓝,不透明度)。
    Step("nitride", ("氮化硅淀积 (LPCVD)", "Silicon nitride deposition"),
         ("用低压化学气相淀积 (LPCVD) 在整片晶圆上淀积约 100 nm Si3N4。"
          "氮化硅几乎不让氧扩散，后面将作为 LOCOS 局部氧化的掩蔽层。",
          "~100 nm Si3N4 is deposited by LPCVD. Nitride blocks oxygen diffusion, so it will mask "
          "the local oxidation (LOCOS) of the active areas."),
         [("方法", "Method", lambda c: "LPCVD 780 °C"),
          ("气体", "Gases", lambda c: "SiH2Cl2 + NH3"),
          ("厚度", "Thickness", lambda c: "≈ 100 nm")],
         [Phase("LPCVD 淀积 Si3N4", "LPCVD Si3N4", 1.6,
                [deposit("nitride", "nitride", thickness=0.12, particles=("depo", (0.4, 0.9, 0.5, 1)))])],
         quiz("为什么用氮化硅作 LOCOS 掩蔽层？", "Why is nitride used as the LOCOS mask?",
            [("导电性好", "It conducts well"), ("氧难以穿过氮化硅", "Oxygen barely diffuses through it"),
             ("透明", "It is transparent"), ("便于金属连接", "Helps metal contacts")], 1,
            "氮化硅的氧化速率极低，被它覆盖的区域不会长出厚场氧。",
            "Nitride oxidises extremely slowly, so covered regions do not grow field oxide.")),

    # ---- 第 7 步：有源区光刻 (第 2 块掩膜) ----
    # 物理上：再做一次光刻，让光刻胶只留在两个“有源区”上 (NMOS 区和 PMOS 区各一个矩形)。
    # 为什么：确定哪里做晶体管、哪里做隔离。胶留下的地方，下一步氮化硅也会被保留。
    # 3D 模型里：保留区域就是 actives (两个有源区矩形)。注意这里直接传函数名 actives，
    #   效果和 lambda c: actives(c) 一样——函数本身也可以当作参数传来传去。
    Step("active_litho", ("有源区光刻 (掩膜 2)", "Active-area lithography (mask 2)"),
         ("再次涂胶、对准有源区 (ACTIVE) 掩膜并曝光、显影。留下的光刻胶覆盖晶体管所在的“有源区”，"
          "其他区域之后要长厚场氧做隔离。",
          "Coat, align the ACTIVE mask, expose and develop. Resist remains over the active areas "
          "where transistors will be; everything else will become isolation field oxide."),
         [("掩膜", "Mask", lambda c: "#2 ACTIVE"),
          ("对准", "Alignment", lambda c: "对准 N 阱标记 / to NWELL marks")],
         litho(lambda c: actives(c), mask="ACTIVE"),
         quiz("“有源区”指的是？", "What is the 'active area'?",
            [("金属走线区", "Metal routing area"), ("晶体管沟道和源漏所在区域", "Where channels and source/drain sit"),
             ("场氧区", "Field-oxide area"), ("划片槽", "Scribe lane")], 1,
            "有源区就是将来做 MOS 管的薄氧区，其余为场区。",
            "Active areas host the transistors; the rest is field (isolation)."),
         ("有源区", "ACTIVE")),

    # ---- 第 8 步：刻蚀氮化硅 + 去胶 ----
    # 物理上：用等离子体把没有光刻胶保护的氮化硅刻掉，然后去掉光刻胶。
    # 为什么：结果是氮化硅只盖在有源区上，成为下一步“局部氧化”的挡板。
    # 3D 模型里：pattern(层名, 保留区域, mask=...) 把该层在保留区域以外的部分刻掉 (带等离子体粒子动画)。
    #   mask="ACTIVE" 让“故障教学模式”里的掩膜错位也能作用到这一步。
    Step("nitride_etch", ("氮化硅刻蚀 + 去胶", "Nitride etch + strip"),
         ("以光刻胶为掩蔽，用等离子体干法刻蚀去除场区的氮化硅，只在有源区保留氮化硅，再去掉光刻胶。",
          "Plasma etch removes the nitride from the field regions; nitride remains only on the "
          "active areas. Then the resist is stripped."),
         [("刻蚀", "Etch", lambda c: "RIE, CF4/O2"),
          ("终点", "Endpoint", lambda c: "光学终点检测 / optical")],
         [Phase("等离子体刻蚀 Si3N4", "Plasma etch Si3N4", 1.8, [pattern("nitride", actives, mask="ACTIVE")]),
          Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("干法刻蚀相比湿法刻蚀最大的优点？", "Main advantage of dry (plasma) etching over wet?",
            [("各向异性，图形更精确", "Anisotropic, better pattern fidelity"), ("更便宜", "Cheaper"),
             ("不需要掩膜", "No mask needed"), ("速度慢", "Slower")], 0,
            "反应离子刻蚀有方向性，侧向钻蚀小，适合细线条。",
            "RIE is directional with little undercut, ideal for fine features.")),

    # ---- 第 9 步：LOCOS 场氧化 (本工艺的标志性步骤) ----
    # 物理上：在湿氧 (含水汽) 中 1000°C 长时间氧化。没被氮化硅盖住的“场区”长出很厚 (约 0.5 µm) 的氧化层。
    # 为什么：相邻晶体管之间必须电气隔离，否则电流会从一个管子漏到另一个管子。厚场氧就是“绝缘围墙”。
    #   LOCOS = LOCal Oxidation of Silicon (硅的局部氧化)。缺点是会长出“鸟嘴”侵占有源区。
    # 3D 模型里：调用上面写好的 _locos 动作函数，再加 1000°C、4 小时的退火记录。
    #   nwe_text 显示“窄宽度效应”导致的阈值电压变化 (鸟嘴让晶体管实际宽度变窄)。
    Step("locos", ("场氧化 LOCOS", "Field oxidation (LOCOS)"),
         ("湿氧 1000°C 长时间氧化：没有氮化硅覆盖的场区长出约 0.5 µm 厚的场氧，用于器件间隔离。"
          "氧会从氮化硅边缘侧向钻入，形成“鸟嘴” (bird's beak)。",
          "Long wet oxidation at ~1000 °C grows ~0.5 µm field oxide where there is no nitride, "
          "isolating devices. Lateral oxidation under the nitride edge forms the 'bird's beak'."),
         [("温度", "Temperature", lambda c: "1000 °C, 湿氧 / wet O2"),
          ("场氧厚度", "FOX thickness", lambda c: "≈ 500 nm"),
          ("特征", "Feature", lambda c: "鸟嘴 / bird's beak"),
          ("窄宽度效应 ΔVtn", "Narrow-width ΔVtn", nwe_text)],
         [Phase("局部氧化：场氧生长", "Local oxidation grows field oxide", 2.6, [_locos, anneal(1000, 4 * 3600)])],
         quiz("LOCOS 的“鸟嘴”带来的主要问题是？", "Main drawback of the LOCOS bird's beak?",
            [("增加导电性", "Raises conductivity"), ("侵占有源区，限制集成度", "Eats into active area, limiting density"),
             ("让硅片变薄", "Thins the wafer"), ("降低温度", "Lowers temperature")], 1,
            "鸟嘴横向侵占有源区，因此先进工艺改用浅槽隔离 STI。",
            "The beak encroaches into the active area; advanced nodes switched to STI.")),

    # ---- 第 10 步：去掉氮化硅和垫氧 ----
    # 物理上：热磷酸只溶解氮化硅、几乎不伤氧化硅；然后稀氢氟酸 (HF) 去掉有源区上的薄垫氧。
    # 为什么：氮化硅“挡板”的任务完成了；有源区要露出干净的硅，下一步才能在上面长高质量的栅氧。
    #   (稀 HF 也会削掉一点场氧，但场氧很厚，影响不大。)
    # 3D 模型里：两层分别被整层去掉。
    Step("nitride_strip", ("去除氮化硅与垫氧", "Strip nitride and pad oxide"),
         ("用热磷酸 (约 160°C) 选择性去除氮化硅，再用稀 HF 去掉垫氧化层，露出干净的有源区硅表面。",
          "Hot phosphoric acid (~160 °C) removes the nitride selectively; a dilute HF dip removes "
          "the pad oxide, exposing clean silicon in the active areas."),
         [("Si3N4 去除", "Nitride removal", lambda c: "H3PO4, 160 °C"),
          ("SiO2 去除", "Oxide removal", lambda c: "稀 HF / dilute HF")],
         [Phase("热磷酸去除 Si3N4", "Hot H3PO4 removes nitride", 1.4, [strip("nitride")]),
          Phase("HF 去除垫氧", "HF removes pad oxide", 1.0, [strip("padox")])],
         quiz("为什么能单独去掉氮化硅而几乎不伤场氧？", "Why can nitride be removed without attacking the field oxide?",
            [("热磷酸对 Si3N4/SiO2 选择比很高", "Hot H3PO4 is highly selective to Si3N4 over SiO2"),
             ("场氧被光刻胶保护", "FOX is protected by resist"), ("运气", "Luck"), ("场氧是金属", "FOX is metal")], 0,
            "湿法刻蚀的选择比可达几十比一。", "Wet etches can have selectivities of tens to one.")),

    # ---- 第 11 步：栅氧化 ----
    # 物理上：在有源区的硅表面长一层非常薄、非常纯净的 SiO2，叫“栅氧” (gate oxide)。
    # 为什么：栅极 (开关的“控制端”) 和下面的沟道之间要隔一层绝缘体，栅电压通过它“隔空”吸引电荷形成导电沟道。
    #   栅氧越薄，栅对沟道的控制越强 (电容 Cox 越大)，晶体管电流越大、阈值越低——这是最关键的参数之一。
    #   厚度 tox 是用户可调参数 c.p.tox_nm。
    # 3D 模型里：只在有源区 (region=actives) 淀积 0.05 厚的 "gox" 层。
    #   f"..." 是“格式化字符串”：花括号 {} 里的表达式会被算出来填进文字，“:.1f” 表示保留 1 位小数。
    #   summarize_cached(...) 调用器件物理模型算出各种电学结果 (带缓存，重复调用不会重复计算)。
    Step("gate_ox", ("栅氧化", "Gate oxidation"),
         ("在有源区生长高质量的薄栅氧化层。栅氧厚度 tox 决定栅电容 Cox = εox/tox，"
          "直接影响阈值电压和驱动电流，是最关键的工艺参数之一。",
          "A high-quality thin gate oxide is grown on the active areas. Its thickness sets "
          "Cox = εox/tox, strongly affecting threshold voltage and drive current."),
         [("温度", "Temperature", lambda c: "900 °C, 干氧 / dry O2"),
          ("tox", "tox", lambda c: f"{c.p.tox_nm:.1f} nm"),
          # cox 的单位是 F/cm²，乘 1e7 换算成 fF/µm² 方便阅读。
          ("Cox", "Cox", lambda c: f"{summarize_cached(c.p, c.features).cox * 1e7:.2f} fF/µm²"),
          ("→ Vtn / Vtp", "→ Vtn / Vtp", lambda c: f"{vt_text(c, 'n')} / {vt_text(c, 'p')}")],
         [Phase("干氧生长栅氧", "Dry oxidation of gate oxide", 1.6,
                [deposit("gox", "gate_ox", thickness=0.05, region=actives), anneal(900, 1200, (1.0, 0.5, 0.2))])],
         quiz("栅氧变薄（其他不变），NMOS 驱动电流会？", "Thinner gate oxide (all else equal) makes NMOS drive current…",
            [("增大", "Increase"), ("减小", "Decrease"), ("不变", "Unchanged"), ("先减后增", "Decrease then increase")], 0,
            "Cox 增大 → k' = µCox 增大且 Vt 降低，电流增大。",
            "Larger Cox raises k' = µCox and lowers Vt, so current increases.")),

    # ---- 第 12 步：淀积多晶硅 ----
    # 物理上：在整片晶圆上淀积一层多晶硅 (许多小硅晶粒组成的硅膜)，它将被刻成栅极。
    # 为什么用多晶硅做栅：它耐高温，后面源漏注入后的高温退火不会把它熔化或破坏，
    #   所以可以“先做栅、再用栅当模板注入源漏” (自对准)。早期的铝栅就做不到这一点。
    # 3D 模型里：整片淀积 0.35 厚的 "poly" 层 (盖在栅氧和场氧上面)。
    Step("poly_dep", ("多晶硅淀积", "Polysilicon deposition"),
         ("用 LPCVD (约 620°C, SiH4 分解) 在整片晶圆上淀积约 300 nm 多晶硅，作为栅电极材料。",
          "~300 nm polysilicon is deposited by LPCVD (SiH4 pyrolysis at ~620 °C) as the gate electrode."),
         [("方法", "Method", lambda c: "LPCVD 620 °C"),
          ("气体", "Gas", lambda c: "SiH4 → Si + 2H2"),
          ("厚度", "Thickness", lambda c: "≈ 300 nm")],
         [Phase("LPCVD 多晶硅", "LPCVD polysilicon", 1.6,
                [deposit("poly", "poly", thickness=0.35, particles=("depo", (0.9, 0.55, 0.4, 1)))])],
         quiz("现代 CMOS 用多晶硅而非铝做栅，关键原因是？", "Key reason poly replaced Al as the gate?",
            [("更便宜", "Cheaper"), ("耐高温，可实现源漏自对准", "Withstands high temp → self-aligned S/D"),
             ("电阻更低", "Lower resistance"), ("颜色好看", "Looks nicer")], 1,
            "多晶硅能承受源漏注入后的高温退火，栅本身就是注入掩膜，实现自对准。",
            "Poly survives the S/D anneal, so the gate itself masks the implant: self-alignment.")),

    # ---- 第 13 步：栅极光刻 (第 3 块掩膜) ----
    # 物理上：光刻出栅极的图形——光刻胶只留在将来是栅极的细长条上。
    # 为什么：栅长 L (栅极在 x 方向的宽度) 是整个芯片上最细的线条，“1 µm 工艺”说的就是它。
    #   L 越短晶体管越快，但越难做。L 和晶体管宽度 Wn/Wp 都是用户可调参数。
    # 3D 模型里：保留区域 gates = NMOS 和 PMOS 栅极的矩形 (每个栅包括沟道上方部分和场氧上的接触垫)。
    Step("gate_litho", ("栅极光刻 (掩膜 3)", "Gate lithography (mask 3)"),
         ("涂胶并用 POLY 掩膜曝光、显影，定义栅极图形。栅长 L 是电路中最小的特征尺寸，"
          "决定工艺节点。",
          "Coat, expose with the POLY mask and develop to define the gates. The gate length L is "
          "the smallest feature and defines the technology node."),
         [("掩膜", "Mask", lambda c: "#3 POLY"),
          ("栅长 L", "Gate length L", lambda c: f"{c.p.l_um:.2f} µm"),
          ("宽度 Wn / Wp", "Wn / Wp", lambda c: f"{c.p.wn_um:.1f} / {c.p.wp_um:.1f} µm")],
         litho(gates, mask="POLY"),
         quiz("为什么 PMOS 的 W 通常比 NMOS 大？", "Why is PMOS W usually larger than NMOS W?",
            [("空穴迁移率低", "Hole mobility is lower"), ("PMOS 更容易制造", "PMOS is easier to make"),
             ("美观", "Aesthetics"), ("N 阱更大", "The n-well is larger")], 0,
            "µp 约为 µn 的 1/2~1/3，加大 Wp 使上拉、下拉电流平衡，VM≈VDD/2。",
            "µp ≈ µn/2..3, so Wp is enlarged to balance pull-up and pull-down (VM ≈ VDD/2)."),
         ("栅极", "POLY")),

    # ---- 第 14 步：刻蚀多晶硅栅 ----
    # 物理上：等离子体垂直向下刻掉没有胶保护的多晶硅，再把露出来的薄栅氧也去掉，最后去胶。
    # 为什么：留下的多晶硅条就是栅极；栅极以外的栅氧去掉，源漏区的硅就露出来，方便后面注入。
    # 3D 模型里：
    #   pattern("poly", gates) 只保留栅极处的多晶硅；
    #   pattern("gox", gates, particles=False) 只保留栅极下方的栅氧 (不再播放第二次粒子动画)；
    #   split_gates 把一整层 "poly" 按左右拆成 "gate_n" (NMOS 栅，x < 10.5) 和 "gate_p" (PMOS 栅)，
    #     这样后面两个栅可以分别被掺成 N+ 和 P+、显示不同颜色。
    Step("gate_etch", ("多晶硅栅刻蚀", "Poly gate etch"),
         ("各向异性等离子体刻蚀多晶硅，再刻去暴露的薄栅氧，只在栅极下方保留栅氧。随后去胶。",
          "Anisotropic plasma etch of the poly, then the exposed thin oxide is removed so gate "
          "oxide remains only under the gates. The resist is then stripped."),
         [("刻蚀", "Etch", lambda c: "RIE, Cl2/HBr"),
          ("选择比 poly:SiO2", "Selectivity poly:SiO2", lambda c: "> 50:1")],
         [Phase("刻蚀多晶硅", "Etch polysilicon", 1.8, [pattern("poly", gates, mask="POLY")]),
          Phase("去除暴露的栅氧", "Remove exposed gate oxide", 1.0, [pattern("gox", gates, particles=False, mask="POLY")]),
          Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist"), split_gates])],
         quiz("刻蚀多晶硅时为什么需要高 poly:SiO2 选择比？", "Why is high poly:SiO2 selectivity needed?",
            [("避免刻穿极薄栅氧伤及硅", "To stop on the very thin gate oxide without damaging Si"),
             ("加快速度", "Faster etch"), ("降低成本", "Lower cost"), ("改变颜色", "Change colour")], 0,
            "栅氧只有几 nm，选择比不够会刻穿到硅衬底。",
            "Gate oxide is only a few nm thick; poor selectivity punches through to silicon.")),

    # ---- 第 15 步：N+ 源漏注入 (第 4 块掩膜) ----
    # 物理上：光刻胶盖住右边的 PMOS 区，向左边 NMOS 有源区大剂量注入砷 (As，N 型杂质)。
    # 为什么：NMOS 的源极 (source) 和漏极 (drain) 必须是高浓度 N 型 (N+)，电子从源流向漏。
    #   多晶硅栅本身挡住了栅下方的沟道，所以源漏恰好落在栅的两侧——“自对准”，不怕光刻对不准。
    #   顺便多晶硅栅也被掺成 N+，导电性变好。
    # 3D 模型里：
    #   litho 保留区域是 nwell (右半边)，胶盖住 PMOS；“+” 把光刻的 3 个阶段和后面的阶段列表拼接起来。
    #   sd_rects(有源区, 栅的x范围) 计算出栅左右两边的两个矩形 = 源和漏。
    #   gate_span(c, "gn") 是 NMOS 栅的实际 x 范围 (考虑了故障模式下 POLY 掩膜的错位)。
    #   recolor("gate_n", "poly_n") 把 NMOS 栅的材料改成 N+ 多晶硅，换个颜色显示。
    Step("nplus", ("N+ 源漏注入 (掩膜 4)", "n+ source/drain implant (mask 4)"),
         ("光刻胶覆盖 PMOS 区域，向 NMOS 有源区注入砷 (As)。多晶硅栅本身挡住了沟道，"
          "源漏自动对准栅极两侧——“自对准”工艺。栅极多晶硅同时被掺成 N+。",
          "Resist covers the PMOS area; arsenic is implanted into the NMOS active area. The poly "
          "gate blocks the channel so source/drain align to it automatically (self-aligned), "
          "and the gate poly itself becomes n+."),
         [("离子", "Species", lambda c: "As+ (砷 / arsenic)"),
          ("剂量", "Dose", lambda c: "5e15 cm^-2"),
          ("能量", "Energy", lambda c: "≈ 60 keV"),
          ("掩膜", "Mask", lambda c: "#4 NSELECT")],
         litho(lambda c: [c.lay["nwell"]], mask="NSELECT") + [
             Phase("砷离子注入 (自对准)", "Arsenic implant (self-aligned)", 2.4,
                   [implant("nplus", "n_plus", lambda c: sd_rects(c.lay["act_n"], gate_span(c, "gn")), -0.3,
                            (1.0, 0.35, 0.3, 1), species="As", dose=5e15, energy_kev=60), recolor("gate_n", "poly_n")]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("源漏“自对准”指的是？", "What does 'self-aligned' source/drain mean?",
            [("用栅极本身作注入掩膜", "The gate itself masks the implant"),
             ("机器自动对准", "The stepper aligns automatically"), ("不需要退火", "No anneal needed"),
             ("源漏用同一掩膜", "S and D share a mask")], 0,
            "栅极挡住沟道区，源漏边缘自然与栅边缘对齐，消除了套刻误差。",
            "The gate shadows the channel, so S/D edges line up with the gate without overlay error."),
         ("N+ 选择", "NSELECT")),

    # ---- 第 16 步：P+ 源漏注入 (第 5 块掩膜) ----
    # 物理上：和上一步对称——这次光刻胶盖住左边 NMOS，向右边 N 阱里的 PMOS 区注入硼 (P 型杂质)。
    # 为什么：PMOS 的源漏是 P+，靠“空穴”导电；同样以栅为模板自对准，PMOS 栅也被掺成 P+。
    # 3D 模型里：保留区域是 pside (左半边)；注入区域是 PMOS 栅两侧的源漏矩形。
    Step("pplus", ("P+ 源漏注入 (掩膜 5)", "p+ source/drain implant (mask 5)"),
         ("光刻胶覆盖 NMOS 区域，向 N 阱中的 PMOS 有源区注入硼 (B 或 BF2)，同样以栅为掩膜自对准，"
          "PMOS 的多晶硅栅被掺成 P+。",
          "Resist covers the NMOS area; boron (B or BF2) is implanted into the PMOS active area in "
          "the n-well, again self-aligned to the gate, which becomes p+ poly."),
         [("离子", "Species", lambda c: "BF2+ (硼 / boron)"),
          ("剂量", "Dose", lambda c: "3e15 cm^-2"),
          ("能量", "Energy", lambda c: "≈ 40 keV"),
          ("掩膜", "Mask", lambda c: "#5 PSELECT")],
         litho(lambda c: [c.lay["pside"]], mask="PSELECT") + [
             Phase("硼离子注入 (自对准)", "Boron implant (self-aligned)", 2.4,
                   [implant("pplus", "p_plus", lambda c: sd_rects(c.lay["act_p"], gate_span(c, "gp")), -0.3,
                            (0.4, 0.6, 1.0, 1), species="BF2", dose=3e15, energy_kev=40), recolor("gate_p", "poly_p")]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("PMOS 的源漏是什么类型掺杂？", "What doping type are PMOS source/drain?",
            [("N+", "n+"), ("P+", "p+"), ("本征", "Intrinsic"), ("与衬底相同", "Same as substrate")], 1,
            "PMOS 在 N 阱中，源漏是 P+，沟道反型层为空穴。",
            "PMOS sits in the n-well with p+ S/D; its inversion layer is made of holes.")),

    # ---- 第 17 步：源漏激活退火 ----
    # 物理上：快速热退火 (RTA)：几秒钟内升到约 1000°C 再降下来。
    # 为什么：刚注入的杂质大多还“挤”在晶格缝隙里、不导电，晶格也被打乱了；加热让杂质就位 (激活) 并修复损伤。
    #   时间要短，是为了让杂质只扩散一点点：稍微钻到栅下面一点，使源漏和沟道接上，但不能扩散太多。
    # 3D 模型里：用 sd_annealed 生成退火后的源漏形状 (向栅下方横向多伸出一点、深度变为约 -0.42)
    #   替换原来的注入层。requires 保证只有真的注入过才会出现。
    Step("sd_anneal", ("源漏激活退火 (RTA)", "Source/drain activation anneal"),
         ("快速热退火 (RTA, 约 1000°C 数秒) 激活注入杂质、修复晶格损伤。杂质略向侧向扩散，"
          "使源漏与栅形成少量交叠，保证沟道连通。",
          "Rapid thermal anneal (~1000 °C, seconds) activates the dopants and repairs damage. "
          "Slight lateral diffusion gives a small gate overlap so the channel connects."),
         [("方法", "Method", lambda c: "RTA 1000 °C, 10 s"),
          ("结深 xj", "Junction depth xj", lambda c: "≈ 0.2 µm")],
         [Phase("快速热退火：激活 + 侧向扩散", "RTA: activation + lateral diffusion", 2.0,
                [replace_layer("nplus", "n_plus", lambda c: sd_annealed(c.lay["act_n"], gate_span(c, "gn")),
                               requires="nplus"),
                 replace_layer("pplus", "p_plus", lambda c: sd_annealed(c.lay["act_p"], gate_span(c, "gp")),
                               requires="pplus"),
                 anneal(1000, 10, (1.0, 0.35, 0.1))])],
         quiz("为什么源漏退火要用“快速”热退火？", "Why use a *rapid* thermal anneal for S/D?",
            [("激活杂质同时限制扩散，保持浅结", "Activate dopants while limiting diffusion (shallow junctions)"),
             ("省电", "Save power"), ("去除光刻胶", "Remove resist"), ("长氧化层", "Grow oxide")], 0,
            "热预算越小，结越浅，短沟道效应越弱。",
            "A small thermal budget keeps junctions shallow and limits short-channel effects.")),

    # ---- 第 18 步：层间介质 (ILD) ----
    # 物理上：在整片晶圆上盖一层厚厚的玻璃 (掺硼磷的二氧化硅 BPSG)，再加热让它稍微“流动”变平。
    # 为什么：上面要走金属导线，导线不能随便碰到下面的栅和源漏，否则就短路了。ILD 是中间的绝缘层；
    #   表面越平，后面光刻越容易对焦。
    # 3D 模型里：top=1.3 表示把介质一直填到 z = 1.3 的高度 (表面变平)，而不是固定厚度。
    Step("ild", ("层间介质淀积 (BPSG)", "Inter-layer dielectric (BPSG)"),
         ("CVD 淀积约 0.8 µm 掺硼磷硅玻璃 (BPSG)，再高温回流使表面平坦化。ILD 把多晶硅/有源区与上层金属隔开。",
          "~0.8 µm boro-phospho-silicate glass is deposited by CVD and reflowed for planarity. "
          "The ILD isolates poly/active from the metal above."),
         [("材料", "Material", lambda c: "BPSG"),
          ("厚度", "Thickness", lambda c: "≈ 0.8 µm"),
          ("回流", "Reflow", lambda c: "850 °C")],
         [Phase("CVD 淀积 + 回流平坦化", "CVD + reflow planarisation", 1.8,
                [deposit("ild", "ild", top=1.3, particles=("depo", (0.95, 0.95, 0.8, 1)))])],
         quiz("BPSG 中掺硼、磷的主要目的？", "Why add boron and phosphorus to the glass (BPSG)?",
            [("降低回流温度，便于平坦化", "Lower the reflow temperature for planarisation"),
             ("提高导电性", "Increase conductivity"), ("改变颜色", "Change colour"), ("作为源漏", "Act as S/D")], 0,
            "B、P 降低玻璃软化点，低温即可回流填平台阶（P 还能吸除钠离子）。",
            "B and P lower the softening point so it flows at lower temperature (P also getters Na+).")),

    # ---- 第 19 步：接触孔 (第 6 块掩膜) ----
    # 物理上：在绝缘层上精确地“打洞”，洞底分别落在源、漏和栅极上。
    # 为什么：金属导线要通过这些孔才能和下面的晶体管电极连通。
    # 3D 模型里：光刻胶要保留的是“除了接触孔以外的所有地方”，
    #   所以用 rect_complement(DOMAIN, contacts(c)) 求出整个区域去掉接触孔矩形后的部分；
    #   pattern("ild", 同样的区域) 就把孔里的 ILD 刻掉了。
    Step("contact", ("接触孔光刻与刻蚀 (掩膜 6)", "Contact lithography & etch (mask 6)"),
         ("涂胶并用 CONTACT 掩膜曝光显影，再各向异性刻蚀 ILD，打开到源、漏和栅极的接触孔，最后去胶。",
          "Coat, expose the CONTACT mask, develop, then anisotropically etch the ILD to open "
          "holes down to source, drain and gate. Strip resist."),
         [("掩膜", "Mask", lambda c: "#6 CONTACT"),
          ("刻蚀", "Etch", lambda c: "RIE, CHF3/CF4"),
          # len(...) 是“个数”。c.lay['contacts'] 是一个字典，记录每个接触孔的位置。
          ("孔数", "Contacts", lambda c: f"{len(c.lay['contacts'])}")],
         litho(lambda c: rect_complement(DOMAIN, contacts(c)), mask="CONTACT") + [
             Phase("刻蚀接触孔", "Etch contact holes", 1.6,
                   [pattern("ild", lambda c: rect_complement(DOMAIN, contacts(c)), mask="CONTACT")]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("接触孔刻蚀应停在哪里？", "Where should the contact etch stop?",
            [("硅/多晶硅表面", "On the silicon / poly surface"), ("衬底底部", "Bottom of the wafer"),
             ("光刻胶中", "Inside the resist"), ("场氧中", "Inside the field oxide")], 0,
            "需要刚好露出源漏硅和栅多晶硅，过刻会损伤浅结。",
            "It must expose S/D silicon and gate poly; over-etch can damage shallow junctions."),
         ("接触孔", "CONTACT")),

    # ---- 第 20 步：溅射铝 ----
    # 物理上：用“溅射” (高能离子撞击铝靶，把铝原子撞下来落到晶圆上) 在整片晶圆上铺一层铝。
    # 为什么：铝导电好、便宜，它会填进接触孔，和下面的电极接通；下一步再刻成一根根导线。
    # 3D 模型里：铝层一直填到 z = 1.65 (比 ILD 顶面 1.3 高出 0.35，就是铝线的厚度)。
    Step("metal_dep", ("金属淀积 (溅射铝)", "Metal deposition (Al sputter)"),
         ("用磁控溅射在整片晶圆上淀积 Al (含少量 Si/Cu)，填充接触孔并覆盖表面。",
          "Aluminium (with a little Si/Cu) is sputtered over the wafer, filling the contact holes."),
         [("方法", "Method", lambda c: "磁控溅射 / magnetron sputter"),
          ("材料", "Material", lambda c: "Al-1%Si-0.5%Cu"),
          ("厚度", "Thickness", lambda c: "≈ 0.6 µm")],
         [Phase("溅射铝", "Sputter aluminium", 1.8,
                [deposit("metal", "metal", top=1.65, particles=("depo", (0.85, 0.87, 0.9, 1)))])],
         quiz("铝中加入少量硅的目的？", "Why add a little Si to the aluminium?",
            [("防止铝穿刺浅结 (spiking)", "Prevent Al spiking into shallow junctions"),
             ("提高亮度", "Make it shinier"), ("降低熔点", "Lower its melting point"), ("增加电阻", "Raise resistance")], 0,
            "Si 在 Al 中有溶解度，预先饱和可防止 Al 吞噬衬底硅造成结短路。",
            "Pre-saturating Al with Si stops it from dissolving substrate Si and shorting junctions.")),

    # ---- 第 21 步：金属光刻与刻蚀 (第 7 块掩膜) ----
    # 物理上：光刻出导线图形，把多余的铝刻掉，剩下 4 根导线。
    # 为什么：这 4 根线把两个晶体管连成反相器：GND (地) 接 NMOS 源，VDD (电源) 接 PMOS 源，
    #   两个漏接在一起作输出 Vout，两个栅接在一起作输入 Vin。
    # 3D 模型里：metal(c) 返回这 4 根导线的矩形，既是光刻胶保留区域，也是铝的保留区域。
    Step("metal_pattern", ("金属光刻与刻蚀 (掩膜 7)", "Metal patterning (mask 7)"),
         ("涂胶、用 METAL1 掩膜曝光显影，刻蚀铝形成互连：GND 连 NMOS 源，VDD 连 PMOS 源，"
          "两个漏极连在一起作输出 Vout，两个栅极连在一起作输入 Vin，构成 CMOS 反相器。",
          "Coat, expose METAL1, develop and etch the Al into wires: GND to NMOS source, VDD to "
          "PMOS source, both drains tied as Vout, both gates tied as Vin: a CMOS inverter."),
         [("掩膜", "Mask", lambda c: "#7 METAL1"),
          ("刻蚀", "Etch", lambda c: "RIE, Cl2/BCl3")],
         litho(metal, mask="METAL1") + [
             Phase("刻蚀铝", "Etch aluminium", 1.8, [pattern("metal", metal, mask="METAL1")]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("这个反相器中，NMOS 的源极接到？", "In this inverter, the NMOS source connects to…",
            [("VDD", "VDD"), ("GND", "GND"), ("Vout", "Vout"), ("Vin", "Vin")], 1,
            "NMOS 做下拉，源接 GND；PMOS 做上拉，源接 VDD。",
            "NMOS pulls down (source at GND); PMOS pulls up (source at VDD)."),
         ("金属 1", "METAL1")),

    # ---- 第 22 步：完成 ----
    # 物理上：最后在氢氮混合气中低温退火 (合金退火)，改善金属-硅接触、修复栅氧界面。
    # 3D 模型里：几何不再变化，只播放一个淡黄色发光效果 (glow)。
    # 参数表显示最终电学结果：阈值电压、VM (输出翻转时的输入电压)、tpHL/tpLH (输出由高变低/由低变高的延迟)。
    #   延迟单位是秒，乘 1e12 换算成皮秒 ps。
    Step("done", ("完成：CMOS 反相器", "Done: CMOS inverter"),
         ("前端器件与第一层金属完成。(实际芯片还需要合金退火、阱/衬底接触、多层金属和钝化层，此处省略。)"
          "切换到右侧“特性”页，拖动 Vin 观察反相器工作：Vin 低时 PMOS 导通输出高，Vin 高时 NMOS 导通输出低。",
          "Front-end devices and metal 1 are done (alloy anneal, well/substrate taps, more metal "
          "and passivation are omitted). Open the 'Characteristics' tab and drag Vin: low Vin "
          "turns the PMOS on (Vout high), high Vin turns the NMOS on (Vout low)."),
         [("Vtn / Vtp", "Vtn / Vtp", lambda c: f"{vt_text(c, 'n')} / {vt_text(c, 'p')}"),
          ("VM", "VM", lambda c: f"{summarize_cached(c.p, c.features).vtc.vm:.3f} V"),
          ("tpHL / tpLH", "tpHL / tpLH",
           lambda c: f"{summarize_cached(c.p, c.features).tran.tphl * 1e12:.1f} / {summarize_cached(c.p, c.features).tran.tplh * 1e12:.1f} ps")],
         [Phase("合金退火 (H2/N2 425°C)", "Forming-gas alloy anneal", 1.2, [glow((0.9, 0.9, 0.5))])],
         quiz("CMOS 反相器静态功耗很低的原因？", "Why is CMOS inverter static power so low?",
            [("稳态时总有一个管子截止，无直流通路", "In steady state one transistor is off: no DC path"),
             ("电压很低", "Very low voltage"), ("用了铝", "Aluminium wiring"), ("场氧很厚", "Thick field oxide")], 0,
            "输出稳定时上拉/下拉中总有一个关断，只有微小的漏电流。",
            "With the output settled, either pull-up or pull-down is off; only leakage flows.")),
]



# 3D label anchors: (layer, zh, en, x, z)
# 3D 画面里的区域文字标签。每项是 (所属层名, 中文, 英文, x 位置, z 位置)。
# 只有当该层存在时才显示标签 (例如做完 N 阱推进后才出现“N 阱”)。
# z 为负数 = 标签在硅里面；例如 n+ 标签在 z = -0.55，正好位于源漏区下方附近。
REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("fox", "场氧", "FOX", 10.25, 0.75),
    ("nplus", "n+", "n+", 3.2, -0.55),
    ("nplus", "n+", "n+", 7.5, -0.55),
    ("pplus", "p+", "p+", 13.0, -0.55),
    ("pplus", "p+", "p+", 17.3, -0.55),
]

# 四个电路端子 (导线) 的名称标签：(名字, x 位置, y 位置)。
# 例如 GND 在左边 NMOS 源极上方，VDD 在右边 PMOS 源极上方，Vout 在中间，Vin 在后方 (y 较大处) 的栅连线上。
TERMINAL_LABELS = [
    ("GND", 3.35, 1.0), ("Vout", 10.25, 3.5), ("VDD", 17.15, 1.0), ("Vin", 12.8, 7.1),
]


# 把上面所有内容打包成一个 Flow (完整工艺流程) 对象，供 flows/__init__.py 登记、界面选择。
FLOW = Flow(
    # 内部名字。
    key="locos",
    # 界面上显示的名称 (中, 英)。
    name=("经典 LOCOS 工艺", "Classic LOCOS"),
    # 一句话介绍这一代工艺。
    node=("约 1.0 µm 代：LOCOS 隔离 + 单 N 阱",
          "~1.0 µm era: LOCOS + single n-well"),
    steps=STEPS,
    # “特性标签”：告诉器件物理模型这一代有哪些特点 ("locos" = 有鸟嘴/窄宽度效应，"sce" = 计算短沟道效应)。
    # frozenset 是“不可修改的集合”。
    features=frozenset({"locos", "sce"}),
    region_labels=REGION_LABELS,
    terminal_labels=TERMINAL_LABELS,
    # 这一代工艺的典型参数 (用户选中此工艺时，“参数”页滑块的初始值)：
    #   栅氧 20 nm、衬底掺杂 5e16 cm^-3、N 阱剂量 1e13 cm^-2、栅长 1 µm、NMOS 宽 4 µm、PMOS 宽 10 µm、
    #   电源电压 5 V、负载电容 100 fF。dict(a=1, b=2) 是创建字典的另一种写法。
    defaults=dict(tox_nm=20.0, na_cm3=5e16, nwell_dose_cm2=1e13, l_um=1.0, wn_um=4.0, wp_um=10.0,
                  vdd=5.0, cload_ff=100.0),
)
