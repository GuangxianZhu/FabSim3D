"""Drive the real Panda3D app offscreen (software renderer) through its main paths.

整个图形界面程序的“冒烟测试”（smoke test）。

什么是“自动化测试”？
    测试是一段用来检查别的代码是否正确的小程序。每个 test_ 开头的函数是一项检查，
    assert（断言）后面写的是“应该成立的条件”，不成立就报错、测试失败。
    “冒烟测试”这个名字来自电子行业：新电路板第一次通电，先看会不会冒烟。
    这里的意思是：把真正的程序启动起来，把主要功能都“点”一遍，确认不会崩溃。

    这些测试不打开可见窗口，而是在“离屏”（offscreen）模式下用软件渲染器绘图，
    并且用代码代替鼠标点击按钮（直接调用按钮背后的函数）。

怎么运行？
    在项目根目录打开命令行，输入：
        python -m pytest tests/test_app_smoke.py
    这个文件比较慢（要真的跑完所有工艺动画），需要安装 panda3d；没装的话会自动跳过。
    （只输入 python -m pytest 会运行全部测试。）
"""
import pytest

# 如果电脑上没有安装 panda3d（3D 图形引擎），就跳过本文件的全部测试，而不是报错
pytest.importorskip("panda3d")


# fixture（夹具）是 pytest 的功能：测试函数的参数里写 app，pytest 就会自动调用下面这个函数，
# 把准备好的程序对象传进去。scope="module" 表示整个文件只启动一次程序，所有测试共用，省时间。
@pytest.fixture(scope="module")
def app():
    """启动一个不显示窗口的 FabSim3D 程序，供本文件的所有测试使用；全部测试结束后关闭它。"""
    from panda3d.core import loadPrcFileData
    # 设置 Panda3D：离屏窗口、使用软件渲染器 p3tinydisplay（不需要显卡）、关闭声音、画面大小 1280×720
    loadPrcFileData("", "window-type offscreen\nload-display p3tinydisplay\naudio-library-name null\nwin-size 1280 720")
    # 注意要在上面的设置之后才导入并创建程序，设置才会生效
    from fabsim3d.app import CmosApp
    a = CmosApp()
    # yield 把程序交给测试使用；等所有测试跑完，再继续执行下面的 destroy() 关闭程序
    yield a
    a.destroy()


def run(app, seconds, speed=1.0):
    """让程序“空转”一段时间，模拟时间流逝，让动画播放下去。

    正常运行时 Panda3D 会自己一帧一帧刷新；测试里没有这个循环，所以手动推进：
    每秒 30 帧，speed 越大动画越快、需要的帧数越少。
    """
    for _ in range(int(seconds * 30 / speed)):
        # 推进 3D 场景动画一帧；如果当前动画阶段刚好播完，就通知程序进入下一个阶段
        if app.scene.update(1 / 30, speed) and app.anim_step is not None:
            app._phase_finished()
        # 让 Panda3D 处理一帧的其他任务（界面刷新等）
        app.taskMgr.step()


# 全部六套工艺流程：两代平面工艺、28 nm HKMG、FinFET、GAA、CFET
FLOW_KEYS = ["locos", "sti", "hkmg", "finfet", "gaa", "cfet"]


@pytest.mark.parametrize("flow", FLOW_KEYS)
def test_play_through_all_steps(app, flow):
    """检查：每套流程都能从第一步开始，按“下一步”一路把每一步的动画播完，最后芯片完成。

    为什么重要：这是程序最主要的使用方式，任何一步的动画出错都会让用户卡住。
    """
    app.set_flow(flow)
    app.goto(0)
    for i in range(1, len(app.steps)):
        app.next_step()
        # 刚按下“下一步”时，程序应正在播放第 i 步的动画
        assert app.anim_step == i
        # 以 6 倍速空转最多 16 秒，足够把这一步的动画播完
        run(app, 16, speed=6.0)
        # 播完后：没有正在播放的动画，当前步骤停在第 i 步
        assert app.anim_step is None and app.step == i
    assert app.is_done()


# FLOW_KEYS[2:] 是“切片”写法：取从第 3 个（下标 2）开始到最后的元素，即四套先进工艺
@pytest.mark.parametrize("flow", FLOW_KEYS[2:])
def test_advanced_flow_simulation_and_sliders(app, flow):
    """检查先进工艺做完后的“电学特性”页：3D 载流子仿真能打开、开关动画能播放、
    五种曲线图都能画出来、每个参数滑块拖动后都能正常重新计算、恢复默认参数不出错。
    """
    app.set_flow(flow)
    app.goto(len(app.steps) - 1)
    app.right_tab = "elec"
    # 先设成“关”，再切换一次，确保仿真是“开”的状态
    app.sim3d = False
    app.toggle_sim3d()
    # 打开仿真后应有：电势/浓度数值、移动的载流子小球、沟道显示
    assert app.scene.sim_values is not None and app.scene.carriers and app.scene.channel_nodes
    app.play_transient()
    run(app, 1.0)
    # 依次切换并重画每种图：Id-Vg、Id-Vd、电压传输曲线、开关瞬态、Vt-L
    for kind in ("idvg", "idvd", "vtc", "tran", "vtl"):
        app._set_plot(kind)
        app._redraw_plot()
    for sl in app.param_widgets:              # every slider of this generation（这一代工艺的每个滑块）
        # 用代码把滑块拖到 0.3 的位置，再刷新一帧
        sl["value"] = 0.3
        app.taskMgr.step()
    app._commit_params()
    app.reset_params()
    # 清掉瞬态动画的计时，并关掉仿真，恢复干净状态给下一个测试
    app.tran_t = None
    app.toggle_sim3d()


def test_simulation_and_transient(app):
    """检查默认流程做完后：3D 仿真能打开，开关动画能让载流子动起来，四种曲线图都能画。"""
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
    """检查几个常用交互：
    拖动“栅长”滑块后 3D 版图里的栅变宽；中英文来回切换不出错；
    小测验能弹出、答对后记为正确、能关闭；“上一步”按钮能回退一步。
    """
    app.set_flow("locos")
    app.goto(13)
    sl = app.param_widgets[3]          # gate length（第 4 个滑块是栅长）
    sl["value"] = 0.9
    app.taskMgr.step()
    app._commit_params()
    assert app.ctx.lay["gl"] > 1.0
    # 切两次语言：中 → 英 → 中
    app._toggle_lang()
    app._toggle_lang()
    # 打开第 5 步的小测验并选择正确答案
    app.quiz_enabled = True
    app.show_quiz(5)
    app._answer(5, app.steps[5].quiz.answer)
    assert app.quiz_results[5] is True
    app._close_quiz()
    assert app.quiz_frame is None
    app.prev_step()
    assert app.step == 12


def test_guide_mode_runs_every_lesson(app):
    """检查“引导模式”：打开后出现“讲解”标签页；每节实验课都能开始，
    每个任务用“帮我做”都能完成并画出灰色对比曲线，整节课被记为已完成；
    退出课程后，在工艺页能看到每一步的提示；关闭引导模式后“讲解”标签页消失。
    """
    from fabsim3d.lessons import LESSONS
    app.guide_mode = False
    app.toggle_guide()
    assert app.right_tab == "guide" and "guide" in app.tab_btns
    for lesson in LESSONS:
        app.start_lesson(lesson)
        # 开始一节课时，程序会自动切到这节课需要的工艺流程，并直接做完芯片
        assert app.flow.key == lesson.flow and app.is_done()
        app.guide_ack()                       # intro card（点掉开场说明卡片）
        # 除开场说明外，剩下的每个任务都点“帮我做”，再点“下一个”
        for _ in range(len(lesson.tasks) - 1):
            app.guide_demo()
            run(app, 0.3, speed=4.0)
            # 第二个值是失败时显示的信息：哪节课的第几个任务没完成
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
    """Stands in for the mouse watcher (offscreen windows have no pointer).

    “假鼠标”：离屏窗口没有真正的鼠标，所以用这个类冒充，让程序以为鼠标停在 (x, y) 处。
    除了下面几个被改写的方法，其他所有属性都转交给真正的鼠标对象（见 __getattr__）。
    """
    # __init__ 是“构造函数”：创建对象时自动运行，这里记下真鼠标对象和假坐标
    def __init__(self, real, x, y):
        self.real, self.x, self.y = real, x, y

    def hasMouse(self):
        """永远回答“鼠标在窗口里”。"""
        return True

    def getMouse(self):
        """返回假的鼠标坐标（Panda3D 的屏幕坐标范围是 -1 到 1）。"""
        from panda3d.core import Point2
        return Point2(self.x, self.y)

    def getMouseX(self):
        return self.x

    def __getattr__(self, k):
        """当访问本类没有的属性时，Python 会调用这个特殊方法；这里把请求转给真鼠标对象。"""
        return getattr(self.real, k)


def test_hover_names_layer_under_mouse(app):
    """检查“鼠标悬停提示”：鼠标停在 NMOS 栅极上时，程序能认出下面是哪一层材料，
    弹出写有材料名字的提示框，并把右侧图例里对应的条目高亮；
    鼠标移到左侧面板上时，提示框消失。
    """
    from panda3d.core import Point2, Point3
    from fabsim3d import i18n
    from fabsim3d.materials import mat
    app.set_flow("locos")
    app.goto(len(app.steps) - 1)
    app.set_cam("front")
    app.taskMgr.step()
    # project the middle of the NMOS gate onto the screen, then hover there
    # （先算出 NMOS 栅中点在 3D 空间的位置，再用相机把它“投影”成屏幕上的坐标 p2）
    gx = sum(app.ctx.lay["gn"]) / 2
    p2 = Point2()
    assert app.camLens.project(app.cam.getRelativePoint(app.render, Point3(gx, app.cut_y, 0.4)), p2)
    # 3D 画面只占窗口中间一部分（左右是面板），所以要把画面内的坐标换算成整个窗口的坐标
    left, right = app.view_frac
    mx = ((p2.x + 1) / 2 * (right - left) + left) * 2 - 1
    real = app.mouseWatcherNode
    app.mouseWatcherNode = _FakeMouse(real, mx, p2.y)
    # try ... finally：不管中间的检查成功还是失败，finally 里的代码都一定执行（把真鼠标换回去）
    try:
        # 参数是“当前时间”；给一个很大的数，确保不会因为“刷新太频繁”被跳过
        app._update_hover(1e9)
        assert app.hover_layer is not None
        material = app.wafer.layers[app.hover_layer].material
        # 栅极位置从上往下可能先碰到的材料：N 型多晶硅、多晶硅、栅氧、硅化物或金属
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
    # 把相机恢复成默认的斜视角
    app.set_cam("iso")
