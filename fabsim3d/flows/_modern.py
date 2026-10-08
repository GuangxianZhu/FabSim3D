"""Building blocks shared by the advanced-node flows (28 nm HKMG, FinFET, GAA, CFET).

All of them use a replacement-metal-gate ("gate-last") module, a planarised
ILD0, self-aligned contacts with a W/Co plug and a single-damascene copper
metal 1.  Each factory returns a Step; gate_top is the height of the dummy
gate (and therefore of the ILD0 after CMP).
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from ..geometry import Rect, Solid, rect_complement
from ..process_core import (DOMAIN, Phase, Step, add_solids, anneal, cmp, contacts, deposit, gates,
                            glow, litho, metal, pattern, quiz, strip, summarize_cached, vt_text)

ILD1_TOP = 1.3          # top of the contact-level dielectric (= bottom of metal 1)
M1_TOP = 1.75           # copper metal-1 thickness 0.45 (display units)


def eot_text(c) -> str:
    return f"{c.p.tox_nm:.2f} nm"


def gate_rects_n(c) -> List[Rect]:
    return c.lay["gates_n"]


def gate_rects_p(c) -> List[Rect]:
    return c.lay["gates_p"]


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------

def side_slabs(rects: Sequence[Rect], bands: Sequence[Tuple[float, float]], z0: float, z1: float,
               offset: float, t: float) -> List[Solid]:
    """Thin vertical films on the y-facing sidewalls of fins / nanosheet stacks,
    inside the gate footprint (x-range of each rect): how a film wraps the channel."""
    out = []
    for r in rects:
        for y0, y1 in bands:
            if y1 <= r[2] or y0 >= r[3]:
                continue
            for a, b in ((y0 - offset - t, y0 - offset), (y1 + offset, y1 + offset + t)):
                s = Solid.box(r[0], r[1], a, b, z0, z1)
                s.anchor = z0
                out.append(s)
    return out


def channel_rects(c, key: str = None) -> List[Rect]:
    """Gate footprints restricted to the channel part (no contact pad)."""
    rs = c.lay["gates_n"] + c.lay["gates_p"] if key is None else c.lay["gates_" + key]
    return [r for r in rs if r[3] - r[2] > 2.0]


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------

def ild0_step(gate_top: float, key: str = "ild0") -> Step:
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
    phases = [Phase("刻蚀去除伪栅多晶硅", "Etch out the dummy poly", 1.8,
                    [strip(g) for g in gate_layers]),
              Phase("HF 去除伪栅氧化层", "HF removes the dummy oxide", 1.0,
                    [pattern("gox", lambda c: rect_complement(DOMAIN, gates(c)), particles=False)])]
    if extra_phase:
        phases.append(extra_phase)
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
    wf*_region say where each work-function metal covers the top of the channel."""
    hk = [deposit("hk", "hfo2", thickness=0.03, region=gates)]
    if extra_hk:
        hk.append(add_solids("hk", "hfo2", extra_hk, mode="fade"))
    wfn = [deposit("wfn", "wf_n", thickness=0.05, region=wfn_region)]
    if extra_wfn:
        wfn.append(add_solids("wfn", "wf_n", extra_wfn, mode="fade"))
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
                [("高 k", "High-k", lambda c: "ALD HfO2 ≈ 1.5 nm (k ≈ 20)"),
                 ("EOT", "EOT", eot_text),
                 ("功函数 N / P", "Work function N / P",
                  lambda c: f"{c.p.wf_n_ev:.2f} / {c.p.wf_p_ev:.2f} eV"),
                 ("→ Vtn / Vtp", "→ Vtn / Vtp", lambda c: f"{vt_text(c, 'n')} / {vt_text(c, 'p')}")]
                + (extra_params or []),
                [Phase("ALD：界面层 + HfO2", "ALD: interfacial layer + HfO2", 1.8, hk),
                 Phase("N 型功函数金属 (TiAl)", "n work-function metal (TiAl)", 1.4, wfn),
                 Phase("P 型功函数金属 (TiN)", "p work-function metal (TiN)", 1.4, wfp),
                 Phase("钨填充栅槽", "Tungsten fills the trench", 1.4,
                       [deposit("gfill", "gate_metal", top=gate_top + 0.15,
                                particles=("depo", (0.8, 0.8, 0.85, 1)))]),
                 Phase("金属 CMP", "Metal CMP", 1.8, [cmp(["gfill", "wfn", "wfp", "hk"], gate_top)])],
                quiz("用 HfO2 代替 SiO2 作栅介质，主要解决了什么问题？", "What does HfO2 solve compared with SiO2?",
                     [("物理上更厚、隧穿漏电小，但等效电容一样大", "Physically thicker (less tunnelling) for the same capacitance"),
                      ("更便宜", "Cheaper"), ("导电更好", "Conducts better"), ("不需要光刻", "Needs no lithography")], 0,
                     "EOT = t_HfO2 × 3.9/k。1 nm 的 SiO2 隧穿电流巨大；k≈20 的 HfO2 可以做到 5 倍厚而电容不变。",
                     "EOT = t_HfO2 × 3.9/k. 1 nm SiO2 leaks enormously; HfO2 with k≈20 can be 5× thicker for the same capacitance."))


def contact_step(etch_layers=("ild", "ild0"), silicide_fn=None, extra_phases=None, key: str = "contact_w",
                 desc=None, title=("接触孔 + 钨/钴塞 (掩膜)", "Contacts + W/Co plugs (mask)")) -> Step:
    """ILD1, contact litho and etch through ILD1 + ILD0, optional silicide at the
    bottom of the holes, then a plug that fills the holes to ILD1_TOP."""
    holes = lambda c: rect_complement(DOMAIN, contacts(c))
    etch = [pattern(etch_layers[0], holes, mask="CONTACT")]
    etch += [pattern(l, holes, particles=False, mask="CONTACT") for l in etch_layers[1:]]
    phases = [Phase("淀积 ILD1", "Deposit ILD1", 1.4,
                    [deposit("ild", "ild_ox", top=ILD1_TOP, particles=("depo", (0.95, 0.95, 0.85, 1)))])]
    phases += litho(holes, mask="CONTACT")
    phases += [Phase("刻蚀接触孔 (自对准，停在源漏上)", "Etch contact holes (self-aligned, stop on S/D)", 1.6, etch)]
    phases += extra_phases or []
    phases += [Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")])]
    if silicide_fn:
        phases.append(Phase("孔底形成硅化物 (TiSi)", "Silicide at the hole bottom (TiSi)", 1.2,
                            [add_solids("silicide", "silicide", silicide_fn, mode="fade"),
                             anneal(600, 30, (1.0, 0.6, 0.3))]))
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
                [Phase("淀积低 k 介质", "Deposit low-k dielectric", 1.4,
                       [deposit("imd", "lowk", top=M1_TOP, particles=("depo", (0.9, 0.85, 1.0, 1)))])]
                + litho(trench_keep, mask="METAL1")
                + [Phase("刻蚀导线沟槽", "Etch wire trenches", 1.6, [pattern("imd", trench_keep, mask="METAL1")]),
                   Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")]),
                   Phase("阻挡层 + 电镀铜", "Barrier + copper electroplating", 1.8,
                         [deposit("cu", "copper", top=M1_TOP + 0.2, particles=("depo", (1.0, 0.65, 0.35, 1)))]),
                   Phase("铜 CMP", "Copper CMP", 2.0, [cmp(["cu"], M1_TOP)])],
                quiz("为什么铜互连要用“大马士革”镶嵌工艺？", "Why is copper wiring made by damascene inlay?",
                     [("铜不能被等离子体干法刻蚀成图形", "Copper can't be patterned by plasma etching"),
                      ("铜太贵", "Copper is too expensive"), ("为了好看", "Looks nicer"), ("铜不导电", "Copper doesn't conduct")], 0,
                     "铜的氯化物不挥发，干法刻不动；于是先刻介质、再填铜、最后 CMP。",
                     "Copper chlorides don't evaporate, so Cu can't be dry-etched: etch the dielectric, fill, then CMP."),
                ("金属 1", "METAL1"))


def done_step(desc, extra_params=None, key: str = "done") -> Step:
    return Step(key, ("完成：CMOS 反相器", "Done: CMOS inverter"), desc,
                [("Vtn / Vtp", "Vtn / Vtp", lambda c: f"{vt_text(c, 'n')} / {vt_text(c, 'p')}"),
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


EPI_NOTE = ("另一种管子用一层薄 SiN 硬掩膜保护 (图中未画)。",
            "The other device type is protected by a thin SiN hard mask (not drawn).")
