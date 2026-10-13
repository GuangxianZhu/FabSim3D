"""The guided lessons (zero-background friendly: analogy first, formula optional)."""

# 【中文说明】四节实验课的具体内容（讲解页 → 实验课）。这个文件几乎全是“教学文字 + 判断条件”。
#
# 数据结构（Task / Lesson 的定义见 engine.py）：
#   LESSONS 是一个列表，每一项是一节课 Lesson(key, 标题, 简介, 开场白, 工艺流程, 任务列表, ...)。
#   每节课的任务列表由 _l1_tasks() ~ _l4_tasks() 函数生成，每个任务 Task(...) 包含：
#     title   任务标题            explain 讲道理 / 打比方      try_    请学生做的操作
#     check   判断“做到了没有”的小函数       observe 做到后显示的解释（会填入真实算出的数值）
#     controls 本任务显示哪些滑块/按钮     demo    “帮我做”按钮要做的改动
#     plot    显示哪张图     compare 是否画灰色“改之前”曲线     deep   可选的公式级解释
#   所有文字都写成 ("中文", "英文") 一对，界面按当前语言挑一个显示。
#
# 本文件里的几个 Python 写法：
#   lambda a, b: 表达式   —— “匿名小函数”，a 是任务开始时的状态，b 是现在（或完成时）的状态。
#                         例如 check=lambda a, b: b.vin < 0.2 表示“现在 Vin 小于 0.2 V 就算完成”。
#   f"...{b.vin:.2f}..."   —— f 字符串：花括号里的表达式会被替换成算出的值，:.2f 表示保留 2 位小数，
#                         :.1e 表示科学计数法（如 1.2e-09）。
#   两段字符串紧挨着写（中间没有逗号）会自动连成一段，所以长文字可以分好几行写。
#   状态 b 上常用的属性：b.vin 输入电压，b.p.xxx 工艺参数，b.s.vtn / b.s.vtp 阈值，b.vout 输出电压，
#   b.mn / b.mp NMOS / PMOS 模型，b.ack 是否点了确认，b.tran_played 是否播放了开关动画。
from __future__ import annotations

from ..device_model import inverter_vout, vt_vs_length
from .engine import LabState, Lesson, Task


# ---- 几个小工具函数 ----

def _ie(v: float) -> str:
    """把电流值格式化成科学计数法文字，例如 1.2e-09 A（用于在解释文字里显示电流）。"""
    return f"{v:.1e} A"


def _ratio(a: float, b: float) -> str:
    """计算 b 是 a 的多少倍，并写成 “×3.5” 这样的文字；倍数很大时改用科学计数法。

    max(a, 1e-30) 防止 a 为 0 时出现“除以零”的错误。
    """
    # r 是倍数；下面的 “x if 条件 else y” 是条件表达式：倍数小于 100 用 1 位小数，否则用科学计数法
    r = b / max(a, 1e-30)
    return f"×{r:.1f}" if r < 100 else f"×{r:.1e}"


def _ack_task(intro, title=("开始", "Start")) -> Task:
    """生成每节课第一个“开场说明”任务：只显示一段介绍文字，学生点「开始实验」按钮就算完成。

    intro 是 (中文, 英文) 的介绍文字；title 不写时默认是“开始”。
    这个任务没有观察说明（observe 返回两段空文字），也不画对比曲线。
    """
    return Task(title=title, explain=intro,
                try_=("读完后点「开始实验」。", "When you are ready, press 'Start'."),
                check=lambda a, b: b.ack, observe=lambda a, b: ("", ""),
                controls=["btn:ack"], demo=lambda s: {"ack": True}, compare=False)


# =============================================================================
# ① How a MOSFET switches
# =============================================================================

# 第①课：MOS 管怎么开关。用“水龙头”打比方，拖动 Vin 观察沟道出现/消失、阈值、
# 关不死的漏电流、CMOS 为什么静态时几乎不耗电，以及翻转瞬间的动态电流。
def _l1_tasks():
    """返回第①课的任务列表。"""
    # 返回一个列表，方括号里每个元素就是一个任务，按顺序排列
    return [
        # 任务 0：开场说明（点「开始实验」即可）
        _ack_task((
            "MOS 管就像一个水龙头：源极 S 是进水口，漏极 D 是出水口，栅极 G 是把手。"
            "把手并不直接碰水，而是隔着一层极薄的绝缘层（栅氧），用电场把电子“吸”到硅表面，"
            "在源和漏之间搭起一座“电子桥”，这座桥叫沟道。本课的芯片是一个反相器："
            "Vin 同时接 NMOS 和 PMOS 的栅极。右侧 3D 已打开剖面和载流子仿真。",
            "A MOSFET is like a water tap: the source S is the inlet, the drain D the outlet and "
            "the gate G the handle. The handle never touches the water; through a very thin "
            "insulator (the gate oxide) its electric field pulls electrons to the silicon surface, "
            "building an 'electron bridge' between source and drain: the channel. The chip here is "
            "an inverter: Vin drives the gates of both the NMOS and the PMOS. The 3D view now shows "
            "a cross-section with carrier simulation.")),
        # 任务 1：把 Vin 调到接近 0 V，看 NMOS 关断、PMOS 导通、输出为高 —— 理解“反相”
        Task(
            title=("关掉 NMOS", "Turn the NMOS off"),
            explain=("栅极电压太低时，电场不够强，吸不来足够的电子，“桥”就搭不起来，NMOS 处于关断状态。",
                     "With a low gate voltage the field is too weak to gather enough electrons, so no "
                     "bridge forms and the NMOS is off."),
            try_=("把 Vin 拖到 0 V 附近（< 0.2 V）。看 3D 里 NMOS 栅下的沟道是不是暗的。",
                  "Drag Vin to about 0 V (< 0.2 V). Is the NMOS channel in 3D dark?"),
            check=lambda a, b: b.vin < 0.2,
            observe=lambda a, b: (
                f"NMOS 关了：栅压 {b.vin:.2f} V 低于阈值 Vtn = {b.s.vtn:.2f} V，沟道是暗的。"
                f"而 PMOS 的栅相对它的源极 (VDD) 是 −{b.p.vdd:.1f} V，正好把 PMOS 打开（橙色沟道亮），"
                f"所以输出 Vout = {b.vout:.2f} V，是高电平。输入低 → 输出高，这就是“反相”。",
                f"The NMOS is off: its gate ({b.vin:.2f} V) is below the threshold Vtn = {b.s.vtn:.2f} V, "
                f"so its channel is dark. The PMOS gate is −{b.p.vdd:.1f} V relative to its source "
                f"(VDD), which turns the PMOS on (orange channel), so Vout = {b.vout:.2f} V: high. "
                "Low in, high out: that is inversion."),
            controls=["vin"], demo=lambda s: {"vin": 0.0}, plot="idvg", compare=False),
        # 任务 2：把 Vin 调到略高于阈值 Vtn，看沟道刚刚出现、电流开始迅速增大 —— 理解阈值电压
        Task(
            title=("找到阈值电压", "Find the threshold voltage"),
            explain=("慢慢加大栅压，被吸到表面的电子越来越多。到某个电压时，表面电子多到把 P 型硅"
                     "“翻转”成了 N 型（反型），桥就通了。这个电压叫阈值电压 Vt。",
                     "As the gate voltage rises, more electrons gather at the surface. At some voltage "
                     "they outnumber the holes and the p-type surface 'inverts' to n-type: the bridge is "
                     "complete. That voltage is the threshold voltage Vt."),
            try_=("慢慢把 Vin 往上拖，越过 Id-Vg 图里蓝色竖虚线（Vtn）一点点，看 NMOS 沟道开始发亮。",
                  "Slowly raise Vin just past the blue dashed line (Vtn) on the Id-Vg plot and watch the "
                  "NMOS channel light up."),
            check=lambda a, b: b.s.vtn + 0.05 < b.vin < b.s.vtn + 0.6,
            observe=lambda a, b: (
                f"Vin = {b.vin:.2f} V 已经超过 Vtn = {b.s.vtn:.2f} V，沟道出现，电流从 {_ie(a.id_n)} "
                f"升到 {_ie(b.id_n)}。Vt 是由工艺决定的：栅氧厚度和衬底掺杂。下一门课会动手改它。",
                f"Vin = {b.vin:.2f} V is above Vtn = {b.s.vtn:.2f} V: the channel exists and the current "
                f"rose from {_ie(a.id_n)} to {_ie(b.id_n)}. Vt is set by the process (oxide thickness, "
                "doping); you will change it in the next lesson."),
            controls=["vin"], demo=lambda s: {"vin": s.s.vtn + 0.25}, plot="idvg", compare=False,
            deep=("强反型时 Id ≈ (k'/2n)(W/L)(Vgs − Vt)²：过了阈值后电流随栅压平方增长。",
                  "In strong inversion Id ≈ (k'/2n)(W/L)(Vgs − Vt)²: above threshold the current grows "
                  "with the square of the overdrive.")),
        # 任务 3：把 Vin 调到略低于阈值，看电流虽小但不为零（亚阈值漏电）—— 理解“关不死”
        Task(
            title=("关不死的水龙头", "A tap that never fully closes"),
            explain=("Id-Vg 图的纵轴是对数刻度，每一格是 10 倍。低于 Vt 时电流并不是 0，而是指数下降，"
                     "就像拧紧的水龙头还在滴水。",
                     "The Id-Vg plot uses a log scale: each grid line is ×10. Below Vt the current is not "
                     "zero but falls exponentially, like a closed tap that still drips."),
            try_=("把 Vin 拖到 Vt 左边一点（比 Vtn 低 0.05~0.35 V），在 Id-Vg 图上看工作点。",
                  "Drag Vin a little left of Vt (0.05–0.35 V below Vtn) and look at the operating "
                  "point on the Id-Vg plot."),
            check=lambda a, b: b.s.vtn - 0.35 < b.vin < b.s.vtn - 0.05,
            observe=lambda a, b: (
                f"低于阈值时电流仍有 {_ie(b.id_n)}。栅压每降低 {b.s.ss_n:.0f} mV，电流才减小 10 倍"
                f"（亚阈值摆幅 SS）。Vin = 0 时还剩 Ioff = {_ie(b.s.ioff_n)}：芯片待机时的漏电就来自这里，"
                "几十亿个晶体管加起来就很可观了。",
                f"Below threshold there is still {_ie(b.id_n)}. The current only drops 10× for every "
                f"{b.s.ss_n:.0f} mV less gate voltage (subthreshold swing). At Vin = 0, "
                f"Ioff = {_ie(b.s.ioff_n)} remains: standby leakage, which adds up over billions of "
                "transistors."),
            controls=["vin"], demo=lambda s: {"vin": max(s.s.vtn - 0.2, 0.0)}, plot="idvg", compare=False,
            deep=("亚阈值区 Id ∝ exp((Vgs − Vt)/(n·kT/q))，SS = n·(kT/q)·ln10 ≈ n × 60 mV/dec。",
                  "Subthreshold Id ∝ exp((Vgs − Vt)/(n·kT/q)), SS = n·(kT/q)·ln10 ≈ n × 60 mV/dec.")),
        # 任务 4：Vin 拉到 VDD，看输出为低且几乎没有电流 —— 理解 CMOS 静态省电
        Task(
            title=("CMOS 为什么省电", "Why CMOS saves power"),
            explain=("NMOS 和 PMOS 是串联在 VDD 和地之间的。只要有一个管子关着，电流就没有通路。",
                     "The NMOS and PMOS are in series between VDD and ground. Whenever one of them is "
                     "off, current has no path."),
            try_=("先把 Vin 拖到中间（约 VDD/2），看 3D 里电子和空穴都在流；再拖到 VDD（满格）。",
                  "First drag Vin to the middle (about VDD/2) and see electrons and holes flowing in 3D; "
                  "then drag it to VDD (full scale)."),
            check=lambda a, b: b.vin > b.p.vdd - 0.1,
            observe=lambda a, b: (
                f"Vin = VDD 时 NMOS 全开、PMOS 关断，输出被拉到 {b.vout:.2f} V。看 3D：载流子几乎不动了！"
                "因为 PMOS 断开，电流没有通路。只有当 Vtn < Vin < VDD − |Vtp|"
                f"（约 {b.s.vtn:.2f}~{b.p.vdd + b.s.vtp:.2f} V）时两个管子才同时导通，"
                "有一股从 VDD 直通到地的短路电流，在 VM 附近最大；输入停在 0 或 VDD 时总是一开一关。"
                "所以 CMOS 电路静止时几乎不耗电，这是它统治数字芯片的原因。",
                f"At Vin = VDD the NMOS is fully on and the PMOS off; the output is pulled to "
                f"{b.vout:.2f} V. In 3D the carriers barely move: with the PMOS off there is no path. "
                f"Both devices conduct only while Vtn < Vin < VDD − |Vtp| (about {b.s.vtn:.2f}–"
                f"{b.p.vdd + b.s.vtp:.2f} V): then a short-circuit current flows straight from VDD to "
                "ground, peaking near VM. At a logic level (0 or VDD) one is always off. That is why idle "
                "CMOS draws almost no power, and why it dominates digital chips."),
            controls=["vin"], demo=lambda s: {"vin": s.p.vdd}, plot="vtc", compare=False),
        # 任务 5：播放开关动画，看翻转瞬间两个管子同时导通、给负载电容充放电 —— 理解动态功耗
        Task(
            title=("开关的一瞬间", "The moment of switching"),
            explain=("输出端连着下一级电路，相当于一个小电容 CL。输出翻转时，导通的那个管子要给它充电或放电。",
                     "The output drives the next stage, which looks like a small capacitor CL. When the "
                     "output flips, the conducting transistor must charge or discharge it."),
            try_=("点「播放瞬态」，看输入跳变时 3D 里的载流子突然加速，瞬态图上的竖线同步移动。",
                  "Press 'Play transient': watch carriers rush in 3D when the input jumps while the "
                  "cursor moves on the transient plot."),
            check=lambda a, b: b.tran_played,
            observe=lambda a, b: (
                f"输入上升后，NMOS 把电容上的电荷放到地，输出过 {b.s.tran.tphl * 1e12:.0f} ps 才降到一半"
                f"（延迟 tpHL）；输入下降时 PMOS 充电，tpLH = {b.s.tran.tplh * 1e12:.0f} ps。"
                f"每充放一次消耗 E = CL·VDD² = {b.p.cload_ff * b.p.vdd ** 2 / 1000:.2f} pJ：CMOS 的功耗主要花在开关上。",
                f"After the input rises the NMOS dumps the capacitor's charge to ground; the output "
                f"reaches half swing after {b.s.tran.tphl * 1e12:.0f} ps (tpHL). On the falling input the "
                f"PMOS charges it, tpLH = {b.s.tran.tplh * 1e12:.0f} ps. Each charge/discharge costs "
                f"E = CL·VDD² = {b.p.cload_ff * b.p.vdd ** 2 / 1000:.2f} pJ: CMOS spends its energy on switching."),
            controls=["btn:tran"], demo=lambda s: {"tran": True}, plot="tran", compare=False),
    ]


# =============================================================================
# ② How the process sets Vt
# =============================================================================

# 第②课：工艺参数怎么决定 Vt。学生扮演工艺工程师，改栅氧厚度、衬底掺杂、N 阱剂量，
# 看阈值电压和电流怎么变，并体会 Vt 太低带来的漏电问题。
def _l2_tasks():
    """返回第②课的任务列表。"""
    return [
        # 任务 0：开场说明
        _ack_task((
            "阈值电压 Vt 不是电路设计时随便写的，而是在工厂里“做”出来的：栅氧有多厚、硅里掺了多少杂质，"
            "在工艺步骤里就定下来了。这一课你来当工艺工程师。图上的灰色曲线是你改动之前的样子。",
            "The threshold voltage is not chosen on paper; it is 'manufactured': the gate-oxide "
            "thickness and the doping are fixed by the process steps. In this lesson you are the "
            "process engineer. Grey curves show how things looked before your change.")),
        # 任务 1：把栅氧 tox 减薄到 10 nm 以下 —— 栅氧越薄，栅控越强，电流越大、Vt 越低
        Task(
            title=("减薄栅氧", "Thin the gate oxide"),
            explain=("栅氧是把手和水之间的那层隔膜。隔膜越薄，栅极离沟道越近，同样的电压能吸来更多电子。",
                     "The gate oxide is the membrane between handle and water. The thinner it is, the "
                     "closer the gate sits to the channel and the more electrons the same voltage attracts."),
            try_=("把栅氧厚度 tox 从 20 nm 减到 10 nm 以下，对比 Id-Vg 曲线和灰色旧曲线。",
                  "Reduce the gate oxide tox from 20 nm to below 10 nm and compare the Id-Vg curve with "
                  "the grey one."),
            check=lambda a, b: b.p.tox_nm <= 10.0,
            observe=lambda a, b: (
                f"栅电容 Cox 从 {a.s.cox * 1e7:.2f} 增大到 {b.s.cox * 1e7:.2f} fF/µm²，"
                f"Vtn 从 {a.s.vtn:.3f} 变成 {b.s.vtn:.3f} V，饱和电流 Idsat 从 {a.s.idsat_n * 1e3:.2f} "
                f"增大到 {b.s.idsat_n * 1e3:.2f} mA。栅极“抓得更紧”，晶体管更快。代价是栅氧薄到几个 nm 时"
                "电子会直接隧穿过去，产生漏电，所以 45 nm 以后改用了高介电常数 (high-k) 材料。",
                f"Cox grew from {a.s.cox * 1e7:.2f} to {b.s.cox * 1e7:.2f} fF/µm², Vtn changed "
                f"{a.s.vtn:.3f} → {b.s.vtn:.3f} V and Idsat rose {a.s.idsat_n * 1e3:.2f} → "
                f"{b.s.idsat_n * 1e3:.2f} mA. The gate 'grips' harder, so the transistor is faster. "
                "At a few nm electrons tunnel straight through, which is why high-k dielectrics "
                "replaced SiO2 from 45 nm on."),
            controls=["param:tox_nm"], demo=lambda s: {"params": {"tox_nm": 8.0}}, plot="idvg",
            deep=("Cox = εox / tox；Vt = Vfb + 2φF + Qdep/Cox，最后一项随 tox 减小而减小。",
                  "Cox = εox / tox; Vt = Vfb + 2φF + Qdep/Cox, whose last term shrinks with tox.")),
        # 任务 2：把 P 型衬底掺杂 Na 提高到 3e17 以上 —— 掺杂越多，Vt 越高
        Task(
            title=("多掺点杂质", "Add more doping"),
            explain=("P 型衬底里掺的是硼，表面布满了空穴。想让表面反型成 N 型，栅极得先把这些空穴“推开”。"
                     "掺得越多，要推开的就越多。",
                     "The p-substrate is doped with boron, so its surface is full of holes. To invert it "
                     "the gate must first push those holes away; more doping means more to push."),
            try_=("把衬底掺杂 Na 提高到 3e17 cm^-3 以上，看 Vtn 和 Id-Vg 曲线往哪边移。",
                  "Raise the substrate doping Na above 3e17 cm^-3. Which way do Vtn and the Id-Vg curve move?"),
            check=lambda a, b: b.p.na_cm3 >= 3e17,
            observe=lambda a, b: (
                f"Vtn 从 {a.s.vtn:.3f} 升到 {b.s.vtn:.3f} V，曲线整体右移。工厂正是用一次专门的"
                "“阈值调整注入”在沟道表面加减杂质，把 Vt 精确地调到设计值。",
                f"Vtn rose from {a.s.vtn:.3f} to {b.s.vtn:.3f} V and the curve shifted right. Fabs use a "
                "dedicated 'threshold-adjust implant' at the channel surface to hit the target Vt precisely."),
            controls=["param:na_cm3"], demo=lambda s: {"params": {"na_cm3": 4e17}}, plot="idvg",
            deep=("Qdep = √(2·εSi·q·Na·2φF)，Na 越大耗尽电荷越多；φF = (kT/q)·ln(Na/ni) 也会略增。",
                  "Qdep = √(2·εSi·q·Na·2φF) grows with Na; φF = (kT/q)·ln(Na/ni) increases slightly too.")),
        # 任务 3：调 N 阱剂量，让 PMOS 阈值的大小 |Vtp| 与 NMOS 的 Vtn 相等（差 < 0.05 V）—— 让两管对称
        Task(
            title=("让 PMOS 跟上", "Match the PMOS"),
            explain=("PMOS 做在 N 阱里，它的阈值由 N 阱的掺杂决定，而 N 阱掺杂来自第 4 步的磷注入剂量。"
                     "反相器希望两个管子“对称”。",
                     "The PMOS lives in the n-well; its threshold depends on the well doping, which comes "
                     "from the phosphorus implant dose of the n-well step. An inverter wants the two "
                     "devices to be symmetric."),
            try_=("调 N 阱注入剂量，让 |Vtp| 和 Vtn 相差小于 0.05 V（看下方数值）。",
                  "Adjust the n-well dose until |Vtp| is within 0.05 V of Vtn (see the numbers below)."),
            check=lambda a, b: abs(abs(b.s.vtp) - b.s.vtn) < 0.05,
            observe=lambda a, b: (
                f"现在 Vtn = {b.s.vtn:.3f} V，Vtp = {b.s.vtp:.3f} V，N 阱浓度 {b.p.nd_cm3:.1e} cm^-3。"
                "一个剂量参数就把工艺（离子注入）和电学（PMOS 阈值）连了起来。",
                f"Now Vtn = {b.s.vtn:.3f} V and Vtp = {b.s.vtp:.3f} V with an n-well doping of "
                f"{b.p.nd_cm3:.1e} cm^-3. One dose number links the process (implantation) to the "
                "electrical behaviour (PMOS threshold)."),
            controls=["param:nwell_dose_cm2"], demo=_match_pmos, plot="idvg",
            deep=("Nd ≈ 剂量 / 阱深；|Vtp| = |Vfb| + 2φF,n + Qdep(Nd)/Cox。",
                  "Nd ≈ dose / well depth; |Vtp| = |Vfb| + 2φF,n + Qdep(Nd)/Cox.")),
        # 任务 4：把掺杂降到 1e17 以下 —— 看 Vt 太低时关态漏电流急剧增大
        Task(
            title=("Vt 太低会怎样", "What if Vt is too low"),
            explain=("Vt 越低，管子越容易打开，速度越快。那是不是越低越好？",
                     "A lower Vt turns the transistor on more easily and makes it faster. So is lower "
                     "always better?"),
            try_=("把衬底掺杂 Na 降到 1e17 以下，看 Vin = 0 时的漏电 Ioff。",
                  "Lower the substrate doping Na below 1e17 and look at the leakage Ioff at Vin = 0."),
            check=lambda a, b: b.p.na_cm3 <= 1e17,
            observe=lambda a, b: (
                f"Vtn 降到 {b.s.vtn:.3f} V，驱动电流变大，但关态漏电 Ioff 从 {_ie(a.s.ioff_n)} 涨到 "
                f"{_ie(b.s.ioff_n)}（{_ratio(a.s.ioff_n, b.s.ioff_n)}）。Vt 是速度和漏电的权衡："
                "手机芯片常同时用高 Vt 和低 Vt 两种管子，各取所长。",
                f"Vtn fell to {b.s.vtn:.3f} V, giving more drive, but the off-state leakage rose from "
                f"{_ie(a.s.ioff_n)} to {_ie(b.s.ioff_n)} ({_ratio(a.s.ioff_n, b.s.ioff_n)}). Vt "
                "trades speed against leakage; phone chips mix high-Vt and low-Vt devices."),
            controls=["param:na_cm3"], demo=lambda s: {"params": {"na_cm3": 8e16}}, plot="idvg"),
    ]


def _match_pmos(s: LabState) -> dict:
    """Bisect the n-well dose so that |Vtp| == Vtn.

    第②课任务 3 的“帮我做”：自动找出让 PMOS 阈值大小 |Vtp| 正好等于 NMOS 阈值 Vtn 的 N 阱剂量。
    方法是“二分法”：每次试范围的中点，根据结果把范围缩小一半，重复 50 次就非常精确了。
    """
    # 二分法：在 2e12 ~ 2e14 之间找剂量。剂量跨了好几个数量级，所以“中点”取几何平均 √(lo×hi)
    lo, hi = 2e12, 2e14
    for _ in range(50):
        mid = (lo * hi) ** 0.5
        # 用试探的剂量造一个临时状态，比较 PMOS 与 NMOS 阈值的大小
        st = LabState(s.flow, s.features, s.done, s.p.copy(nwell_dose_cm2=mid), s.vin)
        # |Vtp| 偏小说明 N 阱掺杂不够，要往大剂量一边找；否则往小剂量一边找
        if abs(st.mp.vt) < st.mn.vt:
            lo = mid
        else:
            hi = mid
    return {"params": {"nwell_dose_cm2": (lo * hi) ** 0.5}}


# =============================================================================
# ③ The inverter and W/L sizing
# =============================================================================

# 第③课用到的辅助函数和任务。
def _vm(st: LabState) -> float:
    """取出反相器的翻转点 VM（输出电压等于输入电压的那个点）。"""
    return st.s.vtc.vm


def _balance_wp(s: LabState) -> dict:
    """第③课任务 2 的“帮我做”：自动找出让翻转点正好落在 VDD/2 的 PMOS 宽度。

    用“二分法”：在 0.5~20 µm 之间先试中点，如果 PMOS 太弱（输出偏低）就往宽的一半找，
    否则往窄的一半找；每次范围缩小一半，重复 40 次后已经非常精确。
    """
    lo, hi = 0.5, 20.0
    target = s.p.vdd / 2
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        # 每次试一个 PMOS 宽度 mid，算输入正好等于 VDD/2 时的输出
        # （vin 写成列表是因为 inverter_vout 可以一次算多个输入）
        vin = [target]
        vout = float(inverter_vout(s.p.copy(wp_um=mid), vin, features=s.features)[0])
        if vout < target:      # PMOS too weak
            lo = mid
        else:
            hi = mid
    return {"params": {"wp_um": 0.5 * (lo + hi)}}


# 第③课：反相器与宽长比。把反相器比作 NMOS 和 PMOS 的“拔河”，
# 调 PMOS 宽度看翻转点 VM 怎么移动，再调负载电容和电源电压，看延迟和功耗的变化。
def _l3_tasks():
    """返回第③课的任务列表。"""
    return [
        # 任务 0：开场说明（拔河比喻、翻转点 VM）
        _ack_task((
            "反相器就是一场拔河：NMOS 想把输出拉到 0，PMOS 想把输出拉到 VDD。谁力气大，输出就偏向谁。"
            "输入在某个电压时两边力气正好相等，输出恰好等于输入，这个点叫翻转点 VM。"
            "管子越宽 (W 越大)，就像拔河的人越多。",
            "An inverter is a tug-of-war: the NMOS pulls the output to 0, the PMOS pulls it to VDD. "
            "Whoever is stronger wins. At one input voltage they are equally strong and the output "
            "equals the input: the switching point VM. A wider transistor (larger W) is like more "
            "people on that side of the rope.")),
        # 任务 1：把 PMOS 做得和 NMOS 一样宽 —— 空穴比电子跑得慢，PMOS 力气小，VM 偏低
        Task(
            title=("一样宽会怎样", "Equal widths"),
            explain=("默认设计里 PMOS 比 NMOS 宽 2.5 倍。为什么不做得一样宽呢？",
                     "By default the PMOS is 2.5× wider than the NMOS. Why not make them equal?"),
            try_=("把 PMOS 宽度 Wp 减小到和 Wn 一样（≤ Wn 的 1.15 倍），看 VTC 曲线和灰色旧曲线。",
                  "Reduce the PMOS width Wp to match Wn (≤ 1.15 × Wn) and compare the VTC with the grey curve."),
            check=lambda a, b: b.p.wp_um <= b.p.wn_um * 1.15,
            observe=lambda a, b: (
                f"VM 从 {_vm(a):.2f} V 掉到 {_vm(b):.2f} V，曲线左移了。因为空穴的迁移率只有电子的约 "
                f"{b.p.mu_n / b.p.mu_p:.1f} 分之一，同样宽的 PMOS 力气小，拔河输了，"
                "输入还没到一半，输出就已经被 NMOS 拉低了。",
                f"VM dropped from {_vm(a):.2f} V to {_vm(b):.2f} V and the curve moved left. Holes are about "
                f"{b.p.mu_n / b.p.mu_p:.1f}× less mobile than electrons, so an equally wide PMOS is weaker, "
                "loses the tug-of-war, and the NMOS pulls the output down before the input reaches half way."),
            controls=["param:wp_um"], demo=lambda s: {"params": {"wp_um": s.p.wn_um}}, plot="vtc",
            deep=("VM 由 Idn = Idp 决定；强反型时近似 √(βn/βp) = (VDD − VM − |Vtp|)/(VM − Vtn)，β = µCox·W/L。",
                  "VM solves Idn = Idp; roughly √(βn/βp) = (VDD − VM − |Vtp|)/(VM − Vtn), with β = µCox·W/L.")),
        # 任务 2：调 PMOS 宽度，把翻转点 VM 调到 VDD/2 附近（差 < 0.05 V）—— 让高低电平噪声容限对称
        Task(
            title=("调到正中间", "Centre the switching point"),
            explain=("VM 在正中间时，输入“偏高一点”或“偏低一点”都能被正确识别，两边的抗干扰能力（噪声容限）一样大。",
                     "With VM in the middle, the inverter tolerates noise equally on both sides: the "
                     "high and low noise margins are equal."),
            try_=("调 Wp，让 VM 尽量接近 VDD/2（误差 < 0.05 V）。",
                  "Adjust Wp until VM is within 0.05 V of VDD/2."),
            check=lambda a, b: abs(_vm(b) - b.p.vdd / 2) < 0.05,
            observe=lambda a, b: (
                f"VM = {_vm(b):.2f} V，此时 Wp/Wn = {b.p.wp_um / b.p.wn_um:.1f}，差不多就是电子和空穴迁移率之比。"
                f"噪声容限 NMH = {b.s.vtc.nmh:.2f} V，NML = {b.s.vtc.nml:.2f} V，几乎相等。",
                f"VM = {_vm(b):.2f} V with Wp/Wn = {b.p.wp_um / b.p.wn_um:.1f}, close to the electron/hole "
                f"mobility ratio. Noise margins NMH = {b.s.vtc.nmh:.2f} V and NML = {b.s.vtc.nml:.2f} V "
                "are nearly equal."),
            controls=["param:wp_um"], demo=_balance_wp, plot="vtc"),
        # 任务 3：把负载电容加到 300 fF 以上 —— 要充放的电荷多了，延迟变长
        Task(
            title=("负载变重", "A heavier load"),
            explain=("输出接的导线越长、后面驱动的门越多，负载电容 CL 就越大，就像要灌满的水桶更大。",
                     "Longer wires and more driven gates mean a larger load capacitance CL, like a "
                     "bigger bucket to fill."),
            try_=("把负载电容 CL 加大到 300 fF 以上，看瞬态图的输出曲线。",
                  "Increase the load CL above 300 fF and watch the output on the transient plot."),
            check=lambda a, b: b.p.cload_ff >= 300,
            observe=lambda a, b: (
                f"延迟 tpHL 从 {a.s.tran.tphl * 1e12:.0f} ps 变成 {b.s.tran.tphl * 1e12:.0f} ps，大致和 CL 成正比。"
                "这就是为什么芯片里要用“缓冲器”逐级放大驱动能力，以及为什么导线越短越好。",
                f"tpHL went from {a.s.tran.tphl * 1e12:.0f} ps to {b.s.tran.tphl * 1e12:.0f} ps, roughly "
                "proportional to CL. That is why chips insert buffers to boost drive, and why short "
                "wires matter."),
            controls=["param:cload_ff"], demo=lambda s: {"params": {"cload_ff": 350.0}}, plot="tran",
            deep=("tp ≈ CL·VDD / (2·Idsat)。", "tp ≈ CL·VDD / (2·Idsat).")),
        # 任务 4：把电源电压降到 2.5 V 以下 —— 功耗大幅下降，但电流变小、速度变慢
        Task(
            title=("降低电源电压", "Lower the supply voltage"),
            explain=("每次开关，负载电容都要充满再放掉，消耗的能量和 VDD 的平方成正比。",
                     "Every switching event fills and empties the load; the energy goes with VDD squared."),
            try_=("把电源电压 VDD 降到 2.5 V 以下，比较能耗和延迟。",
                  "Lower VDD below 2.5 V and compare energy and delay."),
            check=lambda a, b: b.p.vdd <= 2.5,
            observe=lambda a, b: (
                f"每次翻转能量 E = CL·VDD² 从 {a.p.cload_ff * a.p.vdd ** 2 / 1000:.2f} 降到 "
                f"{b.p.cload_ff * b.p.vdd ** 2 / 1000:.2f} pJ，降幅比电压大得多（平方关系）；"
                f"但驱动电流变小，延迟 tpHL 从 {a.s.tran.tphl * 1e12:.0f} 增到 {b.s.tran.tphl * 1e12:.0f} ps。"
                "手机“省电模式”降频降压，用的就是这个关系。",
                f"Energy per transition E = CL·VDD² fell from {a.p.cload_ff * a.p.vdd ** 2 / 1000:.2f} to "
                f"{b.p.cload_ff * b.p.vdd ** 2 / 1000:.2f} pJ, much more than the voltage did (square law); "
                f"but drive current fell and tpHL grew from {a.s.tran.tphl * 1e12:.0f} to "
                f"{b.s.tran.tphl * 1e12:.0f} ps. Phone power-saving modes lower voltage and clock for this reason."),
            controls=["param:vdd"], demo=lambda s: {"params": {"vdd": 2.2}}, plot="tran"),
    ]


# =============================================================================
# ④ The price of scaling
# =============================================================================

# 第④课用到的辅助函数和任务。
def _ldd_gap(st: LabState) -> float:
    """计算当前栅长下“有 LDD”比“没有 LDD（深源漏结）”的饱和阈值高多少（单位 V）。

    vt_vs_length 本来是算一串栅长的 Vt，这里只让它算当前 L 附近的 2 个点，取第一个。
    frozenset(...) - {"ldd"} 表示从工艺特性里去掉 LDD，得到“深结”的对照情况。
    返回的三个值依次是：栅长、低漏压 Vt、高漏压（饱和）Vt；用 _ 接收不需要的值。
    """
    _, _, sat_ldd = vt_vs_length(st.p, st.features, "n", st.p.l_um, st.p.l_um * 1.0001, 2)
    _, _, sat_deep = vt_vs_length(st.p, frozenset(st.features) - {"ldd"}, "n",
                                  st.p.l_um, st.p.l_um * 1.0001, 2)
    return float(sat_ldd[0] - sat_deep[0])


# 第④课：缩小尺寸的代价。用 STI 工艺，把栅长 L 从长缩到很短，
# 观察短沟道效应（Vt 滚降、DIBL），再看 LDD、提高掺杂、减薄栅氧这些补救办法。
def _l4_tasks():
    """返回第④课的任务列表。"""
    return [
        # 任务 0：开场说明（摩尔定律与短沟道效应）
        _ack_task((
            "摩尔定律：每过两年，晶体管尺寸缩小约 0.7 倍。更小意味着更快、更省电、更便宜。"
            "但当栅长 L 缩到很短时，漏极离源极太近，开始和栅极“抢”对沟道的控制权，这就是短沟道效应。"
            "本课使用 0.25 µm 的 STI 工艺（带 LDD）。注意 3D 模型里的栅极宽度会跟着 L 变。",
            "Moore's law: every two years transistors shrink by ~0.7×, becoming faster, leaner and "
            "cheaper. But when the gate length L gets very short, the drain sits so close to the source "
            "that it starts competing with the gate for control of the channel: short-channel effects. "
            "This lesson uses the 0.25 µm STI flow with LDD. Watch the gate width in 3D follow L.")),
        # 任务 1：把栅长 L 调到 2 µm 以上 —— 先看长沟道时一切正常
        Task(
            title=("先看长沟道", "Start with a long channel"),
            explain=("Vt-L 图横轴是栅长，蓝线是漏极电压很低时的 Vt，橙线是漏极加满 VDD 时的 Vt。",
                     "The Vt-L plot shows gate length on the x-axis; the blue line is Vt at a tiny drain "
                     "voltage, the orange line Vt with the full VDD on the drain."),
            try_=("把栅长 L 拉长到 2 µm 以上。", "Stretch the gate length L above 2 µm."),
            check=lambda a, b: b.p.l_um >= 2.0,
            observe=lambda a, b: (
                f"L = {b.p.l_um:.2f} µm 时 Vtn = {b.s.vtn:.3f} V，蓝橙两线几乎重合（DIBL 只有 "
                f"{b.s.dibl_n:.0f} mV/V）：漏极电压基本不影响阈值，栅极说了算。这是“理想”的晶体管。",
                f"At L = {b.p.l_um:.2f} µm, Vtn = {b.s.vtn:.3f} V and the blue and orange lines almost "
                f"coincide (DIBL only {b.s.dibl_n:.0f} mV/V): the drain hardly affects the threshold; the "
                "gate is in charge. An 'ideal' transistor."),
            controls=["param:l_um"], demo=lambda s: {"params": {"l_um": 2.5}}, plot="vtl"),
        # 任务 2：把 L 缩到 0.19 µm 以下 —— Vt 明显降低、DIBL 变大，漏极开始“抢”控制权
        Task(
            title=("缩到很短", "Shrink it hard"),
            explain=("源和漏都是 PN 结，各自“占”着一块耗尽区。沟道很长时这两块可以忽略；沟道很短时，"
                     "它们分走了本该由栅极控制的电荷，漏极电压还会压低源端的势垒。",
                     "Source and drain are p-n junctions, each owning a depletion region. In a long "
                     "channel they are negligible; in a short one they steal charge the gate should "
                     "control, and the drain voltage lowers the source barrier."),
            try_=("把栅长 L 缩到 0.18 µm（滑块最左边附近），看 Vt、DIBL 和 Ioff。",
                  "Shrink L to 0.18 µm (near the left end) and watch Vt, DIBL and Ioff."),
            check=lambda a, b: b.p.l_um <= 0.19,
            observe=lambda a, b: (
                f"Vtn 从 {a.s.vtn:.3f} 掉到 {b.s.vtn:.3f} V（roll-off），DIBL 从 {a.s.dibl_n:.0f} 增到 "
                f"{b.s.dibl_n:.0f} mV/V，关态漏电 Ioff 从 {_ie(a.s.ioff_n)} 涨到 {_ie(b.s.ioff_n)}"
                f"（{_ratio(a.s.ioff_n, b.s.ioff_n)}）。管子更快了，但越来越“关不住”。",
                f"Vtn fell from {a.s.vtn:.3f} to {b.s.vtn:.3f} V (roll-off), DIBL rose from "
                f"{a.s.dibl_n:.0f} to {b.s.dibl_n:.0f} mV/V and Ioff grew from {_ie(a.s.ioff_n)} to "
                f"{_ie(b.s.ioff_n)} ({_ratio(a.s.ioff_n, b.s.ioff_n)}). Faster, but increasingly "
                "hard to switch off."),
            controls=["param:l_um"], demo=lambda s: {"params": {"l_um": 0.18}}, plot="vtl",
            deep=("roll-off：ΔVt = (Qdep/Cox)(xj/L)(√(1 + 2xdm/xj) − 1)；DIBL：σ ∝ exp(−L / 2l)，l = √(εSi/εox·tox·xj)。",
                  "Roll-off: ΔVt = (Qdep/Cox)(xj/L)(√(1 + 2xdm/xj) − 1); DIBL σ ∝ exp(−L / 2l), "
                  "l = √(εSi/εox·tox·xj).")),
        # 任务 3：在 Vt-L 图上比较有/无 LDD 的曲线，点「我看到了」—— 看 LDD 浅结能挽回多少 Vt
        Task(
            title=("LDD 帮了多少", "How much LDD helps"),
            explain=("灰色点线是“没有 LDD、源漏结很深”时的饱和 Vt。结越深，源漏伸到沟道里的耗尽区越大，短沟道效应越强。",
                     "The grey dotted line is the saturation Vt without LDD (deep junctions). Deeper "
                     "junctions push bigger depletion regions into the channel and worsen short-channel effects."),
            try_=("在 Vt-L 图上比较橙色实线和灰色点线在当前 L 处的差距，看完点「我看到了」。",
                  "Compare the orange line with the grey dotted line at the current L, then press 'Got it'."),
            check=lambda a, b: b.ack,
            observe=lambda a, b: (
                f"在 L = {b.p.l_um:.2f} µm 处，有 LDD 的 Vt 比深结高 {_ldd_gap(b) * 1e3:.0f} mV。"
                "浅结 (xj ≈ 80 nm) 让漏极更难“够到”源端，这是 0.25 µm 工艺引入 LDD + 侧墙的原因之一"
                "（另一个原因是降低漏端电场、减少热载流子损伤）。",
                f"At L = {b.p.l_um:.2f} µm the LDD device's Vt is {_ldd_gap(b) * 1e3:.0f} mV higher than "
                "with deep junctions. Shallow xj (~80 nm) keeps the drain from reaching the source, one "
                "reason the 0.25 µm node adopted LDD + spacers (the other is a gentler drain field and "
                "less hot-carrier damage)."),
            controls=["btn:ack"], demo=lambda s: {"ack": True}, plot="vtl", compare=False),
        # 任务 4：补救①，把掺杂提到 9e17 以上 —— 抑制短沟道效应，但也有代价
        Task(
            title=("补救①：提高掺杂", "Fix ①: more doping"),
            explain=("掺杂越高，PN 结的耗尽区越薄，源漏伸进沟道的“触手”就越短。",
                     "Higher doping makes the junction depletion regions thinner, so the source/drain "
                     "'reach' into the channel is shorter."),
            try_=("把衬底掺杂 Na 提高到 9e17 以上。", "Raise the substrate doping Na above 9e17."),
            check=lambda a, b: b.p.na_cm3 >= 9e17,
            observe=lambda a, b: (
                f"DIBL 从 {a.s.dibl_n:.0f} 变为 {b.s.dibl_n:.0f} mV/V，Vtn 从 {a.s.vtn:.3f} 升到 {b.s.vtn:.3f} V。"
                "但掺杂太高会降低载流子迁移率、增大结电容。真实工艺会只在需要的地方局部加掺杂（halo 注入）。"
                "缩小尺寸就是在这些矛盾之间不断找平衡。",
                f"DIBL went from {a.s.dibl_n:.0f} to {b.s.dibl_n:.0f} mV/V and Vtn from {a.s.vtn:.3f} to "
                f"{b.s.vtn:.3f} V. Too much doping hurts mobility and junction capacitance, so real flows "
                "add doping only where needed (halo implants). Scaling is a constant balancing act."),
            controls=["param:na_cm3"], demo=lambda s: {"params": {"na_cm3": 1e18}}, plot="vtl"),
        # 任务 5：补救②，把栅氧减到 3 nm 以下 —— 栅控更强，所以每一代缩小 L 都要同时减薄栅氧
        Task(
            title=("补救②：更薄的栅氧", "Fix ②: thinner oxide"),
            explain=("既然漏极在和栅极抢控制权，那就让栅极离沟道更近、抓得更紧。",
                     "If the drain is competing for control, bring the gate closer so it grips harder."),
            try_=("把栅氧 tox 减到 3 nm 以下，看 DIBL 和 Vt-L 曲线。",
                  "Reduce tox below 3 nm and watch DIBL and the Vt-L curves."),
            check=lambda a, b: b.p.tox_nm <= 3.0,
            observe=lambda a, b: (
                f"DIBL 从 {a.s.dibl_n:.0f} 降到 {b.s.dibl_n:.0f} mV/V，roll-off 也变小了。"
                "所以每一代工艺缩小 L 的同时，栅氧也必须跟着变薄，这叫按比例缩小 (scaling)。",
                f"DIBL dropped from {a.s.dibl_n:.0f} to {b.s.dibl_n:.0f} mV/V and roll-off shrank. That is "
                "why every generation thins the oxide together with L: scaling."),
            controls=["param:tox_nm"], demo=lambda s: {"params": {"tox_nm": 2.5}}, plot="vtl"),
    ]


# ---- 全部实验课的总列表（讲解页按这个顺序显示）----
# 每一项依次是：key（内部名字）、标题、一句话简介、开场白（这里为空，开场内容放在任务 0 里）、
# 使用的工艺流程（"locos" 或 "sti"）、任务列表；sim3d=True 表示自动打开 3D 载流子仿真。
LESSONS = [
    Lesson("switch", ("① MOS 管怎么开关", "① How a MOSFET switches"),
           ("拖动 Vin，看沟道出现、电流变化、CMOS 为什么省电", "Drag Vin: channel, current, why CMOS saves power"),
           ("", ""), "locos", _l1_tasks(), sim3d=True),
    Lesson("vt", ("② 工艺参数怎么决定 Vt", "② How the process sets Vt"),
           ("改栅氧厚度和掺杂，看阈值和电流怎么变", "Change oxide and doping; watch Vt and current"),
           ("", ""), "locos", _l2_tasks()),
    Lesson("inverter", ("③ 反相器与宽长比", "③ The inverter and W/L sizing"),
           ("调宽度、负载和电压，看翻转点、延迟和功耗", "Tune widths, load and supply: VM, delay, energy"),
           ("", ""), "locos", _l3_tasks()),
    Lesson("scaling", ("④ 缩小尺寸的代价", "④ The price of scaling"),
           ("把栅长越缩越短，认识短沟道效应和补救办法", "Shrink L, meet short-channel effects and the fixes"),
           ("", ""), "sti", _l4_tasks()),
]
