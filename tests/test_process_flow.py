"""工艺流程与 3D 几何（fabsim3d/process_core.py、geometry.py、flows/）的自动化测试。

什么是“自动化测试”？
    测试是一段用来检查别的代码是否正确的小程序。每个 test_ 开头的函数是一项检查，
    assert（断言）后面写的是“应该成立的条件”，不成立就报错、测试失败。
    本程序有好几套工艺流程、上百个步骤，靠人手动逐步点开 3D 画面检查太慢，
    测试可以在几秒内把每一步都“做”一遍，确认结构没有出错。

怎么运行？
    在项目根目录打开命令行，输入：
        python -m pytest tests/test_process_flow.py
    （只输入 python -m pytest 会运行全部测试。）

本文件检查什么？
    1. 几何小工具：矩形面积、切分方块、表面高度、光线命中（鼠标点选 3D 物体时用）是否算得对；
    2. 每套工艺流程（LOCOS、STI、28 nm HKMG、FinFET、GAA、CFET）的每一步都能运行，文字齐全；
    3. 做完后的芯片结构里该有的层都在、该去掉的临时层（光刻胶、氮化硅等）都去掉了；
    4. 一些关键工艺细节：CMP 磨平后表面是平的、侧墙和 LDD 的位置、自对准、故障模拟等；
    5. 每一代工艺的电学指标（电压、速度、DIBL 等）符合“越新越好”的历史趋势。

背景知识：
    晶圆（Wafer）由很多“层”（layer，如衬底 sub、栅氧、多晶硅 poly、金属 metal）组成，
    每层又由若干“实体”（Solid）构成。Solid 是一个 (x, z) 截面多边形沿 y 方向拉伸出来的柱体。
    矩形 Rect 写成 (x0, x1, y0, y1)，即 x 从 x0 到 x1、y 从 y0 到 y1。长度单位是微米 (µm)。
"""
from fabsim3d.device_model import ProcessParams
from fabsim3d.geometry import Solid, rect_area, rect_complement, split_box, surface_height
import pytest

from fabsim3d.flows import FLOWS
from fabsim3d.process_core import (DOMAIN, Faults, Wafer, build_until, make_ctx, run_phase,
                                   summarize_cached)

# 两套经典平面工艺流程，下面很多测试会用到，先取出来起个短名字
LOCOS = FLOWS["locos"]
STI = FLOWS["sti"]


def test_rect_complement_area():
    """检查：整块区域挖掉几个“洞”后，剩下部分的面积 + 洞的面积 = 原来的总面积。

    rect_complement 用来算“掩膜开口以外的区域”，面积对不上说明几何切分出错了。
    """
    holes = [(2, 4, 2, 4), (10, 12, 1, 3)]
    comp = rect_complement(DOMAIN, holes)
    # sum(... for r in comp) 是“生成器表达式”：把 comp 里每个矩形的面积逐个算出再加起来
    total = sum(rect_area(r) for r in comp) + sum(rect_area(h) for h in holes)
    # 小数运算有极小误差，所以用“差的绝对值小于 1e-9”来判断相等
    assert abs(total - rect_area(DOMAIN)) < 1e-9


def test_split_box_conserves_volume():
    """检查：把一个方块按某个矩形切成“保留”和“去掉”两部分后，两部分面积加起来不变，
    且保留部分正好是那个矩形的面积（3×3 = 9）。刻蚀步骤就是靠这种切分实现的。
    """
    b = Solid.box(0, 10, 0, 8, 0, 1)
    kept, removed = split_box(b, [(2, 5, 1, 4)])
    # kept + removed 把两个列表连起来；footprint 是实体在俯视图上占的矩形
    area = sum(rect_area(s.footprint) for s in kept + removed)
    assert abs(area - 80) < 1e-9 and abs(sum(rect_area(s.footprint) for s in kept) - 9) < 1e-9


def test_surface_height_prism():
    """检查：三角形截面的实体，在斜坡中间某点算出的表面高度正确（新薄膜会沉积在这个高度上）。"""
    # 三角形顶点 (0,0)、(4,0)、(2,2)，沿 y 从 0 到 1；在 x=1 处斜面高度应为 1
    s = Solid([(0, 0), (4, 0), (2, 2)], 0, 1)
    assert abs(surface_height([s], 1, 0.5) - 1) < 1e-9


# parametrize 装饰器：对 FLOWS 里的每一套工艺流程各运行一次下面的测试
@pytest.mark.parametrize("flow", list(FLOWS.values()), ids=list(FLOWS))
def test_every_step_builds_and_has_text(flow):
    """检查：每套流程里，步骤名字不重复；每一步都有中英文标题和说明；
    参数显示函数能返回文字；小测验的正确答案编号有效；每个动画阶段都能运行不报错。
    """
    ctx = make_ctx(ProcessParams(), flow)
    w = Wafer()
    # {...} 花括号生成一个“集合”，会自动去重；集合大小等于步骤数说明 key 没有重复
    assert len({s.key for s in flow.steps}) == len(flow.steps)
    for st in flow.steps:
        assert st.title[0] and st.title[1] and st.desc[0] and st.desc[1]
        # 每个参数条目是 (中文名, 英文名, 计算显示文字的函数)
        for zh, en, fn in st.params:
            assert isinstance(fn(ctx), str)
        # 有小测验的步骤：答案编号必须在选项范围内
        if st.quiz:
            assert 0 <= st.quiz.answer < len(st.quiz.options)
        # 依次执行这一步的每个动画阶段，真正地在晶圆上“做”出结构
        for ph in st.phases:
            run_phase(w, ctx, ph)


# “列表推导式”：从所有流程里挑出平面工艺（LOCOS、STI）和先进工艺（其余的）
PLANAR = [f for f in FLOWS.values() if f.key in ("locos", "sti")]
ADVANCED = [f for f in FLOWS.values() if f.key not in ("locos", "sti")]


@pytest.mark.parametrize("flow", PLANAR, ids=[f.key for f in PLANAR])
def test_final_structure(flow):
    """检查：平面工艺做完后，该有的结构都在（衬底、N 阱、隔离、两个栅、源漏、绝缘层、金属），
    临时用的层（光刻胶、氮化硅、垫氧等）都已去除；NMOS 栅是 N 型多晶硅，PMOS 栅是 P 型多晶硅。
    """
    # 一直做到最后一步（编号从 0 开始，所以最后一步是 len - 1）
    w = build_until(make_ctx(ProcessParams(), flow), len(flow.steps) - 1)
    # 条件表达式：LOCOS 流程的隔离层叫 fox（场氧），STI 流程叫 sti（浅沟槽）
    iso = "fox" if flow.key == "locos" else "sti"
    for name in ("sub", "nwell", iso, "gate_n", "gate_p", "nplus", "pplus", "ild", "metal"):
        # assert 条件, name —— 逗号后面是失败时显示的信息，方便知道缺了哪一层
        assert w.has(name), name
    for name in ("resist", "resist_exp", "nitride", "padox", "poly", "nimp"):
        assert not w.has(name), name
    assert w.layers["gate_n"].material == "poly_n"
    assert w.layers["gate_p"].material == "poly_p"


def test_gate_length_changes_layout():
    """检查：把栅长 L 从 0.25 µm 改到 3 µm，版图里的栅宽度（gl）跟着变大，3D 模型才会跟着变。"""
    a = make_ctx(ProcessParams(l_um=0.25)).lay["gl"]
    b = make_ctx(ProcessParams(l_um=3.0)).lay["gl"]
    assert b > a


def _zmax(w, layer):
    """辅助函数：求晶圆某一层所有实体中最高点的 z 坐标（即这一层的顶面高度）。"""
    return max(s.zmax for s in w.layers[layer].solids)


def test_sti_trench_cmp_and_planarity():
    """检查 STI 浅沟槽隔离的几个关键阶段：
    刻蚀后硅里确实挖出了沟；CMP（化学机械抛光）磨到氮化硅就停；去掉氮化硅后台阶很小；
    之后沉积的多晶硅落在一个平整的表面上。STI 相比 LOCOS 的最大优点就是“平”。
    """
    ctx = make_ctx(ProcessParams(), STI)
    # step_index("sti_etch") 找出名为 sti_etch 的步骤是第几步，然后做到那一步为止
    trench = build_until(ctx, STI.step_index("sti_etch"))
    assert min(s.zmax for s in trench.layers["sub"].solids) < -0.3      # trenches cut into Si（沟挖进了硅里）
    cmp_done = build_until(ctx, STI.step_index("sti_cmp"))
    assert abs(_zmax(cmp_done, "sti") - _zmax(cmp_done, "nitride")) < 1e-9   # stopped on nitride（停在氮化硅上）
    stripped = build_until(ctx, STI.step_index("sti_strip"))
    assert 0 < _zmax(stripped, "sti") < 0.1                              # small step height（台阶很小）
    poly = build_until(ctx, STI.step_index("poly_dep")).layers["poly"].solids
    # 把每块多晶硅的顶面高度四舍五入到 6 位小数放进集合，只剩 1 个值说明高度全都一样
    assert len({round(s.zmax, 6) for s in poly}) == 1                   # poly lies on a flat surface


def test_ild_cmp_flat():
    """检查：层间绝缘层（ILD）经过 CMP 后，顶面全部在同一高度 1.3 µm，即完全磨平。"""
    ctx = make_ctx(ProcessParams(), STI)
    w = build_until(ctx, STI.step_index("ild_cmp"))
    assert {round(s.zmax, 6) for s in w.layers["ild"].solids} == {1.3}


def test_isolation_narrow_width_effect():
    """检查“窄沟道效应”：管子很窄（0.5 µm）时，LOCOS 隔离让 Vt 升高，STI 隔离反而让 Vt 降低。

    原理：LOCOS 的“鸟嘴”侵入沟道边缘，相当于多了一些要“推开”的电荷 → Vt 上升；
    STI 的尖角让电场集中，边缘更早导通 → Vt 下降（叫“反窄沟道效应”）。
    """
    p = ProcessParams(wn_um=0.5)
    # 不指定隔离方式时的“理想”阈值，作为比较基准
    vt_ideal = summarize_cached(p).vtn
    assert summarize_cached(p, frozenset({"locos"})).vtn > vt_ideal     # LOCOS: Vt up
    assert summarize_cached(p, frozenset({"sti"})).vtn < vt_ideal       # STI: inverse NWE


def test_dopant_and_thermal_records():
    """检查：做完 STI 流程后，晶圆记录下的离子注入顺序、元素种类和类型都正确；
    用户设定的 N 阱剂量被如实记下；高温步骤至少 3 次且都高于 800 °C。

    这些记录供界面显示“掺杂历史”和“热预算”，记错了会误导学习者。
    """
    w = build_until(make_ctx(ProcessParams(nwell_dose_cm2=5e13), STI), len(STI.steps) - 1)
    # 每次注入记成 (步骤名, 元素, 类型)：P 磷、As 砷是 N 型杂质，BF2（含硼）是 P 型杂质
    species = [(d.step, d.species, d.polarity) for d in w.dopants]
    assert species == [("nwell_implant_he", "P", "n"), ("nldd", "P", "n"), ("pldd", "BF2", "p"),
                       ("nplus_sp", "As", "n"), ("pplus_sp", "BF2", "p")]
    assert w.dopants[0].dose_cm2 == 5e13 and w.dopants[0].step == "nwell_implant_he"
    # all(...) 只有当每一个元素都满足条件时才为 True
    assert len(w.thermal) >= 3 and all(t.temp_c > 800 for t in w.thermal)


def test_fault_misalignment_and_skip():
    """检查“故障模拟”功能：
    1. 故意让栅极（POLY 掩膜）对准偏移 0.6 µm，栅极就真的偏了 0.6 µm；
    2. 源漏因为是“自对准”的（以栅为模板注入），也会跟着栅一起偏 0.6 µm；
    3. 故意跳过 N+ 注入步骤，最终结构里就没有 N+ 区。
    """
    p = ProcessParams()
    ok = build_until(make_ctx(p, LOCOS), len(LOCOS.steps) - 1)
    bad = build_until(make_ctx(p, LOCOS, Faults(misalign={"POLY": (0.6, 0.0)})), len(LOCOS.steps) - 1)
    # lambda 是“匿名小函数”的写法：gx(w) 返回晶圆 w 上 NMOS 栅的最左边 x 坐标
    gx = lambda w: min(s.xmin for s in w.layers["gate_n"].solids)
    assert abs(gx(bad) - gx(ok) - 0.6) < 1e-9
    # self-aligned S/D follows the shifted gate
    # （nx 取左边那只管子 N+ 区的最右端，x < 6 用来只看左半边）
    nx = lambda w: max(s.xmax for s in w.layers["nplus"].solids if s.xmax < 6)
    assert abs(nx(bad) - nx(ok) - 0.6) < 1e-9
    skipped = build_until(make_ctx(p, LOCOS, Faults(skip=frozenset({"nplus"}))), len(LOCOS.steps) - 1)
    assert not skipped.has("nplus")


def test_spacers_and_ldd_structure():
    """检查侧墙（spacer）和 LDD 结构：
    沉积后只有一层薄膜还没成形；刻蚀后薄膜消失、留下 4 块侧墙（两个栅各左右两块）；
    每块侧墙的截面多边形是逆时针排列的（面积为正）；
    深 N+ 源漏离栅边退后约一个侧墙宽度，而浅 LDD 伸到栅下面；LDD 比 N+ 浅。
    """
    from fabsim3d.process_core import SPACER_W, gate_span
    ctx = make_ctx(ProcessParams(), STI)
    film = build_until(ctx, STI.step_index("spacer_dep"))
    assert film.has("spacer_film") and not film.has("spacer")
    w = build_until(ctx, len(STI.steps) - 1)
    assert not w.has("spacer_film") and len(w.layers["spacer"].solids) == 4
    for s in w.layers["spacer"].solids:                       # convex, CCW cross-sections
        pts = s.poly
        # “鞋带公式”求多边形面积：顶点逆时针排列时结果为正，顺时针为负
        # % len(pts) 是取余数，让最后一个点和第一个点首尾相接
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts))) / 2
        assert area > 0
    # g0 是 NMOS 栅左边缘的 x 坐标
    g0 = gate_span(ctx, "gn")[0]
    n_edge = max(s.xmax for s in w.layers["nplus"].solids if s.xmax < g0 + 0.5)
    ldd_edge = max(s.xmax for s in w.layers["nldd"].solids if s.xmax < g0 + 0.5)
    # deep n+ stays back by about a spacer width; LDD reaches under the gate edge
    assert g0 - SPACER_W < n_edge < g0
    assert ldd_edge > g0
    # LDD 的底面（zmin）比 N+ 的底面高，即 LDD 更浅
    assert max(s.zmin for s in w.layers["nldd"].solids) > min(s.zmin for s in w.layers["nplus"].solids)


def test_flow_default_params_are_era_typical():
    """检查：两套平面流程的默认参数符合各自年代的典型值：
    老的 LOCOS 工艺电源电压更高；两者阈值都在 0.3~0.6 V；新一代 STI 工艺速度更快。
    """
    lo = summarize_cached(LOCOS.default_params(), LOCOS.features)
    hi = summarize_cached(STI.default_params(), STI.features)
    assert LOCOS.default_params().vdd > STI.default_params().vdd
    for s in (lo, hi):
        assert 0.3 < s.vtn < 0.6 and -0.6 < s.vtp < -0.3
    assert hi.tran.tphl < lo.tran.tphl          # newer generation is faster（延迟更短）


@pytest.mark.parametrize("flow", ADVANCED, ids=[f.key for f in ADVANCED])
def test_advanced_final_structure(flow):
    """Gate-last flows end with a HKMG stack, plugs and copper; no dummy gate is left.

    检查先进工艺（后栅工艺）做完后：有高 k 介质 + 金属栅、钨塞、铜线等；
    “替身栅”（多晶硅 dummy gate）、SiGe 牺牲层、镍等临时材料都已去掉；
    铜 CMP 后表面平整；金属栅 CMP 停在 ILD0 绝缘层顶面。
    """
    w = build_until(make_ctx(flow.default_params(), flow), len(flow.steps) - 1)
    for name in ("sti", "spacer", "hk", "gfill", "plug", "cu", "ild0", "ild"):
        assert w.has(name), name
    for name in ("resist", "resist_exp", "nitride", "padox", "poly", "gate", "gate_n", "gate_p", "sige", "ni"):
        assert not w.has(name), name
    assert {round(s.zmax, 6) for s in w.layers["cu"].solids} == {1.75}       # copper CMP is flat
    gate_top = max(s.zmax for s in w.layers["gfill"].solids)
    assert abs(gate_top - max(s.zmax for s in w.layers["ild0"].solids)) < 1e-9   # metal CMP stops on ILD0


def test_finfet_fins_and_wrapped_gate():
    """检查 FinFET（鳍式晶体管）：
    露鳍步骤后，高出隔离氧化层的硅正好是所有的鳍（NMOS、PMOS 各一组），鳍顶在 z = 0；
    做完高 k 金属栅后，每个栅下每个鳍的左右两侧壁都被高 k 介质包住（栅从三面包住沟道）。
    """
    from fabsim3d.flows import finfet
    f = FLOWS["finfet"]
    ctx = make_ctx(f.default_params(), f)
    w = build_until(ctx, f.step_index("fin_reveal"))
    sti_top = max(s.zmax for s in w.layers["sti"].solids)
    # 高出 STI 顶面的衬底部分就是露出来的鳍
    fin_tops = [s.zmax for s in w.layers["sub"].solids if s.zmax > sti_top]
    # FIN_YC 是鳍的 y 位置列表；乘 2 是因为 NMOS 和 PMOS 各有一组鳍
    assert len(fin_tops) == 2 * len(finfet.FIN_YC) and all(abs(z) < 1e-9 for z in fin_tops)
    w = build_until(ctx, f.step_index("hkmg"))
    # high-k lines both sidewalls of every fin under each gate
    # （侧壁上的高 k 介质很薄，所以用 y 方向厚度 < 0.05 来挑出它们）
    walls = [s for s in w.layers["hk"].solids if abs(s.zmin - finfet.FIN_REVEAL) < 1e-9 and s.y1 - s.y0 < 0.05]
    # 2 个栅 × 每鳍 2 面侧壁 × 鳍数
    assert len(walls) == 2 * 2 * len(finfet.FIN_YC)


def test_gaa_sheets_released_and_wrapped():
    """检查 GAA（全环绕栅）：
    做内侧墙之前，SiGe 牺牲层和内侧墙都在；做完后 SiGe 被全部掏空，留下纳米片；
    原来每个 SiGe 夹层的位置（在栅下面）现在都填上了金属栅，即栅从四面包住每片纳米片。
    """
    from fabsim3d.flows import gaa
    f = FLOWS["gaa"]
    ctx = make_ctx(f.default_params(), f)
    before = build_until(ctx, f.step_index("inner_spacer"))
    assert before.has("sige") and before.has("inner")
    w = build_until(ctx, len(f.steps) - 1)
    assert not w.has("sige") and len(w.layers["sheet"].solids) == 2 * len(gaa.SHEETS)
    # g 是 NMOS 栅的 x 范围 (左, 右)
    g = ctx.lay["gn"]
    for z0, z1 in gaa.SIGE:            # every former SiGe gap under the gate now holds gate metal
        # zc 是这个夹层的中间高度；any(...) 只要有一块金属覆盖这里就为 True
        zc = (z0 + z1) / 2
        assert any(s.xmin <= g[0] + 1e-9 and s.xmax >= g[1] - 1e-9 and s.zmin <= zc <= s.zmax
                   for s in w.layers["wfn"].solids), (z0, z1)


def test_cfet_stack_and_backside():
    """检查 CFET（互补堆叠晶体管，PMOS 叠在 NMOS 上面）：
    衬底被磨掉、背面有供电结构；中间隔层是绝缘体；NMOS 纳米片在隔层下、PMOS 在隔层上；
    输出端的接触塞一直通到底层的漏极；下层的功函数金属是 N 型的（不超过隔层）。
    """
    from fabsim3d.flows import cfet
    f = FLOWS["cfet"]
    ctx = make_ctx(f.default_params(), f)
    w = build_until(ctx, len(f.steps) - 1)
    assert not w.has("sub") and w.has("bsd") and w.has("bsc") and w.has("bsm")   # backside power
    assert w.layers["mdi"].material == "mdi_ox"
    n_top = max(s.zmax for s in w.layers["sheet_n"].solids)
    p_bot = min(s.zmin for s in w.layers["sheet_p"].solids)
    # cfet.MDI 是中间隔层的 (底, 顶) 高度
    assert n_top < cfet.MDI[0] < cfet.MDI[1] < p_bot                          # PMOS above NMOS
    out = ctx.lay["contacts"]["out"]
    # 找出位于输出触点 x 范围内的接触塞的最低点
    deep = min(s.zmin for s in w.layers["plug"].solids if s.xmin >= out[0] - 1e-9 and s.xmax <= out[1] + 1e-9)
    assert deep < min(s.zmin for s in w.layers["psd"].solids)                 # Vout reaches the bottom drain
    # bottom WF metal is n-type, the top one p-type
    assert max(s.zmax for s in w.layers["wfn"].solids) <= cfet.MDI[0] + 1e-9


def test_generations_scale():
    """Each generation runs at a lower VDD; multi-gate devices beat planar 28 nm on DIBL and swing.

    检查各代工艺（按 FLOWS 中的先后顺序）符合历史趋势：
    电源电压一代比一代低；每代的阈值和噪声容限都在合理范围；
    FinFET 比平面 28 nm HKMG、GAA 比 FinFET 的 DIBL 和亚阈值摆幅更小；新一代速度更快。
    """
    keys = list(FLOWS)
    vdds = [FLOWS[k].default_params().vdd for k in keys]
    # sorted(..., reverse=True) 是从大到小排序；与原列表相同说明电压逐代递减
    assert vdds == sorted(vdds, reverse=True)
    # “字典推导式”：为每代工艺算出电学汇总，存成 {流程名: 汇总结果}
    s = {k: summarize_cached(FLOWS[k].default_params(), FLOWS[k].features) for k in keys}
    for k in keys:
        assert 0.2 < s[k].vtn < 0.6 and -0.6 < s[k].vtp < -0.2, k
        assert s[k].vtc.nmh > 0.2 * FLOWS[k].default_params().vdd, k
    assert s["finfet"].dibl_n < s["hkmg"].dibl_n and s["gaa"].dibl_n < s["finfet"].dibl_n
    assert s["finfet"].ss_n < s["hkmg"].ss_n and s["gaa"].ss_n < s["finfet"].ss_n
    assert s["hkmg"].tran.tphl < s["sti"].tran.tphl and s["finfet"].tran.tphl < s["hkmg"].tran.tphl


def test_ray_enter_prism():
    """检查“光线命中”计算：从某点沿某方向射出一条线，算出它在多远处进入实体（打不中就返回 None）。

    3D 界面里用鼠标点选某一层材料时，就是靠这个计算判断点中了谁。
    y_min 表示剖面切掉了 y < y_min 的部分，光线只能命中剩下的部分。
    """
    from fabsim3d.geometry import Solid
    b = Solid.box(0, 2, 0, 4, -1, 0)
    # pytest.approx(10) 表示“约等于 10”，允许微小的计算误差
    assert b.ray_enter((1, 2, 10), (0, 0, -1)) == pytest.approx(10)       # from above（从上方往下打）
    assert b.ray_enter((5, 2, 10), (0, 0, -1)) is None                    # beside it（从旁边打，打不中）
    assert b.ray_enter((1, -5, -0.5), (0, 1, 0)) == pytest.approx(5)      # through the front face（从正面打入）
    assert b.ray_enter((1, -5, -0.5), (0, 1, 0), y_min=3) == pytest.approx(8)   # cut away to y=3
    assert b.ray_enter((1, -5, -0.5), (0, 1, 0), y_min=4) is None
    tri = Solid([(0, 0), (2, 0), (1, 2)], 0, 1)                           # clockwise works too
    assert tri.ray_enter((1.5, 0.5, 5), (0, 0, -1)) == pytest.approx(4)
    # poly[::-1] 把顶点顺序倒过来（顺时针变逆时针），结果应该一样
    assert Solid(tri.poly[::-1], 0, 1).ray_enter((1.5, 0.5, 5), (0, 0, -1)) == pytest.approx(4)


def test_every_material_explains_its_role():
    """检查：每种材料都有中英文“作用说明”，点选 3D 中的材料时界面才能显示它是干什么用的。"""
    from fabsim3d.materials import MATERIALS
    for m in MATERIALS.values():
        assert m.role_zh and m.role_en, m.key
