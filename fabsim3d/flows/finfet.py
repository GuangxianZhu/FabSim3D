"""~14 nm FinFET CMOS: fins, gate wrapped on three sides, epitaxial raised S/D.

The channel stands up out of the wafer as a thin fin; the gate covers its
top and both sidewalls, so the drain field can hardly reach into the channel.
Fins run along x (source -> drain); three fins per transistor sit side by
side in y.  Fin tops are at z = 0, the STI is recessed to FIN_REVEAL.
"""
from __future__ import annotations

from dataclasses import replace
from typing import List

from ..geometry import Solid, rect_complement, rect_intersect
from ..process_core import (DOMAIN, Flow, Phase, Step, add_solids, anneal, cmp, deposit, gate_span,
                            gates, implant_solids, layout, litho, pattern, quiz, recess, replace_layer,
                            sci, spacer_span, split_gates, strip, summarize_cached, vt_text)
from . import locos, sti
from ._modern import (EPI_NOTE, M1_TOP, channel_rects, contact_step, copper_m1_step, done_step,
                      hkmg_step, ild0_step, rmg_remove_step, side_slabs)

_S = {s.key: s for s in sti.STEPS}
_L = {s.key: s for s in locos.STEPS}

FIN_W = 0.36
FIN_YC = (2.3, 3.5, 4.7)
FIN_BANDS = [(y - FIN_W / 2, y + FIN_W / 2) for y in FIN_YC]
TRENCH_Z = -0.85         # silicon etched down to here between fins
FIN_REVEAL = -0.45       # STI top after the recess: exposed fin height 0.45
NITRIDE_TOP = 0.18
GATE_TOP = 0.5
SD_RECESS = -0.25
EPI_TOP = 0.15
WELL_BOT = -1.8


def finfet_layout(p):
    lay = layout(p)
    fins = []
    for act in (lay["act_n"], lay["act_p"]):
        fins += [(act[0], act[1], y0, y1) for y0, y1 in FIN_BANDS]
    lay["fins"] = fins
    lay["iso"] = rect_complement(DOMAIN, fins)
    gy0, gy1 = 1.1, 6.5
    bands, y = [], gy0
    for y0, y1 in FIN_BANDS:
        bands += [(y, y0, FIN_REVEAL), (y0, y1, 0.0)]
        y = y1
    bands.append((y, gy1, FIN_REVEAL))
    lay["spacer_bands"] = bands
    return lay


def _fins(c):
    return c.lay["fins"]


def _well_solids(c) -> List[Solid]:
    nw = c.lay["nwell"]
    out = [Solid.box(nw[0], nw[1], nw[2], nw[3], WELL_BOT, TRENCH_Z)]
    for f in c.lay["fins"]:
        r = rect_intersect(f, nw)
        if r:
            out.append(Solid.box(r[0], r[1], r[2], r[3], TRENCH_Z, 0.0))
    for s in out:
        s.anchor = 0.0
    return out


def _sd_fin_rects(c, key):
    """Fin segments outside gate + spacers of the n (key 'n') or p device."""
    act = c.lay["act_" + key]
    g = spacer_span(c, "g" + key)
    return [(x0, x1, y0, y1) for x0, x1 in ((act[0], g[0]), (g[1], act[1])) for y0, y1 in FIN_BANDS]


def _epi(key):
    """Merged epitaxial S/D: one block per side bridging the three fins."""
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
    return side_slabs(channel_rects(c), FIN_BANDS, FIN_REVEAL, 0.0, 0.0, 0.03)


def _wf_wrap(key):
    return lambda c: side_slabs(channel_rects(c, key), FIN_BANDS, FIN_REVEAL + 0.03, 0.0, 0.03, 0.05)


def _contact_silicide(c):
    ct = c.lay["contacts"]
    return [Solid.box(r[0], r[1], r[2], r[3], EPI_TOP - 0.03, EPI_TOP + 0.02)
            for k, r in ct.items() if not k.startswith("g_")]


def fin_channels(lay):
    """Inversion layers: the whole fin under the gate (top + both sidewalls)."""
    out = []
    for key in ("n", "p"):
        g = lay["g" + key]
        for y0, y1 in FIN_BANDS:
            out.append((key, Solid.box(g[0] - 0.05, g[1] + 0.05, y0 - 0.02, y1 + 0.02, FIN_REVEAL, 0.01)))
    return out


def fin_text(c) -> str:
    weff = 2 * 42 + c.p.tsi_nm
    return (f"{len(FIN_YC)} × (2×42 + {c.p.tsi_nm:.0f}) nm ≈ {len(FIN_YC) * weff / 1e3:.2f} µm")


STEPS = [
    replace(_L["wafer"],
            desc=("300 mm <100> P 型硅片。FinFET (鳍式场效应晶体管) 不再把沟道做在硅表面，"
                  "而是从硅片里“刻”出一排薄薄的竖直硅鳍，让栅从三面包住它。2011 年 Intel 22 nm 首次量产。",
                  "A 300 mm <100> p-type wafer. A FinFET no longer puts the channel in the wafer surface: "
                  "thin vertical silicon fins are carved out of the wafer and the gate wraps them on three "
                  "sides. Intel shipped the first ones at 22 nm in 2011."),
            params=[("晶向", "Orientation", lambda c: "<100>"),
                    ("硅片直径", "Wafer diameter", lambda c: "300 mm"),
                    ("鳍掺杂", "Fin doping", lambda c: sci(c.p.na_cm3, "cm^-3") + " (近本征)")]),
    _L["padox"],
    replace(_S["nitride"],
            desc=("LPCVD 淀积 Si3N4 硬掩膜。它将定义鳍的图形，之后还是 STI CMP 的停止层。",
                  "An LPCVD Si3N4 hard mask. It will carry the fin pattern and later stop the STI CMP.")),

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

    replace(_S["nwell_litho"], title=("N 阱光刻", "N-well lithography")),
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
    replace(_S["spacer_dep"], quiz=None),
    replace(_S["spacer_etch"],
            desc=("各向异性回刻形成栅侧墙。在 FinFET 里还要把鳍侧壁上的侧墙材料清干净，否则会挡住后面的源漏外延。",
                  "An anisotropic etch-back forms the gate spacers. In a FinFET the film must also be cleared "
                  "from the fin sidewalls, or it would block the S/D epitaxy.")),

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

    ild0_step(GATE_TOP),
    rmg_remove_step(["gate_n", "gate_p"],
                    desc=("刻掉伪栅多晶硅和牺牲氧化层。栅槽底部，鳍的顶面和两个侧面都露了出来。",
                          "The dummy poly and sacrificial oxide are etched out. At the bottom of the gate "
                          "trench the top and both sidewalls of each fin are now exposed.")),
    hkmg_step(GATE_TOP, extra_hk=_hk_wrap, extra_wfn=_wf_wrap("n"), extra_wfp=_wf_wrap("p"),
              desc=("ALD 的 HfO2 和功函数金属是“保形”的：它们像涂料一样均匀地包住鳍的顶面和两个侧面，"
                    "于是栅从三面控制沟道 (三栅)。最后用钨填满鳍之间和栅槽，CMP 磨平。Vt 由功函数决定，"
                    "可用不同厚度的功函数金属做出多种 Vt。",
                    "ALD HfO2 and the work-function metals are conformal: like paint they coat the top and both "
                    "sidewalls of each fin, so the gate controls the channel from three sides (tri-gate). "
                    "Tungsten fills the space between the fins and the trench, then CMP. The work function sets "
                    "Vt; different WF-metal thicknesses give several Vt flavours."),
              extra_params=[("包围方式", "Gate wrap", lambda c: "三面 (三栅) / 3 sides")]),
    contact_step(silicide_fn=_contact_silicide),
    copper_m1_step(),
    done_step(("FinFET 反相器完成。在“电学特性 → Vt-L”里对比 28 nm 平面管：栅长更短 (20 nm) 而 DIBL 只有约 60 mV/V，"
               "亚阈值摆幅接近 70 mV/dec。打开 3D 载流子仿真：电子在鳍里流动，栅从三面控制它。"
               "在“工艺参数”里把鳍宽调大，DIBL 会迅速变差。",
               "The FinFET inverter is done. On Electrical → Vt-L compare with 28 nm planar: the gate is "
               "shorter (20 nm) yet DIBL is only ~60 mV/V and the swing is near 70 mV/dec. Turn on the 3D "
               "carrier view: electrons flow inside the fins under a gate that wraps three sides. Widen the "
               "fin on the Parameters tab and DIBL degrades quickly."),
              extra_params=[("鳍数 / 有效宽度", "Fins / Weff", fin_text)]),
]

REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.65),
    ("nsd", "SiP", "SiP", 4.1, 0.0),
    ("psd", "SiGe", "SiGe", 12.4, 0.0),
    ("gfill", "金属栅", "metal gate", 5.25, 0.8),
    ("cu", "Cu", "Cu", 10.25, 1.95),
]

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
