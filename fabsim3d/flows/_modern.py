"""Building blocks shared by the advanced-node flows (28 nm HKMG, FinFET, GAA, CFET).

All of them use a replacement-metal-gate ("gate-last") module, a planarised
ILD0, self-aligned contacts with a W/Co plug and a single-damascene copper
metal 1.  Each factory returns a Step; gate_top is the height of the dummy
gate (and therefore of the ILD0 after CMP).

【中文说明：这个文件是做什么的】
28 nm 高 k 金属栅 (hkmg.py)、FinFET (finfet.py)、环栅 GAA (gaa.py)、CFET (cfet.py) 这几代先进工艺，
后半段的步骤几乎一样：
  1. ILD0：用氧化物把“伪栅” (先放一根假的多晶硅栅占位) 之间填满并磨平，露出伪栅顶；
  2. 去伪栅：把假栅掏空，留下一条“栅槽”；
  3. HKMG：在槽里放入高 k 介质 (HfO2) 和金属栅——这就是“后栅工艺” (gate-last / 替换金属栅 RMG)；
  4. 接触孔 + 钨/钴塞；
  5. 铜导线 (大马士革镶嵌工艺)；
  6. 完成。
为了不在四个文件里重复写四遍，这里把它们写成“工厂函数”：调用一次就生产出一个 Step 对象。
各工艺调用时可以传入自己的额外部分 (例如 FinFET 要让金属栅包住鳍的两侧)。
文件开头还有几个几何小工具 (side_slabs、channel_rects)。

坐标约定：x 左右，y 伸进屏幕 (剖面沿 y 移动)，z 向上，硅表面附近 z ≈ 0，竖直方向被夸张放大。
参数 gate_top 是伪栅顶面的 z 高度，也就是 ILD0 磨平后的高度。
Step / Phase / quiz 各参数的含义见 locos.py 中 STEPS 上方的说明。
"""
# 推迟解析类型提示，技术细节，可忽略。
from __future__ import annotations

# 类型提示用的名字，只起说明作用：
#   Callable = “可以调用的东西” (函数)；List = 列表；Optional[X] = X 或者 None (空)；
#   Sequence = 任何有顺序的一串东西；Tuple = 固定个数的一组值，例如 (y0, y1)。
from typing import Callable, List, Optional, Sequence, Tuple

# Rect = 矩形 (x0, x1, y0, y1)；Solid = 3D 实体；rect_complement = 区域去掉某些矩形后剩下的部分。
from ..geometry import Rect, Solid, rect_complement
# 工艺引擎中的数据结构和动作函数 (淀积 deposit、刻蚀 pattern、抛光 cmp、去层 strip 等)。
from ..process_core import (DOMAIN, Phase, Step, add_solids, anneal, cmp, contacts, deposit, gates,
                            glow, litho, metal, pattern, quiz, strip, summarize_cached, vt_text)

# 两个高度常数 (显示单位，z 方向)：
ILD1_TOP = 1.3          # top of the contact-level dielectric (= bottom of metal 1)
#                         接触孔那一层绝缘介质 (ILD1) 的顶面，也就是第一层金属 (M1) 的底面
M1_TOP = 1.75           # copper metal-1 thickness 0.45 (display units)
#                         铜 M1 顶面高度：1.75 - 1.3 = 0.45 就是铜线的厚度


def eot_text(c) -> str:
    """EOT shown in the parameter table.

    返回“等效氧化层厚度” (EOT) 的显示文字，例如 "0.90 nm"。
    EOT 的意思是：这层高 k 介质的电容，相当于多厚的 SiO2。用户在“参数”页调的 tox 在先进工艺里就代表 EOT。
    “-> str” 是类型提示：表示这个函数返回一段文字。
    """
    return f"{c.p.tox_nm:.2f} nm"


def gate_rects_n(c) -> List[Rect]:
    """NMOS gate footprints (从上往下看，NMOS 栅极占据的矩形)。用于指定 N 型功函数金属放在哪里。"""
    return c.lay["gates_n"]


def gate_rects_p(c) -> List[Rect]:
    """PMOS gate footprints (PMOS 栅极占据的矩形)。用于指定 P 型功函数金属放在哪里。"""
    return c.lay["gates_p"]


# --------------------------------------------------------------------------
# geometry helpers
# 几何小工具
# --------------------------------------------------------------------------

def side_slabs(rects: Sequence[Rect], bands: Sequence[Tuple[float, float]], z0: float, z1: float,
               offset: float, t: float) -> List[Solid]:
    """Thin vertical films on the y-facing sidewalls of fins / nanosheet stacks,
    inside the gate footprint (x-range of each rect): how a film wraps the channel.

    在“鳍” (FinFET) 或“纳米片堆叠” (GAA/CFET) 的两个侧面上，造出竖直的薄膜片。
    为什么需要：先进晶体管的沟道是竖起来的鳍/片，栅介质和金属栅要像“U 形”一样包住它的侧面，
    而简单的“整片淀积”只能画出顶面那一层，所以侧面的部分用这个函数单独补上。
    参数：
      rects  栅极的矩形 (只在栅覆盖的 x 范围内才包住沟道)；
      bands  每条鳍/每个堆叠在 y 方向的范围 (y0, y1)——鳍沿 x 方向延伸，两个侧面朝向 ±y；
      z0,z1  薄膜的底和顶高度；
      offset 薄膜离鳍侧面的距离 (前面已经包了几层膜时，后包的膜要往外让开)；
      t      薄膜厚度。
    """
    out = []
    for r in rects:
        for y0, y1 in bands:
            # r[2]、r[3] 是栅矩形的 y 起止。鳍和栅在 y 方向不重叠就跳过 (continue = 直接处理下一个)。
            if y1 <= r[2] or y0 >= r[3]:
                continue
            # 两个侧面：鳍前方 (y 小的一侧) 一片、后方 (y 大的一侧) 一片，各厚 t，离鳍 offset。
            for a, b in ((y0 - offset - t, y0 - offset), (y1 + offset, y1 + offset + t)):
                s = Solid.box(r[0], r[1], a, b, z0, z1)
                # 生长动画从底部 z0 往上长。
                s.anchor = z0
                out.append(s)
    return out


def channel_rects(c, key: str = None) -> List[Rect]:
    """Gate footprints restricted to the channel part (no contact pad).

    只取栅极中真正盖在沟道上的那部分矩形，去掉场区上用于接触孔的小“接触垫”。
    判断方法：y 方向长度大于 2.0 的是沟道部分 (接触垫很短)。
    key 为 None (不指定) 时返回 NMOS 和 PMOS 两种；指定 "n" 或 "p" 时只返回一种。
    “key: str = None” 里的 “= None” 是默认值：调用时不传这个参数，它就是 None。
    """
    # “A if 条件 else B” 是一行写完的条件表达式：条件成立取 A，否则取 B。
    rs = c.lay["gates_n"] + c.lay["gates_p"] if key is None else c.lay["gates_" + key]
    # 列表推导式 + 条件：只留下满足 “y1 - y0 > 2.0” 的矩形。
    return [r for r in rs if r[3] - r[2] > 2.0]


# --------------------------------------------------------------------------
# steps
# 步骤工厂函数：每个函数“生产”并返回一个 Step 对象
# --------------------------------------------------------------------------

def ild0_step(gate_top: float, key: str = "ild0") -> Step:
    """ILD0 deposition + CMP that stops on top of the dummy gates.

    ILD0 淀积 + CMP。
    物理上：用可流动的氧化物把各个伪栅之间的缝隙填满，再用化学机械抛光 (CMP) 磨平，正好停在伪栅顶面。
    为什么：后栅工艺要从顶上把伪栅挖掉换成金属栅，所以伪栅必须四周被氧化物包住、只露出顶面。
    3D 模型里：先把 "ild0" 层填到 gate_top + 0.3 的高度，再用 cmp 削到 gate_top。
    参数 gate_top 由各工艺传入 (不同工艺伪栅高度不同)；key 是步骤名，一般用默认值 "ild0"。
    """
    return Step(key, ("ILD0 淀积 + CMP 露出伪栅", "ILD0 deposition + CMP to the dummy gates"),
                ("用可流动 CVD (FCVD) 氧化物把栅与栅之间的缝隙填满，再用 CMP 磨平，正好停在伪栅多晶硅的顶上 "
                 "(又叫 POP CMP)。现在伪栅四周都被氧化物和侧墙包住，只有顶面露出来，为“换栅”做准备。",
                 "Flowable CVD oxide fills the gaps between gates and CMP planarises it, stopping exactly on "
                 "top of the dummy poly ('poly open polish'). The dummy gates are now boxed in by oxide and "
                 "spacers with only their tops exposed, ready to be replaced."),
                [("材料", "Material", lambda c: "FCVD SiO2 (+ SiN 刻蚀停止层 / CESL)"),
                 ("CMP 停止", "CMP stop", lambda c: "伪栅顶部 / dummy-gate top")],
                [Phase("可流动氧化物填缝", "Flowable oxide gap-fill", 1.6,
                       [deposit("ild0", "ild_ox", top=gate_top + 0.3, particles=("depo", (0.85, 0.92, 1.0, 1)))]),
                 Phase("CMP 停在伪栅顶部", "CMP stops on the dummy gates", 2.0, [cmp(["ild0"], gate_top)])],
                quiz("ILD0 CMP 为什么要正好停在伪栅顶上？", "Why must the ILD0 CMP stop exactly on the dummy gates?",
                     [("露出伪栅顶面，之后才能把它刻掉换成金属栅", "To expose the dummy gate so it can be etched out and replaced"),
                      ("为了让晶圆更薄", "To thin the wafer"), ("为了掺杂", "For doping"), ("去除侧墙", "To remove the spacers")], 0,
                     "后栅工艺要从顶上把伪栅掏空，所以 CMP 必须把它的顶面露出来，又不能磨掉太多栅高。",
                     "Gate-last hollows the dummy gate out from the top, so the CMP must open it without losing gate height."))


def rmg_remove_step(gate_layers: Sequence[str], extra: Optional[List] = None,
                    title=("去除伪栅 (后栅工艺)", "Dummy-gate removal (gate-last)"), desc=None,
                    extra_phase=None, key: str = "rmg_remove") -> Step:
    """Dummy-gate removal (gate-last / replacement metal gate).

    去除伪栅。
    物理上：用刻蚀把伪栅多晶硅和它下面的牺牲氧化层掏掉，在两侧侧墙之间留下一条空的“栅槽”。
    为什么要先放假栅、再换真栅：源漏激活要约 1000°C 的高温，而高 k 介质和金属栅受不了这么高的温度
      (功函数会漂移、HfO2 会结晶)。所以高温步骤都在假栅还在时做完，真栅最后才放进去。
    参数：
      gate_layers  要去掉的伪栅层名字列表 (不同工艺伪栅的层名不同)；
      extra        (目前未在函数体中使用，保留给调用方的接口)；
      title/desc   可覆盖默认的标题/说明；desc 为 None 时用下面写好的默认说明；
      extra_phase  可选的额外阶段，例如 GAA 在这里还要把纳米片之间的牺牲 SiGe 层刻掉 (“沟道释放”)。
    3D 模型里：
      第 1 阶段 strip 把每个伪栅层整层去掉；
      第 2 阶段 pattern("gox", ...) 把栅区里的伪栅氧化层刻掉：保留区域是“整个区域减去栅极矩形”，
        所以只有栅下面那部分被去掉。
    """
    # 列表推导式：对每个伪栅层名生成一个 strip 动作。
    phases = [Phase("刻蚀去除伪栅多晶硅", "Etch out the dummy poly", 1.8,
                    [strip(g) for g in gate_layers]),
              Phase("HF 去除伪栅氧化层", "HF removes the dummy oxide", 1.0,
                    [pattern("gox", lambda c: rect_complement(DOMAIN, gates(c)), particles=False)])]
    # 如果调用方提供了额外阶段，就追加到末尾。
    if extra_phase:
        phases.append(extra_phase)
    # “desc or (...)”：desc 有值就用 desc，是 None (空) 就用后面括号里的默认说明。
    return Step(key, title,
                desc or ("湿法/干法刻蚀把伪栅多晶硅和下面的牺牲氧化层掏掉，在侧墙之间留下一条“栅槽”。"
                         "伪栅已经完成了它的使命：源漏的高温激活退火 (约 1000°C) 都在它还在的时候做完了，"
                         "真正怕高温的高 k 介质和金属栅之后才放进来。",
                         "Wet/dry etching hollows out the dummy poly and the sacrificial oxide under it, "
                         "leaving a gate trench between the spacers. The dummy has done its job: the ~1000 °C "
                         "S/D activation anneals happened while it was there, so the heat-sensitive high-k "
                         "and metal gate go in only now."),
                [("刻蚀", "Etch", lambda c: "NH4OH / TMAH 湿法 + 干法"),
                 ("选择比", "Selectivity", lambda c: "poly : SiO2 : SiN > 100 : 1 : 1")],
                phases,
                quiz("为什么要“先做假栅、后换真栅” (gate-last)？", "Why build a dummy gate first and replace it later (gate-last)?",
                     [("高 k/金属栅受不了源漏激活的高温", "High-k / metal gates can't survive the S/D activation heat"),
                      ("多晶硅更便宜", "Poly is cheaper"), ("为了少用一次掩膜", "To save a mask"),
                      ("金属栅不能刻蚀", "Metal gates can't be etched")], 0,
                     "高温会让金属功函数漂移、让 HfO2 结晶并长出界面层，Vt 失控；后栅工艺避开了这个热预算。",
                     "Heat shifts the metal work function and crystallises HfO2 / grows the interfacial layer; "
                     "gate-last keeps them out of that thermal budget."))


def hkmg_step(gate_top: float, extra_hk=None, extra_wfn=None, extra_wfp=None, key: str = "hkmg",
              desc=None, extra_params=None, wfn_region=gate_rects_n, wfp_region=gate_rects_p) -> Step:
    """IL + HfO2, dual work-function metals, W fill + CMP.  extra_* (callables
    ctx -> solids) add the parts that wrap fins or fill the gaps between sheets;
    wf*_region say where each work-function metal covers the top of the channel.

    高 k 介质 + 金属栅 (HKMG)。
    物理上，在空栅槽里依次放入：
      1. 极薄的界面 SiO2 + 原子层淀积 (ALD) 的 HfO2 (高 k 介质，k≈20，SiO2 只有 3.9)；
      2. NMOS 栅里放 N 型功函数金属 (TiAl)；
      3. PMOS 栅里放 P 型功函数金属 (TiN)；
      4. 用钨把槽填满；
      5. CMP 磨掉槽外多余的金属，只留槽里的。
    为什么：
      * 栅介质要非常薄 (电容才大、栅才控制得住沟道)，但 SiO2 薄到 1 nm 时电子会直接“隧穿”过去漏电。
        换成 k 大的 HfO2，可以做得物理上更厚 (不漏电)，电容却一样大。
      * 金属的“功函数”决定阈值电压 Vt：NMOS 和 PMOS 需要不同的 Vt，所以要两种不同的金属。
    参数：
      gate_top          栅顶高度 (CMP 磨到这里)；
      extra_hk / extra_wfn / extra_wfp  可选函数 (输入上下文 c，返回实体列表)，
                        用来补上包住鳍侧面或填进纳米片缝隙的那部分 (平面晶体管不需要)；
      wfn_region / wfp_region  两种功函数金属在顶面上覆盖的区域，默认就是各自的栅矩形。
                        注意默认值是“函数本身” (gate_rects_n)，不是调用结果——之后需要时才调用。
      extra_params      追加到参数表末尾的行 (各工艺可以显示自己特有的参数)。
    3D 模型里：add_solids(..., mode="fade") 把额外实体以“淡入”方式加到同一层。
    """
    # 每种膜先准备“顶面那层”的动作，有额外部分就再追加一个动作。
    # 高 k 层：只在栅区 (region=gates) 淀积 0.03 厚。
    hk = [deposit("hk", "hfo2", thickness=0.03, region=gates)]
    if extra_hk:
        hk.append(add_solids("hk", "hfo2", extra_hk, mode="fade"))
    # N 型功函数金属：只盖 NMOS 栅区。
    wfn = [deposit("wfn", "wf_n", thickness=0.05, region=wfn_region)]
    if extra_wfn:
        wfn.append(add_solids("wfn", "wf_n", extra_wfn, mode="fade"))
    # P 型功函数金属：只盖 PMOS 栅区。
    wfp = [deposit("wfp", "wf_p", thickness=0.05, region=wfp_region)]
    if extra_wfp:
        wfp.append(add_solids("wfp", "wf_p", extra_wfp, mode="fade"))
    return Step(key, ("高 k 介质 + 金属栅 (HKMG)", "High-k / metal gate (HKMG)"),
                desc or ("在栅槽里先长约 0.5 nm 的界面 SiO2，再用原子层淀积 (ALD) 一层层铺上约 1.5 nm 的 HfO2 "
                         "(k≈20，比 SiO2 的 3.9 高得多)。接着分别放入 N 型和 P 型功函数金属 (TiAl / TiN)，"
                         "最后用钨/铝把槽填满并 CMP 磨平。Vt 主要由金属的功函数决定，而不是靠沟道掺杂。",
                         "In the trench a ~0.5 nm interfacial SiO2 is grown, then ~1.5 nm of HfO2 (k≈20 vs 3.9 "
                         "for SiO2) is laid down atom layer by atom layer (ALD). Separate n- and p-type "
                         "work-function metals (TiAl / TiN) follow, then W/Al fills the trench and CMP "
                         "planarises it. Vt is now set mainly by the metal work function, not channel doping."),
                # 参数表：wf_n_ev / wf_p_ev 是用户可调的功函数 (单位 eV)，改它会直接改变 Vtn / Vtp。
                [("高 k", "High-k", lambda c: "ALD HfO2 ≈ 1.5 nm (k ≈ 20)"),
                 ("EOT", "EOT", eot_text),
                 ("功函数 N / P", "Work function N / P",
                  lambda c: f"{c.p.wf_n_ev:.2f} / {c.p.wf_p_ev:.2f} eV"),
                 ("→ Vtn / Vtp", "→ Vtn / Vtp", lambda c: f"{vt_text(c, 'n')} / {vt_text(c, 'p')}")]
                # 两个列表用 + 拼接；extra_params 为 None 时用空列表 []，相当于什么都不加。
                + (extra_params or []),
                [Phase("ALD：界面层 + HfO2", "ALD: interfacial layer + HfO2", 1.8, hk),
                 Phase("N 型功函数金属 (TiAl)", "n work-function metal (TiAl)", 1.4, wfn),
                 Phase("P 型功函数金属 (TiN)", "p work-function metal (TiN)", 1.4, wfp),
                 # 钨填到比栅顶高 0.15 的位置 (先填过头)……
                 Phase("钨填充栅槽", "Tungsten fills the trench", 1.4,
                       [deposit("gfill", "gate_metal", top=gate_top + 0.15,
                                particles=("depo", (0.8, 0.8, 0.85, 1)))]),
                 # ……再用 CMP 把钨和各层金属/介质在栅顶以上的部分一起磨掉，只剩槽里的。
                 Phase("金属 CMP", "Metal CMP", 1.8, [cmp(["gfill", "wfn", "wfp", "hk"], gate_top)])],
                quiz("用 HfO2 代替 SiO2 作栅介质，主要解决了什么问题？", "What does HfO2 solve compared with SiO2?",
                     [("物理上更厚、隧穿漏电小，但等效电容一样大", "Physically thicker (less tunnelling) for the same capacitance"),
                      ("更便宜", "Cheaper"), ("导电更好", "Conducts better"), ("不需要光刻", "Needs no lithography")], 0,
                     "EOT = t_HfO2 × 3.9/k。1 nm 的 SiO2 隧穿电流巨大；k≈20 的 HfO2 可以做到 5 倍厚而电容不变。",
                     "EOT = t_HfO2 × 3.9/k. 1 nm SiO2 leaks enormously; HfO2 with k≈20 can be 5× thicker for the same capacitance."))


def contact_step(etch_layers=("ild", "ild0"), silicide_fn=None, extra_phases=None, key: str = "contact_w",
                 desc=None, title=("接触孔 + 钨/钴塞 (掩膜)", "Contacts + W/Co plugs (mask)")) -> Step:
    """ILD1, contact litho and etch through ILD1 + ILD0, optional silicide at the
    bottom of the holes, then a plug that fills the holes to ILD1_TOP.

    接触孔 + 钨/钴塞。
    物理上：
      1. 再淀积一层绝缘介质 ILD1 (盖住刚做好的金属栅)；
      2. 光刻出接触孔的位置；
      3. 向下刻穿 ILD1 和 ILD0，孔底落在源、漏 (和栅) 上；
      4. 去胶；
      5. (可选) 在孔底形成金属硅化物，降低金属和硅之间的接触电阻；
      6. 先铺一层 TiN 阻挡层，再用钨或钴把孔填满，形成导电的“塞子” (plug)。
    为什么：上面的铜导线要通过这些塞子连到下面的晶体管电极上。尺寸越小，接触面积越小、电阻越大，
      所以先进工艺特别在意接触电阻。
    参数：
      etch_layers  要刻穿的各层名字 (第一个播放刻蚀粒子动画，其余不重复播放)；
      silicide_fn  可选：一个函数，返回孔底硅化物实体；
      extra_phases 可选：在刻孔之后、去胶之前插入的额外阶段；
      title/desc   可覆盖默认标题/说明。
    """
    # 定义一个小函数 holes：返回“整个区域去掉接触孔矩形之后剩下的部分”，即光刻胶/介质要保留的区域。
    # 它是用 lambda 写的，并且“记住了”外面的变量 (这种写法叫“闭包”)，后面可以反复使用。
    holes = lambda c: rect_complement(DOMAIN, contacts(c))
    # 刻蚀动作：第一层带粒子动画；etch_layers[1:] 表示“从第 2 个起的其余各层”，不再播粒子。
    etch = [pattern(etch_layers[0], holes, mask="CONTACT")]
    etch += [pattern(l, holes, particles=False, mask="CONTACT") for l in etch_layers[1:]]
    # 依次拼出各阶段 (“+=” 表示把右边的列表接到左边列表末尾)。
    # 先淀积 ILD1 到 z = ILD1_TOP。
    phases = [Phase("淀积 ILD1", "Deposit ILD1", 1.4,
                    [deposit("ild", "ild_ox", top=ILD1_TOP, particles=("depo", (0.95, 0.95, 0.85, 1)))])]
    # 光刻：涂胶、曝光、显影 (只在接触孔处开窗)。
    phases += litho(holes, mask="CONTACT")
    phases += [Phase("刻蚀接触孔 (自对准，停在源漏上)", "Etch contact holes (self-aligned, stop on S/D)", 1.6, etch)]
    # 额外阶段 (没有就加一个空列表)。
    phases += extra_phases or []
    phases += [Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")])]
    # 可选：孔底硅化物 (加一个 600°C、30 秒的退火让金属和硅反应)。
    if silicide_fn:
        phases.append(Phase("孔底形成硅化物 (TiSi)", "Silicide at the hole bottom (TiSi)", 1.2,
                            [add_solids("silicide", "silicide", silicide_fn, mode="fade"),
                             anneal(600, 30, (1.0, 0.6, 0.3))]))
    # 最后用金属把孔填到 ILD1_TOP (region=contacts：只在孔里填)。
    phases.append(Phase("TiN 阻挡层 + 钨/钴填孔", "TiN barrier + W/Co fill", 1.6,
                        [deposit("plug", "plug", top=ILD1_TOP, region=contacts,
                                 particles=("depo", (0.75, 0.8, 0.95, 1)))]))
    return Step(key, title,
                desc or ("淀积 ILD1 后，用 CONTACT 掩膜刻出到源、漏和栅的接触孔，孔底先形成低电阻硅化物，"
                         "再填入 TiN 阻挡层和钨 (或钴)。先进工艺的接触孔比栅间距还窄，"
                         "靠栅顶的 SiN 帽和侧墙“自对准”，即使套刻偏一点也不会碰到栅。",
                         "After ILD1, the CONTACT mask opens holes to source, drain and gate; a low-resistance "
                         "silicide forms at the bottom, then a TiN barrier and W (or Co) fill them. At advanced "
                         "nodes contacts are narrower than the gate pitch and are self-aligned to the gate cap "
                         "and spacers, so a slight overlay error cannot short them to the gate."),
                [("掩膜", "Mask", lambda c: "CONTACT (EUV / 多重图形)"),
                 ("填充", "Fill", lambda c: "TiN + W / Co"),
                 ("孔数", "Contacts", lambda c: f"{len(c.lay['contacts'])}")],
                phases,
                quiz("接触电阻在先进节点为什么越来越重要？", "Why does contact resistance matter more and more at advanced nodes?",
                     [("接触面积随尺寸缩小，电阻反比增大", "Contact area shrinks, so resistance rises"),
                      ("因为电压升高了", "Because voltage went up"), ("因为用了铝", "Because of aluminium"),
                      ("和尺寸无关", "It is independent of size")], 0,
                     "R ≈ ρc/A：接触孔面积缩小一半，电阻就翻倍，会吃掉晶体管本身的驱动能力。",
                     "R ≈ ρc/A: halve the contact area and the resistance doubles, eating the transistor's drive."),
                ("接触孔", "CONTACT"))


def copper_m1_step(key: str = "cu_m1") -> Step:
    """Copper metal 1 by single damascene.

    铜互连第一层金属 (M1)，大马士革 (镶嵌) 工艺。
    物理上：铜无法像铝那样用等离子体刻蚀成导线，所以反过来做：
      1. 先铺一层低 k 绝缘介质 (到 z = M1_TOP)；
      2. 光刻并在介质里刻出导线形状的沟槽；
      3. 去胶；
      4. 铺阻挡层 + 电镀铜，把沟槽填满 (铜会溢出到沟槽外面)；
      5. CMP 把沟槽外多余的铜磨掉，只剩“镶嵌”在沟槽里的铜线。
    为什么：铜比铝电阻低，导线可以更细、信号更快；低 k 介质减小导线之间的寄生电容。
    这 4 根铜线 (GND、VDD、Vout、Vin) 把两个晶体管连成 CMOS 反相器。
    """
    # 介质要保留的区域 = 整个区域去掉导线矩形 (导线处刻出沟槽)。
    trench_keep = lambda c: rect_complement(DOMAIN, metal(c))
    return Step(key, ("铜互连 M1 (大马士革工艺)", "Copper metal 1 (damascene)"),
                ("铜很难干法刻蚀，所以反过来做：先淀积低 k 介质，用 METAL1 掩膜在介质里刻出导线沟槽，"
                 "再溅射 TaN/Ta 阻挡层和铜种子层，电镀铜填满沟槽，最后 CMP 磨掉多余的铜。"
                 "这就是“大马士革”镶嵌工艺 (0.13 µm 起取代铝)。连线：GND、VDD、Vout、Vin，构成 CMOS 反相器。",
                 "Copper can't be plasma-etched, so the wires are inlaid instead: deposit low-k dielectric, "
                 "etch wire trenches with the METAL1 mask, sputter a TaN/Ta barrier and Cu seed, electroplate "
                 "copper to fill the trenches and CMP away the excess: the damascene process (replacing Al "
                 "from 0.13 µm on). The wires form GND, VDD, Vout and Vin of the CMOS inverter."),
                [("介质", "Dielectric", lambda c: "SiCOH 低 k (k ≈ 2.7)"),
                 ("阻挡层", "Barrier", lambda c: "TaN / Ta + Cu seed"),
                 ("填充", "Fill", lambda c: "电镀铜 / Cu electroplating")],
                # 阶段列表由三段拼接而成：淀积介质 + 光刻 3 阶段 + 刻槽/去胶/电镀/CMP。
                [Phase("淀积低 k 介质", "Deposit low-k dielectric", 1.4,
                       [deposit("imd", "lowk", top=M1_TOP, particles=("depo", (0.9, 0.85, 1.0, 1)))])]
                + litho(trench_keep, mask="METAL1")
                + [Phase("刻蚀导线沟槽", "Etch wire trenches", 1.6, [pattern("imd", trench_keep, mask="METAL1")]),
                   Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")]),
                   # 铜先电镀到比 M1_TOP 高 0.2 (溢出)……
                   Phase("阻挡层 + 电镀铜", "Barrier + copper electroplating", 1.8,
                         [deposit("cu", "copper", top=M1_TOP + 0.2, particles=("depo", (1.0, 0.65, 0.35, 1)))]),
                   # ……再 CMP 磨回 M1_TOP，只剩沟槽里的铜。
                   Phase("铜 CMP", "Copper CMP", 2.0, [cmp(["cu"], M1_TOP)])],
                quiz("为什么铜互连要用“大马士革”镶嵌工艺？", "Why is copper wiring made by damascene inlay?",
                     [("铜不能被等离子体干法刻蚀成图形", "Copper can't be patterned by plasma etching"),
                      ("铜太贵", "Copper is too expensive"), ("为了好看", "Looks nicer"), ("铜不导电", "Copper doesn't conduct")], 0,
                     "铜的氯化物不挥发，干法刻不动；于是先刻介质、再填铜、最后 CMP。",
                     "Copper chlorides don't evaporate, so Cu can't be dry-etched: etch the dielectric, fill, then CMP."),
                ("金属 1", "METAL1"))


def done_step(desc, extra_params=None, key: str = "done") -> Step:
    """Final 'inverter finished' step with a summary of the electrical results.

    最后一步“完成”。物理上只做一次低温合金退火 (几何不变，只播放发光效果)。
    参数表显示最终电学结果：
      Vtn / Vtp    NMOS / PMOS 阈值电压；
      DIBL / SS    漏致势垒降低 (mV/V) 和亚阈值摆幅 (mV/dec)：两者越小，栅对沟道控制越好、关得越紧；
      tpHL / tpLH  反相器输出由高变低 / 由低变高的延迟，秒 × 1e12 = 皮秒 (ps)。
    desc 由各工艺自己提供 (每代的总结文字不同)；extra_params 可追加该工艺特有的参数行。
    """
    return Step(key, ("完成：CMOS 反相器", "Done: CMOS inverter"), desc,
                [("Vtn / Vtp", "Vtn / Vtp", lambda c: f"{vt_text(c, 'n')} / {vt_text(c, 'p')}"),
                 # 下面的 lambda 跨了两行：两个相邻的 f-字符串会自动连接成一段文字。
                 ("DIBL / SS", "DIBL / SS",
                  lambda c: f"{summarize_cached(c.p, c.features).dibl_n:.0f} mV/V / "
                            f"{summarize_cached(c.p, c.features).ss_n:.0f} mV/dec"),
                 ("tpHL / tpLH", "tpHL / tpLH",
                  lambda c: f"{summarize_cached(c.p, c.features).tran.tphl * 1e12:.2f} / "
                            f"{summarize_cached(c.p, c.features).tran.tplh * 1e12:.2f} ps")]
                + (extra_params or []),
                [Phase("合金退火 (H2/N2 400°C)", "Forming-gas anneal", 1.2, [glow((0.9, 0.9, 0.5))])],
                quiz("从平面管到 FinFET、GAA，栅对沟道的包围越来越多，主要是为了？",
                     "Gates wrap more and more of the channel (planar → FinFET → GAA). Mainly to…",
                     [("让栅更好地控制沟道，抑制短沟道效应和漏电", "Give the gate better control: less short-channel leakage"),
                      ("让晶体管更好看", "Make transistors prettier"), ("增加电阻", "Add resistance"),
                      ("减少掩膜数", "Use fewer masks")], 0,
                     "栅包得越多，漏端电场越难“伸”进沟道：DIBL 和亚阈值摆幅都变小，L 才能继续缩短。",
                     "The more the gate wraps, the less the drain field reaches into the channel: DIBL and "
                     "the sub-threshold swing shrink, so L can keep scaling."))


# 一句共用的补充说明 (中, 英)，各工艺在“源漏外延”步骤的说明文字末尾拼接它：
# 做 NMOS 外延时 PMOS 要用一层薄氮化硅保护起来 (反之亦然)，这层膜在 3D 图里省略没画。
EPI_NOTE = ("另一种管子用一层薄 SiN 硬掩膜保护 (图中未画)。",
            "The other device type is protected by a thin SiN hard mask (not drawn).")
