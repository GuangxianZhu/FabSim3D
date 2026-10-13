"""Guided learning: hands-on lessons and per-step tips.

【中文说明】“引导学习”功能包的入口文件。

一个文件夹里放了 __init__.py，Python 就把这个文件夹当成一个“包”（package），
别的代码可以写 `from fabsim3d.lessons import ...` 来使用它。本包包含三个文件：
    engine.py   实验课的“引擎”：定义课、任务、实验状态，以及判断任务是否完成的逻辑；
    content.py  实验课的具体内容（四节课的讲解文字、要学生做的操作、完成条件）；
    tips.py     每个工艺步骤的“这一步为什么要做”小提示（引导模式下显示）。
这个文件只是把这三个文件里最常用的东西“转交”出来，方便别处一行导入。
"""
# 下面几行里的点号 . 表示“从本包（lessons 文件夹）里的某个文件导入”
from .content import LESSONS
from .engine import LabState, Lesson, LessonRunner, Task, apply_demo
from .tips import STEP_TIPS

# __all__ 列出本包对外公开的名字：别人写 `from fabsim3d.lessons import *` 时只会导入这些
__all__ = ["LESSONS", "LabState", "Lesson", "LessonRunner", "Task", "STEP_TIPS", "apply_demo"]
