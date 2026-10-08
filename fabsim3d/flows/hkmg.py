"""~28 nm planar CMOS: high-k / metal gate (gate-last), embedded SiGe S/D, NiSi, Cu.

The last planar bulk generation.  New relative to the 0.25 µm STI flow:
dummy poly gate + replacement metal gate, HfO2 high-k, dual work-function
metals, recessed SiGe source/drain for PMOS strain, spike + laser anneal,
nickel silicide, self-aligned contacts and damascene copper.
"""
from __future__ import annotations

from dataclasses import replace

from ..geometry import Solid
from ..process_core import (Flow, Phase, Step, add_solids, anneal, deposit, gate_span, implant, litho,
                            quiz, recess, replace_layer, sd_annealed, sd_rects, spacer_span, strip,
                            summarize_cached)
from . import locos, sti
from ._modern import (EPI_NOTE, contact_step, copper_m1_step, done_step, hkmg_step, ild0_step,
                      rmg_remove_step)

_S = {s.key: s for s in sti.STEPS}

GATE_TOP = 0.40          # dummy oxide 0.05 + dummy poly 0.35
SIGE_BOT, SIGE_TOP = -0.28, 0.12


def _sd_n(c):
    return sd_rects(c.lay["act_n"], spacer_span(c, "gn"))


def _sd_p(c):
    return sd_rects(c.lay["act_p"], spacer_span(c, "gp"))


def _sige(c):
    out = []
    for r in _sd_p(c):
        s = Solid.box(r[0], r[1], r[2], r[3], SIGE_BOT, SIGE_TOP)
        s.anchor = SIGE_BOT
        out.append(s)
    return out


def _nisi(c):
    out = [Solid.box(r[0], r[1], r[2], r[3], -0.04, 0.02) for r in _sd_n(c)]
    out += [Solid.box(r[0], r[1], r[2], r[3], SIGE_TOP - 0.04, SIGE_TOP + 0.02) for r in _sd_p(c)]
    return out


STEPS = [
    replace(_S["wafer"],
            desc=("从 300 mm 的 <100> P 型硅片开始。28 nm 是最后一代“平面”体硅 CMOS："
                  "晶体管仍然平躺在硅表面，但栅极、源漏和互连都已经和 0.25 µm 时代完全不同。",
                  "We start from a 300 mm <100> p-type wafer. 28 nm is the last planar bulk CMOS node: the "
                  "transistor still lies flat on the surface, but its gate, source/drain and wiring are "
                  "completely different from the 0.25 µm era."),
            params=[("晶向", "Orientation", lambda c: "<100>"),
                    ("硅片直径", "Wafer diameter", lambda c: "300 mm"),
                    ("沟道掺杂 Na", "Channel doping Na", lambda c: f"{c.p.na_cm3:.1e} cm^-3")]),
    _S["padox"],
    _S["nitride"],
    replace(_S["sti_litho"],
            params=[("掩膜", "Mask", lambda c: "#1 ACTIVE"),
                    ("光源", "Source", lambda c: "ArF 浸没式 193 nm (193i)")],
            quiz=quiz("28 nm 节点的关键层用什么光刻？", "Lithography for the critical layers at 28 nm?",
                      [("ArF 浸没式 193 nm", "ArF immersion 193 nm"), ("汞灯 i 线", "Hg i-line"),
                       ("EUV 13.5 nm", "EUV 13.5 nm"), ("X 射线", "X-ray")], 0,
                      "镜头和晶圆之间充满水 (n≈1.44)，等效数值孔径 NA 可达 1.35，再加上双重图形就能做到 28 nm。",
                      "Water between lens and wafer (n≈1.44) raises NA to 1.35; with double patterning that reaches 28 nm.")),
    _S["sti_etch"],
    _S["sti_liner"],
    _S["sti_fill"],
    _S["sti_cmp"],
    _S["sti_strip"],
    _S["nwell_litho"],
    _S["nwell_implant_he"],
    _S["nwell_anneal"],

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

    replace(_S["gate_litho"],
            title=("伪栅光刻 (掩膜)", "Dummy-gate lithography (mask)"),
            params=[("掩膜", "Mask", lambda c: "POLY (193i 双重图形 / double patterning)"),
                    ("栅长 Lg", "Gate length Lg", lambda c: f"{c.p.l_um * 1e3:.0f} nm"),
                    ("宽度 Wn / Wp", "Wn / Wp", lambda c: f"{c.p.wn_um:.2f} / {c.p.wp_um:.2f} µm")]),
    replace(_S["gate_etch"], title=("伪栅刻蚀", "Dummy-gate etch")),

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
    replace(_S["pldd"],
            title=("P 型延伸区 + Halo 注入", "p extension + halo implants"),
            desc=("PMOS 做法相同：极浅 BF2 延伸区 + 大倾角砷 Halo。",
                  "Same for the PMOS: an ultra-shallow BF2 extension plus a tilted arsenic halo."),
            params=[("延伸区", "Extension", lambda c: "BF2, 2 keV"),
                    ("Halo", "Halo", lambda c: "As, 40 keV, 30° 倾角 / tilt")]),
    _S["spacer_dep"],
    _S["spacer_etch"],

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

    ild0_step(GATE_TOP),
    rmg_remove_step(["gate_n", "gate_p"]),
    hkmg_step(GATE_TOP),
    contact_step(),
    copper_m1_step(),
    done_step(("28 nm 平面 HKMG 反相器完成。对比 0.25 µm：VDD 只有 0.9 V，栅介质换成 HfO2 + 金属，"
               "PMOS 有 SiGe 应变。打开“电学特性 → Vt-L”可以看到：栅长 30 nm 时 DIBL 已超过 100 mV/V，"
               "亚阈值摆幅也明显变差——平面结构的栅已经“管不住”沟道了，这正是下一代改用 FinFET 的原因。",
               "The 28 nm planar HKMG inverter is done. Versus 0.25 µm: VDD is only 0.9 V, the gate is HfO2 + "
               "metal and the PMOS is strained by SiGe. On Electrical → Vt-L note that at Lg = 30 nm DIBL "
               "exceeds 100 mV/V and the sub-threshold swing degrades: a planar gate can no longer control "
               "the channel, which is why the next generation moved to FinFETs.")),
]

REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.2),
    ("nplus", "n+", "n+", 2.4, -0.45),
    ("psd", "SiGe", "SiGe", 12.4, 0.0),
    ("gfill", "HKMG", "HKMG", 5.25, 0.75),
    ("cu", "Cu", "Cu", 10.25, 1.95),
]

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
