"""Guided-lesson engine (pure python, no Panda3D).

A Lesson is a list of Tasks.  Each task explains an idea, asks the student to
do something ("try"), detects when it has been done (check), and then explains
what changed (observe), comparing the state when the task started with the
state when it was completed.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

from ..device_model import ProcessParams, inverter_vout, nmos, pmos
from ..process_core import summarize_cached

Text = Tuple[str, str]          # (zh, en)


@dataclass
class LabState:
    """Snapshot of everything a task may look at."""
    flow: str
    features: FrozenSet[str]
    done: bool                  # process finished (device exists)
    p: ProcessParams
    vin: float
    plot: str = "vtc"
    tran_played: bool = False
    ack: bool = False

    def copy(self) -> "LabState":
        return replace(self, p=self.p.copy())

    @property
    def s(self):
        return summarize_cached(self.p, self.features)

    @property
    def mn(self):
        return nmos(self.p, self.features)

    @property
    def mp(self):
        return pmos(self.p, self.features)

    @property
    def vout(self) -> float:
        return float(inverter_vout(self.p, self.vin, features=self.features)[0])

    @property
    def id_n(self) -> float:
        """NMOS current at the current Vin with |Vds| = VDD (as on the Id-Vg plot)."""
        return float(self.mn.ids(self.vin, self.p.vdd))


@dataclass
class Task:
    title: Text
    explain: Text                       # why / analogy (zero-background friendly)
    try_: Text                          # the action asked of the student
    check: Callable[[LabState, LabState], bool]          # (start, now) -> done?
    observe: Callable[[LabState, LabState], Text]        # (start, end) -> explanation
    controls: List[str] = field(default_factory=list)    # "param:<key>", "vin", "btn:tran", "btn:ack"
    demo: Optional[Callable[[LabState], Dict]] = None     # what "do it for me" applies
    plot: Optional[str] = None          # plot to show for this task
    compare: bool = True                # draw the start state as a grey reference curve
    deep: Optional[Text] = None         # optional formula-level explanation


@dataclass
class Lesson:
    key: str
    title: Text
    summary: Text
    intro: Text
    flow: str
    tasks: List[Task]
    sim3d: bool = False


class LessonRunner:
    def __init__(self, lesson: Lesson):
        self.lesson = lesson
        self.idx = 0
        self.done = [False] * len(lesson.tasks)
        self.start_states: List[Optional[LabState]] = [None] * len(lesson.tasks)
        self.end_states: List[Optional[LabState]] = [None] * len(lesson.tasks)

    @property
    def task(self) -> Task:
        return self.lesson.tasks[self.idx]

    @property
    def finished(self) -> bool:
        return all(self.done)

    def begin(self, state: LabState):
        """(Re)start the current task from `state`."""
        self.start_states[self.idx] = state.copy()

    def poll(self, state: LabState) -> bool:
        """Check the current task; returns True exactly when it becomes done."""
        if self.done[self.idx]:
            return False
        start = self.start_states[self.idx] or state
        if self.task.check(start, state):
            self.done[self.idx] = True
            self.end_states[self.idx] = state.copy()
            return True
        return False

    def observation(self) -> Optional[Text]:
        if not self.done[self.idx]:
            return None
        return self.task.observe(self.start_states[self.idx], self.end_states[self.idx])

    def go(self, idx: int, state: LabState):
        self.idx = max(0, min(idx, len(self.lesson.tasks) - 1))
        if not self.done[self.idx]:
            self.begin(state)

    @property
    def reference(self) -> Optional[LabState]:
        """State to draw as the grey 'before' curve."""
        if not self.task.compare:
            return None
        return self.start_states[self.idx]


def apply_demo(state: LabState, demo: Dict) -> LabState:
    """Apply a task's 'do it for me' action to a state (the app mirrors this on its widgets)."""
    st = state.copy()
    if "params" in demo:
        st.p = st.p.copy(**demo["params"])
        st.vin = min(st.vin, st.p.vdd)
    if "vin" in demo:
        st.vin = float(demo["vin"])
    if demo.get("tran"):
        st.tran_played = True
    if demo.get("ack"):
        st.ack = True
    return st
