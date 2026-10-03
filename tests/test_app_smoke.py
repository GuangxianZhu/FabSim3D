"""Drive the real Panda3D app offscreen (software renderer) through its main paths."""
import pytest

pytest.importorskip("panda3d")


@pytest.fixture(scope="module")
def app():
    from panda3d.core import loadPrcFileData
    loadPrcFileData("", "window-type offscreen\nload-display p3tinydisplay\naudio-library-name null\nwin-size 1280 720")
    from cmos3d.app import CmosApp
    a = CmosApp()
    yield a
    a.destroy()


def run(app, seconds, speed=1.0):
    for _ in range(int(seconds * 30 / speed)):
        if app.scene.update(1 / 30, speed) and app.anim_step is not None:
            app._phase_finished()
        app.taskMgr.step()


def test_play_through_all_steps(app):
    app.goto(0)
    for i in range(1, 22):
        app.next_step()
        assert app.anim_step == i
        run(app, 9, speed=6.0)
        assert app.anim_step is None and app.step == i
    assert app.is_done()


def test_simulation_and_transient(app):
    app.goto(21)
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
    app._answer(5, STEPS_ANSWER(5))
    assert app.quiz_results[5] is True
    app._close_quiz()
    assert app.quiz_frame is None
    app.prev_step()
    assert app.step == 12


def STEPS_ANSWER(i):
    from cmos3d.process_flow import STEPS
    return STEPS[i].quiz.answer
