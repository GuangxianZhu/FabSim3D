"""MOSFET / CMOS inverter electrical model derived from process parameters.

Units: cm, F, A, V internally unless noted. All functions are pure numpy so they
can be unit-tested without Panda3D.

Model summary
-------------
* Threshold voltage from classic MOS-capacitor theory (Vfb + 2*phiF + Qdep/Cox),
  with dual-doped poly gates (n+ poly for NMOS, p+ poly for PMOS).
* Drain current: Level-1 square law in strong inversion, smoothly extended into
  sub-threshold with the EKV interpolation function
      Id = Is * [F((Vp-Vs)/phit) - F((Vp-Vd)/phit)] * (1 + lambda*Vds)
      F(v) = ln^2(1 + exp(v/2)),  Vp = (Vg - Vt)/n,  Is = 2*n*k'*(W/L)*phit^2
  In strong-inversion saturation this reduces to Id = k'(W/L)(Vgs-Vt)^2/(2n).
* Inverter VTC solved by vectorised bisection of Idn = Idp.
* Transient response by RK2 integration of CL*dVout/dt = Idp - Idn.
* Process-dependent second-order effects are applied through the EFFECTS
  chain, selected by the flow's feature set (e.g. {"locos"}, {"sti", "cmp"}).
* Metal gates (HKMG): when wf_n_ev / wf_p_ev are set, the gate work function
  replaces the n+/p+ poly in phi_ms, and tox is read as the EOT.
* Multi-gate devices (features "finfet" / "gaa"): an undoped fully depleted
  body whose short-channel behaviour is set by the natural length lambda of
  an N-gate structure instead of junction depth and doping.

【中文说明：这个文件是干什么的？】
本程序前半部分（3D 动画）演示"芯片是怎么一步步做出来的"；这个文件负责回答
"做出来的晶体管电学性能怎么样"。它把工艺参数（氧化层多厚、掺杂多浓、栅多长……）
换算成晶体管的电学参数，再算出由一个 NMOS + 一个 PMOS 组成的"反相器"
（最简单的数字电路：输入高 -> 输出低，输入低 -> 输出高）的特性曲线和开关速度。

几个必须先懂的概念（零基础版）：
* MOSFET（晶体管）：一个用电压控制的开关。"栅极(gate)"加电压，就在硅表面感应出
  一层能导电的"沟道"，电流就能从"源极(source)"流到"漏极(drain)"。
* NMOS 靠电子导电，栅极加正电压打开；PMOS 靠空穴导电，栅极加负电压（相对源极）打开。
* 阈值电压 Vt：开关"刚好打开"所需的栅压。小于 Vt 时基本关断（只有很小的漏电流）。
* 反相器 VTC（电压传输特性）：输出电压随输入电压变化的曲线。
* 瞬态（transient）：输入突然跳变时，输出要多久才能跟着变过去——这就是"延迟"，
  决定芯片能跑多快。

单位约定：程序内部长度一律用厘米(cm)、电容用法拉(F)、电流用安培(A)、电压用伏特(V)。
半导体教科书习惯用 cm 而不是 m，所以浓度单位是 cm^-3（每立方厘米多少个原子）。
"pure numpy"的意思是：这里只用数学库 numpy 做计算，不依赖 3D 引擎 Panda3D，
因此可以单独拿出来做自动测试。

这里的公式大多是教科书里的"简化模型"（例如一级平方律模型、EKV 插值），
目的是教学直观、趋势正确，而不是像工业仿真器那样精确到每一个 mV。
"""
# 中文：下面这行让 Python 允许在类型标注里写尚未定义的类名（例如函数返回 "ProcessParams"）。
from __future__ import annotations

# 中文：dataclass 是 Python 自带的"数据类"工具——只要列出字段，就自动生成构造函数等样板代码。
# replace(obj, 字段=新值) 会复制一个对象并改掉其中某些字段，原对象保持不变。
from dataclasses import dataclass, field, replace
import math   # 中文：Python 自带的数学函数库（sqrt 开方、log 对数、exp 指数……），处理单个数字
# 中文：typing 里的东西只用于"类型标注"（告诉读者某个变量应该是什么类型），不影响运行结果。
from typing import Callable, FrozenSet, List

# 中文：numpy 是科学计算库，可以对"一整列数字"（数组）一次性做运算，比逐个循环快得多。
# 约定俗成简写为 np。
import numpy as np

# ---------------------------------------------------------------------------
# 中文：物理常数（全大写的名字在 Python 里习惯表示"常量，不会改"）
# ---------------------------------------------------------------------------
Q = 1.602e-19          # C
# 中文：Q = 一个电子所带电荷量，单位库仑(C)。1.602e-19 是科学计数法，即 1.602 × 10^-19。
EPS0 = 8.854e-14       # F/cm
# 中文：EPS0 = 真空介电常数，单位 F/cm。描述"真空中电场能储存多少电荷"。
EPS_SI = 11.7 * EPS0
# 中文：EPS_SI = 硅的介电常数，是真空的 11.7 倍。
EPS_OX = 3.9 * EPS0
# 中文：EPS_OX = 二氧化硅(SiO2，栅氧化层)的介电常数，是真空的 3.9 倍。
NI = 1.0e10            # cm^-3 at 300 K
# 中文：NI = 本征载流子浓度：纯硅在室温(300 K)下自己热激发出的电子(=空穴)浓度，约 10^10 个/cm^3。
PHIT = 0.02585         # kT/q at 300 K (V)
# 中文：PHIT = 热电压 kT/q ≈ 25.85 mV。可以理解为"室温下热运动对应的电压尺度"，
#       很多半导体公式里的指数项都是 exp(电压 / PHIT)。
EG_HALF = 0.56         # Eg/2 of Si (V)
# 中文：EG_HALF = 硅禁带宽度的一半（硅的禁带宽度 Eg ≈ 1.12 eV），这里用伏特表示。
CHI_SI = 4.05          # electron affinity of Si (eV)
# 中文：CHI_SI = 硅的电子亲和能 4.05 eV：把电子从硅的导带底拿到真空需要的能量。
#       和金属栅的"功函数"比较时要用到它。
NWELL_DEPTH_CM = 2.0e-4  # junction depth after drive-in (2 um)
# 中文：N 阱（给 PMOS 用的 N 型区域）经过高温推进后的深度：2 微米 = 2e-4 厘米。


@dataclass
class ProcessParams:
    """Process knobs exposed in the UI (practical units).

    中文：工艺参数——界面上那些滑块能调的"旋钮"都存在这里。
    为什么要有它：把所有工艺输入集中到一个对象里，后面的物理计算只需要接收这一个对象。
    这里的单位用的是工程师习惯的"实用单位"（nm、um、fF 等），计算时再换算成 cm、F。
    写法说明：`名字: 类型 = 默认值` 是 dataclass 的字段定义；例如 tox_nm 默认 10 nm。
    """
    tox_nm: float = 10.0          # gate oxide thickness
    # 中文：↑ 栅氧化层厚度（nm）。越薄，栅对沟道的控制越强，电流越大，但漏电也越大。
    na_cm3: float = 1.0e17        # p-substrate / NMOS channel doping
    # 中文：↑ P 型衬底掺杂浓度（硼原子个数/cm^3），也是 NMOS 沟道的掺杂。越浓 NMOS 阈值越高。
    nwell_dose_cm2: float = 2.0e13  # n-well phosphorus implant dose
    # 中文：↑ N 阱磷注入"剂量"（每平方厘米打进去多少个磷原子），决定 PMOS 沟道的掺杂。
    l_um: float = 0.5             # drawn gate length
    # 中文：↑ 栅长 L（微米）：源和漏之间的距离。越短越快，但会出现"短沟道效应"。
    wn_um: float = 2.0            # NMOS width
    wp_um: float = 5.0            # PMOS width
    # 中文：↑ NMOS / PMOS 的宽度 W（微米）。越宽能通过的电流越大（像更宽的马路）。
    #       PMOS 通常做得更宽，是因为空穴迁移率比电子低，要靠加宽来补齐电流。
    vdd: float = 3.3              # supply
    # 中文：↑ 电源电压 VDD（伏特）。
    cload_ff: float = 50.0        # inverter load capacitance
    # 中文：↑ 反相器输出端的负载电容（fF，飞法 = 1e-15 法）：后面连着的导线和下一级电路。
    #       电容越大，充放电越慢，延迟越长。
    mu_n: float = 400.0           # effective electron mobility cm^2/Vs
    mu_p: float = 150.0           # effective hole mobility cm^2/Vs
    # 中文：↑ 迁移率 μ（cm^2/V·s）：载流子在电场下"跑得多快"。速度 = μ × 电场。
    #       电子(n)比空穴(p)跑得快约 2~3 倍。
    vsat_n: float = 1.0e7         # electron saturation velocity cm/s
    vsat_p: float = 8.0e6         # hole saturation velocity cm/s
    # 中文：↑ 饱和速度（cm/s）：电场很强时载流子速度不再增加的上限（类似"限速"）。
    qf_cm2: float = 1.0e10        # fixed oxide charge density
    # 中文：↑ 氧化层里的固定电荷密度（个/cm^2），是工艺不完美留下的，会让阈值电压偏移。
    lambda_um: float = 0.05       # CLM: lambda = lambda_um / L[um]  (1/V)
    # 中文：↑ 沟道长度调制系数（CLM）的参数：饱和后电流仍随漏压略微上升的程度，栅越短越明显。
    # advanced nodes (0 = not used, i.e. the classic poly-gate bulk device)
    # 中文：以下是先进工艺节点才用的参数；填 0 表示不用，即传统的"多晶硅栅 + 体硅"器件。
    wf_n_ev: float = 0.0          # NMOS metal-gate work function (eV)
    wf_p_ev: float = 0.0          # PMOS metal-gate work function (eV)
    # 中文：↑ 金属栅功函数（eV）：把电子从金属里拿出来需要的能量，直接决定阈值电压。
    xj_nm: float = 0.0            # S/D extension junction depth (planar)
    # 中文：↑ 源/漏扩展区的结深（nm）：源漏掺杂区往硅里扎多深。越浅，短沟道效应越弱。
    tsi_nm: float = 0.0           # fin width / nanosheet thickness (multi-gate)
    # 中文：↑ FinFET 鳍的宽度 / GAA 纳米片的厚度（nm）。越薄，栅对沟道控制越好。

    # 中文：@property 让下面这个"函数"可以像普通字段一样访问：写 p.nd_cm3，不用加括号。
    @property
    def nd_cm3(self) -> float:
        """N-well doping estimated from implant dose spread over the well depth.

        中文：估算 N 阱的掺杂浓度（个/cm^3）。
        原理（简化）：注入的剂量（个/cm^2）假设均匀摊在阱深度（cm）里，
        所以 浓度 = 剂量 ÷ 深度。真实分布是不均匀的，这里取平均值作为近似。
        """
        return self.nwell_dose_cm2 / NWELL_DEPTH_CM

    def copy(self, **kw) -> "ProcessParams":
        """中文：复制一份参数，并可顺便改几个字段，例如 p.copy(l_um=0.2)。
        `**kw` 表示"接收任意多个 名字=值 形式的参数"，打包成字典传给 replace。
        为什么要复制：扫描不同栅长等场景时，不能把用户当前的参数改掉。
        """
        return replace(self, **kw)


@dataclass
class Mosfet:
    """中文：一个晶体管的"电学参数卡片"。

    ProcessParams 描述"怎么做"，Mosfet 描述"做出来的管子电学上什么样"。
    它由下面的 _mos() 根据工艺参数算出来，再经过 EFFECTS 链（二阶效应）修正。
    同一个类同时表示 NMOS 和 PMOS，用 polarity 字段区分。
    """
    polarity: str        # "n" or "p"
    # 中文：↑ 极性："n" 表示 NMOS，"p" 表示 PMOS。
    vt: float            # threshold (signed; negative for PMOS)
    # 中文：↑ 阈值电压（带正负号；PMOS 的是负值）。
    kp: float            # k' = mu*Cox (A/V^2)
    # 中文：↑ 工艺跨导参数 k' = 迁移率 × 单位面积栅电容。越大，同样电压下电流越大。
    n: float             # sub-threshold slope factor
    # 中文：↑ 亚阈值斜率因子 n（≥1）。理想值 1；越接近 1，管子"关得越干脆"。
    w_um: float
    l_um: float
    # 中文：↑ 宽度 W 和长度 L（微米）。
    lam: float           # channel length modulation (1/V)
    # 中文：↑ 沟道长度调制系数 λ（1/V）。
    gamma: float         # body-effect coefficient (sqrt(V))
    # 中文：↑ 体效应系数 γ（单位 √V）：衬底电压对阈值的影响程度，掺杂越浓、氧化层越厚，γ 越大。
    phi_f: float         # |Fermi potential| (V)
    # 中文：↑ 费米势的绝对值（V）：衡量掺杂有多浓。掺杂越浓，phi_f 越大。
    vfb: float           # flat-band voltage (V)
    # 中文：↑ 平带电压（V）：让硅表面"能带不弯曲"（既不吸引也不排斥载流子）所需的栅压。
    doping: float        # channel doping (cm^-3)
    # 中文：↑ 沟道掺杂浓度（个/cm^3）。
    # short-channel extensions (all zero = long-channel model)
    # 中文：以下是短沟道效应的附加参数；全为 0 就退化成"长沟道"理想模型。
    dibl: float = 0.0    # DIBL coefficient sigma: |Vt| drops by sigma*|Vds|  (V/V)
    # 中文：↑ DIBL 系数 σ：漏极电压每升高 1 V，阈值降低 σ V（漏极"抢"了栅的控制权）。
    ec_l: float = 0.0    # Ec*L for velocity saturation (V); 0 disables it
    # 中文：↑ 临界电场 × 栅长（V），用于速度饱和；0 表示不考虑速度饱和。
    xj_um: float = 0.0   # S/D junction depth seen by the channel (um), informative
    vt_rolloff: float = 0.0  # |Vt| reduction from charge sharing (V), informative
    # 中文：↑ 这两项只是"记录下来给界面显示"的信息：结深、因电荷共享造成的阈值下降量。

    @property
    def vt_mag(self) -> float:
        """Threshold in magnitude convention (positive = enhancement) for both polarities.
        It can go negative when short-channel roll-off turns the device normally-on.

        中文：把阈值统一成"正数表示正常的增强型管子"的写法。
        PMOS 的 vt 本来是负的，取反后就和 NMOS 一样可以按同一套公式计算电流。
        如果短沟道效应太严重，这个值会变成负数，意思是管子"不加栅压也是开着的"（关不断）。
        写法说明：`A if 条件 else B` 是 Python 的一行版"如果……否则……"。
        """
        return self.vt if self.polarity == "n" else -self.vt

    @property
    def beta(self) -> float:
        """中文：β = k' × W / L（A/V^2）：整个管子的"电流能力"。
        W/L 是几何形状的影响：越宽越短，电流越大。"""
        return self.kp * self.w_um / self.l_um

    @property
    def ss_mv_dec(self) -> float:
        """中文：亚阈值摆幅 SS（mV/decade）：在阈值以下，电流每变化 10 倍需要多少栅压。
        公式 SS = n × (kT/q) × ln(10)，×1e3 把伏特换成毫伏。
        理想极限（n=1）约 60 mV/dec；数值越小，开关越陡、关态漏电越少。"""
        return self.n * PHIT * math.log(10) * 1e3

    def ids(self, vgs, vds):
        """Drain current magnitude for magnitude bias (for PMOS pass Vsg, Vsd).

        Accepts numpy broadcasting. Returns A (>= 0 for vds >= 0).

        中文：计算漏极电流（单位安培）——这是整个模型最核心的函数。
        输入：vgs = 栅源电压，vds = 漏源电压（PMOS 传入 Vsg、Vsd，即都用"正数大小"）。
        "numpy broadcasting（广播）"：vgs、vds 可以是单个数，也可以是一整列数，
        numpy 会自动逐个配对计算，一次算出整条曲线。

        用的是 EKV 模型（教科书简化模型）：一个公式同时覆盖
          - 阈值以下（亚阈值区）：电流随栅压指数增长（像二极管）；
          - 阈值以上（强反型区）：电流约等于平方律 k'(W/L)(Vgs-Vt)^2/(2n)。
        中间平滑过渡，不会出现分段公式的"断点"。
        """
        # 中文：把输入统一转成浮点数数组，方便后面用 numpy 一次算一整批。
        vgs = np.asarray(vgs, dtype=float)
        vds = np.asarray(vds, dtype=float)
        # 中文：DIBL 效应——漏压越高，有效阈值越低（np.abs 取绝对值）。
        vt = self.vt_mag - self.dibl * np.abs(vds)
        # 中文：Vp = "夹断电压"：栅压超过阈值多少，再除以斜率因子 n。
        #       n>1 表示栅压只有一部分（1/n）真正作用到沟道表面上。
        vp = (vgs - vt) / self.n
        # 中文：Is = 特征电流，是 EKV 模型里的"电流单位尺度"：2 n β (kT/q)^2。
        i_s = 2.0 * self.n * self.beta * PHIT ** 2
        # 中文：F(v) = [ln(1 + e^(v/2))]^2 —— EKV 插值函数。
        #   v 很负（远低于阈值）时 F ≈ e^v：指数关系 -> 亚阈值电流；
        #   v 很正（远高于阈值）时 F ≈ (v/2)^2：平方关系 -> 强反型平方律。
        # np.logaddexp(0, x) = ln(e^0 + e^x) = ln(1 + e^x)，这样写在 x 很大时也不会数值溢出。
        # f_fwd 是源端（正向）分量，f_rev 是漏端（反向）分量；漏压越大，f_rev 越小。
        f_fwd = np.logaddexp(0.0, vp / (2 * PHIT)) ** 2
        f_rev = np.logaddexp(0.0, (vp - vds) / (2 * PHIT)) ** 2
        # 中文：电流 = Is × (正向 - 反向) × (1 + λ|Vds|)。
        #   当 vds 足够大，f_rev ≈ 0，电流不再随 vds 增加 = "饱和区"；
        #   (1 + λ Vds) 是沟道长度调制：饱和后电流仍随漏压缓慢上升。
        i = i_s * (f_fwd - f_rev) * (1.0 + self.lam * np.abs(vds))
        if self.ec_l > 0:
            # velocity saturation: mobility degraded by the lateral field
            # 中文：速度饱和——沟道里横向电场太强时，载流子速度达到上限，电流被压低。
            #   vdse = 有效漏压，取 |Vds| 与 Vp 的较小者（饱和后有效值不再增加）；
            #   电流除以 (1 + vdse/(Ec·L))：Ec·L 越小（栅越短），压低得越厉害。
            vdse = np.minimum(np.abs(vds), np.maximum(vp, 0.0))
            i = i / (1.0 + vdse / self.ec_l)
        return i

    def idsat(self, vov_gate: float) -> float:
        """中文：饱和电流：栅压和漏压都取同一个值（通常是 VDD）时的电流，
        即管子"全开"时能提供的最大驱动电流。float(...) 把 numpy 结果转成普通数字。"""
        return float(self.ids(vov_gate, vov_gate))


def cox(p: ProcessParams) -> float:
    """Gate oxide capacitance per area (F/cm^2).

    中文：单位面积栅氧化层电容 Cox = ε_ox / t_ox（F/cm^2）。
    物理意义：栅极、氧化层、硅三者就像一个平板电容器，氧化层是中间的绝缘层。
    氧化层越薄，电容越大，栅极每加 1 V 能在沟道里感应出越多电荷 -> 电流越大。
    p.tox_nm * 1e-7：把纳米换算成厘米（1 nm = 1e-7 cm）。
    """
    return EPS_OX / (p.tox_nm * 1e-7)


def _mos(p: ProcessParams, polarity: str) -> Mosfet:
    """中文：根据工艺参数，用经典 MOS 电容理论算出一个"长沟道理想晶体管"的参数。
    名字前的下划线 _ 是 Python 的习惯，表示"内部使用的辅助函数"。
    二阶效应（窄宽度、短沟道、多栅）不在这里，而是由后面的 EFFECTS 链再叠加。
    """
    c = cox(p)
    # 中文：NMOS 做在 P 型衬底里（受主浓度 NA），PMOS 做在 N 阱里（施主浓度 ND）。
    doping = p.na_cm3 if polarity == "n" else p.nd_cm3
    # 中文：费米势 φF = (kT/q) × ln(掺杂浓度 / ni)。
    #   掺杂越浓，φF 越大；要在表面形成反型层（沟道），表面电势需要弯曲 2φF。
    phi_f = PHIT * math.log(doping / NI)
    # 中文：Qdep = 阈值时耗尽层里的电荷（C/cm^2）= sqrt(2 ε_si q N × 2φF)。
    #   栅极要先"抵消"这些被电离的掺杂原子的电荷，才能吸引来导电载流子。掺杂越浓，Qdep 越大。
    qdep = math.sqrt(2 * EPS_SI * Q * doping * 2 * phi_f)
    # 中文：体效应系数 γ = sqrt(2 q ε_si N) / Cox。
    gamma = math.sqrt(2 * Q * EPS_SI * doping) / c
    # 中文：氧化层固定电荷造成的电压偏移 = q × Qf / Cox。
    qf_over_cox = Q * p.qf_cm2 / c
    # 中文：如果用金属栅，取对应极性的功函数（为 0 表示仍用多晶硅栅）。
    wf = p.wf_n_ev if polarity == "n" else p.wf_p_ev
    if polarity == "n":
        # 中文：φms = 栅材料与硅之间的"功函数差"，就像两种材料天生的电势差。
        phi_ms = -(EG_HALF + phi_f)          # n+ poly on p-Si
        if wf > 0:                           # metal gate: phi_m - (chi + Eg/2 + phi_f)
            phi_ms = wf - (CHI_SI + EG_HALF + phi_f)
        # 中文：平带电压 Vfb = φms - Qf/Cox。
        vfb = phi_ms - qf_over_cox
        # 中文：NMOS 阈值电压（经典公式）：Vt = Vfb + 2φF + Qdep/Cox
        #   = 抵消材料电势差 + 把表面电势弯到反型所需 + 抵消耗尽层电荷所需的栅压。
        vt = vfb + 2 * phi_f + qdep / c
        mu = p.mu_n
        w = p.wn_um
    else:
        # 中文：PMOS 情况同理，只是各项符号相反（电荷和电势方向都反过来），所以 Vt 是负的。
        phi_ms = EG_HALF + phi_f             # p+ poly on n-Si
        if wf > 0:                           # metal gate on n-Si
            phi_ms = wf - (CHI_SI + EG_HALF - phi_f)
        vfb = phi_ms - qf_over_cox
        vt = vfb - 2 * phi_f - qdep / c
        mu = p.mu_p
        w = p.wp_um
    # 中文：亚阈值斜率因子 n = 1 + γ / (2 sqrt(2φF + 6 kT/q))（教科书近似）。
    #   直观：栅压被"氧化层电容"和"耗尽层电容"分压，只有一部分作用在表面；
    #   耗尽层电容越大（掺杂越浓），n 越大，开关越不陡。
    n = 1.0 + gamma / (2.0 * math.sqrt(2 * phi_f + 6 * PHIT))
    # 中文：把算好的数据装进 Mosfet 卡片返回。k' = μ × Cox；λ = lambda_um / L（栅越短越大）。
    return Mosfet(
        polarity=polarity, vt=vt, kp=mu * c, n=n, w_um=w, l_um=p.l_um,
        lam=p.lambda_um / p.l_um, gamma=gamma, phi_f=phi_f, vfb=vfb, doping=doping,
    )


# --------------------------------------------------------------------------
# Second-order effects chain
# --------------------------------------------------------------------------
# An effect is f(p, mos, features) -> Mosfet.  It may adjust vt, kp, n, lam ...
# and must return the device unchanged when its feature flag is absent.
# Planned additions: LDD/silicide series resistance, gate tunnelling leakage.
# 中文：【二阶效应链】
# 理想模型之外，真实器件还有各种"二阶效应"，跟具体工艺流程有关。
# 每个效应是一个函数：输入(工艺参数, 晶体管, 工艺特征集合)，输出修正后的晶体管。
# "features" 是一组标签，比如 {"locos"} 表示用 LOCOS 隔离、{"sti","cmp"} 表示用浅槽隔离+化学机械抛光。
# 某个效应的标签不存在时，函数必须原样返回晶体管——这样可以把所有效应依次"串"起来套用。
# 下面这行定义了一个"类型别名" Effect：Callable[[参数类型...], 返回类型] 表示"一种函数"。
Effect = Callable[[ProcessParams, Mosfet, FrozenSet[str]], Mosfet]


def _xdm_cm(m: Mosfet) -> float:
    """Maximum depletion width at threshold.

    中文：阈值时的最大耗尽层宽度 xdm（cm）= sqrt(2 ε_si × 2φF / (q N))。
    耗尽层 = 栅极电场把载流子赶走后留下的"空"区域。掺杂越浓，耗尽层越薄。
    窄宽度效应和短沟道效应都要用到它。
    """
    return math.sqrt(2 * EPS_SI * 2 * m.phi_f / (Q * m.doping))


def narrow_width_effect(p: ProcessParams, m: Mosfet, features: FrozenSet[str]) -> Mosfet:
    """Isolation-dependent narrow-width Vt shift (qualitative teaching model).

    LOCOS: the bird's beak and field implant add fringing depletion charge at
    the channel edges -> |Vt| rises for narrow W:
        d|Vt| = (Qdep/Cox) * pi*xdm / (2W)
    STI: field crowding at the trench corners turns the edges on early ->
    inverse narrow-width effect, |Vt| falls:
        d|Vt| = -(Qdep/Cox) * xdm / (2W)

    中文：窄宽度效应（定性的教学模型）——管子很窄时，阈值会随隔离方式而变化。
    * LOCOS 隔离（局部氧化）：边缘的"鸟嘴"氧化层和场区注入，让沟道两侧多出一些要栅极去
      抵消的耗尽电荷 -> 阈值绝对值升高；W 越窄，边缘占比越大，影响越明显（公式里除以 W）。
    * STI 隔离（浅槽隔离）：沟槽拐角处电场集中，边缘提前导通 -> 阈值反而降低（"反窄宽度效应"）。
    两种情况只是系数 k 不同（π/2 或 -0.5）。
    """
    # 中文：根据工艺特征选系数 k；两种隔离都没有，就不做修正，原样返回。
    if "locos" in features:
        k = math.pi / 2
    elif "sti" in features:
        k = -0.5
    else:
        return m
    # 中文：Qdep/Cox 可以用 γ × sqrt(2φF) 计算（两者在数学上相等）。
    qdep_cox = m.gamma * math.sqrt(2 * m.phi_f)
    # 中文：阈值变化量 d = (Qdep/Cox) × k × xdm / W；m.w_um * 1e-4 把微米换成厘米。
    d = qdep_cox * k * _xdm_cm(m) / (m.w_um * 1e-4)
    # 中文：NMOS 的 vt 为正、PMOS 为负，用 sign 保证"绝对值"朝同一方向变化。
    sign = 1.0 if m.polarity == "n" else -1.0
    return replace(m, vt=m.vt + sign * d)


XJ_DEEP_UM = 0.25    # conventional S/D junction depth
XJ_LDD_UM = 0.08     # shallow LDD extension at the channel edge
# 中文：↑ 两个默认结深：传统深源漏 0.25 um；LDD（轻掺杂漏）浅扩展区 0.08 um。
#   LDD 是在沟道边缘做的一小段浅而轻的掺杂，用来减弱靠近漏端的强电场。


def short_channel_effect(p: ProcessParams, m: Mosfet, features: FrozenSet[str]) -> Mosfet:
    """Short-channel effects for real flows (feature "sce").

    The junction depth seen by the channel is the LDD depth when the flow has
    LDD ("ldd" feature), otherwise the deep S/D junction.

    * Vt roll-off (Yau charge sharing):
        d|Vt| = -(Qdep/Cox) * (xj/L) * (sqrt(1 + 2*xdm/xj) - 1)
    * DIBL: |Vt| drops by sigma*|Vds|,  sigma = exp(-L / (2*l)),
      natural length l = sqrt(eps_si/eps_ox * tox * sqrt(xj * xdm))
      (thinner oxide, shallower junctions and heavier doping all shorten l)
    * Velocity saturation: Id / (1 + Vds_eff/(Ec*L)),  Ec = 2*vsat/mu
    * Slope degradation: n -> n / (1 - 2*sigma)

    中文：短沟道效应（平面体硅器件，工艺特征 "sce" 时启用）。
    栅长 L 很短时，源和漏离得太近，它们也会"插手"控制沟道，栅极不再说了算。具体包括：
    * 阈值滚降（Yau 电荷共享模型）：沟道下的耗尽电荷有一部分其实由源/漏结"代劳"，
      栅极需要负担的变少 -> 阈值下降。L 越短、结深 xj 越深，下降越多。
    * DIBL（漏致势垒降低）：漏压越高，阈值越低，σ = exp(-L / 2l)。
      l 是"特征长度"：静电影响能传播多远。L 比 l 大很多时 σ 很快趋近 0（影响按指数衰减）。
      氧化层越薄、结越浅、掺杂越浓，l 越小，短沟道效应越弱。
    * 速度饱和：短沟道里电场强，载流子速度到达上限，电流被压低。Ec = 2 vsat / μ 是临界电场。
    * 斜率退化：漏极同样削弱了栅的控制，n 变大（开关不再那么陡）。
    这些都是教科书级的简化公式。
    """
    # 中文：没有 "sce" 标签，或者是多栅器件（由 multigate_effect 单独处理），就不修正。
    if "sce" not in features or _gates(features):
        return m
    # 中文：确定沟道"看到"的结深 xj（单位 cm）。
    #   先进平面工艺：用用户给定的 xj_nm（有 LDD 用原值，否则按 3 倍深的源漏）；
    #   传统工艺：用上面的默认值。1e-7 是 nm->cm，1e-4 是 um->cm。
    if p.xj_nm > 0:      # advanced planar node: shallow extension, deep S/D about 3x deeper
        xj = p.xj_nm * (1 if "ldd" in features else 3) * 1e-7
    else:
        xj = (XJ_LDD_UM if "ldd" in features else XJ_DEEP_UM) * 1e-4
    L = m.l_um * 1e-4
    qdep_cox = m.gamma * math.sqrt(2 * m.phi_f)
    xdm = _xdm_cm(m)
    # 中文：阈值滚降量（Yau 公式），见上方 docstring。
    rolloff = qdep_cox * (xj / L) * (math.sqrt(1 + 2 * xdm / xj) - 1)
    # 中文：特征长度 l 和 DIBL 系数 σ。
    l_char = math.sqrt(EPS_SI / EPS_OX * p.tox_nm * 1e-7 * math.sqrt(xj * xdm))
    sigma = math.exp(-L / (2 * l_char))
    # 中文：速度饱和参数 Ec·L = (2 vsat / μ) × L。
    mu = p.mu_n if m.polarity == "n" else p.mu_p
    vsat = p.vsat_n if m.polarity == "n" else p.vsat_p
    ec_l = 2 * vsat / mu * L
    sign = 1.0 if m.polarity == "n" else -1.0
    # the drain also degrades the sub-threshold slope through the same coupling
    # 中文：斜率退化 n -> n / (1 - 2σ)；用 max(..., 0.2) 防止分母变成 0 或负数导致结果爆炸。
    n = m.n / max(1.0 - 2.0 * sigma, 0.2)
    # 中文：返回修正后的晶体管：阈值绝对值减去滚降量，并记录 DIBL、速度饱和、结深等信息。
    return replace(m, vt=m.vt - sign * rolloff, dibl=sigma, ec_l=ec_l, n=n,
                   xj_um=xj * 1e4, vt_rolloff=rolloff)


def _gates(features: FrozenSet[str]) -> int:
    """Equivalent number of gates around the channel (Colinge): 0 = planar bulk.

    中文：沟道周围"等效有几个栅"。普通平面管只有顶部一个栅（这里记为 0，表示不用多栅模型）；
    FinFET 鳍的三面被栅包住，记 3；GAA（环栅）四面全包，记 4。栅越多，对沟道控制越强。
    """
    if "gaa" in features:
        return 4
    if "finfet" in features:
        return 3
    return 0


PSI_INV = PHIT * math.log(1e18 / NI)   # band bending for n = 1e18 cm^-3 at the surface (V)
# 中文：↑ 多栅器件"反型"所需的表面电势：让表面电子浓度达到 1e18 /cm^3 需要弯曲多少电势。
VBI_EFF = 0.5                          # built-in potential seen across the channel ends (V)
# 中文：↑ 源/漏与沟道之间 PN 结的有效内建电势（V），用于估算多栅器件的阈值滚降。


def natural_length_cm(p: ProcessParams, n_gates: int) -> float:
    """Electrostatic scale length of an N-gate thin body (Suzuki / Colinge):
        lambda = sqrt(eps_si/(N*eps_ox) * tsi * tox * (1 + eps_ox*tsi/(4*eps_si*tox)))
    A thinner body, thinner EOT and more gates all shrink lambda, i.e. the
    gate keeps control over a shorter channel.

    中文：多栅薄体器件的"自然长度" λ（cm）：源/漏的静电影响在沟道里能延伸多远。
    λ 越小，栅越"霸道"，短沟道效应越弱，栅长就可以做得越短。
    公式里：tsi = 硅体厚度，tox = 氧化层（等效）厚度，N = 栅的个数。
    硅体越薄、氧化层越薄、栅越多 -> λ 越小。这就是为什么先进工艺要做 FinFET、GAA。
    """
    tsi = p.tsi_nm * 1e-7
    tox = p.tox_nm * 1e-7
    return math.sqrt(EPS_SI / (n_gates * EPS_OX) * tsi * tox * (1 + EPS_OX * tsi / (4 * EPS_SI * tox)))


def multigate_effect(p: ProcessParams, m: Mosfet, features: FrozenSet[str]) -> Mosfet:
    """FinFET / gate-all-around device (features "finfet" (3 gates) or "gaa" (4)).

    The undoped thin body is fully depleted, so Vt is set by the gate work
    function, not by channel doping, and there is almost no body effect:
        Vtn = (WF - chi - Eg/2) + psi_inv + q*N*tsi/(N_g*Cox) + dE_qc - roll-off
    Short-channel effects follow exp(-L / 2*lambda):
        DIBL sigma = exp(-L/2l),  n = 1 / (1 - 2 exp(-L/2l)),
        roll-off = 2*Vbi*exp(-L/2l)

    中文：FinFET（3 栅）/ GAA 环栅（4 栅）器件模型。
    这类器件的硅体又薄又基本不掺杂，整个被耗尽，所以：
    * 阈值主要由金属栅功函数决定（WF - χ - Eg/2），而不是靠沟道掺杂；
    * 几乎没有体效应（γ 取一个很小的值）；
    * 短沟道效应全部按 exp(-L / 2λ) 衰减：L 比 λ 大得越多，DIBL、斜率退化、阈值滚降都越小。
    阈值公式各项：功函数差 + 反型所需表面电势 + 体内少量掺杂电荷 + 量子限制修正 - 滚降。
    这里会完全重新计算 vt 和 n，覆盖 _mos() 里按体硅算出的值。
    """
    # 中文：不是多栅器件，或者没给硅体厚度，就不处理。
    ng = _gates(features)
    if not ng or p.tsi_nm <= 0:
        return m
    c = cox(p)
    lam = natural_length_cm(p, ng)
    L = m.l_um * 1e-4
    # 中文：e = exp(-L/2λ)：所有短沟道效应的共同"衰减因子"。
    e = math.exp(-L / (2 * lam))
    # 中文：斜率因子 n 和阈值滚降，max(..., 0.2) 同样是防止分母过小。
    n = 1.0 / max(1.0 - 2.0 * e, 0.2)
    rolloff = 2 * VBI_EFF * e
    # 中文：体内残余掺杂电荷对阈值的贡献 = q N tsi / (栅数 × Cox)；不掺杂时几乎为 0。
    qbody = Q * m.doping * p.tsi_nm * 1e-7 / ng / c
    # 中文：量子限制效应：硅体太薄时，电子能级被"挤高"，阈值略升；厚度越小影响越大（∝ 1/tsi^2）。
    qc = 0.3 / p.tsi_nm ** 2                    # quantum-confinement shift (V), ~10 mV at 5 nm
    wf = p.wf_n_ev if m.polarity == "n" else p.wf_p_ev
    if m.polarity == "n":
        # 中文：`wf or 默认值`：若 wf 为 0（没设置），就用"中带"功函数 χ+Eg/2 作为默认值。
        wf = wf or CHI_SI + EG_HALF
        vt = (wf - CHI_SI - EG_HALF) + PSI_INV + qbody + qc - rolloff
    else:
        # 中文：PMOS 符号相反。
        wf = wf or CHI_SI + EG_HALF
        vt = (wf - CHI_SI - EG_HALF) - PSI_INV - qbody - qc + rolloff
    mu = p.mu_n if m.polarity == "n" else p.mu_p
    vsat = p.vsat_n if m.polarity == "n" else p.vsat_p
    # 中文：返回更新后的晶体管；xj_um=0 因为多栅器件不用结深来描述短沟道效应。
    return replace(m, vt=vt, n=n, gamma=0.02, dibl=e, ec_l=2 * vsat / mu * L,
                   xj_um=0.0, vt_rolloff=rolloff)


# 中文：效应链：按顺序依次套用的二阶效应函数列表。以后增加新效应，只要加到这个列表里即可。
EFFECTS: List[Effect] = [narrow_width_effect, short_channel_effect, multigate_effect]


def nmos(p: ProcessParams, features: FrozenSet[str] = frozenset()) -> Mosfet:
    """中文：得到最终的 NMOS：先算理想长沟道参数，再依次套用效应链里的每个修正。
    features 默认是 frozenset()（一个空的、不可修改的集合），即不考虑任何二阶效应。"""
    m = _mos(p, "n")
    for eff in EFFECTS:
        m = eff(p, m, features)
    return m


def pmos(p: ProcessParams, features: FrozenSet[str] = frozenset()) -> Mosfet:
    """中文：同 nmos()，得到最终的 PMOS。"""
    m = _mos(p, "p")
    for eff in EFFECTS:
        m = eff(p, m, features)
    return m


# --------------------------------------------------------------------------
# Inverter
# --------------------------------------------------------------------------
# 中文：【反相器】PMOS 接在电源 VDD 和输出之间（负责把输出"拉高"），
#       NMOS 接在输出和地之间（负责把输出"拉低"），两管栅极连在一起作为输入。

def inverter_vout(p: ProcessParams, vin, n_iter: int = 60, features: FrozenSet[str] = frozenset()):
    """Static output voltage for input(s) vin (vectorised bisection).

    中文：给定输入电压 vin，求反相器稳定后的输出电压 Vout。
    原理：稳态时（输出不再变化）没有电流流进/流出输出端（负载电容），
    所以 NMOS 往下拉的电流 = PMOS 往上推的电流：Idn(Vout) = Idp(Vout)。
    这个方程没有简单的解析解，于是用"二分法"求解：
      Vout 一定在 0 ~ VDD 之间；每次取中点试一下，看电流差是正是负，
      就能知道答案在左半还是右半，范围减半。重复 60 次，精度远超需要。
    "vectorised（向量化）"：vin 可以是一整列输入电压，所有点同时做二分，速度快。
    """
    mn, mp = nmos(p, features), pmos(p, features)
    # 中文：np.atleast_1d 保证 vin 至少是一维数组（哪怕只传了一个数）。
    vin = np.atleast_1d(np.asarray(vin, dtype=float))
    # 中文：搜索区间的下界 lo 全是 0，上界 hi 全是 VDD（和 vin 同样长度）。
    lo = np.zeros_like(vin)
    hi = np.full_like(vin, p.vdd)
    # 中文：`for _ in range(n_iter)` 表示重复 n_iter 次；变量名 _ 表示"循环序号用不到"。
    for _ in range(n_iter):
        mid = 0.5 * (lo + hi)
        # 中文：f = NMOS 电流 - PMOS 电流。PMOS 用"源在 VDD"的正值写法：Vsg = VDD-Vin，Vsd = VDD-Vout。
        f = mn.ids(vin, mid) - mp.ids(p.vdd - vin, p.vdd - mid)
        # f increases monotonically with Vout
        # 中文：Vout 越高，NMOS 电流越大、PMOS 电流越小，所以 f 随 Vout 单调递增。
        #   f > 0 说明 mid 偏高 -> 答案在下半，把 hi 移到 mid；否则把 lo 移到 mid。
        #   np.where(条件, A, B)：逐个元素判断，条件成立取 A，否则取 B。
        hi = np.where(f > 0, mid, hi)
        lo = np.where(f > 0, lo, mid)
    return 0.5 * (lo + hi)


@dataclass
class VTCResult:
    """中文：反相器电压传输特性（VTC）的计算结果，打包给界面画图和显示数值。"""
    vin: np.ndarray
    vout: np.ndarray
    # 中文：↑ 输入电压序列和对应的输出电压序列（画曲线用）。
    gain: np.ndarray
    # 中文：↑ 增益 = dVout/dVin（曲线斜率），反相器中间段斜率为很大的负数。
    vm: float
    # 中文：↑ 开关阈值 VM：Vout = Vin 的那个点，理想情况在 VDD/2 附近。
    vil: float
    vih: float
    # 中文：↑ VIL / VIH：增益刚好 = -1 的两个输入点。低于 VIL 稳当地算"0"，高于 VIH 稳当地算"1"。
    voh: float
    vol: float
    # 中文：↑ VOH / VOL：输出高电平和低电平。
    nmh: float
    nml: float
    # 中文：↑ 噪声容限 NMH = VOH - VIH、NML = VIL - VOL：信号能容忍多大的干扰而不出错。
    max_gain: float
    # 中文：↑ 最大增益（取正值）。
    i_short: np.ndarray = field(repr=False, default=None)
    # 中文：↑ 每个输入点下从 VDD 直通到地的"短路电流"（两个管子同时半开时最大）。
    #   field(repr=False, ...) 表示打印这个对象时不显示这一项（数组太长）。


def vtc(p: ProcessParams, npts: int = 601, features: FrozenSet[str] = frozenset()) -> VTCResult:
    """中文：计算反相器的整条电压传输曲线和各项关键指标。
    为什么需要：这些指标（VM、噪声容限、增益）是判断"数字电路能不能可靠工作"的标准。
    """
    # 中文：在 0 ~ VDD 之间均匀取 npts 个输入电压点，一次性解出所有输出电压。
    vin = np.linspace(0.0, p.vdd, npts)
    vout = inverter_vout(p, vin, features=features)
    # 中文：np.gradient 用数值差分求斜率 dVout/dVin。
    gain = np.gradient(vout, vin)
    # 中文：找 Vout - Vin = 0 的位置（开关阈值 VM），用线性插值 np.interp。
    #   np.interp 要求横坐标递增，而 Vout-Vin 是递减的，所以用 [::-1] 把数组倒序。
    vm = float(np.interp(0.0, (vout - vin)[::-1], vin[::-1]))
    # 中文：找出所有斜率比 -1 更陡的点；第一个是 VIL，最后一个是 VIH。
    #   np.where(条件)[0] 返回满足条件的下标数组；.size 是元素个数。
    steep = np.where(gain < -1.0)[0]
    if steep.size:
        vil = float(vin[steep[0]])
        vih = float(vin[steep[-1]])
    else:
        # 中文：曲线太平（增益始终不到 1），就退化为都等于 VM。
        vil = vih = vm
    # 中文：输入 0 时输出为高电平 VOH；输入 VDD 时输出为低电平 VOL。（[-1] 表示最后一个元素）
    voh, vol = float(vout[0]), float(vout[-1])
    # 中文：稳态时流过 NMOS 的电流就是从电源到地的直通电流。
    i_short = nmos(p, features).ids(vin, vout)
    # 中文：组装结果；NMH = VOH-VIH，NML = VIL-VOL，最大增益取 -min(gain)。
    return VTCResult(vin, vout, gain, vm, vil, vih, voh, vol,
                     voh - vih, vil - vol, float(-gain.min()), i_short)


@dataclass
class TransientResult:
    """中文：瞬态仿真结果：时间轴、输入波形、输出波形，以及两个传播延迟。"""
    t: np.ndarray        # s
    vin: np.ndarray
    vout: np.ndarray
    tphl: float          # s (nan if not found)
    # 中文：↑ tPHL：输出从高变低的延迟（秒）；找不到交叉点时为 nan（"不是一个数"）。
    tplh: float
    # 中文：↑ tPLH：输出从低变高的延迟（秒）。


def _cross(t, v, level, rising: bool, after: float) -> float:
    """中文：找波形 v 在时刻 after 之后第一次穿过电压 level 的精确时间。
    rising=True 找上升穿越，False 找下降穿越。用来测量"输出到达一半电压的时刻"。
    """
    # 中文：只看 after 之后的那段波形（mask 是一列 True/False，用来筛选数组元素）。
    mask = t >= after
    tt, vv = t[mask], v[mask]
    # 中文：s = 电压与目标值的差；符号从负变正就是上升穿越，从正变负就是下降穿越。
    #   s[:-1] 是"除最后一个外的所有点"，s[1:] 是"除第一个外的所有点"，两者对齐即相邻两点比较。
    #   & 表示两个条件逐元素"同时成立"。行末的反斜杠 \ 表示这一行代码在下一行继续。
    s = vv - level
    idx = np.where((s[:-1] < 0) & (s[1:] >= 0))[0] if rising else \
        np.where((s[:-1] > 0) & (s[1:] <= 0))[0]
    if idx.size == 0:
        return float("nan")
    # 中文：在穿越点前后两个采样点之间做线性插值，得到比采样间隔更精确的时间。
    i = idx[0]
    return float(tt[i] + (tt[i + 1] - tt[i]) * (level - vv[i]) / (vv[i + 1] - vv[i]))


def transient(p: ProcessParams, nsteps: int = 3000, features: FrozenSet[str] = frozenset()) -> TransientResult:
    """Pulse response of the inverter driving CL.

    中文：反相器带负载电容 CL 时，对一个输入脉冲（先升后降）的响应。
    物理核心：输出端就是一个电容，电容电压的变化速度 = 净流入电流 / 电容：
        CL × dVout/dt = Idp（PMOS 充电） - Idn（NMOS 放电）
    这是一个微分方程，用数值方法（RK2，二阶龙格-库塔法）一小步一小步往前推算。
    最后测出两个传播延迟 tPHL、tPLH——芯片速度的直接体现。
    """
    mn, mp = nmos(p, features), pmos(p, features)
    cl = p.cload_ff * 1e-15   # 中文：fF -> F
    # 中文：估算时间尺度 τ = CL × VDD / I：用驱动电流把电容充满大约要多久。
    #   取两管中较弱的那个；max(..., 1e-12) 防止电流为 0 时除以 0。
    i_drive = max(min(mn.idsat(p.vdd), mp.idsat(p.vdd)), 1e-12)
    tau = cl * p.vdd / i_drive
    # 中文：根据 τ 自动安排仿真时长和输入波形：总时长 14τ，边沿时间 0.3τ，
    #   在 1τ 时刻输入开始上升，7τ 时刻开始下降。这样无论器件快慢，图上都能看清楚。
    t_end = 14 * tau
    tr = 0.3 * tau
    t1, t2 = 1.0 * tau, 7.0 * tau
    t = np.linspace(0.0, t_end, nsteps)
    dt = t[1] - t[0]   # 中文：每一步的时间间隔

    # 中文：函数里面还能定义函数（"内部函数"），它可以直接使用外层的变量（如 t1、tr、p）。
    def vin_at(tt):
        """中文：输入梯形脉冲在时刻 tt 的电压：线性上升 -> 保持高 -> 线性下降。
        np.clip(x, 0, 1) 把数值限制在 0~1 之间。"""
        up = np.clip((tt - t1) / tr, 0, 1)
        down = np.clip((tt - t2) / tr, 0, 1)
        return p.vdd * (up - down)

    def dvdt(tt, v):
        """中文：输出电压的变化速率 dVout/dt = (PMOS 充电电流 - NMOS 放电电流) / CL。"""
        vi = vin_at(tt)
        return (mp.ids(p.vdd - vi, p.vdd - v) - mn.ids(vi, v)) / cl

    vin = vin_at(t)
    vout = np.empty_like(t)   # 中文：准备一个和 t 一样长的空数组，用来存输出波形
    # 中文：初始输出 = 输入为 0 时的稳态输出（应接近 VDD）。[0] 取数组中的第一个值。
    v = float(inverter_vout(p, 0.0, features=features)[0])
    # 中文：RK2（Heun 法）逐步积分。enumerate 同时给出序号 k 和值 tk。
    #   k1 = 当前点的斜率；k2 = 按 k1 走一步后那个点的斜率；用两者平均值前进，比只用 k1 更准。
    #   np.clip 把电压限制在 -0.5 ~ VDD+0.5，防止数值不稳定时跑飞。
    for k, tk in enumerate(t):
        vout[k] = v
        k1 = dvdt(tk, v)
        k2 = dvdt(tk + dt, v + dt * k1)
        v = float(np.clip(v + 0.5 * dt * (k1 + k2), -0.5, p.vdd + 0.5))
    # 中文：传播延迟的定义：从输入到达 VDD/2 到输出到达 VDD/2 的时间差。
    #   输入边沿是线性的，所以输入到达一半的时刻 = 边沿起点 + tr/2。
    half = p.vdd / 2
    t_in_rise = t1 + tr / 2
    t_in_fall = t2 + tr / 2
    # 中文：输入上升 -> 输出下降（tPHL）；输入下降 -> 输出上升（tPLH）。
    tphl = _cross(t, vout, half, rising=False, after=t1) - t_in_rise
    tplh = _cross(t, vout, half, rising=True, after=t2) - t_in_fall
    return TransientResult(t, vin, vout, tphl, tplh)


@dataclass
class Summary:
    """中文：所有电学结果的"总表"，界面上的电学面板从这里取数显示。"""
    cox: float
    # 中文：↑ 栅氧电容 Cox（F/cm^2）
    vtn: float
    vtp: float
    # 中文：↑ NMOS / PMOS 阈值电压（V）
    kpn: float
    kpp: float
    # 中文：↑ NMOS / PMOS 的 k'（A/V^2）
    gamma_n: float
    gamma_p: float
    # 中文：↑ 体效应系数
    ss_n: float
    ss_p: float
    # 中文：↑ 亚阈值摆幅（mV/dec）
    idsat_n: float
    idsat_p: float
    # 中文：↑ 饱和电流（A）
    ioff_n: float
    # 中文：↑ NMOS 关态漏电流：栅压 0、漏压 VDD 时的电流（A）
    nd: float
    # 中文：↑ N 阱掺杂浓度（cm^-3）
    vtc: VTCResult
    tran: TransientResult
    # 中文：↑ 电压传输特性和瞬态结果
    dibl_n: float = 0.0        # mV/V
    dibl_p: float = 0.0
    rolloff_n: float = 0.0     # V
    rolloff_p: float = 0.0
    xj_um: float = 0.0
    # 中文：↑ 短沟道相关：DIBL（mV/V）、阈值滚降（V）、结深（um）


def summarize(p: ProcessParams, features: FrozenSet[str] = frozenset()) -> Summary:
    """中文：一次性算出所有电学结果并打包成 Summary。界面每次参数改变后调用它。"""
    mn, mp = nmos(p, features), pmos(p, features)
    return Summary(
        cox=cox(p), vtn=mn.vt, vtp=mp.vt, kpn=mn.kp, kpp=mp.kp,
        gamma_n=mn.gamma, gamma_p=mp.gamma, ss_n=mn.ss_mv_dec, ss_p=mp.ss_mv_dec,
        idsat_n=mn.idsat(p.vdd), idsat_p=mp.idsat(p.vdd),
        ioff_n=float(mn.ids(0.0, p.vdd)), nd=p.nd_cm3,
        vtc=vtc(p, features=features), tran=transient(p, features=features),
        # 中文：DIBL 系数 ×1e3 从 V/V 换成 mV/V，更直观。
        dibl_n=mn.dibl * 1e3, dibl_p=mp.dibl * 1e3, rolloff_n=mn.vt_rolloff,
        rolloff_p=mp.vt_rolloff, xj_um=mn.xj_um,
    )


def vt_vs_length(p: ProcessParams, features: FrozenSet[str], polarity: str = "n",
                 l_min: float = 0.1, l_max: float = 5.0, npts: int = 80):
    """|Vt| versus gate length at low |Vds| (0.05 V) and at |Vds| = VDD.

    Returns (L_um, vt_lin, vt_sat).  Shows Vt roll-off (lin) and DIBL (sat - lin).

    中文：画"阈值电压随栅长变化"曲线用的数据。
    对一系列栅长，分别算低漏压（0.05 V，线性区）和高漏压（VDD，饱和区）下的 |Vt|。
    - 线性区曲线随 L 变短而下降 = 阈值滚降；
    - 两条曲线之间的差距 = DIBL 的大小。
    这是展示"为什么栅长不能无限缩短"的经典图。
    """
    # 中文：np.geomspace 按"等比"取点（对数均匀），短栅长区域取点更密。
    ls = np.geomspace(l_min, l_max, npts)
    lin, sat = [], []
    for L in ls:
        # 中文：(nmos if ... else pmos) 先选出要用的函数，再用 (...) 调用它。
        #   p.copy(l_um=L) 只改栅长、其他参数不变。
        m = (nmos if polarity == "n" else pmos)(p.copy(l_um=float(L)), features)
        lin.append(m.vt_mag - m.dibl * 0.05)
        sat.append(m.vt_mag - m.dibl * p.vdd)
    return ls, np.array(lin), np.array(sat)
