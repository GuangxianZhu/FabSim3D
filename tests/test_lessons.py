import pytest

from fabsim3d import i18n
from fabsim3d.flows import FLOWS
from fabsim3d.lessons import LESSONS, STEP_TIPS, LabState, LessonRunner, apply_demo


def _start_state(lesson):
    f = FLOWS[lesson.flow]
    p = f.default_params()
    return LabState(f.key, f.features, True, p, p.vdd / 2)


@pytest.mark.parametrize("lesson", LESSONS, ids=[l.key for l in LESSONS])
def test_every_task_is_completable_with_demo(lesson):
    st = _start_state(lesson)
    r = LessonRunner(lesson)
    for i, task in enumerate(lesson.tasks):
        st.ack = False
        st.tran_played = False
        r.go(i, st)
        assert task.demo is not None, task.title
        st = apply_demo(st, task.demo(st))
        assert r.poll(st) or r.done[i], f"task {i} not completed by its demo"
        for lang in ("zh", "en"):
            i18n.set_lang(lang)
            obs = r.observation()
            assert obs is not None
            assert task.title[0] and task.title[1] and task.try_[0] and task.try_[1]
    i18n.set_lang("zh")
    assert r.finished


@pytest.mark.parametrize("lesson", LESSONS, ids=[l.key for l in LESSONS])
def test_tasks_not_done_before_acting(lesson):
    """No task (after the intro) may be satisfied by the state it starts from."""
    st = _start_state(lesson)
    r = LessonRunner(lesson)
    for i, task in enumerate(lesson.tasks):
        st.ack = False
        st.tran_played = False
        r.go(i, st)
        if i > 0:
            assert not task.check(st, st), f"task {i} of {lesson.key} is already satisfied at start"
        st = apply_demo(st, task.demo(st))
        r.poll(st)


def test_reference_is_start_state():
    lesson = LESSONS[1]
    st = _start_state(lesson)
    r = LessonRunner(lesson)
    r.go(1, st)
    st2 = apply_demo(st, lesson.tasks[1].demo(st))
    r.poll(st2)
    assert r.reference.p.tox_nm == st.p.tox_nm != st2.p.tox_nm


def test_every_step_has_a_tip():
    for flow in FLOWS.values():
        for step in flow.steps:
            assert step.key in STEP_TIPS, f"missing tip for {flow.key}:{step.key}"
            zh, en = STEP_TIPS[step.key]
            assert zh and en
