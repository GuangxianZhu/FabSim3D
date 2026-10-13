"""实验课（lessons）的自动化测试。

什么是“自动化测试”？
    测试就是一段专门用来“检查别的代码有没有写对”的小程序。每个以 test_ 开头的函数
    都是一次检查：它调用程序里的功能，然后用 assert（断言）说明“结果应该是这样”。
    如果结果不符合，assert 就会报错，测试被标记为“失败”，提醒我们哪里坏了。
    这样每次改代码后，不用手动把每节课都点一遍，就能在几秒钟内确认没有改坏东西。

怎么运行？
    在项目根目录（FabSim3D 文件夹）打开命令行，输入：
        python -m pytest
    只跑本文件：
        python -m pytest tests/test_lessons.py
    pytest 是一个测试工具，它会自动找到所有 test_ 开头的函数并逐个运行，最后报告通过/失败的数量。

本文件检查什么？
    讲解页里的“实验课”由很多小任务组成（见 fabsim3d/lessons/content.py）。
    这里确认：每个任务都能用“帮我做”按钮完成、任务不会一开始就自动算完成、
    灰色对比曲线用的是任务开始时的状态、每个工艺步骤都有一条提示文字。
"""
import pytest

from fabsim3d import i18n
from fabsim3d.flows import FLOWS
from fabsim3d.lessons import LESSONS, STEP_TIPS, LabState, LessonRunner, apply_demo


def _start_state(lesson):
    """为某节课准备一个“实验开始时”的状态（LabState）。

    函数名前面的下划线 _ 是 Python 的习惯写法，表示“内部辅助用”，不是测试本身。
    做法：找到这节课使用的工艺流程（如 LOCOS / STI），取它的默认工艺参数，
    假设芯片已经做完（True），输入电压 Vin 先放在电源电压的一半。
    """
    # FLOWS 是一个字典（dict）：用名字（如 "locos"）查出对应的工艺流程对象
    f = FLOWS[lesson.flow]
    p = f.default_params()
    # 依次是：流程名、工艺特性集合、工艺是否已完成、工艺参数、Vin
    return LabState(f.key, f.features, True, p, p.vdd / 2)


# @pytest.mark.parametrize 是“装饰器”（写在函数上方、以 @ 开头）：
# 它让下面这个测试对 LESSONS 里的每一节课各运行一遍，相当于自动写了 4 份测试。
# ids=... 只是给每一份起个好认的名字（课的 key），失败时一看就知道是哪节课。
@pytest.mark.parametrize("lesson", LESSONS, ids=[l.key for l in LESSONS])
def test_every_task_is_completable_with_demo(lesson):
    """检查：每节课的每个任务，点“帮我做”(demo) 之后都一定能完成，并且中英文文字齐全。

    为什么重要：如果某个任务的完成条件写错了，学生无论怎么操作都过不了关，课程就卡死了。
    """
    st = _start_state(lesson)
    r = LessonRunner(lesson)
    # enumerate 会同时给出序号 i 和元素 task，方便知道“现在是第几个任务”
    for i, task in enumerate(lesson.tasks):
        # 每个任务开始前清掉“已确认”“已播放动画”这两个标记，模拟一个干净的开始
        st.ack = False
        st.tran_played = False
        r.go(i, st)
        # 每个任务都必须提供“帮我做”的动作，否则失败信息里显示该任务标题
        assert task.demo is not None, task.title
        # 执行“帮我做”，得到新的状态
        st = apply_demo(st, task.demo(st))
        # poll 返回 True 表示“刚刚完成”；或者之前已经完成过，也算通过
        assert r.poll(st) or r.done[i], f"task {i} not completed by its demo"
        # 中文、英文两种界面语言下都要能生成“观察结果”说明，且标题和操作提示都不能为空
        for lang in ("zh", "en"):
            i18n.set_lang(lang)
            obs = r.observation()
            assert obs is not None
            assert task.title[0] and task.title[1] and task.try_[0] and task.try_[1]
    # 把语言改回默认的中文，免得影响后面的其他测试
    i18n.set_lang("zh")
    # 全部任务做完后，整节课应显示为“已完成”
    assert r.finished


@pytest.mark.parametrize("lesson", LESSONS, ids=[l.key for l in LESSONS])
def test_tasks_not_done_before_acting(lesson):
    """No task (after the intro) may be satisfied by the state it starts from.

    检查：除了第一个“开场说明”任务外，任何任务在学生还没动手时都不能已经算完成。
    为什么重要：否则任务会一出现就自动跳过，学生根本没机会动手体验。
    """
    st = _start_state(lesson)
    r = LessonRunner(lesson)
    for i, task in enumerate(lesson.tasks):
        st.ack = False
        st.tran_played = False
        r.go(i, st)
        # i > 0 跳过第 0 个（开场说明）任务；check(st, st) 表示“开始状态 = 现在状态”，即什么都没做
        if i > 0:
            assert not task.check(st, st), f"task {i} of {lesson.key} is already satisfied at start"
        # 用“帮我做”完成本任务，得到下一个任务的起点
        st = apply_demo(st, task.demo(st))
        r.poll(st)


def test_reference_is_start_state():
    """检查：图上的灰色“改之前”参考曲线，用的是任务开始时的参数，而不是改完后的参数。

    用第 ② 课（LESSONS[1]，编号从 0 开始）的第 2 个任务“减薄栅氧”来试：
    改完栅氧厚度后，参考状态里的栅氧厚度应仍是原来的值。
    """
    lesson = LESSONS[1]
    st = _start_state(lesson)
    r = LessonRunner(lesson)
    r.go(1, st)
    st2 = apply_demo(st, lesson.tasks[1].demo(st))
    r.poll(st2)
    # 连写比较 a == b != c 的意思是：a 等于 b，并且 b 不等于 c
    assert r.reference.p.tox_nm == st.p.tox_nm != st2.p.tox_nm


def test_every_step_has_a_tip():
    """检查：所有工艺流程里的每一个步骤，都在 STEP_TIPS 里有中英文提示。

    为什么重要：引导模式会在每一步显示“这一步为什么要做”，缺了提示界面就会出错或显示空白。
    """
    for flow in FLOWS.values():
        for step in flow.steps:
            assert step.key in STEP_TIPS, f"missing tip for {flow.key}:{step.key}"
            # 每条提示是 (中文, 英文) 两段文字，这里把它们分别取出来，都不能为空
            zh, en = STEP_TIPS[step.key]
            assert zh and en
