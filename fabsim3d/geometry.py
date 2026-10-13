"""Pure-python solid geometry for the layered wafer model.

Every solid is a convex polygon in the x-z plane (cross-section) extruded along
y.  Boxes are just 4-vertex polygons.  This keeps the cross-section view (cut
along y) trivially correct: clipping a solid at y=c only changes y0/y1.

Coordinates (display units, roughly microns laterally, exaggerated vertically):
    x : 0 .. 20   (NMOS left, PMOS right)
    y : 0 .. 8    (device width direction; the cut plane moves along y)
    z : up; silicon surface at z = 0

【这个文件是做什么的】（中文说明）
芯片制造的过程，在 3D 模型里就是：在硅片上一层一层地“长”材料（氧化层、多晶硅、金属……），
或者把某些区域“刻掉”。本文件提供描述这些材料块形状的纯数学工具，不涉及画图。
画图（把形状变成屏幕上的 3D 模型）由 scene.py 负责；决定每一步加什么、删什么由工艺流程文件负责。

【怎么表示一块材料】
每一块材料（Solid，“实体”）都是这样构造的：先在 x-z 平面（横向 x、竖直 z 的“侧视截面”）里画一个
凸多边形，然后把它沿 y 方向“拉伸”成一段柱体，从 y0 拉到 y1。像挤牙膏：管口形状就是那个多边形。
  - 最常见的长方体，就是 4 个顶点的矩形截面；
  - 斜面（例如 LOCOS 氧化层的“鸟嘴”边缘、侧墙）就是梯形等其它凸多边形。
这样设计的好处：做“剖面切割”（沿某个 y 值切开模型）时，只要改 y0/y1 就行，截面形状不用重新计算。

“凸多边形”：任意两点连线都完全在图形内部、没有凹进去的角的多边形（矩形、梯形、三角形都是）。

【坐标系】（显示单位，横向大约是微米，竖直方向故意放大以便看清薄膜）
    x：0 到 20，左边是 NMOS 晶体管，右边是 PMOS 晶体管；
    y：0 到 8，晶体管的“宽度”方向，剖面切割的切面就沿 y 移动；
    z：竖直向上，硅片原始表面在 z = 0。
"""
# 让类型提示（例如 "float | None"）在旧版本 Python 里也能正常使用的固定写法。
from __future__ import annotations

# dataclass：一个“装饰器”工具，能根据类里写的字段自动生成构造函数等样板代码（下面会解释）。
from dataclasses import dataclass, field
# typing 里是一些“类型提示”的名字，只用来帮助读代码的人理解数据类型，不影响程序运行。
#   List[X] = 由 X 组成的列表；Tuple[...] = 元组（固定长度的一组值）；
#   Iterable / Sequence = “可以逐个取出元素的东西” / “有顺序、可按下标取的东西”。
from typing import Iterable, List, Sequence, Tuple

# Rect 是给“矩形”起的别名：一个 4 个小数组成的元组 (x0, x1, y0, y1)，
# 表示俯视图（x-y 平面）里一个与坐标轴对齐的矩形：x 从 x0 到 x1，y 从 y0 到 y1。
Rect = Tuple[float, float, float, float]   # x0, x1, y0, y1
# EPS（epsilon）= 一个极小的数 0.000001。计算机里小数有微小误差（例如 0.1+0.2 不严格等于 0.3），
# 所以比较两个小数“是否相等/是否在边界上”时，允许相差不超过 EPS，避免因误差判断错。
EPS = 1e-6


# @dataclass 是“装饰器”（以 @ 开头，写在类或函数上方，用来给它附加功能）。
# 这里它会根据下面列出的字段（poly、y0、y1、anchor）自动生成构造函数，
# 于是可以直接写 Solid(多边形, y0, y1) 来创建对象。
# eq=False 表示不要自动生成“按内容比较相等”的功能：两个形状完全相同的块仍被当作两个不同的对象。
@dataclass(eq=False)
class Solid:
    """一块材料（实体）：x-z 平面里的凸多边形，沿 y 方向从 y0 拉伸到 y1。

    为什么需要：整个芯片 3D 模型就是很多个 Solid 叠在一起。工艺步骤（淀积、刻蚀、氧化）
    都是在增加、删除或修改 Solid；scene.py 再把每个 Solid 画成 3D 网格。
    """
    # 截面多边形的顶点列表，每个顶点是 (x, z)。按逆时针（CCW）顺序排列，且必须是凸多边形。
    poly: List[Tuple[float, float]]       # CCW (x, z) vertices, convex
    # 沿 y 方向的起点和终点。
    y0: float
    y1: float
    # “生长动画”的基准高度：动画时材料从这个 z 高度开始向上（或向下）逐渐长出来。
    # = None 表示默认没有，创建时可以不填。
    anchor: float | None = None           # z anchor used by grow animations

    # @staticmethod：“静态方法”，不需要先有某个具体的 Solid 对象就能调用，写法是 Solid.box(...)。
    @staticmethod
    def box(x0, x1, y0, y1, z0, z1) -> "Solid":
        """快捷创建一个长方体：x 从 x0 到 x1，y 从 y0 到 y1，z 从 z0 到 z1。

        长方体是最常用的形状（例如一层平整的薄膜），所以单独提供这个便利函数。
        """
        # 截面是一个矩形，四个顶点按逆时针排列：左下 -> 右下 -> 右上 -> 左上。
        return Solid([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], y0, y1)

    # @property：把一个方法变成“属性”，使用时不用加括号，写 s.is_box 而不是 s.is_box()。
    @property
    def is_box(self) -> bool:
        """判断这个实体是不是长方体（截面是与坐标轴对齐的矩形）。

        为什么需要：有些操作（如按俯视区域切开 split_box）只对长方体成立，要先检查。
        """
        # 不是 4 个顶点，肯定不是矩形。
        if len(self.poly) != 4:
            return False
        # {... for p in ...} 是“集合推导式”：把每个顶点的 x 坐标取出来放进一个“集合”，
        # 集合会自动去掉重复值。round(…, 9) 保留 9 位小数，消除微小误差。
        xs = {round(p[0], 9) for p in self.poly}
        zs = {round(p[1], 9) for p in self.poly}
        # 与坐标轴对齐的矩形，4 个顶点恰好只有 2 种不同的 x 值和 2 种不同的 z 值。
        return len(xs) == 2 and len(zs) == 2

    # 下面四个属性分别求截面多边形最左、最右、最低、最高的坐标。
    # self 指“当前这个对象本身”；p[0] 是顶点的 x，p[1] 是顶点的 z。
    @property
    def xmin(self):
        return min(p[0] for p in self.poly)

    @property
    def xmax(self):
        return max(p[0] for p in self.poly)

    @property
    def zmin(self):
        return min(p[1] for p in self.poly)

    @property
    def zmax(self):
        return max(p[1] for p in self.poly)

    @property
    def footprint(self) -> Rect:
        """俯视时占据的矩形区域（“占地面积”）：(xmin, xmax, y0, y1)。"""
        return (self.xmin, self.xmax, self.y0, self.y1)

    def top_at(self, x: float) -> float | None:
        """Highest z of the polygon at abscissa x (None if outside).

        在横坐标 x 处，这块材料的“顶面高度”（最大 z）。x 不在材料范围内则返回 None。
        为什么需要：淀积新薄膜时要知道“下面的表面有多高”，新薄膜才能正好铺在上面。
        方法：在 x 处画一条竖线，看它与多边形每条边的交点，取其中最高的那个。
        """
        # x 在多边形左右范围之外：竖线碰不到这块材料。
        if x < self.xmin - EPS or x > self.xmax + EPS:
            return None
        best = None
        n = len(self.poly)
        # 逐条检查多边形的边。第 i 条边连接顶点 i 和顶点 i+1。
        # (i + 1) % n：% 是“取余数”，最后一个顶点的下一个会绕回第 0 个，让多边形首尾相连。
        for i in range(n):
            (xa, za), (xb, zb) = self.poly[i], self.poly[(i + 1) % n]
            # 这条边覆盖的 x 范围；x 不在其中，这条边与竖线不相交，跳过（continue = 直接进入下一轮）。
            lo, hi = min(xa, xb), max(xa, xb)
            if x < lo - EPS or x > hi + EPS:
                continue
            if abs(xb - xa) < EPS:
                # 竖直的边（两端 x 相同）：竖线与它重合，取这条边较高的端点。
                z = max(za, zb)
            else:
                # 普通斜边：用“线性插值”求 x 处的高度。
                # (x - xa) / (xb - xa) 是 x 在这条边上走过的比例（0 到 1），
                # 起点高度加上“比例 × 总高度差”就是该点高度。
                z = za + (zb - za) * (x - xa) / (xb - xa)
            # 记录目前为止最高的交点。
            best = z if best is None else max(best, z)
        return best

    def contains_xy(self, x: float, y: float) -> bool:
        """俯视时，点 (x, y) 是否落在这块材料的占地范围内。"""
        # Python 支持连写比较：a <= x <= b 表示 x 在 a 和 b 之间。
        return self.xmin - EPS <= x <= self.xmax + EPS and self.y0 - EPS <= y <= self.y1 + EPS

    def ray_enter(self, o, d, y_min: float = -1e9) -> float | None:
        """Ray parameter t >= 0 where o + t*d enters this prism (the part with
        y >= y_min, i.e. what the cross-section shows), or None if it misses.

        Cyrus-Beck clipping: the prism is the intersection of the y slab and one
        half-plane per polygon edge, so the hit interval is [max enter, min exit].

        【中文说明】射线与棱柱求交：求从相机射出的一条“光线”第一次碰到这块材料的位置。
        为什么需要：鼠标悬停在 3D 画面上时，要知道鼠标指着的是哪种材料（显示材料名）。
        做法是从相机沿鼠标方向发出一条射线，看它先撞到哪块材料。

        - 射线：从起点 o 出发，沿方向 d 无限延伸的直线。射线上的点写成 o + t*d，
          t 是“走了多远”的参数，t = 0 在起点，t 越大越远。o 和 d 都是 (x, y, z) 三个数。
        - 棱柱：就是本 Solid（多边形沿 y 拉伸成的柱体）。
        - y_min：剖面切割时，y < y_min 的部分被“切掉”不显示，所以只考虑 y >= y_min 的部分。
        - 返回值：射线进入棱柱时的 t；没碰到返回 None。

        Cyrus-Beck 算法思路：凸的棱柱可以看成若干“半空间”的交集——
          · y 方向的“夹层”：ya <= y <= yb；
          · 多边形每条边都把平面分成“内侧”和“外侧”两半，棱柱必须在每条边的内侧。
        射线在每个半空间里的那一段都是一个 t 区间 [进入, 离开]。所有区间的交集
        = [所有“进入”的最大值, 所有“离开”的最小值]。若这个区间为空（进入 > 离开），说明没碰到。
        """
        # t0 = 目前的进入时刻，t1 = 目前的离开时刻。一开始是从 0 到无穷大（float("inf")）。
        t0, t1 = 0.0, float("inf")
        # y 方向的有效范围（考虑剖面切割后的下限）。
        ya, yb = max(self.y0, y_min), self.y1
        # 切完后几乎没剩下厚度：看不见，当作没碰到。
        if yb - ya <= 1e-4:
            return None
        # —— 第 1 步：y 方向的“夹层” ——
        if abs(d[1]) < 1e-12:
            # 射线方向几乎不沿 y 变化（与夹层平行）：起点的 y 在夹层内就一直在内，否则永远碰不到。
            if not ya <= o[1] <= yb:
                return None
        else:
            # 解方程 o_y + t*d_y = ya 和 = yb，得到射线穿过两个 y 边界面的 t 值。
            ta, tb = (ya - o[1]) / d[1], (yb - o[1]) / d[1]
            # 两者中较小的是进入夹层，较大的是离开夹层；与现有区间取交集。
            t0, t1 = max(t0, min(ta, tb)), min(t1, max(ta, tb))
        poly = self.poly
        n = len(poly)
        # —— 第 2 步：判断多边形顶点的绕向 ——
        # “鞋带公式”求多边形面积的 2 倍：逆时针排列时结果为正，顺时针为负。
        # sum(... for i in range(n)) 把每条边算出的值加起来。
        area2 = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
                    for i in range(n))
        # sgn 记录绕向（+1 或 -1），后面用它统一“哪一侧算内侧”，这样即使顶点顺序反了也能算对。
        sgn = 1.0 if area2 >= 0 else -1.0
        # —— 第 3 步：多边形的每条边（在 x-z 平面里是一条直线，拉伸后是棱柱的一个侧面） ——
        for i in range(n):
            (xa, za), (xb, zb) = poly[i], poly[(i + 1) % n]
            # 边的方向向量 e = (ex, ez)：从顶点 a 指向顶点 b。
            ex, ez = xb - xa, zb - za
            # inside  <=>  sgn * (e x (p - a)) >= 0, linear in t along the ray
            # 用“二维叉积” e × (p - a) 判断点 p 在边的哪一侧：
            # 对逆时针多边形，内部的点都在每条边的左侧，叉积 >= 0。
            # 把 p = o + t*d 代入，叉积 = f0 + t*fd，是 t 的一次函数：
            #   f0 = 射线起点处的值，fd = 每走单位 t 变化多少。
            # 注意只用到 x（下标 0）和 z（下标 2），因为侧面与 y 无关。
            f0 = sgn * (ex * (o[2] - za) - ez * (o[0] - xa))
            fd = sgn * (ex * d[2] - ez * d[0])
            if abs(fd) < 1e-12:
                # 射线与这个侧面平行：起点在外侧就永远进不去；在内侧则这条边不构成限制。
                if f0 < 0:
                    return None
                continue
            # 解 f0 + t*fd = 0，得到射线穿过这个侧面的 t。
            t = -f0 / fd
            if fd > 0:
                # 越走越往“内侧”：这是一个“进入”点，进入时刻取最大值。
                t0 = max(t0, t)
            else:
                # 越走越往“外侧”：这是一个“离开”点，离开时刻取最小值。
                t1 = min(t1, t)
            # 区间已经为空：射线从棱柱旁边擦过，没有碰到。
            if t0 > t1:
                return None
        # 所有限制都满足：t0 就是射线进入这块材料的位置。
        return t0

    def scaled_z(self, anchor: float, s: float) -> "Solid":
        """以高度 anchor 为基准，把实体在竖直方向缩放 s 倍，返回一个新实体。

        为什么需要：做“生长动画”。例如氧化层从 0 慢慢长到完整厚度时，s 从 0 逐渐变到 1，
        每一帧都以表面（anchor）为底，把材料压扁到 s 倍高度来画。
        """
        # 列表推导式：[新元素 for 变量 in 列表] 一次性生成一个新列表。
        # 每个顶点的 x 不变，z 到基准面的距离乘以 s。
        poly = [(x, anchor + (z - anchor) * s) for x, z in self.poly]
        return Solid(poly, self.y0, self.y1, self.anchor)

    def with_box_footprint(self, r: Rect) -> "Solid":
        """Box solid restricted to footprint r (only valid for boxes).

        保持高度（zmin 到 zmax）不变，把占地范围换成矩形 r，得到一个新的长方体。只适用于长方体。
        为什么需要：刻蚀时要把一块长方体按掩膜图形切成几小块，每块高度相同、占地不同。
        """
        return Solid.box(r[0], r[1], r[2], r[3], self.zmin, self.zmax)


# --------------------------------------------------------------------------
# Rectangle algebra (axis aligned, in the x-y plane)
# 矩形运算（俯视 x-y 平面里、与坐标轴对齐的矩形）
# 光刻掩膜的图形、各块材料的占地范围都是这种矩形，所以需要求面积、求交集、求“剩余部分”等运算。
# --------------------------------------------------------------------------

def rect_area(r: Rect) -> float:
    """矩形面积 = 宽 × 高。宽或高为负（无效矩形）时按 0 计算。"""
    return max(0.0, r[1] - r[0]) * max(0.0, r[3] - r[2])


def rect_intersect(a: Rect, b: Rect) -> Rect | None:
    """两个矩形的重叠部分；不重叠（或只碰到边）则返回 None。

    例如：判断某块材料是否落在掩膜开口里，就要求它们的交集。
    """
    # 重叠区域的左边界取两者左边界中较大的，右边界取较小的；y 方向同理。
    r = (max(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]))
    # 宽或高 <= 0，说明根本没重叠。
    if r[1] - r[0] <= EPS or r[3] - r[2] <= EPS:
        return None
    return r


def _breaks(vals: Iterable[float]) -> List[float]:
    """把一串数字排序并去掉“几乎相等”的重复值，得到一组分割点。

    为什么需要：网格切分时，许多矩形的边可能落在同一位置（或只差极小误差），只保留一个。
    """
    # “out: List[float] = []” 是带类型提示的赋值：out 是一个空的小数列表。
    out: List[float] = []
    for v in sorted(vals):
        # out[-1] 表示列表最后一个元素。只有当 v 与上一个保留的值相差超过 EPS 时才加入。
        if not out or v - out[-1] > EPS:
            out.append(v)
    return out


def _inside_any(x: float, y: float, rects: Sequence[Rect]) -> bool:
    """点 (x, y) 是否落在给定的任意一个矩形之内。"""
    # any(...)：只要其中有一个为 True 就返回 True。
    return any(r[0] - EPS <= x <= r[1] + EPS and r[2] - EPS <= y <= r[3] + EPS for r in rects)


def grid_cells(domain: Rect, rects: Sequence[Rect], extra_x=(), extra_y=()):
    """Split domain at every rect edge; yields cells (x0,x1,y0,y1).

    把区域 domain 沿所有矩形的边切成一个个小格子（像棋盘），逐个产出每个小格子。
    为什么需要：切完之后，每个小格子要么完全在某个矩形内，要么完全在外，不会“一半在内一半在外”。
    这样只需检查格子中心点，就能判断整个格子属于哪里，把复杂的图形运算变成简单的逐格判断。
    extra_x / extra_y：额外指定的切分位置（例如下面材料的边缘，以便新薄膜跟着台阶起伏）。
    """
    # 收集所有 x 方向的切分位置：区域左右边界、额外位置、以及每个矩形落在区域内的左右边。
    # [v for r in rects for v in (r[0], r[1]) if ...] 是双层列表推导式：
    #   对每个矩形 r，再对它的左边和右边 v，满足条件就收集起来。
    # 列表前的 * 号把它展开，合并进外层列表。
    xs = _breaks([domain[0], domain[1], *extra_x,
                  *[v for r in rects for v in (r[0], r[1]) if domain[0] < v < domain[1]]])
    # y 方向同理。
    ys = _breaks([domain[2], domain[3], *extra_y,
                  *[v for r in rects for v in (r[2], r[3]) if domain[2] < v < domain[3]]])
    # 丢掉落在区域外面的切分位置（extra_x/extra_y 可能超出区域）。
    xs = [x for x in xs if domain[0] - EPS <= x <= domain[1] + EPS]
    ys = [y for y in ys if domain[2] - EPS <= y <= domain[3] + EPS]
    # 相邻两个切分位置之间就是一个格子。
    # yield：把一个结果“交出去”但函数不结束，下次再要时从这里继续。
    # 这种函数叫“生成器”，可以用 for 循环逐个取出格子，不必一次性把所有格子存进内存。
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            yield (xs[i], xs[i + 1], ys[j], ys[j + 1])


def merge_cells(cells: List[Tuple[Rect, tuple]]) -> List[Tuple[Rect, tuple]]:
    """Merge neighbouring cells with identical payload (row-wise then column-wise).

    把相邻且“附带信息”(payload) 相同的小格子合并成大矩形。
    为什么需要：grid_cells 会切出很多碎格子，如果每个都变成一个 3D 方块，模型会很碎、很慢。
    合并后块数大大减少。payload 是每个格子附带的数据（例如这一格薄膜的底和顶高度），
    只有 payload 完全一样的格子才能合并。
    先在每一行内左右合并，再把 x 范围相同的块上下合并。
    """
    # row merge (along x)
    # —— 第 1 步：按行（相同 y0、y1）分组，然后在每行里沿 x 方向合并 ——
    # rows 是字典：键 = (y0, y1)，值 = 这一行所有格子的列表。
    rows: dict = {}
    for r, payload in cells:
        # setdefault(键, [])：如果键不存在就先放一个空列表，然后返回这个列表，接着 append 加入格子。
        rows.setdefault((round(r[2], 9), round(r[3], 9)), []).append((r, payload))
    merged = []
    for key in sorted(rows):
        # 这一行的格子按左边界 x0 从左到右排序。
        # lambda c: c[0][0] 是“匿名小函数”：输入 c，返回 c[0][0]（格子矩形的 x0），作为排序依据。
        row = sorted(rows[key], key=lambda c: c[0][0])
        # cur：当前正在“延长”的合并块。
        cur = None
        for r, pl in row:
            # 当前块的右边正好接上这一格的左边，而且 payload 相同：把当前块向右延长。
            if cur and abs(cur[0][1] - r[0]) < EPS and cur[1] == pl:
                cur = ((cur[0][0], r[1], cur[0][2], cur[0][3]), pl)
            else:
                # 接不上：把之前的块存起来，从这一格开始新的块。
                if cur:
                    merged.append(cur)
                cur = (r, pl)
        # 每行最后一个块也别忘了存。
        if cur:
            merged.append(cur)
    # column merge (along y) for identical x-spans
    # —— 第 2 步：x 范围相同且 payload 相同的块，沿 y 方向上下合并 ——
    cols: dict = {}
    for r, pl in merged:
        cols.setdefault((round(r[0], 9), round(r[1], 9), pl), []).append(r)
    out = []
    # .items() 同时取出字典的键和值；这里键本身是三元组，直接拆成 x0、x1、pl。
    for (x0, x1, pl), rs in cols.items():
        # 按 y0 从小到大排序。
        rs.sort(key=lambda r: r[2])
        cur = None
        for r in rs:
            # 当前块的上边 y1 正好接上这一块的下边 y0：向上延长。
            if cur and abs(cur[3] - r[2]) < EPS:
                cur = (cur[0], cur[1], cur[2], r[3])
            else:
                if cur:
                    out.append((cur, pl))
                cur = r
        if cur:
            out.append((cur, pl))
    return out


def rect_complement(domain: Rect, holes: Sequence[Rect]) -> List[Rect]:
    """区域 domain 去掉所有 holes（“洞”）之后剩下的部分，用若干矩形表示。

    为什么需要：例如掩膜只给出“开口”的位置，而我们需要知道“被遮住”的区域，就是求补集。
    """
    cells = []
    # 切成格子，检查每个格子的中心点：不在任何洞里，就属于剩余部分。
    for c in grid_cells(domain, holes):
        cx, cy = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2
        if not _inside_any(cx, cy, holes):
            # payload 用空元组 ()，表示所有格子都一样，可以随意合并。
            cells.append((c, ()))
    # 合并后只要矩形本身，丢掉 payload（_ 表示“这个值不需要”）。
    return [r for r, _ in merge_cells(cells)]


def split_box(solid: Solid, keep: Sequence[Rect]) -> Tuple[List[Solid], List[Solid]]:
    """Split a box solid by footprint: (parts inside keep, parts outside).

    按俯视区域把一块长方体材料切开，返回两组：(落在 keep 区域内的部分, 在外面的部分)。
    为什么需要：这正是“光刻 + 刻蚀”的效果。光刻胶保护的区域（keep）留下来，
    没被保护的部分被刻蚀掉（removed）。动画里被刻掉的部分可以单独做消失效果。
    """
    fp = solid.footprint
    kept, removed = [], []
    for c in grid_cells(fp, keep):
        cx, cy = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2
        # 一行内用条件表达式选出要放进的列表：中心在 keep 内就放进 kept，否则放进 removed。
        (kept if _inside_any(cx, cy, keep) else removed).append((c, ()))
    # 把两组格子分别合并成大矩形，再变回保持原高度的长方体。
    return ([solid.with_box_footprint(r) for r, _ in merge_cells(kept)],
            [solid.with_box_footprint(r) for r, _ in merge_cells(removed)])


def surface_height(solids: Iterable[Solid], x: float, y: float, floor: float = 0.0) -> float:
    """在俯视位置 (x, y) 处，所有材料中最高的顶面高度；那里什么都没有就返回 floor（默认 0，硅表面）。

    为什么需要：新淀积的薄膜要铺在“当前最上面的表面”上，所以要先知道每个位置表面有多高。
    """
    h = None
    for s in solids:
        # 只看在 y 方向覆盖这个点的材料。
        if s.y0 - EPS <= y <= s.y1 + EPS:
            t = s.top_at(x)
            # 记录最高的顶面。
            if t is not None and (h is None or t > h):
                h = t
    return floor if h is None else h


def conformal_cells(solids: List[Solid], region: Sequence[Rect], domain: Rect,
                    thickness: float | None = None, top: float | None = None,
                    min_top_gap: float = 0.0) -> List[Solid]:
    """Boxes that sit on the current topography inside `region`.

    Either a constant `thickness` (conformal film) or a fixed `top` (planarised
    film).  With `top`, cells whose surface is higher than top get
    `min_top_gap` thickness instead.

    【中文说明】在 region 区域内，生成一层“铺在当前表面起伏上”的新薄膜（由若干长方体组成）。
    为什么需要：模拟“淀积”工艺。真实芯片表面高低不平（有台阶），新薄膜会顺着台阶铺上去。
    两种模式：
      - thickness（厚度固定）：“共形”薄膜，处处一样厚，表面跟着下面的台阶起伏
        （例如化学气相淀积 CVD 的氮化硅、多晶硅）；
      - top（顶面固定）：“平坦化”薄膜，不管下面多高，顶面都在同一高度 top
        （例如淀积后再经过化学机械抛光 CMP 磨平的介质层）。
        如果某处下面已经比 top 还高，就只在上面加 min_top_gap 那么薄的一层。
    """
    # 收集已有材料的所有顶点 x 位置和 y 边界，作为额外切分位置。
    # 这样切出的每个格子下面的表面高度基本一致，新薄膜才能准确贴合台阶。
    # += 把另一个列表的元素追加到当前列表末尾。
    xs_extra, ys_extra = [], []
    for s in solids:
        xs_extra += [p[0] for p in s.poly]
        ys_extra += [s.y0, s.y1]
    cells = []
    for c in grid_cells(domain, list(region), xs_extra, ys_extra):
        # 格子中心不在要淀积的区域内：跳过。
        cx, cy = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2
        if not _inside_any(cx, cy, region):
            continue
        # 新薄膜的底面 = 这里当前的表面高度。
        z0 = surface_height(solids, cx, cy)
        # 新薄膜的顶面：固定厚度模式下 = 底面 + 厚度；平坦化模式下 = top（但至少比底面高 min_top_gap）。
        z1 = z0 + thickness if thickness is not None else max(top, z0 + min_top_gap)
        # 把 (底, 顶) 作为 payload，只有底和顶都相同的相邻格子才会被合并成一块。
        cells.append((c, (round(z0, 6), round(z1, 6))))
    out = []
    for r, (z0, z1) in merge_cells(cells):
        s = Solid.box(r[0], r[1], r[2], r[3], z0, z1)
        # 生长动画以底面为基准，从下往上长出来。
        s.anchor = z0
        out.append(s)
    return out
