"""~0.25 µm CMOS flow: shallow-trench isolation (STI) with CMP planarisation.

Front half is new (trench etch, liner, HDP fill, CMP, retrograde n-well,
ILD CMP); gate, source/drain, contact and metal steps are shared with the
LOCOS flow.
"""
from __future__ import annotations

from dataclasses import replace

from ..geometry import Solid
from ..process_core import (Flow, Phase, Step, actives, anneal, cmp, deposit, implant, litho,
                            nwe_text, pattern, quiz, recess, replace_layer, sci, strip, summarize_cached,
                            vt_text)
from . import locos

_L = {s.key: s for s in locos.STEPS}

TRENCH_Z = -0.45        # trench bottom (display units)
NITRIDE_TOP = 0.18      # pad oxide 0.06 + nitride 0.12 -> CMP stop
STI_STEP = 0.05         # final STI step height above silicon


def _iso(c):
    return c.lay["iso"]


STEPS = [
    _L["wafer"],
    _L["padox"],

    replace(_L["nitride"],
            desc=("LPCVD 淀积约 100 nm Si3N4。在 STI 工艺里它有两个作用：刻槽时作硬掩膜，"
                  "CMP 时作抛光停止层 (氮化硅比氧化硅难磨得多)。",
                  "~100 nm LPCVD Si3N4. In an STI flow it is both the hard mask for the trench "
                  "etch and the CMP stop layer (nitride polishes far slower than oxide)."),
            quiz=quiz("STI 工艺中氮化硅的作用是？", "Role of the nitride in an STI flow?",
                      [("刻槽硬掩膜 + CMP 停止层", "Trench hard mask + CMP stop layer"),
                       ("栅介质", "Gate dielectric"), ("金属阻挡层", "Metal barrier"),
                       ("离子注入源", "Implant source")], 0,
                      "氮化硅既保护有源区不被刻槽，又让 CMP 正好停在有源区上方。",
                      "It protects the active area during the trench etch and stops the CMP right above it.")),

    Step("sti_litho", ("有源区光刻 (掩膜 1)", "Active-area lithography (mask 1)"),
         ("涂胶并用 ACTIVE 掩膜曝光、显影。光刻胶留在有源区上，其余场区之后要刻出浅槽。"
          "注意：现代工艺先做隔离、后做阱。",
          "Coat, expose the ACTIVE mask and develop. Resist stays on the active areas; the field "
          "areas will become shallow trenches. Modern flows form isolation before the wells."),
         [("掩膜", "Mask", lambda c: "#1 ACTIVE"),
          ("光源", "Source", lambda c: "KrF 248 nm DUV")],
         litho(actives, mask="ACTIVE"),
         quiz("0.25 µm 节点一般用什么光源？", "Typical exposure source at the 0.25 µm node?",
              [("汞灯 g 线 436 nm", "Hg g-line 436 nm"), ("KrF 准分子激光 248 nm", "KrF excimer 248 nm"),
               ("EUV 13.5 nm", "EUV 13.5 nm"), ("可见光", "Visible light")], 1,
              "分辨率 ∝ λ/NA，0.25 µm 起开始用 248 nm 深紫外。",
              "Resolution scales with λ/NA; 248 nm DUV arrived around 0.25 µm."),
         ("有源区", "ACTIVE")),

    Step("sti_etch", ("硬掩膜刻蚀 + 浅槽刻蚀", "Hard-mask etch + trench etch"),
         ("先刻穿场区的氮化硅和垫氧，去胶后以氮化硅为硬掩膜，用 Cl2/HBr 等离子体各向异性刻蚀硅，"
          "形成约 0.3-0.4 µm 深的浅槽。",
          "Etch the nitride and pad oxide in the field, strip the resist, then use the nitride as "
          "a hard mask to etch ~0.3-0.4 µm deep trenches into silicon with Cl2/HBr plasma."),
         [("硬掩膜刻蚀", "Hard-mask etch", lambda c: "CF4/CHF3 RIE"),
          ("硅槽刻蚀", "Si trench etch", lambda c: "Cl2/HBr/O2 RIE"),
          ("槽深", "Trench depth", lambda c: "≈ 0.35 µm"),
          ("侧壁角", "Sidewall angle", lambda c: "≈ 80-85°")],
         [Phase("刻蚀氮化硅 + 垫氧 (硬掩膜)", "Etch nitride + pad oxide (hard mask)", 1.6,
                [pattern("nitride", actives, mask="ACTIVE"),
                 pattern("padox", actives, particles=False, mask="ACTIVE")]),
          Phase("去除光刻胶", "Strip resist", 0.9, [strip("resist")]),
          Phase("各向异性刻蚀硅槽", "Anisotropic silicon trench etch", 2.2,
                [recess(["sub"], _iso, TRENCH_Z)])],
         quiz("为什么刻硅槽前要先去掉光刻胶，改用氮化硅作掩膜？",
              "Why strip the resist and etch the trench with a nitride hard mask?",
              [("光刻胶在长时间硅刻蚀中会被消耗/污染槽", "Resist erodes and contaminates during the long Si etch"),
               ("光刻胶太贵", "Resist is expensive"), ("氮化硅导电", "Nitride conducts"),
               ("为了好看", "Looks nicer")], 0,
              "硬掩膜选择比高、不产生有机聚合物，槽形更好控制。",
              "A hard mask has high selectivity and no organic residue, giving better trench profiles.")),

    Step("sti_liner", ("衬垫氧化 (Liner)", "Liner oxidation"),
         ("在槽底和槽壁热生长约 10-20 nm 薄氧化层：修复刻蚀损伤、圆化槽角，降低漏电并减轻"
          "角部电场集中 (与窄宽度效应有关)。",
          "A 10-20 nm thermal liner is grown in the trench: it repairs etch damage and rounds "
          "the top corners, reducing leakage and corner field crowding (related to narrow-width effects)."),
         [("温度", "Temperature", lambda c: "1000 °C, 干氧 / dry O2"),
          ("厚度", "Thickness", lambda c: "≈ 15 nm")],
         [Phase("热生长衬垫氧化层", "Grow thermal liner", 1.5,
                [deposit("liner", "liner_ox", thickness=0.04, region=_iso), anneal(1000, 900)])],
         quiz("衬垫氧化的主要作用之一是？", "One main purpose of the liner oxide?",
              [("圆化槽角、修复刻蚀损伤", "Round trench corners and repair etch damage"),
               ("作为栅氧", "Serve as gate oxide"), ("导电", "Conduct current"), ("作 CMP 停止层", "CMP stop")], 0,
              "尖锐槽角会造成电场集中，使窄器件提前开启 (反窄宽度效应)。",
              "Sharp corners crowd the field and turn narrow devices on early (inverse narrow-width effect).")),

    Step("sti_fill", ("HDP 氧化物填充", "HDP oxide gap-fill"),
         ("用高密度等离子体 CVD (HDP-CVD) 淀积厚 SiO2，边淀积边溅射，可无空洞地填满窄而深的槽；"
          "整片晶圆都被氧化物覆盖，表面高低不平。",
          "High-density-plasma CVD deposits thick SiO2 while simultaneously sputtering, filling "
          "narrow trenches without voids. The whole wafer is covered and the surface is uneven."),
         [("方法", "Method", lambda c: "HDP-CVD (SiH4/O2/Ar)"),
          ("厚度", "Thickness", lambda c: "≈ 0.6 µm")],
         [Phase("HDP-CVD 填槽", "HDP-CVD trench fill", 2.0,
                [deposit("sti", "sti_ox", top=0.45, particles=("depo", (0.8, 0.85, 0.95, 1)))])],
         quiz("HDP-CVD 能无空洞填槽的关键是？", "Why can HDP-CVD fill trenches void-free?",
              [("淀积同时有离子溅射削掉槽口", "Simultaneous ion sputtering trims the trench opening"),
               ("温度很高", "Very high temperature"), ("用了液体", "It uses a liquid"),
               ("槽很浅", "The trench is shallow")], 0,
              "溅射把槽口的“屋檐”削掉，避免槽口先封闭留下空洞。",
              "Sputtering removes the overhang so the opening does not pinch off and leave a void.")),

    Step("sti_cmp", ("化学机械抛光 (CMP)", "Chemical-mechanical polishing (CMP)"),
         ("旋转的抛光垫加上含磨粒的碱性浆料，把多余氧化物磨掉。氮化硅磨得很慢，抛光停在氮化硅上，"
          "得到全局平坦的表面。CMP 是 0.35 µm 以下工艺的关键技术。",
          "A rotating pad with an abrasive alkaline slurry removes the excess oxide. Nitride "
          "polishes slowly, so the CMP stops on it, leaving a globally planar surface. CMP is "
          "a key enabler below 0.35 µm."),
         [("浆料", "Slurry", lambda c: "SiO2/CeO2 磨粒, pH≈11"),
          ("选择比 SiO2:Si3N4", "Selectivity SiO2:Si3N4", lambda c: "≈ 4:1 (CeO2 可达 30:1)"),
          ("终点", "Endpoint", lambda c: "电机电流 / 光学 / motor current")],
         [Phase("CMP 抛光，停在氮化硅上", "Polish down, stop on nitride", 2.6,
                [cmp(["sti"], NITRIDE_TOP)])],
         quiz("为什么 STI 必须配合 CMP？", "Why does STI need CMP?",
              [("填槽后表面不平，需要全局平坦化", "Gap-fill leaves topography; global planarity is needed"),
               ("为了掺杂", "For doping"), ("为了退火", "For annealing"), ("去除光刻胶", "To remove resist")], 0,
              "后续光刻景深很小，表面必须足够平；回流或回刻只能做到局部平坦。",
              "Lithography depth of focus is tiny; reflow/etch-back only gives local planarity.")),

    Step("sti_strip", ("去氮化硅 + 去垫氧", "Nitride and pad-oxide strip"),
         ("热磷酸去掉氮化硅，再用 HF 去垫氧；HF 同时把 STI 顶部略微回刻，使其只比硅表面高几十 nm。"
          "与 LOCOS 相比，STI 没有鸟嘴，表面几乎是平的。",
          "Hot H3PO4 removes the nitride; HF removes the pad oxide and slightly recesses the STI so "
          "it stands only tens of nm above silicon. Unlike LOCOS there is no bird's beak."),
         [("Si3N4 去除", "Nitride removal", lambda c: "H3PO4, 160 °C"),
          ("台阶高度", "Step height", lambda c: "≈ 20-50 nm"),
          ("窄宽度效应 ΔVtn", "Narrow-width ΔVtn", nwe_text)],
         [Phase("热磷酸去除 Si3N4", "Hot H3PO4 removes nitride", 1.4, [strip("nitride")]),
          Phase("HF 去垫氧 + STI 回刻", "HF: pad oxide off, STI recessed", 1.4,
                [strip("padox"), cmp(["sti"], STI_STEP, pad=False)])],
         quiz("与 LOCOS 相比，STI 的主要优势是？", "Main advantage of STI over LOCOS?",
              [("无鸟嘴、隔离间距小、表面平坦", "No bird's beak, tighter pitch, planar surface"),
               ("工艺步骤更少", "Fewer steps"), ("不需要掩膜", "No mask needed"), ("更便宜", "Cheaper")], 0,
              "STI 步骤更多，但几乎不侵占有源区，可以把器件排得更密。",
              "STI has more steps but barely encroaches on the active area, allowing denser layout.")),

    replace(_L["nwell_litho"],
            title=("N 阱光刻 (掩膜 2)", "N-well lithography (mask 2)"),
            params=[("光刻胶", "Resist", lambda c: "正胶 / positive, ~1.5 µm (高能注入需厚胶)"),
                    ("光源", "Source", lambda c: "i-line 365 nm"),
                    ("掩膜", "Mask", lambda c: "#2 NWELL")]),

    Step("nwell_implant_he", ("高能 N 阱注入 (倒掺杂阱)", "High-energy n-well implant (retrograde)"),
         ("用 MeV 级高能注入把磷直接打到深处，形成浓度峰在体内的“倒掺杂阱”，再加一次低能注入调节"
          "表面浓度。这样不需要 LOCOS 时代的长时间推阱。",
          "MeV-class implants place phosphorus deep in the silicon, forming a retrograde well "
          "whose peak lies below the surface, plus a shallow implant to set the surface doping. "
          "No long LOCOS-era drive-in is needed."),
         [("离子", "Species", lambda c: "P+ (磷 / phosphorus)"),
          ("剂量", "Dose", lambda c: sci(c.p.nwell_dose_cm2, "cm^-2")),
          ("能量", "Energy", lambda c: "≈ 400 keV - 1 MeV"),
          ("→ PMOS Vtp", "→ PMOS Vtp", lambda c: vt_text(c, "p"))],
         [Phase("高能磷注入", "High-energy phosphorus implant", 2.4,
                [implant("nimp", "n_implant", lambda c: [c.lay["nwell"]], -1.2, (1.0, 0.85, 0.2, 1),
                         species="P", dose=lambda c: c.p.nwell_dose_cm2, energy_kev=600)])],
         quiz("“倒掺杂阱”指的是？", "What is a 'retrograde' well?",
              [("浓度峰值在体内而非表面", "Its peak concentration is below the surface"),
               ("掺杂类型相反", "Opposite doping type"), ("先退火后注入", "Annealed before implant"),
               ("浓度随时间降低", "Doping that decays over time")], 0,
              "体内高浓度可抑制闩锁和穿通，表面低浓度保证低 Vt 和高迁移率。",
              "High buried doping suppresses latch-up and punch-through; low surface doping keeps Vt low.")),

    Step("nwell_anneal", ("去胶 + 阱退火", "Resist strip + well anneal"),
         ("去胶后以较低热预算 (约 1000°C、30 分钟) 退火，激活杂质并修复注入损伤。"
          "热预算小，STI 和浅结都不会被破坏。",
          "Strip the resist and anneal with a modest thermal budget (~1000 °C, 30 min) to "
          "activate dopants and repair damage while protecting the STI and shallow junctions."),
         [("温度", "Temperature", lambda c: "1000 °C, 30 min"),
          ("阱深", "Well depth", lambda c: "≈ 1.5 µm")],
         [Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")]),
          Phase("退火激活", "Activation anneal", 1.8,
                [replace_layer("nwell", "n_well", lambda c: [Solid.box(10.5, 20, 0, 8, -1.8, 0)],
                               anchor=0.0, mode="grow", requires="nimp"),
                 strip("nimp", "fade"),
                 anneal(1000, 1800, (1.0, 0.4, 0.1))])],
         quiz("现代工艺为什么要控制“热预算”？", "Why do modern flows limit the thermal budget?",
              [("防止已形成的浅结和杂质分布继续扩散", "So existing shallow profiles don't diffuse further"),
               ("省电", "Save electricity"), ("防止光刻胶燃烧", "Stop resist burning"),
               ("让晶圆更亮", "Make the wafer shinier")], 0,
              "扩散长度 ∝ √(Dt)，每一次高温都会让之前的杂质分布变宽。",
              "Diffusion length ∝ √(Dt); every hot step broadens earlier dopant profiles.")),

    replace(_L["gate_ox"],
            desc=("在有源区生长薄栅氧。STI 表面与硅几乎齐平，栅氧和多晶硅都落在平坦表面上，"
                  "这让更细的栅线光刻成为可能。",
                  "A thin gate oxide is grown on the active areas. Because the STI is almost flush "
                  "with silicon, gate oxide and poly sit on a flat surface, enabling finer gate lithography.")),
    _L["poly_dep"],
    _L["gate_litho"],
    _L["gate_etch"],
    _L["nplus"],
    _L["pplus"],
    _L["sd_anneal"],

    Step("ild_cmp", ("ILD 淀积 + CMP", "ILD deposition + CMP"),
         ("淀积较厚的掺杂氧化物 (BPSG/PSG) 作为层间介质，然后用 CMP 磨平，取代 LOCOS 时代的高温回流。"
          "平坦的 ILD 让接触孔光刻有足够景深。",
          "A thick doped oxide is deposited as the ILD and then planarised by CMP instead of the "
          "older high-temperature reflow, giving lithography enough depth of focus for contacts."),
         [("材料", "Material", lambda c: "PECVD TEOS / BPSG"),
          ("CMP 后厚度", "Thickness after CMP", lambda c: "≈ 0.8 µm")],
         [Phase("淀积 ILD", "Deposit ILD", 1.6,
                [deposit("ild", "ild", top=1.7, particles=("depo", (0.95, 0.95, 0.8, 1)))]),
          Phase("CMP 平坦化", "CMP planarisation", 2.0, [cmp(["ild"], 1.3)])],
         quiz("ILD 用 CMP 代替 BPSG 回流的好处？", "Benefit of ILD CMP over BPSG reflow?",
              [("全局平坦且热预算低", "Global planarity with a low thermal budget"),
               ("材料更便宜", "Cheaper material"), ("不需要淀积", "No deposition needed"),
               ("可以导电", "It conducts")], 0,
              "回流需要 850°C 以上且只能局部平坦；CMP 在室温下实现全局平坦。",
              "Reflow needs >850 °C and only smooths locally; CMP planarises globally at room temperature.")),

    _L["contact"],
    _L["metal_dep"],
    _L["metal_pattern"],
    _L["done"],
]

REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.2),
    ("nplus", "n+", "n+", 3.2, -0.55),
    ("nplus", "n+", "n+", 7.5, -0.55),
    ("pplus", "p+", "p+", 13.0, -0.55),
    ("pplus", "p+", "p+", 17.3, -0.55),
]

FLOW = Flow(
    key="sti",
    name=("STI + CMP 工艺", "STI + CMP"),
    node=("约 0.25 µm 代：STI 隔离 + CMP + 倒掺杂阱",
          "~0.25 µm era: STI + CMP + retrograde well"),
    steps=STEPS,
    features=frozenset({"sti", "cmp"}),
    region_labels=REGION_LABELS,
    terminal_labels=locos.TERMINAL_LABELS,
)
