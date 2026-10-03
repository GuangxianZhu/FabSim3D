"""Classic ~1 µm CMOS flow: single n-well, LOCOS isolation, Al metal 1."""
from __future__ import annotations

from typing import List

from ..geometry import Solid, rect_complement, split_box
from ..process_core import (DOMAIN, ACT_Y, SUB_DEPTH, Ctx, Flow, Phase, PhaseAnim, Step, Wafer,
                            actives, anneal, contacts, gate_span, coat, deposit, develop, expose, gates, glow,
                            implant, litho, metal, nwe_text, pattern, quiz, recolor, replace_layer, sci,
                            sd_annealed, sd_rects, split_gates, strip, summarize_cached, vt_text)


def _locos_prism(a: float, b: float, y0: float, y1: float) -> Solid:
    top, bot, beak_in, beak_out = 0.35, -0.25, 0.35, 0.25
    pts = []
    if a <= DOMAIN[0] + 1e-6:
        pts += [(a, bot)]
    else:
        pts += [(a - beak_out, 0.0), (a + beak_in, bot)]
    if b >= DOMAIN[1] - 1e-6:
        pts += [(b, bot), (b, top)]
    else:
        pts += [(b - beak_in, bot), (b + beak_out, 0.0), (b - beak_in, top)]
    if a <= DOMAIN[0] + 1e-6:
        pts += [(a, top)]
    else:
        pts += [(a + beak_in, top)]
    s = Solid(pts, y0, y1)
    s.anchor = 0.0
    return s



def _fox_solids(c: Ctx) -> List[Solid]:
    out = [_locos_prism(a, b, 0.0, 8.0) for a, b in c.lay["fox_x"]]
    for act in actives(c):
        out.append(Solid.box(act[0], act[1], 0.0, ACT_Y[0], -0.25, 0.35))
        out.append(Solid.box(act[0], act[1], ACT_Y[1], 8.0, -0.25, 0.35))
    for s in out:
        s.anchor = 0.0
    return out


def _locos(w: Wafer, c: Ctx, a: PhaseAnim):
    fox = _fox_solids(c)
    w.layer("fox", "fox").solids = fox
    a.grow.extend(fox)
    pad = w.layers.get("padox")
    if pad:
        kept_all = []
        for s in pad.solids:
            kept, removed = split_box(s, actives(c))
            kept_all += kept
            a.ghosts += [("pad_ox", r, "fade") for r in removed]
        pad.solids = kept_all
    a.glow = (1.0, 0.45, 0.15)



STEPS: List[Step] = [
    Step("wafer", ("P 型硅衬底", "p-type silicon wafer"),
         ("工艺从轻掺杂硼的 <100> 晶向 P 型单晶硅片开始。NMOS 直接做在 P 型衬底上，"
          "PMOS 之后要做在 N 阱里。<100> 晶向界面态密度低，适合 MOS 器件。",
          "We start from a lightly boron-doped <100> p-type single-crystal wafer. NMOS devices "
          "are built directly in the p-substrate; PMOS devices will sit in an n-well. <100> "
          "gives the lowest interface-trap density."),
         [("晶向", "Orientation", lambda c: "<100>"),
          ("衬底/沟道掺杂 Na (硼)", "Substrate/channel Na (B)", lambda c: sci(c.p.na_cm3, "cm^-3")),
          ("硅片直径", "Wafer diameter", lambda c: "200 mm")],
         [Phase("准备硅片 (RCA 清洗)", "Wafer preparation (RCA clean)", 1.0,
                [replace_layer("sub", "p_sub", lambda c: [Solid.box(0, 20, 0, 8, -SUB_DEPTH, 0)])])],
         quiz("为什么 CMOS 常用 <100> 晶向硅片？", "Why are <100> wafers preferred for CMOS?",
            [("硬度最高", "Highest hardness"), ("Si/SiO2 界面态密度最低", "Lowest Si/SiO2 interface-trap density"),
             ("最便宜", "Cheapest"), ("导热最好", "Best thermal conductivity")], 1,
            "<100> 面悬挂键少，界面态密度低，阈值电压更稳定、迁移率更高。",
            "The <100> surface has fewer dangling bonds, so interface traps are lowest.")),

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
         ("N 阱", "NWELL")),

    Step("nwell_implant", ("N 阱离子注入", "N-well ion implantation"),
         ("以光刻胶为掩蔽，注入磷离子 (P+)。离子在光刻胶中被挡住，只有窗口区域的硅被掺杂。"
          "注入剂量决定 N 阱浓度，进而决定 PMOS 的阈值电压。",
          "Phosphorus ions are implanted using the resist as a mask. Only the opened window is "
          "doped. The dose sets the well concentration and hence the PMOS threshold."),
         [("离子", "Species", lambda c: "P+ (磷 / phosphorus)"),
          ("剂量", "Dose", lambda c: sci(c.p.nwell_dose_cm2, "cm^-2")),
          ("能量", "Energy", lambda c: "≈ 150 keV"),
          ("推进后 Nd", "Nd after drive-in", lambda c: sci(c.p.nd_cm3, "cm^-3")),
          ("→ PMOS Vtp", "→ PMOS Vtp", lambda c: vt_text(c, "p"))],
         [Phase("磷离子注入", "Phosphorus implant", 2.4,
                [implant("nimp", "n_implant", lambda c: [c.lay["nwell"]], -0.3, (1.0, 0.85, 0.2, 1),
                         species="P", dose=lambda c: c.p.nwell_dose_cm2, energy_kev=150)])],
         quiz("N 阱注入剂量升高，PMOS 的 |Vtp| 会？", "If the n-well dose increases, |Vtp| of the PMOS will…",
            [("增大", "Increase"), ("减小", "Decrease"), ("不变", "Stay the same"), ("变为 0", "Become zero")], 0,
            "阱浓度越高，耗尽电荷 Qdep 越大，需要更大的栅压才能反型，|Vtp| 增大。可在“参数”页验证。",
            "Higher Nd means larger depletion charge, so |Vtp| rises. Try it on the Parameters tab.")),

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

    Step("gate_ox", ("栅氧化", "Gate oxidation"),
         ("在有源区生长高质量的薄栅氧化层。栅氧厚度 tox 决定栅电容 Cox = εox/tox，"
          "直接影响阈值电压和驱动电流，是最关键的工艺参数之一。",
          "A high-quality thin gate oxide is grown on the active areas. Its thickness sets "
          "Cox = εox/tox, strongly affecting threshold voltage and drive current."),
         [("温度", "Temperature", lambda c: "900 °C, 干氧 / dry O2"),
          ("tox", "tox", lambda c: f"{c.p.tox_nm:.1f} nm"),
          ("Cox", "Cox", lambda c: f"{summarize_cached(c.p, c.features).cox * 1e7:.2f} fF/µm²"),
          ("→ Vtn / Vtp", "→ Vtn / Vtp", lambda c: f"{vt_text(c, 'n')} / {vt_text(c, 'p')}")],
         [Phase("干氧生长栅氧", "Dry oxidation of gate oxide", 1.6,
                [deposit("gox", "gate_ox", thickness=0.05, region=actives), anneal(900, 1200, (1.0, 0.5, 0.2))])],
         quiz("栅氧变薄（其他不变），NMOS 驱动电流会？", "Thinner gate oxide (all else equal) makes NMOS drive current…",
            [("增大", "Increase"), ("减小", "Decrease"), ("不变", "Unchanged"), ("先减后增", "Decrease then increase")], 0,
            "Cox 增大 → k' = µCox 增大且 Vt 降低，电流增大。",
            "Larger Cox raises k' = µCox and lowers Vt, so current increases.")),

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

    Step("contact", ("接触孔光刻与刻蚀 (掩膜 6)", "Contact lithography & etch (mask 6)"),
         ("涂胶并用 CONTACT 掩膜曝光显影，再各向异性刻蚀 ILD，打开到源、漏和栅极的接触孔，最后去胶。",
          "Coat, expose the CONTACT mask, develop, then anisotropically etch the ILD to open "
          "holes down to source, drain and gate. Strip resist."),
         [("掩膜", "Mask", lambda c: "#6 CONTACT"),
          ("刻蚀", "Etch", lambda c: "RIE, CHF3/CF4"),
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
REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("fox", "场氧", "FOX", 10.25, 0.75),
    ("nplus", "n+", "n+", 3.2, -0.55),
    ("nplus", "n+", "n+", 7.5, -0.55),
    ("pplus", "p+", "p+", 13.0, -0.55),
    ("pplus", "p+", "p+", 17.3, -0.55),
]

TERMINAL_LABELS = [
    ("GND", 3.35, 1.0), ("Vout", 10.25, 3.5), ("VDD", 17.15, 1.0), ("Vin", 12.8, 7.1),
]


FLOW = Flow(
    key="locos",
    name=("经典 LOCOS 工艺", "Classic LOCOS"),
    node=("约 1.0 µm 代：LOCOS 隔离 + 单 N 阱",
          "~1.0 µm era: LOCOS + single n-well"),
    steps=STEPS,
    features=frozenset({"locos"}),
    region_labels=REGION_LABELS,
    terminal_labels=TERMINAL_LABELS,
)
