"""材料表：每种材料的颜色、中英文名字、绘制优先级，以及“它是干什么用的”。

Material colours, names, draw priority and a one-line "what is it for".

整个程序里凡是要画一块材料（衬底、氧化层、金属……），都先到这里查它的颜色；
鼠标悬停提示框和右侧图例里显示的名字、用途说明也来自这里。
想改某种材料的颜色或说明，只改这一个文件就行。
"""
# dataclass 是 Python 自带的一个小工具：写一个类，只列出“有哪些字段”，
# Python 会自动帮我们生成创建对象的代码，省得手写一大堆赋值。
from dataclasses import dataclass


# frozen=True 表示对象创建后不能再修改，材料表是固定不变的，这样更安全。
@dataclass(frozen=True)
class Material:
    key: str              # 程序内部用的短名字，例如 "p_sub"，别的代码靠它查材料
    color: tuple          # 颜色 (红, 绿, 蓝, 不透明度)，每个数都在 0..1 之间；不透明度 < 1 就是半透明
    zh: str               # 中文名
    en: str               # 英文名
    priority: int = 0     # 两块材料的表面正好重合时谁的颜色露出来：数字大的赢（rgba 0..1 / depth offset）
    legend: bool = True   # 是否显示在右侧“图例”里（仿真用的反型层不显示）
    role_zh: str = ""     # 中文：这种材料在芯片里起什么作用（悬停提示框里显示）
    role_en: str = ""     # English: what the material is for (shown in the hover tooltip)


# 下面这张大表就是全部材料。每一行的写法：
#   Material(内部名, 颜色, 中文名, 英文名, 优先级, [是否进图例,] role_zh=用途, role_en=用途)
# 排列顺序大致就是工艺里出现的先后顺序：先是硅片本身，然后隔离、栅极、源漏，最后是金属导线。
_M = [
    # ---------------- 地基：硅片和阱 ----------------
    Material("p_sub", (0.45, 0.86, 0.95, 1), "P 型硅衬底", "p-type Si substrate", 0,
             role_zh="整颗芯片的地基。掺了少量硼的硅，里面可以自由移动的主要是“空穴”；"
                     "NMOS 晶体管就直接做在它上面。",
             role_en="The foundation of the whole chip: silicon lightly doped with boron. "
                     "NMOS transistors are built directly in it."),
    Material("n_implant", (0.95, 0.80, 0.35, 1), "磷注入层(未推进)", "P implant (as-implanted)", 2,
             role_zh="刚用离子注入打进硅里的磷原子，还挤在表面很薄的一层。"
                     "下一步高温“推进”后它会向深处扩散，变成 N 阱。",
             role_en="Phosphorus atoms just shot into the surface. A high-temperature drive-in "
                     "spreads them deeper to form the N-well."),
    Material("n_well", (0.98, 0.88, 0.50, 1), "N 阱", "N-well", 1,
             role_zh="在 P 型衬底里“挖”出的一块 N 型区域。PMOS 必须做在 N 型硅上，"
                     "所以要先做阱，NMOS 和 PMOS 才能做在同一块硅片上（这就是 CMOS 里的 C）。",
             role_en="An n-type pocket inside the p-type wafer. PMOS needs n-type silicon, so the well "
                     "lets NMOS and PMOS share one wafer (the 'C' in CMOS)."),

    # ---------------- 隔离：把相邻的晶体管隔开 ----------------
    Material("pad_ox", (0.80, 0.80, 0.82, 1), "垫氧化层 SiO2", "Pad oxide SiO2", 3,
             role_zh="一层很薄的二氧化硅“缓冲垫”。氮化硅直接压在硅上应力太大，会把硅表面压出缺陷，"
                     "所以中间先垫一层。",
             role_en="A thin SiO2 cushion: nitride straight on silicon is so stressed it damages the "
                     "surface, so this buffer goes in between."),
    Material("nitride", (0.30, 0.70, 0.40, 1), "氮化硅 Si3N4", "Silicon nitride Si3N4", 3,
             role_zh="坚硬的氮化硅，在这里当“盖子”：被它盖住的地方不会被氧化（LOCOS），"
                     "化学机械抛光磨到它就停下（STI）。用完就去掉。",
             role_en="Hard nitride used as a lid: it blocks oxidation (LOCOS) and is the stop layer "
                     "for polishing (STI). Removed afterwards."),
    Material("resist", (0.45, 0.10, 0.45, 1), "光刻胶", "Photoresist", 4,
             role_zh="光刻胶，像照相底片：透过掩膜曝光、显影后留下图形。"
                     "有胶的地方被保护，没胶的地方才会被刻蚀或注入。用完洗掉。",
             role_en="Light-sensitive film, like photo film. After exposure and development it "
                     "protects some areas so etching or implanting only hits the open ones."),
    Material("resist_exp", (0.85, 0.55, 0.90, 1), "已曝光光刻胶", "Exposed resist", 4,
             role_zh="刚被紫外光照过的那部分光刻胶，性质变了，显影时会被洗掉，露出下面的材料。",
             role_en="Resist that has just been hit by UV light; the developer washes it away."),
    Material("fox", (0.62, 0.62, 0.66, 1), "场氧化层 (LOCOS)", "Field oxide (LOCOS)", 4,
             role_zh="很厚的二氧化硅“围墙”，把相邻的晶体管电隔离开，防止电流从一个管子漏到另一个。"
                     "老工艺用局部氧化（LOCOS）长出来，边缘会形成“鸟嘴”。",
             role_en="Thick oxide walls that electrically isolate neighbouring transistors. Grown by "
                     "local oxidation; its edges form the 'bird's beak'."),
    Material("sti_ox", (0.70, 0.74, 0.82, 1), "STI 填充氧化物 (HDP)", "STI fill oxide (HDP)", 4,
             role_zh="填进浅沟槽里的二氧化硅，作用和场氧一样：隔离相邻晶体管。"
                     "但它是先挖槽再填满，占地更小、表面更平，0.25 µm 以后都用它。",
             role_en="Oxide filling shallow trenches. Same job as field oxide (isolation) but smaller "
                     "and flatter; used from 0.25 µm on."),
    Material("liner_ox", (0.88, 0.88, 0.92, 1), "衬垫氧化层", "Liner oxide", 5,
             role_zh="沟槽挖好后先在槽壁上长的一层薄氧化层：修复刻蚀造成的损伤、把尖角变圆，"
                     "减少漏电。",
             role_en="Thin oxide grown on the trench walls first: heals etch damage and rounds the "
                     "corners to cut leakage."),

    # ---------------- 栅极：晶体管的“开关把手” ----------------
    Material("gate_ox", (0.92, 0.92, 0.95, 1), "栅氧化层", "Gate oxide", 4,
             role_zh="栅极下面极薄的绝缘层。栅极电压隔着它把电荷“吸”到硅表面形成沟道，"
                     "但电流本身不能穿过它。越薄，栅极的控制力越强。",
             role_en="Very thin insulator under the gate. The gate voltage pulls charge to the surface "
                     "through it without current flowing; thinner means stronger control."),
    Material("poly", (0.80, 0.45, 0.35, 1), "多晶硅", "Polysilicon", 5,
             role_zh="多晶硅，用来做栅极的导电材料。栅极加电压就能打开或关断下面的沟道。",
             role_en="Polycrystalline silicon, the conductor the gate is made of."),
    Material("poly_n", (0.85, 0.30, 0.30, 1), "N+ 多晶硅栅", "n+ poly gate", 5,
             role_zh="掺了大量磷的多晶硅栅，用在 NMOS 上。栅的掺杂类型会影响晶体管在多大电压下打开（阈值电压）。",
             role_en="Heavily n-doped poly gate for the NMOS; the doping sets the threshold voltage."),
    Material("poly_p", (0.40, 0.45, 0.90, 1), "P+ 多晶硅栅", "p+ poly gate", 5,
             role_zh="掺了大量硼的多晶硅栅，用在 PMOS 上，作用同 N+ 多晶硅栅。",
             role_en="Heavily p-doped poly gate for the PMOS."),

    # ---------------- 源和漏：电流的入口和出口 ----------------
    Material("n_ldd", (0.98, 0.55, 0.55, 1), "N- LDD 轻掺杂漏", "n- LDD extension", 2,
             role_zh="紧挨着沟道的一小段浅而淡的 N 型区。它让漏极附近的电场变缓，"
                     "减少高速电子撞坏栅氧（热载流子效应）。",
             role_en="A shallow, light n-region right next to the channel. It softens the electric field "
                     "near the drain so fast electrons do not damage the gate oxide."),
    Material("p_ldd", (0.55, 0.65, 1.00, 1), "P- LDD 轻掺杂漏", "p- LDD extension", 2,
             role_zh="PMOS 的轻掺杂漏，作用同 N- LDD。",
             role_en="The PMOS version of the LDD extension."),
    Material("spacer", (0.45, 0.80, 0.58, 1), "Si3N4 侧墙", "Si3N4 sidewall spacer", 6,
             role_zh="贴在栅极两侧的氮化硅“小墙”。后面的重掺杂注入会被它挡住，"
                     "于是重掺杂区自动离沟道远一点，中间留出 LDD（不用额外掩膜，叫“自对准”）。",
             role_en="Nitride walls on both sides of the gate. They block the heavy S/D implant so it "
                     "lands a little away from the channel, leaving room for the LDD (self-aligned)."),
    Material("n_plus", (0.92, 0.20, 0.20, 1), "N+ 源/漏", "n+ source/drain", 3,
             role_zh="重掺杂的 N 型区：NMOS 的源极和漏极。电子从源极进、经沟道、从漏极出。",
             role_en="Heavily doped n-regions: the NMOS source and drain, where current enters and leaves."),
    Material("p_plus", (0.25, 0.35, 0.95, 1), "P+ 源/漏", "p+ source/drain", 3,
             role_zh="重掺杂的 P 型区：PMOS 的源极和漏极，这里流动的是空穴。",
             role_en="Heavily doped p-regions: the PMOS source and drain (holes carry the current)."),

    # ---------------- 连线：把晶体管接成电路 ----------------
    Material("ild", (0.80, 0.90, 0.95, 0.30), "层间介质 (BPSG)", "Inter-layer dielectric (BPSG)", 6,
             role_zh="盖在晶体管上面的绝缘层，把下面的器件和上面的金属线隔开，"
                     "只有在开了接触孔的地方才连通。画成半透明是为了能看到下面。",
             role_en="Insulating blanket between the transistors and the metal above; they only connect "
                     "where contact holes are opened. Drawn see-through."),
    Material("metal", (0.70, 0.72, 0.78, 1), "铝金属层", "Aluminium metal", 7,
             role_zh="铝导线，把晶体管和电源 VDD、地 GND、输入、输出连起来，组成反相器电路。",
             role_en="Aluminium wires connecting the transistors to VDD, GND, input and output."),

    # ---------------- 先进工艺（HKMG / FinFET / GAA / CFET）新增的材料 ----------------
    Material("poly_dummy", (0.80, 0.55, 0.45, 1), "伪栅多晶硅 (之后去除)", "Dummy poly gate (removed later)", 5,
             role_zh="先放一个“假”的多晶硅栅占住位置，等高温步骤都做完再把它挖掉，换成真正的金属栅"
                     "（后栅工艺）。因为金属栅怕高温。",
             role_en="A placeholder gate. After all hot steps are done it is dug out and replaced by the "
                     "real metal gate, which cannot take the heat (gate-last)."),
    Material("ild_ox", (0.80, 0.90, 0.95, 0.30), "层间介质 (SiO2)", "Inter-layer dielectric (SiO2)", 6,
             role_zh="二氧化硅绝缘层，把器件和上面的导线隔开，只在接触孔处连通。画成半透明。",
             role_en="Oxide blanket isolating devices from the wiring above, except at contacts."),
    Material("nickel", (0.78, 0.80, 0.82, 1), "镍 (Ni)", "Nickel (Ni)", 6,
             role_zh="镀上去的一层镍。加热后和下面的硅反应生成导电很好的硅化物，没反应的镍再洗掉。",
             role_en="Nickel film: heated, it reacts with the silicon below into silicide; the rest is "
                     "washed off."),
    Material("si_fin", (0.55, 0.90, 0.98, 1), "硅鳍 / 纳米片 (沟道)", "Si fin / nanosheet (channel)", 1,
             role_zh="电流真正流过的硅（沟道）。做成立起来的“鳍”或叠起来的薄片，"
                     "让栅极能从三面甚至四面包住它，晶体管更小也关得住。",
             role_en="The silicon the current actually flows through, shaped as an upright fin or stacked "
                     "sheets so the gate can wrap it on three or four sides."),
    Material("sige", (0.95, 0.62, 0.78, 1), "SiGe 牺牲层", "SiGe sacrificial layer", 2,
             role_zh="和硅交替堆叠的锗硅层，只是临时“占位”：最后被选择性刻掉，"
                     "让硅纳米片悬空，栅极才能把每一片都包住。",
             role_en="SiGe layers stacked between the silicon sheets as placeholders; selectively etched "
                     "away so the gate can wrap every sheet."),
    Material("sige_hi", (0.80, 0.40, 0.65, 1), "高 Ge SiGe (中间隔离牺牲层)", "High-Ge SiGe (isolation placeholder)", 2,
             role_zh="锗含量更高的锗硅，可以比普通 SiGe 更早被刻掉；空出来的位置填上绝缘介质，"
                     "把上下叠着的两个晶体管隔开（CFET）。",
             role_en="Higher-Ge SiGe that etches first; the gap it leaves is filled with dielectric to "
                     "separate the stacked top and bottom transistors (CFET)."),
    Material("mdi_ox", (0.62, 0.86, 0.70, 1), "中间介质隔离 (MDI)", "Middle dielectric isolation (MDI)", 3,
             role_zh="CFET 里夹在上层 PMOS 和下层 NMOS 之间的绝缘层，把它们电隔离开。",
             role_en="Insulator between the stacked PMOS (top) and NMOS (bottom) in a CFET."),
    Material("hfo2", (0.98, 0.98, 0.55, 1), "高 k 介质 HfO2", "High-k HfO2", 7,
             role_zh="取代二氧化硅的栅绝缘层。它“k 值高”：物理上可以做得厚一些（漏电小），"
                     "对栅极控制力的效果却相当于很薄的二氧化硅。",
             role_en="Replaces SiO2 as gate insulator: physically thicker (less leakage) but electrically "
                     "acts like a very thin oxide."),
    Material("wf_n", (0.55, 0.62, 0.70, 1), "N 型功函数金属 (TiAl)", "n work-function metal (TiAl)", 7,
             role_zh="薄薄一层特定金属，它的“功函数”决定 NMOS 在多大栅压下打开（阈值电压）。",
             role_en="A thin metal whose work function sets the NMOS turn-on (threshold) voltage."),
    Material("wf_p", (0.40, 0.50, 0.62, 1), "P 型功函数金属 (TiN)", "p work-function metal (TiN)", 7,
             role_zh="作用同上，但用于 PMOS，决定 PMOS 的阈值电压。",
             role_en="Same idea for the PMOS: sets its threshold voltage."),
    Material("gate_metal", (0.58, 0.58, 0.64, 1), "栅极填充金属 (W)", "Gate fill metal (W)", 6,
             role_zh="钨，把栅极沟槽剩下的空间填满，降低栅极的电阻。",
             role_en="Tungsten filling the rest of the gate trench to lower gate resistance."),
    Material("n_epi", (0.95, 0.30, 0.30, 1), "N+ 外延源漏 (SiP)", "n+ epitaxial S/D (SiP)", 3,
             role_zh="在源漏位置“长”出来的含磷硅：电阻低，还会拉伸沟道，让电子跑得更快。",
             role_en="Phosphorus-rich silicon grown at the S/D: low resistance, and it stretches the "
                     "channel so electrons move faster."),
    Material("p_epi", (0.30, 0.42, 0.95, 1), "P+ 外延源漏 (SiGe:B)", "p+ epitaxial S/D (SiGe:B)", 3,
             role_zh="在 PMOS 源漏长出的掺硼锗硅：电阻低，还会挤压沟道，让空穴跑得更快（应变硅）。",
             role_en="Boron-doped SiGe grown at the PMOS S/D: squeezes the channel so holes move faster "
                     "(strained silicon)."),
    Material("silicide", (0.45, 0.42, 0.50, 1), "金属硅化物 (NiSi / TiSi)", "Silicide (NiSi / TiSi)", 5,
             role_zh="金属和硅的化合物，导电好。垫在源漏或栅与接触孔之间，降低接触电阻。",
             role_en="Metal-silicon compound that conducts well; sits between S/D or gate and the contact "
                     "to cut contact resistance."),
    Material("plug", (0.62, 0.66, 0.80, 1), "接触孔金属 (W / Co)", "Contact metal (W / Co)", 7,
             role_zh="填在接触孔里的金属“柱子”（钨或钴），竖着穿过绝缘层，把下面的源漏或栅接到上面的导线。",
             role_en="Metal posts (W or Co) through the insulator, connecting S/D or gate to the wires above."),
    Material("lowk", (0.85, 0.80, 0.95, 0.30), "低 k 介质", "Low-k dielectric", 6,
             role_zh="比二氧化硅介电常数更低的绝缘层，减小相邻导线之间的寄生电容，信号跑得更快、更省电。"
                     "画成半透明。",
             role_en="Insulator with lower permittivity than SiO2: less capacitance between wires, so "
                     "signals are faster and use less power."),
    Material("copper", (0.90, 0.55, 0.30, 1), "铜互连 (Cu)", "Copper wiring (Cu)", 8,
             role_zh="铜导线，电阻比铝小，现代芯片都用铜做连线。",
             role_en="Copper wires; lower resistance than aluminium, used in all modern chips."),
    Material("bs_metal", (0.90, 0.70, 0.30, 1), "背面供电金属", "Backside power metal", 8,
             role_zh="从晶圆背面走的电源线。正面留给信号线，布线不再拥挤，电源压降也更小。",
             role_en="Power lines routed on the back of the wafer, leaving the front for signals."),

    # ---------------- 仿真时才出现的“反型层”（不进图例） ----------------
    Material("channel_n", (0.3, 1.0, 1.0, 0.0), "电子反型层", "Electron inversion layer", 9, False,
             role_zh="NMOS 打开时栅极下面聚集的一薄层电子，就是导电的沟道。",
             role_en="The thin sheet of electrons under the NMOS gate when it is on: the channel."),
    Material("channel_p", (1.0, 0.6, 0.2, 0.0), "空穴反型层", "Hole inversion layer", 9, False,
             role_zh="PMOS 打开时栅极下面聚集的一薄层空穴。",
             role_en="The thin sheet of holes under the PMOS gate when it is on."),
]

# 把列表转成“字典”：用内部名就能直接查到材料，例如 MATERIALS["p_sub"]
MATERIALS = {m.key: m for m in _M}


def mat(key: str) -> Material:
    """按内部名取材料，例如 mat("poly").color 就是多晶硅的颜色。"""
    return MATERIALS[key]
