"""Guide mode UI: lesson list, task cards with embedded controls, step tips.

Mixed into CmosApp; relies on its helpers (_button, _text, _slider, wrap, set_param ...).

【中文说明：这个文件是干什么的？】
这里实现"引导模式"（教学模式）的界面，也就是右侧面板里的"课程"标签页：
* 课程列表：列出所有课程，点一个就开始学；
* 任务卡片：每节课分成若干小任务，卡片上有说明文字、"试一试"提示、
  可以直接拖动的滑块/按钮、示意图，以及完成后的"你观察到了什么"解释；
* 步骤提示：在 3D 工艺动画的每一步旁边显示一条小贴士。

它和程序其他部分的关系：
* 课程内容（文字、检查条件）写在 lessons 包里；这里只负责"显示"和"交互"。
* 本文件定义的 GuideMixin 是一个"混入类(Mixin)"：它自己不能单独运行，
  而是被主程序类 CmosApp（在 app.py 里）继承，相当于把这些方法"拼"进主程序。
  因此代码里的 self 指的就是整个主程序，可以直接用主程序提供的 _button（建按钮）、
  _text（写文字）、_slider（建滑块）、set_param（修改工艺参数）等工具函数。
* 界面用的是 Panda3D 自带的 DirectGui 控件库。屏幕坐标：x 向右为正，y 向上为正，
  所以往下排版时 y 不断减小（代码里大量出现 y -= ...）。
"""
# 中文：允许在类型标注里使用较新的写法（如 `LessonRunner | None`，表示"要么是它，要么是空"）。
from __future__ import annotations

import math   # 中文：数学函数（这里用到 sin 做闪烁、log10 做对数滑块）
import time   # 中文：读取当前时间（控制轮询频率和闪烁节奏）

# 中文：Panda3D 的界面控件：DirectFrame 是一个矩形"框/面板"，OnscreenImage 在屏幕上显示一张图片。
from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenImage import OnscreenImage

# 中文：i18n = 多语言（中/英）支持；tr("键名") 根据当前语言取出对应的界面文字。
from . import i18n
from .i18n import tr
# 中文：从课程包导入：所有课程 LESSONS、工艺步骤小贴士 STEP_TIPS、
#       实验状态快照 LabState、负责推进课程进度的 LessonRunner。
from .lessons import LESSONS, STEP_TIPS, LabState, LessonRunner

# 中文：界面颜色，格式 (红, 绿, 蓝, 不透明度)，每个数在 0~1 之间。
ACCENT = (1.0, 0.82, 0.35, 1)     # 中文：强调色（金黄），用于标题
TXT = (0.93, 0.93, 0.93, 1)       # 中文：普通正文（接近白色）
TXT2 = (0.70, 0.71, 0.74, 1)      # 中文：次要文字（灰色）
GOOD = (0.45, 0.90, 0.55, 1)      # 中文：完成/正确（绿色）
TRY = (1.0, 0.86, 0.45, 1)        # 中文："试一试"提示文字
BLINK_A = (1.0, 0.80, 0.25, 1)    # 中文：闪烁时的高亮色，提醒学生"该操作这个了"


class GuideMixin:
    """中文：引导模式的全部界面逻辑，作为"混入类"被主程序 CmosApp 继承。
    为什么单独成类：把教学相关的代码和主程序其余部分分开，文件更短、更好维护。
    """
    # ------------------------------------------------------------------ state
    # 中文：======== 状态（引导模式需要记住的数据） ========
    def _guide_init(self):
        """中文：初始化引导模式用到的所有变量。主程序启动时调用一次。"""
        self.guide_mode = False         # 中文：当前是否处于引导模式
        self.runner: LessonRunner | None = None   # 中文：正在进行的课程（没有则为 None）
        self.lessons_done = set()       # 中文：已完成课程的编号集合（用于在列表里打勾）
        self.lab_ack = False            # 中文：学生是否点了"我看到了/开始"按钮
        self.lab_tran = False           # 中文：学生是否播放过瞬态（开关过程）动画
        self.guide_deep = False         # 中文：是否展开"深入讲解"（公式级解释）
        self.guide_blink = []           # (widget, kind) to blink
        # 中文：↑ 需要闪烁提示的控件列表，每项是 (控件, 类型"slider"/"button", 原本的颜色)
        self.guide_last_poll = 0.0      # 中文：上次检查任务是否完成的时间
        self.tab_guide = None           # 中文：课程标签页的容器面板（还没建好时为 None）

    def lab_state(self) -> LabState:
        """中文：给当前"实验室"拍一张快照：用的哪种工艺流程、工艺是否已做完、参数、
        输入电压、正在看哪张图、是否播放过瞬态、是否点过确认。
        课程系统拿这张快照去判断"学生是否完成了任务"。
        params.copy() 复制一份，避免之后修改参数时把快照也改掉。
        """
        return LabState(self.flow.key, self.flow.features, self.is_done(), self.params.copy(),
                        self.vin, self.plot_kind, self.lab_tran, self.lab_ack)

    # 中文：@property 让下面的方法可以像变量一样读取：写 self.guide_ref，不用加括号。
    @property
    def guide_ref(self):
        """(params, features) of the 'before' curve for the current task, if it differs.

        中文：返回"改动之前"的参数，用来在图上画一条灰色参考曲线，方便学生对比前后变化。
        以下情况返回 None（不画参考线）：没有在上课、当前不在课程标签页、
        这个任务不需要对比、换了工艺流程、或者参数根本没变（两条线会重合，没有意义）。
        """
        if not self.runner or self.right_tab != "guide":
            return None
        ref = self.runner.reference
        # 中文：vars(对象) 把对象的所有字段变成字典，便于整体比较"参数是否完全相同"。
        if ref is None or ref.flow != self.flow.key or vars(ref.p) == vars(self.params):
            return None
        return (ref.p, ref.features)

    # ------------------------------------------------------------------ mode / lessons
    # 中文：======== 开关引导模式、开始/结束课程、切换任务 ========
    def toggle_guide(self):
        """中文：打开/关闭引导模式。打开时自动切到"课程"标签页；关闭时退回"工艺"标签页。"""
        self.guide_mode = not self.guide_mode
        if self.guide_mode:
            self.right_tab = "guide"
        elif self.right_tab == "guide":
            self.right_tab = "process"
        # 中文：界面布局变了，整体重建一次。
        self.rebuild_ui()

    def start_lesson(self, lesson):
        """中文：开始一节课：先把实验环境准备好，再进入第 1 个任务。"""
        # 中文：如果这节课要求的工艺流程和当前的不同，先切换流程；
        #       否则把参数恢复为默认值，输入电压放在 VDD 的一半（反相器的中间点）。
        if lesson.flow != self.flow.key:
            self.set_flow(lesson.flow)
        else:
            self.params = self.flow.default_params()
            self.vin = self.params.vdd / 2
        # 中文：跳到工艺的最后一步，即"芯片已经做好"，这样才有晶体管可以测。
        self.goto(len(self.steps) - 1)
        # 中文：如果课程需要 3D 仿真视图而当前没开，就帮学生打开。
        if lesson.sim3d and not self.sim3d:
            self.toggle_sim3d()
        self.runner = LessonRunner(lesson)
        self._enter_task(0)

    def stop_lesson(self):
        """中文：退出当前课程，回到课程列表。plot_dirty=True 表示"图需要重画"。"""
        self.runner = None
        self._build_guide_page()
        self.plot_dirty = True

    def _enter_task(self, idx):
        """中文：进入第 idx 个任务（从 0 开始数）：清空上一个任务的操作记录，
        让课程系统记下"开始时的状态"（之后用来和现在比较），切到任务指定的图，再刷新界面。"""
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
        """中文："下一步"：还有后续任务就进入下一个；已是最后一个且全部完成，就把整节课记为已完成。"""
        if not self.runner:
            return
        if self.runner.idx < len(self.runner.lesson.tasks) - 1:
            self._enter_task(self.runner.idx + 1)
        elif self.runner.finished:
            self.lessons_done.add(self.runner.lesson.key)
            self._build_guide_page()

    def guide_prev(self):
        """中文："上一步"：回到前一个任务（已经在第一个就不动）。"""
        if self.runner and self.runner.idx > 0:
            self._enter_task(self.runner.idx - 1)

    def guide_demo(self):
        """'Do it for me': apply the task's demo action through the normal UI paths.

        中文："帮我做"按钮：自动执行任务要求的操作，给不会操作的学生演示。
        为什么要走"正常的界面路径"：这样效果和学生亲手拖滑块完全一样
        （图会刷新、滑块会移动、任务检查也照常进行）。
        demo 返回一个字典（键->值的对照表），可能包含：
          "params"：要修改的工艺参数；"vin"：要设置的输入电压；
          "tran"：是否播放瞬态动画；"ack"：是否相当于点了确认按钮。
        """
        if not self.runner or not self.runner.task.demo:
            return
        d = self.runner.task.demo(self.lab_state())
        # 中文：修改参数。setattr(对象, "字段名", 值) 等价于 对象.字段名 = 值，只是字段名可以用变量给出。
        #   改完后输入电压不能超过新的 VDD，然后"提交"参数让程序重新计算。
        if "params" in d:
            for k, v in d["params"].items():
                setattr(self.params, k, v)
            self.vin = min(self.vin, self.params.vdd)
            self._commit_params()
        # 中文：设置输入电压，并刷新图和 3D 仿真。
        if "vin" in d:
            self.vin = float(d["vin"])
            self.plot_dirty = True
            self._apply_sim()
        # 中文：d.get("键") 在键不存在时返回 None（视为"否"），不会报错。
        if d.get("tran"):
            self.play_transient()
        if d.get("ack"):
            self.lab_ack = True
        # 中文：让所有滑块移动到新数值，并立即检查任务是否完成。
        self._sync_controls()
        self._poll_guide(force=True)

    def guide_ack(self):
        """中文：学生点了"开始/我看到了"按钮：记下来，并立刻检查任务是否因此完成。"""
        self.lab_ack = True
        self._poll_guide(force=True)

    # ------------------------------------------------------------------ polling / blink
    # 中文：======== 轮询（定期检查任务完成情况）和闪烁提示 ========
    def _poll_guide(self, force=False):
        """中文：检查当前任务是否刚刚完成。
        为了不拖慢程序，平时最多每 0.15 秒检查一次；force=True 时立即检查。"""
        if not self.runner:
            return
        now = time.time()
        if not force and now - self.guide_last_poll < 0.15:
            return
        self.guide_last_poll = now
        # 中文：runner.poll 只在任务"刚好变成完成"的那一刻返回 True。
        if self.runner.poll(self.lab_state()):
            # 中文：obs = 完成后要显示的观察解释（中文, 英文）两段文字。
            #   如果两段都是空的，说明这是一张纯介绍卡片，没什么可解释的，直接进入下一个任务。
            obs = self.runner.observation()
            if obs is not None and not obs[0] and not obs[1]:
                self.guide_next()           # intro card: go straight on
            else:
                # 中文：如果整节课都完成了就记录下来；然后重建卡片，显示观察结果和"下一步"按钮。
                if self.runner.finished:
                    self.lessons_done.add(self.runner.lesson.key)
                self._build_guide_page()

    def _guide_tick(self):
        """中文：每一帧画面都会被调用一次（由主程序的定时任务驱动）。
        做两件事：定期检查任务；让需要提示的控件闪烁。"""
        if self.runner and self.guide_mode:
            self._poll_guide()
        if not self.guide_blink:
            return
        # 中文：用正弦函数 sin 随时间正负交替，得到"亮/暗"切换，每秒约闪一次。
        on = math.sin(time.time() * 6.0) > 0
        for w, kind, base in self.guide_blink:
            # 中文：控件可能已经被删除（界面重建了），跳过它。
            if w.isEmpty():
                continue
            col = BLINK_A if on else base
            # 中文：滑块只闪中间的拖动块(thumb)；按钮则整个闪。
            #   按钮的 frameColor 要给 4 个颜色，分别对应 普通/按下/悬停/禁用 四种状态。
            if kind == "slider":
                w["thumb_frameColor"] = col
            else:
                w["frameColor"] = (col, col, col, col)

    # ------------------------------------------------------------------ controls
    # 中文：======== 控件同步 ========
    def _sync_controls(self):
        """Move every slider (params tab, elec tab, guide page) to the current values.

        中文：参数被程序（而不是学生的手）改动后，把所有地方的滑块都挪到对应的新位置，
        保证界面显示和实际数值一致。
        """
        # 中文：在函数内部才导入 app 模块，是为了避免两个文件互相导入造成"循环导入"错误。
        from .app import PARAM_SLIDERS
        # 中文：zip 把两个列表一一配对：第 i 个滑块 <-> 第 i 个参数说明。
        #   参数说明是 (参数名, 标签文字键, 最小值, 最大值, 是否对数刻度)；_lk 前的下划线表示这里用不到它。
        #   getattr(self, "param_widgets", []) 取不到时用空列表代替（参数页还没建时）。
        for sl, (key, _lk, lo, hi, log) in zip(getattr(self, "param_widgets", []),
                                               self.flow.sliders or PARAM_SLIDERS):
            sl["value"] = _to_unit(getattr(self.params, key), lo, hi, log)
        # 中文：输入电压滑块的位置 = Vin / VDD（0~1 之间）。hasattr 检查这个滑块是否存在。
        if hasattr(self, "vin_slider"):
            self.vin_slider["value"] = self.vin / self.params.vdd
        # 中文：任务卡片里也嵌有滑块，最简单的办法是整张卡片重建。
        if self.runner and self.tab_guide is not None:
            self._build_guide_page()

    def _guide_vin_changed(self, slider, label):
        """中文：任务卡片里的输入电压滑块被拖动时调用：更新 Vin、更新文字标签、刷新图。"""
        v = float(slider["value"]) * self.params.vdd
        # 中文：变化小到可以忽略时什么也不做，避免无意义的重复计算。
        if abs(v - self.vin) < 1e-6:
            return
        self.vin = v
        label.setText(tr("vin", v=v))
        self.plot_dirty = True
        # 中文：如果没有正在播放的瞬态动画，就把新的 Vin 应用到 3D 仿真上。
        if self.tran_t is None:
            self._apply_sim()

    # ------------------------------------------------------------------ building
    # 中文：======== 构建界面（真正把文字、按钮、滑块摆到屏幕上） ========
    def _build_guide_tab(self, parent):
        """中文：创建"课程"标签页的空白容器（透明背景），再往里填内容。"""
        self.tab_guide = DirectFrame(parent=parent, frameColor=(0, 0, 0, 0))
        self._build_guide_page()

    def _build_guide_page(self):
        """中文：重建课程标签页的内容：先删掉旧内容，再根据是否在上课，
        显示"任务卡片"或"课程列表"。每次状态变化都整页重画，逻辑最简单不易出错。"""
        if self.tab_guide is None or self.tab_guide.isEmpty():
            return
        for c in self.tab_guide.getChildren():
            c.removeNode()
        # 中文：旧控件都删掉了，闪烁列表也要清空，由新建的控件重新登记。
        self.guide_blink = []
        if self.runner:
            self._build_task_card()
        else:
            self._build_lesson_list()

    def _build_lesson_list(self):
        """中文：画课程列表：标题、简介，然后每节课一个按钮 + 一行简短说明。"""
        from .app import RIGHT_W
        f = self.tab_guide
        # 中文：x0 = 左边起点（右侧面板左缘再往里一点），w = 可用宽度（两边各留 0.03 的边距）。
        x0 = -RIGHT_W + 0.03
        w = RIGHT_W - 0.06
        self._text(f, tr("guide_lessons"), (x0, -0.17), 0.04, ACCENT)
        # 中文：y 是当前"写到哪一行"的纵坐标，每放一样东西就往下减去它的高度。
        y = -0.23
        intro = self._text(f, tr("guide_intro"), (x0, y), 0.028, TXT2, wrap=w)
        y -= _h(intro) + 0.04
        for lesson in LESSONS:
            # 中文：已完成的课程，标题后面加一个"已完成"标记，按钮也显示成"点亮"状态。
            #   i18n.pick(*lesson.title)：title 是 (中文, 英文)，前面的 * 把它拆成两个参数传入。
            done = lesson.key in self.lessons_done
            title = i18n.pick(*lesson.title) + ("   " + tr("guide_done_mark") if done else "")
            # 中文：lambda 是"一次性的小函数"，按钮被点击时才执行。
            #   写成 l=lesson 是 Python 的常用技巧：把当前循环的课程"固定"下来，
            #   否则所有按钮点下去都会打开最后一节课。
            self._button(f, title, (x0, y), w, lambda l=lesson: self.start_lesson(l),
                         align="left", scale=0.034, height=0.07, on=done)
            sub = self._text(f, i18n.pick(*lesson.summary), (x0 + 0.02, y - 0.065), 0.026, TXT2, wrap=w - 0.04)
            y -= 0.07 + _h(sub) + 0.04
        y -= 0.02
        self._text(f, tr("guide_tip_note"), (x0, y), 0.026, TXT2, wrap=w)

    def _build_task_card(self):
        """中文：画当前任务的卡片。从上到下依次是：
        返回按钮+课程标题 -> 进度格子 -> 任务说明（可展开深入讲解）-> "试一试"提示
        -> 嵌入的滑块/按钮 -> "帮我做"按钮 -> 示意图 -> 完成后的观察解释 -> 上一步/下一步。
        """
        from .app import PARAM_SLIDERS, RIGHT_W, PLOT_W, PLOT_H
        f = self.tab_guide
        r = self.runner
        t = r.task
        x0 = -RIGHT_W + 0.03
        w = RIGHT_W - 0.06
        y = -0.155
        # 中文：顶部一行：左边"返回"按钮，右边课程标题。
        self._button(f, tr("guide_back"), (x0, y), 0.22, self.stop_lesson, align="left", scale=0.026)
        self._text(f, i18n.pick(*r.lesson.title), (x0 + 0.25, y - 0.005), 0.032, ACCENT)
        y -= 0.07
        # progress boxes
        # 中文：进度格子：每个任务一个小方块。绿色 = 已完成，蓝色 = 当前任务，灰色 = 还没做。
        #   格子宽度 bw 不超过 0.06，任务多时自动变窄，保证放得下。
        n = len(r.lesson.tasks)
        bw = min(0.06, (w - 0.3) / n)
        for k in range(n):
            col = (0.25, 0.65, 0.35, 1) if r.done[k] else ((0.25, 0.5, 0.9, 1) if k == r.idx else (0.3, 0.31, 0.35, 1))
            # 中文：frameSize = (左, 右, 下, 上) 的边界；pos = (x, 深度, 高度)，Panda3D 用三维坐标。
            DirectFrame(parent=f, frameColor=col, frameSize=(0, bw - 0.008, -0.012, 0.012),
                        pos=(x0 + k * bw, 0, y + 0.012))
        # 中文：格子右边写"任务 i / n  任务标题"（显示时从 1 开始数，所以 idx + 1）。
        self._text(f, tr("guide_task", i=r.idx + 1, n=n) + "  " + i18n.pick(*t.title),
                   (x0 + n * bw + 0.02, y), 0.03, TXT)
        y -= 0.06
        # 中文：任务说明文字；如果学生展开了"深入讲解"，在后面追加公式级的解释（"\n" 是换行）。
        body = i18n.pick(*t.explain)
        if self.guide_deep and t.deep:
            body += "\n" + tr("guide_deep_prefix") + i18n.pick(*t.deep)
        ex = self._text(f, body, (x0, y), 0.027, TXT, wrap=w)
        y -= _h(ex)
        # 中文：有深入讲解的任务，右侧放一个"展开/收起"按钮。
        if t.deep:
            y -= 0.02
            self._button(f, tr("guide_deep_off") if self.guide_deep else tr("guide_deep_on"),
                         (x0 + w - 0.24, y), 0.24, self._toggle_deep, align="left", scale=0.024)
            y -= 0.04
        y -= 0.02
        # 中文："试一试"：告诉学生这一步具体要做什么。
        tr_txt = self._text(f, tr("guide_try") + i18n.pick(*t.try_), (x0, y), 0.029, TRY, wrap=w)
        y -= _h(tr_txt) + 0.02
        done = r.done[r.idx]
        # embedded controls
        # 中文：嵌入的控件——让学生不用切换标签页，在卡片里就能直接操作。
        # 中文：先做一个"参数名 -> (标签键, 最小值, 最大值, 是否对数)"的查找表（字典推导式写法），
        #   后面根据任务需要的参数名直接查。
        specs = {k: (lk, lo, hi, log) for k, lk, lo, hi, log in self.flow.sliders or PARAM_SLIDERS}
        # 中文：t.controls 是字符串列表，例如 "param:tox_nm"（某个参数的滑块）、"vin"（输入电压滑块）、
        #   "btn:tran"（播放瞬态按钮）、"btn:ack"（确认按钮）。
        for c in t.controls:
            if c.startswith("param:"):
                # 中文：c[6:] 去掉前 6 个字符 "param:"，得到参数名。
                key = c[6:]
                lk, lo, hi, log = specs[key]
                v = getattr(self.params, key)
                # 中文：上面一行文字显示参数当前值，下面一个滑块。
                lab = self._text(f, _param_text(key, lk, v, log), (x0, y), 0.028, TXT)
                sl = self._slider(f, (x0, y - 0.045), w, _to_unit(v, lo, hi, log), None)
                # 中文：滑块拖动时调用主程序的 set_param 修改参数。
                #   lambda 里的 key=key, lo=lo ... 同样是为了"固定"当前循环里的值。
                sl["command"] = (lambda key=key, lo=lo, hi=hi, log=log, sl=sl, lab=lab, lk=lk:
                                 self.set_param(key, lo, hi, log, sl, lab, lk))
                # 中文：任务还没完成时让滑块闪烁，提示"拖这个"。
                if not done:
                    self.guide_blink.append((sl, "slider", (0.55, 0.70, 0.95, 1)))
                y -= 0.1
            elif c == "vin":
                # 中文：输入电压滑块：位置 = Vin / VDD。
                lab = self._text(f, tr("vin", v=self.vin), (x0, y), 0.028, TXT)
                sl = self._slider(f, (x0, y - 0.045), w, self.vin / self.params.vdd, None)
                sl["command"] = lambda sl=sl, lab=lab: self._guide_vin_changed(sl, lab)
                if not done:
                    self.guide_blink.append((sl, "slider", (0.55, 0.70, 0.95, 1)))
                y -= 0.1
            elif c in ("btn:tran", "btn:ack"):
                # 中文：按钮文字：瞬态按钮显示"播放开关过程"；确认按钮在第一个任务显示"开始"，
                #   之后显示"我看到了"。点击分别调用 play_transient 或 guide_ack。
                label = tr("play_tran") if c == "btn:tran" else (
                    tr("guide_start") if r.idx == 0 else tr("guide_seen"))
                b = self._button(f, label, (x0 + 0.2, y - 0.01), 0.4,
                                 self.play_transient if c == "btn:tran" else self.guide_ack)
                if not done:
                    self.guide_blink.append((b, "button", (0.20, 0.21, 0.25, 1)))
                y -= 0.08
        # 中文："帮我做"按钮：任务未完成、有演示动作、且不是第一个（介绍）任务时才显示。
        if not done and t.demo and r.idx > 0:
            self._button(f, tr("guide_demo"), (x0 + w - 0.15, y + 0.01), 0.3, self.guide_demo, scale=0.026)
            y -= 0.06
        # plot
        # 中文：示意图：把主程序画好的图（贴图 plot_tex）缩放到卡片宽度显示，保持原来的长宽比。
        #   OnscreenImage 的 pos 是图片中心，scale 是半宽/半高，所以都要除以 2。
        if t.plot:
            pw = w
            ph = pw * PLOT_H / PLOT_W
            OnscreenImage(parent=f, image=self.plot_tex, pos=(x0 + pw / 2, 0, y - ph / 2),
                          scale=(pw / 2, 1, ph / 2))
            y -= ph + 0.03
        # observation
        # 中文：观察解释：任务完成后，用绿色文字解释"刚才发生了什么、为什么"。
        if done:
            obs = r.observation()
            if obs and (obs[0] or obs[1]):
                o = self._text(f, tr("guide_seen_head") + i18n.pick(*obs), (x0, y), 0.027, GOOD, wrap=w)
                y -= _h(o) + 0.02
        # navigation
        # 中文：底部导航。先把 y 限制在 -1.93 ~ -1.86 之间，让按钮基本固定在面板底部。
        y = min(y, -1.86)
        y = max(y, -1.93)
        if r.idx > 0:
            self._button(f, tr("guide_prev"), (x0 + 0.13, y), 0.26, self.guide_prev, scale=0.028)
        last = r.idx == len(r.lesson.tasks) - 1
        # 中文：任务完成后：若是最后一个任务，显示"课程完成"；否则显示闪烁的"下一步"按钮。
        if done:
            if last:
                self._text(f, tr("guide_finished"), (x0 + w - 0.02, y - 0.01), 0.03, GOOD, align="right")
            elif r.idx > 0:
                nb = self._button(f, tr("guide_next"), (x0 + w - 0.15, y), 0.3, self.guide_next, scale=0.028)
                self.guide_blink.append((nb, "button", (0.20, 0.45, 0.82, 1)))

    def _toggle_deep(self):
        """中文：展开/收起"深入讲解"，然后重画卡片。"""
        self.guide_deep = not self.guide_deep
        self._build_guide_page()

    # ------------------------------------------------------------------ step tips
    # 中文：======== 工艺步骤小贴士 ========
    def step_tip(self, step) -> str | None:
        """中文：返回某个工艺步骤的小贴士文字（按当前语言）。
        只有在引导模式下、且该步骤有贴士时才返回文字，否则返回 None（不显示）。
        STEP_TIPS.get(键) 在找不到时返回 None 而不是报错。"""
        if not self.guide_mode:
            return None
        tip = STEP_TIPS.get(step.key)
        return i18n.pick(*tip) if tip else None


# 中文：======== 以下是模块级的小工具函数（不属于任何类）========

def _rows(ost) -> int:
    """中文：数一段屏幕文字有几行：换行符 "\\n" 的个数 + 1，至少算 1 行。"""
    return max(1, ost.textNode.getText().count("\n") + 1)


def _h(ost) -> float:
    """Height in parent units actually taken by a (wrapped) OnscreenText block.

    中文：计算一段文字在屏幕上实际占多高 = 行数 × 每行高度 × 文字缩放比例。
    排版时用它决定下一个元素往下挪多少，避免文字重叠。
    """
    tn = ost.textNode
    return _rows(ost) * tn.getLineHeight() * ost.getScale()[0]


def _to_unit(v, lo, hi, log):
    """中文：把参数的真实值 v 换算成滑块位置（0 = 最左，1 = 最右）。
    log=True 时按对数刻度换算：掺杂浓度这类参数能从 1e15 跨到 1e18，
    用对数刻度时每个"数量级"在滑块上占的长度一样，才方便调节。
    min(max(..., 0.0), 1.0) 把结果限制在 0~1 之间，防止超出滑块范围。
    """
    if log:
        return min(max((math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)), 0.0), 1.0)
    return min(max((v - lo) / (hi - lo), 0.0), 1.0)


def _param_text(key, lk, v, log):
    """中文：生成参数滑块上方显示的文字，例如"栅长 = 0.5 um"。
    对数刻度的参数（掺杂浓度/剂量）用科学计数法显示，并根据参数名选单位：
    na_cm3 是体浓度（cm^-3），其余是面剂量（cm^-2）。
    非对数参数同时提供 v 和 v*1e3（即微米换算成纳米），由文字模板决定用哪个。
    """
    from .process_core import sci
    if log:
        return tr(lk, v=sci(v, "cm^-3" if key == "na_cm3" else "cm^-2"))
    return tr(lk, v=v, nm=v * 1e3)
