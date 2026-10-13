"""FabSim3D —— CMOS 工艺 3D 教学演示 入口.

    python main.py                 # 正常启动
    python main.py --lang en       # 英文界面
    python main.py --shot out.png --step 21 --tab elec   # 无界面截图 (调试用)

【这个文件是做什么的】
这是整个程序的“入口”，也就是你在命令行里运行 python main.py 时最先执行的文件。
它本身不画 3D、也不算物理，只负责三件事：
  1. 读取命令行参数（例如 --lang en 表示用英文界面）；
  2. 告诉 Panda3D（我们用的 3D 引擎）窗口多大、标题是什么、要不要抗锯齿等设置；
  3. 创建真正的程序对象 CmosApp（定义在 fabsim3d/app.py），按参数把它调到指定状态，然后运行。
另外它还有一个“截图模式”(--shot)：不打开窗口，在后台画一帧图存成图片就退出，用于测试和写文档。
"""
# argparse：Python 自带的“命令行参数解析”工具，能把 --lang en 这样的文字变成程序里好用的变量。
import argparse

# 从 Panda3D 引擎里导入 loadPrcFileData：用来在程序启动前，以文字形式写入引擎的配置项。
from panda3d.core import loadPrcFileData


def parse():
    """定义并读取所有命令行参数，返回一个装着各参数值的对象。

    为什么需要：让用户（或测试脚本）不改代码就能控制程序，例如换语言、直接跳到第几步、只截图不开窗。
    返回的对象可以用 a.lang、a.step 这样的写法取出每个参数的值。
    """
    # 创建“参数解析器”，description 是用 --help 查看帮助时显示的说明。
    ap = argparse.ArgumentParser(description="Planar CMOS process 3D teaching demo (Panda3D)")
    # 下面每一行 add_argument 声明一个可用的参数：
    #   choices=[...] 限定只能取这几个值；default=... 是不写该参数时的默认值；
    #   action="store_true" 表示这是个“开关”，写了就是 True，不写就是 False；
    #   type=int / float 表示把输入的文字转成整数 / 小数；help=... 是帮助说明。
    ap.add_argument("--lang", choices=["zh", "en"], default="zh")
    # --flow：选择工艺流程。locos 和 sti 是两种不同的“器件隔离”方法（把相邻晶体管电气上隔开）。
    ap.add_argument("--flow", default=None, help="process flow: locos (default) | sti")
    ap.add_argument("--guide", action="store_true", help="start with guide mode on")
    ap.add_argument("--lesson", type=int, default=None, help="open lesson N (1-4) in guide mode")
    ap.add_argument("--size", default="1600x900", help="window size, e.g. 1920x1080")
    ap.add_argument("--fullscreen", action="store_true")
    # headless screenshot helpers (used for testing / docs)
    # 以下参数主要给“无界面截图”用：直接把程序摆到某个状态，然后拍一张图。
    ap.add_argument("--shot", help="render offscreen, save a screenshot and exit")
    ap.add_argument("--step", type=int, default=None, help="show state after step N (0-based)")
    ap.add_argument("--anim", type=float, default=None,
                    help="with --step: animate that step and capture after this many seconds")
    ap.add_argument("--tab", choices=["process", "elec", "params"], default=None)
    ap.add_argument("--plot", choices=["idvg", "idvd", "vtc", "tran", "vtl"], default=None)
    ap.add_argument("--cut", type=float, default=None, help="enable cross-section at y")
    ap.add_argument("--sim", action="store_true", help="enable 3D carrier simulation")
    ap.add_argument("--vin", type=float, default=None)
    ap.add_argument("--quiz", action="store_true", help="open the quiz dialog of --step")
    ap.add_argument("--cam", choices=["iso", "front", "top"], default=None)
    ap.add_argument("--software", action="store_true", help="use the software renderer")
    # 真正去读取命令行，并返回结果。
    return ap.parse_args()


def main():
    """程序主流程：读参数 -> 配置 Panda3D -> 创建程序 -> 按参数设置状态 -> 运行（或截图后退出）。"""
    a = parse()
    # 把 "1600x900" 这样的文字先转小写，再按字母 x 切开，得到宽 "1600" 和高 "900" 两段。
    # “w, h = ...”一次给两个变量赋值，叫“拆包”。
    w, h = a.size.lower().split("x")
    # 准备一组 Panda3D 配置项（每项是一行文字）：
    #   win-size 窗口大小；window-title 窗口标题；
    #   framebuffer-multisample / multisamples 4：开启 4 倍多重采样抗锯齿，让模型边缘不出现锯齿；
    #   sync-video 1：垂直同步，避免画面撕裂；text-encoding utf8：让文字支持中文；
    #   audio-library-name null：本程序不需要声音，直接关闭音频模块。
    # f"..." 叫 f-string：字符串里花括号 {w} 会被替换成变量 w 的值。
    prc = [f"win-size {w} {h}", "window-title FabSim3D · CMOS 工艺 3D 演示 / CMOS Process 3D Demo",
           "framebuffer-multisample 1", "multisamples 4", "sync-video 1", "text-encoding utf8",
           "audio-library-name null"]
    # 根据参数追加额外配置（.append 是往列表末尾加一项）。
    if a.fullscreen:
        prc.append("fullscreen 1")
    if a.shot:
        # 截图模式：使用“离屏”窗口，不在屏幕上弹出窗口，只在内存里画图。
        prc.append("window-type offscreen")
    if a.software:
        # 使用纯软件渲染器（不依赖显卡），适合没有显卡驱动的电脑或服务器。
        prc.append("load-display p3tinydisplay")
    # 用换行符把各项连成一段文字，一次性交给 Panda3D。必须在创建窗口之前做。
    loadPrcFileData("", "\n".join(prc))

    # 注意这些 import 故意放在函数中间而不是文件开头：
    # 必须先设置好语言和 Panda3D 配置，再导入 app 模块，否则这些设置可能来不及生效。
    from fabsim3d import i18n
    i18n.set_lang(a.lang)
    from fabsim3d.app import CmosApp

    # 创建程序主对象（会打开窗口、搭建 3D 场景和界面）。传入的字典里指定工艺流程。
    app = CmosApp({"flow": a.flow})
    # 如果是英文界面，重新生成一遍界面，确保所有按钮文字都是英文。
    if a.lang == "en" or i18n.LANG == "en":
        app.rebuild_ui()
    # “is not None”表示“用户确实给了这个参数”。
    if a.cut is not None:
        # 打开剖面切割，并设定切面位置（一行同时给两个属性赋值）。
        app.cut_on, app.cut_y = True, a.cut
        app.scene.set_cut(a.cut)
    if a.vin is not None:
        # 设置反相器的输入电压，并同步移动界面上的滑块。
        # 滑块的取值范围是 0~1，所以要除以电源电压 VDD 换算成比例。
        app.vin = a.vin
        app.vin_slider["value"] = a.vin / app.params.vdd
    if a.step is not None:
        if a.anim is not None:
            # 想看第 N 步“正在进行中”的动画：先直接跳到上一步完成的状态，再开始播放第 N 步的动画。
            # 这里的写法 “X if 条件 else None” 只是借用条件表达式来“条件满足才执行 X”。
            app.goto(a.step - 1) if a.step > 0 else None
            app.animate_step(a.step)
        else:
            # 直接跳到第 N 步完成后的状态（不播放动画）。
            app.goto(a.step)
    # 以下几项：切换右侧标签页、选择曲线图、设置相机角度、开启 3D 载流子仿真。
    if a.tab:
        app.right_tab = a.tab
    if a.plot:
        app.plot_kind = a.plot
    if a.cam:
        app.set_cam(a.cam)
    if a.sim:
        app.toggle_sim3d()
    # 讲解模式 / 打开指定的实验课。
    if a.guide or a.lesson:
        app.toggle_guide()
        if a.lesson:
            from fabsim3d.lessons import LESSONS
            # 用户输入的课程编号从 1 开始，而列表下标从 0 开始，所以要减 1。
            app.start_lesson(LESSONS[a.lesson - 1])
    if a.quiz and a.step is not None:
        app.show_quiz(a.step)
    # 根据上面所有设置刷新一次界面。
    app.refresh_ui()

    # —— 截图模式：手动推进动画，画几帧，保存图片后直接结束 ——
    if a.shot:
        import time
        app.layout_viewport()
        # 需要让动画播放多少秒（没给 --anim 就是 0 秒）。
        t_end = a.anim or 0.0
        sim_t = 0.0
        # 以每帧 1/30 秒的步长手动“快进”动画，直到达到目标时间。
        # 这样不用真的等待，截图结果也每次都一样。
        while sim_t < t_end:
            dt = 1 / 30
            # scene.update 返回 True 表示当前这一阶段动画播完了，需要通知程序进入下一阶段。
            if app.scene.update(dt, 1.0) and app.anim_step is not None:
                app._phase_finished()
            sim_t += dt
        app.last_time = time.time()
        # 让 Panda3D 跑 3 帧，确保界面和曲线图都已画好（for _ in range(3) 就是“重复 3 次”，_ 表示不关心计数）。
        for _ in range(3):
            app.last_plot = 0
            app.taskMgr.step()
        app.screenshot(a.shot, defaultFilename=False)
        print("saved", a.shot)
        return
    # 正常模式：进入 Panda3D 的主循环，程序一直运行直到用户关闭窗口。
    app.run()


# 这是 Python 的固定写法：只有“直接运行本文件”时才调用 main()；
# 如果别的文件只是 import main，则不会自动启动程序。
if __name__ == "__main__":
    main()
