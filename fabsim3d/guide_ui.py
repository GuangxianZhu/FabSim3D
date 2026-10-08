"""Guide mode UI: lesson list, task cards with embedded controls, step tips.

Mixed into CmosApp; relies on its helpers (_button, _text, _slider, wrap, set_param ...).
"""
from __future__ import annotations

import math
import time

from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenImage import OnscreenImage

from . import i18n
from .i18n import tr
from .lessons import LESSONS, STEP_TIPS, LabState, LessonRunner

ACCENT = (1.0, 0.82, 0.35, 1)
TXT = (0.93, 0.93, 0.93, 1)
TXT2 = (0.70, 0.71, 0.74, 1)
GOOD = (0.45, 0.90, 0.55, 1)
TRY = (1.0, 0.86, 0.45, 1)
BLINK_A = (1.0, 0.80, 0.25, 1)


class GuideMixin:
    # ------------------------------------------------------------------ state
    def _guide_init(self):
        self.guide_mode = False
        self.runner: LessonRunner | None = None
        self.lessons_done = set()
        self.lab_ack = False
        self.lab_tran = False
        self.guide_deep = False
        self.guide_blink = []           # (widget, kind) to blink
        self.guide_last_poll = 0.0
        self.tab_guide = None

    def lab_state(self) -> LabState:
        return LabState(self.flow.key, self.flow.features, self.is_done(), self.params.copy(),
                        self.vin, self.plot_kind, self.lab_tran, self.lab_ack)

    @property
    def guide_ref(self):
        """(params, features) of the 'before' curve for the current task, if it differs."""
        if not self.runner or self.right_tab != "guide":
            return None
        ref = self.runner.reference
        if ref is None or ref.flow != self.flow.key or vars(ref.p) == vars(self.params):
            return None
        return (ref.p, ref.features)

    # ------------------------------------------------------------------ mode / lessons
    def toggle_guide(self):
        self.guide_mode = not self.guide_mode
        if self.guide_mode:
            self.right_tab = "guide"
        elif self.right_tab == "guide":
            self.right_tab = "process"
        self.rebuild_ui()

    def start_lesson(self, lesson):
        if lesson.flow != self.flow.key:
            self.set_flow(lesson.flow)
        else:
            self.params = self.flow.default_params()
            self.vin = self.params.vdd / 2
        self.goto(len(self.steps) - 1)
        if lesson.sim3d and not self.sim3d:
            self.toggle_sim3d()
        self.runner = LessonRunner(lesson)
        self._enter_task(0)

    def stop_lesson(self):
        self.runner = None
        self._build_guide_page()
        self.plot_dirty = True

    def _enter_task(self, idx):
        self.lab_ack = False
        self.lab_tran = False
        self.guide_deep = False
        self.runner.go(idx, self.lab_state())
        if self.runner.task.plot:
            self.plot_kind = self.runner.task.plot
        self._build_guide_page()
        self.refresh_ui()
        self.plot_dirty = True

    def guide_next(self):
        if not self.runner:
            return
        if self.runner.idx < len(self.runner.lesson.tasks) - 1:
            self._enter_task(self.runner.idx + 1)
        elif self.runner.finished:
            self.lessons_done.add(self.runner.lesson.key)
            self._build_guide_page()

    def guide_prev(self):
        if self.runner and self.runner.idx > 0:
            self._enter_task(self.runner.idx - 1)

    def guide_demo(self):
        """'Do it for me': apply the task's demo action through the normal UI paths."""
        if not self.runner or not self.runner.task.demo:
            return
        d = self.runner.task.demo(self.lab_state())
        if "params" in d:
            for k, v in d["params"].items():
                setattr(self.params, k, v)
            self.vin = min(self.vin, self.params.vdd)
            self._commit_params()
        if "vin" in d:
            self.vin = float(d["vin"])
            self.plot_dirty = True
            self._apply_sim()
        if d.get("tran"):
            self.play_transient()
        if d.get("ack"):
            self.lab_ack = True
        self._sync_controls()
        self._poll_guide(force=True)

    def guide_ack(self):
        self.lab_ack = True
        self._poll_guide(force=True)

    # ------------------------------------------------------------------ polling / blink
    def _poll_guide(self, force=False):
        if not self.runner:
            return
        now = time.time()
        if not force and now - self.guide_last_poll < 0.15:
            return
        self.guide_last_poll = now
        if self.runner.poll(self.lab_state()):
            obs = self.runner.observation()
            if obs is not None and not obs[0] and not obs[1]:
                self.guide_next()           # intro card: go straight on
            else:
                if self.runner.finished:
                    self.lessons_done.add(self.runner.lesson.key)
                self._build_guide_page()

    def _guide_tick(self):
        if self.runner and self.guide_mode:
            self._poll_guide()
        if not self.guide_blink:
            return
        on = math.sin(time.time() * 6.0) > 0
        for w, kind, base in self.guide_blink:
            if w.isEmpty():
                continue
            col = BLINK_A if on else base
            if kind == "slider":
                w["thumb_frameColor"] = col
            else:
                w["frameColor"] = (col, col, col, col)

    # ------------------------------------------------------------------ controls
    def _sync_controls(self):
        """Move every slider (params tab, elec tab, guide page) to the current values."""
        from .app import PARAM_SLIDERS
        for sl, (key, _lk, lo, hi, log) in zip(getattr(self, "param_widgets", []),
                                               self.flow.sliders or PARAM_SLIDERS):
            sl["value"] = _to_unit(getattr(self.params, key), lo, hi, log)
        if hasattr(self, "vin_slider"):
            self.vin_slider["value"] = self.vin / self.params.vdd
        if self.runner and self.tab_guide is not None:
            self._build_guide_page()

    def _guide_vin_changed(self, slider, label):
        v = float(slider["value"]) * self.params.vdd
        if abs(v - self.vin) < 1e-6:
            return
        self.vin = v
        label.setText(tr("vin", v=v))
        self.plot_dirty = True
        if self.tran_t is None:
            self._apply_sim()

    # ------------------------------------------------------------------ building
    def _build_guide_tab(self, parent):
        self.tab_guide = DirectFrame(parent=parent, frameColor=(0, 0, 0, 0))
        self._build_guide_page()

    def _build_guide_page(self):
        if self.tab_guide is None or self.tab_guide.isEmpty():
            return
        for c in self.tab_guide.getChildren():
            c.removeNode()
        self.guide_blink = []
        if self.runner:
            self._build_task_card()
        else:
            self._build_lesson_list()

    def _build_lesson_list(self):
        from .app import RIGHT_W
        f = self.tab_guide
        x0 = -RIGHT_W + 0.03
        w = RIGHT_W - 0.06
        self._text(f, tr("guide_lessons"), (x0, -0.17), 0.04, ACCENT)
        y = -0.23
        intro = self._text(f, tr("guide_intro"), (x0, y), 0.028, TXT2, wrap=w)
        y -= _h(intro) + 0.04
        for lesson in LESSONS:
            done = lesson.key in self.lessons_done
            title = i18n.pick(*lesson.title) + ("   " + tr("guide_done_mark") if done else "")
            self._button(f, title, (x0, y), w, lambda l=lesson: self.start_lesson(l),
                         align="left", scale=0.034, height=0.07, on=done)
            sub = self._text(f, i18n.pick(*lesson.summary), (x0 + 0.02, y - 0.065), 0.026, TXT2, wrap=w - 0.04)
            y -= 0.07 + _h(sub) + 0.04
        y -= 0.02
        self._text(f, tr("guide_tip_note"), (x0, y), 0.026, TXT2, wrap=w)

    def _build_task_card(self):
        from .app import PARAM_SLIDERS, RIGHT_W, PLOT_W, PLOT_H
        f = self.tab_guide
        r = self.runner
        t = r.task
        x0 = -RIGHT_W + 0.03
        w = RIGHT_W - 0.06
        y = -0.155
        self._button(f, tr("guide_back"), (x0, y), 0.22, self.stop_lesson, align="left", scale=0.026)
        self._text(f, i18n.pick(*r.lesson.title), (x0 + 0.25, y - 0.005), 0.032, ACCENT)
        y -= 0.07
        # progress boxes
        n = len(r.lesson.tasks)
        bw = min(0.06, (w - 0.3) / n)
        for k in range(n):
            col = (0.25, 0.65, 0.35, 1) if r.done[k] else ((0.25, 0.5, 0.9, 1) if k == r.idx else (0.3, 0.31, 0.35, 1))
            DirectFrame(parent=f, frameColor=col, frameSize=(0, bw - 0.008, -0.012, 0.012),
                        pos=(x0 + k * bw, 0, y + 0.012))
        self._text(f, tr("guide_task", i=r.idx + 1, n=n) + "  " + i18n.pick(*t.title),
                   (x0 + n * bw + 0.02, y), 0.03, TXT)
        y -= 0.06
        body = i18n.pick(*t.explain)
        if self.guide_deep and t.deep:
            body += "\n" + tr("guide_deep_prefix") + i18n.pick(*t.deep)
        ex = self._text(f, body, (x0, y), 0.027, TXT, wrap=w)
        y -= _h(ex)
        if t.deep:
            y -= 0.02
            self._button(f, tr("guide_deep_off") if self.guide_deep else tr("guide_deep_on"),
                         (x0 + w - 0.24, y), 0.24, self._toggle_deep, align="left", scale=0.024)
            y -= 0.04
        y -= 0.02
        tr_txt = self._text(f, tr("guide_try") + i18n.pick(*t.try_), (x0, y), 0.029, TRY, wrap=w)
        y -= _h(tr_txt) + 0.02
        done = r.done[r.idx]
        # embedded controls
        specs = {k: (lk, lo, hi, log) for k, lk, lo, hi, log in self.flow.sliders or PARAM_SLIDERS}
        for c in t.controls:
            if c.startswith("param:"):
                key = c[6:]
                lk, lo, hi, log = specs[key]
                v = getattr(self.params, key)
                lab = self._text(f, _param_text(key, lk, v, log), (x0, y), 0.028, TXT)
                sl = self._slider(f, (x0, y - 0.045), w, _to_unit(v, lo, hi, log), None)
                sl["command"] = (lambda key=key, lo=lo, hi=hi, log=log, sl=sl, lab=lab, lk=lk:
                                 self.set_param(key, lo, hi, log, sl, lab, lk))
                if not done:
                    self.guide_blink.append((sl, "slider", (0.55, 0.70, 0.95, 1)))
                y -= 0.1
            elif c == "vin":
                lab = self._text(f, tr("vin", v=self.vin), (x0, y), 0.028, TXT)
                sl = self._slider(f, (x0, y - 0.045), w, self.vin / self.params.vdd, None)
                sl["command"] = lambda sl=sl, lab=lab: self._guide_vin_changed(sl, lab)
                if not done:
                    self.guide_blink.append((sl, "slider", (0.55, 0.70, 0.95, 1)))
                y -= 0.1
            elif c in ("btn:tran", "btn:ack"):
                label = tr("play_tran") if c == "btn:tran" else (
                    tr("guide_start") if r.idx == 0 else tr("guide_seen"))
                b = self._button(f, label, (x0 + 0.2, y - 0.01), 0.4,
                                 self.play_transient if c == "btn:tran" else self.guide_ack)
                if not done:
                    self.guide_blink.append((b, "button", (0.20, 0.21, 0.25, 1)))
                y -= 0.08
        if not done and t.demo and r.idx > 0:
            self._button(f, tr("guide_demo"), (x0 + w - 0.15, y + 0.01), 0.3, self.guide_demo, scale=0.026)
            y -= 0.06
        # plot
        if t.plot:
            pw = w
            ph = pw * PLOT_H / PLOT_W
            OnscreenImage(parent=f, image=self.plot_tex, pos=(x0 + pw / 2, 0, y - ph / 2),
                          scale=(pw / 2, 1, ph / 2))
            y -= ph + 0.03
        # observation
        if done:
            obs = r.observation()
            if obs and (obs[0] or obs[1]):
                o = self._text(f, tr("guide_seen_head") + i18n.pick(*obs), (x0, y), 0.027, GOOD, wrap=w)
                y -= _h(o) + 0.02
        # navigation
        y = min(y, -1.86)
        y = max(y, -1.93)
        if r.idx > 0:
            self._button(f, tr("guide_prev"), (x0 + 0.13, y), 0.26, self.guide_prev, scale=0.028)
        last = r.idx == len(r.lesson.tasks) - 1
        if done:
            if last:
                self._text(f, tr("guide_finished"), (x0 + w - 0.02, y - 0.01), 0.03, GOOD, align="right")
            elif r.idx > 0:
                nb = self._button(f, tr("guide_next"), (x0 + w - 0.15, y), 0.3, self.guide_next, scale=0.028)
                self.guide_blink.append((nb, "button", (0.20, 0.45, 0.82, 1)))

    def _toggle_deep(self):
        self.guide_deep = not self.guide_deep
        self._build_guide_page()

    # ------------------------------------------------------------------ step tips
    def step_tip(self, step) -> str | None:
        if not self.guide_mode:
            return None
        tip = STEP_TIPS.get(step.key)
        return i18n.pick(*tip) if tip else None


def _rows(ost) -> int:
    return max(1, ost.textNode.getText().count("\n") + 1)


def _h(ost) -> float:
    """Height in parent units actually taken by a (wrapped) OnscreenText block."""
    tn = ost.textNode
    return _rows(ost) * tn.getLineHeight() * ost.getScale()[0]


def _to_unit(v, lo, hi, log):
    if log:
        return min(max((math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)), 0.0), 1.0)
    return min(max((v - lo) / (hi - lo), 0.0), 1.0)


def _param_text(key, lk, v, log):
    from .process_core import sci
    if log:
        return tr(lk, v=sci(v, "cm^-3" if key == "na_cm3" else "cm^-2"))
    return tr(lk, v=v, nm=v * 1e3)
