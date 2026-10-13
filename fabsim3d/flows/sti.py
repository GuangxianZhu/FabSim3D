"""~0.25 µm CMOS flow: STI + CMP isolation, LDD extensions and sidewall spacers.

New relative to LOCOS: trench etch, liner, HDP fill, CMP, retrograde n-well,
LDD implants, spacer deposition/etch-back, spacer-aligned S/D, ILD CMP.
Gate, contact and metal steps are shared with the LOCOS flow.

【中文说明：这个文件是做什么的】
本文件描述约 0.25 µm 时代 (1990 年代末) 的 CMOS 反相器制造流程。和 locos.py (约 1 µm 代) 相比，
晶体管更小了，于是出现了几项新技术：
  * STI 浅槽隔离：不再用会长“鸟嘴”的 LOCOS，而是在硅里挖浅槽、填满氧化物来隔离晶体管；
  * CMP 化学机械抛光：把填槽后高低不平的表面磨平；
  * 倒掺杂 N 阱：用高能注入直接把杂质打到深处，不再需要几个小时的高温推进；
  * LDD 轻掺杂漏 + 侧墙 (spacer)：在沟道两端先做一段“淡”的延伸区，减轻小尺寸晶体管的毛病；
  * ILD 也用 CMP 磨平。
栅极、接触孔、金属导线这些步骤和 LOCOS 工艺完全一样，所以直接从 locos.py 借用 (见下面的 _L)。

坐标约定和 locos.py 相同：x 左右 (左 NMOS、右 PMOS)，y 伸进屏幕 (剖面沿 y 移动)，
z 向上，硅表面在 z = 0，竖直方向被夸张放大。
"""
# 推迟解析类型提示，技术细节，可忽略。
from __future__ import annotations

# dataclasses.replace(旧对象, 字段=新值, ...)：复制一个对象，只改掉指定的几个字段，其余照旧。
# 本文件用它“借用” LOCOS 工艺的某一步，只改说明文字或测验题，而不必整步重写。
from dataclasses import replace

from ..geometry import Solid
# 从工艺引擎导入要用到的东西。比 locos.py 多出的几样：
#   SPACER_W        侧墙宽度 (显示单位)
#   cmp             化学机械抛光：把某些层高于某个 z 的部分磨掉
#   recess          往已有的实体里“挖下去” (用来刻硅槽)
#   spacer_deposit  保形淀积侧墙薄膜；spacer_etchback 回刻成侧墙
#   spacer_span     “栅 + 两侧侧墙”的 x 范围
from ..process_core import (SPACER_W, Flow, Phase, Step, actives, anneal, cmp, deposit,
                            gate_span, implant, litho, recolor, sd_annealed, sd_rects,
                            spacer_deposit, spacer_etchback, spacer_span,
                            nwe_text, pattern, quiz, recess, replace_layer, sci, strip, summarize_cached,
                            vt_text)
# 导入同一文件夹下的 locos 模块，以便复用它的步骤和标签。
from . import locos

# 把 LOCOS 工艺的所有步骤做成字典：键是步骤名 (如 "padox")，值是那个 Step 对象。
# 这样就能用 _L["padox"] 直接取出 LOCOS 的“垫氧化”步骤。(这是一个“字典推导式”。)
_L = {s.key: s for s in locos.STEPS}

# 几个高度常数 (显示单位，z 方向；硅表面 z = 0)：
TRENCH_Z = -0.45        # trench bottom (display units)
#                         浅槽底部的深度：槽从表面挖到 z = -0.45
NITRIDE_TOP = 0.18      # pad oxide 0.06 + nitride 0.12 -> CMP stop
#                         氮化硅顶面高度 = 垫氧 0.06 + 氮化硅 0.12；CMP 磨到这里就停
STI_STEP = 0.05         # final STI step height above silicon
#                         最后 STI 氧化物只比硅表面高出 0.05 (几乎齐平)


def _iso(c):
    """Isolation (field) regions = everything that is not an active area.

    返回“隔离区” (场区) 的矩形列表：整个区域里除去两个有源区以外的部分。
    浅槽就挖在这些地方。版图里预先算好存在 c.lay["iso"] 里。
    """
    return c.lay["iso"]


# ==========================================================================================
# 工艺步骤清单 (Step 各参数的含义见 locos.py 中 STEPS 上方的说明)
# 注意顺序：现代工艺是“先做隔离 (STI)，后做阱”，和 LOCOS 工艺相反。
# ==========================================================================================
STEPS = [
    # ---- 起始硅片、垫氧化：和 LOCOS 工艺完全相同，直接借用 ----
    _L["wafer"],
    # 垫氧：缓冲后面氮化硅对硅的应力 (理由同 LOCOS 工艺)。
    _L["padox"],

    # ---- 氮化硅淀积：动作和 LOCOS 相同，只换了说明文字和测验 ----
    # 在 STI 工艺里氮化硅身兼两职：
    #   1) 挖槽时当“硬掩膜”，保护有源区的硅不被刻掉；
    #   2) CMP 时当“停止层”：氮化硅比氧化硅难磨得多，抛光到它就基本停下，不会磨伤下面的硅。
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

    # ---- 有源区光刻 (第 1 块掩膜) ----
    # 物理上：光刻胶留在两个有源区 (将来做晶体管的矩形) 上，其余“场区”露出来，之后要挖槽。
    # 为什么先做它：隔离结构决定了每个晶体管的“地盘”，现代工艺把它放在最前面。
    # 3D 模型里：litho 的保留区域 = actives (两个有源区)。lambda 的含义见 locos.py 中的说明。
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

    # ---- 刻硬掩膜 + 挖浅槽 ----
    # 物理上：
    #   1) 先把场区的氮化硅和垫氧刻穿 (只在有源区保留)；
    #   2) 去掉光刻胶；
    #   3) 以剩下的氮化硅为“硬掩膜”，用等离子体垂直向下刻硅，挖出约 0.35 µm 深的浅槽。
    # 为什么：槽将被绝缘的氧化物填满，成为晶体管之间的“沟壕”，比 LOCOS 省地方、没有鸟嘴。
    # 3D 模型里：
    #   pattern(..., actives) 只保留有源区上的氮化硅/垫氧 (垫氧那次不播粒子动画)；
    #   recess(["sub"], _iso, TRENCH_Z)：把衬底层在隔离区 (_iso) 里的部分从顶部削到 z = -0.45，即挖槽。
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

    # ---- 衬垫氧化 (liner) ----
    # 物理上：在槽底和槽壁上热氧化长一层很薄的氧化层。
    # 为什么：等离子体刻蚀会在槽壁留下晶格损伤，会漏电；氧化能修复损伤，并把槽口尖角磨圆一点，
    #   避免尖角处电场过强让窄晶体管提前导通。
    # 3D 模型里：只在隔离区 (region=_iso，即槽里) 淀积 0.04 厚的 "liner" 层。
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

    # ---- HDP 氧化物填槽 ----
    # 物理上：用高密度等离子体 CVD 在整片晶圆上淀积厚厚的二氧化硅，把槽填满。
    # 为什么：槽里填满绝缘体才能隔离晶体管。HDP 一边淀积一边用离子“削”槽口，槽口不会先封死，
    #   所以槽里不会留下空洞。代价是整片晶圆 (包括有源区上方) 都被盖住，表面坑坑洼洼。
    # 3D 模型里：top=0.45 表示把氧化物填到 z = 0.45 的高度 (比氮化硅顶 0.18 还高，下一步要磨掉)。
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

    # ---- CMP 化学机械抛光 ----
    # 物理上：把晶圆压在旋转的抛光垫上，加含磨粒的化学浆料，把高出来的氧化物磨掉。
    # 为什么：有源区上方多余的氧化物必须去掉，而且后面光刻要求表面非常平 (镜头景深很浅)。
    #   磨到氮化硅时速度大大变慢，于是自动停在氮化硅顶面，得到整片平坦的表面。
    # 3D 模型里：cmp(["sti"], NITRIDE_TOP) 把 "sti" 层高于 z = 0.18 的部分全部削平，并显示抛光垫下降的动画。
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

    # ---- 去氮化硅 + 去垫氧 ----
    # 物理上：热磷酸去掉氮化硅；HF 去掉垫氧，同时把槽里氧化物的顶部也溶掉一点。
    # 为什么：硬掩膜/停止层的任务完成，要露出有源区的干净硅；STI 最后只比硅表面略高，几乎是平的。
    # 3D 模型里：两层整层去掉；再用 cmp(["sti"], STI_STEP, pad=False) 把 STI 顶削到 z = 0.05。
    #   这里借用 cmp 函数做“削平”，但 pad=False 表示不显示抛光垫 (实际是 HF 湿法回刻，不是抛光)。
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

    # ---- N 阱光刻 (第 2 块掩膜) ----
    # 借用 LOCOS 的 N 阱光刻：光刻胶盖住左边 NMOS 区，打开右边将来做 N 阱 (放 PMOS) 的区域。
    # 只改了标题 (这里是第 2 块掩膜) 和参数表：下一步是高能注入，离子能穿得更深，所以光刻胶要更厚才挡得住。
    replace(_L["nwell_litho"],
            title=("N 阱光刻 (掩膜 2)", "N-well lithography (mask 2)"),
            params=[("光刻胶", "Resist", lambda c: "正胶 / positive, ~1.5 µm (高能注入需厚胶)"),
                    ("光源", "Source", lambda c: "i-line 365 nm"),
                    ("掩膜", "Mask", lambda c: "#2 NWELL")]),

    # ---- 高能 N 阱注入 (倒掺杂阱) ----
    # 物理上：用很高的能量 (几百 keV 到 1 MeV) 把磷离子直接打到硅的深处。
    # 为什么：这样不用像 LOCOS 时代那样在 1100°C 下推进好几个小时；而且浓度峰值在深处、表面较淡
    #   (“倒掺杂”)：深处浓可以防止闩锁和穿通，表面淡让 PMOS 阈值低、载流子跑得快。
    #   剂量仍是用户可调参数，决定 PMOS 阈值电压 Vtp。
    # 3D 模型里：注入层一开始就深到 z = -1.2 (LOCOS 那一步只有 -0.3)，表示离子打得很深。
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

    # ---- 去胶 + 阱退火 ----
    # 物理上：去掉光刻胶，再在 1000°C 下只加热 30 分钟 (远少于 LOCOS 时代的 1100°C、6 小时)。
    # 为什么：只需激活杂质、修复注入损伤，不需要再让杂质长距离扩散；热预算小，已经做好的 STI 不受影响。
    # 3D 模型里：和 LOCOS 的推进步骤一样，出现深到 z = -1.8 的 N 阱 (x 10.5-20)，原注入层淡出。
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

    # ---- 栅氧化：动作同 LOCOS，只换说明 ----
    # 在有源区长薄栅氧 (栅极和沟道之间的绝缘层)。STI 表面平整，后面的细栅线更容易光刻。
    replace(_L["gate_ox"],
            desc=("在有源区生长薄栅氧。STI 表面与硅几乎齐平，栅氧和多晶硅都落在平坦表面上，"
                  "这让更细的栅线光刻成为可能。",
                  "A thin gate oxide is grown on the active areas. Because the STI is almost flush "
                  "with silicon, gate oxide and poly sit on a flat surface, enabling finer gate lithography.")),
    # ---- 多晶硅淀积、栅光刻、栅刻蚀：与 LOCOS 完全相同 ----
    # 结果：NMOS 和 PMOS 各有一根多晶硅栅极，栅下面保留栅氧。
    _L["poly_dep"],
    _L["gate_litho"],
    _L["gate_etch"],

    # ---- N- LDD 注入 (第 4 块掩膜) ----
    # 物理上：光刻胶盖住 PMOS 区，向 NMOS 区做一次低剂量、低能量的注入，在栅两侧形成又浅又淡的 N- 区。
    # 为什么：晶体管小了以后，漏极附近的电场非常强，会把电子加速成“热载流子”撞坏栅氧，
    #   并让晶体管更难关断 (短沟道效应)。在沟道和浓源漏之间加一段“淡”的缓冲区 (LDD)，电场就缓和了。
    #   这一步仍以栅极为模板，与栅自对准。
    # 3D 模型里：注入区域 = NMOS 栅两侧的矩形；深度只有 z = -0.12 (比 N+ 的 -0.3 浅得多)。
    Step("nldd", ("N- LDD 注入 (掩膜 4)", "n- LDD implant (mask 4)"),
         ("光刻胶盖住 PMOS 区，以多晶硅栅为掩膜做一次低剂量、低能量的磷/砷注入，在栅边形成浅而淡的"
          "N- 延伸区 (轻掺杂漏 LDD)。它降低了漏端电场，从而抑制热载流子注入和短沟道效应。",
          "With resist over the PMOS, a low-dose, low-energy implant self-aligned to the poly gate "
          "forms shallow, lightly doped n- extensions (LDD). They soften the drain field, "
          "reducing hot-carrier injection and short-channel effects."),
         [("离子", "Species", lambda c: "P+ / As+"),
          ("剂量", "Dose", lambda c: "≈ 2e13 cm^-2 (约为 N+ 的 1/200)"),
          ("能量", "Energy", lambda c: "≈ 20 keV"),
          ("结深 xj", "Junction depth xj", lambda c: "≈ 80 nm")],
         litho(lambda c: [c.lay["nwell"]], mask="NSELECT") + [
             Phase("低剂量 LDD 注入 (自对准栅极)", "Low-dose LDD implant (gate-aligned)", 2.0,
                   [implant("nldd", "n_ldd", lambda c: sd_rects(c.lay["act_n"], gate_span(c, "gn")), -0.12,
                            (1.0, 0.6, 0.6, 1), species="P", dose=2e13, energy_kev=20)]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("LDD 的主要作用是？", "Main purpose of the LDD?",
              [("降低漏端峰值电场，抑制热载流子", "Lower the peak drain field, suppress hot carriers"),
               ("提高源漏导电性", "Make S/D more conductive"), ("作为栅介质", "Act as gate dielectric"),
               ("隔离器件", "Isolate devices")], 0,
              "淡掺杂区让漏端电势变化更平缓，峰值电场下降，代价是多了一段串联电阻。",
              "The lightly doped region spreads the drain potential drop; the price is extra series resistance."),
         ("N+ 选择", "NSELECT")),

    # ---- P- LDD 注入 (第 5 块掩膜) ----
    # 和上一步对称：光刻胶盖住 NMOS，给 PMOS 两侧做浅而淡的 P- 区 (用 BF2，它比单个硼原子重，打得更浅)。
    # 3D 模型里：注入区域 = PMOS 栅两侧，深度 z = -0.12。
    Step("pldd", ("P- LDD 注入 (掩膜 5)", "p- LDD implant (mask 5)"),
         ("光刻胶盖住 NMOS 区，对 PMOS 做低能 BF2 注入形成 P- 延伸区。BF2 分子较重，注入更浅。",
          "With resist over the NMOS, a low-energy BF2 implant forms the p- extensions. The heavy "
          "BF2 molecule gives an even shallower profile."),
         [("离子", "Species", lambda c: "BF2+"),
          ("剂量", "Dose", lambda c: "≈ 2e13 cm^-2"),
          ("能量", "Energy", lambda c: "≈ 15 keV")],
         litho(lambda c: [c.lay["pside"]], mask="PSELECT") + [
             Phase("低剂量 LDD 注入 (自对准栅极)", "Low-dose LDD implant (gate-aligned)", 2.0,
                   [implant("pldd", "p_ldd", lambda c: sd_rects(c.lay["act_p"], gate_span(c, "gp")), -0.12,
                            (0.55, 0.7, 1.0, 1), species="BF2", dose=2e13, energy_kev=15)]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("为什么 PMOS 常用 BF2 而不是 B 做浅注入？", "Why use BF2 rather than B for shallow p-type implants?",
              [("BF2 质量大，同能量下射程更浅", "BF2 is heavier, so it stops shallower at the same energy"),
               ("BF2 更便宜", "BF2 is cheaper"), ("B 是 N 型杂质", "B is n-type"), ("BF2 不需要退火", "BF2 needs no anneal")], 0,
              "硼原子很轻、射程长；BF2 分子把能量分给 F 原子，硼的有效能量只有约 22%。",
              "Boron is light and travels far; in BF2 the B atom carries only ~22% of the energy."),
         ("P+ 选择", "PSELECT")),

    # ---- 侧墙介质淀积 ----
    # 物理上：保形 (“贴着形状”) 地淀积一层氮化硅或氧化硅，栅极顶部、侧壁、硅表面都盖上同样厚的一层。
    # 为什么：为下一步做“侧墙”准备。栅极两侧竖直方向的薄膜特别“高”，回刻后能留下来。
    # 3D 模型里：spacer_deposit() 生成一层平铺的薄膜 + 紧贴每根栅两侧、宽 SPACER_W 的竖直膜块。
    Step("spacer_dep", ("侧墙介质淀积", "Spacer dielectric deposition"),
         ("用 LPCVD 保形淀积一层 Si3N4 (或 TEOS 氧化物)。保形淀积意味着栅极侧壁上也覆盖了同样厚度的薄膜，"
          "栅边的竖直方向厚度最大。",
          "A conformal LPCVD Si3N4 (or TEOS oxide) film is deposited. Being conformal, it coats "
          "the gate sidewalls too, so the vertical thickness is largest right next to the gate."),
         [("材料", "Material", lambda c: "Si3N4 / TEOS"),
          ("厚度", "Thickness", lambda c: "≈ 80-100 nm"),
          ("方法", "Method", lambda c: "LPCVD 700-780 °C")],
         [Phase("保形淀积侧墙介质", "Conformal spacer film", 1.8, [spacer_deposit()])],
         quiz("为什么侧墙介质必须是“保形”淀积？", "Why must the spacer film be conformal?",
              [("这样栅侧壁上才有足够厚度，回刻后留下侧墙", "So the sidewalls get coated and a spacer remains after etch-back"),
               ("为了导电", "To conduct"), ("为了更快", "To go faster"), ("为了透明", "To be transparent")], 0,
              "各向异性回刻按竖直厚度去除；栅边竖直方向最厚，刚好留下来。",
              "The anisotropic etch removes a fixed vertical thickness; the film beside the gate is tallest and survives.")),

    # ---- 侧墙回刻 ----
    # 物理上：不用光刻掩膜，直接对整片晶圆做垂直向下的等离子体刻蚀，刻掉“一层膜的厚度”。
    #   平面上的薄膜被刻光，而栅两侧竖直方向很“高”的部分刻不完，留下圆弧形的“侧墙”。
    # 为什么先做侧墙、再做重掺杂源漏：侧墙像一块“垫片”，把下一步的浓源漏注入推离沟道一个侧墙宽度，
    #   这段距离里保留刚才做的淡 LDD 区。如果先做浓注入，LDD 就被覆盖掉、白做了。
    # 3D 模型里：spacer_etchback() 去掉平面薄膜，在每根栅两侧留下圆弧形侧墙实体。
    Step("spacer_etch", ("侧墙回刻", "Spacer etch-back"),
         ("不用掩膜，直接各向异性干法刻蚀整片晶圆。平面上的薄膜被刻掉，栅极两侧留下圆弧形的侧墙。"
          "侧墙宽度决定了后面重掺杂源漏离沟道有多远，也就是 LDD 区的长度。",
          "A maskless anisotropic etch clears the film from flat surfaces, leaving rounded spacers "
          "on both sides of each gate. The spacer width sets how far the heavy S/D implant stays "
          "from the channel, i.e. the LDD length."),
         [("刻蚀", "Etch", lambda c: "RIE CF4/CHF3, 无掩膜 / maskless"),
          ("侧墙宽度", "Spacer width", lambda c: "≈ 80 nm"),
          ("过刻", "Over-etch", lambda c: "≈ 10-20 %")],
         [Phase("各向异性回刻，形成侧墙", "Anisotropic etch-back forms spacers", 2.2, [spacer_etchback()])],
         quiz("侧墙回刻为什么不需要光刻掩膜？", "Why does the spacer etch-back need no mask?",
              [("利用栅极台阶和各向异性刻蚀自对准形成", "Gate topography + anisotropic etch make it self-aligned"),
               ("掩膜太贵", "Masks are too expensive"), ("侧墙会自己长出来", "Spacers grow by themselves"),
               ("用了湿法", "It is a wet etch")], 0,
              "这是又一个自对准结构：形状完全由栅极决定。",
              "Another self-aligned structure: its shape is set entirely by the gate.")),

    # ---- N+ 源漏注入 (以侧墙对准) ----
    # 物理上：光刻胶盖住 PMOS，向 NMOS 做大剂量砷注入。这次挡住离子的是“栅 + 两侧侧墙”。
    # 为什么：浓而深的 N+ 区负责低电阻地连接金属；它离沟道有一个侧墙宽度，中间留下淡的 LDD。
    #   顺带把 NMOS 的多晶硅栅掺成 N+。
    # 3D 模型里：和 LOCOS 的 N+ 注入相比，唯一区别是用 spacer_span (栅 + 侧墙的 x 范围) 代替 gate_span，
    #   所以注入矩形离栅边多退了一个 SPACER_W。
    Step("nplus_sp", ("N+ 源漏注入 (以侧墙对准)", "n+ S/D implant (spacer-aligned)"),
         ("再次用 N+ 选择掩膜，做高剂量砷注入。这次挡住注入的是“栅 + 侧墙”，所以深而浓的 N+ 区离沟道有一段距离，"
          "中间留下 LDD 区。",
          "Using the NSELECT mask again, a high-dose arsenic implant is blocked by gate + spacers, "
          "so the deep n+ region sits back from the channel and the LDD remains in between."),
         [("离子", "Species", lambda c: "As+"),
          ("剂量", "Dose", lambda c: "5e15 cm^-2"),
          ("能量", "Energy", lambda c: "≈ 40 keV")],
         litho(lambda c: [c.lay["nwell"]], mask="NSELECT") + [
             Phase("砷离子注入 (以侧墙为掩膜)", "Arsenic implant (spacer-masked)", 2.2,
                   [implant("nplus", "n_plus", lambda c: sd_rects(c.lay["act_n"], spacer_span(c, "gn")), -0.3,
                            (1.0, 0.35, 0.3, 1), species="As", dose=5e15, energy_kev=40),
                    recolor("gate_n", "poly_n")]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("加了侧墙之后，N+ 注入的边界由什么决定？", "With spacers, what defines the n+ implant edge?",
              [("侧墙外边缘", "The outer spacer edge"), ("栅极边缘", "The gate edge"),
               ("有源区边缘", "The active-area edge"), ("接触孔", "The contact hole")], 0,
              "栅 + 侧墙一起当掩膜，N+ 与沟道之间相隔一个侧墙宽度。",
              "Gate plus spacers mask the implant, so n+ is one spacer width away from the channel."),
         ("N+ 选择", "NSELECT")),

    # ---- P+ 源漏注入 (以侧墙对准) ----
    # 和上一步对称：光刻胶盖住 NMOS，给 PMOS 做大剂量 BF2 注入，同样以“栅 + 侧墙”对准；PMOS 栅变成 P+。
    Step("pplus_sp", ("P+ 源漏注入 (以侧墙对准)", "p+ S/D implant (spacer-aligned)"),
         ("光刻胶盖住 NMOS，对 PMOS 做高剂量 BF2 注入，同样以栅 + 侧墙对准。",
          "With resist over the NMOS, a high-dose BF2 implant into the PMOS, again aligned to gate + spacers."),
         [("离子", "Species", lambda c: "BF2+"),
          ("剂量", "Dose", lambda c: "3e15 cm^-2"),
          ("能量", "Energy", lambda c: "≈ 30 keV")],
         litho(lambda c: [c.lay["pside"]], mask="PSELECT") + [
             Phase("硼离子注入 (以侧墙为掩膜)", "Boron implant (spacer-masked)", 2.2,
                   [implant("pplus", "p_plus", lambda c: sd_rects(c.lay["act_p"], spacer_span(c, "gp")), -0.3,
                            (0.4, 0.6, 1.0, 1), species="BF2", dose=3e15, energy_kev=30),
                    recolor("gate_p", "poly_p")]),
             Phase("去除光刻胶", "Strip resist", 1.0, [strip("resist")])],
         quiz("LDD 结构的代价是什么？", "What is the cost of the LDD structure?",
              [("增加源漏串联电阻，驱动电流略降", "Extra S/D series resistance, slightly less drive"),
               ("栅氧变厚", "Thicker gate oxide"), ("Vt 变成负值", "Vt goes negative"), ("无法做 PMOS", "No PMOS possible")], 0,
              "淡掺杂区电阻较高；后来用硅化物 (Salicide) 降低源漏电阻来弥补。",
              "The light region is resistive; later silicide (salicide) was added to win it back."),
         ("P+ 选择", "PSELECT")),

    # ---- 源漏激活退火 (RTA) ----
    # 物理上：几秒钟的快速高温退火，一次激活所有注入 (LDD 和 N+/P+)。
    # 为什么：杂质要加热才能“上岗”导电；时间很短，杂质只稍微扩散：LDD 钻到栅下一点点 (让沟道接上)，
    #   深源漏钻到侧墙下面。最终沟道两端是“浅而淡的 LDD + 深而浓的源漏”台阶形结构。
    # 3D 模型里：sd_annealed(有源区, x范围, 横向扩展量, 深度) 生成退火后的形状：
    #   LDD：以栅为界，向栅下伸 0.06，深到 z = -0.15；
    #   N+/P+：以“栅 + 侧墙”为界，向内伸 0.1，深到 z = -0.4。
    #   每个 replace_layer 都带 requires，没做过相应注入就不会凭空出现。
    #   参数表显示 DIBL (漏极电压对阈值的影响，越小越好)，用来体会 LDD 对短沟道效应的改善。
    Step("sd_anneal_ldd", ("源漏激活退火 (RTA)", "Source/drain activation anneal (RTA)"),
         ("快速热退火激活所有注入。LDD 略微扩散到栅下形成交叠，深 N+/P+ 区扩散到侧墙下方，"
          "最终在沟道两端形成“浅 LDD + 深源漏”的阶梯结构。",
          "RTA activates all implants. The LDD diffuses slightly under the gate for overlap and the "
          "deep n+/p+ reaches under the spacers, giving the stepped 'shallow LDD + deep S/D' profile."),
         [("方法", "Method", lambda c: "RTA 1000 °C, 10 s"),
          ("LDD 结深", "LDD depth", lambda c: "≈ 80 nm"),
          ("源漏结深", "S/D depth", lambda c: "≈ 0.15 µm"),
          ("→ DIBL (NMOS)", "→ DIBL (NMOS)", lambda c: f"{summarize_cached(c.p, c.features).dibl_n:.0f} mV/V")],
         [Phase("快速热退火：激活 + 扩散", "RTA: activation + diffusion", 2.0,
                [replace_layer("nldd", "n_ldd", lambda c: sd_annealed(c.lay["act_n"], gate_span(c, "gn"), 0.06, -0.15),
                               requires="nldd"),
                 replace_layer("pldd", "p_ldd", lambda c: sd_annealed(c.lay["act_p"], gate_span(c, "gp"), 0.06, -0.15),
                               requires="pldd"),
                 replace_layer("nplus", "n_plus", lambda c: sd_annealed(c.lay["act_n"], spacer_span(c, "gn"), 0.1, -0.4),
                               requires="nplus"),
                 replace_layer("pplus", "p_plus", lambda c: sd_annealed(c.lay["act_p"], spacer_span(c, "gp"), 0.1, -0.4),
                               requires="pplus"),
                 anneal(1000, 10, (1.0, 0.35, 0.1))])],
         quiz("LDD 让短沟道效应变弱，主要是因为？", "LDD weakens short-channel effects mainly because…",
              [("沟道两端的结更浅，漏端对沟道的控制变弱", "Shallower junctions at the channel ends weaken drain control"),
               ("栅氧更厚", "Thicker oxide"), ("沟道更长", "A longer channel"), ("温度更低", "Lower temperature")], 0,
              "结深 xj 越浅，电荷分享和 DIBL 越小。可在“电学特性 → Vt-L”图上对比。",
              "Smaller xj means less charge sharing and DIBL; compare on the Electrical → Vt-L plot.")),

    # ---- ILD 淀积 + CMP ----
    # 物理上：淀积厚厚的绝缘氧化物 (层间介质 ILD)，再用 CMP 磨平。
    # 为什么：ILD 把晶体管和上面的金属导线隔开；用 CMP 而不是高温回流来变平，表面更平且不用再加热
    #   (加热会让刚做好的浅结继续扩散)。
    # 3D 模型里：先填到 z = 1.7，再磨到 z = 1.3 (与 LOCOS 工艺 ILD 顶面相同，后面的接触孔/金属步骤可通用)。
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

    # ---- 接触孔、铝淀积、铝刻蚀、完成：与 LOCOS 工艺完全相同 ----
    # 在 ILD 上打孔 → 铺铝 → 刻成 GND/VDD/Vin/Vout 四根导线 → 合金退火，反相器完成。
    _L["contact"],
    _L["metal_dep"],
    _L["metal_pattern"],
    _L["done"],
]

# 3D 画面里的区域文字标签：(所属层名, 中文, 英文, x 位置, z 位置)，该层存在时才显示。
# 与 LOCOS 相比，“场氧”标签换成了 "STI"，位置放在两管之间的槽里 (z = -0.2，在硅表面以下)。
REGION_LABELS = [
    ("sub", "P 型衬底", "p-sub", 1.4, -2.4),
    ("nwell", "N 阱", "N-well", 19.0, -1.3),
    ("sti", "STI", "STI", 10.25, -0.2),
    ("nplus", "n+", "n+", 3.2, -0.55),
    ("nplus", "n+", "n+", 7.5, -0.55),
    ("pplus", "p+", "p+", 13.0, -0.55),
    ("pplus", "p+", "p+", 17.3, -0.55),
]

# 打包成完整的工艺流程对象，供 flows/__init__.py 登记。
FLOW = Flow(
    key="sti",
    name=("STI + CMP 工艺", "STI + CMP"),
    node=("约 0.25 µm 代：STI + CMP + LDD 侧墙",
          "~0.25 µm era: STI + CMP + LDD spacers"),
    steps=STEPS,
    # 特性标签：告诉器件物理模型这一代用了 STI、CMP、LDD，并计算短沟道效应 (sce)。
    features=frozenset({"sti", "cmp", "ldd", "sce"}),
    region_labels=REGION_LABELS,
    # 导线标签位置与 LOCOS 工艺相同，直接借用。
    terminal_labels=locos.TERMINAL_LABELS,
    # 这一代的典型参数：栅氧 5 nm、衬底掺杂 6e17、N 阱剂量 1.2e14、栅长 0.25 µm、Wn 1 µm、Wp 2.5 µm、
    # 电源 2.5 V、负载 20 fF；mu_n / mu_p 是电子/空穴迁移率 (cm²/V·s)，衬底更浓时迁移率更低。
    defaults=dict(tox_nm=5.0, na_cm3=6e17, nwell_dose_cm2=1.2e14, l_um=0.25, wn_um=1.0, wp_um=2.5,
                  vdd=2.5, cload_ff=20.0, mu_n=300.0, mu_p=120.0),
)
