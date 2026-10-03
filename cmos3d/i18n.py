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
    "app_title": ("CMOS 工艺 3D 演示", "CMOS Process 3D Demo"),
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
    "skip": ("跳过", "Skip"),
}
