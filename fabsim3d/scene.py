"""Panda3D rendering of the wafer: layers, animations, particles, labels, carriers.

【这个文件是做什么的】
本文件负责把“晶圆（wafer，即正在加工的硅片）”画到 3D 窗口里，是程序的“画师”。
  - geometry.py 用数学描述每块材料的形状（Solid）；
  - process_core.py 等工艺文件决定每一步加什么材料、刻掉什么材料（Wafer 里有很多层 layer）；
  - 本文件把这些形状变成 Panda3D 能显示的三角形网格，并负责：
      · 每一步工艺的动画（薄膜长出来、被刻蚀的部分缩下去、颜色渐变、高温发光）；
      · 粒子特效（光刻的紫外光、离子注入的离子、等离子刻蚀、淀积的原子）；
      · 光刻掩膜板和 CMP 抛光垫的动画；
      · 3D 文字标注（材料名、端口电压）；
      · 电路工作时的“载流子”小方块沿导线和沟道流动的动画；
      · 鼠标悬停时判断指的是哪一层材料（拾取 picking）。

【几个 3D 图形学基本概念】
  - Panda3D 里所有东西都挂在一棵“场景树”上，每个节点用 NodePath 表示；
    把节点挂到某个父节点下面（attachNewNode / reparentTo），它就会被画出来。
  - 3D 模型由许多小三角形拼成。每个三角形的顶点（vertex）有：位置、法向量、颜色。
  - 法向量（normal）：一个垂直于表面、指向外面的长度为 1 的箭头。灯光计算靠它判断表面
    朝向哪里、该多亮。本程序每个面用同一个法向量（“平面着色”），所以棱角分明。
"""
# 让类型提示在旧版 Python 中可用的固定写法。
from __future__ import annotations

# math：数学函数（正弦 sin、开方 sqrt、对数 log10 等）；random：随机数（粒子的随机位置）。
import math
import random
# 类型提示用的名字：Dict 字典、List 列表、Optional[X] 表示“X 或 None”、Tuple 元组。
from typing import Dict, List, Optional, Tuple

# 从 Panda3D 引擎导入要用到的类（括号可以让导入列表跨多行书写）：
#   Geom / GeomTriangles / GeomLines / GeomNode：几何体、三角形集合、线段集合、几何节点；
#   GeomVertexData / GeomVertexFormat / GeomVertexWriter：顶点数据表、它的格式、往表里写数据的工具；
#   NodePath：场景树中的节点；TextNode：3D 文字；TransparencyAttrib：透明设置；Vec4：四维向量。
from panda3d.core import (Geom, GeomLines, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, NodePath, TextNode,
                          TransparencyAttrib, Vec4)

# 前面的点 . 表示“从本包（fabsim3d 文件夹）里导入”。
from . import i18n                                     # 中英文切换
from .geometry import Solid, surface_height            # 材料块形状、求表面高度
from .materials import mat                             # 按材料名查颜色等属性
from .process_core import DOMAIN, PhaseAnim, Wafer     # 模型范围、动画说明书、晶圆

# 棱线（每块材料边缘的细黑线）的颜色：(红, 绿, 蓝, 不透明度)，每个数都在 0~1 之间。
# 不透明度 0.55 表示半透明，线条不会太抢眼。
EDGE_COLOR = (0.08, 0.08, 0.10, 0.55)


def _ease(t: float) -> float:
    """“缓入缓出”曲线：输入动画进度 t（0~1），输出平滑后的进度。

    为什么需要：如果动画匀速进行会显得生硬。用 3t² - 2t³ 这条 S 形曲线，
    开始和结束时慢、中间快，看起来更自然。
    """
    # 先把 t 限制在 0~1 之间（小于 0 当 0，大于 1 当 1）。
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _lerp4(a, b, t):
    """在两个颜色 a、b（各 4 个分量 RGBA）之间做线性插值：t=0 得 a，t=1 得 b，中间按比例混合。

    为什么需要：材料变色动画（例如多晶硅经掺杂后颜色变化）要让颜色逐渐过渡。
    """
    # tuple(... for i in range(4))：对 4 个分量分别计算，再组成元组。
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


def build_solids_node(name: str, items: List[Tuple[Solid, tuple]], cut_y: float,
                      edges: bool) -> NodePath:
    """One GeomNode with flat-shaded triangles (+ optional edge lines).

    把一组材料块（每块带一个颜色）转换成一个可显示的 3D 节点（由平面着色的三角形组成），
    可选地再加上棱线。这是本文件最核心的“建模”函数，所有层、掩膜、粒子方块都用它来生成。

    参数：
      name   —— 节点名字；
      items  —— [(材料块, 颜色), ...]；
      cut_y  —— 剖面切割位置：y < cut_y 的部分被切掉不画；
      edges  —— 是否画棱线。
    """
    # —— 准备“顶点表”：每个顶点存 位置(V3) + 法向量(n3) + 颜色(c4) ——
    # getV3n3c4 就是这种格式的名字；UHStatic 告诉显卡“数据画好后不会再改”，可以优化。
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    # 三个“写入器”，分别往顶点表里写位置、法向量、颜色。
    vw = GeomVertexWriter(vdata, "vertex")
    nw = GeomVertexWriter(vdata, "normal")
    cw = GeomVertexWriter(vdata, "color")
    # 三角形集合：每 3 个顶点编号组成一个三角形。
    tris = GeomTriangles(Geom.UHStatic)
    # —— 棱线用另一张顶点表（只需位置和颜色，线条不需要法向量）——
    ldata = GeomVertexData(name + "_e", GeomVertexFormat.getV3c4(), Geom.UHStatic)
    lvw = GeomVertexWriter(ldata, "vertex")
    lcw = GeomVertexWriter(ldata, "color")
    lines = GeomLines(Geom.UHStatic)
    # nv / nl：目前已经写入的三角形顶点数 / 线段顶点数，用来给新顶点编号。
    nv = 0
    nl = 0

    # 函数里面还可以再定义函数（“内部函数”），只在这个函数内部使用。
    def quad(p, n, c):
        """画一个四边形面：p 是 4 个顶点 (x,y,z)，n 是法向量，c 是颜色。拆成两个三角形。"""
        # nonlocal nv：声明要修改的是外层函数的变量 nv，而不是新建一个局部变量。
        nonlocal nv
        # 求两条边向量 a = p1 - p0，b = p2 - p0。
        ax, ay, az = (p[1][i] - p[0][i] for i in range(3))
        bx, by, bz = (p[2][i] - p[0][i] for i in range(3))
        # 三维叉积 a × b：得到一个垂直于这个面的向量，方向由顶点的绕行顺序决定（右手定则）。
        cr = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
        # 点积 cr·n < 0 说明顶点顺序与期望的朝向相反。
        # 显卡通常只画“正面”（顶点逆时针看过去的那一面），所以顺序反了就把顶点倒过来。
        # p[::-1] 是“切片”写法，表示把列表倒序。
        if cr[0] * n[0] + cr[1] * n[1] + cr[2] * n[2] < 0:
            p = p[::-1]
        # 写入 4 个顶点。*v 把 (x, y, z) 展开成三个独立参数传进去。
        for v in p:
            vw.addData3(*v)
            nw.addData3(*n)
            cw.addData4(*c)
        # 四边形 0-1-2-3 拆成两个三角形：(0,1,2) 和 (0,2,3)。
        tris.addVertices(nv, nv + 1, nv + 2)
        tris.addVertices(nv, nv + 2, nv + 3)
        nv += 4

    def seg(a, b):
        """画一条从点 a 到点 b 的棱线。"""
        nonlocal nl
        lvw.addData3(*a)
        lvw.addData3(*b)
        lcw.addData4(*EDGE_COLOR)
        lcw.addData4(*EDGE_COLOR)
        lines.addVertices(nl, nl + 1)
        nl += 2

    # —— 逐块材料生成网格 ——
    for s, col in items:
        # 剖面切割：起点 y 不能小于 cut_y（前面那部分被“切掉”）。
        y0 = max(s.y0, cut_y)
        y1 = s.y1
        # 切完没有长度了，或者材料薄得几乎没有厚度：不画。
        if y1 - y0 <= 1e-4 or s.zmax - s.zmin <= 1e-5:
            continue
        poly = s.poly
        npt = len(poly)
        # caps (fan) – front cap faces -y, back cap +y
        # —— 前后两个“端面”（截面多边形本身）——
        # 用“扇形三角剖分”：从第 0 个顶点出发，连接 (0, i, i+1)，把凸多边形切成若干三角形。
        # 前端面在 y0 处，朝向 -y（法向量 (0,-1,0)，即朝着观察者/切面）。
        base = nv
        for x, z in poly:
            vw.addData3(x, y0, z)
            nw.addData3(0, -1, 0)
            cw.addData4(*col)
        for i in range(1, npt - 1):
            tris.addVertices(base, base + i, base + i + 1)
        nv += npt
        # 后端面在 y1 处，朝向 +y。顶点顺序反过来（i+1 在前），让它的正面朝外。
        base = nv
        for x, z in poly:
            vw.addData3(x, y1, z)
            nw.addData3(0, 1, 0)
            cw.addData4(*col)
        for i in range(1, npt - 1):
            tris.addVertices(base, base + i + 1, base + i)
        nv += npt
        # sides
        # —— 侧面：多边形的每条边沿 y 拉伸成一个长方形侧面 ——
        for i in range(npt):
            (xa, za), (xb, zb) = poly[i], poly[(i + 1) % npt]
            # 这条边在 x-z 平面里的方向 (dx, dz) 和长度 ln（math.hypot 求直角三角形斜边长）。
            dx, dz = xb - xa, zb - za
            ln = math.hypot(dx, dz)
            # 长度为 0 的“边”（重复顶点）跳过，否则下面会除以 0。
            if ln < 1e-9:
                continue
            # 侧面的法向量：把边方向 (dx, dz) 旋转 90° 得到 (dz, -dx)，再除以长度变成单位长度。
            # 对逆时针多边形，这样得到的方向正好指向多边形外侧。y 分量为 0（侧面与 y 平行）。
            n = (dz / ln, 0, -dx / ln)
            quad([(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)], n, col)
            if edges:
                # 每条边画 3 根棱线：前端面上的边、后端面上的边、以及沿 y 的那条棱。
                seg((xa, y0, za), (xb, y0, zb))
                seg((xa, y1, za), (xb, y1, zb))
                seg((xa, y0, za), (xa, y1, za))

    # —— 把顶点表和三角形打包成节点 ——
    gnode = GeomNode(name)
    # 有顶点才创建几何体（全被切掉时就是一个空节点）。
    if nv:
        g = Geom(vdata)
        g.addPrimitive(tris)
        gnode.addGeom(g)
    # 变量名 np_ 末尾加下划线，是为了避免和常用缩写 np（numpy）混淆。
    np_ = NodePath(gnode)
    if edges and nl:
        lg = Geom(ldata)
        lg.addPrimitive(lines)
        ln_node = GeomNode(name + "_edges")
        ln_node.addGeom(lg)
        # 棱线作为子节点挂在模型下面。
        enp = np_.attachNewNode(ln_node)
        # 线条不受灯光影响（始终是设定的颜色）；开启透明；
        # setDepthOffset(1)：让线条在深度比较时稍微“靠前”，避免与它所在的面重合而闪烁。
        enp.setLightOff()
        enp.setTransparency(TransparencyAttrib.MAlpha)
        enp.setDepthOffset(1)
    return np_


def _fmt_amp(i: float) -> str:
    """把电流值（单位安培）格式化成易读的文字，自动选单位：mA（毫安）、µA（微安）、nA（纳安）、pA（皮安）。"""
    # 从大单位到小单位依次尝试，第一个“电流 >= 该单位”的就用它。
    for scale, unit in ((1e-3, "mA"), (1e-6, "µA"), (1e-9, "nA")):
        if i >= scale:
            # f-string 中 {数值:.3g} 表示保留 3 位有效数字。
            return f"{i / scale:.3g} {unit}"
    return f"{i / 1e-12:.2g} pA"


def _unit_cube() -> NodePath:
    """生成一个边长为 1、中心在原点的白色小立方体模型。

    为什么需要：粒子和载流子都画成小方块。先做一个“模板”，用时复制、缩放、上色即可，比每次重建快。
    """
    s = Solid.box(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5)
    # cut_y 传 -99（远小于任何 y），表示不做任何切割；不要棱线。
    return build_solids_node("cube", [(s, (1, 1, 1, 1))], -99, False)


def default_channels(lay) -> list:
    """Inversion layers of the planar devices: a thin sheet under each gate.

    平面晶体管的“反型层”（导电沟道）：每个栅极正下方的一层薄片。
    物理含义：当栅极电压超过“阈值电压”（Vt，让晶体管开始导通的最低栅压）时，
    栅极下方硅表面会聚集大量与衬底类型相反的载流子（NMOS 是电子，PMOS 是空穴），
    形成一层很薄的导电通道，把源极和漏极连起来，晶体管就“打开”了。
    这里返回 [(键 "n"/"p", 沟道形状)]，lay["gn"] / lay["gp"] 是 NMOS / PMOS 栅极的 x 范围。
    沟道比栅极左右各宽 0.12，位于硅表面下方一点点（z 从 -0.06 到 -0.005）。
    """
    return [(key, Solid.box(g[0] - 0.12, g[1] + 0.12, 1.5, 6.5, -0.06, -0.005))
            for key, g in (("n", lay["gn"]), ("p", lay["gp"]))]


def default_carrier_paths(lay, ym: float) -> dict:
    """(x, y, z) paths.  "n"/"p": carriers inside each transistor, contact plug ->
    S/D -> channel -> S/D -> plug.  The rest is electron flow in metal 1, which
    closes the loop GND -> NMOS -> Vout -> PMOS -> VDD (conventional current runs
    the other way).  The Vout wire is split at the output node: its NMOS half
    carries In and its PMOS half Ip, so during a transient only the half that
    charges / discharges CL flows.

    【中文说明】载流子动画的运动路线，每条路线是一串 (x, y, z) 拐点，小方块沿折线移动。
      - "n" / "p"：晶体管内部的路线：接触孔 -> 源/漏区 -> 沟道 -> 漏/源区 -> 接触孔。
      - 其余几条是第一层金属导线（metal 1）里的电子流动，组成回路：
        地 GND -> NMOS -> 输出 Vout -> PMOS -> 电源 VDD。
        （注意：习惯上的“电流方向”与电子运动方向相反。）
      - 输出导线在输出节点处分成两半："on" 属于 NMOS 那半，流的是 NMOS 电流 In；
        "op" 属于 PMOS 那半，流的是 PMOS 电流 Ip。这样在瞬态（输入突变）时，
        只有正在给负载电容 CL 充电（PMOS 侧）或放电（NMOS 侧）的那一半在流动。
    参数 ym：载流子所在的 y 平面（放在剖面切口稍后面，让切开后能看见）。
    """
    zm = 1.55                      # inside metal 1  （金属 1 层的高度）
    yr = 4.7                       # far end of the GND / VDD rails  （地线/电源线远端的 y）
    xo = (7.15 + 13.35) / 2        # Vout node (where the load CL hangs)  （输出节点：负载电容接在这里）
    # 下面数字 3.35、7.15、13.35、17.15 是各个接触孔的 x 位置；z = 1.45 在接触孔顶部，
    # z = -0.15 在硅里面的源/漏区，z = -0.035 在沟道里。
    return {
        "n": [(3.35, ym, 1.45), (3.35, ym, -0.15), (lay["gn"][0], ym, -0.035),
              (lay["gn"][1], ym, -0.035), (7.15, ym, -0.15), (7.15, ym, 1.45)],
        "p": [(17.15, ym, 1.45), (17.15, ym, -0.15), (lay["gp"][1], ym, -0.035),
              (lay["gp"][0], ym, -0.035), (13.35, ym, -0.15), (13.35, ym, 1.45)],
        "gnd": [(3.35, yr, zm), (3.35, ym, zm), (3.35, ym, 1.45)],
        "on": [(7.15, ym, 1.45), (7.15, ym, zm), (xo, ym, zm)],
        "op": [(xo, ym, zm), (13.35, ym, zm), (13.35, ym, 1.45)],
        "vdd": [(17.15, ym, 1.45), (17.15, ym, zm), (17.15, yr, zm)],
    }


def _snap_to_bands(y: float, bands) -> float:
    """Nearest y inside one of the silicon bands (fins / nanosheet stacks).

    把 y 移到最近的一条“硅带”内部。
    为什么需要：FinFET（鳍式晶体管）和纳米片晶体管的硅不是一整片，而是一条条竖着的“鳍”
    或一叠薄片，中间是空隙/绝缘体。载流子只能在硅里跑，所以动画平面必须落在某条硅带里。
    bands 是 [(y0, y1), ...]，每一项是一条硅带的 y 范围。
    """
    best = None
    for y0, y1 in bands:
        # 把 y 夹到这条带内（离边缘留 0.04 的余量）。
        c = min(max(y, y0 + 0.04), y1 - 0.04)
        # 保留离原来 y 最近的那个结果。
        if best is None or abs(c - y) < abs(best - y):
            best = c
    return y if best is None else best


# --------------------------------------------------------------------------

class Particle:
    """一个粒子特效（例如一束紫外光、一颗离子）的数据。

    __slots__ 规定这个类的对象只能有这几个属性，好处是更省内存、更快（粒子数量很多）。
    各属性：np 它的 3D 节点；x/y/z 当前位置；vz 竖直速度（负数表示往下落）；
    stop 落到哪个高度停下（碰到表面）；life 落地后还能存在多久（秒，用于淡出）；kind 粒子种类。
    """
    __slots__ = ("np", "x", "y", "z", "vz", "stop", "life", "kind")


class WaferScene:
    """管理整个晶圆 3D 场景的类：模型的建立与刷新、动画、粒子、标注、载流子仿真、鼠标拾取。

    为什么需要：主程序（app.py）只需告诉它“现在晶圆是什么样”“开始播放哪个动画”“切面在哪”，
    具体怎么画、怎么动都由这个类负责，把“画图”和“界面/工艺逻辑”分开。
    """

    def __init__(self, base, parent: NodePath):
        """构造函数：创建 WaferScene 对象时自动执行，设置好各个场景节点和初始状态。

        base：Panda3D 程序主对象；parent：所有内容挂在它下面的父节点。
        """
        self.base = base
        # 晶圆各层模型都挂在 root 节点下。
        self.root = parent.attachNewNode("wafer")
        # 每一层材料对应一个 3D 节点：{层名: 节点}。
        # “变量: 类型 = 值” 是带类型提示的赋值，帮助阅读。
        self.layer_nodes: Dict[str, NodePath] = {}
        # “幽灵”节点：动画中正在消失的旧材料（被刻蚀/淡出的部分）。
        self.ghost_node: Optional[NodePath] = None
        # 光刻掩膜板节点、CMP 抛光垫节点（只在对应动画时存在）。
        self.mask_node: Optional[NodePath] = None
        self.pad_node: Optional[NodePath] = None
        # 特效（粒子）的父节点；关闭灯光，让粒子始终保持鲜艳颜色。
        self.fx = parent.attachNewNode("fx")
        self.fx.setLightOff()
        # 文字标注的父节点；载流子动画的父节点（同样不受灯光影响）。
        self.labels_root = parent.attachNewNode("labels")
        self.carrier_root = parent.attachNewNode("carriers")
        self.carrier_root.setLightOff()
        # 小立方体模板，粒子和载流子都复制它。
        self.cube = _unit_cube()
        # 当前显示的晶圆数据。
        self.wafer: Optional[Wafer] = None
        # 剖面切割位置（0 = 不切）、是否显示棱线、是否显示标注。
        self.cut_y = 0.0
        self.edges = True
        self.show_labels = True
        # 当前动画：动画说明书、进度（0~1）、总时长（秒）。
        self.anim: Optional[PhaseAnim] = None
        self.anim_t = 0.0
        self.anim_dur = 1.0
        # 当前存在的粒子列表；spawn_acc 用来累积“不足一个”的小数粒子数（见 _spawn_particles）。
        self.particles: List[Particle] = []
        self.spawn_acc = 0.0
        # terminal_mode：工艺全部完成后进入“端口模式”，显示 VDD/GND/Vin/Vout 等端口标注。
        self.terminal_mode = False
        # 电学仿真结果（各端电压、电流等），None 表示没开启 3D 载流子仿真。
        self.sim_values: Optional[dict] = None
        # 载流子小方块列表、沟道节点。
        self.carriers: list = []
        self.channel_nodes: Dict[str, NodePath] = {}
        # ctx：上下文信息（当前工艺流程 flow、版图尺寸 lay 等）。
        self.ctx = None

    # ---------------------------------------------------------------- state
    # —— 状态：设置晶圆、整体重建 ——
    def set_wafer(self, wafer: Wafer, ctx, terminal_mode: bool = False):
        """换一个晶圆状态来显示（例如跳到某一步）。会先结束正在播放的动画，再全部重建。"""
        self.finish_anim()
        self.wafer = wafer
        self.ctx = ctx
        self.terminal_mode = terminal_mode
        self.rebuild_all()

    def rebuild_all(self):
        """删掉所有层的 3D 节点并重新生成，同时重建幽灵、标注和沟道。

        为什么需要：切面位置、棱线开关、晶圆内容变化时，模型都必须重新生成。
        """
        # list(...) 先复制一份键名列表，因为循环中要从字典里删东西（边遍历边删会出错）。
        # .pop(n) 从字典取出并删除该项，.removeNode() 把节点从场景中移除。
        for n in list(self.layer_nodes):
            self.layer_nodes.pop(n).removeNode()
        if self.wafer:
            for name in self.wafer.layers:
                self._rebuild_layer(name)
        self._rebuild_ghosts()
        self.rebuild_labels()
        self._rebuild_channels()

    def _layer_items(self, name: str) -> List[Tuple[Solid, tuple]]:
        """算出某一层在“当前动画进度”下，每块材料该画成什么形状、什么颜色。

        动画效果在这里实现：
          - recolor：颜色从旧材料色渐变到新材料色；
          - grow：材料从基准面开始按进度长高；
          - fade_in：材料按进度从透明变到不透明。
        """
        layer = self.wafer.layers[name]
        m = mat(layer.material)
        col = m.color
        a = self.anim
        # 有动画时用平滑后的进度 e，没有动画时直接是完成状态 1.0。
        e = _ease(self.anim_t) if a else 1.0
        # 这一层在变色：从旧材料的颜色过渡到当前材料颜色。
        if a and name in a.recolor:
            col = _lerp4(mat(a.recolor[name]).color, col, e)
        items = []
        # id(x) 是对象的“身份编号”。用编号集合来判断某块是否在 grow / fade_in 列表里，
        # 因为要区分“同一个对象”，而不是“形状相同的对象”。
        # map(id, 列表) 对列表每个元素都调用 id；set(...) 变成集合，查找很快。
        grow = set(map(id, a.grow)) if a else set()
        fade = set(map(id, a.fade_in)) if a else set()
        for s in layer.solids:
            c = col
            sol = s
            if id(s) in grow:
                # 生长动画：以 anchor（没有就用底面 zmin）为基准，高度乘以进度 e。
                # 至少 0.002，避免高度为 0 时被当作“没有厚度”而不画。
                anchor = s.anchor if s.anchor is not None else s.zmin
                sol = s.scaled_z(anchor, max(e, 0.002))
            if id(s) in fade:
                # 淡入动画：不透明度（颜色第 4 个分量）乘以进度 e。
                c = (c[0], c[1], c[2], c[3] * e)
            items.append((sol, c))
        return items

    def _style(self, np_: NodePath, material: str, alpha: bool):
        """给一层材料的节点设置显示方式（深度优先级、透明）。"""
        # 深度偏移：多块材料表面重合时（例如注入区画在衬底里面），优先级高的显示在前面。
        np_.setDepthOffset(mat(material).priority)
        if alpha:
            # 半透明材料：开启透明混合。
            np_.setTransparency(TransparencyAttrib.MAlpha)
            # 只有基本不透明的材料才写入“深度缓冲”（记录每个像素最近的物体有多远），
            # 真正半透明的材料不写，这样后面的东西还能透过它看到。
            np_.setDepthWrite(mat(material).color[3] >= 0.99)
            np_.setTwoSided(False)

    def _rebuild_layer(self, name: str):
        """重新生成某一层的 3D 节点（先删旧的再建新的）。"""
        # pop(name, None)：取出并删除；不存在时返回 None 而不报错。
        old = self.layer_nodes.pop(name, None)
        if old:
            old.removeNode()
        # 这一层已经不存在了（被完全刻蚀掉），删掉就行，不用再建。
        if name not in self.wafer.layers:
            return
        items = self._layer_items(name)
        node = build_solids_node(name, items, self.cut_y, self.edges)
        node.reparentTo(self.root)
        # 只要有一块颜色不是完全不透明（例如正在淡入），整层就按透明方式处理。
        # “for _, c in items”中的 _ 表示忽略元组中的第一个值（形状）。
        alpha = any(c[3] < 0.999 for _, c in items)
        self._style(node, self.wafer.layers[name].material, alpha)
        self.layer_nodes[name] = node

    def _rebuild_ghosts(self):
        """重新生成“幽灵”：本步动画中正在消失的旧材料。

        两种消失方式：
          - "etch"（刻蚀）：从上往下变薄，直到没有（模拟材料被一层层刻掉）；
          - 其它（fade，淡出）：保持形状，逐渐变透明（例如光刻胶被去除）。
        """
        if self.ghost_node:
            self.ghost_node.removeNode()
            self.ghost_node = None
        # 没有动画或没有要消失的材料：什么都不做。
        if not self.anim or not self.anim.ghosts:
            return
        e = _ease(self.anim_t)
        self.ghost_node = self.root.attachNewNode("ghosts")
        # 按材料分组：同一种材料的块合在一个节点里，减少节点数量。
        by_mat: Dict[str, list] = {}
        for material, s, mode in self.anim.ghosts:
            col = mat(material).color
            if mode == "etch":
                # 已经刻完了，不用画。
                if e >= 0.999:
                    continue
                # 以底面为基准，高度缩为 (1 - 进度)：越来越薄。
                sol = s.scaled_z(s.zmin, 1 - e)
            else:
                sol = s
                col = (col[0], col[1], col[2], col[3] * (1 - e))
            by_mat.setdefault(material, []).append((sol, col))
        for material, items in by_mat.items():
            n = build_solids_node("ghost_" + material, items, self.cut_y, self.edges)
            n.reparentTo(self.ghost_node)
            self._style(n, material, True)

    # ---------------------------------------------------------------- anim
    # —— 动画：开始、推进、结束 ——
    def start_anim(self, anim: PhaseAnim, duration: float):
        """开始播放一个动画阶段。anim 是动画说明书，duration 是时长（秒）。"""
        self.anim = anim
        self.anim_t = 0.0
        # 时长至少 0.05 秒，防止后面除以 0。
        self.anim_dur = max(duration, 0.05)
        self.spawn_acc = 0.0
        # 光刻步骤：建立掩膜板模型。
        if anim.mask:
            self._build_mask(anim.mask)
        # CMP（化学机械抛光）步骤：建立抛光垫模型。
        if anim.pad is not None:
            self._build_pad()
        self._refresh_anim_layers()

    def _anim_layers(self):
        """找出在本次动画中会变化（需要每帧重画）的层的名字集合。

        为什么需要：每帧重建全部层太慢，只重建正在变化的层。
        """
        a = self.anim
        # 正在变色的层。
        names = set(a.recolor)
        # | 是集合的“并集”：生长的块和淡入的块的编号合在一起。
        ids = set(map(id, a.grow)) | set(map(id, a.fade_in))
        # 某层里只要有一块在生长或淡入，这层就需要重画。
        for name, layer in self.wafer.layers.items():
            if any(id(s) in ids for s in layer.solids):
                names.add(name)
        return names

    def _refresh_anim_layers(self):
        """动画开始时，同步场景节点和晶圆数据：删掉已不存在的层，建好新出现的层和动画相关层。"""
        # layers added/removed by the phase must exist/disappear
        # （本阶段新增或删除的层，其节点也要相应出现或消失）
        for name in list(self.layer_nodes):
            if name not in self.wafer.layers:
                self.layer_nodes.pop(name).removeNode()
        for name in self.wafer.layers:
            if name not in self.layer_nodes or name in self._anim_layers():
                self._rebuild_layer(name)
        self._rebuild_ghosts()
        self.rebuild_labels()

    def update(self, dt: float, speed: float = 1.0) -> bool:
        """Advance animation; returns True when the current phase finished.

        每一帧调用一次，把动画向前推进。dt 是距上一帧过了多少秒，speed 是播放速度倍数。
        返回 True 表示当前动画阶段刚刚播完。
        """
        done = False
        if self.anim:
            # 进度增加量 = 经过时间 × 速度 / 总时长。
            self.anim_t += dt * speed / self.anim_dur
            if self.anim_t >= 1.0:
                self.anim_t = 1.0
                done = True
            # 按新进度重画变化中的层、幽灵、掩膜、抛光垫、发光效果，并产生新粒子。
            for name in self._anim_layers():
                self._rebuild_layer(name)
            self._rebuild_ghosts()
            self._update_mask()
            self._update_pad()
            self._update_glow()
            self._spawn_particles(dt * speed)
        # 粒子在动画结束后还要继续落完；载流子动画按真实时间运行（不受速度倍数影响）。
        self._update_particles(dt * speed)
        self._update_carriers(dt)
        if done:
            self.finish_anim()
        return done

    def finish_anim(self):
        """立即结束当前动画：清除掩膜、抛光垫、发光效果，并把场景重建成最终状态。"""
        if not self.anim:
            return
        self.anim_t = 1.0
        self.anim = None
        if self.mask_node:
            self.mask_node.removeNode()
            self.mask_node = None
        if self.pad_node:
            self.pad_node.removeNode()
            self.pad_node = None
        # 去掉“高温发光”时加上的颜色倍增。
        self.root.clearColorScale()
        if self.wafer:
            self.rebuild_all()

    def clear_particles(self):
        """删除所有粒子。"""
        for p in self.particles:
            p.np.removeNode()
        self.particles.clear()

    # ---------------------------------------------------------------- mask / glow
    # —— 掩膜板 / 抛光垫 / 发光 ——
    def _build_mask(self, spec):
        """建立光刻掩膜板模型。

        工艺含义：光刻（photolithography）时，紫外光透过掩膜板照到涂了光刻胶的硅片上。
        掩膜板是一块透明石英玻璃，上面镀了铬（chrome）的图形，铬挡光、玻璃透光，
        这样就能把电路图形“印”到光刻胶上。这里用半透明的浅蓝方块表示玻璃，深灰色块表示铬图形。
        spec.z 是掩膜板的高度，spec.chrome 是铬图形的矩形列表。
        """
        if self.mask_node:
            self.mask_node.removeNode()
        # 掩膜挂在 render（整个世界的根节点）下，不跟随晶圆节点的颜色效果。
        self.mask_node = self.base.render.attachNewNode("mask")
        # DOMAIN 是整个模型的范围 (x0, x1, y0, y1)；玻璃比它四周各大 0.5。
        x0, x1, y0, y1 = DOMAIN
        z = spec.z
        glass = Solid.box(x0 - 0.5, x1 + 0.5, y0 - 0.5, y1 + 0.5, z, z + 0.08)
        g = build_solids_node("glass", [(glass, (0.75, 0.9, 1.0, 0.25))], -99, True)
        g.reparentTo(self.mask_node)
        g.setTransparency(TransparencyAttrib.MAlpha)
        # 玻璃透明，不写深度，以免挡住下面的东西。
        g.setDepthWrite(False)
        # 铬图形：薄薄地贴在玻璃上方。r 是每个铬矩形 (x0, x1, y0, y1)。
        chrome = [Solid.box(r[0], r[1], r[2], r[3], z + 0.08, z + 0.12) for r in spec.chrome]
        c = build_solids_node("chrome", [(s, (0.12, 0.12, 0.14, 0.92)) for s in chrome], -99, False)
        c.reparentTo(self.mask_node)
        c.setTransparency(TransparencyAttrib.MAlpha)
        # 一开始完全透明（不可见），由 _update_mask 逐渐显现。
        self.mask_node.setAlphaScale(0.0)

    def _update_mask(self):
        """掩膜动画：前 15% 进度淡入，最后 15% 淡出；前 20% 进度从上方 1.5 高处降落到位。"""
        if not self.mask_node:
            return
        t = self.anim_t
        a = min(1.0, t / 0.15) if t < 0.85 else max(0.0, (1 - t) / 0.15)
        self.mask_node.setAlphaScale(a)
        self.mask_node.setZ((1 - min(1.0, t / 0.2)) * 1.5)

    def _build_pad(self):
        """CMP polishing pad: a translucent grooved pad riding on the surface being polished.

        建立 CMP 抛光垫模型：一块半透明、底面带沟槽的垫子，压在正被抛光的表面上。
        工艺含义：CMP（化学机械抛光）用旋转的抛光垫加上研磨液，把高低不平的表面磨平，
        方便后续光刻和布线。动画中垫子从最高点开始，随着磨削下降到目标高度 anim.pad。
        """
        if self.pad_node:
            self.pad_node.removeNode()
        self.pad_node = self.base.render.attachNewNode("cmp_pad")
        # 垫子在 y 方向只覆盖切面之后的部分，避免挡住剖面。
        y0, y1 = max(self.cut_y, 0.0) - 0.3, 8.3
        # 垫子主体：厚 0.3 的半透明蓝灰色板，底面在 z=0（之后整体移动到合适高度）。
        items = [(Solid.box(-1.5, 21.5, y0, y1, 0.0, 0.3), (0.55, 0.60, 0.72, 0.45))]
        for k in range(12):          # grooves  （12 条沟槽，间隔 1.9）
            x = -1.0 + k * 1.9
            items.append((Solid.box(x, x + 0.25, y0, y1, -0.02, 0.0), (0.85, 0.88, 0.95, 0.55)))
        pad = build_solids_node("pad", items, -99, False)
        pad.reparentTo(self.pad_node)
        pad.setTransparency(TransparencyAttrib.MAlpha)
        pad.setDepthWrite(False)
        # 放进“透明物体”绘制队列并指定较晚绘制（序号 30），确保透明效果正确叠加。
        pad.setBin("transparent", 30)
        self.pad_node.setLightOff()
        # 起始高度 = 被磨掉部分（幽灵）中最高的顶面；没有幽灵就直接用目标高度。
        tops = [s.zmax for _, s, _ in self.anim.ghosts]
        self.pad_start = max(tops) if tops else self.anim.pad
        self._update_pad()

    def _update_pad(self):
        """抛光垫动画：开头 8% 从上方降下，中间随表面一起下降并左右晃动（模拟旋转摩擦），结尾 8% 抬起并淡出。"""
        if not self.pad_node or not self.anim or self.anim.pad is None:
            return
        t = self.anim_t
        e = _ease(t)
        # lower：降下的进度（0→1），up：抬起的进度（0→1）。
        lower = min(1.0, t / 0.08)
        up = max(0.0, (t - 0.92) / 0.08)
        # 当前被磨到的表面高度：从起始高度平滑下降到目标高度。
        surface = self.pad_start - (self.pad_start - self.anim.pad) * e
        # 垫子高度 = 表面 + 一点点间隙 + 降下前/抬起后的额外高度。
        z = surface + 0.02 + (1 - lower) * 2.0 + up * 2.0
        # x 方向用正弦函数快速来回摆动，表现“打磨”的动作。
        self.pad_node.setPos(math.sin(t * 60) * 0.5, 0, z)
        self.pad_node.setAlphaScale(1.0 - up)

    def _update_glow(self):
        """高温工艺（氧化、退火）时让晶圆“发光”：整体颜色向发光色偏移，强度随进度先增后减。"""
        g = self.anim.glow if self.anim else None
        if not g:
            return
        # sin(π t) 在 t=0 和 t=1 时为 0，在 t=0.5 时最大：表示升温再降温。
        k = 0.55 * math.sin(math.pi * self.anim_t)
        # setColorScale 把整个晶圆的颜色乘以 (红, 绿, 蓝, 透明) 系数；红色额外多加一点，看起来更像炽热。
        self.root.setColorScale(1 + (g[0] - 1) * k + 0.15 * k, 1 + (g[1] - 1) * k, 1 + (g[2] - 1) * k, 1)

    # ---------------------------------------------------------------- particles
    # —— 粒子特效 ——
    def _spawn_particles(self, dt):
        """按动画说明书里的粒子规格，在本帧产生新粒子。

        粒子落点在指定区域内随机分布，区域越大粒子越多（按面积加权）。
        """
        # 动画进行到 85% 以后不再产生新粒子，让已有的粒子在结束前落完。
        if not self.anim or self.anim_t > 0.85:
            return
        for spec in self.anim.particles:
            # 没指定区域就是整个模型范围。
            regions = spec.region or [DOMAIN]
            # 每个区域的可见面积（只算切面后面看得见的部分）。至少 1e-6，避免权重为 0。
            areas = [max(1e-6, (r[1] - r[0]) * max(0.0, r[3] - max(r[2], self.cut_y))) for r in regions]
            total = sum(areas)
            if total <= 1e-5:
                continue
            # 本帧应产生的粒子数 = 速率 × 时间 × 面积比例（最多为 1）。
            # 结果常常是小数（如 0.4 个），把上一帧剩下的小数部分 spawn_acc 加进来，
            # 取整数部分产生粒子，余下的小数留到下一帧——这样长期平均的数量是准确的。
            n_float = spec.rate * dt * min(1.0, total / 160.0) + self.spawn_acc
            n = int(n_float)
            self.spawn_acc = n_float - n
            for _ in range(n):
                # random.choices 按权重随机挑一个区域（面积大的更容易被选中），[0] 取出结果。
                r = random.choices(regions, weights=areas)[0]
                # 在区域内随机取一个落点 (x, y)。
                x = random.uniform(r[0], r[1])
                y = random.uniform(max(r[2], self.cut_y), r[3])
                self._spawn_one(spec, x, y)

    def _spawn_one(self, spec, x, y):
        """在 (x, y) 上方产生一个粒子，根据粒子种类设定起始高度、下落速度和外形。"""
        p = Particle()
        p.kind = spec.kind
        p.x, p.y = x, y
        # 粒子下落到“阻挡层”表面就停下，例如注入的离子被光刻胶挡住、或打到硅表面。
        p.stop = surface_height(spec.stop_solids, x, y)
        if spec.kind == "uv":
            # 紫外光（光刻曝光）：从掩膜板处出发，速度快，外形细长像一道光线。
            p.z = (self.anim.mask.z if self.anim.mask else 4.0)
            p.vz = -9.0
            scale = (0.035, 0.035, 0.45)
        elif spec.kind == "ion":
            # 离子注入：离子被电场加速，以很高速度打进硅里，所以最快。
            p.z = 5.0
            p.vz = -11.0
            scale = (0.07, 0.07, 0.07)
        elif spec.kind == "plasma":
            # 等离子刻蚀：带电的活性粒子轰击表面。
            p.z = 4.0
            p.vz = -6.0
            scale = (0.08, 0.08, 0.08)
        else:  # depo
            # 淀积：气体中的原子/分子慢慢落到表面形成薄膜，速度最慢。
            p.z = 4.0
            p.vz = -4.5
            scale = (0.09, 0.09, 0.09)
        # 落地后还能停留 0.25 秒（淡出）。
        p.life = 0.25
        # 复制小立方体模板，缩放、上色、放到起始位置。
        p.np = self.cube.copyTo(self.fx)
        p.np.setScale(*scale)
        p.np.setColor(*spec.color)
        p.np.setPos(x, y, p.z)
        self.particles.append(p)

    def _update_particles(self, dt):
        """每帧移动所有粒子：还在空中的继续下落；落地的倒计时淡出，时间到就删除。"""
        keep = []
        for p in self.particles:
            if p.z > p.stop:
                # 还在空中：按速度下落（位置 += 速度 × 时间），但不低于停止高度。
                p.z = max(p.stop, p.z + p.vz * dt)
                # 紫外光粒子是细长条，中心抬高 0.22，让它的下端正好碰到表面。
                p.np.setZ(p.z + (0.22 if p.kind == "uv" else 0))
                keep.append(p)
            else:
                # 已落地：减少剩余寿命。
                p.life -= dt
                if p.life <= 0:
                    p.np.removeNode()
                else:
                    # 透明度随剩余寿命按比例降低，形成淡出效果。
                    p.np.setAlphaScale(p.life / 0.25)
                    p.np.setTransparency(TransparencyAttrib.MAlpha)
                    keep.append(p)
        # 只保留还存在的粒子。
        self.particles = keep

    # ---------------------------------------------------------------- labels
    # —— 3D 文字标注 ——
    def _label(self, text: str, pos, scale=0.42, fg=(1, 1, 1, 1), bg=(0, 0, 0, 0.55)):
        """在 3D 位置 pos 放一个文字标签。fg 是文字颜色，bg 是背景底板颜色，scale 是大小。"""
        tn = TextNode("lbl")
        tn.setText(text)
        # 文字居中对齐。
        tn.setAlign(TextNode.ACenter)
        tn.setTextColor(*fg)
        # 文字后面加一块半透明底板（“卡片”），四周留边距，让文字在复杂背景上也清楚。
        tn.setCardColor(*bg)
        tn.setCardAsMargin(0.2, 0.2, 0.1, 0.1)
        tn.setCardDecal(True)
        np_ = self.labels_root.attachNewNode(tn)
        np_.setScale(scale)
        np_.setPos(*pos)
        # “广告牌”效果：无论相机怎么转，文字始终正面朝向观察者。
        np_.setBillboardPointEye()
        # 放到“固定”绘制队列较后的位置，并关闭深度测试：文字总是画在最上面，不会被模型挡住。
        np_.setBin("fixed", 50)
        np_.setDepthTest(False)
        np_.setDepthWrite(False)
        np_.setLightOff()
        return np_

    def rebuild_labels(self):
        """重新生成所有文字标注：区域名称（如“N 阱”“栅氧”），完成后还有端口电压和 NMOS/PMOS 标签。"""
        # 先删掉所有旧标签。
        for child in self.labels_root.getChildren():
            child.removeNode()
        if not self.show_labels or not self.wafer:
            return
        # 标签放在剖面切口稍前一点的位置，这样切开后标签正好在截面上。
        yf = max(self.cut_y, 0.0) - 0.05
        # 正在消失的材料不显示标签。
        # {m for m, _, _ in ...} 是集合推导式，只取出每个幽灵的材料名。
        animating_out = set()
        if self.anim:
            animating_out = {m for m, _, _ in self.anim.ghosts}
        flow = self.ctx.flow if self.ctx else None
        # region_labels 每项是 (层名, 中文名, 英文名, x, z)；该层存在才显示它的名字。
        for layer, zh, en, x, z in (flow.region_labels if flow else []):
            if self.wafer.has(layer) and layer not in animating_out:
                self._label(i18n.pick(zh, en), (x, yf, z), 0.38)
        if self.terminal_mode:
            # —— 工艺完成后：显示端口（VDD、GND、Vin、Vout）及其电压 ——
            vals = self.sim_values or {}
            # “name, x, y, *z”：前三个值分别给 name/x/y，剩下的（可能有一个，也可能没有）收集成列表 z。
            for name, x, y, *z in (flow.terminal_labels if flow else []):
                text = name
                key = name.lower()
                if key in vals:
                    # 有仿真结果时在端口名后显示电压，保留 2 位小数。
                    text = f"{name} = {vals[key]:.2f} V"
                    # 电源端额外显示电源电流 IDD（等于 PMOS 电流 ip）。\n 表示换行。
                    if key == "vdd" and "ip" in vals:
                        text += f"\nIDD = {_fmt_amp(vals['ip'])}"
                # 位于前半部分的标签要挪到切面后面，否则会被切掉的那部分“悬空”。
                ly = max(y, self.cut_y + 0.4) if y < 6 else y
                # 有指定高度就用它（z[0]），否则默认 2.2。端口标签用黄色字、深蓝底。
                self._label(text, (x, ly, z[0] if z else 2.2), 0.36, fg=(1, 0.95, 0.4, 1),
                            bg=(0.05, 0.05, 0.1, 0.75))
            if flow and flow.device_labels:
                # 工艺流程自定义的器件标签；文字可以是普通字符串，也可以是 (中文, 英文) 对。
                # isinstance(text, str) 判断 text 是不是字符串；*text 把 (中文, 英文) 展开传给 pick。
                for text, x, y, z, fg in flow.device_labels:
                    self._label(text if isinstance(text, str) else i18n.pick(*text), (x, y, z), 0.42, fg=fg)
            else:
                # 默认：在两个栅极中心上方分别标出 NMOS（红色）和 PMOS（蓝色）。
                ln, lp = self.ctx.lay["gnc"], self.ctx.lay["gpc"]
                self._label("NMOS", (ln, 8.6, 1.9), 0.42, fg=(1, 0.6, 0.6, 1))
                self._label("PMOS", (lp, 8.6, 1.9), 0.42, fg=(0.6, 0.7, 1, 1))

    # ---------------------------------------------------------------- simulation
    # —— 3D 载流子仿真（电路工作时的可视化）——
    def _rebuild_channels(self):
        """重新生成导电沟道和载流子小方块。

        只有在“工艺已完成 + 开启了仿真 + 有上下文信息”时才显示：
          - 沟道：栅极下的薄层，其透明度表示反型（导通）程度；
          - 载流子：沿 default_carrier_paths 等路线运动的小方块，
            NMOS 里是电子（青色），PMOS 里是空穴（橙色），金属线里是电子。
        """
        # 删掉旧的沟道节点和载流子。
        for n in self.channel_nodes.values():
            n.removeNode()
        self.channel_nodes.clear()
        for c in self.carriers:
            c[0].removeNode()
        self.carriers = []
        if not (self.terminal_mode and self.sim_values is not None and self.ctx):
            return
        lay = self.ctx.lay
        flow = self.ctx.flow
        # 工艺流程可以自定义沟道形状（例如 FinFET 的沟道包在鳍的三面），否则用平面晶体管默认的。
        chans = flow.channel_fn(lay) if flow and flow.channel_fn else default_channels(lay)
        by_key: Dict[str, list] = {}
        for key, s in chans:
            # 取沟道材料的颜色（只要前 3 个 RGB 分量），不透明度设为 1；实际透明度后面另外控制。
            # [:3] 是切片，取前 3 个；元组相加 + (1.0,) 就是在末尾再接一个元素。
            col = mat("channel_" + key).color[:3] + (1.0,)
            by_key.setdefault(key, []).append((s, col))
        for key, items in by_key.items():
            node = build_solids_node("chan_" + key, items, self.cut_y, False)
            node.reparentTo(self.carrier_root)
            node.setTransparency(TransparencyAttrib.MAlpha)
            # 沟道在硅里面，正常情况下会被挡住；关闭深度测试让它“透出来”显示。
            node.setDepthOffset(12)
            node.setBin("fixed", 40)
            node.setDepthTest(False)
            self.channel_nodes[key] = node
        # 固定种子 1 的随机数生成器：每次载流子的初始分布都一样，截图结果可重复。
        rnd = random.Random(1)
        # 选择载流子所在的 y 平面：有剖面切割时放在切口后面一点，否则放在 y=3.5；最多 4.3。
        y = max(self.cut_y, 2.6) + 0.02 if self.cut_y > 0 else 3.5
        y = min(y, 4.3)
        ym = y - 0.08                  # carrier plane, just behind the cut  （载流子平面，紧贴切口后方）
        if flow and flow.carrier_ys:   # fins / nanosheets: carriers stay inside the silicon
            # 鳍式/纳米片晶体管：载流子平面要落在硅里。
            ym = _snap_to_bands(ym, flow.carrier_ys)
        # 运动路线：工艺流程可自定义，否则用默认平面器件的路线。
        if flow and flow.carrier_fn:
            paths = flow.carrier_fn(lay, ym)
        else:
            paths = default_carrier_paths(lay, ym)
        e_metal = (0.35, 1.0, 1.0, 1)      # electrons, same colour as in the NMOS  （金属里的电子，与 NMOS 中同色）
        # 各路线的颜色：电子青色，空穴（PMOS 中）橙色。
        colors = {"n": (0.35, 1.0, 1.0, 1), "p": (1.0, 0.65, 0.2, 1),
                  "gnd": e_metal, "on": e_metal, "op": e_metal, "vdd": e_metal}
        # 各路线上的载流子数量。
        counts = {"n": 18, "p": 18, "gnd": 5, "on": 6, "op": 6, "vdd": 5}
        for key, pts in paths.items():
            # 每一段折线的长度（math.dist 求两点间直线距离），以及路线总长。
            segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
            total = sum(segs)
            for i in range(counts[key]):
                np_ = self.cube.copyTo(self.carrier_root)
                # 晶体管里的载流子大一点（0.11），导线里的小一点（0.09）。
                np_.setScale(0.11 if key in ("n", "p") else 0.09)
                np_.setColor(*colors[key])
                np_.setBin("fixed", 45)
                np_.setDepthTest(False)
                np_.setTransparency(TransparencyAttrib.MAlpha)
                # 每个载流子记录为一个列表：[节点, 路线名, 在路线上的位置(0~1，随机初值), 拐点, 各段长, 总长]。
                self.carriers.append([np_, key, rnd.random(), pts, segs, total])
        self._apply_sim_alpha()

    # which device current each carrier path carries
    # 每条载流子路线对应哪个器件的电流："in" = NMOS 电流，"ip" = PMOS 电流。
    # 这是“类属性”：写在类里、方法外，所有对象共用一份。
    _PATH_CURRENT = {"n": "in", "gnd": "in", "on": "in", "p": "ip", "vdd": "ip", "op": "ip"}

    def _activity(self, key: str) -> float:
        """某条路线的“活跃度”（0~1）：电流越大越活跃，载流子跑得越快、越亮。

        电流可以从皮安到毫安跨越很多数量级，直接按比例的话小电流根本看不见，所以：
          - 若有参考电流 iref：用 sqrt(电流 / iref)，开方让差别被压缩、小电流也可见；
          - 否则用对数刻度：log10(电流) 从 -10.5（约 30 pA）到 -3（1 mA）映射到 0~1。
        """
        v = self.sim_values or {}
        # 取对应器件的电流，负值按 0 处理。dict.get(键, 默认值)：没有这个键时返回默认值。
        cur = max(v.get(self._PATH_CURRENT[key], 0.0), 0.0)
        iref = v.get("iref")
        if iref:
            return min(math.sqrt(cur / iref), 1.0)
        # 1e-16 防止对 0 取对数（数学上无意义，会报错）。
        return min(max((math.log10(max(cur, 1e-16)) + 10.5) / 7.5, 0.0), 1.0)

    def _apply_sim_alpha(self):
        """根据仿真结果设置沟道的透明度：反型程度 inv_n / inv_p（0~1）越大，沟道越明显。

        物理含义：栅压超过阈值电压越多，沟道里的载流子越多、导电性越强，所以显示得越“实”。
        """
        v = self.sim_values or {}
        for key, node in self.channel_nodes.items():
            node.setAlphaScale(0.85 * v.get("inv_" + key, 0.0))

    def set_sim(self, values: Optional[dict]):
        """更新仿真结果（例如用户拖动了输入电压滑块）。values 为 None 表示关闭仿真。"""
        # 只有“开/关”状态改变时才需要重建沟道和载流子；数值变化只需更新透明度和标签。
        # (A is None) != (B is None)：恰好一个是 None 时为 True，即开关状态发生了变化。
        rebuild = (values is None) != (self.sim_values is None)
        self.sim_values = values
        if rebuild:
            self._rebuild_channels()
        self._apply_sim_alpha()
        self.rebuild_labels()

    def _update_carriers(self, dt):
        """每帧移动载流子：根据活跃度沿各自路线前进，并调整亮度。"""
        if not self.carriers:
            return
        # 字典推导式：对每条路线算一次活跃度，{路线名: 活跃度}。
        act = {k: self._activity(k) for k in self._PATH_CURRENT}
        for c in self.carriers:
            np_, key, s, pts, segs, total = c
            a = act[key]
            # same drift speed (scene units / s) on every path, so short wires don't race
            # 所有路线上的实际速度（场景单位/秒）相同，所以要除以路线总长 total 换算成“进度增量”，
            # 否则短导线上的载流子会跑得飞快。速度随活跃度 a 增大；a=0 时完全不动。
            # % 1.0 取小数部分：走到终点（1.0）后又回到起点，循环流动。
            s = (s + dt * (0.05 + 0.6 * a) * a * 7.0 / total) % 1.0
            c[2] = s
            # 把进度换算成沿路线走过的距离 d，再找它落在哪一段折线上。
            d = s * total
            # enumerate(segs) 同时给出下标 i 和元素 L（第 i 段的长度）。
            for i, L in enumerate(segs):
                if d <= L or i == len(segs) - 1:
                    # 落在第 i 段上：按比例 t 在该段两端点间线性插值得到位置。
                    t = d / L if L else 0
                    pos = [pts[i][j] + (pts[i + 1][j] - pts[i][j]) * t for j in range(3)]
                    break
                # 还没到：减去这一段长度，继续看下一段。
                d -= L
            np_.setPos(*pos)
            # 活跃度越高越不透明（最低 0.15，保证总能隐约看到）。
            np_.setAlphaScale(0.15 + 0.85 * a)

    # ---------------------------------------------------------------- picking
    # —— 鼠标拾取：判断鼠标指着哪一层 ——
    def pick(self, origin, direction) -> List[Tuple[float, str, str]]:
        """Layers hit by a ray, front to back: [(t, layer name, material)].

        Works on the model geometry rather than the rendered triangles, so it
        matches what is drawn after the cross-section cut.  Solids that share a
        face (an implant drawn inside the substrate, say) enter at the same t;
        those are ordered by material priority, the same rule the renderer uses
        (depth offset) to decide which colour shows.

        【中文说明】从相机沿鼠标方向发一条射线（origin 起点、direction 方向），
        返回它穿过的所有层，按从近到远排序：[(距离参数 t, 层名, 材料名), ...]。
        第一个就是鼠标直接指着的材料，后面的用于显示“透过某某看到”。
        直接用模型的几何形状计算（Solid.ray_enter），而不是用画出来的三角形，所以与剖面切割后的显示一致。
        如果几块材料表面重合（例如注入区画在衬底内部）、在同一个 t 被射线进入，
        就按材料优先级排序——与画图时决定显示哪种颜色的规则相同。
        """
        if not self.wafer:
            return []
        hits = {}
        for name, layer in self.wafer.layers.items():
            m = mat(layer.material)
            # 完全透明（看不见）的材料、或者空层，跳过。
            if m.color[3] <= 0.0 or not layer.solids:
                continue
            # 这里用到了“海象运算符” :=（Python 3.8+）：在表达式中先计算并赋值给 t，再判断 t 是否为 None。
            # 整句意思：对这层每块材料求射线进入点 t，把碰到的（不为 None 的）都收集起来。
            ts = [t for s in layer.solids
                  if (t := s.ray_enter(origin, direction, self.cut_y)) is not None]
            if ts:
                # 记录这一层最近的进入点、材料优先级、材料名。
                hits[name] = (min(ts), m.priority, layer.material)
        # 排序：先按 t（保留 4 位小数，让几乎相同的 t 视为相同），t 相同时按优先级从高到低（取负号实现降序）。
        # kv 是 (层名, (t, 优先级, 材料)) 这样的键值对。
        order = sorted(hits.items(), key=lambda kv: (round(kv[1][0], 4), -kv[1][1]))
        return [(t, name, material) for name, (t, _, material) in order]

    def highlight(self, name: Optional[str]):
        """Brighten one layer.  Called every frame: layer nodes are rebuilt during
        animations, so a highlight set once would be lost.

        把指定的一层调亮（鼠标悬停时高亮显示）。每帧都要调用：因为动画期间层节点会被不断重建，
        只设置一次的高亮会随旧节点一起丢失。name 为 None 时所有层都取消高亮。
        """
        for n, node in self.layer_nodes.items():
            if n == name:
                # 颜色乘以 1.45 倍：变亮。
                node.setColorScale(1.45, 1.45, 1.45, 1)
            elif node.hasColorScale():
                node.clearColorScale()

    # ---------------------------------------------------------------- options
    # —— 显示选项（由界面上的开关/滑块调用）——
    def set_cut(self, y: float):
        """设置剖面切割位置 y，并重建模型。"""
        self.cut_y = y
        if self.wafer:
            self.rebuild_all()

    def set_edges(self, on: bool):
        """开/关棱线显示，并重建模型。"""
        self.edges = on
        if self.wafer:
            self.rebuild_all()

    def set_labels(self, on: bool):
        """开/关文字标注。"""
        self.show_labels = on
        self.rebuild_labels()
