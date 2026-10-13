"""Process engine: wafer state, animated actions and the Flow abstraction.

A Flow is an ordered list of Steps; a Step is a list of animated Phases; a
Phase is a list of actions.  An action mutates the Wafer and describes how to
animate the change in a PhaseAnim.  Nothing here imports Panda3D.

Extension points
----------------
* Flow / FLOWS registry (fabsim3d.flows) – one module per technology
  generation (LOCOS 1 µm, STI 0.25 µm, ...).  Flow.features tells the device
  model which physical effects apply (see device_model.EFFECTS).
* Faults (Ctx.faults) – deliberate process errors for "find the bug" lessons:
  mask misalignment and skipped steps are honoured by the core actions.
* Wafer.dopants / Wafer.thermal – every implant and anneal is recorded so a
  later doping-profile view can compute concentrations without re-parsing
  geometry.

【中文说明：这个文件是干什么的？】
这是整个程序的“工艺引擎”——它负责记录“晶圆（wafer，做芯片用的硅片）现在长什么样”，
以及“每一步工艺（沉积、刻蚀、注入、退火……）会把晶圆变成什么样”。

层级关系（从大到小）：
    Flow（工艺流程，比如“1 微米 LOCOS 工艺”）
      └─ Step（工艺步骤，比如“做栅极”）
           └─ Phase（动画小阶段，比如“涂光刻胶”“曝光”“显影”）
                └─ action（动作：真正去修改晶圆数据的小函数）

每个 action 做两件事：
  1. 修改 Wafer（晶圆的数据：有哪些材料层、每层由哪些立方块组成）；
  2. 往 PhaseAnim（动画说明书）里写下“这次变化该怎么播放动画”，
     比如哪些块要“长出来”、哪些块要“被刻蚀消失”、要不要喷粒子特效。

注意：这个文件只管“数据和规则”，不负责画 3D 画面（不导入 Panda3D）。
真正把东西画到屏幕上的是别的文件，它们会读取这里产生的 Wafer 和 PhaseAnim。

几个扩展点（中文）：
* Flow / FLOWS：每一代工艺技术（LOCOS、STI 等）各写一个模块；Flow.features 告诉
  “器件模型”（计算电学特性的部分）该考虑哪些物理效应。
* Faults：故意制造的工艺错误（掩膜对歪、跳过某步），用于“找茬”教学。
* Wafer.dopants / Wafer.thermal：每次离子注入和退火都会被记录下来，
  这样以后画“掺杂浓度分布图”时，不用重新分析几何形状。
"""
# 【语法】from __future__ import annotations：让类型标注（例如 -> Layer）先当成文字保存，
# 这样可以在类还没定义完时就引用它的名字。对初学者来说，可以理解为“兼容性开关”。
from __future__ import annotations

# dataclass（数据类）：一种快速定义“只装数据的盒子”的写法，后面会详细解释。
# field：给数据类的某个字段设置默认值（尤其是列表、字典这种“可变”的默认值）。
from dataclasses import dataclass, field
# typing 里的这些名字只是“类型提示”，帮助人和编辑器理解变量里装的是什么，不影响运行：
#   Callable=可调用的函数, Dict=字典, FrozenSet=不可修改的集合, List=列表,
#   Optional[X]=X 或者 None(空), Tuple=元组(固定长度、不可修改的一组值)
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

# 从同一个包里的其他文件导入：
#   ProcessParams：工艺参数（栅长、掺杂剂量、氧化层厚度等）
#   summarize：根据工艺参数算出电学结果（阈值电压、反相器曲线等）
from .device_model import ProcessParams, summarize
# geometry 模块提供几何工具：
#   Rect=矩形(俯视图上的一块区域), Solid=立体块, conformal_cells=“顺着表面”铺一层薄膜,
#   rect_complement=求“矩形之外的剩余区域”, rect_intersect=求两个矩形的重叠部分,
#   split_box=把一个立体块按矩形切成“里面的部分”和“外面的部分”
from .geometry import (Rect, Solid, conformal_cells, rect_complement,
                       rect_intersect, split_box)

# DOMAIN：整个模拟区域在俯视图上的范围 (x 最小, x 最大, y 最小, y 最大)。
# 单位是“显示单位”（大约对应微米，但为了画面好看做过缩放）。
DOMAIN: Rect = (0.0, 20.0, 0.0, 8.0)
# SUB_DEPTH：硅衬底（substrate，晶圆最底下那块硅）画多深。
SUB_DEPTH = 3.0
# ACT_Y：有源区（active area，真正做晶体管的那块硅）在 y 方向的起止位置。
ACT_Y = (1.5, 6.5)


# --------------------------------------------------------------------------
# Wafer state
# 晶圆状态：用来描述“此刻晶圆上有什么”
# --------------------------------------------------------------------------

# 【语法】@dataclass 是“装饰器”（写在类/函数上一行、以 @ 开头）。
# 它会自动帮这个类生成构造函数 __init__ 等，所以我们只需列出“字段名: 类型”即可。
# 例如 Layer("poly", "poly") 就能直接创建一个对象。
@dataclass
class Layer:
    """一层材料（例如“多晶硅层”“光刻胶层”）。

    name：这层的名字（程序内部用来查找它）；
    material：材料种类（决定画面上用什么颜色/质感显示）；
    solids：组成这一层的所有立体块。一层材料可以由很多不相连的小块组成。
    """
    name: str
    material: str
    # field(default_factory=list)：每创建一个新 Layer，都给它一个“全新的空列表”。
    # 如果直接写 = []，所有对象会共用同一个列表，造成奇怪的 bug，所以要这样写。
    solids: List[Solid] = field(default_factory=list)


@dataclass
class DopantEvent:
    """One ion implantation (for doping-profile visualisation).

    一次离子注入的记录（用于画掺杂浓度分布图）。
    离子注入 = 把带电的杂质原子（如磷 P、砷 As、硼 B）加速后“打”进硅里，
    从而改变那块硅的导电类型（n 型：多电子；p 型：多空穴）。
    """
    step: str               # 发生在哪个工艺步骤
    species: str            # "P", "As", "B", "BF2"     （注入的元素种类）
    polarity: str           # "n" | "p"                 （掺完后是 n 型还是 p 型）
    dose_cm2: float         # 剂量：每平方厘米打进去多少个原子
    energy_kev: float       # 能量（千电子伏）：越大打得越深
    rects: List[Rect]       # 注入到了哪些区域（俯视图上的矩形）
    z_top: float            # surface height where the ions entered（离子进入时表面的高度）


@dataclass
class ThermalEvent:
    """一次高温处理（退火/氧化等）的记录。

    温度和时间合起来叫“热预算”（thermal budget）：越热越久，
    之前注入的杂质就扩散得越远，所以需要把每次加热都记下来。
    """
    step: str               # 哪个步骤
    temp_c: float           # 温度（摄氏度）
    time_s: float           # 持续时间（秒）


class Wafer:
    """晶圆：整个模拟的“当前状态”。

    它就像一个账本，记录着：
      layers   —— 现在有哪些材料层（按名字存放在字典里）
      dopants  —— 做过的所有离子注入
      thermal  —— 做过的所有加热
      current_step —— 现在正在执行哪个工艺步骤（记录事件时会用到）
    """

    def __init__(self):
        # __init__ 是“构造函数”：创建 Wafer() 时自动运行，用来准备初始的空数据。
        # self 指“这个对象自己”，self.xxx 就是存在对象身上的数据。
        self.layers: Dict[str, Layer] = {}
        self.dopants: List[DopantEvent] = []
        self.thermal: List[ThermalEvent] = []
        self.current_step: str = ""

    def layer(self, name: str, material: Optional[str] = None) -> Layer:
        """取出名为 name 的层；如果还没有，就新建一层再返回。

        这样各个工艺动作只要写 w.layer("oxide", ...)，不用操心这层是否已存在。
        如果没给 material，就默认材料名和层名一样（`material or name` 的意思是
        “material 有值就用它，否则用 name”）。
        """
        if name not in self.layers:
            self.layers[name] = Layer(name, material or name)
        return self.layers[name]

    def solids(self, exclude=()) -> List[Solid]:
        """把所有层的立体块合并成一个大列表返回（可以排除某些层）。

        用途：沉积新薄膜时，需要知道“当前表面”长什么样，才能顺着表面铺上去。
        """
        # 【语法】这是“列表推导式”：[结果 for ... in ... if 条件 for ... in ...]
        # 等价于两层 for 循环：遍历每一层(名字 n, 层 l)，跳过 exclude 中的层，
        # 再把这一层里的每个立体块 s 收集到新列表里。
        return [s for n, l in self.layers.items() if n not in exclude for s in l.solids]

    def remove(self, name: str) -> Optional[Layer]:
        """把一整层从晶圆上拿掉，并返回被拿掉的那层（没有就返回 None）。

        用于“整层剥除”，例如去掉全部光刻胶。返回旧层是为了播放它消失的动画。
        """
        # dict.pop(键, 默认值)：删除并返回该键对应的值；键不存在时返回默认值，不会报错。
        return self.layers.pop(name, None)

    def has(self, name: str) -> bool:
        """判断这一层是否存在并且“确实有东西”（至少一个立体块）。"""
        return name in self.layers and bool(self.layers[name].solids)


@dataclass
class ParticleSpec:
    """粒子特效的说明（纯视觉效果，用来让工艺过程看起来更直观）。

    kind 的几种取值：
      ion    —— 离子注入时飞向晶圆的离子
      uv     —— 光刻曝光时的紫外光
      plasma —— 等离子刻蚀时的等离子体
      depo   —— 沉积时落到表面的原子/分子
    """
    kind: str                      # ion | uv | plasma | depo
    color: tuple                   # 颜色 (红, 绿, 蓝, 不透明度)，每个数在 0~1 之间
    region: Optional[List[Rect]] = None   # spawn region(s); None = whole wafer（粒子从哪些区域落下，None=整片）
    rate: float = 120.0            # particles per second（每秒产生多少粒子）
    stop_solids: List[Solid] = field(default_factory=list)  # 粒子碰到这些块就停下（即落在当时的表面上）


@dataclass
class MaskSpec:
    """光刻掩膜（mask）的动画说明。

    掩膜就像“镂空的模板”：铬（chrome）挡住光的地方，下面的光刻胶不会被曝光。
    chrome：被铬遮挡的矩形区域；z：掩膜在动画里悬停的高度。
    """
    chrome: List[Rect]
    z: float


@dataclass
class PhaseAnim:
    """一个动画小阶段的“播放说明书”。

    工艺动作（action）在修改晶圆的同时，会往这里写“该怎么演”，
    3D 画面部分再根据它来播放动画。各字段：
      grow      —— 要“从下往上长出来”的块（如沉积薄膜、氧化生长）
      fade_in   —— 要“慢慢显现”的块（如注入后出现的掺杂区）
      ghosts    —— 要消失的旧块，附带材料和消失方式（etch 刻蚀 / fade 淡出）
      recolor   —— 要变色的层（记录它原来的材料，好做颜色渐变）
      particles —— 粒子特效列表
      mask      —— 是否显示掩膜
      glow      —— 是否让晶圆发光（表示高温加热）
      pad       —— CMP 抛光垫压下来的高度
    """
    grow: List[Solid] = field(default_factory=list)
    fade_in: List[Solid] = field(default_factory=list)
    ghosts: List[Tuple[str, Solid, str]] = field(default_factory=list)  # (material, solid, etch|fade)
    recolor: Dict[str, str] = field(default_factory=dict)              # layer -> old material
    particles: List[ParticleSpec] = field(default_factory=list)
    mask: Optional[MaskSpec] = None
    glow: Optional[tuple] = None
    pad: Optional[float] = None    # CMP polishing pad comes down to this z（CMP 抛光垫下降到的高度）


@dataclass
class Faults:
    """Deliberate process errors (hook for a fault-finding teaching mode).

    misalign: mask name -> (dx, dy) shift of that mask's pattern
    skip:     step keys that are silently left out of the flow

    故意制造的工艺错误（给“找茬”教学模式用）：
      misalign：掩膜名字 -> (dx, dy)，表示这块掩膜对准时偏移了多少（套刻误差）；
      skip：被偷偷跳过的工艺步骤的名字集合。
    学生可以观察做错之后芯片性能如何变化，从而理解每一步的重要性。
    """
    misalign: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    # frozenset()：一个空的“不可修改集合”。因为不可修改，可以安全地直接当默认值。
    skip: FrozenSet[str] = frozenset()

    def shift(self, mask: Optional[str], rects: List[Rect]) -> List[Rect]:
        """把某块掩膜的图形按设定的偏移量平移（模拟“没对准”）。

        如果这块掩膜没有设偏移，就原样返回。平移后超出模拟区域的部分会被裁掉。
        """
        if not mask or mask not in self.misalign:
            return rects
        # 把元组 (dx, dy) 一次性拆给两个变量（叫“解包”）。
        dx, dy = self.misalign[mask]
        out = []
        for r in rects:
            # r 是 (x0, x1, y0, y1)：x 方向两端都加 dx，y 方向两端都加 dy，
            # 再和 DOMAIN 求交集，保证不超出晶圆范围。
            s = rect_intersect((r[0] + dx, r[1] + dx, r[2] + dy, r[3] + dy), DOMAIN)
            if s:      # 完全移出范围时 s 为空，就丢弃
                out.append(s)
        return out


@dataclass
class Ctx:
    """上下文（context）：执行工艺动作时需要“随身携带”的信息打包在一起。

      p      —— 工艺参数（用户在界面上调的那些数值）
      lay    —— 版图（layout）：各个区域在俯视图上的位置，是一个字典
      flow   —— 当前使用的工艺流程
      faults —— 故意设置的工艺错误
    """
    p: ProcessParams
    lay: dict
    # 这里 "Flow" 加了引号，是因为 Flow 类在下面才定义（“提前引用”）。
    flow: Optional["Flow"] = None
    faults: Faults = field(default_factory=Faults)

    # 【语法】@property：让一个方法可以像普通属性一样用 ctx.features 读取，不用加括号。
    @property
    def features(self) -> FrozenSet[str]:
        """当前流程启用了哪些物理特性/工艺特点（没有流程时返回空集合）。"""
        # 【语法】A if 条件 else B：条件成立取 A，否则取 B（“条件表达式”）。
        return self.flow.features if self.flow else frozenset()


# Action（动作）的类型：一个接收 (晶圆, 上下文, 动画说明书)、没有返回值(None) 的函数。
# 下面所有 deposit()/pattern()/implant() 等函数，都是“制造这种动作函数”的工厂。
Action = Callable[[Wafer, Ctx, PhaseAnim], None]


@dataclass
class Phase:
    """一个动画小阶段：一段中文/英文说明 + 播放时长 + 要执行的动作列表。

    例如 Phase("旋涂光刻胶", "Spin-coat photoresist", 1.2, [coat()])。
    """
    zh: str                 # 中文标题
    en: str                 # 英文标题
    duration: float         # 动画时长（秒）
    actions: List[Action]   # 这一阶段依次执行的动作


@dataclass
class Quiz:
    """一道随堂小测验（每个字段都是 (中文, 英文) 成对出现）。"""
    q: Tuple[str, str]                  # 题目
    options: List[Tuple[str, str]]      # 选项列表
    answer: int                         # 正确答案的序号（从 0 开始数）
    explain: Tuple[str, str]            # 答案解析


@dataclass
class Step:
    """一个工艺步骤（例如“场氧化”“多晶硅栅刻蚀”），界面上的一页。"""
    key: str                            # 内部唯一名字（程序用来识别这一步）
    title: Tuple[str, str]              # 标题（中, 英）
    desc: Tuple[str, str]               # 说明文字（中, 英）
    # 参数表：每项是 (中文名, 英文名, 一个根据上下文算出显示文字的函数)
    params: List[Tuple[str, str, Callable[["Ctx"], str]]]
    phases: List[Phase]                 # 这一步包含的动画小阶段
    quiz: Optional[Quiz] = None         # 可选的小测验
    mask_name: Optional[Tuple[str, str]] = None   # 这一步用到的掩膜名字（如果有光刻）


@dataclass
class Flow:
    """A complete process recipe for one technology generation.

    一个完整的工艺“配方”，对应一代芯片制造技术（例如 1 微米 LOCOS 隔离、
    0.25 微米 STI 浅沟槽隔离、FinFET 等）。里面按顺序列出所有步骤，
    外加这一代工艺的特点、标签位置、典型参数等。
    """
    key: str
    name: Tuple[str, str]
    node: Tuple[str, str]                     # one-line description of the generation（一句话介绍这一代工艺）
    steps: List[Step]
    features: FrozenSet[str] = frozenset()    # e.g. {"locos"} / {"sti", "cmp"}（工艺特点标签）
    region_labels: List[tuple] = field(default_factory=list)   # (layer, zh, en, x, z)（剖面图上的区域文字标签）
    terminal_labels: List[tuple] = field(default_factory=list)  # (name, x, y)（端口名标签，如 VDD/GND）
    defaults: Dict[str, float] = field(default_factory=dict)    # typical ProcessParams of the era（那个年代的典型参数）
    short: Optional[Tuple[str, str]] = None   # compact name for the flow selector（选择菜单里显示的短名字）
    # optional per-generation hooks (None = the planar side-by-side inverter)
    # 下面是可选的“定制钩子”：某一代工艺如果结构特殊（如 FinFET、CFET），可以提供自己的函数；
    # 为 None 时，就用默认的“平面结构、NMOS 和 PMOS 左右并排”的反相器。
    layout_fn: Optional[Callable[[ProcessParams], dict]] = None  # replaces layout()（替换默认版图函数）
    sliders: Optional[List[tuple]] = None     # (key, i18n key, lo, hi, log) for the Parameters tab（参数页的滑块）
    device_labels: Optional[List[tuple]] = None   # (text, x, y, z, rgba) shown in simulation mode（仿真模式下的标签）
    channel_fn: Optional[Callable[[dict], List[tuple]]] = None   # lay -> [(key "n"/"p", Solid)]（沟道在哪里）
    carrier_fn: Optional[Callable[[dict, float], dict]] = None   # (lay, y) -> carrier paths（载流子运动路径）
    carrier_ys: List[Tuple[float, float]] = field(default_factory=list)  # silicon bands carriers snap to

    def default_params(self) -> ProcessParams:
        """用这一代工艺的典型数值，创建一套工艺参数。"""
        # 【语法】**字典：把字典“展开”成“名字=值”的关键字参数传进去，
        # 例如 {"l_um": 1.0} 就相当于 ProcessParams(l_um=1.0)。
        return ProcessParams(**self.defaults)

    @property
    def label(self) -> Tuple[str, str]:
        """界面上显示用的名字：有短名就用短名，否则用全名。"""
        return self.short or self.name

    def step_index(self, key: str) -> int:
        """根据步骤名字 key，找到它在步骤列表中排第几（从 0 开始）。"""
        # enumerate 会同时给出“序号 i 和元素 s”；next(...) 取出第一个满足条件的结果。
        # 括号里的 (i for ... if ...) 叫“生成器表达式”，和列表推导式类似，但是按需逐个产生。
        return next(i for i, s in enumerate(self.steps) if s.key == key)


# --------------------------------------------------------------------------
# Layout (depends on drawn gate length)
# 版图：决定每个结构在俯视图上的位置（会随用户设置的栅长而变化）
# --------------------------------------------------------------------------

def layout(p: ProcessParams) -> dict:
    """默认的平面 CMOS 反相器版图：左边是 NMOS，右边是 PMOS。

    反相器（inverter）= 一个 NMOS + 一个 PMOS 串在电源 VDD 和地 GND 之间，
    输入高电平时输出低电平，反之亦然，是最基本的数字电路。

    返回一个字典，里面是各个区域的矩形坐标 (x0, x1, y0, y1)，
    后面的工艺步骤会用这些坐标决定“在哪里刻蚀、在哪里注入”。
    """
    # 画面里的栅极宽度 gl：随真实栅长 p.l_um 变化，但限制在 0.6~1.8 之间，
    # 这样栅长很小或很大时画面都不会太离谱（只是示意，不是按真实比例）。
    gl = min(max(0.45 + 0.3 * p.l_um, 0.6), 1.8)
    # NMOS 栅极中心 x=5.25，PMOS 栅极中心 x=15.25
    gnc, gpc = 5.25, 15.25
    # 两个栅极在 x 方向的起止位置（中心左右各一半宽度）
    gn = (gnc - gl / 2, gnc + gl / 2)
    gp = (gpc - gl / 2, gpc + gl / 2)
    # 有源区（做晶体管的硅区域）。【语法】*ACT_Y 把元组 ACT_Y 的两个值“摊开”放进来，
    # 所以 act_n 实际是 (2.0, 8.5, 1.5, 6.5)。
    act_n = (2.0, 8.5, *ACT_Y)
    act_p = (12.0, 18.5, *ACT_Y)

    # 【语法】在函数里面再定义一个函数（嵌套函数），只在这里用。
    def gate_rects(g, c):
        """栅极的形状由两块矩形组成：跨过沟道的长条 + 伸到场区上的接触垫。"""
        return [(g[0], g[1], 1.1, ACT_Y[1]),                 # over channel + end cap（跨过沟道并稍微伸出）
                (min(g[0], c - 0.5), max(g[1], c + 0.5), ACT_Y[1], 7.6)]  # contact pad on field（场区上的接触垫）

    # 接触孔（contact）：金属连线向下连到硅或栅极的小孔。
    #   n_src/n_drn：NMOS 的源极/漏极；p_drn/p_src：PMOS 的漏极/源极；g_n/g_p：两个栅极
    contacts = {
        "n_src": (2.8, 3.9, 2.6, 4.4), "n_drn": (6.6, 7.7, 2.6, 4.4),
        "p_drn": (12.8, 13.9, 2.6, 4.4), "p_src": (16.6, 17.7, 2.6, 4.4),
        "g_n": (gnc - 0.3, gnc + 0.3, 6.8, 7.35), "g_p": (gpc - 0.3, gpc + 0.3, 6.8, 7.35),
    }
    # 金属连线：GND(地)接 NMOS 源极，VDD(电源)接 PMOS 源极，
    # VOUT(输出)把两个漏极连起来，VIN(输入)把两个栅极连起来——这就组成了反相器。
    metal = {
        "GND": (2.4, 4.3, 0.3, 4.9), "VOUT": (6.2, 14.3, 2.2, 4.8),
        "VDD": (16.2, 18.1, 0.3, 4.9), "VIN": (gnc - 0.5, gpc + 0.5, 6.6, 7.6),
    }
    actives = [act_n, act_p]
    # dict(名字=值, ...) 是另一种创建字典的写法。
    return dict(
        gl=gl, gn=gn, gp=gp, gnc=gnc, gpc=gpc, act_n=act_n, act_p=act_p,
        # nwell：N 阱（右半边，PMOS 要做在 n 型硅里）；pside：左半边 p 型区域（NMOS 用）
        nwell=(10.5, 20.0, 0.0, 8.0), pside=(0.0, 10.5, 0.0, 8.0),
        gates_n=gate_rects(gn, gnc), gates_p=gate_rects(gp, gpc),
        contacts=contacts, metal=metal,
        # 场氧（field oxide，晶体管之间起隔离作用的厚氧化层）在 x 方向的位置
        fox_x=[(0.0, 2.0), (8.5, 12.0), (18.5, 20.0)],
        iso=rect_complement(DOMAIN, actives),          # isolation (field) regions（有源区以外都是隔离区）
    )


def make_ctx(p: ProcessParams, flow: Optional[Flow] = None, faults: Optional[Faults] = None) -> Ctx:
    """根据工艺参数、流程和故障设置，组装出一个上下文 Ctx。

    如果流程自带特殊版图函数（layout_fn），就用它；否则用上面默认的 layout()。
    """
    lay = flow.layout_fn(p) if flow and flow.layout_fn else layout(p)
    return Ctx(p, lay, flow, faults or Faults())


# --------------------------------------------------------------------------
# Actions
# 工艺动作：每个函数都是一个“工厂”，调用它会返回一个真正的动作函数 act。
#
# 【语法：闭包 closure】例如 deposit("oxide", ...) 并不会马上沉积，
# 它返回内部定义的 act 函数，而 act “记住”了外层传入的参数（layer、material……）。
# 等到播放到这一阶段时，程序才调用 act(晶圆, 上下文, 动画) 真正执行。
# 这样就可以先把整套工艺“写成配方”，之后再按顺序执行。
# --------------------------------------------------------------------------

def _rects(c: Ctx, rects, mask=None) -> List[Rect]:
    """把“区域”参数统一变成矩形列表，并应用掩膜偏移（如果设置了套刻误差）。

    rects 可以是一个函数（根据上下文计算区域），也可以是现成的矩形列表。
    函数名前面的下划线 _ 是惯例，表示“这是内部辅助函数，别的文件不要直接用”。
    """
    # callable(x)：判断 x 能不能像函数一样被调用。
    r = rects(c) if callable(rects) else list(rects)
    return c.faults.shift(mask, r)


def deposit(layer, material, thickness=None, top=None, region=None, particles=None):
    """沉积（deposition）：在晶圆表面盖上一层新薄膜（如氧化硅、多晶硅、金属）。

    “保形”沉积（conformal）意思是薄膜会顺着现有表面的高低起伏铺上去，
    就像下雪后雪层覆盖在地形上。
      thickness：薄膜厚度；top：或者直接指定薄膜顶面高度；
      region：只在这些区域沉积（默认整片）；particles：可选的粒子特效 (种类, 颜色)。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        # 确定沉积范围：region 是函数就调用它，没给就用整个 DOMAIN。
        reg = region(c) if callable(region) else (region or [DOMAIN])
        # 记下沉积“之前”的所有立体块，作为新薄膜要贴合的表面。
        snapshot = w.solids()
        # 计算新薄膜由哪些小块组成（顺着表面起伏）。min_top_gap 防止薄膜过薄到看不见。
        cells = conformal_cells(snapshot, reg, DOMAIN, thickness=thickness, top=top,
                                min_top_gap=0.1)
        # 把新块加入对应的层，并告诉动画：这些块要“长出来”。
        w.layer(layer, material).solids.extend(cells)
        a.grow.extend(cells)
        # 如果要粒子特效：粒子从整片上方落下，碰到旧表面就停。
        if particles:
            a.particles.append(ParticleSpec(particles[0], particles[1], None, 90, snapshot))
    return act


def strip(layer, mode="etch"):
    """剥除（strip）：把某一整层全部去掉（例如用完的光刻胶、牺牲氧化层）。

    mode 决定消失动画的样子："etch" 像被刻蚀掉，"fade" 慢慢淡出。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        lay = w.remove(layer)
        if lay:
            # += 列表推导式：把被删层的每个块都加入“幽灵”列表，用来播放消失动画。
            a.ghosts += [(lay.material, s, mode) for s in lay.solids]
    return act


def pattern(layer, keep, particles=True, mask=None):
    """Etch `layer` everywhere except footprint rects keep(ctx).

    图形化刻蚀：把 layer 这一层刻掉，只保留 keep 指定的区域。
    真实工艺中，保留的区域上面有光刻胶保护，没有保护的地方被等离子体刻蚀掉。
    例如：整片沉积多晶硅后，只保留栅极形状，这就“刻”出了栅极。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        # 这一层根本不存在时，什么也不做（直接返回）。
        if layer not in w.layers:
            return
        lay = w.layers[layer]
        snapshot = w.solids()
        keep_r = _rects(c, keep, mask)     # 要保留的区域（已考虑掩膜偏移）
        kept_all = []
        # 每个立体块都切成“在保留区内的部分”和“被刻掉的部分”。
        for s in lay.solids:
            kept, removed = split_box(s, keep_r)
            kept_all += kept
            # 被刻掉的部分加入幽灵列表，播放刻蚀动画。
            a.ghosts += [(lay.material, r, "etch") for r in removed]
        lay.solids = kept_all
        # 粉紫色的等离子体粒子特效。
        if particles:
            a.particles.append(ParticleSpec("plasma", (1.0, 0.45, 0.85, 1), None, 140, snapshot))
    return act


def expose(keep, mask_z=3.0, mask=None):
    """Positive resist: area outside `keep` (mask openings) becomes exposed.

    曝光（光刻的关键一步）：紫外光透过掩膜照在光刻胶上。
    这里用的是“正性光刻胶”：被光照到的地方会变得可溶，之后显影时被洗掉。
    keep 是掩膜上铬挡住的区域（光刻胶保留）；其余地方是“开口”，会被曝光。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        lay = w.layers["resist"]
        snapshot = w.solids()
        keep_r = _rects(c, keep, mask)
        # 把光刻胶分成两份：kept_all（没被照到）和 exp（被照到）。
        kept_all, exp = [], []
        for s in lay.solids:
            kept, removed = split_box(s, keep_r)
            kept_all += kept
            exp += removed
        lay.solids = kept_all
        # 被曝光的部分单独放进新层 "resist_exp"，这样显影时可以整层去掉。
        w.layer("resist_exp", "resist").solids = exp
        # 动画：这层先按原来光刻胶的颜色显示，再渐变成“已曝光”的颜色。
        a.recolor["resist_exp"] = "resist"
        w.layers["resist_exp"].material = "resist_exp"
        # 动画：在上方显示掩膜，并让紫外光粒子只从掩膜开口处落下。
        a.mask = MaskSpec(keep_r, mask_z)
        a.particles.append(ParticleSpec("uv", (0.65, 0.35, 1.0, 1), rect_complement(DOMAIN, keep_r),
                                        160, snapshot))
    return act


def develop():
    """显影：把曝光过的光刻胶溶解掉（即剥除 "resist_exp" 层）。

    显影后，剩下的光刻胶图形就是掩膜图形的“复制品”，用来保护下面的材料。
    """
    return strip("resist_exp", "etch")


def coat():
    """旋涂光刻胶：在整片晶圆上铺一层 0.45 厚的光刻胶（感光材料）。"""
    return deposit("resist", "resist", thickness=0.45)


def implant(layer, material, rects, z0=-0.3, ion_color=(1, 0.9, 0.2, 1),
            species=None, dose=None, energy_kev=None):
    """Ion implantation into rects(ctx); records a DopantEvent when species is given.

    dose may be a number or a callable(ctx) (e.g. tied to a UI parameter).

    离子注入：把杂质离子打进 rects 指定区域的硅里，形成掺杂区
    （例如晶体管的源极/漏极）。z0 是掺杂区底部的深度（负数表示在硅表面以下）。
    如果给出了 species（元素种类），还会记录一条 DopantEvent，供掺杂分布图使用。
    dose 可以是固定数字，也可以是函数（随界面上的参数变化）。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        rs = rects(c)
        # 每个注入矩形变成一个从深度 z0 到表面 0 的立体块，代表“被掺杂的硅”。
        new = [Solid.box(r[0], r[1], r[2], r[3], z0, 0.0) for r in rs]
        w.layer(layer, material).solids.extend(new)
        a.fade_in.extend(new)       # 掺杂区慢慢显现
        # 黄色的离子粒子从上方飞下来。
        a.particles.append(ParticleSpec("ion", ion_color, None, 220, snapshot))
        if species:
            d = dose(c) if callable(dose) else dose
            # 磷(P)、砷(As)、锑(Sb)是 5 价元素，会多给出电子 -> n 型；其他（硼等）-> p 型。
            pol = "n" if species in ("P", "As", "Sb") else "p"
            # float(d or 0.0)：d 为空时当作 0，再转成小数。
            w.dopants.append(DopantEvent(w.current_step, species, pol, float(d or 0.0),
                                         float(energy_kev or 0.0), rs, 0.0))
    return act


def implant_solids(layer, material, solids_fn, ion_color=(1, 0.9, 0.2, 1), species=None, dose=None,
                   energy_kev=None, region=None):
    """Ion implantation whose doped volume follows the topography (e.g. only the
    fins, not the oxide between them).  solids_fn(ctx) gives the doped solids;
    region(ctx) the implanted footprint recorded in the DopantEvent.

    和 implant 类似的离子注入，但掺杂区的形状由 solids_fn 直接给出，
    可以顺着立体结构走（例如 FinFET 里只掺“鳍”本身，不掺鳍之间的氧化物）。
    region 是记录到 DopantEvent 里的俯视区域；没给就用每个块的“脚印”（俯视投影）。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        new = solids_fn(c)
        w.layer(layer, material).solids.extend(new)
        a.fade_in.extend(new)
        a.particles.append(ParticleSpec("ion", ion_color, None, 220, snapshot))
        if species:
            d = dose(c) if callable(dose) else dose
            pol = "n" if species in ("P", "As", "Sb") else "p"
            rs = region(c) if region else [s.footprint for s in new]
            w.dopants.append(DopantEvent(w.current_step, species, pol, float(d or 0.0),
                                         float(energy_kev or 0.0), rs, 0.0))
    return act


def add_solids(layer, material, solids_fn, mode="grow", particles=None):
    """Add explicit solids (epitaxy, liners, ...) with a grow or fade-in animation.

    直接添加指定形状的立体块（例如外延生长 epitaxy：在硅上长出新的单晶层；
    或者衬垫层 liner）。mode="grow" 播放生长动画，否则播放淡入动画。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        new = solids_fn(c)
        w.layer(layer, material).solids.extend(new)
        # 括号里先根据 mode 选出 a.grow 或 a.fade_in 这个列表，再往里追加。
        (a.grow if mode == "grow" else a.fade_in).extend(new)
        if particles:
            a.particles.append(ParticleSpec(particles[0], particles[1], None, 90, snapshot))
    return act


def convert(src, dst, material, keep_rects, mode="fade"):
    """Move the parts of layer `src` inside keep_rects(ctx) into layer `dst`
    with a new material (e.g. SiGe under the spacers -> inner spacer).

    材料转换：把 src 层位于 keep_rects 区域内的部分“搬”到 dst 层，并换成新材料。
    用于表示某块材料被替换/改性，例如环栅晶体管中，侧墙下面的锗硅（SiGe）
    被换成“内侧墙”绝缘材料。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        lay = w.layers.get(src)    # dict.get：键不存在时返回 None，而不是报错
        if not lay:
            return
        rects = keep_rects(c)
        stay, moved = [], []
        # 区域内的部分 -> moved（要转换），区域外的部分 -> stay（保持原样）。
        for s in lay.solids:
            inside, outside = split_box(s, rects)
            moved += inside
            stay += outside
        lay.solids = stay
        if not stay:
            w.remove(src)          # 原层已经空了，就整个删掉
        # 动画：旧材料淡出，新材料在同一位置淡入，看起来像“变了材料”。
        a.ghosts += [(lay.material, s, "fade") for s in moved]
        w.layer(dst, material).solids.extend(moved)
        a.fade_in.extend(moved)
    return act


def recolor(layer, material):
    """把一整层的材料改成另一种（只改“是什么材料”，形状不变）。

    例如多晶硅经过掺杂后变成“掺杂多晶硅”，在画面上换个颜色表示。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        if layer in w.layers:
            # 先记下旧材料（动画用它做颜色渐变），再换成新材料。
            a.recolor[layer] = w.layers[layer].material
            w.layers[layer].material = material
    return act


def glow(color=(1.0, 0.55, 0.2)):
    """只播放“晶圆发光”的动画（表示加热），不记录热预算。"""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        a.glow = color
    return act


def anneal(temp_c: float, time_s: float, color=(1.0, 0.45, 0.15)):
    """Thermal step: glow animation + ThermalEvent record (thermal budget).

    退火（anneal）：把晶圆加热到高温保持一段时间。
    作用：修复离子注入撞坏的晶格、“激活”杂质让它真正导电，同时杂质会向周围扩散。
    这里播放发光动画，并记录温度和时间（热预算）。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        a.glow = color
        w.thermal.append(ThermalEvent(w.current_step, temp_c, time_s))
    return act


def replace_layer(layer, material, solids_fn, anchor=None, mode="fade", requires=None):
    """Swap a layer's geometry (e.g. diffusion during an anneal).

    requires: layer that must exist for the replacement to happen (an anneal
    only diffuses dopants that were actually implanted).

    替换一层的形状。典型用途：退火时杂质扩散，掺杂区会变大变深，
    于是把旧的掺杂区换成新的、更大的形状。
    requires：必须先存在的层——如果之前根本没注入（比如被故障模式跳过了），
    退火时也就没有东西可扩散，这时什么都不做。
    anchor：新块“生长”动画的基准高度。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        if requires and not w.has(requires):
            return
        # 删除旧层，让它淡出。
        old = w.remove(layer)
        if old:
            a.ghosts += [(old.material, s, "fade") for s in old.solids]
        # 生成新形状，设置每个块的动画基准高度，然后放回晶圆。
        new = solids_fn(c)
        for s in new:
            s.anchor = anchor
        w.layer(layer, material).solids = new
        (a.grow if mode == "grow" else a.fade_in).extend(new)
    return act


def recess(layers, rects, z_top, particles=True, mask=None):
    """Etch *into* existing solids (e.g. silicon trenches): inside rects(ctx),
    every box of `layers` is cut down to z_top.

    向下挖刻蚀：在 rects 区域内，把指定层的材料从上往下削到 z_top 高度。
    例如 STI（浅沟槽隔离）工艺中，先在硅里挖出沟槽，之后再填入氧化物来隔离晶体管。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        rs = _rects(c, rects, mask)
        snapshot = w.solids()
        for name in layers:
            lay = w.layers.get(name)
            if not lay:
                continue           # 这层不存在就跳过，处理下一层
            out = []
            for s in lay.solids:
                # 不是长方体（形状复杂，无法切）或者本来就不高于 z_top 的块：原样保留。
                if not s.is_box or s.zmax <= z_top:
                    out.append(s)
                    continue
                trench, rest = split_box(s, rs)      # (inside rects, outside rects)（沟槽区内 / 区外）
                out += rest                          # 区外部分不受影响
                for t in trench:
                    # 区内部分：只保留 z_top 以下的那截（如果还有剩）。
                    if t.zmin < z_top:
                        out.append(Solid.box(t.xmin, t.xmax, t.y0, t.y1, t.zmin, z_top))
                    # 被削掉的上半截作为幽灵，播放刻蚀动画。
                    a.ghosts.append((lay.material, Solid.box(t.xmin, t.xmax, t.y0, t.y1,
                                                             max(t.zmin, z_top), t.zmax), "etch"))
            lay.solids = out
        if particles:
            # 等离子体粒子只出现在被刻蚀的区域上方。
            a.particles.append(ParticleSpec("plasma", (1.0, 0.45, 0.85, 1), rs, 160, snapshot))
    return act


def cmp(layers, z_top, pad=True):
    """Chemical-mechanical polish: everything in `layers` above z_top is removed.

    CMP（化学机械抛光）：用抛光垫加化学研磨液把晶圆表面磨平。
    凡是高于 z_top 的材料都被磨掉，得到一个平整的表面，方便后续工艺。
    例如 STI 中沟槽填满氧化物后，用 CMP 把多余的氧化物磨平。
    pad=True 时播放抛光垫压下来的动画。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        for name in layers:
            lay = w.layers.get(name)
            if not lay:
                continue
            out = []
            for s in lay.solids:
                # 顶面不高于 z_top 的块不受影响（1e-9 是很小的容差，避免小数误差导致误判）。
                if s.zmax <= z_top + 1e-9 or not s.is_box:
                    out.append(s)
                    continue
                # 如果块的底部低于 z_top，保留 z_top 以下的部分。
                if s.zmin < z_top:
                    out.append(Solid.box(s.xmin, s.xmax, s.y0, s.y1, s.zmin, z_top))
                # 磨掉的部分播放消失动画。
                a.ghosts.append((lay.material, Solid.box(s.xmin, s.xmax, s.y0, s.y1,
                                                         max(s.zmin, z_top), s.zmax), "etch"))
            lay.solids = out
            if not out:
                w.remove(name)     # 整层都被磨光了，就把这层删掉
        if pad:
            a.pad = z_top
    return act


# geometry recipes shared by flows ---------------------------------------------
# 各个工艺流程共用的几何“小配方”：根据上下文算出常用区域

def actives(c: Ctx) -> List[Rect]:
    """返回两个有源区（NMOS 的和 PMOS 的）。"""
    return [c.lay["act_n"], c.lay["act_p"]]


def gate_span(c: Ctx, key: str) -> Tuple[float, float]:
    """Actual gate x-extent ("gn"/"gp"), honouring a POLY-mask misalignment so
    self-aligned implants follow the real gate.

    返回栅极实际在 x 方向的范围。如果 POLY（多晶硅栅）掩膜被设置了对准偏差，
    栅极会跟着偏移；“自对准”注入（以栅极本身作为遮挡）也要跟着真实栅极走。
    """
    g = c.lay[key]
    # 取 POLY 掩膜的偏移 (dx, dy) 里的 dx；没设置偏移就是 0。
    dx = c.faults.misalign.get("POLY", (0.0, 0.0))[0]
    return (g[0] + dx, g[1] + dx)


SPACER_W = 0.22          # spacer foot width (display units)（侧墙底部宽度）
GATE_Y = (1.1, ACT_Y[1])  # y-extent of the gate body (where sidewall spacers sit)（栅极主体的 y 范围）


def spacer_span(c: Ctx, key: str) -> Tuple[float, float]:
    """Gate x-extent widened by the sidewall spacers (mask for the deep S/D implant).

    栅极加上两侧侧墙后的 x 范围。侧墙（spacer）是贴在栅极两边的绝缘小墙，
    深源漏注入时它和栅极一起挡住离子，使深掺杂区离沟道远一点（减轻短沟道效应）。
    """
    g = gate_span(c, key)
    return (g[0] - SPACER_W, g[1] + SPACER_W)


def _gate_top(w: Wafer, layer: str, g: Tuple[float, float]) -> float:
    """找出栅极顶面的高度（侧墙要做到和栅极一样高）。找不到时默认 0.4。"""
    # 只看完全落在栅极 x 范围内的块（1e-6 是小数比较的容差），取它们顶面高度。
    tops = [s.zmax for s in w.layers[layer].solids
            if s.xmin >= g[0] - 1e-6 and s.xmax <= g[1] + 1e-6] if layer in w.layers else []
    return max(tops) if tops else 0.4


def _spacer_prism(edge: float, side: int, z0: float, z1: float, w: float, nseg: int = 6,
                  ys: Tuple[float, float] = GATE_Y) -> Solid:
    """Quarter-ellipse spacer cross-section against a gate edge (side=-1 left, +1 right).

    生成一个侧墙的立体形状：横截面是“四分之一椭圆”（底部宽、顶部窄、外侧圆弧），
    这正是真实侧墙经过各向异性回刻后的样子。side=-1 在栅极左边，+1 在右边。
    edge=栅极边缘 x；z0~z1=底部到顶部高度；w=底宽；nseg=圆弧分成几段；ys=y 方向范围。
    """
    import math              # 数学库（sin、cos、pi），只在这个函数里用到
    h = z1 - z0              # 侧墙高度
    # 用参数 t 从 0 到 90 度取 nseg+1 个点，画出四分之一椭圆弧：
    #   t=0 时点在栅极边缘顶部，t=90 度时点在底部最外侧。
    arc = [(edge + side * w * math.sin(t), z0 + h * math.cos(t))
           for t in (math.pi / 2 * k / nseg for k in range(nseg + 1))]
    # 把各点按逆时针顺序连成一个多边形轮廓（几何模块要求这种顺序）。
    if side < 0:      # CCW: foot -> corner -> top -> arc back to foot（逆时针：外脚 -> 内角 -> 顶 -> 沿弧回外脚）
        pts = [(edge - w, z0), (edge, z0)] + arc[:-1]
    else:
        pts = [(edge, z0), (edge + w, z0)] + list(reversed(arc))[1:-1] + [(edge, z1)]
    # 用这个轮廓在 y 方向拉伸成立体（*ys 把 (y0, y1) 摊开成两个参数）。
    s = Solid(pts, *ys)
    s.anchor = z0
    return s


def gate_keys(c: Ctx) -> List[Tuple[str, str]]:
    """(gate layer, layout span key) of every gate (one shared gate in a CFET).

    列出所有栅极：(栅极所在的层名, 版图里栅极范围的键名)。
    默认有 NMOS、PMOS 两个栅极；CFET（上下叠起来的互补晶体管）只有一个共用栅极，
    那时版图里会提供自己的 "gate_keys"。
    """
    return c.lay.get("gate_keys", [("gate_n", "gn"), ("gate_p", "gp")])


def _bands(c: Ctx) -> List[Tuple[float, float, float]]:
    """(y0, y1, z0) strips along the gate: where the spacer foot sits.  Planar
    devices have one strip on the silicon surface; in a FinFET the spacer reaches
    down to the STI between the fins.

    侧墙“脚”落在哪些条带上：(y 起点, y 终点, 底部高度)。
    平面晶体管只有一条，就在硅表面；FinFET 中，鳍之间的侧墙会一直延伸到更低的 STI 氧化层上。
    """
    return c.lay.get("spacer_bands", [(GATE_Y[0], GATE_Y[1], 0.0)])


def spacer_deposit(thickness=SPACER_W):
    """Conformal spacer film: planar film everywhere plus sidewall coverage of the gates.

    侧墙工艺第一步：整片沉积一层保形绝缘薄膜（通常是氮化硅或氧化硅）。
    平坦处薄一点，栅极两侧的竖直侧壁上也会盖上一层（这是之后形成侧墙的原料）。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        # 平坦表面上的薄膜（厚度取 0.6 倍，只为画面效果）。
        cells = conformal_cells(snapshot, [DOMAIN], DOMAIN, thickness=thickness * 0.6)
        # 每个栅极左右两侧各加一块竖直的“侧壁膜”。
        side = []
        for layer, key in gate_keys(c):
            g = gate_span(c, key)
            top = _gate_top(w, layer, g)
            # 左侧 (g[0]-厚度 ~ g[0]) 和右侧 (g[1] ~ g[1]+厚度)
            for x0, x1 in ((g[0] - thickness, g[0]), (g[1], g[1] + thickness)):
                for y0, y1, z0 in _bands(c):
                    b = Solid.box(x0, x1, y0, y1, z0, top + thickness * 0.6)
                    b.anchor = z0
                    side.append(b)
        w.layer("spacer_film", "spacer").solids = cells + side
        a.grow.extend(cells + side)
        a.particles.append(ParticleSpec("depo", (0.5, 0.85, 0.6, 1), None, 90, snapshot))
    return act


def spacer_etchback():
    """Anisotropic etch-back: the film is cleared from flat surfaces, leaving
    rounded spacers on the gate sidewalls.

    侧墙工艺第二步：各向异性回刻（只往下刻、不往旁边刻）。
    平坦处的薄膜全部被刻掉，而栅极侧壁上的竖直薄膜因为“竖着比较厚”会剩下一部分，
    形成两侧带圆弧的小墙——这就是侧墙（spacer）。
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        # 先把整层侧墙薄膜去掉，播放刻蚀动画。
        film = w.remove("spacer_film")
        if film:
            a.ghosts += [("spacer", s, "etch") for s in film.solids]
        # 再在每个栅极两侧、每个条带上生成四分之一椭圆形的侧墙。
        sp = []
        for layer, key in gate_keys(c):
            g = gate_span(c, key)
            top = _gate_top(w, layer, g)
            for y0, y1, z0 in _bands(c):
                sp.append(_spacer_prism(g[0], -1, z0, top, SPACER_W, ys=(y0, y1)))
                sp.append(_spacer_prism(g[1], +1, z0, top, SPACER_W, ys=(y0, y1)))
        w.layer("spacer", "spacer").solids = sp
        a.fade_in.extend(sp)
        a.particles.append(ParticleSpec("plasma", (1.0, 0.45, 0.85, 1), None, 140, w.solids()))
    return act


def sd_rects(act, g) -> List[Rect]:
    """源极/漏极（S/D）区域：有源区被栅极分成左右两块，栅极左边一块、右边一块。

    act=有源区矩形，g=栅极 x 范围。栅极下面不注入（那里是沟道）。
    """
    return [(act[0], g[0], act[2], act[3]), (g[1], act[1], act[2], act[3])]


def split_gates(w: Wafer, c: Ctx, a: PhaseAnim):
    """把整层多晶硅 "poly" 按位置拆成 NMOS 栅极和 PMOS 栅极两层。

    这本身就是一个动作函数（直接符合 Action 的格式，不需要工厂）。
    拆开后，后续工艺可以对两种栅极分别做不同的掺杂。x=10.5 是左右两半的分界线。
    """
    lay = w.remove("poly")
    if not lay:
        return
    w.layer("gate_n", lay.material).solids = [s for s in lay.solids if s.xmax < 10.5]
    w.layer("gate_p", lay.material).solids = [s for s in lay.solids if s.xmin >= 10.5]


def sd_annealed(act, g, grow=0.15, depth=-0.42):
    """退火后的源漏区形状：杂质横向扩散，向栅极下方伸进去一点（grow），也变得更深（depth）。

    源漏伸到栅极下面的这段“交叠”是真实存在的物理现象，会影响沟道的有效长度。
    """
    left = (act[0], g[0] + grow, act[2], act[3])
    right = (g[1] - grow, act[1], act[2], act[3])
    return [Solid.box(r[0], r[1], r[2], r[3], depth, 0.0) for r in (left, right)]


def gates(c):
    """所有栅极的矩形（NMOS 的 + PMOS 的），用作多晶硅刻蚀时要保留的区域。"""
    return c.lay["gates_n"] + c.lay["gates_p"]


def contacts(c):
    """所有接触孔的矩形（把字典里的值取出来变成列表）。"""
    return list(c.lay["contacts"].values())


def metal(c):
    """所有金属连线的矩形。"""
    return list(c.lay["metal"].values())


def litho(mask_keep, mask=None) -> List[Phase]:
    """光刻（lithography）的标准三连：涂胶 -> 对准曝光 -> 显影。

    几乎每次要“只在某些地方”做工艺时都需要光刻，所以把它包装成一个函数，
    返回三个 Phase，直接拼进工艺步骤里即可。mask_keep 是光刻胶要保留的区域。
    """
    return [
        Phase("旋涂光刻胶", "Spin-coat photoresist", 1.2, [coat()]),
        Phase("掩膜对准 + 紫外曝光", "Mask align + UV exposure", 2.2, [expose(mask_keep, mask=mask)]),
        Phase("显影：去除曝光区光刻胶", "Develop: exposed resist dissolves", 1.2, [develop()]),
    ]


def quiz(qzh, qen, opts, ans, ezh, een) -> Quiz:
    """创建测验的快捷写法：把分开传的中英文题目/解析打包成 Quiz 对象。"""
    return Quiz((qzh, qen), opts, ans, (ezh, een))


# --------------------------------------------------------------------------
# Formatting helpers for parameter tables
# 参数表的格式化工具：把数字变成好看的文字
# --------------------------------------------------------------------------

def sci(v: float, unit: str = "") -> str:
    """把数字写成科学计数法文字，例如 sci(3e15, "cm⁻²") -> "3.00e15 cm⁻²"。"""
    # 【语法】f-string：f"..." 里用 {变量:格式} 插入数值。".2e" 表示保留两位小数的科学计数法，
    # 例如 3e15 -> "3.00e+15"。再用 split("e") 拆成尾数 "3.00" 和指数 "+15"。
    m, e = f"{v:.2e}".split("e")
    # int(e) 把 "+15" 变成 15，去掉多余的加号和前导零；strip() 去掉没有单位时末尾的空格。
    return f"{m}e{int(e)} {unit}".strip()


# 缓存：电学计算比较耗时，相同参数算过一次就把结果存起来，下次直接用。
_SUM_CACHE: dict = {}


def summarize_cached(p: ProcessParams, features: FrozenSet[str] = frozenset()):
    """带缓存的 summarize：参数和特性完全相同时，直接返回上次的计算结果。

    界面刷新时会多次请求同一组结果（参数表、各种图都要用），缓存可以避免重复计算。
    """
    # 用“所有参数的 (名字, 值) 排序后组成的元组”+特性集合作为缓存的钥匙。
    # vars(p) 取出对象里所有字段组成的字典。
    key = (tuple(sorted(vars(p).items())), frozenset(features))
    if key not in _SUM_CACHE:
        # 只保留最近一次的结果（先清空），防止缓存越积越多占用内存。
        _SUM_CACHE.clear()
        _SUM_CACHE[key] = summarize(p, features)
    return _SUM_CACHE[key]


def nwe_text(c: Ctx) -> str:
    """NMOS narrow-width Vt shift caused by the flow's isolation scheme.

    计算“窄沟道效应”造成的 NMOS 阈值电压变化，并格式化成文字。
    阈值电压 Vt：让晶体管开始导通所需的栅极电压。
    窄沟道效应：晶体管很窄时，隔离结构（LOCOS 或 STI）的边缘会改变 Vt。
    做法：分别算“有隔离效应”和“去掉隔离效应”两种情况，相减就是隔离带来的影响。
    """
    s = summarize_cached(c.p, c.features)
    base = summarize_cached(c.p, frozenset(c.features) - {"locos", "sti"})   # same, minus isolation（去掉隔离特性再算一次）
    # 乘 1e3 把伏特换成毫伏；":+.0f" 表示总是显示正负号、不保留小数。
    return f"{(s.vtn - base.vtn) * 1e3:+.0f} mV  (Wn = {c.p.wn_um:.1f} µm)"


def vt_text(c: Ctx, which: str) -> str:
    """返回 NMOS（which='n'）或 PMOS 的阈值电压文字，例如 "+0.700 V"。"""
    s = summarize_cached(c.p, c.features)
    return f"{(s.vtn if which == 'n' else s.vtp):+.3f} V"


# --------------------------------------------------------------------------
# Building state
# 构建状态：把工艺步骤一步步“执行”到晶圆上
# --------------------------------------------------------------------------

def run_phase(w: Wafer, ctx: Ctx, phase: Phase) -> PhaseAnim:
    """执行一个动画小阶段里的所有动作，返回收集好的动画说明书。"""
    anim = PhaseAnim()
    # 依次调用每个动作函数；它们会修改晶圆 w，并往 anim 里写动画信息。
    for act in phase.actions:
        act(w, ctx, anim)
    return anim


def is_skipped(ctx: Ctx, step: Step) -> bool:
    """这一步是否被故障模式设置成“跳过”。"""
    return step.key in ctx.faults.skip


def build_until(ctx: Ctx, step_index: int) -> Wafer:
    """Wafer state after completing ctx.flow.steps[0..step_index] (inclusive).

    从一片全新的晶圆开始，按顺序执行第 0 步到第 step_index 步（包括这一步），
    返回此时的晶圆状态。用户在界面上跳到某一步时，就用它快速“重放”出那一刻的晶圆。
    （这里只要结果，不播放动画，所以 run_phase 返回的动画说明书被丢弃了。）
    """
    w = Wafer()
    # 【语法】列表切片 steps[: n]：取从开头到第 n-1 个元素。这里 n = step_index + 1，
    # 所以正好包含第 step_index 步。
    for st in ctx.flow.steps[: step_index + 1]:
        if is_skipped(ctx, st):
            continue          # 被跳过的步骤不执行（模拟“漏做了一步”）
        w.current_step = st.key   # 记下当前步骤，注入/退火事件会用到
        for ph in st.phases:
            run_phase(w, ctx, ph)
    return w
