"""Main Panda3D application: three-column teaching UI around the 3D wafer."""
# ======================================================================
# 【这个文件是干什么的？】（中文说明）
# 这是整个程序的“主窗口”。运行 FabSim3D 时，最终打开的那个窗口就是这里的 CmosApp 类创建的。
# 窗口分成三栏：
#   · 左栏：工艺步骤列表（第 1 步、第 2 步……）、播放/上一步/下一步按钮、视图开关；
#   · 中间：3D 晶圆（wafer，就是做芯片用的硅片）的立体动画，可以用鼠标旋转、缩放；
#   · 右栏：几个“标签页”：工艺说明、电学曲线图、可调参数、引导模式。
# 它本身不负责具体的物理计算或 3D 建模，而是像“总指挥”一样把其它文件串起来：
#   · process_core.py：一步步执行工艺（长氧化层、光刻、刻蚀、注入……），得到晶圆的状态；
#   · scene.py：把晶圆状态画成 3D 画面并播放动画；
#   · device_model.py：根据工艺参数算出晶体管（NMOS/PMOS）和反相器的电学特性；
#   · plots.py：把电学结果画成曲线图片；
#   · i18n.py：中英文切换；guide_ui.py：引导模式的界面。
# 小知识：CMOS 反相器 = 一个 NMOS + 一个 PMOS 串联，输入高电平时输出低电平，反之亦然，
# 是数字芯片里最基本的“非门”。这个程序演示的就是怎样在硅片上一步步把它“造”出来。
# ======================================================================
# 下面这行让类型标注（例如 key: str）不会在运行时被立即求值，属于 Python 的兼容性写法，可以忽略。
from __future__ import annotations

# ---- 导入（import）：把别的代码库/文件里的功能“借”过来用 ----
# math：数学函数（sin、cos、log 等）；re：正则表达式，用来按规则切分文字；time：读取当前时间。
import math
import re
import time

# direct.* 和 panda3d.* 都来自 Panda3D —— 一个开源的 3D 游戏/图形引擎。
# DirectGui 系列是它自带的界面控件：按钮(DirectButton)、面板(DirectFrame)、
# 可滚动面板(DirectScrolledFrame)、滑块(DirectSlider)。"as DGG" 表示起个短名字方便书写。
from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import (DirectButton, DirectFrame, DirectScrolledFrame,
                                  DirectSlider)
# OnscreenImage / OnscreenText：直接显示在屏幕上的图片和文字；ShowBase：Panda3D 程序的“基础窗口”类。
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
# panda3d.core 里的各种基础零件：灯光、文件路径、二维/三维坐标点(Point2/Point3/Vec3)、
# 文字节点(TextNode)、文字样式、贴图(Texture)、透明度设置等。
from panda3d.core import (AmbientLight, DirectionalLight, Filename, Point2, Point3, TextNode,
                          TextProperties, TextPropertiesManager, Texture, TransparencyAttrib, Vec3)

# 下面以 "." 开头的是“相对导入”：从本项目（fabsim3d 文件夹）里的其它文件导入。
#   i18n / tr：中英文翻译；device_model：晶体管电学模型（nmos/pmos/反相器输出电压）；
#   fonts：找中文字体；materials：各种材料（硅、氧化层、多晶硅、金属……）的颜色和说明；
#   plots：画电学曲线；flows：不同“工艺代”（老工艺 → 先进工艺）的步骤清单；
#   process_core：真正执行每个工艺步骤的核心；guide_ui：引导模式；scene：3D 场景。
from . import i18n
from .device_model import ProcessParams, inverter_vout, nmos, pmos
from .fonts import find_cjk_font
from .i18n import tr
from .materials import MATERIALS, mat
from .plots import PlotRenderer, setup_fonts
from .flows import DEFAULT_FLOW, FLOWS
from .process_core import Wafer, build_until, is_skipped, make_ctx, run_phase, sci, summarize_cached
from .guide_ui import GuideMixin
from .scene import WaferScene

# ↓ 界面配色。每个颜色写成 (红, 绿, 蓝, 不透明度)，取值 0~1。
#   用圆括号括起来、逗号分隔的一组值叫“元组(tuple)”，创建后不能修改，适合当常量。
#   全大写的变量名是约定俗成的“常量”写法，表示程序运行中不会去改它。
# ---------------------------------------------------------------- style
# BG3D：中间 3D 区域背景色；PANEL：左右面板底色；BTN*：按钮在普通/悬停/按下/选中时的颜色；
# TXT/TXT2：主要文字和次要（灰色）文字；ACCENT：强调用的黄色；DONE_COL：已完成步骤的绿色。
BG3D = (0.17, 0.18, 0.21, 1)
PANEL = (0.085, 0.09, 0.105, 0.97)
BTN = (0.20, 0.21, 0.25, 1)
BTN_HOVER = (0.28, 0.30, 0.36, 1)
BTN_PRESS = (0.14, 0.15, 0.18, 1)
BTN_ON = (0.20, 0.45, 0.82, 1)
TXT = (0.93, 0.93, 0.93, 1)
TXT2 = (0.70, 0.71, 0.74, 1)
ACCENT = (1.0, 0.82, 0.35, 1)
DONE_COL = (0.15, 0.30, 0.22, 1)

# 自动换行时，这些标点不能出现在一行的开头（中文排版规则，避免一行以“，”或“。”开头）。
# set(...) 把字符串拆成单个字符组成的“集合”，查找某个字符在不在里面非常快。
NO_LINE_START = set("，。、；：！？）》」』”’,.;:!?)%")   # never begin a wrapped line with these

# 左右两栏的宽度（Panda3D 的屏幕坐标单位，窗口高度对应 2.0），以及电学曲线图片的像素大小。
LEFT_W = 0.74
RIGHT_W = 0.94
PLOT_W, PLOT_H = 540, 400

# 中文：参数滑块的配置表。每一行是一个元组：(参数名, 翻译用的键, 最小值, 最大值, 是否用对数刻度)。
#   对数刻度：像掺杂浓度这种从 1e15 到 1e18（相差 1000 倍）的量，用对数滑动才均匀好调。
#   1e15 是科学计数法，表示 1×10^15。
#   各参数的物理含义：
#     tox_nm        栅氧化层厚度（纳米）。栅极下面那层很薄的绝缘 SiO2，越薄栅极对沟道控制越强、电流越大。
#     na_cm3        衬底（P 型硅）的掺杂浓度（每立方厘米多少个杂质原子），主要影响 NMOS 的阈值电压。
#     nwell_dose    N 阱注入剂量（每平方厘米注入多少离子），N 阱是 PMOS 所在的区域。
#     l_um          栅长 L（微米）：源极到漏极之间沟道的长度，越短越快，但“短沟道效应”越明显。
#     wn_um/wp_um   NMOS / PMOS 的栅宽 W，越宽能流过的电流越大。
#     vdd           电源电压（伏特）。
#     cload_ff      反相器输出端接的负载电容（飞法 fF，1fF = 1e-15 法拉），决定开关速度。
# parameter sliders: key, i18n key, lo, hi, log-scale
PARAM_SLIDERS = [
    ("tox_nm", "p_tox", 2.0, 40.0, False),
    ("na_cm3", "p_na", 1e15, 1e18, True),
    ("nwell_dose_cm2", "p_dose", 2e12, 2e14, True),
    ("l_um", "p_l", 0.18, 5.0, False),
    ("wn_um", "p_wn", 0.5, 20.0, False),
    ("wp_um", "p_wp", 0.5, 20.0, False),
    ("vdd", "p_vdd", 0.8, 5.0, False),
    ("cload_ff", "p_cl", 1.0, 500.0, False),
]


# ======================================================================
# CmosApp：整个程序的主类。
#   “类(class)”可以理解为一张设计图，里面打包了数据（属性）和操作（方法/函数）。
#   括号里的 GuideMixin, ShowBase 表示“继承”：CmosApp 自动拥有这两个类的全部功能。
#     · ShowBase 来自 Panda3D，提供窗口、摄像机、渲染循环、键盘鼠标事件等；
#     · GuideMixin 来自 guide_ui.py，提供“引导模式”相关的方法（_guide_init、toggle_guide 等）。
# ======================================================================
class CmosApp(GuideMixin, ShowBase):
    """CmosApp 主应用：三栏教学界面 + 中间的 3D 晶圆。

    负责：创建窗口和界面、管理“当前演示到第几步工艺”、响应鼠标键盘、
    定时刷新动画和电学曲线。具体的工艺计算和 3D 绘制交给其它模块。
    """
    def __init__(self, opts=None):
        """程序启动时运行一次的“初始化”函数（__init__ 是 Python 规定的名字，创建对象时自动调用）。

        self 代表“这个对象自己”，self.xxx = ... 就是把数据存到对象身上，以后其它方法都能读到。
        opts：命令行传进来的选项字典，例如 {"flow": "..."} 用来选择工艺代；不传则为 None。
        """
        ShowBase.__init__(self)
        # 上一行：先让父类 ShowBase 完成窗口创建等基础工作。
        # "opts or {}"：如果 opts 是 None（空），就用一个空字典 {} 代替，避免后面出错。
        self.opts = opts or {}
        # disableMouse()：关掉 Panda3D 自带的鼠标控制摄像机，我们下面自己实现旋转/平移/缩放。
        # *BG3D：星号把元组“拆开”成多个参数传入，相当于 setBackgroundColor(0.17, 0.18, 0.21, 1)。
        self.disableMouse()
        self.setBackgroundColor(*BG3D)
        self.setFrameRateMeter(False)

        # ---- 加载中文字体 ----
        # Panda3D 默认字体没有汉字，所以要找系统里的中文字体；找到就设为所有界面文字的默认字体。
        # 找不到的话打印提示，并把界面语言切换成英文（否则汉字会显示成方块）。
        font_path = find_cjk_font()
        self.font = None
        if font_path:
            self.font = self.loader.loadFont(Filename.fromOsSpecific(font_path).getFullpath())
            self.font.setPixelsPerUnit(56)
            DGG.setDefaultFont(self.font)
            TextNode.setDefaultFont(self.font)
        else:
            print("[fabsim3d] 未找到中文字体，可设置环境变量 FABSIM3D_FONT 或放入 fonts/ 目录; "
                  "no CJK font found, falling back to English")
            i18n.set_lang("en")
        # 画电学曲线的 matplotlib 也要用同一个字体，才能在图里显示中文。
        setup_fonts(font_path)

        # ---- 工艺流程和参数 ----
        # flow：选用哪一代工艺（步骤清单不同）；params：该工艺的默认参数（氧化层厚度、栅长等）。
        # ctx：“工艺上下文”，把参数换算成工艺执行时需要的各种尺寸/数值；scene：负责 3D 画面的对象。
        self.flow = FLOWS[(opts or {}).get("flow") or DEFAULT_FLOW]
        self.params = self.flow.default_params()
        self.ctx = self._new_ctx()
        self.scene = WaferScene(self, self.render)
        self._setup_lights()

        # 中文：摄像机“环绕”参数 —— 摄像机始终看着 cam_target 这个点，
        # cam_h 是水平转角（度），cam_p 是俯仰角（度），cam_d 是离目标点的距离。
        # "a, b, c = 1, 2, 3" 是一次给多个变量赋值的写法。
        # drag 记录当前鼠标拖动的模式（旋转/平移/无），last_mouse 记录上一帧鼠标位置。
        # camera orbit state
        self.cam_target = Vec3(10.0, 4.0, -0.4)
        self.cam_h, self.cam_p, self.cam_d = -28.0, 30.0, 36.0
        self.drag = None
        self.last_mouse = None

        # 中文：鼠标悬停“拾取”：鼠标指到哪一层材料，就弹出提示框告诉你它叫什么、有什么用。
        # hover_next 是下次允许重新计算的时间，避免每一帧都做耗时的射线检测。
        # hover picking: which layer is under the mouse
        self.hover_layer = None
        self.hover_key = None
        self.hover_next = 0.0
        self.legend_texts = {}
        # 创建悬停提示框：TextNode 是文字对象，这里设置文字颜色、蓝色底板(card)、黄色边框，
        # 再挂到 aspect2d（2D 界面层，覆盖在 3D 画面之上）。setBin 让它画在最上层，不被别的界面挡住。
        tn = TextNode("hover_tip")
        tn.setTextColor(*TXT)
        tn.setCardColor(0.10, 0.20, 0.42, 0.95)      # unlike the black region labels
        tn.setCardAsMargin(0.35, 0.35, 0.2, 0.15)
        tn.setCardDecal(True)
        tn.setFrameColor(*ACCENT)
        tn.setFrameAsMargin(0.35, 0.35, 0.2, 0.15)
        self.hover_tip = self.aspect2d.attachNewNode(tn)
        self.hover_tip.setScale(0.032)
        self.hover_tip.setBin("gui-popup", 60)
        self.hover_tip.hide()
        # 提示框第一行（材料名）用黄色：TextNode 支持在文字里用 \1名字\1 ... \2 切换样式，
        # 这里先登记一个叫 "hov_title" 的样式 / a yellow style for the tooltip title
        title_style = TextProperties()
        title_style.setTextColor(*ACCENT)
        TextPropertiesManager.getGlobalPtr().setProperties("hov_title", title_style)

        # 中文：工艺播放状态。
        #   step：当前已完成到第几步（从 0 开始数）；anim_step：正在播放动画的那一步（没在播放时为 None）；
        #   phase_queue：一步工艺通常分成几个“阶段”（例如：涂胶→曝光→显影），这里排队等待播放；
        #   caption：当前阶段的中英文说明；wafer：当前晶圆的状态（有哪些材料层、形状如何）；
        #   playing：是否在自动连续播放；play_wait：两步之间停顿的倒计时；speed：播放速度倍数。
        # process state
        self.step = 0
        self.anim_step = None
        self.phase_queue = []
        self.caption = ("", "")
        self.wafer = None
        self.playing = False
        self.play_wait = 0.0
        self.speed = 1.0

        # 中文：小测验。quiz_results 用字典记录每一步答对(True)/答错(False)；quiz_frame 是弹出的测验窗口。
        # quiz
        self.quiz_enabled = False
        self.quiz_results = {}
        self.quiz_frame = None
        self.resume_after_quiz = False

        # 中文：电学相关状态。
        #   right_tab：右栏当前显示哪个标签页；plot_kind：当前画哪种曲线（vtc = 电压传输特性曲线）；
        #   vin：反相器的输入电压，默认取电源电压的一半；sim3d：是否在 3D 里显示载流子（电子/空穴）流动；
        #   tran_t：瞬态（随时间变化）动画已播放的时间，None 表示没在播放；
        #   plot_dirty / params_dirty：“脏标记”，表示数据变了、需要重画/重算（攒到一起做，避免卡顿）。
        #   最后创建画图器和一张贴图(Texture)，曲线图片会被拷贝进这张贴图显示在右栏。
        # electrical
        self.right_tab = "process"
        self.plot_kind = "vtc"
        self.vin = self.params.vdd / 2
        self.sim3d = False
        self.tran_t = None
        self.plot_dirty = True
        self.params_dirty = False
        self.last_plot = 0.0
        self.renderer = PlotRenderer(PLOT_W, PLOT_H)
        self.plot_tex = Texture("plot")
        self.plot_tex.setup2dTexture(PLOT_W, PLOT_H, Texture.TUnsignedByte, Texture.FRgba8)

        # 初始化引导模式（方法来自 GuideMixin）；cut_on / cut_y：是否开启“剖面”以及剖切位置，
        # 剖开晶圆才能看到内部一层层的结构。
        self._guide_init()
        self.cut_on = True
        self.cut_y = 3.5
        self.scene.cut_y = self.cut_y

        # ui_roots 保存左右两个面板，切换语言/工艺时可以整体销毁重建。
        # 然后：搭建界面 → 显示第 0 步 → 调整 3D 视口大小 → 放好摄像机。
        self.ui_roots = []
        self.build_ui()
        self.goto(0)
        self.layout_viewport()
        self.update_camera()

        # ---- 绑定事件 ----
        # self.accept("事件名", 函数, [额外参数])：当事件发生时自动调用这个函数（叫“回调”）。
        #   mouse1 = 鼠标左键（拖动旋转），mouse3 = 右键（拖动平移），wheel = 滚轮（缩放），
        #   方向键左右 = 上一步/下一步，空格 = 播放/暂停。
        # taskMgr.add(self._tick, "tick")：注册一个“每帧都会被调用”的任务，动画就靠它推进。
        self.accept("window-event", self._on_window)
        self.accept("mouse1", self._drag_start, ["rot"])
        self.accept("mouse3", self._drag_start, ["pan"])
        self.accept("mouse1-up", self._drag_end)
        self.accept("mouse3-up", self._drag_end)
        self.accept("wheel_up", self._zoom, [0.9])
        self.accept("wheel_down", self._zoom, [1.1])
        self.accept("arrow_right", self.next_step)
        self.accept("arrow_left", self.prev_step)
        self.accept("space", self.toggle_play)
        self.taskMgr.add(self._tick, "tick")
        self.last_time = time.time()

    # ================================================================= scene
    # ================= 3D 场景：灯光、视口、摄像机、鼠标交互 =================
    def _setup_lights(self):
        """给 3D 场景加灯光：一盏均匀的环境光 + 两盏方向光（主光和补光），让立体感更清楚。"""
        amb = AmbientLight("amb")
        amb.setColor((0.48, 0.48, 0.52, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        # for hpr, c in (...)：循环时把每个元组拆成两个变量。hpr 是光照方向（水平角, 俯仰角, 翻滚角），
        # c 是亮度。第一盏是较亮的主光，第二盏是从背后来的较暗补光。
        for hpr, c in (((-35, -50, 0), 0.62), ((140, -30, 0), 0.25)):
            d = DirectionalLight("dir")
            d.setColor((c, c, c, 1))
            np_ = self.render.attachNewNode(d)
            np_.setHpr(*hpr)
            self.render.setLight(np_)

    def layout_viewport(self):
        """把 3D 画面限制在左右两栏中间的区域，并根据窗口宽高比调整镜头，避免画面被拉伸。"""
        if not self.win:
            return
        w, h = self.win.getXSize(), self.win.getYSize()
        if w <= 0 or h <= 0:
            return
        # 显示区域用 0~1 的比例表示窗口宽度。left/right 是中间区域的左右边界：
        # 左栏和右栏各占一部分宽度，剩下的给 3D；min/max 保证窗口很窄时 3D 区域也不会小到没有。
        aspect = w / h
        left = LEFT_W / (2 * aspect)
        right = 1 - RIGHT_W / (2 * aspect)
        left, right = min(left, 0.45), max(right, 0.55)
        # 设置显示区域、镜头宽高比和视野角(FOV 40 度)，并记下中间区域范围（判断鼠标是否在 3D 区里用）。
        dr = self.cam.node().getDisplayRegion(0)
        dr.setDimensions(left, right, 0, 1)
        self.camLens.setAspectRatio((right - left) * w / h)
        self.camLens.setFov(40)
        self.view_frac = (left, right)

    def _on_window(self, win):
        """窗口大小改变（例如用户拖动窗口边缘）时被调用，重新计算 3D 区域的布局。"""
        if win == self.win:
            self.layout_viewport()

    def update_camera(self):
        """根据环绕角度和距离，用三角函数算出摄像机的位置，并让它对准目标点。

        这是“球坐标 → 直角坐标”的换算：已知方向角和距离，求 x/y/z。
        """
        h, p = math.radians(self.cam_h), math.radians(self.cam_p)
        off = Vec3(math.cos(p) * math.sin(h), -math.cos(p) * math.cos(h), math.sin(p)) * self.cam_d
        self.camera.setPos(self.cam_target + off)
        self.camera.lookAt(self.cam_target)

    def set_cam(self, preset):
        """切换到预设视角："iso"（斜 45° 立体）、"front"（正面看剖面）、"top"（俯视）。"""
        self.cam_target = Vec3(10.0, 4.0, -0.4)
        # {...}[preset]：先写一个字典，再立刻用 preset 作为键取出对应的 (水平角, 俯仰角, 距离)。
        self.cam_h, self.cam_p, self.cam_d = {
            "iso": (-28.0, 30.0, 36.0), "front": (0.0, 4.0, 30.0), "top": (0.0, 88.0, 32.0)}[preset]
        self.update_camera()

    def _mouse_in_view(self):
        """判断鼠标是否在中间的 3D 区域里（而且没有弹出测验窗口），只有这时鼠标才控制摄像机。"""
        if self.mouseWatcherNode is None or not self.mouseWatcherNode.hasMouse():
            return False
        # 鼠标 X 坐标原本是 -1(最左)~1(最右)，换算成 0~1，再和 3D 区域的左右边界比较。
        x = (self.mouseWatcherNode.getMouseX() + 1) / 2
        return self.view_frac[0] <= x <= self.view_frac[1] and self.quiz_frame is None

    def _drag_start(self, mode):
        """按下鼠标键时调用：mode 为 "rot"（左键旋转）或 "pan"（右键平移），并记住起点位置。"""
        if self._mouse_in_view():
            self.drag = mode
            m = self.mouseWatcherNode.getMouse()
            self.last_mouse = (m.x, m.y)

    def _drag_end(self):
        """松开鼠标键时调用：结束拖动。"""
        self.drag = None

    def _zoom(self, f):
        """滚轮缩放：f 小于 1 拉近，大于 1 拉远；min/max 把距离限制在 8~90 之间，防止穿模或飞太远。"""
        if self._mouse_in_view():
            self.cam_d = min(max(self.cam_d * f, 8.0), 90.0)
            self.update_camera()

    def _handle_drag(self):
        """每帧调用：如果正在拖动，就根据鼠标移动的距离旋转或平移摄像机。"""
        if not self.drag or not self.mouseWatcherNode.hasMouse():
            return
        # dx, dy：这一帧鼠标移动了多少。
        m = self.mouseWatcherNode.getMouse()
        dx, dy = m.x - self.last_mouse[0], m.y - self.last_mouse[1]
        self.last_mouse = (m.x, m.y)
        # 旋转：左右移动改变水平角，上下移动改变俯仰角（限制在 -10°~89°，不能翻到底下去）。
        if self.drag == "rot":
            self.cam_h -= dx * 120
            self.cam_p = min(max(self.cam_p - dy * 80, -10), 89)
        # 平移：取得摄像机自己的“右方向”和“上方向”，沿着它们移动目标点；离得越远移动越多，手感一致。
        else:
            q = self.camera.getQuat(self.render)
            right, up = q.getRight(), q.getUp()
            k = self.cam_d * 0.6
            self.cam_target -= right * dx * k + up * dy * k
        self.update_camera()

    def _mouse_ray(self):
        # 中文：从摄像机出发、穿过鼠标所在像素的一条“射线”（起点 + 方向），用来判断鼠标指着哪一层材料。
        # 鼠标不在 3D 区域内则返回 None（Python 里表示“没有”的特殊值）。
        """World-space ray (origin, direction) through the mouse, or None."""
        if not self._mouse_in_view():
            return None
        m = self.mouseWatcherNode.getMouse()
        left, right = self.view_frac
        # 鼠标坐标是相对整个窗口的，要换算成相对中间 3D 区域的坐标（-1~1）。
        fx = ((m.x + 1) / 2 - left) / (right - left) * 2 - 1     # window -> display region
        # extrude：让镜头算出这个屏幕点在“近平面”和“远平面”上对应的两个 3D 点，连起来就是射线。
        # 再把这两个点从摄像机坐标系转换到世界坐标系。
        near, far = Point3(), Point3()
        if not self.camLens.extrude(Point2(fx, m.y), near, far):
            return None
        o = self.render.getRelativePoint(self.cam, near)
        f = self.render.getRelativePoint(self.cam, far)
        return (o.x, o.y, o.z), (f.x - o.x, f.y - o.y, f.z - o.z)

    def _update_hover(self, now):
        # 中文：鼠标悬停提示：显示鼠标下面材料的名字和用途，并在 3D 画面和图例里高亮这一层。
        # now 是当前时间（秒），用来控制重新检测的频率。
        """Tooltip naming the material under the mouse, plus 3D / legend highlight."""
        # "A if 条件 else B" 是“条件表达式”：条件成立取 A，否则取 B。正在拖动时不做检测。
        ray = None if self.drag else self._mouse_ray()
        if ray is None:
            hits = []
        else:
            # key 把“鼠标位置 + 摄像机位置朝向 + 剖切位置 + 当前晶圆”打包成一个元组，
            # 只要这些都没变，检测结果就不会变，可以直接沿用上次的结果，节省计算。
            m = self.mouseWatcherNode.getMouse()
            cam = self.camera.getPos(), self.camera.getHpr()
            key = (round(m.x, 4), round(m.y, 4), tuple(cam[0]), tuple(cam[1]), self.cut_y, id(self.wafer))
            # re-pick when the mouse / view moved, and a few times a second while
            # the wafer itself changes underneath a still mouse (animations)
            if key == self.hover_key and now < self.hover_next:
                self.scene.highlight(self.hover_layer)
                return
            self.hover_key, self.hover_next = key, now + 0.25
            # scene.pick 返回射线穿过的所有层，按距离从近到远排好；*ray 把 (起点, 方向) 拆成两个参数传入。
            hits = self.scene.pick(*ray)
        # 找“主要”命中层：next(生成器, 默认值) 取出第一个满足条件的元素。
        #   (h for h in hits if ...) 叫“生成器表达式”，逐个筛选 hits 里的元素。
        #   条件 color[3] >= 0.99 表示不透明的材料（半透明的光刻胶、氧化层等会被“看穿”）。
        #   如果全都是半透明的，就取最近的那个 hits[0]；什么都没打中则为 None。
        # 每个命中 h 是 (距离, 层名, 材料名)，所以 h[1] 是层名，h[2] 是材料名。
        main = next((h for h in hits if mat(h[2]).color[3] >= 0.99), hits[0] if hits else None)
        name = main[1] if main else None
        # 在 3D 里高亮这一层；层变了才去更新右栏图例的高亮（避免重复工作）。
        self.scene.highlight(name)
        if name != self.hover_layer:
            self.hover_layer = name
            self._refresh_legend_hover()
        # 鼠标下面什么都没有：隐藏提示框，直接结束（return）。
        if not main:
            self.hover_tip.hide()
            return
        m_ = mat(main[2])
        # 第一行：黄色的材料名 / line 1: material name in yellow
        lines = ["\1hov_title\1" + i18n.pick(m_.zh, m_.en) + "\2"]
        # 第二行（可选）：鼠标和这层之间隔着的半透明层 / translucent layers in front of it
        # [ ... for h in ... ] 叫“列表推导式”：一行代码生成一个新列表，这里收集主要层前面的半透明层名字。
        # hits[:n] 是“切片”，取前 n 个元素。
        above = [i18n.pick(mat(h[2]).zh, mat(h[2]).en) for h in hits[:hits.index(main)]]
        if above:
            lines.append(tr("hover_through", m="、".join(above) if i18n.LANG == "zh" else ", ".join(above)))
        # 后面几行：这种材料是干什么用的，按宽度自动换行 / what it is for, wrapped
        role = i18n.pick(m_.role_zh, m_.role_en)
        if role:
            lines.append(self.wrap(role, 0.78, 0.032))
        tn = self.hover_tip.node()
        tn.setText("\n".join(lines))
        # 放在鼠标右下方；靠近视图右边缘就改放左边，靠近底部就改放上方，免得被挡住
        # place it below-right of the mouse, flipping left / up near the view edges
        mp = self.mouseWatcherNode.getMouse()
        x = mp.x * self.getAspectRatio()
        w = tn.getWidth() * 0.032
        h = tn.getHeight() * 0.032
        right_edge = (self.view_frac[1] * 2 - 1) * self.getAspectRatio()
        x = x + 0.03 if x + 0.03 + w < right_edge - 0.02 else x - 0.03 - w
        y = mp.y - 0.06
        if y - h < -0.97:
            y = mp.y + 0.04 + h - tn.getLineHeight() * 0.032
        self.hover_tip.setPos(x, 0, y)
        self.hover_tip.show()

    def _refresh_legend_hover(self):
        """更新右栏图例的高亮：鼠标指着的那种材料的名字变黄，其它恢复灰色。"""
        cur = None
        if self.hover_layer and self.wafer and self.hover_layer in self.wafer.layers:
            cur = self.wafer.layers[self.hover_layer].material
        # .items() 同时取出字典的键和值：m 是材料名，t 是对应的文字控件。
        for m, t in self.legend_texts.items():
            t.setFg(ACCENT if m == cur else TXT2)

    # ================================================================= process control
    # ================= 工艺流程控制：跳到某一步、播放动画、上一步/下一步 =================
    # @property 是“装饰器”（写在函数上方、以 @ 开头）：它让 self.steps 可以像变量一样直接读取，
    # 而实际上每次都会调用下面这个函数，返回当前工艺流程的步骤列表。
    @property
    def steps(self):
        """当前工艺流程的全部步骤（列表）。"""
        return self.flow.steps

    def _new_ctx(self):
        """用当前参数、当前工艺流程和故障设置，新建一个“工艺上下文”(ctx)。

        getattr(对象, "名字", 默认值)：安全地读取属性，没有这个属性就返回默认值 None。
        faults 是引导模式里人为设置的“工艺故障”（用来练习找问题），可能还没创建，所以这样读。
        """
        faults = getattr(self, "faults", None)
        return make_ctx(self.params, self.flow, faults)

    def set_flow(self, key: str):
        # 中文：切换“工艺代”（例如从老的微米级工艺换到先进的纳米级工艺）。
        # key: str 是“类型标注”，提示 key 应该是字符串，不影响运行。
        # 切换后参数恢复默认、清空测验成绩、停止播放、回到第 0 步，并重建界面（步骤列表不同了）。
        """Switch technology generation (process flow)."""
        if key == self.flow.key or key not in FLOWS:
            return
        self.flow = FLOWS[key]
        self.params = self.flow.default_params()
        self.vin = self.params.vdd / 2
        self.tran_t = None                 # a transient of the previous generation stops
        self.quiz_results = {}
        self.playing = False
        self.anim_step = None
        self.phase_queue = []
        self.step = 0
        self.goto(0)
        self.rebuild_ui()

    def goto(self, i: int):
        # 中文：直接显示“做完第 i 步之后”的晶圆状态，不播放动画（点击步骤列表、上一步时用）。
        """Show the state after step i without animation."""
        # 把 i 限制在合法范围 0 ~ 步骤数-1 之间，防止越界。
        i = max(0, min(i, len(self.steps) - 1))
        # 清掉正在飞的粒子（例如离子注入动画里的离子），清空待播放阶段，退出动画状态。
        self.scene.clear_particles()
        self.phase_queue = []
        self.anim_step = None
        # 重新从第 0 步一路算到第 i 步，得到那时的晶圆（build_until 内部会逐步执行工艺）。
        self.ctx = self._new_ctx()
        self.wafer = build_until(self.ctx, i)
        self.step = i
        self.caption = ("", "")
        # 交给 3D 场景显示；如果已经是最后一步(芯片做完)，terminal_mode 会显示电极标签(VDD/GND/IN/OUT)。
        # 然后更新载流子仿真显示和整个界面。
        self.scene.set_wafer(self.wafer, self.ctx, terminal_mode=self.is_done())
        self._apply_sim()
        self.refresh_ui()

    def is_done(self):
        """是否已经完成全部工艺（处在最后一步且没有在播放动画）。只有芯片做完才能做电学仿真。"""
        return self.step == len(self.steps) - 1 and self.anim_step is None

    def animate_step(self, i: int):
        """用动画播放第 i 步工艺（例如：氧化层慢慢长出来、离子一颗颗打进硅里）。"""
        if i < 0 or i >= len(self.steps):
            return
        # 动画必须从“第 i-1 步做完”的状态开始。如果当前不是这个状态，先跳过去；
        # i 为 0 时（第一步之前什么都没有）就换成一块空白晶圆。
        # 这里把条件表达式当作语句用：条件成立执行 goto，否则执行 _blank。
        if self.anim_step is not None or self.step != i - 1:
            self.goto(i - 1) if i > 0 else self._blank()
        # 进入动画状态：关掉电极标签和载流子仿真（芯片还没做完，谈不上通电）。
        self.anim_step = i
        self.scene.terminal_mode = False
        self.scene.set_sim(None)
        self.wafer.current_step = self.steps[i].key
        # 取出这一步的所有阶段排队。有的步骤在当前参数下会被“跳过”（is_skipped，例如某代工艺不需要它），
        # 那就没有阶段要播放，直接当作完成。list(...) 复制一份，避免弹出时改坏原始数据。
        self.phase_queue = [] if is_skipped(self.ctx, self.steps[i]) else list(self.steps[i].phases)
        if not self.phase_queue:
            self._phase_finished()
            return
        self._next_phase()
        self.refresh_ui()

    def _blank(self):
        """准备一块什么都没做过的空白硅片，step = -1 表示“第 1 步之前”。"""
        self.wafer = Wafer()
        self.ctx = self._new_ctx()
        self.scene.set_wafer(self.wafer, self.ctx)
        self.step = -1

    def _next_phase(self):
        """取出队列里的下一个阶段，执行它（改变晶圆状态），并开始播放它的动画，同时更新说明文字。"""
        ph = self.phase_queue.pop(0)
        # pop(0) 取出并删除列表的第一个元素；ph.zh/ph.en 是该阶段的中英文说明。
        # run_phase 真正修改晶圆，并返回描述“怎么动”的动画数据；duration 是动画时长（秒）。
        self.caption = (ph.zh, ph.en)
        anim = run_phase(self.wafer, self.ctx, ph)
        self.scene.start_anim(anim, ph.duration)
        self._refresh_caption()

    def _phase_finished(self):
        """一个阶段的动画播完时调用。还有阶段就继续；全部播完则把这一步标记为完成。"""
        if self.phase_queue:
            self._next_phase()
            return
        # 这一步全部完成：更新 step，退出动画状态。
        self.step = self.anim_step
        self.anim_step = None
        self.caption = ("", "")
        # 如果是最后一步，芯片做好了：显示电极标签，开启电学仿真显示。
        if self.is_done():
            self.scene.terminal_mode = True
            self.scene.rebuild_labels()
            self._apply_sim()
        self.refresh_ui()
        # 自动播放时，下一步开始前停顿 0.9 秒，给人看清结果。
        self.play_wait = 0.9
        # 测验模式开着、这一步有题目、而且还没答过 → 弹出测验。
        if self.quiz_enabled and self.steps[self.step].quiz and self.step not in self.quiz_results:
            self.show_quiz(self.step)
        # 已经是最后一步：停止自动播放，并把按钮文字改回“播放”。
        if self.step == len(self.steps) - 1:
            self.playing = False
            self._refresh_play_btn()

    def next_step(self):
        """“下一步”：若正在播放动画，就立刻跳到动画结束状态；否则播放下一步的动画。测验窗口打开时不响应。"""
        if self.quiz_frame:
            return
        if self.anim_step is not None:
            self.goto(self.anim_step)
        elif self.step < len(self.steps) - 1:
            self.animate_step(self.step + 1)

    def prev_step(self):
        """“上一步”：直接显示前一步完成后的状态（不倒放动画）。"""
        if self.quiz_frame:
            return
        cur = self.anim_step if self.anim_step is not None else self.step
        self.goto(max(cur - 1, 0))

    def toggle_play(self):
        """播放/暂停自动连续演示。如果已经在最后一步，按播放会从头开始。"""
        if self.quiz_frame:
            return
        # not 取反：True 变 False，False 变 True。
        self.playing = not self.playing
        if self.playing and self.anim_step is None:
            if self.step >= len(self.steps) - 1:
                self.goto(0)
            self.play_wait = 0.0
        self._refresh_play_btn()

    def jump_to(self, i):
        """点击左栏步骤列表时调用：如果点的正好是“下一步”就播放动画，否则直接跳过去显示结果。"""
        if self.quiz_frame:
            return
        cur = self.anim_step if self.anim_step is not None else self.step
        if i == cur + 1 and self.anim_step is None:
            self.animate_step(i)
        else:
            self.goto(i)

    # ================================================================= tick
    # ================= 每帧更新（游戏循环） =================
    # 屏幕每秒刷新几十次，每次刷新都会调用一次 _tick，所有“随时间变化”的事情都在这里推进。
    def _tick(self, task):
        """每帧调用一次：处理拖动和悬停、推进动画、自动播放、瞬态动画，并在需要时重画曲线。

        task 是 Panda3D 传进来的任务对象；返回 task.cont 表示“下一帧继续调用我”。
        """
        now = time.time()
        # dt：距上一帧过了多少秒。最多算 0.1 秒，防止卡顿后动画一下子跳太远。
        dt = min(now - self.last_time, 0.1)
        self.last_time = now
        self._handle_drag()
        self._update_hover(now)
        # scene.update 推进 3D 动画，返回 True 表示当前阶段动画播完了。
        if self.scene.update(dt, self.speed) and self.anim_step is not None:
            self._phase_finished()
        # 自动播放：停顿倒计时结束后，开始下一步。
        if self.playing and self.anim_step is None and not self.quiz_frame:
            self.play_wait -= dt * self.speed
            if self.play_wait <= 0 and self.step < len(self.steps) - 1:
                self.animate_step(self.step + 1)
        # 正在播放瞬态动画（输入电压随时间翻转）时推进它。
        if self.tran_t is not None:
            self._advance_transient(dt)
        # 参数改了（拖滑块）也不会每帧都重算，至少间隔 0.15 秒才提交一次，避免拖动时卡顿。
        # 同理，曲线只在右栏显示“电学”或“引导”页时才重画，且间隔至少 0.12 秒。
        if self.params_dirty and now - self.last_plot > 0.15:
            self._commit_params()
        if self.plot_dirty and self.right_tab in ("elec", "guide") and now - self.last_plot > 0.12:
            self._redraw_plot()
        self._guide_tick()
        return task.cont

    # ================================================================= electrical
    # ================= 电学：仿真数值、瞬态动画、曲线绘制、参数滑块 =================
    def _sim_values(self, vin, vout=None):
        """给定反相器输入电压 vin，算出 3D 载流子动画需要的各种数值（输出电压、两管电流等）。

        物理背景：
          · 反相器由 NMOS（下拉到地 GND）和 PMOS（上拉到电源 VDD）组成；
          · 阈值电压 Vt：栅极电压超过它，晶体管下面才形成导电沟道（“开关打开”）；
          · NMOS 看的是栅-源电压 Vgs = vin；PMOS 的源极接 VDD，所以看的是 VDD - vin。
        vout 可以由调用者给出（瞬态动画时），不给就按直流稳态算。
        """
        p = self.params
        # 根据工艺参数建立 NMOS 和 PMOS 的模型；features 表示这一代工艺的特殊结构（例如 SOI、FinFET）。
        mn, mp = nmos(p, self.flow.features), pmos(p, self.flow.features)
        # 没给 vout 就求解反相器的直流输出电压（[0] 取结果里的第一个值）。
        if vout is None:
            vout = float(inverter_vout(p, vin, features=self.flow.features)[0])
        # ids(Vgs, Vds)：晶体管电流。NMOS 的 Vds 就是 vout；PMOS 的 Vds 是 VDD - vout。
        # max(..., 0.0) 防止出现负电压。
        idn = float(mn.ids(vin, max(vout, 0.0)))
        idp = float(mp.ids(p.vdd - vin, max(p.vdd - vout, 0.0)))

        # 在函数内部又定义了一个小函数 sig：S 形“软开关”曲线，输入从负到正时输出从 0 平滑过渡到 1。
        # 用来表示沟道“反型”（导通）的程度。把 x 限制在 ±40 是为了防止 exp 计算溢出。
        def sig(x):
            return 1 / (1 + math.exp(-max(min(x, 40), -40)))
        # carrier speed is scaled to the on-current, so leakage and the short-circuit
        # hump around VM look as small as they really are next to switching current
        # 中文：iref 是参考电流（两管中较大的饱和电流），动画里载流子速度按它归一化，
        # 这样漏电流和翻转点附近的“短路电流峰”看起来和真实比例一样小。
        iref = max(mn.idsat(p.vdd), mp.idsat(p.vdd), 1e-12)
        # 返回一个字典（键: 值），交给 3D 场景使用：
        #   in/ip：NMOS/PMOS 电流；inv_n/inv_p：两管沟道的导通程度（0 关断 ~ 1 完全导通），
        #   (vin - Vt)/0.08 表示栅压超过阈值越多越接近 1，0.08 V 控制过渡的“软硬”。
        return {"vin": vin, "vout": vout, "vdd": p.vdd, "gnd": 0.0, "in": idn, "ip": idp, "iref": iref,
                "inv_n": sig((vin - mn.vt_mag) / 0.08), "inv_p": sig((p.vdd - vin - mp.vt_mag) / 0.08)}

    def _apply_sim(self):
        """决定 3D 场景里是否显示载流子动画：只有打开了“3D 载流子仿真”且芯片已经做完才显示。"""
        if self.sim3d and self.is_done():
            # 瞬态动画播放期间由 _advance_transient 负责更新，这里就不用直流值去覆盖。
            if self.tran_t is None:
                self.scene.set_sim(self._sim_values(self.vin))
        else:
            self.scene.set_sim(None)

    def _advance_transient(self, dt):
        """推进瞬态动画：把仿真得到的“输入/输出电压随时间变化”的曲线，用 5 秒真实时间播放一遍。

        瞬态(transient)：输入电压突然从低跳到高（或反过来），输出要过一小段时间才翻转，
        这段延迟就是芯片速度的关键指标（传播延迟 tpHL/tpLH）。
        """
        s = summarize_cached(self.params, self.flow.features)
        # 上一行的 summarize_cached：算出（并缓存）这组参数下的全部电学指标，其中 s.tran 是瞬态仿真结果。
        # dur：整段瞬态动画用 5 秒真实时间播完。
        dur = 5.0
        self.tran_t += dt
        # 播完 5 秒就结束动画，恢复成普通的直流显示。
        if self.tran_t > dur:
            self.tran_t = None
            self.plot_dirty = True
            self._apply_sim()
            return
        # 把动画进度（0~5 秒）按比例映射到仿真时间轴（0 ~ 最后时刻 r.t[-1]，[-1] 表示列表最后一个元素）。
        r = s.tran
        t_sim = self.tran_t / dur * r.t[-1]
        # 在函数中途 import：只有用到时才加载 numpy（数值计算库）。
        # np.interp：线性插值，根据仿真时间查出这一刻的输入、输出电压。
        import numpy as np
        vin = float(np.interp(t_sim, r.t, r.vin))
        vout = float(np.interp(t_sim, r.t, r.vout))
        # tran_cursor 记录当前时刻，画曲线时会在图上标出一条竖线表示“现在播到这里”。
        self.tran_cursor = t_sim
        if self.sim3d and self.is_done():
            self.scene.set_sim(self._sim_values(vin, vout))
        self.plot_dirty = True

    def play_transient(self):
        """点击“播放瞬态”按钮时调用：切到瞬态曲线，从 0 开始播放，并自动打开 3D 载流子动画。

        lab_tran 是给引导模式用的标记：记录用户已经看过瞬态动画。
        """
        self.lab_tran = True
        self.tran_t = 0.0
        self.tran_cursor = 0.0
        self.plot_kind = "tran"
        if self.is_done() and not self.sim3d:
            self.toggle_sim3d()
        self.refresh_ui()

    def toggle_sim3d(self):
        """打开/关闭“3D 载流子仿真”。打开时自动开启剖面，这样才能看到沟道里电子和空穴的流动。"""
        self.sim3d = not self.sim3d
        if self.sim3d and self.is_done():
            self.cut_on = True
            self.cut_y = 3.5
            self.scene.set_cut(self.cut_y)
        self._apply_sim()
        self.refresh_ui()

    def _redraw_plot(self):
        """按当前选择的曲线种类重新画图，并把图片拷进贴图，显示在右栏。

        几种曲线（ref 是引导模式里的“参考答案”曲线，用来对比）：
          · idvg：Id-Vg，漏极电流随栅压变化，看阈值电压和亚阈值漏电；
          · idvd：Id-Vd，输出特性曲线，看线性区/饱和区；
          · vtl ：阈值电压随栅长 L 变化，展示短沟道效应（L 越短 Vt 越低）和 DIBL；
          · tran：瞬态波形，看开关延迟；
          · vtc ：电压传输特性，反相器输出电压随输入电压变化的“S”形曲线。
        """
        p = self.params
        s = summarize_cached(p, self.flow.features)
        vin = min(self.vin, p.vdd)
        ref = self.guide_ref
        if self.plot_kind == "idvg":
            img = self.renderer.idvg(p, vin, self.flow.features, ref)
        elif self.plot_kind == "idvd":
            img = self.renderer.idvd(p, vin, self.flow.features, ref)
        elif self.plot_kind == "vtl":
            img = self.renderer.vtl(p, self.flow.features, ref)
        elif self.plot_kind == "tran":
            img = self.renderer.tran(p, s, self.tran_cursor if self.tran_t is not None else None, ref)
        else:
            img = self.renderer.vtc(p, vin, s, self.flow.features, ref)
        # tobytes() 把图片转成原始字节，写进贴图；然后清除“需要重画”标记并记下时间。
        self.plot_tex.setRamImageAs(img.tobytes(), "RGBA")
        self.plot_dirty = False
        self.last_plot = time.time()

    def set_vin(self):
        """拖动 Vin 滑块时调用。滑块值是 0~1，乘以 VDD 得到实际输入电压。"""
        v = float(self.vin_slider["value"]) * self.params.vdd
        # 值几乎没变就什么也不做（abs 是绝对值，1e-6 = 0.000001）。
        if abs(v - self.vin) < 1e-6:
            return
        self.vin = v
        # tr("vin", v=v)：取出翻译好的文字模板并填入数值，例如“输入电压 Vin = 1.65 V”。
        self.vin_text.setText(tr("vin", v=v))
        self.plot_dirty = True
        if self.tran_t is None:
            self._apply_sim()

    def set_param(self, key, lo, hi, log, slider, label, lkey):
        """拖动某个参数滑块时调用：把滑块位置换算成参数值，写进 self.params，并更新旁边的文字。

        参数含义见文件开头的 PARAM_SLIDERS 说明。lo/hi 是范围，log 表示是否按对数刻度换算。
        """
        x = float(slider["value"])
        # 对数刻度：在 log10(lo) 和 log10(hi) 之间按比例取值，再求 10 的幂（** 是乘方）；
        # 线性刻度：直接在 lo 和 hi 之间按比例取值。
        v = 10 ** (math.log10(lo) + x * (math.log10(hi) - math.log10(lo))) if log else lo + x * (hi - lo)
        old = getattr(self.params, key)
        if abs(v - old) <= 1e-6 * abs(old):
            return
        # setattr(对象, "名字", 值)：按名字设置属性，相当于 self.params.<key> = v。
        # 只做标记(params_dirty)，真正的重新计算由 _tick 稍后统一执行，拖动更流畅。
        setattr(self.params, key, v)
        label.setText(self._param_text(key, lkey, v, log))
        self.params_dirty = True

    # @staticmethod：静态方法，不需要 self（不依赖对象本身的数据），像普通函数一样挂在类上。
    @staticmethod
    def _param_text(key, lkey, v, log):
        """生成参数滑块旁边显示的文字（例如“栅氧厚度 tox = 10.0 nm”），实际实现放在 guide_ui.py 里共用。"""
        from .guide_ui import _param_text
        return _param_text(key, lkey, v, log)

    def _commit_params(self):
        """真正“提交”参数修改：重新计算工艺上下文，必要时重建 3D 晶圆，并标记曲线需要重画。"""
        self.params_dirty = False
        self.vin = min(self.vin, self.params.vdd)
        # lay["gl"] 是 3D 模型里画出来的栅极长度。如果栅长变了，晶圆的几何形状就变了，
        # 必须从头重新“制造”到当前步骤；否则几何不变，只要换掉上下文、更新数值即可（更快）。
        new_ctx = self._new_ctx()
        if abs(new_ctx.lay["gl"] - self.ctx.lay["gl"]) > 1e-9:
            if self.anim_step is not None:
                self.goto(self.anim_step)
            else:
                self.goto(self.step)
        else:
            self.ctx = new_ctx
            self._apply_sim()
            self.refresh_ui()
        self.plot_dirty = True
        self.last_plot = time.time()

    def reset_params(self):
        """“恢复默认参数”按钮：参数回到当前工艺代的默认值，重新生成晶圆并重建界面（滑块位置要归位）。"""
        self.params = self.flow.default_params()
        self.vin = self.params.vdd / 2
        self.goto(self.anim_step if self.anim_step is not None else self.step)
        self.rebuild_ui()

    # ================================================================= quiz
    # ================= 小测验 =================
    def show_quiz(self, i):
        """在第 i 步完成后弹出一道选择题。弹出时暂停自动播放，并记住之后要不要接着播放。"""
        q = self.steps[i].quiz
        self.resume_after_quiz = self.playing
        self.playing = False
        # 创建测验窗口（深色半透明背景板）；state=DGG.NORMAL 让它能接收鼠标点击，挡住后面的界面。
        f = DirectFrame(parent=self.aspect2d, frameColor=(0.06, 0.065, 0.08, 0.97),
                        frameSize=(-0.78, 0.78, -0.62, 0.55), state=DGG.NORMAL)
        self.quiz_frame = f
        # 标题、题目（自动换行）和一个暂时为空的“答题反馈”文字。i18n.pick(*q.q) 按当前语言选中文或英文。
        OnscreenText(parent=f, text=tr("quiz_title", i=i + 1), pos=(-0.72, 0.46), scale=0.04,
                     fg=ACCENT, align=TextNode.ALeft)
        OnscreenText(parent=f, text=self.wrap(i18n.pick(*q.q), 1.44, 0.045), pos=(-0.72, 0.37), scale=0.045,
                     fg=TXT, align=TextNode.ALeft)
        self.quiz_feedback = OnscreenText(parent=f, text="", pos=(-0.72, -0.36), scale=0.034, fg=TXT2,
                                          align=TextNode.ALeft, mayChange=True)
        # 为每个选项生成一个按钮。
        #   enumerate(列表) 同时给出序号 k 和元素 opt。
        #   f"..." 是 f-string（格式化字符串）：花括号 {} 里的表达式会被算出来填进去；'ABCD'[k] 取第 k 个字母。
        #   lambda k=k: ... 是“匿名小函数”，点击按钮时调用 self._answer(i, k)。
        #   写成 k=k 是为了把当前循环的 k 值“定格”下来，否则所有按钮都会用到循环结束时的最后一个 k。
        self.quiz_btns = []
        for k, opt in enumerate(q.options):
            b = self._button(f, f"{'ABCD'[k]}.  {i18n.pick(*opt)}", (-0.70, 0.18 - k * 0.12), 1.40,
                             lambda k=k: self._answer(i, k), align="left", scale=0.038)
            self.quiz_btns.append(b)
        # 右下角的“跳过/继续”按钮。
        self.quiz_continue = self._button(f, tr("skip"), (0.48, -0.54), 0.24, self._close_quiz)

    def _answer(self, i, k):
        """用户点了第 k 个选项：判断对错、记录成绩、把正确答案标绿/选错的标红，并显示解析。"""
        q = self.steps[i].quiz
        # 同一题只能答一次。
        if i in self.quiz_results:
            return
        ok = k == q.answer
        self.quiz_results[i] = ok
        # 正确选项变绿；如果用户选错了，他选的那个变红。
        for j, b in enumerate(self.quiz_btns):
            if j == q.answer:
                b["frameColor"] = (0.12, 0.50, 0.25, 1)
            elif j == k:
                b["frameColor"] = (0.60, 0.18, 0.18, 1)
        head = tr("quiz_ok") if ok else tr("quiz_bad", a="ABCD"[q.answer])
        self.quiz_feedback.setText(head + "\n" + self.wrap(i18n.pick(*q.explain), 1.0, 0.034))
        self.quiz_continue["text"] = tr("continue")
        self.refresh_ui()

    def _close_quiz(self):
        """关闭测验窗口；如果弹出测验前正在自动播放，就稍等 0.3 秒后继续播放。"""
        if self.quiz_frame:
            self.quiz_frame.destroy()
            self.quiz_frame = None
        if self.resume_after_quiz and self.step < len(self.steps) - 1:
            self.playing = True
            self.play_wait = 0.3
        self._refresh_play_btn()

    # ================================================================= UI helpers
    # ================= 界面小工具：统一风格地创建按钮、文字、滑块 =================
    def _button(self, parent, text, pos, width, cmd, on=False, align="center", scale=0.032, height=None):
        """创建一个统一风格的扁平按钮。

        parent：放在哪个面板里；text：按钮文字；pos：(x, y) 位置；width：宽度；cmd：点击时调用的函数；
        on：是否“选中”（显示为蓝色）；align：文字左对齐还是居中；scale：字号；height：高度（不给就按字号算）。
        参数里写了 =默认值 的，调用时可以不传。
        """
        h = height or scale * 1.75
        # frameSize=(左, 右, 下, 上) 是按钮的边框范围；frameColor 依次是 普通/按下/悬停/禁用 四种状态的颜色。
        # Panda3D 的 2D 界面坐标是 (x, 0, y)，中间那个 0 是深度方向，界面上用不到。
        x0 = 0 if align == "left" else -width / 2
        b = DirectButton(
            parent=parent, text=text, command=cmd, relief=DGG.FLAT, pos=(pos[0], 0, pos[1]),
            frameSize=(x0, x0 + width, -h * 0.36, h * 0.64),
            frameColor=(BTN_ON if on else BTN, BTN_PRESS, BTN_HOVER if not on else BTN_ON, BTN),
            text_scale=scale, text_fg=TXT,
            text_align=TextNode.ALeft if align == "left" else TextNode.ACenter,
            text_pos=(0.018 if align == "left" else 0, 0), pressEffect=0)
        return b

    def wrap(self, text: str, width: float, scale: float) -> str:
        # 中文：自动换行：用真实字体量出每段文字的宽度，超出 width 就换行。中文可以在任意字之间断开，
        # 英文单词和数字则作为一个整体不拆开。返回带 "\n"（换行符）的字符串。
        # "-> str" 是类型标注，说明这个函数返回字符串。
        """Greedy line wrap measured with the real font; CJK may break anywhere."""
        # 第一次调用时创建一个专门用来“量宽度”的文字对象，之后重复使用（hasattr 判断对象有没有某个属性）。
        if not hasattr(self, "_measure"):
            self._measure = TextNode("measure")
            if self.font:
                self._measure.setFont(self.font)
        # re.findall(正则, 文字)：按规则把文字切成小块(token)。这个规则的意思是：
        #   连续的英文字母/数字/英文标点 作为一块 | 单个空白字符 作为一块 | 其它任意单个字符（如一个汉字）作为一块。
        # r"..." 是“原始字符串”，里面的反斜杠不会被特殊处理，写正则时常用。
        tokens = re.findall(r"[A-Za-z0-9_.,;:!?%()'\"<>/+\-=~°µ^]+|\s|.", text)
        # 贪心算法：一块一块往当前行 cur 里加，加了会超宽就先把当前行存起来，另起一行。
        lines, cur = [], ""
        limit = width / scale - 1.0      # keep one em for hanging punctuation
        for tok in tokens:
            if tok == "\n":
                lines.append(cur)
                cur = ""
                continue
            # 超宽了，并且这一块不是“不能放行首”的标点时才换行（标点允许稍微伸出去一点）。
            if cur and self._measure.calcWidth(cur + tok) > limit and tok not in NO_LINE_START:
                lines.append(cur.rstrip())
                cur = "" if tok.isspace() else tok
            else:
                cur += tok
        lines.append(cur)
        return "\n".join(lines)

    def _text(self, parent, text, pos, scale=0.032, fg=TXT, wrap=None, align="left"):
        """创建一段屏幕文字。wrap 给了宽度就自动换行；align 可以是 left/right/center。mayChange=True 允许以后修改文字。"""
        if wrap:
            text = self.wrap(text, wrap, scale)
        return OnscreenText(parent=parent, text=text, pos=pos, scale=scale, fg=fg, mayChange=True,
                            align=TextNode.ALeft if align == "left" else
                            (TextNode.ARight if align == "right" else TextNode.ACenter),
                            )

    def _slider(self, parent, pos, width, value, cmd):
        """创建一个横向滑块，值范围 0~1；拖动时调用 cmd。外观：细长的灰条 + 浅蓝色的拖柄(thumb)。"""
        s = DirectSlider(parent=parent, range=(0, 1), value=value, pageSize=0.05,
                         pos=(pos[0], 0, pos[1]), frameSize=(0, width, -0.008, 0.008),
                         frameColor=(0.3, 0.32, 0.37, 1), relief=DGG.FLAT,
                         thumb_frameSize=(-0.014, 0.014, -0.026, 0.026), thumb_relief=DGG.FLAT,
                         thumb_frameColor=(0.55, 0.70, 0.95, 1), command=cmd)
        return s

    def _clear_ui(self):
        """销毁左右面板上的全部界面控件。"""
        for r in self.ui_roots:
            r.destroy()
        self.ui_roots = []

    def rebuild_ui(self):
        """整个界面推倒重建（切换语言、切换工艺代、恢复参数时用），然后刷新显示状态。"""
        self._clear_ui()
        self.build_ui()
        self.refresh_ui()

    # ================================================================= UI build
    # ================= 搭建界面（只在启动或重建时运行） =================
    def build_ui(self):
        """搭建左栏和右栏。"""
        self._build_left()
        self._build_right()

    def _build_left(self):
        """搭建左栏：标题、工艺代选择按钮、工艺步骤列表、播放控制、视图选项、引导/测验开关。

        y 坐标从上往下越来越小（负数），所以代码里经常用 y -= 0.07 表示“往下挪一行”。
        """
        f = DirectFrame(parent=self.a2dTopLeft, frameColor=PANEL, frameSize=(0, LEFT_W, -2.0, 0))
        # 上一行创建了左栏的底板，挂在窗口左上角(a2dTopLeft)；记到 ui_roots 里方便以后整体销毁。
        self.ui_roots.append(f)
        # 程序标题（黄色大字）和当前工艺代的说明（例如“0.18µm 体硅 CMOS”这样的节点名）。
        self._text(f, tr("app_title"), (0.03, -0.075), 0.052, ACCENT)
        self._text(f, i18n.pick(*self.flow.node), (0.03, -0.118), 0.024, TXT2, wrap=LEFT_W - 0.06)
        # ---- 工艺代选择按钮：每行 3 个，从老工艺到新工艺排列 ----
        # // 是“整除”（只保留整数部分）；(n + 2) // 3 是“向上取整”的常用技巧，算出需要几行。
        # % 是“取余数”，k % 3 得到列号，k // 3 得到行号。
        self.flow_btns = {}
        keys = list(FLOWS)
        per_row = 3                      # generations, oldest first, three per row
        nrows = (len(keys) + per_row - 1) // per_row
        fw = (LEFT_W - 0.06 - 0.01 * (per_row - 1)) / per_row
        for k, key in enumerate(keys):
            col, r = k % per_row, k // per_row
            self.flow_btns[key] = self._button(
                f, i18n.pick(*FLOWS[key].label), (0.03 + fw / 2 + col * (fw + 0.01), -0.205 - r * 0.058), fw,
                lambda key=key: self.set_flow(key), on=key == self.flow.key, scale=0.027)
        # 步骤列表从按钮下方开始，按钮行数越多，列表顶部就越往下。
        list_top = -0.245 - (nrows - 1) * 0.058

        # ---- 工艺步骤列表：放在可滚动面板里，步骤多时可以上下滚动 ----
        # canvasSize 是里面“画布”的总高度（步骤数 × 每行高度），超出可见区域时出现滚动条。
        # verticalScroll_xxx 这样带下划线前缀的参数是在设置滚动条各个部件的颜色。
        n = len(self.steps)
        row = 0.05
        sf = DirectScrolledFrame(parent=f, frameSize=(0.02, LEFT_W - 0.02, -1.0, list_top),
                                 canvasSize=(0, LEFT_W - 0.08, -n * row - 0.01, 0),
                                 frameColor=(0.06, 0.065, 0.075, 1), scrollBarWidth=0.022,
                                 verticalScroll_frameColor=(0.12, 0.13, 0.15, 1),
                                 verticalScroll_thumb_frameColor=(0.35, 0.37, 0.42, 1),
                                 verticalScroll_incButton_frameColor=(0.12, 0.13, 0.15, 1),
                                 verticalScroll_decButton_frameColor=(0.12, 0.13, 0.15, 1),
                                 horizontalScroll_frameColor=(0, 0, 0, 0), relief=DGG.FLAT)
        self.step_list = sf
        canvas = sf.getCanvas()
        self.step_btns = []
        # 每个步骤一个按钮，文字如“03  热氧化”。{i + 1:02d} 表示把数字补成两位（3 → 03）。
        for i, st in enumerate(self.steps):
            b = self._button(canvas, f"{i + 1:02d}  {i18n.pick(*st.title)}", (0.005, -(i + 0.6) * row),
                             LEFT_W - 0.085, lambda i=i: self.jump_to(i), align="left", scale=0.03,
                             height=row * 0.95)
            self.step_btns.append(b)

        # ---- 播放控制：上一步 / 播放 / 下一步，回到开头 / 跳到最后，速度滑块 ----
        # lambda: self.goto(0) 是不带参数的小函数，点击时跳到第 0 步。
        y = -1.06
        self._button(f, tr("prev"), (0.14, y), 0.22, self.prev_step)
        self.play_btn = self._button(f, tr("play"), (0.37, y), 0.22, self.toggle_play)
        self._button(f, tr("next"), (0.60, y), 0.22, self.next_step)
        y -= 0.075
        self._button(f, tr("reset"), (0.20, y), 0.34, lambda: self.goto(0))
        self._button(f, tr("to_end"), (0.55, y), 0.34, lambda: self.goto(len(self.steps) - 1))
        y -= 0.075
        # 速度范围 0.25~3.0 倍；滑块值 0~1 和速度之间按 速度 = 0.25 + 滑块值 × 2.75 换算（这里是反算初始位置）。
        self.speed_text = self._text(f, tr("speed", v=self.speed), (0.04, y), 0.028, TXT2)
        self.speed_slider = self._slider(f, (0.36, y + 0.01), 0.34, (self.speed - 0.25) / 2.75, self._set_speed)

        # ---- 视图选项 ----
        # 剖面：把晶圆切开看内部结构；边线：显示各层的轮廓线；剖切位置滑块：0~1 对应 0.2~7.8。
        y -= 0.085
        self._text(f, tr("view"), (0.03, y), 0.034, ACCENT)
        y -= 0.06
        self.cut_btn = self._button(f, tr("cut"), (0.20, y), 0.34, self._toggle_cut, on=self.cut_on)
        self.edge_btn = self._button(f, tr("edges"), (0.55, y), 0.34, self._toggle_edges, on=self.scene.edges)
        y -= 0.065
        self.cut_text = self._text(f, tr("cut_pos", v=self.cut_y), (0.04, y), 0.028, TXT2)
        self.cut_slider = self._slider(f, (0.36, y + 0.01), 0.34, self.cut_y / 8.0, self._set_cut)
        y -= 0.07
        # 区域标签开关（在 3D 里标出“源极”“漏极”“N 阱”等）和中/英文切换按钮。
        self.label_btn = self._button(f, tr("labels"), (0.20, y), 0.34, self._toggle_labels,
                                      on=self.scene.show_labels)
        self._button(f, tr("lang_btn"), (0.55, y), 0.34, self._toggle_lang)
        y -= 0.07
        # 三个视角按钮。key[4:] 是字符串切片：去掉前 4 个字符 "cam_"，得到 "iso"/"front"/"top"。
        for k, (key, xx) in enumerate((("cam_iso", 0.14), ("cam_front", 0.37), ("cam_top", 0.60))):
            self._button(f, tr(key), (xx, y), 0.22, lambda key=key: self.set_cam(key[4:]))
        y -= 0.085
        # 引导模式、测验模式开关，以及测验得分文字；最底部是鼠标操作说明。
        self.guide_btn = self._button(f, tr("guide_mode"), (0.20, y), 0.34, self.toggle_guide,
                                      on=self.guide_mode)
        self.quiz_btn = self._button(f, tr("quiz_mode"), (0.55, y), 0.34, self._toggle_quiz,
                                     on=self.quiz_enabled)
        self.score_text = self._text(f, "", (0.40, y - 0.075), 0.03, TXT2)
        self._text(f, tr("mouse_hint"), (0.03, -1.93), 0.026, TXT2, wrap=LEFT_W - 0.06)

    def _build_right(self):
        """搭建右栏：顶部是标签页按钮，下面叠放着 工艺 / 电学 / 参数 / 引导 四个页面，每次只显示一个。"""
        f = DirectFrame(parent=self.a2dTopRight, frameColor=PANEL, frameSize=(-RIGHT_W, 0, -2.0, 0))
        self.ui_roots.append(f)
        # x0：右栏内容的左边距（右栏挂在窗口右上角，所以 x 坐标是负数）。
        x0 = -RIGHT_W + 0.03
        self.tab_btns = {}
        # 标签页列表：引导模式打开时多一个“引导”页。tw 是每个标签按钮的宽度（平均分配）。
        tabs = ("process", "elec", "params") + (("guide",) if self.guide_mode else ())
        names = {"process": "tab_process", "elec": "tab_elec", "params": "tab_params", "guide": "tab_guide"}
        tw = (RIGHT_W - 0.06 - 0.01 * (len(tabs) - 1)) / len(tabs)
        for k, key in enumerate(tabs):
            self.tab_btns[key] = self._button(
                f, tr(names[key]), (x0 + tw / 2 + k * (tw + 0.01), -0.065), tw,
                lambda key=key: self._set_tab(key), on=self.right_tab == key,
                scale=0.034 if len(tabs) == 3 else 0.031)

        # ---- process tab
        # 中文：工艺页：显示 “第几步/共几步”、步骤标题、当前阶段说明、详细描述，
        # 以及小贴士、工艺参数表、材料图例三个区域（内容在 refresh_ui 里填写，这里只先建好空容器）。
        # frameColor=(0,0,0,0) 表示完全透明，只是当作一个“分组容器”。
        pt = DirectFrame(parent=f, frameColor=(0, 0, 0, 0))
        self.tab_process = pt
        self.step_no_text = self._text(pt, "", (x0, -0.16), 0.03, TXT2)
        self.title_text = self._text(pt, "", (x0, -0.225), 0.048, TXT)
        self.caption_text = self._text(pt, "", (x0, -0.285), 0.032, ACCENT)
        self.desc_text = self._text(pt, "", (x0, -0.35), 0.031, TXT)
        self.tip_frame = DirectFrame(parent=pt, frameColor=(0, 0, 0, 0))
        self.params_frame = DirectFrame(parent=pt, frameColor=(0, 0, 0, 0))
        self.legend_frame = DirectFrame(parent=pt, frameColor=(0, 0, 0, 0))

        # ---- electrical tab
        # 中文：电学页：上方 5 个曲线种类按钮，中间是曲线图，下面是 Vin 滑块、3D 仿真按钮和关键指标。
        et = DirectFrame(parent=f, frameColor=(0, 0, 0, 0))
        self.tab_elec = et
        self.plot_btns = {}
        kinds = (("idvg", "plot_idvg"), ("idvd", "plot_idvd"), ("vtc", "plot_vtc"), ("tran", "plot_tran"),
                 ("vtl", "plot_vtl"))
        bw = (RIGHT_W - 0.06 - 0.01 * (len(kinds) - 1)) / len(kinds)
        for k, (kind, key) in enumerate(kinds):
            self.plot_btns[kind] = self._button(et, tr(key), (x0 + bw / 2 + k * (bw + 0.01), -0.15), bw,
                                                lambda kind=kind: self._set_plot(kind),
                                                on=self.plot_kind == kind, scale=0.03)
        # 曲线图大小：宽度占满右栏，高度按图片的宽高比算；OnscreenImage 用之前创建的贴图显示它。
        pw = RIGHT_W - 0.05
        ph = pw * PLOT_H / PLOT_W
        self.plot_img = OnscreenImage(parent=et, image=self.plot_tex, pos=(-RIGHT_W / 2, 0, -0.2 - ph / 2),
                                      scale=(pw / 2, 1, ph / 2))
        # 曲线图下方：输入电压 Vin 滑块（初始位置 = vin / VDD）。
        y = -0.2 - ph - 0.06
        self.vin_text = self._text(et, tr("vin", v=self.vin), (x0, y), 0.03, TXT)
        self.vin_slider = self._slider(et, (x0 + 0.40, y + 0.01), RIGHT_W - 0.48,
                                       self.vin / self.params.vdd, self.set_vin)
        # “3D 载流子仿真”开关和“播放瞬态”按钮；sim_note 在芯片没做完时提示“需要先完成全部工艺”。
        y -= 0.08
        self.sim_btn = self._button(et, tr("sim3d"), (x0 + 0.21, y), 0.42, self.toggle_sim3d, on=self.sim3d)
        self._button(et, tr("play_tran"), (x0 + 0.66, y), 0.40, self.play_transient)
        y -= 0.06
        self.sim_note = self._text(et, "", (x0, y), 0.026, TXT2)
        y -= 0.06
        # 两列关键指标文字（阈值电压、饱和电流、延迟等），内容在 refresh_ui 里填写。
        self.metrics_text = self._text(et, "", (x0, y), 0.029, TXT)
        self.metrics_text2 = self._text(et, "", (x0 + RIGHT_W / 2, y), 0.029, TXT)

        # ---- params tab
        # 中文：参数页：每个可调参数一行文字 + 一个滑块。
        pa = DirectFrame(parent=f, frameColor=(0, 0, 0, 0))
        self.tab_params = pa
        y = -0.17
        self.param_widgets = []
        # 当前工艺代有自己的滑块列表就用它，否则（or）用文件开头的默认 PARAM_SLIDERS。
        # 每行拆成 5 个变量（参数名, 翻译键, 最小值, 最大值, 是否对数）。
        for key, lkey, lo, hi, log in self.flow.sliders or PARAM_SLIDERS:
            # 把参数的当前值反算成滑块位置 x（0~1），这是 set_param 里换算的逆运算。
            v = getattr(self.params, key)
            if log:
                x = (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
            else:
                x = (v - lo) / (hi - lo)
            txt = self._param_text(key, lkey, v, log)
            # 创建文字和滑块；min(max(x, 0), 1) 把位置限制在 0~1。
            lab = self._text(pa, txt, (x0, y), 0.03, TXT)
            sl = self._slider(pa, (x0, y - 0.045), RIGHT_W - 0.08, min(max(x, 0), 1), None)
            # 滑块建好后再设置回调：用 lambda 的默认参数把这一行的 key/lo/hi/sl/lab 等“定格”住，
            # 这样每个滑块拖动时只会改它自己对应的参数。
            sl["command"] = (lambda key=key, lo=lo, hi=hi, log=log, sl=sl, lab=lab, lkey=lkey:
                             self.set_param(key, lo, hi, log, sl, lab, lkey))
            self.param_widgets.append(sl)
            y -= 0.125
        # “恢复默认”按钮，以及“提取的器件参数”区域（由工艺参数推算出的 Cox、k'、γ 等）。
        self._button(pa, tr("restore"), (x0 + 0.15, y + 0.02), 0.30, self.reset_params)
        y -= 0.07
        self._text(pa, tr("extracted"), (x0, y), 0.032, ACCENT)
        self.extract_text = self._text(pa, "", (x0, y - 0.055), 0.028, TXT)
        self.extract_text2 = self._text(pa, "", (x0 + RIGHT_W / 2, y - 0.055), 0.028, TXT)

        # ---- guide tab
        # 中文：引导页由 GuideMixin 搭建。
        self._build_guide_tab(f)

    # ================================================================= UI callbacks
    # ================= 界面回调：用户点击按钮/拖动滑块时执行 =================
    def _set_tab(self, key):
        """切换右栏标签页。切到参数页或电学页时，先让滑块位置和当前数值同步。"""
        self.right_tab = key
        self.plot_dirty = True
        if key in ("params", "elec"):
            self._sync_controls()
        self.refresh_ui()

    def _set_plot(self, kind):
        """切换要画的曲线种类（idvg / idvd / vtc / tran / vtl）。"""
        self.plot_kind = kind
        self.plot_dirty = True
        self.refresh_ui()

    def _set_speed(self):
        """速度滑块被拖动：滑块值 0~1 换算成 0.25~3 倍速，并更新显示文字。"""
        self.speed = 0.25 + float(self.speed_slider["value"]) * 2.75
        self.speed_text.setText(tr("speed", v=self.speed))

    def _toggle_cut(self):
        """开/关剖面视图。关闭时剖切位置设为 0（即不切）。"""
        self.cut_on = not self.cut_on
        self.scene.set_cut(self.cut_y if self.cut_on else 0.0)
        self._apply_sim()
        self.refresh_ui()

    def _set_cut(self):
        """拖动剖切位置滑块：0~1 换算成 0.2~7.8，并重新切开晶圆、重建沟道显示。"""
        self.cut_y = float(self.cut_slider["value"]) * 7.6 + 0.2
        self.cut_text.setText(tr("cut_pos", v=self.cut_y))
        if self.cut_on:
            self.scene.set_cut(self.cut_y)
            self.scene._rebuild_channels()

    def _toggle_edges(self):
        """开/关各层的轮廓边线。"""
        self.scene.set_edges(not self.scene.edges)
        self.refresh_ui()

    def _toggle_labels(self):
        """开/关 3D 里的区域文字标签。"""
        self.scene.set_labels(not self.scene.show_labels)
        self.refresh_ui()

    def _toggle_lang(self):
        """中英文切换。没有中文字体时只能用英文，所以直接返回。切换后整个界面和 3D 标签都要重建。"""
        if not self.font:
            return
        i18n.set_lang("en" if i18n.LANG == "zh" else "zh")
        self.rebuild_ui()
        self.scene.rebuild_labels()
        self.plot_dirty = True

    def _toggle_quiz(self):
        """开/关测验模式（开了以后每完成一步会弹出相关的选择题）。"""
        self.quiz_enabled = not self.quiz_enabled
        self.refresh_ui()

    def _refresh_play_btn(self):
        """根据是否在播放，把按钮文字改成“暂停”或“播放”，并切换蓝色高亮。

        界面可能还没建好（启动早期），所以先用 hasattr 检查按钮是否存在。
        """
        if hasattr(self, "play_btn"):
            self.play_btn["text"] = tr("pause") if self.playing else tr("play")
            self._set_on(self.play_btn, self.playing)

    @staticmethod
    def _set_on(btn, on):
        """设置按钮的颜色：on 为 True 显示为蓝色“选中”状态，否则为普通灰色。"""
        btn["frameColor"] = (BTN_ON if on else BTN, BTN_PRESS, BTN_ON if on else BTN_HOVER, BTN)

    def _refresh_caption(self):
        """更新右栏的“当前阶段”说明：正在播放时显示 “→ 阶段名”，否则显示“本步完成”之类的文字。"""
        if not hasattr(self, "caption_text"):
            return
        if self.anim_step is not None and self.caption[0]:
            self.caption_text.setText("→ " + i18n.pick(*self.caption))
        else:
            self.caption_text.setText(tr("phase_done") if self.step >= 0 else "")

    # ================================================================= refresh
    # ================= 刷新界面：把当前状态显示出来 =================
    def refresh_ui(self):
        """根据当前状态更新整个界面的显示：按钮颜色、步骤说明、参数表、图例、电学指标等。

        和 build_ui 的区别：build_ui 只负责“创建”控件，refresh_ui 负责“填内容/改颜色”，会被频繁调用。
        """
        if not hasattr(self, "step_btns"):
            return
        # cur：当前关注的步骤（正在播放动画的那一步，或已完成的那一步）。
        cur = self.anim_step if self.anim_step is not None else self.step
        # 步骤列表上色：当前步骤蓝色，之前的步骤绿色（已完成），之后的步骤灰色。
        for i, b in enumerate(self.step_btns):
            if i == cur:
                col = BTN_ON
            elif i < cur or (i == cur and self.anim_step is None):
                col = DONE_COL
            else:
                col = BTN
            b["frameColor"] = (col, BTN_PRESS, BTN_HOVER, BTN)
        # 各类开关按钮：和当前状态一致的显示为选中（蓝色）。
        self._refresh_play_btn()
        for key, b in self.flow_btns.items():
            self._set_on(b, key == self.flow.key)
        for key, b in self.tab_btns.items():
            self._set_on(b, key == self.right_tab)
        for key, b in self.plot_btns.items():
            self._set_on(b, key == self.plot_kind)
        self._set_on(self.cut_btn, self.cut_on)
        self._set_on(self.edge_btn, self.scene.edges)
        self._set_on(self.label_btn, self.scene.show_labels)
        self._set_on(self.quiz_btn, self.quiz_enabled)
        self._set_on(self.guide_btn, self.guide_mode)
        self._set_on(self.sim_btn, self.sim3d)
        # 测验得分：sum(1 for v in ... if v) 数一数有多少题答对（值为 True 的个数）。
        n_ok = sum(1 for v in self.quiz_results.values() if v)
        self.score_text.setText(tr("score", ok=n_ok, n=len(self.quiz_results)) if self.quiz_enabled else "")

        # 只显示当前选中的标签页，其余隐藏。
        self.tab_process.show() if self.right_tab == "process" else self.tab_process.hide()
        self.tab_elec.show() if self.right_tab == "elec" else self.tab_elec.hide()
        self.tab_params.show() if self.right_tab == "params" else self.tab_params.hide()
        if self.tab_guide is not None:
            self.tab_guide.show() if self.right_tab == "guide" else self.tab_guide.hide()

        # ---- process tab
        # 中文：---- 工艺页内容 ----
        # max(cur, 0)：cur 可能是 -1（空白晶圆），这时按第 0 步显示。
        st = self.steps[max(cur, 0)]
        self.step_no_text.setText(tr("step_n", i=max(cur, 0) + 1, n=len(self.steps)))
        self.title_text.setText(i18n.pick(*st.title))
        self._refresh_caption()
        self.desc_text.setText(self.wrap(i18n.pick(*st.desc), RIGHT_W - 0.07, 0.031))
        # 根据描述文字实际占了几行，算出下面内容应该从哪个 y 位置开始，避免重叠。
        tn = self.desc_text.textNode
        y = -0.35 - tn.getNumRows() * tn.getLineHeight() * 0.031 - 0.03
        # 小贴士：先删掉旧内容；这一步有贴士就画一个绿色底框，把文字放在框上面。
        # reparentTo 把文字重新挂到容器下，确保它画在底框之后（显示在底框上面）。
        for c in self.tip_frame.getChildren():
            c.removeNode()
        tip = self.step_tip(st)
        if tip:
            tt = self._text(self.tip_frame, tr("tip_head") + tip, (-RIGHT_W + 0.05, y - 0.005), 0.028,
                            (0.75, 0.92, 0.6, 1), wrap=RIGHT_W - 0.1)
            rows = tt.textNode.getText().count("\n") + 1
            h = rows * 0.035 + 0.02
            DirectFrame(parent=self.tip_frame, frameColor=(0.16, 0.22, 0.14, 1),
                        frameSize=(-RIGHT_W + 0.03, -0.03, y - h + 0.01, y + 0.035))
            tt.reparentTo(self.tip_frame)
            y -= h + 0.04
        # 工艺参数表：每行左边是参数名，右边是数值。st.params 里每项是 (中文名, 英文名, 计算函数)，
        # fn(self.ctx) 用当前上下文算出要显示的值（例如“氧化温度 1000 °C”“注入能量 30 keV”）。
        for c in self.params_frame.getChildren():
            c.removeNode()
        self._text(self.params_frame, tr("params"), (-RIGHT_W + 0.03, y), 0.034, ACCENT)
        y -= 0.055
        for zh, en, fn in st.params:
            self._text(self.params_frame, i18n.pick(zh, en), (-RIGHT_W + 0.05, y), 0.029, TXT2)
            self._text(self.params_frame, fn(self.ctx), (-0.03, y), 0.029, TXT, align="right")
            y -= 0.045
        y -= 0.04
        # 材料图例：列出晶圆上目前出现过的所有材料（每种只列一次），每行两列，左边色块右边名字。
        for c in self.legend_frame.getChildren():
            c.removeNode()
        self.legend_texts = {}
        self._text(self.legend_frame, tr("legend"), (-RIGHT_W + 0.03, y), 0.034, ACCENT)
        y -= 0.055
        mats = []
        if self.wafer:
            # .values() 取字典里所有的值；lay.solids 非空表示这层真的有形状；legend 表示这种材料要在图例中显示。
            for lay in self.wafer.layers.values():
                if lay.solids and lay.material not in mats and MATERIALS[lay.material].legend:
                    mats.append(lay.material)
        colw = (RIGHT_W - 0.06) / 2
        # k % 2 决定在左列还是右列，k // 2 决定第几行。
        for k, m in enumerate(mats):
            cx = -RIGHT_W + 0.04 + (k % 2) * colw
            cy = y - (k // 2) * 0.05
            col = mat(m).color
            DirectFrame(parent=self.legend_frame, frameColor=(col[0], col[1], col[2], 1),
                        frameSize=(0, 0.035, -0.008, 0.022), pos=(cx, 0, cy))
            self.legend_texts[m] = self._text(self.legend_frame, i18n.pick(mat(m).zh, mat(m).en),
                                              (cx + 0.05, cy), 0.026, TXT2)
        self._refresh_legend_hover()

        # ---- electrical
        # 中文：---- 电学页指标 ----
        # s 是这组参数下的全部电学结果。下面的 f-string 里，{数值:+.3f} 表示带正负号、保留 3 位小数，
        # {:.2e} 表示科学计数法（如 1.23e-09）。各指标含义：
        #   Vtn / Vtp       NMOS / PMOS 的阈值电压（PMOS 为负值）；
        #   Idsat,n / ,p    饱和电流：管子完全打开时能提供的最大电流，越大开关越快（单位换成 mA）；
        #   Ioff,n          关断漏电流：管子“关着”时仍然漏过的电流，越小越省电；
        #   xj              源漏结深（纳米）；先进工艺（SOI/FinFET）没有这个概念，改显示硅膜厚度 tsi；
        #   VM              反相器翻转点：输入等于这个电压时输出正好在翻转中间；
        #   NMH / NML       高/低噪声容限：输入信号能容忍多大的干扰而不出错；
        #   tpHL / tpLH     传播延迟：输出从高到低 / 从低到高需要的时间（单位换成皮秒 ps）；
        #   DIBL            漏致势垒降低：漏极电压升高让阈值电压下降的程度，短沟道效应的指标。
        s = summarize_cached(self.params, self.flow.features)
        p = self.params
        # VDD 被调低后，输入电压不能超过新的 VDD。
        if self.vin > p.vdd:
            self.vin = p.vdd
        self.vin_text.setText(tr("vin", v=self.vin))
        self.sim_note.setText("" if self.is_done() else tr("sim_need_done"))
        # r 是 VTC（电压传输特性）分析的结果，里面有 VM、噪声容限等。
        r = s.vtc
        self.metrics_text.setText(
            f"Vtn = {s.vtn:+.3f} V\nVtp = {s.vtp:+.3f} V\n"
            f"Idsat,n = {s.idsat_n * 1e3:.3f} mA\nIdsat,p = {s.idsat_p * 1e3:.3f} mA\n"
            f"Ioff,n = {s.ioff_n:.2e} A\n"
            + (f"xj = {s.xj_um * 1e3:.0f} nm" if s.xj_um > 0 else f"tsi = {p.tsi_nm:.1f} nm"))
        self.metrics_text2.setText(
            f"VM = {r.vm:.3f} V\nNMH = {r.nmh:.2f} V\nNML = {r.nml:.2f} V\n"
            f"tpHL = {s.tran.tphl * 1e12:.1f} ps\ntpLH = {s.tran.tplh * 1e12:.1f} ps\n"
            f"DIBL = {s.dibl_n:.0f} mV/V")
        # 中文：参数页的“提取参数”（由工艺参数推算出的器件参数）：
        #   Cox    单位面积栅氧电容 = 介电常数 / 氧化层厚度，氧化层越薄越大；
        #   k'n/p  工艺跨导参数 = 迁移率 × Cox，决定同样尺寸的管子能有多大电流；
        #   γn/p   体效应系数：衬底掺杂越高，源-衬底电压对阈值电压的影响越大；
        #   Nd     N 阱的掺杂浓度；SSn/SSp 亚阈值摆幅：电流变化 10 倍需要多少 mV 栅压，越小开关越“干脆”；
        #   E=CV²  每次充放电负载电容消耗的能量（皮焦 pJ）。
        # 这里根据语言选中文或英文版本（条件表达式跨了多行）。
        # ---- params tab
        self.extract_text.setText(
            f"Cox = {s.cox * 1e7:.2f} fF/µm²\nk'n = {s.kpn * 1e6:.0f} µA/V²\nk'p = {s.kpp * 1e6:.0f} µA/V²\n"
            f"γn = {s.gamma_n:.2f} √V\nγp = {s.gamma_p:.2f} √V")
        self.extract_text2.setText(
            f"Nd(N阱) = {s.nd:.2e}\nSSn = {s.ss_n:.0f} mV/dec\nSSp = {s.ss_p:.0f} mV/dec\n"
            f"E = CV² = {p.cload_ff * p.vdd ** 2 / 1000:.2f} pJ\nVtn/Vtp: {s.vtn:+.2f}/{s.vtp:+.2f} V"
            if i18n.LANG == "zh" else
            f"Nd (well) = {s.nd:.2e}\nSSn = {s.ss_n:.0f} mV/dec\nSSp = {s.ss_p:.0f} mV/dec\n"
            f"E = CV² = {p.cload_ff * p.vdd ** 2 / 1000:.2f} pJ\nVtn/Vtp: {s.vtn:+.2f}/{s.vtp:+.2f} V")
        # 数值变了，曲线也要重画。
        self.plot_dirty = True
