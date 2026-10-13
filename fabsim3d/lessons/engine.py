"""Guided-lesson engine (pure python, no Panda3D).

A Lesson is a list of Tasks.  Each task explains an idea, asks the student to
do something ("try"), detects when it has been done (check), and then explains
what changed (observe), comparing the state when the task started with the
state when it was completed.

【中文说明】实验课的“引擎”（只用纯 Python，不依赖 3D 图形库，所以可以单独测试）。

一节课（Lesson）由若干个任务（Task）组成。每个任务分四步：
    1. explain：先用打比方的方式讲一个概念；
    2. try_：请学生动手做一件事（比如“把 Vin 拖到 0 V 附近”）；
    3. check：程序不断检查学生是否做到了；
    4. observe：做到后，比较“任务开始时”和“完成时”的两个状态，解释发生了什么变化。

本文件定义：
    LabState     实验状态的“快照”：当前用的工艺、参数、输入电压等；
    Task         一个任务包含的全部内容；
    Lesson       一节课；
    LessonRunner 上课过程的“进度管理员”：记住做到第几个任务、哪些已完成、每个任务开始时的状态；
    apply_demo   “帮我做”按钮的效果。
界面部分（guide_ui.py / app.py）负责显示这些内容，并把学生的操作转成 LabState 交给这里判断。
"""
# 让类型注解可以写尚未定义的类名（如在 LabState 里写 "LabState"），属于技术细节
from __future__ import annotations

# dataclass：自动为“主要用来装数据的类”生成构造函数等代码，省去大量重复书写
# field：给 dataclass 的某个字段设置特殊默认值；replace：复制一个对象并修改其中几个字段
from dataclasses import dataclass, field, replace
# typing 里的名字只用于“类型注解”，即说明变量应该是什么类型，帮助阅读，不影响运行
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

# 两个点 .. 表示上一级包（fabsim3d）：
# 器件模型（根据工艺参数算晶体管电流、反相器输出等）和带缓存的电学汇总计算
from ..device_model import ProcessParams, inverter_vout, nmos, pmos
from ..process_core import summarize_cached

# 所有给学生看的文字都写成 (中文, 英文) 两段，这里给这种类型起个短名字 Text
Text = Tuple[str, str]          # (zh, en)


# @dataclass 写在类的上方，是“装饰器”：它会根据下面列出的字段，自动生成构造函数，
# 所以可以直接写 LabState(flow, features, done, p, vin) 来创建对象。
# “字段名: 类型 = 默认值”的写法中，有默认值的字段创建时可以不填。
@dataclass
class LabState:
    """Snapshot of everything a task may look at.

    实验状态快照：任务判断“完成了没有”时需要看的全部信息。
    字段含义：
        flow         当前工艺流程名（如 "locos"、"sti"）
        features     工艺特性集合（如是否有 LDD、是否计算短沟道效应），影响电学计算
        done         工艺是否已全部做完（做完才有器件可以测量）
        p            全部工艺参数（栅氧厚度、掺杂、栅长、电源电压等）
        vin          反相器的输入电压 Vin（学生用滑块调节）
        plot         当前显示哪张曲线图（"vtc" 电压传输曲线、"idvg" 等）
        tran_played  是否播放过“开关一瞬间”的动画
        ack          学生是否点过“确认/开始”按钮
    """
    flow: str
    features: FrozenSet[str]
    done: bool                  # process finished (device exists)
    p: ProcessParams
    vin: float
    plot: str = "vtc"
    tran_played: bool = False
    ack: bool = False

    def copy(self) -> "LabState":
        """复制一份状态。工艺参数 p 也要单独复制，否则两份状态会共用同一个参数对象，
        改一个另一个也跟着变，就无法比较“改之前”和“改之后”了。"""
        return replace(self, p=self.p.copy())

    # @property 让方法可以像普通属性一样使用：写 state.s 而不是 state.s()。
    # 下面几个属性都是“需要时现算”的电学结果，所以不用存储，参数一变结果自然跟着变。
    @property
    def s(self):
        """整个反相器的电学汇总（阈值 vtn/vtp、翻转点、延迟等），有缓存，重复调用很快。"""
        return summarize_cached(self.p, self.features)

    @property
    def mn(self):
        """按当前参数建立的 NMOS 晶体管模型（可以查询它的阈值、电流等）。"""
        return nmos(self.p, self.features)

    @property
    def mp(self):
        """按当前参数建立的 PMOS 晶体管模型。"""
        return pmos(self.p, self.features)

    @property
    def vout(self) -> float:
        """当前输入电压 Vin 下反相器的输出电压 Vout。
        inverter_vout 可以一次算很多个输入，返回一组结果，[0] 取其中第一个；float 转成普通小数。"""
        return float(inverter_vout(self.p, self.vin, features=self.features)[0])

    @property
    def id_n(self) -> float:
        """NMOS current at the current Vin with |Vds| = VDD (as on the Id-Vg plot).

        当前 Vin 作为栅压、漏源电压等于电源电压时 NMOS 的电流，与 Id-Vg 曲线图上的读数一致。"""
        return float(self.mn.ids(self.vin, self.p.vdd))


@dataclass
class Task:
    """一个实验任务的全部内容（字段说明见每行右侧注释）。

    check 和 observe 不是普通数值，而是“函数”：Python 里函数也可以像数据一样存起来、传来传去。
    它们都接收两个状态 (开始时, 现在/结束时)，所以任务可以判断“学生把某个参数改大了吗”这类问题。
    controls 列出这个任务需要在界面上显示哪些控件：
        "param:<key>" 某个工艺参数的滑块，"vin" 输入电压滑块，"btn:tran" 播放开关动画按钮，"btn:ack" 确认按钮。
    """
    title: Text
    explain: Text                       # why / analogy (zero-background friendly)（为什么 / 打比方）
    # 名字末尾的 _ 是为了避开 Python 的关键字 try（关键字不能用作名字）
    try_: Text                          # the action asked of the student（要学生做的操作）
    check: Callable[[LabState, LabState], bool]          # (start, now) -> done?（完成了吗？）
    observe: Callable[[LabState, LabState], Text]        # (start, end) -> explanation（完成后的解释文字）
    # default_factory=list 表示每个任务各自得到一个新的空列表（直接写 = [] 会让所有任务共用同一个列表）
    controls: List[str] = field(default_factory=list)    # "param:<key>", "vin", "btn:tran", "btn:ack"
    demo: Optional[Callable[[LabState], Dict]] = None     # what "do it for me" applies（“帮我做”要执行的改动）
    plot: Optional[str] = None          # plot to show for this task（本任务显示哪张图）
    compare: bool = True                # draw the start state as a grey reference curve（画灰色“改之前”曲线）
    deep: Optional[Text] = None         # optional formula-level explanation（可选的公式级深入解释）


@dataclass
class Lesson:
    """一节实验课。

    key      课程的内部名字（如 "switch"），用于记录哪些课已完成
    title    标题；summary 课程列表里显示的一句话简介；intro 开场介绍
    flow     这节课使用哪套工艺流程
    tasks    任务列表（按顺序做）
    sim3d    是否自动打开 3D 载流子仿真
    """
    key: str
    title: Text
    summary: Text
    intro: Text
    flow: str
    tasks: List[Task]
    sim3d: bool = False


class LessonRunner:
    """上课进度管理员：跟踪当前做到第几个任务、哪些任务已完成，
    并记住每个任务“开始时”和“完成时”的状态，供判断完成和写观察说明使用。"""

    def __init__(self, lesson: Lesson):
        """开始一节课：从第 0 个任务开始，所有任务都标记为未完成。"""
        self.lesson = lesson
        # idx 是当前任务的编号（Python 从 0 开始数）
        self.idx = 0
        # [False] * n 生成 n 个 False 组成的列表：每个任务一个“已完成”标记
        self.done = [False] * len(lesson.tasks)
        # 每个任务开始/完成时的状态快照，还没有时是 None（表示“空”）
        self.start_states: List[Optional[LabState]] = [None] * len(lesson.tasks)
        self.end_states: List[Optional[LabState]] = [None] * len(lesson.tasks)

    @property
    def task(self) -> Task:
        """当前正在做的任务。"""
        return self.lesson.tasks[self.idx]

    @property
    def finished(self) -> bool:
        """整节课是否全部完成：all(...) 在列表里每一项都为 True 时才为 True。"""
        return all(self.done)

    def begin(self, state: LabState):
        """(Re)start the current task from `state`.

        （重新）开始当前任务：把此刻的状态复制一份存为“开始状态”，之后用来和学生改动后的状态比较。"""
        self.start_states[self.idx] = state.copy()

    def poll(self, state: LabState) -> bool:
        """Check the current task; returns True exactly when it becomes done.

        检查当前任务是否完成。界面会频繁调用它；只有在“刚刚完成”的那一次返回 True，
        这样界面只会弹出一次“完成啦”的说明，而不会反复弹出。
        """
        # 已经完成过的任务不再重复判断
        if self.done[self.idx]:
            return False
        # “a or b”：如果还没有开始状态（a 是 None），就退而用当前状态代替
        start = self.start_states[self.idx] or state
        # 调用任务自带的判断函数；完成了就记下标记和完成时的状态快照
        if self.task.check(start, state):
            self.done[self.idx] = True
            self.end_states[self.idx] = state.copy()
            return True
        return False

    def observation(self) -> Optional[Text]:
        """返回当前任务完成后的“观察说明”文字；任务还没完成时返回 None（不显示）。"""
        if not self.done[self.idx]:
            return None
        # 把“开始时”和“完成时”两个状态交给任务的 observe 函数，生成带具体数值的解释
        return self.task.observe(self.start_states[self.idx], self.end_states[self.idx])

    def go(self, idx: int, state: LabState):
        """跳到第 idx 个任务（点“上一个/下一个”时调用）。

        max(0, min(idx, 最后编号)) 把编号限制在有效范围内，防止越界。
        如果跳到的任务还没完成，就以当前状态作为它的新起点；已完成的任务保留原来的记录。
        """
        self.idx = max(0, min(idx, len(self.lesson.tasks) - 1))
        if not self.done[self.idx]:
            self.begin(state)

    @property
    def reference(self) -> Optional[LabState]:
        """State to draw as the grey 'before' curve.

        曲线图上用灰色画出的“改之前”参考曲线所对应的状态，即当前任务的开始状态。
        有些任务（compare=False）不需要对比，就返回 None，不画灰线。
        """
        if not self.task.compare:
            return None
        return self.start_states[self.idx]


def apply_demo(state: LabState, demo: Dict) -> LabState:
    """Apply a task's 'do it for me' action to a state (the app mirrors this on its widgets).

    执行“帮我做”：根据 demo 字典里写的改动，生成一个新的状态（原状态不变）。
    界面那边会把同样的改动同步到滑块和按钮上，让学生看到“程序替我做了什么”。
    demo 字典里可能有这些键：
        "params" 要修改的工艺参数，如 {"tox_nm": 8.0}
        "vin"    要设置的输入电压
        "tran"   为 True 表示播放开关动画
        "ack"    为 True 表示点了确认按钮
    """
    st = state.copy()
    if "params" in demo:
        # ** 把字典“展开”成关键字参数：copy(**{"tox_nm": 8.0}) 等同于 copy(tox_nm=8.0)
        st.p = st.p.copy(**demo["params"])
        # 如果电源电压被调低了，Vin 不能超过新的电源电压
        st.vin = min(st.vin, st.p.vdd)
    if "vin" in demo:
        st.vin = float(demo["vin"])
    # demo.get(键) 在键不存在时返回 None（视为假），不会报错
    if demo.get("tran"):
        st.tran_played = True
    if demo.get("ack"):
        st.ack = True
    return st
