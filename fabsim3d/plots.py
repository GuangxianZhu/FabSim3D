"""Matplotlib (Agg) charts rendered into Panda3D textures."""
from __future__ import annotations

import numpy as np
import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from . import i18n  # noqa: E402
from .process_core import summarize_cached  # noqa: E402
from .device_model import ProcessParams, nmos, pmos, inverter_vout, vt_vs_length  # noqa: E402

# dark-surface palette (validated categorical slots 1/2 + text tokens)
SURFACE = "#1a1a19"
TEXT = "#ffffff"
TEXT2 = "#c3c2b7"
GRID = "#383835"
C_N = "#3987e5"     # NMOS / series 1
C_P = "#d95926"     # PMOS / series 2
C_MUTED = "#8a8980"
C_REF = "#6f6e68"      # grey "before" reference curves


def setup_fonts(path: str | None):
    if path:
        try:
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
        except Exception:
            pass
    matplotlib.rcParams["axes.unicode_minus"] = False


class PlotRenderer:
    def __init__(self, w_px=520, h_px=400, dpi=100):
        self.w, self.h, self.dpi = w_px, h_px, dpi
        self.fig = Figure(figsize=(w_px / dpi, h_px / dpi), dpi=dpi, facecolor=SURFACE)
        self.canvas = FigureCanvasAgg(self.fig)

    def _ax(self, title: str, xlabel: str, ylabel: str):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(SURFACE)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=TEXT2, labelsize=11, length=3)
        ax.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_title(title, color=TEXT, fontsize=13, loc="left", pad=8)
        ax.set_xlabel(xlabel, color=TEXT2, fontsize=11.5)
        ax.set_ylabel(ylabel, color=TEXT2, fontsize=11.5)
        return ax

    def _legend(self, ax, loc="best"):
        leg = ax.legend(loc=loc, fontsize=10, frameon=True, facecolor=SURFACE, edgecolor=GRID,
                        labelcolor=TEXT2)
        return leg

    @staticmethod
    def _ref_label():
        return i18n.pick("操作前", "before")

    def _finish(self) -> np.ndarray:
        self.fig.tight_layout(pad=0.6)
        self.canvas.draw()
        buf = np.asarray(self.canvas.buffer_rgba())
        return np.ascontiguousarray(buf[::-1])     # Panda textures start at bottom row

    # ------------------------------------------------------------------ charts
    def idvg(self, p: ProcessParams, vin: float, f=frozenset(), ref=None):
        mn, mp = nmos(p, f), pmos(p, f)
        v = np.linspace(0, p.vdd, 200)
        ax = self._ax(i18n.pick("转移特性 |Id|-|Vgs|  (|Vds| = VDD)", "Transfer |Id| vs |Vgs|  (|Vds| = VDD)"),
                      "|Vgs| (V)", "|Id| (A)")
        idn = mn.ids(v, p.vdd)
        idp = mp.ids(v, p.vdd)
        if ref:
            rp, rf = ref
            rv = np.linspace(0, rp.vdd, 200)
            ax.semilogy(rv, nmos(rp, rf).ids(rv, rp.vdd), color=C_REF, lw=1.6, label=self._ref_label())
            ax.semilogy(rv, pmos(rp, rf).ids(rv, rp.vdd), color=C_REF, lw=1.6, ls="--")
        ax.semilogy(v, idn, color=C_N, lw=2, label=f"NMOS  Vtn={mn.vt:.2f} V")
        ax.semilogy(v, idp, color=C_P, lw=2, ls="--", label=f"PMOS  |Vtp|={mp.vt_mag:.2f} V")
        for vt, c in ((mn.vt_mag, C_N), (mp.vt_mag, C_P)):
            ax.axvline(vt, color=c, lw=1, ls=":")
        ax.plot([vin], [mn.ids(vin, p.vdd)], "o", ms=8, color=C_N, mec=SURFACE, mew=2)
        ax.plot([p.vdd - vin], [mp.ids(p.vdd - vin, p.vdd)], "o", ms=8, color=C_P, mec=SURFACE, mew=2)
        ax.set_ylim(1e-14, max(idn.max(), idp.max()) * 3)
        ax.set_xlim(0, p.vdd)
        self._legend(ax, "lower right")
        return self._finish()

    def idvd(self, p: ProcessParams, vin: float, f=frozenset(), ref=None):
        mn, mp = nmos(p, f), pmos(p, f)
        vd = np.linspace(0, p.vdd, 160)
        ax = self._ax(i18n.pick("输出特性 Id-Vds (NMOS 第一象限 / PMOS 第三象限)",
                                "Output Id-Vds (NMOS Q1 / PMOS Q3)"), "Vds (V)", "Id (mA)")
        levels = [0.4, 0.6, 0.8, 1.0]
        for i, frac in enumerate(levels):
            vg = frac * p.vdd
            lab_n = "NMOS" if i == len(levels) - 1 else None
            lab_p = "PMOS" if i == len(levels) - 1 else None
            ax.plot(vd, mn.ids(vg, vd) * 1e3, color=C_N, lw=1.2, alpha=0.45 + 0.15 * i, label=lab_n)
            ax.plot(-vd, -mp.ids(vg, vd) * 1e3, color=C_P, lw=1.2, alpha=0.45 + 0.15 * i, label=lab_p)
            ax.text(p.vdd * 1.01, mn.ids(vg, p.vdd) * 1e3, f"{vg:.1f}V", color=TEXT2, fontsize=9, va="center")
        # curves at the current input bias
        if ref:
            rp, rf = ref
            rvd = np.linspace(0, rp.vdd, 160)
            ax.plot(rvd, nmos(rp, rf).ids(min(vin, rp.vdd), rvd) * 1e3, color=C_REF, lw=1.6,
                    label=self._ref_label())
        ax.plot(vd, mn.ids(vin, vd) * 1e3, color=C_N, lw=2.2)
        ax.plot(-vd, -mp.ids(p.vdd - vin, vd) * 1e3, color=C_P, lw=2.2)
        vout = float(inverter_vout(p, vin, features=f)[0])
        i_op = float(mn.ids(vin, vout))
        ax.plot([vout], [i_op * 1e3], "o", ms=8, color=C_N, mec=SURFACE, mew=2)
        ax.plot([vout - p.vdd], [-i_op * 1e3], "o", ms=8, color=C_P, mec=SURFACE, mew=2)
        ax.axhline(0, color=C_MUTED, lw=0.8)
        ax.axvline(0, color=C_MUTED, lw=0.8)
        ax.set_xlim(-p.vdd * 1.02, p.vdd * 1.15)
        self._legend(ax, "upper left")
        return self._finish()

    def vtc(self, p: ProcessParams, vin: float, s, f=frozenset(), ref=None):
        r = s.vtc
        ax = self._ax(i18n.pick("反相器电压传输特性 VTC", "Inverter voltage transfer characteristic"),
                      "Vin (V)", "Vout (V)")
        if ref:
            rs = summarize_cached(*ref)
            ax.plot(rs.vtc.vin, rs.vtc.vout, color=C_REF, lw=1.6,
                    label=f"{self._ref_label()}  VM={rs.vtc.vm:.2f} V")
        ax.plot(r.vin, r.vout, color=C_N, lw=2, label="Vout(Vin)")
        ax.plot([0, p.vdd], [0, p.vdd], color=C_MUTED, lw=1, ls="--", label="Vout = Vin")
        for x, name in ((r.vil, "VIL"), (r.vm, "VM"), (r.vih, "VIH")):
            ax.axvline(x, color=C_MUTED, lw=0.8, ls=":")
            ax.text(x, p.vdd * 1.03, f"{name}\n{x:.2f}", color=TEXT2, fontsize=9.5, ha="center", va="bottom")
        vout = float(inverter_vout(p, vin, features=f)[0])
        ax.plot([vin], [vout], "o", ms=9, color=C_P, mec=SURFACE, mew=2, label=i18n.pick("工作点", "Operating point"))
        ax.text(0.02, 0.04,
                f"NMH = {r.nmh:.2f} V   NML = {r.nml:.2f} V\n"
                + i18n.pick("最大增益", "Max gain") + f" = {r.max_gain:.1f}",
                transform=ax.transAxes, color=TEXT2, fontsize=10.5)
        ax.set_xlim(0, p.vdd)
        ax.set_ylim(-0.05 * p.vdd, p.vdd * 1.18)
        self._legend(ax, "center right")
        return self._finish()

    def tran(self, p: ProcessParams, s, cursor_t: float | None = None, ref=None):
        r = s.tran
        t_ps = r.t * 1e12
        ax = self._ax(i18n.pick(f"瞬态响应 (CL = {p.cload_ff:.0f} fF)", f"Transient (CL = {p.cload_ff:.0f} fF)"),
                      i18n.pick("时间 (ps)", "time (ps)"), "V")
        ax.plot(t_ps, r.vin, color=C_N, lw=2, label="Vin")
        t_max = t_ps[-1]
        if ref:
            rr = summarize_cached(*ref).tran
            ax.plot(rr.t * 1e12, rr.vout, color=C_REF, lw=1.6,
                    label=f"{self._ref_label()}  tpHL={rr.tphl * 1e12:.0f} ps")
            t_max = max(t_max, rr.t[-1] * 1e12)
        ax.plot(t_ps, r.vout, color=C_P, lw=2, label="Vout")
        ax.axhline(p.vdd / 2, color=C_MUTED, lw=0.8, ls=":")
        ax.text(0.98, 0.5, f"tpHL = {r.tphl * 1e12:.1f} ps\ntpLH = {r.tplh * 1e12:.1f} ps",
                transform=ax.transAxes, ha="right", va="center", color=TEXT2, fontsize=11)
        if cursor_t is not None:
            ax.axvline(cursor_t * 1e12, color=TEXT, lw=1)
        ax.set_xlim(0, t_max)
        top = max(p.vdd, ref[0].vdd) if ref else p.vdd
        ax.set_ylim(-0.1 * top, 1.15 * top)
        self._legend(ax, "upper right")
        return self._finish()

    def vtl(self, p: ProcessParams, f=frozenset(), ref=None):
        """NMOS threshold vs gate length: roll-off (low Vds) and DIBL (Vds = VDD)."""
        ax = self._ax(i18n.pick("NMOS 阈值电压随栅长变化 (短沟道效应)", "NMOS Vt vs gate length (short-channel effects)"),
                      i18n.pick("栅长 L (µm, 对数)", "gate length L (µm, log)"), "Vtn (V)")
        ls, lin, sat = vt_vs_length(p, f, "n")
        ideal = nmos(p, frozenset()).vt_mag
        ax.axhline(ideal, color=C_MUTED, lw=1, ls="--", label=i18n.pick("理想 (无二级效应)", "ideal (no 2nd-order effects)"))
        if "ldd" in f:
            _, _, sat0 = vt_vs_length(p, frozenset(f) - {"ldd"}, "n")
            ax.plot(ls, sat0, color=C_MUTED, lw=1.4, ls=":",
                    label=i18n.pick("无 LDD 深结, Vds = VDD", "no LDD (deep xj), Vds = VDD"))
        if ref:
            _, rlin, rsat = vt_vs_length(ref[0], ref[1], "n")
            ax.plot(ls, rlin, color=C_REF, lw=1.4, label=self._ref_label())
            ax.plot(ls, rsat, color=C_REF, lw=1.4)
        ax.plot(ls, lin, color=C_N, lw=2, label="|Vds| = 0.05 V")
        ax.plot(ls, sat, color=C_P, lw=2, label=f"|Vds| = VDD = {p.vdd:.1f} V")
        m = nmos(p, f)
        ax.plot([p.l_um], [m.vt_mag - m.dibl * 0.05], "o", ms=8, color=C_N, mec=SURFACE, mew=2)
        ax.plot([p.l_um], [m.vt_mag - m.dibl * p.vdd], "o", ms=8, color=C_P, mec=SURFACE, mew=2)
        ax.annotate(f"DIBL = {m.dibl * 1e3:.0f} mV/V", (p.l_um, m.vt_mag - m.dibl * p.vdd),
                    textcoords="offset points", xytext=(10, -14), color=TEXT2, fontsize=10)
        ax.set_xscale("log")
        ax.set_xlim(ls[0], ls[-1])
        ticks = [0.1, 0.18, 0.25, 0.5, 1, 2, 5]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        lo = min(float(sat.min()), 0.0)
        if "ldd" in f:
            lo = min(lo, float(sat0.min()))
        ax.set_ylim(max(lo - 0.05, -0.6), ideal * 1.25 + 0.05)
        self._legend(ax, "lower right")
        return self._finish()
