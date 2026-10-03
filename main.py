"""FabSim3D —— CMOS 工艺 3D 教学演示 入口.

    python main.py                 # 正常启动
    python main.py --lang en       # 英文界面
    python main.py --shot out.png --step 21 --tab elec   # 无界面截图 (调试用)
"""
import argparse

from panda3d.core import loadPrcFileData


def parse():
    ap = argparse.ArgumentParser(description="Planar CMOS process 3D teaching demo (Panda3D)")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh")
    ap.add_argument("--flow", default=None, help="process flow: locos (default) | sti")
    ap.add_argument("--guide", action="store_true", help="start with guide mode on")
    ap.add_argument("--lesson", type=int, default=None, help="open lesson N (1-4) in guide mode")
    ap.add_argument("--size", default="1600x900", help="window size, e.g. 1920x1080")
    ap.add_argument("--fullscreen", action="store_true")
    # headless screenshot helpers (used for testing / docs)
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
    return ap.parse_args()


def main():
    a = parse()
    w, h = a.size.lower().split("x")
    prc = [f"win-size {w} {h}", "window-title FabSim3D · CMOS 工艺 3D 演示 / CMOS Process 3D Demo",
           "framebuffer-multisample 1", "multisamples 4", "sync-video 1", "text-encoding utf8",
           "audio-library-name null"]
    if a.fullscreen:
        prc.append("fullscreen 1")
    if a.shot:
        prc.append("window-type offscreen")
    if a.software:
        prc.append("load-display p3tinydisplay")
    loadPrcFileData("", "\n".join(prc))

    from fabsim3d import i18n
    i18n.set_lang(a.lang)
    from fabsim3d.app import CmosApp

    app = CmosApp({"flow": a.flow})
    if a.lang == "en" or i18n.LANG == "en":
        app.rebuild_ui()
    if a.cut is not None:
        app.cut_on, app.cut_y = True, a.cut
        app.scene.set_cut(a.cut)
    if a.vin is not None:
        app.vin = a.vin
        app.vin_slider["value"] = a.vin / app.params.vdd
    if a.step is not None:
        if a.anim is not None:
            app.goto(a.step - 1) if a.step > 0 else None
            app.animate_step(a.step)
        else:
            app.goto(a.step)
    if a.tab:
        app.right_tab = a.tab
    if a.plot:
        app.plot_kind = a.plot
    if a.cam:
        app.set_cam(a.cam)
    if a.sim:
        app.toggle_sim3d()
    if a.guide or a.lesson:
        app.toggle_guide()
        if a.lesson:
            from fabsim3d.lessons import LESSONS
            app.start_lesson(LESSONS[a.lesson - 1])
    if a.quiz and a.step is not None:
        app.show_quiz(a.step)
    app.refresh_ui()

    if a.shot:
        import time
        app.layout_viewport()
        t_end = a.anim or 0.0
        sim_t = 0.0
        while sim_t < t_end:
            dt = 1 / 30
            if app.scene.update(dt, 1.0) and app.anim_step is not None:
                app._phase_finished()
            sim_t += dt
        app.last_time = time.time()
        for _ in range(3):
            app.last_plot = 0
            app.taskMgr.step()
        app.screenshot(a.shot, defaultFilename=False)
        print("saved", a.shot)
        return
    app.run()


if __name__ == "__main__":
    main()
