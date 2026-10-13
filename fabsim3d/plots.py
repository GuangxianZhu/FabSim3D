"""Matplotlib (Agg) charts rendered into Panda3D textures.

【中文说明：这个文件是干什么的？】
这个文件负责画“电学特性曲线图”——也就是做好的晶体管/反相器到底表现如何。
它用 Matplotlib（Python 最常用的画图库）在内存里画出图表，
再把图片转成像素数组，交给 Panda3D（3D 引擎）当作“贴图”显示在界面上。

这里一共有 5 种图（都在 PlotRenderer 类里）：
  idvg —— 转移特性：栅极电压 Vgs 和电流 Id 的关系（晶体管怎么被“打开”）
  idvd —— 输出特性：漏极电压 Vds 和电流 Id 的关系（打开后能流多大电流）
  vtc  —— 反相器电压传输特性：输入电压 Vin 和输出电压 Vout 的关系
  tran —— 瞬态响应：输入突然翻转时，输出随时间怎么变（反映电路速度）
  vtl  —— 阈值电压随栅长的变化（短沟道效应）

很多图都支持 ref 参数：把“修改参数之前”的曲线用灰色画出来，方便对比前后变化。
"""
from __future__ import annotations

# numpy：做数值计算的库，这里主要用来生成一串均匀分布的电压值、处理图片像素数组。
import numpy as np
import matplotlib

# 选择 "Agg" 后端：只在内存里画图、不弹出窗口。必须在导入下面这些 matplotlib 模块之前设置，
# 所以后面的 import 行末尾都有 "# noqa: E402"（告诉代码检查工具“导入不在文件开头是故意的”）。
matplotlib.use("Agg")
from matplotlib import font_manager  # noqa: E402            （字体管理：用来加载中文字体）
from matplotlib.figure import Figure  # noqa: E402           （Figure：一整张图的“画布”）
# 坐标轴刻度工具：FixedLocator=固定在指定位置画刻度，FuncFormatter=用函数决定刻度文字，
# NullLocator=不画（次要）刻度
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402
# FigureCanvasAgg：把 Figure 真正“渲染”成像素的工具
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

# i18n：中英文切换（i18n.pick("中文", "English") 会按当前界面语言选一个）
from . import i18n  # noqa: E402
# summarize_cached：带缓存的电学计算（见 process_core.py）
from .process_core import summarize_cached  # noqa: E402
# 器件模型：nmos/pmos 创建晶体管模型，inverter_vout 算反相器输出电压，
# vt_vs_length 算阈值电压随栅长变化的曲线
from .device_model import ProcessParams, nmos, pmos, inverter_vout, vt_vs_length  # noqa: E402

# dark-surface palette (validated categorical slots 1/2 + text tokens)
# 深色背景的配色方案（颜色用“#红绿蓝”十六进制写法）：
SURFACE = "#1a1a19"     # 背景色（深灰近黑）
TEXT = "#ffffff"        # 主要文字（白）
TEXT2 = "#c3c2b7"       # 次要文字（浅灰：坐标轴标签、刻度等）
GRID = "#383835"        # 网格线
C_N = "#3987e5"     # NMOS / series 1（NMOS 用蓝色）
C_P = "#d95926"     # PMOS / series 2（PMOS 用橙色）
C_MUTED = "#8a8980"     # 辅助线（参考线、零线）
C_I = "#3fa66b"     # inverter supply current（反相器电源电流用绿色）
C_REF = "#6f6e68"      # grey "before" reference curves（灰色的“操作前”对比曲线）


def setup_fonts(path: str | None):
    """设置图表字体：如果给了字体文件路径（通常是中文字体），就加载它。

    Matplotlib 默认字体不含中文，中文会显示成方框，所以需要额外加载。
    【语法】str | None 表示“参数可以是字符串，也可以是 None（空）”。
    """
    if path:
        # try/except：尝试执行；如果出错（比如字体文件坏了），就跳到 except，不让程序崩溃。
        try:
            font_manager.fontManager.addfont(path)                      # 注册字体文件
            name = font_manager.FontProperties(fname=path).get_name()   # 读出字体名字
            # 设为默认无衬线字体；中文字体找不到某个字时，退回到 DejaVu Sans。
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
        except Exception:
            pass          # 加载失败就算了，继续用默认字体
    # 负号用普通的 "-"，避免某些中文字体里没有数学负号“−”而显示成方框。
    matplotlib.rcParams["axes.unicode_minus"] = False


class PlotRenderer:
    """图表渲染器：持有一张可反复使用的画布，每次调用画一种图，返回像素数组。

    复用同一张画布（而不是每次新建）可以节省时间，因为界面会频繁刷新图表。
    """

    def __init__(self, w_px=520, h_px=400, dpi=100):
        # 图片大小：宽 w_px、高 h_px 像素；dpi=每英寸多少像素。
        # Matplotlib 用“英寸”表示尺寸，所以 figsize = 像素 / dpi。
        self.w, self.h, self.dpi = w_px, h_px, dpi
        self.fig = Figure(figsize=(w_px / dpi, h_px / dpi), dpi=dpi, facecolor=SURFACE)
        self.canvas = FigureCanvasAgg(self.fig)

    def _ax(self, title: str, xlabel: str, ylabel: str):
        """清空画布，新建一组坐标轴（ax），并统一设置深色风格、标题和坐标轴名称。

        每种图开头都调用它，保证所有图表外观一致。
        """
        self.fig.clear()
        # add_subplot(111)：“1 行 1 列中的第 1 个”，也就是整张图只有一个坐标区。
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(SURFACE)
        # 隐藏上边框和右边框，只留左边和下边（更简洁的现代风格）。
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        # 刻度颜色/字号、网格线，网格画在曲线下面（set_axisbelow）。
        ax.tick_params(colors=TEXT2, labelsize=11, length=3)
        ax.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        # 标题靠左；x、y 轴的名称。
        ax.set_title(title, color=TEXT, fontsize=13, loc="left", pad=8)
        ax.set_xlabel(xlabel, color=TEXT2, fontsize=11.5)
        ax.set_ylabel(ylabel, color=TEXT2, fontsize=11.5)
        return ax

    def _legend(self, ax, loc="best"):
        """画图例（说明每条曲线代表什么的小方框），使用统一的深色样式。"""
        leg = ax.legend(loc=loc, fontsize=10, frameon=True, facecolor=SURFACE, edgecolor=GRID,
                        labelcolor=TEXT2)
        return leg

    # 【语法】@staticmethod：静态方法，不需要 self（不用访问对象自身的数据）。
    @staticmethod
    def _ref_label():
        """灰色对比曲线在图例里的名字：“操作前”/“before”。"""
        return i18n.pick("操作前", "before")

    def _finish(self) -> np.ndarray:
        """完成绘图：自动排版、渲染成像素，返回 RGBA（红绿蓝+透明度）像素数组。"""
        self.fig.tight_layout(pad=0.6)     # 自动调整边距，防止文字被裁掉
        self.canvas.draw()                 # 真正把图画出来
        buf = np.asarray(self.canvas.buffer_rgba())
        # buf[::-1] 把图片上下翻转（[::-1] 是“倒序”切片）。
        # 因为 Panda3D 贴图从最底下一行开始存，而 Matplotlib 从最上面一行开始。
        # ascontiguousarray 让数据在内存里连续存放，Panda3D 才能直接读取。
        return np.ascontiguousarray(buf[::-1])     # Panda textures start at bottom row

    # ------------------------------------------------------------------ charts
    # 下面是 5 种图表。共同参数：
    #   p   —— 当前工艺参数（ProcessParams）
    #   vin —— 反相器当前的输入电压（用来在图上标出“工作点”）
    #   f   —— 启用的物理特性集合（features）
    #   ref —— 可选的 (旧参数, 旧特性)，用来画灰色“操作前”曲线
    def idvg(self, p: ProcessParams, vin: float, f=frozenset(), ref=None):
        """转移特性图：横轴 |Vgs|（栅极-源极电压，单位伏），纵轴 |Id|（漏极电流，单位安培）。

        物理意义：栅极电压就像水龙头的把手，电流就是水流。
        当 Vgs 低于阈值电压 Vt 时，晶体管“关断”，只有极小的漏电流（亚阈值区）；
        超过 Vt 后电流迅速增大，晶体管“打开”。
        纵轴用对数刻度，这样既能看到 1e-14 A 的微小漏电，也能看到毫安级的大电流。
        NMOS 和 PMOS 都画成绝对值，方便放在一起比较。
        """
        mn, mp = nmos(p, f), pmos(p, f)          # 根据工艺参数建立两个晶体管模型
        # np.linspace(0, VDD, 200)：从 0 到电源电压均匀取 200 个点，作为横轴电压。
        v = np.linspace(0, p.vdd, 200)
        ax = self._ax(i18n.pick("转移特性 |Id|-|Vgs|  (|Vds| = VDD)", "Transfer |Id| vs |Vgs|  (|Vds| = VDD)"),
                      "|Vgs| (V)", "|Id| (A)")
        # 漏极电压固定为 VDD，计算每个栅压下的电流。
        idn = mn.ids(v, p.vdd)
        idp = mp.ids(v, p.vdd)
        # 有对比数据时，先画灰色的“操作前”曲线（实线 NMOS，虚线 PMOS）。
        if ref:
            rp, rf = ref
            rv = np.linspace(0, rp.vdd, 200)
            # semilogy：纵轴为对数刻度的折线图。
            ax.semilogy(rv, nmos(rp, rf).ids(rv, rp.vdd), color=C_REF, lw=1.6, label=self._ref_label())
            ax.semilogy(rv, pmos(rp, rf).ids(rv, rp.vdd), color=C_REF, lw=1.6, ls="--")
        # 当前曲线：NMOS 蓝色实线，PMOS 橙色虚线；图例里显示各自的阈值电压。
        ax.semilogy(v, idn, color=C_N, lw=2, label=f"NMOS  Vtn={mn.vt:.2f} V")
        ax.semilogy(v, idp, color=C_P, lw=2, ls="--", label=f"PMOS  |Vtp|={mp.vt_mag:.2f} V")
        # 在阈值电压处画竖直的点线，标出“开关点”。
        for vt, c in ((mn.vt_mag, C_N), (mp.vt_mag, C_P)):
            ax.axvline(vt, color=c, lw=1, ls=":")
        # 圆点标出当前输入电压下两个管子的工作点。
        # 对 NMOS，|Vgs| = Vin；对 PMOS（源极接 VDD），|Vgs| = VDD - Vin。
        ax.plot([vin], [mn.ids(vin, p.vdd)], "o", ms=8, color=C_N, mec=SURFACE, mew=2)
        ax.plot([p.vdd - vin], [mp.ids(p.vdd - vin, p.vdd)], "o", ms=8, color=C_P, mec=SURFACE, mew=2)
        # 纵轴下限 1e-14 A，上限比最大电流再高 3 倍留点空白。
        ax.set_ylim(1e-14, max(idn.max(), idp.max()) * 3)
        ax.set_xlim(0, p.vdd)
        self._legend(ax, "lower right")
        return self._finish()

    def idvd(self, p: ProcessParams, vin: float, f=frozenset(), ref=None):
        """输出特性图：横轴 Vds（漏-源电压，伏），纵轴 Id（漏极电流，毫安）。

        物理意义：在几个固定的栅压下，看漏极电压增大时电流怎么变化。
        Vds 很小时电流随电压近似线性增长（线性区，像一个电阻）；
        Vds 较大时电流基本不再增长（饱和区，像一个恒流源）。
        NMOS 画在第一象限（电压、电流都为正）；PMOS 的电压电流都是负的，画在第三象限。
        """
        mn, mp = nmos(p, f), pmos(p, f)
        vd = np.linspace(0, p.vdd, 160)
        ax = self._ax(i18n.pick("输出特性 Id-Vds (NMOS 第一象限 / PMOS 第三象限)",
                                "Output Id-Vds (NMOS Q1 / PMOS Q3)"), "Vds (V)", "Id (mA)")
        # 画 4 条不同栅压的曲线族：栅压分别为 VDD 的 40%、60%、80%、100%。
        levels = [0.4, 0.6, 0.8, 1.0]
        # enumerate 同时给出序号 i 和值 frac。
        for i, frac in enumerate(levels):
            vg = frac * p.vdd
            # 只给最后一条曲线加图例名字，避免图例里重复出现 4 次 “NMOS”。
            lab_n = "NMOS" if i == len(levels) - 1 else None
            lab_p = "PMOS" if i == len(levels) - 1 else None
            # 乘 1e3：安培换成毫安。栅压越高，曲线越不透明（alpha 越大）。
            ax.plot(vd, mn.ids(vg, vd) * 1e3, color=C_N, lw=1.2, alpha=0.45 + 0.15 * i, label=lab_n)
            # PMOS：横纵坐标都取负号，画到第三象限。
            ax.plot(-vd, -mp.ids(vg, vd) * 1e3, color=C_P, lw=1.2, alpha=0.45 + 0.15 * i, label=lab_p)
            # 在每条 NMOS 曲线右端写上它的栅压，例如 "3.0V"。
            ax.text(p.vdd * 1.01, mn.ids(vg, p.vdd) * 1e3, f"{vg:.1f}V", color=TEXT2, fontsize=9, va="center")
        # curves at the current input bias（当前输入电压下的曲线，用粗线画）
        if ref:
            rp, rf = ref
            rvd = np.linspace(0, rp.vdd, 160)
            # min(vin, rp.vdd)：如果旧参数的电源电压更低，输入电压不能超过它。
            ax.plot(rvd, nmos(rp, rf).ids(min(vin, rp.vdd), rvd) * 1e3, color=C_REF, lw=1.6,
                    label=self._ref_label())
        ax.plot(vd, mn.ids(vin, vd) * 1e3, color=C_N, lw=2.2)
        ax.plot(-vd, -mp.ids(p.vdd - vin, vd) * 1e3, color=C_P, lw=2.2)
        # 反相器的工作点：在反相器里，NMOS 和 PMOS 串联，流过的电流必须相等。
        # 先算出当前 Vin 对应的 Vout，再算此时的电流，在两条粗线上各标一个点。
        # inverter_vout(...) 返回一组结果，[0] 取第一个，再用 float 转成普通小数。
        vout = float(inverter_vout(p, vin, features=f)[0])
        i_op = float(mn.ids(vin, vout))
        ax.plot([vout], [i_op * 1e3], "o", ms=8, color=C_N, mec=SURFACE, mew=2)
        # PMOS 的 Vds = Vout - VDD（负值），电流也取负。
        ax.plot([vout - p.vdd], [-i_op * 1e3], "o", ms=8, color=C_P, mec=SURFACE, mew=2)
        # 画出横轴、纵轴的零线，分隔四个象限。
        ax.axhline(0, color=C_MUTED, lw=0.8)
        ax.axvline(0, color=C_MUTED, lw=0.8)
        # 右边多留 15% 空间，用来放栅压标签文字。
        ax.set_xlim(-p.vdd * 1.02, p.vdd * 1.15)
        self._legend(ax, "upper left")
        return self._finish()

    def vtc(self, p: ProcessParams, vin: float, s, f=frozenset(), ref=None):
        """反相器电压传输特性（VTC）：横轴 Vin（输入电压），纵轴 Vout（输出电压），单位都是伏。

        物理意义：理想反相器在输入低时输出高、输入高时输出低，中间有一段陡峭的翻转区。
          VM  —— 翻转点（Vout = Vin 的位置），理想情况在 VDD 的一半；
          VIL/VIH —— 曲线斜率为 -1 的两点，界定“可靠的低/高输入”范围；
          NMH/NML —— 噪声容限：输入上叠加多大的干扰仍能正确识别高/低电平；
          最大增益 —— 翻转区最陡处的斜率，越大越接近理想开关。
        右侧第二个纵轴（绿色）画的是电源电流 IDD：翻转过程中 NMOS 和 PMOS 同时导通，
        会有电流从 VDD 直接流到地（短路电流），这是功耗的来源之一。
        s 是 summarize 的计算结果，里面已经算好了 VTC 数据。
        """
        r = s.vtc
        ax = self._ax(i18n.pick("反相器电压传输特性 VTC", "Inverter voltage transfer characteristic"),
                      "Vin (V)", "Vout (V)")
        if ref:
            # 【语法】*ref 把元组 (旧参数, 旧特性) 拆成两个参数传入。
            rs = summarize_cached(*ref)
            ax.plot(rs.vtc.vin, rs.vtc.vout, color=C_REF, lw=1.6,
                    label=f"{self._ref_label()}  VM={rs.vtc.vm:.2f} V")
        ax.plot(r.vin, r.vout, color=C_N, lw=2, label="Vout(Vin)")
        # 对角虚线 Vout = Vin：它和 VTC 曲线的交点就是翻转点 VM。
        ax.plot([0, p.vdd], [0, p.vdd], color=C_MUTED, lw=1, ls="--", label="Vout = Vin")
        # 在 VIL、VM、VIH 处画竖直点线，顶部写上名字和数值（"\n" 表示换行）。
        for x, name in ((r.vil, "VIL"), (r.vm, "VM"), (r.vih, "VIH")):
            ax.axvline(x, color=C_MUTED, lw=0.8, ls=":")
            ax.text(x, p.vdd * 1.03, f"{name}\n{x:.2f}", color=TEXT2, fontsize=9.5, ha="center", va="bottom")
        # 当前输入电压对应的工作点（橙色圆点）。
        vout = float(inverter_vout(p, vin, features=f)[0])
        ax.plot([vin], [vout], "o", ms=9, color=C_P, mec=SURFACE, mew=2, label=i18n.pick("工作点", "Operating point"))
        # 左下角写上噪声容限和最大增益。transform=ax.transAxes 表示坐标按“坐标区比例”算
        # （0,0 是左下角，1,1 是右上角），而不是按数据值。
        ax.text(0.02, 0.04,
                f"NMH = {r.nmh:.2f} V   NML = {r.nml:.2f} V\n"
                + i18n.pick("最大增益", "Max gain") + f" = {r.max_gain:.1f}",
                transform=ax.transAxes, color=TEXT2, fontsize=10.5)
        ax.set_xlim(0, p.vdd)
        ax.set_ylim(-0.05 * p.vdd, p.vdd * 1.18)
        # supply current VDD -> GND through both devices (no DC current flows into the gate)
        # 电源电流：从 VDD 经过两个晶体管流到 GND（栅极是绝缘的，没有直流电流流进栅极）。
        # twinx()：创建共享横轴、但有独立右侧纵轴的第二组坐标轴。
        ax2 = ax.twinx()
        i_ma = r.i_short * 1e3                   # 安培 -> 毫安
        ax2.plot(r.vin, i_ma, color=C_I, lw=1.8,
                 label=i18n.pick("电源电流 IDD (右轴)", "Supply current IDD (right)"))
        # 当前工作点的电流（绿色圆点）。
        i_op = float(nmos(p, f).ids(vin, vout)) * 1e3
        ax2.plot([vin], [i_op], "o", ms=7, color=C_I, mec=SURFACE, mew=1.5)
        # 纵轴上限设为最大电流的 2.4 倍，让电流曲线只占下半部分，不挡住 VTC 曲线。
        ax2.set_ylim(0, float(i_ma.max()) * 2.4)
        ax2.set_ylabel("IDD (mA)", color=TEXT2, fontsize=11.5)
        ax2.tick_params(colors=TEXT2, labelsize=10, length=3)
        for side in ("top", "left", "bottom"):
            ax2.spines[side].set_visible(False)
        ax2.spines["right"].set_color(GRID)
        # 两组坐标轴各有自己的曲线，把它们的图例条目合并到一个图例框里显示。
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax2.legend(h1 + h2, l1 + l2, loc="upper right", bbox_to_anchor=(1.0, 0.9), fontsize=10, frameon=True,
                   facecolor=SURFACE, edgecolor=GRID, labelcolor=TEXT2)
        return self._finish()

    def tran(self, p: ProcessParams, s, cursor_t: float | None = None, ref=None):
        """瞬态响应图：横轴时间（皮秒 ps，1 ps = 10⁻¹² 秒），纵轴电压（伏）。

        物理意义：输入 Vin 突然从低跳到高（或反过来）时，输出 Vout 不会瞬间翻转，
        因为晶体管要给负载电容 CL 充放电，需要时间。
          tpHL —— 输出从高变低的传播延迟；tpLH —— 输出从低变高的传播延迟。
        延迟越小，芯片能跑得越快。中间的水平点线是 VDD/2，延迟就是在这一半电压处量的。
        cursor_t：可选，在某个时刻画一条竖线（配合 3D 动画显示当前时间）。
        """
        r = s.tran
        t_ps = r.t * 1e12                        # 秒 -> 皮秒
        ax = self._ax(i18n.pick(f"瞬态响应 (CL = {p.cload_ff:.0f} fF)", f"Transient (CL = {p.cload_ff:.0f} fF)"),
                      i18n.pick("时间 (ps)", "time (ps)"), "V")
        ax.plot(t_ps, r.vin, color=C_N, lw=2, label="Vin")
        # t_ps[-1]：列表最后一个元素（负数下标表示从末尾倒着数），即仿真结束时间。
        t_max = t_ps[-1]
        if ref:
            rr = summarize_cached(*ref).tran
            ax.plot(rr.t * 1e12, rr.vout, color=C_REF, lw=1.6,
                    label=f"{self._ref_label()}  tpHL={rr.tphl * 1e12:.0f} ps")
            # 横轴要能同时放下新旧两条曲线，取较长的结束时间。
            t_max = max(t_max, rr.t[-1] * 1e12)
        ax.plot(t_ps, r.vout, color=C_P, lw=2, label="Vout")
        ax.axhline(p.vdd / 2, color=C_MUTED, lw=0.8, ls=":")      # VDD/2 参考线
        # 在图右侧中间写上两个延迟数值。
        ax.text(0.98, 0.5, f"tpHL = {r.tphl * 1e12:.1f} ps\ntpLH = {r.tplh * 1e12:.1f} ps",
                transform=ax.transAxes, ha="right", va="center", color=TEXT2, fontsize=11)
        if cursor_t is not None:
            ax.axvline(cursor_t * 1e12, color=TEXT, lw=1)
        ax.set_xlim(0, t_max)
        # 纵轴范围取新旧两套电源电压中较大的那个，上下各留一点空白。
        top = max(p.vdd, ref[0].vdd) if ref else p.vdd
        ax.set_ylim(-0.1 * top, 1.15 * top)
        self._legend(ax, "upper right")
        return self._finish()

    def vtl(self, p: ProcessParams, f=frozenset(), ref=None):
        """NMOS threshold vs gate length: roll-off (low Vds) and DIBL (Vds = VDD).

        NMOS 阈值电压随栅长变化图：横轴栅长 L（对数刻度），纵轴阈值电压 Vtn（伏）。

        物理意义（短沟道效应）：
          * 阈值滚降（roll-off）：栅长越短，源漏两端的耗尽区“抢走”了沟道里更多的电荷，
            栅极更容易打开晶体管，Vt 下降。蓝线是漏压很小（0.05 V）时的情况。
          * DIBL（漏致势垒降低）：漏极电压高时，漏极的电场会进一步拉低源端的势垒，
            Vt 再下降一截。橙线是 Vds = VDD 时的情况。两条线的差距除以电压差就是 DIBL（mV/V）。
          * 灰色虚线是“理想值”：没有这些二级效应时的阈值电压。
          * LDD（轻掺杂漏）能让结更浅，减轻短沟道效应；开启时会额外画一条“无 LDD”对比线。
        """
        nano = p.l_um < 0.1                   # advanced node: zoom the L axis into the nm range
        # （栅长小于 0.1 µm 属于先进工艺，横轴改用纳米 nm 显示）
        ax = self._ax(i18n.pick("NMOS 阈值电压随栅长变化 (短沟道效应)", "NMOS Vt vs gate length (short-channel effects)"),
                      i18n.pick("栅长 L (nm, 对数)", "gate length L (nm, log)") if nano else
                      i18n.pick("栅长 L (µm, 对数)", "gate length L (µm, log)"), "Vtn (V)")
        # 横轴范围（单位 µm）：先进工艺 8 nm~300 nm，老工艺 0.1~5 µm。
        lr = (0.008, 0.3) if nano else (0.1, 5.0)
        # 算出曲线：ls=一串栅长值，lin=低漏压下的 Vt，sat=高漏压（VDD）下的 Vt。
        # *lr 把 (最小, 最大) 摊开成两个参数。
        ls, lin, sat = vt_vs_length(p, f, "n", *lr)
        # 理想阈值电压（灰色虚线）的算法分两种情况：
        if p.tsi_nm > 0:                      # multi-gate: Vt is set by the work function, not doping
            # 多栅器件（FinFET/GAA，硅体厚度 tsi>0）：Vt 由栅极材料的功函数决定，
            # 用一个很长的栅长（10 µm）来近似“没有短沟道效应”的情况。
            ideal = nmos(p.copy(l_um=10.0), f).vt_mag
        else:
            # 平面器件：关闭所有特性（空集合）算出的 Vt 就是理想值。
            ideal = nmos(p, frozenset()).vt_mag
        ax.axhline(ideal, color=C_MUTED, lw=1, ls="--", label=i18n.pick("理想 (无二级效应)", "ideal (no 2nd-order effects)"))
        # 如果启用了 LDD，就把 "ldd" 从特性中去掉再算一次，画出点线作对比，展示 LDD 的好处。
        # "_" 是惯用的“不需要的变量”名字。
        if "ldd" in f:
            _, _, sat0 = vt_vs_length(p, frozenset(f) - {"ldd"}, "n", *lr)
            ax.plot(ls, sat0, color=C_MUTED, lw=1.4, ls=":",
                    label=i18n.pick("无 LDD 深结, Vds = VDD", "no LDD (deep xj), Vds = VDD"))
        if ref:
            _, rlin, rsat = vt_vs_length(ref[0], ref[1], "n", *lr)
            ax.plot(ls, rlin, color=C_REF, lw=1.4, label=self._ref_label())
            ax.plot(ls, rsat, color=C_REF, lw=1.4)
        ax.plot(ls, lin, color=C_N, lw=2, label="|Vds| = 0.05 V")
        ax.plot(ls, sat, color=C_P, lw=2, label=f"|Vds| = VDD = {p.vdd:.1f} V")
        # 用圆点标出当前栅长下两种漏压的 Vt：Vt(Vds) ≈ Vt0 - DIBL × Vds。
        m = nmos(p, f)
        ax.plot([p.l_um], [m.vt_mag - m.dibl * 0.05], "o", ms=8, color=C_N, mec=SURFACE, mew=2)
        ax.plot([p.l_um], [m.vt_mag - m.dibl * p.vdd], "o", ms=8, color=C_P, mec=SURFACE, mew=2)
        # 在橙色圆点旁边写出 DIBL 数值（xytext 是相对圆点偏移的像素点数）。
        ax.annotate(f"DIBL = {m.dibl * 1e3:.0f} mV/V", (p.l_um, m.vt_mag - m.dibl * p.vdd),
                    textcoords="offset points", xytext=(10, -14), color=TEXT2, fontsize=10)
        # 横轴改为对数刻度，并设置固定的刻度位置（选的都是历史上常见的工艺节点）。
        ax.set_xscale("log")
        ax.set_xlim(ls[0], ls[-1])
        ticks = [0.01, 0.02, 0.03, 0.05, 0.1, 0.2] if nano else [0.1, 0.18, 0.25, 0.5, 1, 2, 5]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_minor_locator(NullLocator())
        # 【语法】lambda v, _: ...  是“匿名小函数”：接收刻度值 v（和一个不用的参数 _），返回刻度文字。
        # 纳米模式下把 µm 乘 1000 显示成 nm；":g" 格式会去掉多余的零（如 0.10 -> 0.1）。
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 1e3:g}" if nano else f"{v:g}"))
        # 纵轴下限：取曲线最低点（至少到 0），留一点边距，但不低于 -0.6 V；上限比理想值高 25%。
        lo = min(float(sat.min()), 0.0)
        if "ldd" in f:
            lo = min(lo, float(sat0.min()))
        ax.set_ylim(max(lo - 0.05, -0.6), ideal * 1.25 + 0.05)
        self._legend(ax, "lower right")
        return self._finish()
