"""~28 nm planar CMOS: high-k / metal gate (gate-last), embedded SiGe S/D, NiSi, Cu.

The last planar bulk generation.  New relative to the 0.25 µm STI flow:
dummy poly gate + replacement metal gate, HfO2 high-k, dual work-function
metals, recessed SiGe source/drain for PMOS strain, spike + laser anneal,
nickel silicide, self-aligned contacts and damascene copper.

【中文说明 —— 这个文件是干什么的？】
本文件描述“28 nm 平面高 k 金属栅 (HKMG) 工艺”这一整条工艺流程 (flow)。
所谓“工艺流程”，就是把一片光秃秃的硅片一步一步加工成一个 CMOS 反相器
(一个 NMOS 管 + 一个 PMOS 管) 的全部步骤清单。

程序里一条工艺流程 = 一份“数据清单” (下面的 STEPS 列表) + 几个小函数：
  * 每一步 (Step) 写明：标题、给初学者看的说明文字、参数表、动画分几个阶段 (Phase)、一道小测验 (quiz)；
  * 每个阶段里的动作 (deposit 淀积、recess 刻凹槽、implant 离子注入、anneal 退火……)
    会去修改屏幕上的 3D 硅片模型，所以你能看到薄膜一层层长出来、被刻掉。
  * 文件最后的 FLOW 把这些打包成一个对象，主程序在“工艺选择”菜单里列出它。

这一代 (约 2011 年) 是最后一代“平面”晶体管 —— 沟道还平躺在硅表面上。
和老的 0.25 µm STI 工艺相比，新增的关键技术有：
  1. 后栅工艺：先做一个“伪栅”(假的多晶硅栅) 占位，高温步骤做完后再挖掉，换成真正的金属栅；
  2. 高 k 介质 HfO2：比 SiO2 介电常数大，物理上可以做厚一点、漏电少，电学上却等效于很薄的氧化层；
  3. 双功函数金属：NMOS、PMOS 用不同的金属，以分别设定各自的阈值电压 Vt；
  4. 嵌入式 SiGe 源漏：给 PMOS 沟道加压应力，让空穴跑得更快；
  5. 尖峰退火 + 激光退火、镍硅化物 (NiSi)、自对准接触孔、大马士革铜互连。

很多步骤直接复用了 sti.py 里 0.25 µm 工艺的步骤 (只改改文字或参数)，
共用的“现代工艺”步骤 (ILD0、去伪栅、HKMG、接触孔、铜) 放在 _modern.py 里。

【坐标约定】(本文件里出现的数字都按这个理解)
  x = 屏幕左右方向 (源 -> 栅 -> 漏 的方向；NMOS 在左半边，PMOS 在右半边)；
  y = 垂直于屏幕、往里的深度方向 (也就是剖面切开的方向)；
  z = 向上；硅片原始表面在 z = 0，z < 0 是硅里面，z > 0 是硅表面上面长出来的薄膜。
  数字是“显示单位”，不是真实纳米；为了看得清，竖直方向 (z) 被大大放大了。
"""
# 让类型注解 (形如 "-> List[Solid]" 的写法) 推迟解析；对初学者来说可以忽略这一行。
from __future__ import annotations

# replace(旧对象, 字段=新值)：复制一个已有的“步骤”对象，只改其中几个字段，其他保持不变。
# 本文件大量用它来“借用” sti.py 的步骤，再改一下说明文字。
from dataclasses import replace

# “from ..xxx import yyy”：从上一级目录的 xxx 模块里拿来 yyy 来用 (两个点 = 上一级包)。
# Solid 是 3D 模型里的一个实体块 (比如一块长方体的硅、一块 SiGe)。
from ..geometry import Solid
# process_core 里是所有工艺动作的“积木”：deposit 淀积、implant 注入、anneal 退火、recess 刻凹槽、
# strip 去除一层、litho 光刻、quiz 出题 …… 以及 Flow/Phase/Step 这些描述流程的数据结构。
from ..process_core import (Flow, Phase, Step, add_solids, anneal, deposit, gate_span, implant, litho,
                            quiz, recess, replace_layer, sd_annealed, sd_rects, spacer_span, strip,
                            summarize_cached)
# 同一目录 (一个点) 下的另外两条老工艺流程，这里要复用它们的步骤和标签。
from . import locos, sti
# _modern.py 里是 28 nm、FinFET 等“现代”工艺共用的步骤生成函数。
from ._modern import (EPI_NOTE, contact_step, copper_m1_step, done_step, hkmg_step, ild0_step,
                      rmg_remove_step)

# 把 sti.py 的步骤列表做成一本“字典”：用步骤名 (key，比如 "padox") 就能查到那一步。
# {a: b for s in 列表} 叫“字典推导式”，意思是：对列表里每个 s，存一条 “s.key -> s”。
# 之后写 _S["padox"] 就等于“0.25 µm STI 工艺里的长垫氧化层那一步”。
_S = {s.key: s for s in sti.STEPS}

# 伪栅顶部的高度 (z)：牺牲氧化层 0.05 + 伪栅多晶硅 0.35 = 0.40。
# 后面的 ILD0 介质层会填到这个高度并用 CMP 磨平，正好露出伪栅顶面，方便把伪栅挖掉。
GATE_TOP = 0.40          # dummy oxide 0.05 + dummy poly 0.35
# SiGe 源漏块的底部和顶部高度：先把硅往下刻到 z = -0.28，再外延长 SiGe 一直长到 z = +0.12，
# 也就是比原来的硅表面还高出一点 (“抬高的源漏”)。“a, b = 1, 2” 是一次给两个变量赋值的写法。
SIGE_BOT, SIGE_TOP = -0.28, 0.12


def _sd_n(c):
    """NMOS 的源区和漏区在俯视图上的两个矩形。

    c 是“上下文”(context)：里面有工艺参数 c.p 和版图 c.lay (各区域的矩形坐标)。
    有源区 act_n 去掉“栅 + 两侧侧墙”所占的那一段，剩下左右两块就是源和漏。
    为什么要扣掉侧墙？因为深的源漏注入要离沟道远一点，侧墙正好当“隔离垫片”。
    函数名前面的下划线 _ 表示“只在本文件内部使用”。
    """
    return sd_rects(c.lay["act_n"], spacer_span(c, "gn"))


def _sd_p(c):
    """PMOS 的源区和漏区矩形 (做法同 _sd_n，只是换成 PMOS 的有源区和栅)。"""
    return sd_rects(c.lay["act_p"], spacer_span(c, "gp"))


def _sige(c):
    """生成 PMOS 源漏处要“长出来”的 SiGe 立体块 (每个源/漏各一块)。

    每块从 SIGE_BOT (凹槽底) 一直到 SIGE_TOP (高出硅表面)。
    anchor (锚点) = 底部高度，表示动画里这块材料是“从底部往上长”出来的，符合外延生长的样子。
    """
    out = []
    for r in _sd_p(c):
        # r 是一个矩形 (x0, x1, y0, y1)；r[0] 表示取第 0 个数 (Python 从 0 开始数)。
        # Solid.box(x0, x1, y0, y1, z0, z1) 造一个长方体。
        s = Solid.box(r[0], r[1], r[2], r[3], SIGE_BOT, SIGE_TOP)
        s.anchor = SIGE_BOT
        out.append(s)
    return out


def _nisi(c):
    """生成镍硅化物 (NiSi) 薄层：盖在每个源漏表面上的一层很薄的导电“皮”。

    NMOS 源漏的表面就是原来的硅表面 z = 0，所以薄层在 -0.04 ~ +0.02；
    PMOS 源漏表面是 SiGe 的顶 SIGE_TOP，所以薄层贴着 SIGE_TOP 做。
    (硅化物一半“吃进”硅里，一半略高出表面，所以上下各占一点。)
    方括号里带 for 的写法叫“列表推导式”：对每个矩形 r 造一个块，收集成一个列表。
    """
    out = [Solid.box(r[0], r[1], r[2], r[3], -0.04, 0.02) for r in _sd_n(c)]
    out += [Solid.box(r[0], r[1], r[2], r[3], SIGE_TOP - 0.04, SIGE_TOP + 0.02) for r in _sd_p(c)]
    return out


# ==========================================================================
# STEPS：整条工艺的步骤清单，按从上到下的顺序依次执行 (屏幕上按“下一步”就走到下一个)。
# 每一步要么是 replace(_S["..."], ...) —— 借用 0.25 µm STI 工艺的步骤并改几个字段；
# 要么是 _S["..."] —— 原样照搬；要么是 Step(...) —— 本代工艺新增的步骤。
# Step 的参数依次是：步骤名 key、(中文标题, 英文标题)、(中文说明, 英文说明)、
#   参数表 [(中文名, 英文名, 计算显示值的函数)]、动画阶段列表 [Phase...]、小测验 quiz(...)。
# “lambda c: ...” 是一个没有名字的一行小函数：输入 c，返回冒号后面的值；
#   参数表用它是因为显示的数值 (如沟道掺杂) 要等用户拖动滑块后再实时计算。
# ==========================================================================
STEPS = [
    # ---- 第 1 步：起始硅片。把 0.25 µm 工艺的“硅片”步骤换成 28 nm 版本的说明和参数 ----
    # 300 mm 大硅片；<100> 晶向的表面缺陷少、电子迁移率高；P 型衬底用来做 NMOS。
    replace(_S["wafer"],
            desc=("从 300 mm 的 <100> P 型硅片开始。28 nm 是最后一代“平面”体硅 CMOS："
                  "晶体管仍然平躺在硅表面，但栅极、源漏和互连都已经和 0.25 µm 时代完全不同。",
                  "We start from a 300 mm <100> p-type wafer. 28 nm is the last planar bulk CMOS node: the "
                  "transistor still lies flat on the surface, but its gate, source/drain and wiring are "
                  "completely different from the 0.25 µm era."),
            params=[("晶向", "Orientation", lambda c: "<100>"),
                    ("硅片直径", "Wafer diameter", lambda c: "300 mm"),
                    ("沟道掺杂 Na", "Channel doping Na", lambda c: f"{c.p.na_cm3:.1e} cm^-3")]),
    # ---- 浅沟槽隔离 (STI)：在相邻晶体管之间挖沟、填满氧化物，把它们电学上隔开 ----
    # 这几步和 0.25 µm 工艺完全一样，直接照搬：
    # padox  = 长一层薄的“垫氧化层”，缓冲上面氮化硅对硅的应力；
    # nitride = 淀积氮化硅，它是刻沟槽的硬掩膜，也是后面 CMP 研磨的“停止层”。
    _S["padox"],
    _S["nitride"],
    # STI 光刻：用 ACTIVE 掩膜定义“有源区”(要做晶体管的地方)，其余地方将被挖成沟槽。
    # 这里只把光源换成 28 nm 时代的 193 nm 浸没式光刻，并换了一道测验题。
    replace(_S["sti_litho"],
            params=[("掩膜", "Mask", lambda c: "#1 ACTIVE"),
                    ("光源", "Source", lambda c: "ArF 浸没式 193 nm (193i)")],
            quiz=quiz("28 nm 节点的关键层用什么光刻？", "Lithography for the critical layers at 28 nm?",
                      [("ArF 浸没式 193 nm", "ArF immersion 193 nm"), ("汞灯 i 线", "Hg i-line"),
                       ("EUV 13.5 nm", "EUV 13.5 nm"), ("X 射线", "X-ray")], 0,
                      "镜头和晶圆之间充满水 (n≈1.44)，等效数值孔径 NA 可达 1.35，再加上双重图形就能做到 28 nm。",
                      "Water between lens and wafer (n≈1.44) raises NA to 1.35; with double patterning that reaches 28 nm.")),
    _S["sti_etch"],      # 刻沟槽：把有源区之外的硅往下刻出浅沟
    _S["sti_liner"],     # 沟槽内壁先长一层薄氧化层 (衬垫)，修复刻蚀损伤
    _S["sti_fill"],      # 用 CVD 氧化物把沟槽填满
    _S["sti_cmp"],       # 化学机械抛光 (CMP)：把表面磨平，停在氮化硅上
    _S["sti_strip"],     # 去掉氮化硅和垫氧，露出干净的有源区硅表面
    # ---- N 阱：PMOS 必须做在 N 型硅里，所以在右半边 (PMOS 区) 注入磷形成 N 阱 ----
    _S["nwell_litho"],       # 光刻：只露出 PMOS 区
    _S["nwell_implant_he"],  # 高能磷离子注入，打进较深的地方
    _S["nwell_anneal"],      # 高温退火：修复晶格损伤，让磷原子扩散并“激活”

    # ---- 伪栅 (dummy gate)：后栅工艺 (gate-last) 的关键 ----
    # 为什么不直接做金属栅？因为后面还有源漏注入后的 1000 °C 以上高温退火，
    # 高 k 介质和功函数金属受不了这么高的温度 (会变质、Vt 漂移)。
    # 所以先放一个耐高温的“假”多晶硅栅占住位置，让源漏等结构都以它为基准自对准做好；
    # 等所有高温步骤结束，再把它挖掉，填进真正的 HfO2 + 金属栅 (见后面的 rmg_remove_step 和 hkmg_step)。
    # deposit(层名, 材料, thickness=厚度, region=只长在哪些区域) 是“淀积薄膜”的动作；
    # anneal(温度°C, 时间秒, 发光颜色) 是“退火”(加热) 的动作，动画里硅片会发红光。
    Step("dummy_gate", ("伪栅叠层淀积 (后栅工艺)", "Dummy gate stack (gate-last)"),
         ("先长一层牺牲氧化层，再淀积多晶硅——但这是“伪栅” (dummy gate)：它只负责在接下来的注入、侧墙和"
          "高温退火中占住栅的位置，最后会被挖掉，换成高 k 介质 + 金属栅 (HKMG)。",
          "A sacrificial oxide and polysilicon are deposited, but this is a dummy gate: it only holds the "
          "gate's place through the implants, spacers and hot anneals, and will later be dug out and "
          "replaced by a high-k / metal gate (HKMG)."),
         [("牺牲氧化层", "Sacrificial oxide", lambda c: "≈ 2 nm"),
          ("伪栅多晶硅", "Dummy poly", lambda c: "≈ 50 nm, LPCVD"),
          ("最终 EOT", "Final EOT", lambda c: f"{c.p.tox_nm:.2f} nm")],
         [Phase("热氧化牺牲层", "Sacrificial oxide", 1.2,
                [deposit("gox", "gate_ox", thickness=0.05, region=lambda c: [c.lay["act_n"], c.lay["act_p"]]),
                 anneal(850, 30, (1.0, 0.5, 0.2))]),
          Phase("LPCVD 伪栅多晶硅", "LPCVD dummy poly", 1.4,
                [deposit("poly", "poly_dummy", thickness=0.35, particles=("depo", (0.9, 0.6, 0.45, 1)))])],
         quiz("为什么 28 nm 不再用 SiO2 + 多晶硅栅？", "Why did 28 nm drop the SiO2 + poly gate?",
              [("SiO2 薄到 1 nm 时隧穿漏电太大，多晶硅还有耗尽效应", "1 nm SiO2 tunnels too much and poly depletes"),
               ("多晶硅太贵", "Poly is too expensive"), ("SiO2 不绝缘", "SiO2 doesn't insulate"),
               ("没有原因", "No reason")], 0,
              "栅介质每薄 0.2 nm 隧穿电流约增 10 倍；多晶硅栅底部还会耗尽，相当于又加厚了栅氧。",
              "Every 0.2 nm thinner oxide leaks ~10× more; the poly also depletes, adding effective thickness.")),

    # ---- 伪栅光刻 + 刻蚀：把整片多晶硅刻成细细的栅条 (栅长只有约 30 nm) ----
    # 30 nm 比 193 nm 光的波长小得多，所以要用“双重图形”：分两次曝光拼出更密的线条。
    replace(_S["gate_litho"],
            title=("伪栅光刻 (掩膜)", "Dummy-gate lithography (mask)"),
            params=[("掩膜", "Mask", lambda c: "POLY (193i 双重图形 / double patterning)"),
                    ("栅长 Lg", "Gate length Lg", lambda c: f"{c.p.l_um * 1e3:.0f} nm"),
                    ("宽度 Wn / Wp", "Wn / Wp", lambda c: f"{c.p.wn_um:.2f} / {c.p.wp_um:.2f} µm")]),
    replace(_S["gate_etch"], title=("伪栅刻蚀", "Dummy-gate etch")),

    # ---- 源漏延伸区 (LDD/extension) + Halo 注入 ----
    # 延伸区是紧挨着栅边缘的、非常浅的掺杂区，把沟道和深源漏连起来；做得越浅，短沟道效应越小。
    # Halo (袋状注入) 斜着打进沟道两端，提高那里的掺杂，防止栅很短时 Vt 掉得太厉害 (Vt roll-off)。
    replace(_S["nldd"],
            title=("N 型延伸区 + Halo 注入", "n extension + halo implants"),
            desc=("对 NMOS 做极浅的砷注入形成源漏延伸区 (约 15 nm 深)，再以大倾角注入硼形成“Halo/袋状注入”，"
                  "在沟道两端局部提高掺杂，抵消短沟道 Vt 下降。",
                  "A very shallow arsenic implant forms the NMOS S/D extensions (~15 nm deep); a tilted "
                  "boron 'halo/pocket' implant then raises the doping locally at the channel ends to fight "
                  "short-channel Vt roll-off."),
            params=[("延伸区", "Extension", lambda c: "As, 1 keV, 1e15 cm^-2"),
                    ("Halo", "Halo", lambda c: "B, 10 keV, 30° 倾角 / tilt"),
                    ("结深 xj", "Junction depth xj", lambda c: f"{c.p.xj_nm:.0f} nm")]),
    # PMOS 一侧同理，只是杂质类型反过来 (延伸区用 BF2 即硼，Halo 用砷)。
    replace(_S["pldd"],
            title=("P 型延伸区 + Halo 注入", "p extension + halo implants"),
            desc=("PMOS 做法相同：极浅 BF2 延伸区 + 大倾角砷 Halo。",
                  "Same for the PMOS: an ultra-shallow BF2 extension plus a tilted arsenic halo."),
            params=[("延伸区", "Extension", lambda c: "BF2, 2 keV"),
                    ("Halo", "Halo", lambda c: "As, 40 keV, 30° 倾角 / tilt")]),
    # ---- 侧墙 (spacer)：在伪栅两侧做出氮化硅“小墙” ----
    # 先整片淀积一层介质，再各向异性 (只往下) 回刻，平面上的被刻光，只有栅侧壁上的留下来。
    # 侧墙让后面的深源漏注入、SiGe 凹槽离沟道保持一小段距离。
    _S["spacer_dep"],
    _S["spacer_etch"],

    # ---- 嵌入式 SiGe 源漏 (只做 PMOS)：用“应变”提高空穴速度 ----
    # 空穴天生比电子慢 (迁移率低)，PMOS 就比 NMOS 弱。办法：把 PMOS 源漏的硅挖掉，换成 SiGe。
    # 锗原子比硅原子大，SiGe 的晶格比硅大，它从左右两边把中间的硅沟道“挤紧”(压应力)，
    # 改变硅的能带，使空穴有效质量变小、跑得更快。
    # 动画分两段：recess(要挖的层, 区域, 挖到的 z 高度) 把硅刻出凹槽；
    #            add_solids(层名, 材料, 生成实体的函数) 把 _sige 算出的 SiGe 块“长”进去。
    Step("sige_sd", ("PMOS 嵌入式 SiGe 源漏", "Embedded SiGe source/drain (PMOS)"),
         ("把 PMOS 源漏区的硅刻出凹槽，再选择性外延生长掺硼的 SiGe (Ge 约 30-40%)。SiGe 的晶格比 Si 大，"
          "它从两侧“挤压”沟道，产生压应力，使空穴迁移率提高 50% 以上。这就是“应变硅”技术 (90 nm 起)。"
          + EPI_NOTE[0],
          "The PMOS S/D silicon is recessed and boron-doped SiGe (30-40 % Ge) is grown epitaxially. "
          "SiGe has a larger lattice than Si, so it squeezes the channel from both sides: the compressive "
          "strain boosts hole mobility by more than 50 %. This is strained silicon (from 90 nm on). "
          + EPI_NOTE[1]),
         [("凹槽深度", "Recess depth", lambda c: "≈ 60 nm (Σ 形)"),
          ("外延", "Epitaxy", lambda c: "SiGe:B, Ge 35 %, 650 °C"),
          ("空穴迁移率 µp", "Hole mobility µp", lambda c: f"{c.p.mu_p:.0f} cm²/Vs")],
         [Phase("刻蚀 PMOS 源漏凹槽", "Recess the PMOS S/D", 1.6,
                [recess(["sub", "nwell", "pldd"], _sd_p, SIGE_BOT)]),
          Phase("选择性外延 SiGe:B", "Selective SiGe:B epitaxy", 2.2,
                [add_solids("psd", "p_epi", _sige, particles=("depo", (0.4, 0.5, 1.0, 1))),
                 anneal(650, 1200, (1.0, 0.7, 0.4))])],
         quiz("PMOS 源漏里嵌入 SiGe 是为了？", "Why embed SiGe in the PMOS source/drain?",
              [("给沟道加压应力，提高空穴迁移率", "Compressive channel strain raises hole mobility"),
               ("降低成本", "Lower cost"), ("作为栅介质", "Act as gate dielectric"), ("隔离器件", "Isolate devices")], 0,
              "Ge 原子更大，SiGe 晶格常数比 Si 大约 1.4%，沿沟道方向把硅压紧，空穴有效质量变小、跑得更快。",
              "Ge is larger, so SiGe's lattice is ~1.4 % bigger; it compresses the channel and lightens the holes.")),

    # ---- NMOS 深源漏 N+ 注入 ----
    # 先光刻 (NSELECT 掩膜挡住 PMOS)，再对 NMOS 做高剂量砷注入，形成导电很好的源漏；
    # “伪栅 + 侧墙”本身就是掩膜，所以源漏自动对准栅两边 (自对准)。
    # phases= 这里用“列表 + 列表”把光刻的几个阶段和注入、去胶阶段拼在一起。
    # (PMOS 不需要这一步：SiGe 外延时已经边长边掺了硼。)
    replace(_S["nplus_sp"],
            desc=("用 N+ 选择掩膜盖住 PMOS，对 NMOS 做高剂量砷/磷注入，以“伪栅 + 侧墙”为掩膜。"
                  "伪栅之后会被换掉，所以这里不需要像多晶硅栅那样顺便把栅掺成 N+。",
                  "With the NSELECT mask over the PMOS, a high-dose As/P implant goes into the NMOS, masked by "
                  "dummy gate + spacers. The dummy gate will be replaced, so it no longer needs to be doped n+."),
            params=[("离子", "Species", lambda c: "As+ / P+"),
                    ("剂量", "Dose", lambda c: "3e15 cm^-2"),
                    ("能量", "Energy", lambda c: "≈ 10 keV")],
            phases=litho(lambda c: [c.lay["nwell"]], mask="NSELECT") + [
                Phase("砷离子注入 (以侧墙为掩膜)", "Arsenic implant (spacer-masked)", 2.2,
                      [implant("nplus", "n_plus", _sd_n, -0.3, (1.0, 0.35, 0.3, 1),
                               species="As", dose=3e15, energy_kev=10)]),
                Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])]),

    # ---- 尖峰退火 + 毫秒激光退火：激活杂质，但不让它们扩散开 ----
    # 注入进去的杂质原子要加热后才能“坐”进硅晶格、真正导电 (叫“激活”)；
    # 但加热太久杂质会往四周扩散，把浅结变深，短沟道效应就变差。
    # 所以用极短的高温：1 秒的尖峰退火 + 1 毫秒的激光退火。
    # replace_layer 把注入区换成“退火后略微扩散变大”的形状，requires= 表示只有那一层存在时才换。
    Step("msa", ("尖峰退火 + 毫秒激光退火", "Spike + millisecond laser anneal"),
         ("先做 1050°C 的“尖峰”快速退火 (在峰值温度只停 1 秒左右)，再用激光把表面在毫秒内加热到 1250°C 以上。"
          "杂质几乎来不及扩散就被激活，结深可以保持在 15 nm 左右。PMOS 的 SiGe 已经原位掺硼，不需要再注入。",
          "A 1050 °C spike anneal (about a second at peak) is followed by a laser that heats only the "
          "surface above 1250 °C for milliseconds. Dopants are activated with almost no diffusion, "
          "keeping junctions ~15 nm deep. The PMOS SiGe is boron-doped in situ and needs no implant."),
         [("尖峰 RTA", "Spike RTA", lambda c: "1050 °C, ~1 s"),
          ("激光退火", "Laser anneal", lambda c: "1250 °C, ~1 ms"),
          ("延伸区结深", "Extension xj", lambda c: f"{c.p.xj_nm:.0f} nm"),
          ("→ DIBL (NMOS)", "→ DIBL (NMOS)",
           lambda c: f"{summarize_cached(c.p, c.features).dibl_n:.0f} mV/V")],
         [Phase("尖峰退火 + 激光退火", "Spike + laser anneal", 2.0,
                [replace_layer("nldd", "n_ldd", lambda c: sd_annealed(c.lay["act_n"], gate_span(c, "gn"), 0.05, -0.12),
                               requires="nldd"),
                 replace_layer("nplus", "n_plus", lambda c: sd_annealed(c.lay["act_n"], spacer_span(c, "gn"), 0.08, -0.32),
                               requires="nplus"),
                 anneal(1050, 1, (1.0, 0.3, 0.1)), anneal(1250, 0.001, (1.0, 0.3, 0.1))])],
         quiz("为什么要用毫秒级的激光退火？", "Why a millisecond laser anneal?",
              [("激活杂质但几乎不扩散，保持超浅结", "Activate dopants with almost no diffusion (ultra-shallow junctions)"),
               ("节省电费", "Save electricity"), ("去除光刻胶", "Remove resist"), ("长栅氧", "Grow oxide")], 0,
              "扩散长度 ∝ √(Dt)：时间从 10 s 缩到 1 ms，扩散长度缩小约 100 倍。",
              "Diffusion length ∝ √(Dt): cutting the time from 10 s to 1 ms shrinks it ~100×.")),

    # ---- 自对准镍硅化物 (NiSi)：给源漏表面镀一层导电好的“金属皮” ----
    # 掺杂的硅本身电阻还是偏大，在表面形成金属硅化物可以大大降低电阻和接触电阻。
    # 三段动画：溅射镍 → 退火让镍和硅反应 (_nisi 给出生成的硅化物形状) → 把没反应的镍洗掉。
    Step("nisi", ("自对准镍硅化物 (NiSi)", "Self-aligned nickel silicide (NiSi)"),
         ("整片溅射一层镍，低温退火时镍只和裸露的硅/SiGe 反应生成 NiSi，和氧化物、氮化物侧墙不反应；"
          "再用酸把没反应的镍洗掉。源漏表面的方块电阻从几百 Ω/□ 降到约 10 Ω/□。",
          "Nickel is sputtered everywhere; a low-temperature anneal makes it react only with exposed Si/SiGe "
          "to form NiSi (not with the oxide or nitride spacers), and an acid then strips the unreacted "
          "nickel. The S/D sheet resistance drops from hundreds to ~10 Ω/sq."),
         [("金属", "Metal", lambda c: "Ni(Pt) ≈ 10 nm"),
          ("退火", "Anneal", lambda c: "≈ 400 °C RTA"),
          ("方块电阻", "Sheet resistance", lambda c: "≈ 10 Ω/□")],
         [Phase("溅射镍", "Sputter nickel", 1.2,
                [deposit("ni", "nickel", thickness=0.04, particles=("depo", (0.8, 0.8, 0.85, 1)))]),
          Phase("退火：镍与硅反应", "Anneal: Ni reacts with Si", 1.4,
                [add_solids("silicide", "silicide", _nisi, mode="fade"), anneal(400, 30, (1.0, 0.6, 0.3))]),
          Phase("去除未反应的镍", "Strip unreacted nickel", 1.0, [strip("ni")])],
         quiz("“自对准”硅化物为什么不需要掩膜？", "Why does self-aligned silicide need no mask?",
              [("镍只和裸露的硅反应，不和氧化物/氮化物反应", "Ni reacts only with bare silicon, not with oxide or nitride"),
               ("掩膜太贵", "Masks are too expensive"), ("镍会自己移动", "Nickel moves by itself"),
               ("用了激光", "A laser is used")], 0,
              "反应只在硅表面发生，侧墙和 STI 上的镍原样留下，随后被选择性洗掉。",
              "The reaction happens only on silicon; Ni on the spacers and STI stays metallic and is etched off.")),

    # ---- 以下几步由 _modern.py 里的函数生成 (FinFET 等工艺也共用它们) ----
    # ILD0：淀积第一层层间介质 (氧化物) 把所有东西埋起来，再 CMP 磨到 GATE_TOP，刚好露出伪栅顶面。
    ild0_step(GATE_TOP),
    # 去除伪栅 (RMG = replacement metal gate，替换金属栅)：把 NMOS、PMOS 的伪栅多晶硅和牺牲氧化层刻掉，
    # 留下一条条“栅槽”。此时所有高温步骤都已结束，可以放心放入怕高温的高 k 和金属了。
    rmg_remove_step(["gate_n", "gate_p"]),
    # HKMG：往栅槽里依次填入 —— 极薄界面氧化层 + 高 k 介质 HfO2 + 功函数金属 + 钨填充，最后 CMP 磨平。
    # 高 k：HfO2 介电常数约 20 (SiO2 只有 3.9)，物理厚度可以厚好几倍，隧穿漏电大大减小，
    #       但对沟道的控制能力等效于约 1 nm 的 SiO2 (这就是参数里的 EOT，等效氧化层厚度)。
    # 金属栅：没有多晶硅栅的“耗尽效应”；NMOS 和 PMOS 用功函数不同的金属，分别把 Vt 调到合适的值。
    hkmg_step(GATE_TOP),
    # 接触孔：在源、漏、栅上方的介质里打孔并填钨，把晶体管和上面的金属导线连起来。
    contact_step(),
    # 第一层铜互连 (M1)：大马士革工艺 —— 先在介质里刻出导线槽，再填铜、CMP 磨平。
    copper_m1_step(),
    # 最后一步：完成，并总结这一代工艺的特点 (以及为什么下一代要改用 FinFET)。
    done_step(("28 nm 平面 HKMG 反相器完成。对比 0.25 µm：VDD 只有 0.9 V，栅介质换成 HfO2 + 金属，"
               "PMOS 有 SiGe 应变。打开“电学特性 → Vt-L”可以看到：栅长 30 nm 时 DIBL 已超过 100 mV/V，"
               "亚阈值摆幅也明显变差——平面结构的栅已经“管不住”沟道了，这正是下一代改用 FinFET 的原因。",
               "The 28 nm planar HKMG inverter is done. Versus 0.25 µm: VDD is only 0.9 V, the gate is HfO2 + "
               "metal and the PMOS is strained by SiGe. On Electrical → Vt-L note that at Lg = 30 nm DIBL "
               "exceeds 100 mV/V and the sub-threshold swing degrades: a planar gate can no longer control "
               "the channel, which is why the next generation moved to FinFETs.")),
]

# 3D 视图里贴在各区域旁边的文字标签。每一项是：(层名, 中文, 英文, 标签的 x 位置, 标签的 z 位置)。
# 例如 ("psd", "SiGe", ...) 就是在 PMOS 源漏的 SiGe 块旁边写 “SiGe”。
REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.2),
    ("nplus", "n+", "n+", 2.4, -0.45),
    ("psd", "SiGe", "SiGe", 12.4, 0.0),
    ("gfill", "HKMG", "HKMG", 5.25, 0.75),
    ("cu", "Cu", "Cu", 10.25, 1.95),
]

# “工艺参数”面板里的滑块：(参数名, 界面文字的翻译键, 最小值, 最大值, 是否按对数刻度拖动)。
# 学生拖动滑块改变参数 (如 EOT、沟道掺杂、栅长、电源电压)，程序会重新计算反相器的电学特性。
# 掺杂浓度这类跨好几个数量级的量用对数刻度 (True)，否则一点点距离就跳太多。
PLANAR_ADV_SLIDERS = [
    ("tox_nm", "p_eot", 0.6, 3.0, False),
    ("na_cm3", "p_na", 1e17, 1e19, True),
    ("nwell_dose_cm2", "p_dose", 2e13, 2e15, True),
    ("l_um", "p_l_nm", 0.020, 0.25, False),
    ("wn_um", "p_wn", 0.1, 2.0, False),
    ("wp_um", "p_wp", 0.1, 2.0, False),
    ("vdd", "p_vdd", 0.5, 1.5, False),
    ("cload_ff", "p_cl_small", 0.1, 10.0, False),
]

# FLOW：把上面所有东西打包成“一条完整工艺流程”，主程序通过它找到本文件的全部内容。
# features 是一组“特性标签”，告诉电学计算部分这一代有哪些物理效应要考虑：
#   sti=浅沟槽隔离, cmp=化学机械抛光, ldd=源漏延伸区, sce=短沟道效应, hkmg=高 k 金属栅。
# terminal_labels 直接借用 locos.py 的端子标签 (VIN/VOUT/VDD/GND 的位置相同)。
# defaults 是这一代工艺的典型参数 (刚选中这条流程时滑块的初始值)：
#   tox_nm=EOT 等效氧化层厚度 (nm)，na_cm3=沟道掺杂，l_um=栅长 (µm，0.030 即 30 nm)，
#   wn_um/wp_um=NMOS/PMOS 宽度，vdd=电源电压，cload_ff=负载电容 (fF)，mu_n/mu_p=电子/空穴迁移率，
#   wf_n_ev/wf_p_ev=两种金属的功函数 (eV)，xj_nm=结深，lambda_um=沟道长度调制系数 (让饱和电流随漏压略微上升，λ = lambda_um / 栅长)。
FLOW = Flow(
    key="hkmg",
    name=("28 nm 平面 HKMG 工艺", "28 nm planar HKMG"),
    short=("平面 28nm", "Planar 28nm"),
    node=("约 28 nm 代：高 k 金属栅 (后栅) + SiGe 应变 + 铜互连，最后一代平面管",
          "~28 nm: high-k metal gate (gate-last), SiGe strain, Cu; the last planar node"),
    steps=STEPS,
    features=frozenset({"sti", "cmp", "ldd", "sce", "hkmg"}),
    region_labels=REGION_LABELS,
    terminal_labels=locos.TERMINAL_LABELS,
    sliders=PLANAR_ADV_SLIDERS,
    defaults=dict(tox_nm=1.1, na_cm3=3e18, nwell_dose_cm2=6e14, l_um=0.030, wn_um=0.3, wp_um=0.45,
                  vdd=0.9, cload_ff=1.0, mu_n=250.0, mu_p=140.0, wf_n_ev=4.36, wf_p_ev=4.86, xj_nm=15.0,
                  lambda_um=0.004),
)
