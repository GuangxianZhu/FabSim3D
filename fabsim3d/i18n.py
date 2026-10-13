"""Tiny bilingual (中文 / English) string table.

【这个文件是做什么的】
i18n 是 “internationalization（国际化）”的缩写（i 和 n 之间有 18 个字母）。
本程序的界面可以在中文和英文之间切换。为了做到这一点，界面上出现的每一句文字
都不直接写死在界面代码里，而是集中放在这里的 STRINGS 字典中，每一条同时有中文版和英文版。
界面代码只需要写 tr("next")，本文件就会根据当前语言返回 “下一步 >” 或 “Next >”。

整体流程：
  1. 程序启动时 main.py 调用 set_lang("zh" 或 "en") 设定语言；
  2. 界面需要文字时调用 tr(键名) 或 pick(中文, 英文)；
  3. 点“English/中文”按钮切换语言后，界面重新调用 tr()，文字就全部换成另一种语言。
"""

# 当前语言。"zh" 表示中文，"en" 表示英文。默认是中文。
# 这是一个“全局变量”：整个文件里的函数都能读到它。
LANG = "zh"


def set_lang(lang: str):
    """切换界面语言（传入 "zh" 或 "en"）。

    为什么需要：语言是全局设置，所有界面文字都要跟着它变，所以用一个函数统一修改。
    """
    # global LANG：声明“我要修改的是文件最上面那个全局变量 LANG”。
    # 如果不写这一行，Python 会以为你在函数内部新建了一个同名的局部变量，全局的那个不会变。
    global LANG
    LANG = lang


def pick(zh: str, en: str) -> str:
    """从中文和英文两个版本里，按当前语言挑一个返回。

    为什么需要：有些文字不在 STRINGS 表里（例如工艺步骤说明直接在别处写了中英两份），
    这时就可以直接用 pick("中文", "English") 来选。
    """
    # “A if 条件 else B”是 Python 的一行式条件写法：条件成立返回 A，否则返回 B。
    return zh if LANG == "zh" else en


def tr(key: str, **kw) -> str:
    """按“键名”从 STRINGS 表里取出当前语言的文字；可以顺便把数字等填进文字中的空位。

    tr 是 “translate（翻译）”的缩写。例子：
        tr("step_n", i=3, n=20)  ->  中文时得到 "第 3 / 20 步"，英文时得到 "Step 3 / 20"

    参数里的 **kw 表示“可以再传任意多个 名字=值 的参数”，它们会被收集成一个字典 kw。
    """
    # STRINGS[key] 取出一对 (中文, 英文)，再“拆包”分别放进 zh 和 en 两个变量。
    zh, en = STRINGS[key]
    # 按当前语言选一个。
    s = pick(zh, en)
    # 如果调用时传了额外参数（kw 不为空），就用 .format(**kw) 把文字里的 {i}、{v:.1f} 等占位符填上真实值。
    # 例如 {v:.1f} 表示“把 v 填进来，保留 1 位小数”。没传参数就原样返回。
    return s.format(**kw) if kw else s


# STRINGS：整个程序界面用到的文字表。
# 它是一个“字典”（dict，用花括号 {} 表示），由一条条 “键: 值” 组成：
#   键   = 一个简短的英文名字，程序里用它来找文字；
#   值   = 一个“元组”(中文, 英文)，即用圆括号括起来的一对文字。
# 文字中 {v:.2f} 之类的花括号是占位符，在 tr() 里会被替换成实际数值。
STRINGS = {
    # —— 标题、播放控制按钮 ——
    "app_title": ("FabSim3D · CMOS 工艺演示", "FabSim3D · CMOS Process"),
    "app_sub": ("平面 CMOS 前端工艺 · 教学版", "Planar CMOS front-end · teaching"),
    "prev": ("< 上一步", "< Prev"),
    "next": ("下一步 >", "Next >"),
    "play": ("播放", "Play"),
    "pause": ("暂停", "Pause"),
    "reset": ("重置", "Reset"),
    "to_end": ("跳到完成", "Jump to end"),
    "speed": ("动画速度 {v:.1f}x", "Speed {v:.1f}x"),
    # —— 视图相关：剖面切割、显示选项、相机角度 ——
    # “剖面切割”就是把 3D 芯片模型沿某个平面切开，露出内部各层材料，像切蛋糕看夹层一样。
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
    "mouse_hint": ("鼠标：左键旋转 · 右键平移 · 滚轮缩放 · 悬停显示材料",
                   "Mouse: L-drag rotate · R-drag pan · wheel zoom · hover to name a layer"),
    "hover_through": ("（透过 {m}）", "(seen through {m})"),
    # —— 右侧面板的标签页 ——
    "tab_process": ("工艺说明", "Process"),
    "tab_elec": ("电学特性", "Electrical"),
    "tab_params": ("工艺参数", "Parameters"),
    "step_n": ("第 {i} / {n} 步", "Step {i} / {n}"),
    # 掩膜（mask）：光刻时用的“模板”，决定哪些区域被曝光、哪些被保护。
    "mask": ("掩膜：{m}", "Mask: {m}"),
    "params": ("工艺参数", "Parameters"),
    "legend": ("图例", "Legend"),
    "phase_done": ("● 本步完成", "● Step complete"),
    # —— 电学曲线图的名字 ——
    # Id-Vg：漏极电流 Id 随栅极电压 Vg 的变化（看晶体管怎么“打开”）；
    # Id-Vd：漏极电流随漏极电压的变化（输出特性）；
    # VTC：反相器的电压传输特性（输入电压 -> 输出电压）；
    # 瞬态：输入突然跳变时输出随时间的变化；Vt-L：阈值电压随栅长的变化（短沟道效应）。
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
    # —— 工艺参数滑块的标签 ——
    # tox：栅氧化层厚度；Na：衬底（硅片）里受主杂质的浓度；N 阱剂量：注入离子的数量；
    # L：栅长（沟道长度）；Wn/Wp：NMOS/PMOS 的沟道宽度；VDD：电源电压；CL：输出端的负载电容。
    "p_tox": ("栅氧厚度 tox = {v:.1f} nm", "Gate oxide tox = {v:.1f} nm"),
    "p_na": ("衬底掺杂 Na = {v}", "Substrate Na = {v}"),
    "p_dose": ("N 阱注入剂量 = {v}", "N-well dose = {v}"),
    "p_l": ("栅长 L = {v:.2f} µm", "Gate length L = {v:.2f} µm"),
    "p_wn": ("NMOS 宽 Wn = {v:.1f} µm", "NMOS Wn = {v:.1f} µm"),
    "p_wp": ("PMOS 宽 Wp = {v:.1f} µm", "PMOS Wp = {v:.1f} µm"),
    "p_vdd": ("电源 VDD = {v:.2f} V", "Supply VDD = {v:.2f} V"),
    "p_cl": ("负载电容 CL = {v:.0f} fF", "Load CL = {v:.0f} fF"),
    # advanced nodes
    # 先进工艺节点（FinFET 鳍式晶体管、纳米片 GAA 晶体管）专用的参数标签。
    # EOT：把高介电常数栅介质“折算”成同等效果的二氧化硅厚度；功函数：决定阈值电压的栅极金属性质。
    "p_eot": ("等效氧化层厚度 EOT = {v:.2f} nm", "Equivalent oxide EOT = {v:.2f} nm"),
    "p_l_nm": ("栅长 Lg = {nm:.0f} nm", "Gate length Lg = {nm:.0f} nm"),
    "p_wn_eff": ("NMOS 有效宽 Weff = {v:.2f} µm", "NMOS Weff = {v:.2f} µm"),
    "p_wp_eff": ("PMOS 有效宽 Weff = {v:.2f} µm", "PMOS Weff = {v:.2f} µm"),
    "p_cl_small": ("负载电容 CL = {v:.2f} fF", "Load CL = {v:.2f} fF"),
    "p_tfin": ("鳍宽 Wfin = {v:.1f} nm", "Fin width Wfin = {v:.1f} nm"),
    "p_tsheet": ("纳米片厚 Tsh = {v:.1f} nm", "Sheet thickness Tsh = {v:.1f} nm"),
    "p_wfn": ("NMOS 栅功函数 = {v:.2f} eV", "NMOS gate work function = {v:.2f} eV"),
    "p_wfp": ("PMOS 栅功函数 = {v:.2f} eV", "PMOS gate work function = {v:.2f} eV"),
    "extracted": ("提取的器件参数", "Extracted device parameters"),
    # —— 小测验 ——
    "quiz_title": ("小测验 · 第 {i} 步", "Quiz · step {i}"),
    "quiz_ok": ("回答正确！", "Correct!"),
    "quiz_bad": ("不对哦，正确答案：{a}", "Not quite. Answer: {a}"),
    "continue": ("继续", "Continue"),
    # —— 讲解模式 / 动手实验课 ——
    "guide_mode": ("讲解模式", "Guide mode"),
    "tab_guide": ("讲解", "Guide"),
    "tip_head": ("小贴士：", "Tip: "),
    "guide_lessons": ("动手实验课", "Hands-on lessons"),
    # 下面这条很长：Python 会把紧挨着的几段字符串自动连成一整段，所以可以分行书写。
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
