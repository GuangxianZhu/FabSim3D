"""Drive the real Panda3D app offscreen (software renderer) through its main paths."""
import pytest

pytest.importorskip("panda3d")


@pytest.fixture(scope="module")
def app():
    from panda3d.core import loadPrcFileData
    loadPrcFileData("", "window-type offscreen\nload-display p3tinydisplay\naudio-library-name null\nwin-size 1280 720")
    from fabsim3d.app import CmosApp
    a = CmosApp()
    yield a
    a.destroy()


def run(app, seconds, speed=1.0):
    for _ in range(int(seconds * 30 / speed)):
        if app.scene.update(1 / 30, speed) and app.anim_step is not None:
            app._phase_finished()
        app.taskMgr.step()


FLOW_KEYS = ["locos", "sti", "hkmg", "finfet", "gaa", "cfet"]


@pytest.mark.parametrize("flow", FLOW_KEYS)
def test_play_through_all_steps(app, flow):
    app.set_flow(flow)
    app.goto(0)
    for i in range(1, len(app.steps)):
        app.next_step()
        assert app.anim_step == i
        run(app, 16, speed=6.0)
        assert app.anim_step is None and app.step == i
    assert app.is_done()


@pytest.mark.parametrize("flow", FLOW_KEYS[2:])
def test_advanced_flow_simulation_and_sliders(app, flow):
    app.set_flow(flow)
    app.goto(len(app.steps) - 1)
    app.right_tab = "elec"
    app.sim3d = False
    app.toggle_sim3d()
    assert app.scene.sim_values is not None and app.scene.carriers and app.scene.channel_nodes
    app.play_transient()
    run(app, 1.0)
    for kind in ("idvg", "idvd", "vtc", "tran", "vtl"):
        app._set_plot(kind)
        app._redraw_plot()
    for sl in app.param_widgets:              # every slider of this generation
        sl["value"] = 0.3
        app.taskMgr.step()
    app._commit_params()
    app.reset_params()
    app.tran_t = None
    app.toggle_sim3d()


def test_simulation_and_transient(app):
    app.goto(len(app.steps) - 1)
    app.right_tab = "elec"
    app.toggle_sim3d()
    assert app.scene.sim_values is not None
    app.play_transient()
    run(app, 1.0)
    assert app.scene.carriers
    for kind in ("idvg", "idvd", "vtc", "tran"):
        app._set_plot(kind)
        app._redraw_plot()


def test_params_lang_quiz(app):
    app.set_flow("locos")
    app.goto(13)
    sl = app.param_widgets[3]          # gate length
    sl["value"] = 0.9
    app.taskMgr.step()
    app._commit_params()
    assert app.ctx.lay["gl"] > 1.0
    app._toggle_lang()
    app._toggle_lang()
    app.quiz_enabled = True
    app.show_quiz(5)
    app._answer(5, app.steps[5].quiz.answer)
    assert app.quiz_results[5] is True
    app._close_quiz()
    assert app.quiz_frame is None
    app.prev_step()
    assert app.step == 12


def test_guide_mode_runs_every_lesson(app):
    from fabsim3d.lessons import LESSONS
    app.guide_mode = False
    app.toggle_guide()
    assert app.right_tab == "guide" and "guide" in app.tab_btns
    for lesson in LESSONS:
        app.start_lesson(lesson)
        assert app.flow.key == lesson.flow and app.is_done()
        app.guide_ack()                       # intro card
        for _ in range(len(lesson.tasks) - 1):
            app.guide_demo()
            run(app, 0.3, speed=4.0)
            assert app.runner.done[app.runner.idx], (lesson.key, app.runner.idx)
            app._redraw_plot()                # with the grey reference curve
            app.guide_next()
        assert app.runner.finished
        assert lesson.key in app.lessons_done
    app._toggle_lang()
    app._toggle_lang()
    app.stop_lesson()
    app.goto(3)
    app._set_tab("process")
    assert app.tip_frame.getChildren().getNumPaths() > 0     # step tip visible in guide mode
    app.toggle_guide()
    assert app.right_tab == "process" and "guide" not in app.tab_btns


class _FakeMouse:
    """Stands in for the mouse watcher (offscreen windows have no pointer)."""
    def __init__(self, real, x, y):
        self.real, self.x, self.y = real, x, y

    def hasMouse(self):
        return True

    def getMouse(self):
        from panda3d.core import Point2
        return Point2(self.x, self.y)

    def getMouseX(self):
        return self.x

    def __getattr__(self, k):
        return getattr(self.real, k)


def test_hover_names_layer_under_mouse(app):
    from panda3d.core import Point2, Point3
    from fabsim3d import i18n
    from fabsim3d.materials import mat
    app.set_flow("locos")
    app.goto(len(app.steps) - 1)
    app.set_cam("front")
    app.taskMgr.step()
    # project the middle of the NMOS gate onto the screen, then hover there
    gx = sum(app.ctx.lay["gn"]) / 2
    p2 = Point2()
    assert app.camLens.project(app.cam.getRelativePoint(app.render, Point3(gx, app.cut_y, 0.4)), p2)
    left, right = app.view_frac
    mx = ((p2.x + 1) / 2 * (right - left) + left) * 2 - 1
    real = app.mouseWatcherNode
    app.mouseWatcherNode = _FakeMouse(real, mx, p2.y)
    try:
        app._update_hover(1e9)
        assert app.hover_layer is not None
        material = app.wafer.layers[app.hover_layer].material
        assert material in ("poly_n", "poly", "gate_ox", "silicide", "metal")
        assert not app.hover_tip.isHidden()
        assert i18n.pick(mat(material).zh, mat(material).en) in app.hover_tip.node().getText()
        from fabsim3d.app import ACCENT
        assert tuple(app.legend_texts[material].fg) == pytest.approx(ACCENT)   # legend entry lit
        app.mouseWatcherNode = _FakeMouse(real, -0.99, 0.0)     # over the left panel
        app._update_hover(2e9)
        assert app.hover_layer is None and app.hover_tip.isHidden()
    finally:
        app.mouseWatcherNode = real
    app.set_cam("iso")
