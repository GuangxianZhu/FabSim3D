"""Main Panda3D application: three-column teaching UI around the 3D wafer."""
from __future__ import annotations

import math
import re
import time

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import (DirectButton, DirectFrame, DirectScrolledFrame,
                                  DirectSlider)
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (AmbientLight, DirectionalLight, Filename, TextNode,
                          Texture, TransparencyAttrib, Vec3)

from . import i18n
from .device_model import ProcessParams, inverter_vout, nmos, pmos
from .fonts import find_cjk_font
from .i18n import tr
from .materials import MATERIALS, mat
from .plots import PlotRenderer, setup_fonts
from .flows import DEFAULT_FLOW, FLOWS
from .process_core import Wafer, build_until, is_skipped, make_ctx, run_phase, sci, summarize_cached
from .scene import WaferScene

# ---------------------------------------------------------------- style
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

LEFT_W = 0.74
RIGHT_W = 0.94
PLOT_W, PLOT_H = 540, 400

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


class CmosApp(ShowBase):
    def __init__(self, opts=None):
        ShowBase.__init__(self)
        self.opts = opts or {}
        self.disableMouse()
        self.setBackgroundColor(*BG3D)
        self.setFrameRateMeter(False)

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
        setup_fonts(font_path)

        self.params = ProcessParams()
        self.flow = FLOWS[(opts or {}).get("flow") or DEFAULT_FLOW]
        self.ctx = self._new_ctx()
        self.scene = WaferScene(self, self.render)
        self._setup_lights()

        # camera orbit state
        self.cam_target = Vec3(10.0, 4.0, -0.4)
        self.cam_h, self.cam_p, self.cam_d = -28.0, 30.0, 36.0
        self.drag = None
        self.last_mouse = None

        # process state
        self.step = 0
        self.anim_step = None
        self.phase_queue = []
        self.caption = ("", "")
        self.wafer = None
        self.playing = False
        self.play_wait = 0.0
        self.speed = 1.0

        # quiz
        self.quiz_enabled = False
        self.quiz_results = {}
        self.quiz_frame = None
        self.resume_after_quiz = False

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

        self.cut_on = True
        self.cut_y = 3.5
        self.scene.cut_y = self.cut_y

        self.ui_roots = []
        self.build_ui()
        self.goto(0)
        self.layout_viewport()
        self.update_camera()

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
    def _setup_lights(self):
        amb = AmbientLight("amb")
        amb.setColor((0.48, 0.48, 0.52, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        for hpr, c in (((-35, -50, 0), 0.62), ((140, -30, 0), 0.25)):
            d = DirectionalLight("dir")
            d.setColor((c, c, c, 1))
            np_ = self.render.attachNewNode(d)
            np_.setHpr(*hpr)
            self.render.setLight(np_)

    def layout_viewport(self):
        if not self.win:
            return
        w, h = self.win.getXSize(), self.win.getYSize()
        if w <= 0 or h <= 0:
            return
        aspect = w / h
        left = LEFT_W / (2 * aspect)
        right = 1 - RIGHT_W / (2 * aspect)
        left, right = min(left, 0.45), max(right, 0.55)
        dr = self.cam.node().getDisplayRegion(0)
        dr.setDimensions(left, right, 0, 1)
        self.camLens.setAspectRatio((right - left) * w / h)
        self.camLens.setFov(40)
        self.view_frac = (left, right)

    def _on_window(self, win):
        if win == self.win:
            self.layout_viewport()

    def update_camera(self):
        h, p = math.radians(self.cam_h), math.radians(self.cam_p)
        off = Vec3(math.cos(p) * math.sin(h), -math.cos(p) * math.cos(h), math.sin(p)) * self.cam_d
        self.camera.setPos(self.cam_target + off)
        self.camera.lookAt(self.cam_target)

    def set_cam(self, preset):
        self.cam_target = Vec3(10.0, 4.0, -0.4)
        self.cam_h, self.cam_p, self.cam_d = {
            "iso": (-28.0, 30.0, 36.0), "front": (0.0, 4.0, 30.0), "top": (0.0, 88.0, 32.0)}[preset]
        self.update_camera()

    def _mouse_in_view(self):
        if not self.mouseWatcherNode.hasMouse():
            return False
        x = (self.mouseWatcherNode.getMouseX() + 1) / 2
        return self.view_frac[0] <= x <= self.view_frac[1] and self.quiz_frame is None

    def _drag_start(self, mode):
        if self._mouse_in_view():
            self.drag = mode
            m = self.mouseWatcherNode.getMouse()
            self.last_mouse = (m.x, m.y)

    def _drag_end(self):
        self.drag = None

    def _zoom(self, f):
        if self._mouse_in_view():
            self.cam_d = min(max(self.cam_d * f, 8.0), 90.0)
            self.update_camera()

    def _handle_drag(self):
        if not self.drag or not self.mouseWatcherNode.hasMouse():
            return
        m = self.mouseWatcherNode.getMouse()
        dx, dy = m.x - self.last_mouse[0], m.y - self.last_mouse[1]
        self.last_mouse = (m.x, m.y)
        if self.drag == "rot":
            self.cam_h -= dx * 120
            self.cam_p = min(max(self.cam_p - dy * 80, -10), 89)
        else:
            q = self.camera.getQuat(self.render)
            right, up = q.getRight(), q.getUp()
            k = self.cam_d * 0.6
            self.cam_target -= right * dx * k + up * dy * k
        self.update_camera()

    # ================================================================= process control
    @property
    def steps(self):
        return self.flow.steps

    def _new_ctx(self):
        faults = getattr(self, "faults", None)
        return make_ctx(self.params, self.flow, faults)

    def set_flow(self, key: str):
        """Switch technology generation (process flow)."""
        if key == self.flow.key or key not in FLOWS:
            return
        self.flow = FLOWS[key]
        self.quiz_results = {}
        self.playing = False
        self.anim_step = None
        self.phase_queue = []
        self.step = 0
        self.goto(0)
        self.rebuild_ui()

    def goto(self, i: int):
        """Show the state after step i without animation."""
        i = max(0, min(i, len(self.steps) - 1))
        self.scene.clear_particles()
        self.phase_queue = []
        self.anim_step = None
        self.ctx = self._new_ctx()
        self.wafer = build_until(self.ctx, i)
        self.step = i
        self.caption = ("", "")
        self.scene.set_wafer(self.wafer, self.ctx, terminal_mode=self.is_done())
        self._apply_sim()
        self.refresh_ui()

    def is_done(self):
        return self.step == len(self.steps) - 1 and self.anim_step is None

    def animate_step(self, i: int):
        if i < 0 or i >= len(self.steps):
            return
        if self.anim_step is not None or self.step != i - 1:
            self.goto(i - 1) if i > 0 else self._blank()
        self.anim_step = i
        self.scene.terminal_mode = False
        self.scene.set_sim(None)
        self.wafer.current_step = self.steps[i].key
        self.phase_queue = [] if is_skipped(self.ctx, self.steps[i]) else list(self.steps[i].phases)
        if not self.phase_queue:
            self._phase_finished()
            return
        self._next_phase()
        self.refresh_ui()

    def _blank(self):
        self.wafer = Wafer()
        self.ctx = self._new_ctx()
        self.scene.set_wafer(self.wafer, self.ctx)
        self.step = -1

    def _next_phase(self):
        ph = self.phase_queue.pop(0)
        self.caption = (ph.zh, ph.en)
        anim = run_phase(self.wafer, self.ctx, ph)
        self.scene.start_anim(anim, ph.duration)
        self._refresh_caption()

    def _phase_finished(self):
        if self.phase_queue:
            self._next_phase()
            return
        self.step = self.anim_step
        self.anim_step = None
        self.caption = ("", "")
        if self.is_done():
            self.scene.terminal_mode = True
            self.scene.rebuild_labels()
            self._apply_sim()
        self.refresh_ui()
        self.play_wait = 0.9
        if self.quiz_enabled and self.steps[self.step].quiz and self.step not in self.quiz_results:
            self.show_quiz(self.step)
        if self.step == len(self.steps) - 1:
            self.playing = False
            self._refresh_play_btn()

    def next_step(self):
        if self.quiz_frame:
            return
        if self.anim_step is not None:
            self.goto(self.anim_step)
        elif self.step < len(self.steps) - 1:
            self.animate_step(self.step + 1)

    def prev_step(self):
        if self.quiz_frame:
            return
        cur = self.anim_step if self.anim_step is not None else self.step
        self.goto(max(cur - 1, 0))

    def toggle_play(self):
        if self.quiz_frame:
            return
        self.playing = not self.playing
        if self.playing and self.anim_step is None:
            if self.step >= len(self.steps) - 1:
                self.goto(0)
            self.play_wait = 0.0
        self._refresh_play_btn()

    def jump_to(self, i):
        if self.quiz_frame:
            return
        cur = self.anim_step if self.anim_step is not None else self.step
        if i == cur + 1 and self.anim_step is None:
            self.animate_step(i)
        else:
            self.goto(i)

    # ================================================================= tick
    def _tick(self, task):
        now = time.time()
        dt = min(now - self.last_time, 0.1)
        self.last_time = now
        self._handle_drag()
        if self.scene.update(dt, self.speed) and self.anim_step is not None:
            self._phase_finished()
        if self.playing and self.anim_step is None and not self.quiz_frame:
            self.play_wait -= dt * self.speed
            if self.play_wait <= 0 and self.step < len(self.steps) - 1:
                self.animate_step(self.step + 1)
        if self.tran_t is not None:
            self._advance_transient(dt)
        if self.params_dirty and now - self.last_plot > 0.15:
            self._commit_params()
        if self.plot_dirty and self.right_tab == "elec" and now - self.last_plot > 0.12:
            self._redraw_plot()
        return task.cont

    # ================================================================= electrical
    def _sim_values(self, vin, vout=None):
        p = self.params
        mn, mp = nmos(p, self.flow.features), pmos(p, self.flow.features)
        if vout is None:
            vout = float(inverter_vout(p, vin, features=self.flow.features)[0])
        idn = float(mn.ids(vin, max(vout, 0.0)))
        idp = float(mp.ids(p.vdd - vin, max(p.vdd - vout, 0.0)))

        def sig(x):
            return 1 / (1 + math.exp(-max(min(x, 40), -40)))
        return {"vin": vin, "vout": vout, "vdd": p.vdd, "gnd": 0.0, "in": idn, "ip": idp,
                "inv_n": sig((vin - mn.vt) / 0.08), "inv_p": sig((p.vdd - vin - abs(mp.vt)) / 0.08)}

    def _apply_sim(self):
        if self.sim3d and self.is_done():
            if self.tran_t is None:
                self.scene.set_sim(self._sim_values(self.vin))
        else:
            self.scene.set_sim(None)

    def _advance_transient(self, dt):
        s = summarize_cached(self.params, self.flow.features)
        dur = 5.0
        self.tran_t += dt
        if self.tran_t > dur:
            self.tran_t = None
            self.plot_dirty = True
            self._apply_sim()
            return
        r = s.tran
        t_sim = self.tran_t / dur * r.t[-1]
        import numpy as np
        vin = float(np.interp(t_sim, r.t, r.vin))
        vout = float(np.interp(t_sim, r.t, r.vout))
        self.tran_cursor = t_sim
        if self.sim3d and self.is_done():
            self.scene.set_sim(self._sim_values(vin, vout))
        self.plot_dirty = True

    def play_transient(self):
        self.tran_t = 0.0
        self.tran_cursor = 0.0
        self.plot_kind = "tran"
        if self.is_done() and not self.sim3d:
            self.toggle_sim3d()
        self.refresh_ui()

    def toggle_sim3d(self):
        self.sim3d = not self.sim3d
        if self.sim3d and self.is_done():
            self.cut_on = True
            self.cut_y = 3.5
            self.scene.set_cut(self.cut_y)
        self._apply_sim()
        self.refresh_ui()

    def _redraw_plot(self):
        p = self.params
        s = summarize_cached(p, self.flow.features)
        vin = min(self.vin, p.vdd)
        if self.plot_kind == "idvg":
            img = self.renderer.idvg(p, vin, self.flow.features)
        elif self.plot_kind == "idvd":
            img = self.renderer.idvd(p, vin, self.flow.features)
        elif self.plot_kind == "tran":
            img = self.renderer.tran(p, s, self.tran_cursor if self.tran_t is not None else None)
        else:
            img = self.renderer.vtc(p, vin, s, self.flow.features)
        self.plot_tex.setRamImageAs(img.tobytes(), "RGBA")
        self.plot_dirty = False
        self.last_plot = time.time()

    def set_vin(self):
        v = float(self.vin_slider["value"]) * self.params.vdd
        if abs(v - self.vin) < 1e-6:
            return
        self.vin = v
        self.vin_text.setText(tr("vin", v=v))
        self.plot_dirty = True
        if self.tran_t is None:
            self._apply_sim()

    def set_param(self, key, lo, hi, log, slider, label, lkey):
        x = float(slider["value"])
        v = 10 ** (math.log10(lo) + x * (math.log10(hi) - math.log10(lo))) if log else lo + x * (hi - lo)
        old = getattr(self.params, key)
        if abs(v - old) <= 1e-6 * abs(old):
            return
        setattr(self.params, key, v)
        label.setText(tr(lkey, v=sci(v, "cm^-3" if key == "na_cm3" else "cm^-2") if log else v))
        self.params_dirty = True

    def _commit_params(self):
        self.params_dirty = False
        self.vin = min(self.vin, self.params.vdd)
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
        self.params = ProcessParams()
        self.vin = self.params.vdd / 2
        self.goto(self.anim_step if self.anim_step is not None else self.step)
        self.rebuild_ui()

    # ================================================================= quiz
    def show_quiz(self, i):
        q = self.steps[i].quiz
        self.resume_after_quiz = self.playing
        self.playing = False
        f = DirectFrame(parent=self.aspect2d, frameColor=(0.06, 0.065, 0.08, 0.97),
                        frameSize=(-0.78, 0.78, -0.62, 0.55), state=DGG.NORMAL)
        self.quiz_frame = f
        OnscreenText(parent=f, text=tr("quiz_title", i=i + 1), pos=(-0.72, 0.46), scale=0.04,
                     fg=ACCENT, align=TextNode.ALeft)
        OnscreenText(parent=f, text=self.wrap(i18n.pick(*q.q), 1.44, 0.045), pos=(-0.72, 0.37), scale=0.045,
                     fg=TXT, align=TextNode.ALeft)
        self.quiz_feedback = OnscreenText(parent=f, text="", pos=(-0.72, -0.36), scale=0.034, fg=TXT2,
                                          align=TextNode.ALeft, mayChange=True)
        self.quiz_btns = []
        for k, opt in enumerate(q.options):
            b = self._button(f, f"{'ABCD'[k]}.  {i18n.pick(*opt)}", (-0.70, 0.18 - k * 0.12), 1.40,
                             lambda k=k: self._answer(i, k), align="left", scale=0.038)
            self.quiz_btns.append(b)
        self.quiz_continue = self._button(f, tr("skip"), (0.48, -0.54), 0.24, self._close_quiz)

    def _answer(self, i, k):
        q = self.steps[i].quiz
        if i in self.quiz_results:
            return
        ok = k == q.answer
        self.quiz_results[i] = ok
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
        if self.quiz_frame:
            self.quiz_frame.destroy()
            self.quiz_frame = None
        if self.resume_after_quiz and self.step < len(self.steps) - 1:
            self.playing = True
            self.play_wait = 0.3
        self._refresh_play_btn()

    # ================================================================= UI helpers
    def _button(self, parent, text, pos, width, cmd, on=False, align="center", scale=0.032, height=None):
        h = height or scale * 1.75
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
        """Greedy line wrap measured with the real font; CJK may break anywhere."""
        if not hasattr(self, "_measure"):
            self._measure = TextNode("measure")
            if self.font:
                self._measure.setFont(self.font)
        tokens = re.findall(r"[A-Za-z0-9_.,;:!?%()'\"<>/+\-=~°µ^]+|\s|.", text)
        lines, cur = [], ""
        limit = width / scale
        for tok in tokens:
            if tok == "\n":
                lines.append(cur)
                cur = ""
                continue
            if cur and self._measure.calcWidth(cur + tok) > limit:
                lines.append(cur.rstrip())
                cur = "" if tok.isspace() else tok
            else:
                cur += tok
        lines.append(cur)
        return "\n".join(lines)

    def _text(self, parent, text, pos, scale=0.032, fg=TXT, wrap=None, align="left"):
        if wrap:
            text = self.wrap(text, wrap, scale)
        return OnscreenText(parent=parent, text=text, pos=pos, scale=scale, fg=fg, mayChange=True,
                            align=TextNode.ALeft if align == "left" else
                            (TextNode.ARight if align == "right" else TextNode.ACenter),
                            )

    def _slider(self, parent, pos, width, value, cmd):
        s = DirectSlider(parent=parent, range=(0, 1), value=value, pageSize=0.05,
                         pos=(pos[0], 0, pos[1]), frameSize=(0, width, -0.008, 0.008),
                         frameColor=(0.3, 0.32, 0.37, 1), relief=DGG.FLAT,
                         thumb_frameSize=(-0.014, 0.014, -0.026, 0.026), thumb_relief=DGG.FLAT,
                         thumb_frameColor=(0.55, 0.70, 0.95, 1), command=cmd)
        return s

    def _clear_ui(self):
        for r in self.ui_roots:
            r.destroy()
        self.ui_roots = []

    def rebuild_ui(self):
        self._clear_ui()
        self.build_ui()
        self.refresh_ui()

    # ================================================================= UI build
    def build_ui(self):
        self._build_left()
        self._build_right()

    def _build_left(self):
        f = DirectFrame(parent=self.a2dTopLeft, frameColor=PANEL, frameSize=(0, LEFT_W, -2.0, 0))
        self.ui_roots.append(f)
        self._text(f, tr("app_title"), (0.03, -0.075), 0.052, ACCENT)
        self._text(f, i18n.pick(*self.flow.node), (0.03, -0.118), 0.024, TXT2, wrap=LEFT_W - 0.06)
        self.flow_btns = {}
        keys = list(FLOWS)
        fw = (LEFT_W - 0.06 - 0.01 * (len(keys) - 1)) / len(keys)
        for k, key in enumerate(keys):
            self.flow_btns[key] = self._button(
                f, i18n.pick(*FLOWS[key].name), (0.03 + fw / 2 + k * (fw + 0.01), -0.205), fw,
                lambda key=key: self.set_flow(key), on=key == self.flow.key, scale=0.029)

        n = len(self.steps)
        row = 0.05
        sf = DirectScrolledFrame(parent=f, frameSize=(0.02, LEFT_W - 0.02, -1.0, -0.245),
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
        for i, st in enumerate(self.steps):
            b = self._button(canvas, f"{i + 1:02d}  {i18n.pick(*st.title)}", (0.005, -(i + 0.6) * row),
                             LEFT_W - 0.085, lambda i=i: self.jump_to(i), align="left", scale=0.03,
                             height=row * 0.95)
            self.step_btns.append(b)

        y = -1.06
        self._button(f, tr("prev"), (0.14, y), 0.22, self.prev_step)
        self.play_btn = self._button(f, tr("play"), (0.37, y), 0.22, self.toggle_play)
        self._button(f, tr("next"), (0.60, y), 0.22, self.next_step)
        y -= 0.075
        self._button(f, tr("reset"), (0.20, y), 0.34, lambda: self.goto(0))
        self._button(f, tr("to_end"), (0.55, y), 0.34, lambda: self.goto(len(self.steps) - 1))
        y -= 0.075
        self.speed_text = self._text(f, tr("speed", v=self.speed), (0.04, y), 0.028, TXT2)
        self.speed_slider = self._slider(f, (0.36, y + 0.01), 0.34, (self.speed - 0.25) / 2.75, self._set_speed)

        y -= 0.085
        self._text(f, tr("view"), (0.03, y), 0.034, ACCENT)
        y -= 0.06
        self.cut_btn = self._button(f, tr("cut"), (0.20, y), 0.34, self._toggle_cut, on=self.cut_on)
        self.edge_btn = self._button(f, tr("edges"), (0.55, y), 0.34, self._toggle_edges, on=self.scene.edges)
        y -= 0.065
        self.cut_text = self._text(f, tr("cut_pos", v=self.cut_y), (0.04, y), 0.028, TXT2)
        self.cut_slider = self._slider(f, (0.36, y + 0.01), 0.34, self.cut_y / 8.0, self._set_cut)
        y -= 0.07
        self.label_btn = self._button(f, tr("labels"), (0.20, y), 0.34, self._toggle_labels,
                                      on=self.scene.show_labels)
        self._button(f, tr("lang_btn"), (0.55, y), 0.34, self._toggle_lang)
        y -= 0.07
        for k, (key, xx) in enumerate((("cam_iso", 0.14), ("cam_front", 0.37), ("cam_top", 0.60))):
            self._button(f, tr(key), (xx, y), 0.22, lambda key=key: self.set_cam(key[4:]))
        y -= 0.085
        self.quiz_btn = self._button(f, tr("quiz_mode"), (0.20, y), 0.34, self._toggle_quiz,
                                     on=self.quiz_enabled)
        self.score_text = self._text(f, "", (0.40, y - 0.01), 0.03, TXT2)
        self._text(f, tr("mouse_hint"), (0.03, -1.93), 0.026, TXT2, wrap=LEFT_W - 0.06)

    def _build_right(self):
        f = DirectFrame(parent=self.a2dTopRight, frameColor=PANEL, frameSize=(-RIGHT_W, 0, -2.0, 0))
        self.ui_roots.append(f)
        x0 = -RIGHT_W + 0.03
        self.tab_btns = {}
        for k, key in enumerate(("process", "elec", "params")):
            tw = (RIGHT_W - 0.08) / 3
            self.tab_btns[key] = self._button(
                f, tr({"process": "tab_process", "elec": "tab_elec", "params": "tab_params"}[key]),
                (x0 + tw / 2 + k * (tw + 0.01), -0.065), tw, lambda key=key: self._set_tab(key),
                on=self.right_tab == key, scale=0.034)

        # ---- process tab
        pt = DirectFrame(parent=f, frameColor=(0, 0, 0, 0))
        self.tab_process = pt
        self.step_no_text = self._text(pt, "", (x0, -0.16), 0.03, TXT2)
        self.title_text = self._text(pt, "", (x0, -0.225), 0.048, TXT)
        self.caption_text = self._text(pt, "", (x0, -0.285), 0.032, ACCENT)
        self.desc_text = self._text(pt, "", (x0, -0.35), 0.031, TXT)
        self.params_frame = DirectFrame(parent=pt, frameColor=(0, 0, 0, 0))
        self.legend_frame = DirectFrame(parent=pt, frameColor=(0, 0, 0, 0))

        # ---- electrical tab
        et = DirectFrame(parent=f, frameColor=(0, 0, 0, 0))
        self.tab_elec = et
        self.plot_btns = {}
        kinds = (("idvg", "plot_idvg"), ("idvd", "plot_idvd"), ("vtc", "plot_vtc"), ("tran", "plot_tran"))
        bw = (RIGHT_W - 0.09) / 4
        for k, (kind, key) in enumerate(kinds):
            self.plot_btns[kind] = self._button(et, tr(key), (x0 + bw / 2 + k * (bw + 0.01), -0.15), bw,
                                                lambda kind=kind: self._set_plot(kind),
                                                on=self.plot_kind == kind, scale=0.03)
        pw = RIGHT_W - 0.05
        ph = pw * PLOT_H / PLOT_W
        self.plot_img = OnscreenImage(parent=et, image=self.plot_tex, pos=(-RIGHT_W / 2, 0, -0.2 - ph / 2),
                                      scale=(pw / 2, 1, ph / 2))
        y = -0.2 - ph - 0.06
        self.vin_text = self._text(et, tr("vin", v=self.vin), (x0, y), 0.03, TXT)
        self.vin_slider = self._slider(et, (x0 + 0.40, y + 0.01), RIGHT_W - 0.48,
                                       self.vin / self.params.vdd, self.set_vin)
        y -= 0.08
        self.sim_btn = self._button(et, tr("sim3d"), (x0 + 0.21, y), 0.42, self.toggle_sim3d, on=self.sim3d)
        self._button(et, tr("play_tran"), (x0 + 0.66, y), 0.40, self.play_transient)
        y -= 0.06
        self.sim_note = self._text(et, "", (x0, y), 0.026, TXT2)
        y -= 0.06
        self.metrics_text = self._text(et, "", (x0, y), 0.029, TXT)
        self.metrics_text2 = self._text(et, "", (x0 + RIGHT_W / 2, y), 0.029, TXT)

        # ---- params tab
        pa = DirectFrame(parent=f, frameColor=(0, 0, 0, 0))
        self.tab_params = pa
        y = -0.17
        self.param_widgets = []
        for key, lkey, lo, hi, log in PARAM_SLIDERS:
            v = getattr(self.params, key)
            if log:
                x = (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
                txt = tr(lkey, v=sci(v, "cm^-3" if key == "na_cm3" else "cm^-2"))
            else:
                x = (v - lo) / (hi - lo)
                txt = tr(lkey, v=v)
            lab = self._text(pa, txt, (x0, y), 0.03, TXT)
            sl = self._slider(pa, (x0, y - 0.045), RIGHT_W - 0.08, min(max(x, 0), 1), None)
            sl["command"] = (lambda key=key, lo=lo, hi=hi, log=log, sl=sl, lab=lab, lkey=lkey:
                             self.set_param(key, lo, hi, log, sl, lab, lkey))
            self.param_widgets.append(sl)
            y -= 0.125
        self._button(pa, tr("restore"), (x0 + 0.15, y + 0.02), 0.30, self.reset_params)
        y -= 0.07
        self._text(pa, tr("extracted"), (x0, y), 0.032, ACCENT)
        self.extract_text = self._text(pa, "", (x0, y - 0.055), 0.028, TXT)
        self.extract_text2 = self._text(pa, "", (x0 + RIGHT_W / 2, y - 0.055), 0.028, TXT)

    # ================================================================= UI callbacks
    def _set_tab(self, key):
        self.right_tab = key
        self.plot_dirty = True
        self.refresh_ui()

    def _set_plot(self, kind):
        self.plot_kind = kind
        self.plot_dirty = True
        self.refresh_ui()

    def _set_speed(self):
        self.speed = 0.25 + float(self.speed_slider["value"]) * 2.75
        self.speed_text.setText(tr("speed", v=self.speed))

    def _toggle_cut(self):
        self.cut_on = not self.cut_on
        self.scene.set_cut(self.cut_y if self.cut_on else 0.0)
        self._apply_sim()
        self.refresh_ui()

    def _set_cut(self):
        self.cut_y = float(self.cut_slider["value"]) * 7.6 + 0.2
        self.cut_text.setText(tr("cut_pos", v=self.cut_y))
        if self.cut_on:
            self.scene.set_cut(self.cut_y)
            self.scene._rebuild_channels()

    def _toggle_edges(self):
        self.scene.set_edges(not self.scene.edges)
        self.refresh_ui()

    def _toggle_labels(self):
        self.scene.set_labels(not self.scene.show_labels)
        self.refresh_ui()

    def _toggle_lang(self):
        if not self.font:
            return
        i18n.set_lang("en" if i18n.LANG == "zh" else "zh")
        self.rebuild_ui()
        self.scene.rebuild_labels()
        self.plot_dirty = True

    def _toggle_quiz(self):
        self.quiz_enabled = not self.quiz_enabled
        self.refresh_ui()

    def _refresh_play_btn(self):
        if hasattr(self, "play_btn"):
            self.play_btn["text"] = tr("pause") if self.playing else tr("play")
            self._set_on(self.play_btn, self.playing)

    @staticmethod
    def _set_on(btn, on):
        btn["frameColor"] = (BTN_ON if on else BTN, BTN_PRESS, BTN_ON if on else BTN_HOVER, BTN)

    def _refresh_caption(self):
        if not hasattr(self, "caption_text"):
            return
        if self.anim_step is not None and self.caption[0]:
            self.caption_text.setText("→ " + i18n.pick(*self.caption))
        else:
            self.caption_text.setText(tr("phase_done") if self.step >= 0 else "")

    # ================================================================= refresh
    def refresh_ui(self):
        if not hasattr(self, "step_btns"):
            return
        cur = self.anim_step if self.anim_step is not None else self.step
        for i, b in enumerate(self.step_btns):
            if i == cur:
                col = BTN_ON
            elif i < cur or (i == cur and self.anim_step is None):
                col = DONE_COL
            else:
                col = BTN
            b["frameColor"] = (col, BTN_PRESS, BTN_HOVER, BTN)
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
        self._set_on(self.sim_btn, self.sim3d)
        n_ok = sum(1 for v in self.quiz_results.values() if v)
        self.score_text.setText(tr("score", ok=n_ok, n=len(self.quiz_results)) if self.quiz_enabled else "")

        self.tab_process.show() if self.right_tab == "process" else self.tab_process.hide()
        self.tab_elec.show() if self.right_tab == "elec" else self.tab_elec.hide()
        self.tab_params.show() if self.right_tab == "params" else self.tab_params.hide()

        # ---- process tab
        st = self.steps[max(cur, 0)]
        self.step_no_text.setText(tr("step_n", i=max(cur, 0) + 1, n=len(self.steps)))
        self.title_text.setText(i18n.pick(*st.title))
        self._refresh_caption()
        self.desc_text.setText(self.wrap(i18n.pick(*st.desc), RIGHT_W - 0.07, 0.031))
        tn = self.desc_text.textNode
        y = -0.35 - tn.getNumRows() * tn.getLineHeight() * 0.031 - 0.03
        for c in self.params_frame.getChildren():
            c.removeNode()
        self._text(self.params_frame, tr("params"), (-RIGHT_W + 0.03, y), 0.034, ACCENT)
        y -= 0.055
        for zh, en, fn in st.params:
            self._text(self.params_frame, i18n.pick(zh, en), (-RIGHT_W + 0.05, y), 0.029, TXT2)
            self._text(self.params_frame, fn(self.ctx), (-0.03, y), 0.029, TXT, align="right")
            y -= 0.045
        y -= 0.04
        for c in self.legend_frame.getChildren():
            c.removeNode()
        self._text(self.legend_frame, tr("legend"), (-RIGHT_W + 0.03, y), 0.034, ACCENT)
        y -= 0.055
        mats = []
        if self.wafer:
            for lay in self.wafer.layers.values():
                if lay.solids and lay.material not in mats and MATERIALS[lay.material].legend:
                    mats.append(lay.material)
        colw = (RIGHT_W - 0.06) / 2
        for k, m in enumerate(mats):
            cx = -RIGHT_W + 0.04 + (k % 2) * colw
            cy = y - (k // 2) * 0.05
            col = mat(m).color
            DirectFrame(parent=self.legend_frame, frameColor=(col[0], col[1], col[2], 1),
                        frameSize=(0, 0.035, -0.008, 0.022), pos=(cx, 0, cy))
            self._text(self.legend_frame, i18n.pick(mat(m).zh, mat(m).en), (cx + 0.05, cy), 0.026, TXT2)

        # ---- electrical
        s = summarize_cached(self.params, self.flow.features)
        p = self.params
        if self.vin > p.vdd:
            self.vin = p.vdd
        self.vin_text.setText(tr("vin", v=self.vin))
        self.sim_note.setText("" if self.is_done() else tr("sim_need_done"))
        r = s.vtc
        self.metrics_text.setText(
            f"Vtn = {s.vtn:+.3f} V\nVtp = {s.vtp:+.3f} V\n"
            f"Idsat,n = {s.idsat_n * 1e3:.3f} mA\nIdsat,p = {s.idsat_p * 1e3:.3f} mA\n"
            f"Ioff,n = {s.ioff_n:.2e} A")
        self.metrics_text2.setText(
            f"VM = {r.vm:.3f} V\nNMH = {r.nmh:.2f} V\nNML = {r.nml:.2f} V\n"
            f"tpHL = {s.tran.tphl * 1e12:.1f} ps\ntpLH = {s.tran.tplh * 1e12:.1f} ps")
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
        self.plot_dirty = True
