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


@pytest.mark.parametrize("flow", ["locos", "sti"])
def test_play_through_all_steps(app, flow):
    app.set_flow(flow)
    app.goto(0)
    for i in range(1, len(app.steps)):
        app.next_step()
        assert app.anim_step == i
        run(app, 9, speed=6.0)
        assert app.anim_step is None and app.step == i
    assert app.is_done()


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
