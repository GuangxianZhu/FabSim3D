"""~3 nm gate-all-around (GAA) nanosheet CMOS.

A Si/SiGe superlattice is grown, etched into stacks, and after the dummy
gate is removed the SiGe is etched away selectively: the Si sheets hang
between the source and drain and the high-k / metal gate fills in around
every sheet.  Sheets run along x; one stack per transistor, centred on the
default cut plane (y = 3.5) so the cross-section shows the sheets.
"""
from __future__ import annotations

from dataclasses import replace
from typing import List

from ..geometry import Solid, rect_complement, rect_intersect
from ..process_core import (DOMAIN, Flow, Phase, Step, add_solids, anneal, cmp, convert, deposit,
                            implant_solids, layout, litho, pattern, quiz, recess, replace_layer, sci,
                            spacer_span, strip, vt_text, SPACER_W, gate_span)
from . import finfet, locos, sti
from ._modern import (EPI_NOTE, channel_rects, contact_step, copper_m1_step, done_step, hkmg_step,
                      ild0_step, rmg_remove_step, side_slabs)

_S = {s.key: s for s in sti.STEPS}
_L = {s.key: s for s in locos.STEPS}
_F = {s.key: s for s in finfet.STEPS}

SHEETS = [(-0.5, -0.4), (-0.3, -0.2), (-0.1, 0.0)]      # Si channels, bottom to top
SIGE = [(-0.6, -0.5), (-0.4, -0.3), (-0.2, -0.1)]       # sacrificial SiGe below each sheet
SUB_TOP = -0.6
STACK_Y = (2.7, 4.3)
TRENCH_Z = -0.95
STI_TOP = -0.65
GATE_TOP = 0.55
EPI_TOP = 0.15
WELL_BOT = -1.8


def gaa_layout(p):
    lay = layout(p)
    lay["stacks"] = [(a[0], a[1], *STACK_Y) for a in (lay["act_n"], lay["act_p"])]
    lay["iso"] = rect_complement(DOMAIN, lay["stacks"])
    lay["spacer_bands"] = [(1.1, STACK_Y[0], STI_TOP), (STACK_Y[0], STACK_Y[1], 0.0),
                           (STACK_Y[1], 6.5, STI_TOP)]
    return lay


def _stacks(c):
    return c.lay["stacks"]


def _wafer(c):
    return [Solid.box(0, 20, 0, 8, -3.0, SUB_TOP)]


def _layers(zs):
    def fn(c):
        out = []
        for z0, z1 in zs:
            s = Solid.box(0, 20, 0, 8, z0, z1)
            s.anchor = z0
            out.append(s)
        return out
    return fn


def _well_solids(c) -> List[Solid]:
    nw = c.lay["nwell"]
    out = [Solid.box(nw[0], nw[1], nw[2], nw[3], WELL_BOT, TRENCH_Z)]
    for st in c.lay["stacks"]:
        r = rect_intersect(st, nw)
        if r:
            out.append(Solid.box(r[0], r[1], r[2], r[3], TRENCH_Z, SUB_TOP))
    return out


def _sd_rects(c, key):
    act = c.lay["act_" + key]
    g = spacer_span(c, "g" + key)
    return [(act[0], g[0], *STACK_Y), (g[1], act[1], *STACK_Y)]


def _inner_zones(c):
    """Under the spacers, where the SiGe is recessed and replaced by inner spacers."""
    out = []
    for key in ("gn", "gp"):
        g = gate_span(c, key)
        out += [(g[0] - SPACER_W, g[0], *STACK_Y), (g[1], g[1] + SPACER_W, *STACK_Y)]
    return out


def _epi(key):
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
    films of `thickness` line the top and bottom faces."""
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
    return lambda c: side_slabs(channel_rects(c, key), [STACK_Y], z0, 0.0, offset, t)


def _hk_extra(c):
    return gap_films(SIGE, thickness=0.02)(c) + _wrap(None, 0.0, 0.03, STI_TOP)(c)


def _wf_extra(key):
    return lambda c: gap_films(SIGE, key, inset=0.02)(c) + _wrap(key, 0.03, 0.05, STI_TOP + 0.03)(c)


def _contact_silicide(c):
    return [Solid.box(r[0], r[1], r[2], r[3], EPI_TOP - 0.03, EPI_TOP + 0.02)
            for k, r in c.lay["contacts"].items() if not k.startswith("g_")]


def sheet_channels(lay):
    out = []
    for key in ("n", "p"):
        g = lay["g" + key]
        for z0, z1 in SHEETS:
            out.append((key, Solid.box(g[0] - 0.05, g[1] + 0.05, STACK_Y[0] - 0.02, STACK_Y[1] + 0.02,
                                       z0 - 0.01, z1 + 0.01)))
    return out


def sheet_text(c) -> str:
    return f"3 × 2 × ({c.p.tsi_nm:.0f} + 30) nm ≈ {3 * 2 * (c.p.tsi_nm + 30) / 1e3:.2f} µm"


STEPS = [
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

    replace(_L["padox"], params=[("厚度", "Thickness", lambda c: "≈ 5 nm")]),
    replace(_S["nitride"],
            desc=("淀积 Si3N4 硬掩膜，用来刻出纳米片“叠层鳍”，之后作 STI CMP 停止层。",
                  "A Si3N4 hard mask for etching the nanosheet stacks; later the STI CMP stop.")),

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

    replace(_S["nwell_litho"], title=("N 阱光刻", "N-well lithography")),
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

    Step("gaa_dummy_gate", ("伪栅：氧化层 + 多晶硅", "Dummy gate: oxide + poly"),
         ("在叠层上长牺牲氧化层，淀积多晶硅把叠层完全埋住并磨平。",
          "A sacrificial oxide is formed on the stacks and polysilicon buries them, then it is planarised."),
         [("多晶硅", "Poly", lambda c: "≈ 100 nm, CMP 平坦化")],
         [Phase("牺牲氧化层", "Sacrificial oxide", 1.0,
                [deposit("gox", "gate_ox", thickness=0.03, region=_stacks)]),
          Phase("淀积伪栅多晶硅并磨平", "Deposit and planarise dummy poly", 1.6,
                [deposit("poly", "poly_dummy", top=GATE_TOP, particles=("depo", (0.9, 0.6, 0.45, 1)))])]),

    replace(_F["gate_litho"],
            title=("伪栅光刻 (横跨叠层)", "Dummy-gate lithography (across the stacks)"),
            desc=("用 EUV 定义横跨叠层的伪栅线，栅长约 12-16 nm。",
                  "EUV defines the dummy gate lines across the stacks; the gate length is ~12-16 nm."),
            params=[("掩膜", "Mask", lambda c: "POLY (EUV)"),
                    ("栅长 Lg", "Gate length Lg", lambda c: f"{c.p.l_um * 1e3:.0f} nm"),
                    ("栅间距 CPP", "Gate pitch CPP", lambda c: "≈ 45-50 nm")]),
    replace(_S["gate_etch"], title=("伪栅刻蚀", "Dummy-gate etch")),
    replace(_S["spacer_dep"], quiz=None),
    replace(_S["spacer_etch"]),

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

    ild0_step(GATE_TOP),
    rmg_remove_step(["gate_n", "gate_p"],
                    title=("去除伪栅 + 纳米片释放", "Dummy-gate removal + sheet release"),
                    desc=("掏空伪栅后，栅槽里露出叠层。再用对 SiGe 选择比极高的刻蚀把剩下的 SiGe 全部挖掉："
                          "硅纳米片像几块悬空的木板一样，只靠两端的源漏支撑，片与片之间留出空隙。",
                          "With the dummy gate gone the stack is exposed in the trench. A highly SiGe-selective "
                          "etch then removes the remaining SiGe: the silicon sheets hang like planks held only "
                          "by the source/drain at their ends, with gaps between them."),
                    extra_phase=Phase("选择性刻蚀 SiGe：纳米片悬空", "Selective SiGe etch: sheets released", 2.2,
                                      [strip("sige")])),
    hkmg_step(GATE_TOP, extra_hk=_hk_extra, extra_wfn=_wf_extra("n"), extra_wfp=_wf_extra("p"),
              desc=("ALD 的气体能钻进片与片之间几纳米的缝隙：HfO2 先包住每一片的上下左右四面，"
                    "功函数金属再把缝隙填满，最后钨填满栅槽并 CMP。栅从四面包住每一片纳米片——“全环绕栅”。",
                    "ALD precursors creep into the few-nm gaps: HfO2 coats every sheet on all four sides, the "
                    "work-function metal fills the gaps, then tungsten fills the trench and CMP. The gate now "
                    "surrounds every sheet: gate-all-around."),
              extra_params=[("包围方式", "Gate wrap", lambda c: "四面 (全环绕) / all 4 sides")]),
    contact_step(silicide_fn=_contact_silicide),
    copper_m1_step(),
    done_step(("GAA 纳米片反相器完成。把剖面放在 y = 3.5 可以看到三片纳米片被金属栅上下夹住。"
               "在“电学特性”里对比 FinFET：栅长更短 (15 nm)，DIBL 却更小、亚阈值摆幅接近 60 mV/dec 的理论极限。"
               "打开 3D 载流子仿真看电子在纳米片中流动。",
               "The GAA nanosheet inverter is done. With the cut at y = 3.5 you can see the three sheets "
               "sandwiched by the metal gate. Compared with the FinFET the gate is shorter (15 nm) yet DIBL "
               "is smaller and the swing approaches the 60 mV/dec limit. Turn on the 3D carrier view to see "
               "electrons flowing in the sheets."),
              extra_params=[("纳米片 / 有效宽度", "Sheets / Weff", sheet_text)]),
]

REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.8),
    ("nsd", "SiP", "SiP", 4.1, 0.0),
    ("psd", "SiGe", "SiGe", 12.4, 0.0),
    ("gfill", "金属栅", "metal gate", 5.25, 0.85),
    ("cu", "Cu", "Cu", 10.25, 1.95),
]

GAA_SLIDERS = [s if s[0] != "tsi_nm" else ("tsi_nm", "p_tsheet", 3.0, 15.0, False)
               for s in finfet.MULTIGATE_SLIDERS]

FLOW = Flow(
    key="gaa",
    name=("GAA 纳米片工艺", "GAA nanosheet"),
    short=("GAA 3nm", "GAA 3nm"),
    node=("约 3-2 nm 代：硅纳米片堆叠，栅四面全环绕 (GAA)",
          "~3-2 nm: stacked Si nanosheets, gate all around"),
    steps=STEPS,
    features=frozenset({"sce", "hkmg", "gaa"}),
    region_labels=REGION_LABELS,
    terminal_labels=locos.TERMINAL_LABELS,
    layout_fn=gaa_layout,
    sliders=GAA_SLIDERS,
    channel_fn=sheet_channels,
    carrier_ys=[STACK_Y],
    defaults=dict(tox_nm=0.8, na_cm3=1e16, nwell_dose_cm2=2e13, l_um=0.015, wn_um=0.21, wp_um=0.21,
                  vdd=0.7, cload_ff=0.4, mu_n=250.0, mu_p=170.0, wf_n_ev=4.45, wf_p_ev=4.77, tsi_nm=5.0,
                  lambda_um=0.0015),
)
