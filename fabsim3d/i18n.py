"""Tiny bilingual (中文 / English) string table."""

LANG = "zh"


def set_lang(lang: str):
    global LANG
    LANG = lang


def pick(zh: str, en: str) -> str:
    return zh if LANG == "zh" else en


def tr(key: str, **kw) -> str:
    zh, en = STRINGS[key]
    s = pick(zh, en)
    return s.format(**kw) if kw else s


STRINGS = {
    "app_title": ("FabSim3D · CMOS 工艺演示", "FabSim3D · CMOS Process"),
    "app_sub": ("平面 CMOS 前端工艺 · 教学版", "Planar CMOS front-end · teaching"),
    "prev": ("< 上一步", "< Prev"),
    "next": ("下一步 >", "Next >"),
    "play": ("播放", "Play"),
    "pause": ("暂停", "Pause"),
    "reset": ("重置", "Reset"),
    "to_end": ("跳到完成", "Jump to end"),
    "speed": ("动画速度 {v:.1f}x", "Speed {v:.1f}x"),
    "view": ("视图", "View"),
    "cut": ("剖面切割", "Cross-section"),
    "cut_pos": ("切面位置 y = {v:.1f}", "Cut at y = {v:.1f}"),
    "edges": ("显示棱线", "Edges"),
    "labels": ("显示标注", "Labels"),
    "cam_iso": ("等轴", "Iso"),
    "cam_front": ("正视", "Front"),
    "cam_top": ("俯视", "Top"),
    "lang_btn": ("English", "中文"),
    "quiz_mode": ("测验模式", "Quiz mode"),
    "score": ("得分 {ok}/{n}", "Score {ok}/{n}"),
    "mouse_hint": ("鼠标：左键旋转 · 右键平移 · 滚轮缩放", "Mouse: L-drag rotate · R-drag pan · wheel zoom"),
    "tab_process": ("工艺说明", "Process"),
    "tab_elec": ("电学特性", "Electrical"),
    "tab_params": ("工艺参数", "Parameters"),
    "step_n": ("第 {i} / {n} 步", "Step {i} / {n}"),
    "mask": ("掩膜：{m}", "Mask: {m}"),
    "params": ("工艺参数", "Parameters"),
    "legend": ("图例", "Legend"),
    "phase_done": ("● 本步完成", "● Step complete"),
    "plot_idvg": ("Id-Vg", "Id-Vg"),
    "plot_idvd": ("Id-Vd", "Id-Vd"),
    "plot_vtc": ("VTC", "VTC"),
    "plot_tran": ("瞬态", "Transient"),
    "plot_vtl": ("Vt-L", "Vt-L"),
    "vin": ("输入 Vin = {v:.2f} V", "Input Vin = {v:.2f} V"),
    "sim3d": ("3D 载流子仿真", "3D carrier sim"),
    "play_tran": ("播放瞬态", "Play transient"),
    "sim_need_done": ("（完成全部工艺后才可在 3D 中仿真）", "(finish the process to simulate in 3D)"),
    "restore": ("恢复默认", "Defaults"),
    "p_tox": ("栅氧厚度 tox = {v:.1f} nm", "Gate oxide tox = {v:.1f} nm"),
    "p_na": ("衬底掺杂 Na = {v}", "Substrate Na = {v}"),
    "p_dose": ("N 阱注入剂量 = {v}", "N-well dose = {v}"),
    "p_l": ("栅长 L = {v:.2f} µm", "Gate length L = {v:.2f} µm"),
    "p_wn": ("NMOS 宽 Wn = {v:.1f} µm", "NMOS Wn = {v:.1f} µm"),
    "p_wp": ("PMOS 宽 Wp = {v:.1f} µm", "PMOS Wp = {v:.1f} µm"),
    "p_vdd": ("电源 VDD = {v:.2f} V", "Supply VDD = {v:.2f} V"),
    "p_cl": ("负载电容 CL = {v:.0f} fF", "Load CL = {v:.0f} fF"),
    "extracted": ("提取的器件参数", "Extracted device parameters"),
    "quiz_title": ("小测验 · 第 {i} 步", "Quiz · step {i}"),
    "quiz_ok": ("回答正确！", "Correct!"),
    "quiz_bad": ("不对哦，正确答案：{a}", "Not quite. Answer: {a}"),
    "continue": ("继续", "Continue"),
    "guide_mode": ("讲解模式", "Guide mode"),
    "tab_guide": ("讲解", "Guide"),
    "tip_head": ("小贴士：", "Tip: "),
    "guide_lessons": ("动手实验课", "Hands-on lessons"),
    "guide_intro": ("每门课由几个小任务组成：先读原理，再按“试一试”的提示拖动滑块或点按钮，"
                    "完成后系统会自动打勾，并告诉你哪些数值变了、为什么。不会操作时可以点“帮我操作”。"
                    "开始课程时会自动切到对应工艺，并把参数恢复为默认值。",
                    "Each lesson is a few small tasks: read the idea, then follow 'Try it' to drag a "
                    "slider or press a button. The task ticks itself off and explains what changed and "
                    "why. Stuck? Press 'Do it for me'. Starting a lesson switches to its process flow "
                    "and resets the parameters."),
    "guide_tip_note": ("讲解模式下，“工艺说明”页每一步都会多一段绿色的小贴士。",
                       "In guide mode every step on the Process tab also shows a green tip."),
    "guide_done_mark": ("[已完成]", "[done]"),
    "guide_back": ("< 课程列表", "< Lessons"),
    "guide_task": ("任务 {i}/{n}", "Task {i}/{n}"),
    "guide_try": ("试一试：", "Try it: "),
    "guide_deep_on": ("深入一点 (公式)", "Go deeper (math)"),
    "guide_deep_off": ("收起公式", "Hide math"),
    "guide_deep_prefix": ("【深入】", "[Deeper] "),
    "guide_start": ("开始实验 >", "Start >"),
    "guide_seen": ("我看到了", "Got it"),
    "guide_demo": ("帮我操作", "Do it for me"),
    "guide_seen_head": ("看到了什么：", "What happened: "),
    "guide_prev": ("< 上一个", "< Back"),
    "guide_next": ("下一个 >", "Next >"),
    "guide_finished": ("本课完成！回课程列表选下一课", "Lesson complete! Pick the next one"),
    "skip": ("跳过", "Skip"),
}
