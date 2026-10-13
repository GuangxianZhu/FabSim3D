"""器件物理模型（fabsim3d/device_model.py）的自动化测试。

什么是“自动化测试”？
    测试是一段用来检查别的代码是否正确的小程序。每个 test_ 开头的函数是一项检查，
    里面的 assert（断言）写的是“结果应当满足的条件”；条件不成立就报错，表示测试失败。
    改了物理公式之后跑一遍测试，就能立刻发现是不是把某个规律算反了、算错了数量级。

怎么运行？
    在项目根目录打开命令行，输入：
        python -m pytest tests/test_device_model.py
    （只输入 python -m pytest 会运行 tests 文件夹里的全部测试。）

本文件检查什么？
    device_model.py 根据工艺参数（栅氧厚度、掺杂浓度、栅长等）算出晶体管和反相器的电学特性。
    这里的每个测试都对应教科书上的一条物理规律，例如“栅氧越薄电流越大”“掺杂越高阈值越高”，
    确保程序算出的趋势和数量级与真实半导体器件一致，不会误导学习者。

常用缩写：Vt 阈值电压；Vdd 电源电压；Vgs 栅源电压；Vds 漏源电压；Idsat 饱和电流；
    tox 栅氧厚度；Na 衬底掺杂浓度；L 栅长；W 栅宽；DIBL 漏致势垒降低；VM 反相器翻转点。
"""
# math 是 Python 自带的数学库；numpy（简写 np）是处理成批数字（数组）的常用第三方库
import math

import numpy as np

# 从项目自己的器件模型里导入要测试的函数和类；括号让一条 import 可以换行写
from fabsim3d.device_model import (ProcessParams, cox, inverter_vout, nmos, pmos,
                                 summarize, transient, vtc)


def test_threshold_signs_and_range():
    """检查：默认工艺下，NMOS 阈值是正的、PMOS 阈值是负的，且都在 0.1~0.8 V 的合理范围内。

    为什么重要：NMOS 要加正电压才导通，PMOS 要加负电压才导通，符号反了整个反相器就不工作了。
    """
    # ProcessParams() 不带参数就是使用全部默认工艺参数
    p = ProcessParams()
    # Python 可以连写比较：0.1 < x < 0.8 表示 x 在 0.1 和 0.8 之间
    assert 0.1 < nmos(p).vt < 0.8
    assert -0.8 < pmos(p).vt < -0.1


def test_cox_matches_textbook():
    """检查：栅氧电容 Cox 的计算结果与教科书数值一致（10 nm 栅氧约 3.45e-7 F/cm²）。"""
    # 10 nm oxide -> 3.45 fF/um^2 = 3.45e-7 F/cm^2
    # math.isclose(a, b, rel_tol=1e-3) 表示 a 和 b 的相对误差不超过 0.1% 就算相等（小数计算总有微小误差）
    assert math.isclose(cox(ProcessParams(tox_nm=10)), 3.453e-7, rel_tol=1e-3)


def test_thinner_oxide_more_current():
    """检查：栅氧从 10 nm 减薄到 5 nm，同样栅压下 NMOS 的饱和电流变大。

    原理：栅氧越薄，栅极对沟道的“遥控”越强，吸来的电子越多。这是实验课②的核心结论。
    """
    a = nmos(ProcessParams(tox_nm=10)).idsat(3.3)
    b = nmos(ProcessParams(tox_nm=5)).idsat(3.3)
    assert b > a


def test_higher_doping_raises_vt():
    """检查：掺杂越浓，阈值电压的绝对值越大（NMOS 的 Vt 更正，PMOS 的 Vt 更负）。"""
    # 5e17 是科学计数法，等于 5×10¹⁷（每立方厘米的杂质原子个数）
    assert nmos(ProcessParams(na_cm3=5e17)).vt > nmos(ProcessParams(na_cm3=1e16)).vt
    assert pmos(ProcessParams(nwell_dose_cm2=1e14)).vt < pmos(ProcessParams(nwell_dose_cm2=5e12)).vt


def test_strong_inversion_square_law():
    """检查：强反型（栅压明显高于阈值）时，电流符合“平方律” Id ≈ β·(Vgs−Vt)²/(2n)。

    lambda_um=0 关掉“沟道长度调制”效应，让结果正好可以和公式比较；允许 5% 误差。
    """
    m = nmos(ProcessParams(lambda_um=0.0))
    # vov 是“过驱动电压”：栅压超过阈值多少
    vov = 1.5
    # ** 是乘方运算，vov ** 2 就是 vov 的平方
    expected = m.beta * vov ** 2 / (2 * m.n)
    assert math.isclose(m.idsat(m.vt + vov), expected, rel_tol=0.05)


def test_subthreshold_slope():
    """检查：阈值以下（亚阈值区）的电流随栅压指数变化，其斜率 SS 与模型给出的值一致。

    SS（亚阈值摆幅）= 电流每变化 10 倍需要多少 mV 栅压，越小说明开关越“干脆”。
    """
    m = nmos(ProcessParams())
    # 一行同时给两个变量赋值：栅压分别比阈值低 0.3 V 和 0.2 V（相差 100 mV）
    i1, i2 = m.ids(m.vt - 0.3, 1.0), m.ids(m.vt - 0.2, 1.0)
    # 100 mV 除以电流变化了几个“10 倍”（log10），就得到每 10 倍需要的 mV 数
    ss = 100.0 / math.log10(i2 / i1)          # mV/dec
    assert math.isclose(ss, m.ss_mv_dec, rel_tol=0.05)


def test_current_zero_at_zero_vds():
    """检查：漏源之间没有电压（Vds = 0）时，即使沟道打开也没有电流。

    原理：就像水龙头开着，但进水口和出水口一样高，水不会流。
    """
    m = nmos(ProcessParams())
    # abs 取绝对值；1e-15 A 实际上就是 0（留一点余量给计算误差）
    assert abs(float(m.ids(2.0, 0.0))) < 1e-15


def test_inverter_rails_and_monotonic():
    """检查：反相器输入 0 V 时输出接近 Vdd，输入 Vdd 时输出接近 0 V，且中间曲线一路下降不回头。

    这是“反相器”最基本的定义：输入低 → 输出高，输入高 → 输出低。
    """
    p = ProcessParams()
    # np.linspace(0, vdd, 101) 生成从 0 到 Vdd 均匀分布的 101 个输入电压
    v = inverter_vout(p, np.linspace(0, p.vdd, 101))
    # v[0] 是第一个输出，v[-1] 是最后一个输出（负数下标表示从末尾倒数）
    assert v[0] > 0.99 * p.vdd and v[-1] < 0.01 * p.vdd
    # np.diff 求相邻两点之差；全部 ≤ 0（容许极小误差）说明曲线单调下降
    assert np.all(np.diff(v) <= 1e-9)


def test_vtc_switching_point_and_margins():
    """检查：电压传输曲线（VTC）的翻转点 VM 在 Vdd 中间附近，噪声容限为正、增益足够大；
    把 PMOS 加宽后翻转点往上移。

    为什么重要：VM 居中、噪声容限为正，数字电路才能可靠地区分 0 和 1。这是实验课③的内容。
    """
    p = ProcessParams()
    r = vtc(p)
    assert 0.35 * p.vdd < r.vm < 0.65 * p.vdd
    # nmh / nml 是高、低电平噪声容限；max_gain 是曲线最陡处的放大倍数
    assert r.nmh > 0 and r.nml > 0 and r.max_gain > 5
    # stronger PMOS pushes VM up
    # （PMOS 更强，把输出往上拉的力气更大，翻转点就上移）
    # p.copy(wp_um=20) 表示复制一份参数，只把 PMOS 宽度改成 20 µm
    assert vtc(p.copy(wp_um=20)).vm > r.vm


def test_transient_delays():
    """检查：反相器翻转的延迟时间在 1 皮秒 ~ 1 纳秒之间，且负载电容加倍时延迟大约加倍。

    原理：延迟 ≈ 负载电容 × 电压 / 电流，电容翻倍要充放的电荷翻倍，所需时间也翻倍。
    """
    p = ProcessParams()
    r = transient(p)
    # tphl：输出从高到低的延迟；tplh：输出从低到高的延迟
    assert 1e-12 < r.tphl < 1e-9 and 1e-12 < r.tplh < 1e-9
    # doubling the load roughly doubles the delay
    r2 = transient(p.copy(cload_ff=100))
    assert 1.6 < r2.tphl / r.tphl < 2.4


def test_summary_runs():
    """检查：汇总函数能正常运行，且开态电流比关态漏电流大 100 万倍以上（开关“开”和“关”分得很清）。"""
    s = summarize(ProcessParams())
    assert s.idsat_n > s.ioff_n * 1e6


# 下面几个测试共用的“工艺特性”集合：
# frozenset 是“不可修改的集合”；"sti" 表示浅沟槽隔离工艺，"sce" 表示打开短沟道效应模型
SCE = frozenset({"sti", "sce"})
# | 在集合之间表示“并集”：在 SCE 的基础上再加上 "ldd"（轻掺杂漏）
SCE_LDD = SCE | {"ldd"}


def test_vt_rolloff_and_dibl_grow_as_l_shrinks():
    """检查短沟道效应的趋势：栅长越短，阈值越低（Vt 滚降），DIBL 越大；
    而栅长很长（5 µm）时，打不打开短沟道模型结果几乎一样。

    为什么重要：这是实验课④“缩小尺寸的代价”要演示的现象，模型必须给出正确方向。
    """
    # 在函数内部 import 也可以，只在用到时才导入
    from fabsim3d.device_model import vt_vs_length
    # vt_vs_length 返回三组数：一串栅长、对应的低漏压阈值、对应的高漏压阈值
    ls, lin, sat = vt_vs_length(ProcessParams(), SCE)
    assert np.all(np.diff(lin) > 0)            # Vt rises towards long channel  （栅长变长，Vt 一路升高）
    # 低漏压与高漏压下阈值之差就是 DIBL（漏极电压把阈值“压低”了多少）
    dibl = lin - sat
    assert np.all(np.diff(dibl) <= 1e-12)      # DIBL shrinks with L  （栅长变长，DIBL 一路变小）
    long_ch = nmos(ProcessParams(l_um=5.0), frozenset({"sce"}))
    assert abs(long_ch.vt - nmos(ProcessParams(l_um=5.0)).vt) < 0.02


def test_ldd_reduces_dibl():
    """检查：加了 LDD（轻掺杂漏）后，0.25 µm 管子的 DIBL 至少降低 30%，阈值也更高。

    原理：LDD 在栅边做了一段浅而淡的“缓坡”，让漏极不那么容易“抢”走栅极对沟道的控制。
    """
    p = ProcessParams(l_um=0.25)
    assert nmos(p, SCE_LDD).dibl < 0.7 * nmos(p, SCE).dibl
    assert nmos(p, SCE_LDD).vt > nmos(p, SCE).vt


def test_velocity_saturation_limits_current():
    """检查：打开短沟道模型后，速度饱和会让电流比理想公式算出来的小。

    原理：电场很强时电子跑不了更快（有“限速”），所以短沟道管子的电流达不到理想平方律的值。
    """
    p = ProcessParams(l_um=0.25, lambda_um=0.0)
    ideal = nmos(p).idsat(p.vdd)
    m = nmos(p, frozenset({"sce"}))
    assert m.idsat(p.vdd) < ideal
    assert m.ec_l > 0


def test_punch_through_device_is_normally_on():
    """Extreme roll-off drives Vt negative: the device must conduct at Vgs = 0.

    检查：栅极极短、栅氧又厚、掺杂又低的极端情况下，阈值会被压成负值，
    这时管子在栅压为 0 时也关不掉（“穿通”），模型必须如实算出有明显电流。
    """
    p = ProcessParams(l_um=0.1, tox_nm=20, na_cm3=1e16)
    m = nmos(p, frozenset({"sce"}))
    assert m.vt_mag < 0
    assert float(m.ids(0.0, p.vdd)) > 1e-5


def test_metal_gate_work_function():
    """A metal with the work function of n+ / p+ poly gives the poly-gate Vt; a
    higher NMOS work function raises Vtn one-for-one.

    检查金属栅（先进工艺用金属代替多晶硅做栅极）的模型：
    1. 金属功函数如果正好等于 n+/p+ 多晶硅的值，算出的阈值应与多晶硅栅完全相同；
    2. NMOS 金属功函数每升高 0.1 eV，阈值也正好升高 0.1 V（一比一）。
    功函数可以理解为“把电子从材料里拿出来要花多少能量”，它直接决定金属栅管子的阈值。
    """
    p = ProcessParams()
    poly_n, poly_p = nmos(p).vt, pmos(p).vt
    # 4.05 eV 是 n+ 多晶硅的功函数；4.05 + 1.12（硅的禁带宽度）是 p+ 多晶硅的功函数
    assert math.isclose(nmos(p.copy(wf_n_ev=4.05)).vt, poly_n, abs_tol=1e-9)
    assert math.isclose(pmos(p.copy(wf_p_ev=4.05 + 1.12)).vt, poly_p, abs_tol=1e-9)
    assert math.isclose(nmos(p.copy(wf_n_ev=4.35)).vt - nmos(p.copy(wf_n_ev=4.25)).vt, 0.1, rel_tol=1e-6)


def test_multigate_electrostatics():
    """More gates and a thinner body shrink the natural length: less DIBL, steeper swing.

    检查多栅结构（FinFET 鳍式三面包围、GAA 四面全包围）的规律：
    栅从越多的方向包住沟道、沟道越薄，栅的控制力越强 → DIBL 更小、亚阈值摆幅更接近理想的 60 mV/dec。
    这正是芯片工艺从平面管走向 FinFET、再走向 GAA 的原因。
    """
    from fabsim3d.device_model import natural_length_cm
    # 一组接近先进工艺的参数：0.9 nm 栅氧、20 nm 栅长、8 nm 沟道厚度、0.8 V 电源
    p = ProcessParams(tox_nm=0.9, na_cm3=1e16, l_um=0.02, tsi_nm=8.0, wf_n_ev=4.45, wf_p_ev=4.77,
                      vdd=0.8, lambda_um=0.002)
    # “自然长度”越短，栅控能力越强；第二个参数是包围沟道的栅面数（4 面 < 3 面 < 2 面）
    assert natural_length_cm(p, 4) < natural_length_cm(p, 3) < natural_length_cm(p, 2)
    fin, gaa = frozenset({"sce", "finfet"}), frozenset({"sce", "gaa"})
    assert nmos(p, gaa).dibl < nmos(p, fin).dibl
    # 鳍更薄（8 nm → 5 nm），DIBL 也更小
    assert nmos(p.copy(tsi_nm=5), fin).dibl < nmos(p, fin).dibl
    # 室温下 SS 的理论极限约 60 mV/dec；GAA 比 FinFET 更接近这个极限
    assert 60 < nmos(p, gaa).ss_mv_dec < nmos(p, fin).ss_mv_dec < 80
    # fully depleted, undoped body: channel doping barely matters, the work function sets Vt
    # （沟道很薄且几乎不掺杂，所以改掺杂对 Vt 影响很小，Vt 主要由金属功函数决定）
    assert abs(nmos(p.copy(na_cm3=1e17), fin).vt - nmos(p, fin).vt) < 0.01
    assert nmos(p.copy(wf_n_ev=4.55), fin).vt > nmos(p, fin).vt + 0.09
    # 用这组参数做出来的反相器，翻转点也应在电源电压的一半附近
    s = summarize(p, fin)
    assert abs(s.vtc.vm - p.vdd / 2) < 0.15
