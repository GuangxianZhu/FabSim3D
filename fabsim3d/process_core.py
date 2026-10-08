"""Process engine: wafer state, animated actions and the Flow abstraction.

A Flow is an ordered list of Steps; a Step is a list of animated Phases; a
Phase is a list of actions.  An action mutates the Wafer and describes how to
animate the change in a PhaseAnim.  Nothing here imports Panda3D.

Extension points
----------------
* Flow / FLOWS registry (fabsim3d.flows) – one module per technology
  generation (LOCOS 1 µm, STI 0.25 µm, ...).  Flow.features tells the device
  model which physical effects apply (see device_model.EFFECTS).
* Faults (Ctx.faults) – deliberate process errors for "find the bug" lessons:
  mask misalignment and skipped steps are honoured by the core actions.
* Wafer.dopants / Wafer.thermal – every implant and anneal is recorded so a
  later doping-profile view can compute concentrations without re-parsing
  geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

from .device_model import ProcessParams, summarize
from .geometry import (Rect, Solid, conformal_cells, rect_complement,
                       rect_intersect, split_box)

DOMAIN: Rect = (0.0, 20.0, 0.0, 8.0)
SUB_DEPTH = 3.0
ACT_Y = (1.5, 6.5)


# --------------------------------------------------------------------------
# Wafer state
# --------------------------------------------------------------------------

@dataclass
class Layer:
    name: str
    material: str
    solids: List[Solid] = field(default_factory=list)


@dataclass
class DopantEvent:
    """One ion implantation (for doping-profile visualisation)."""
    step: str
    species: str            # "P", "As", "B", "BF2"
    polarity: str           # "n" | "p"
    dose_cm2: float
    energy_kev: float
    rects: List[Rect]
    z_top: float            # surface height where the ions entered


@dataclass
class ThermalEvent:
    step: str
    temp_c: float
    time_s: float


class Wafer:
    def __init__(self):
        self.layers: Dict[str, Layer] = {}
        self.dopants: List[DopantEvent] = []
        self.thermal: List[ThermalEvent] = []
        self.current_step: str = ""

    def layer(self, name: str, material: Optional[str] = None) -> Layer:
        if name not in self.layers:
            self.layers[name] = Layer(name, material or name)
        return self.layers[name]

    def solids(self, exclude=()) -> List[Solid]:
        return [s for n, l in self.layers.items() if n not in exclude for s in l.solids]

    def remove(self, name: str) -> Optional[Layer]:
        return self.layers.pop(name, None)

    def has(self, name: str) -> bool:
        return name in self.layers and bool(self.layers[name].solids)


@dataclass
class ParticleSpec:
    kind: str                      # ion | uv | plasma | depo
    color: tuple
    region: Optional[List[Rect]] = None   # spawn region(s); None = whole wafer
    rate: float = 120.0            # particles per second
    stop_solids: List[Solid] = field(default_factory=list)


@dataclass
class MaskSpec:
    chrome: List[Rect]
    z: float


@dataclass
class PhaseAnim:
    grow: List[Solid] = field(default_factory=list)
    fade_in: List[Solid] = field(default_factory=list)
    ghosts: List[Tuple[str, Solid, str]] = field(default_factory=list)  # (material, solid, etch|fade)
    recolor: Dict[str, str] = field(default_factory=dict)              # layer -> old material
    particles: List[ParticleSpec] = field(default_factory=list)
    mask: Optional[MaskSpec] = None
    glow: Optional[tuple] = None
    pad: Optional[float] = None    # CMP polishing pad comes down to this z


@dataclass
class Faults:
    """Deliberate process errors (hook for a fault-finding teaching mode).

    misalign: mask name -> (dx, dy) shift of that mask's pattern
    skip:     step keys that are silently left out of the flow
    """
    misalign: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    skip: FrozenSet[str] = frozenset()

    def shift(self, mask: Optional[str], rects: List[Rect]) -> List[Rect]:
        if not mask or mask not in self.misalign:
            return rects
        dx, dy = self.misalign[mask]
        out = []
        for r in rects:
            s = rect_intersect((r[0] + dx, r[1] + dx, r[2] + dy, r[3] + dy), DOMAIN)
            if s:
                out.append(s)
        return out


@dataclass
class Ctx:
    p: ProcessParams
    lay: dict
    flow: Optional["Flow"] = None
    faults: Faults = field(default_factory=Faults)

    @property
    def features(self) -> FrozenSet[str]:
        return self.flow.features if self.flow else frozenset()


Action = Callable[[Wafer, Ctx, PhaseAnim], None]


@dataclass
class Phase:
    zh: str
    en: str
    duration: float
    actions: List[Action]


@dataclass
class Quiz:
    q: Tuple[str, str]
    options: List[Tuple[str, str]]
    answer: int
    explain: Tuple[str, str]


@dataclass
class Step:
    key: str
    title: Tuple[str, str]
    desc: Tuple[str, str]
    params: List[Tuple[str, str, Callable[["Ctx"], str]]]
    phases: List[Phase]
    quiz: Optional[Quiz] = None
    mask_name: Optional[Tuple[str, str]] = None


@dataclass
class Flow:
    """A complete process recipe for one technology generation."""
    key: str
    name: Tuple[str, str]
    node: Tuple[str, str]                     # one-line description of the generation
    steps: List[Step]
    features: FrozenSet[str] = frozenset()    # e.g. {"locos"} / {"sti", "cmp"}
    region_labels: List[tuple] = field(default_factory=list)   # (layer, zh, en, x, z)
    terminal_labels: List[tuple] = field(default_factory=list)  # (name, x, y)
    defaults: Dict[str, float] = field(default_factory=dict)    # typical ProcessParams of the era
    short: Optional[Tuple[str, str]] = None   # compact name for the flow selector
    # optional per-generation hooks (None = the planar side-by-side inverter)
    layout_fn: Optional[Callable[[ProcessParams], dict]] = None  # replaces layout()
    sliders: Optional[List[tuple]] = None     # (key, i18n key, lo, hi, log) for the Parameters tab
    device_labels: Optional[List[tuple]] = None   # (text, x, y, z, rgba) shown in simulation mode
    channel_fn: Optional[Callable[[dict], List[tuple]]] = None   # lay -> [(key "n"/"p", Solid)]
    carrier_fn: Optional[Callable[[dict, float], dict]] = None   # (lay, y) -> carrier paths
    carrier_ys: List[Tuple[float, float]] = field(default_factory=list)  # silicon bands carriers snap to

    def default_params(self) -> ProcessParams:
        return ProcessParams(**self.defaults)

    @property
    def label(self) -> Tuple[str, str]:
        return self.short or self.name

    def step_index(self, key: str) -> int:
        return next(i for i, s in enumerate(self.steps) if s.key == key)


# --------------------------------------------------------------------------
# Layout (depends on drawn gate length)
# --------------------------------------------------------------------------

def layout(p: ProcessParams) -> dict:
    gl = min(max(0.45 + 0.3 * p.l_um, 0.6), 1.8)
    gnc, gpc = 5.25, 15.25
    gn = (gnc - gl / 2, gnc + gl / 2)
    gp = (gpc - gl / 2, gpc + gl / 2)
    act_n = (2.0, 8.5, *ACT_Y)
    act_p = (12.0, 18.5, *ACT_Y)

    def gate_rects(g, c):
        return [(g[0], g[1], 1.1, ACT_Y[1]),                 # over channel + end cap
                (min(g[0], c - 0.5), max(g[1], c + 0.5), ACT_Y[1], 7.6)]  # contact pad on field

    contacts = {
        "n_src": (2.8, 3.9, 2.6, 4.4), "n_drn": (6.6, 7.7, 2.6, 4.4),
        "p_drn": (12.8, 13.9, 2.6, 4.4), "p_src": (16.6, 17.7, 2.6, 4.4),
        "g_n": (gnc - 0.3, gnc + 0.3, 6.8, 7.35), "g_p": (gpc - 0.3, gpc + 0.3, 6.8, 7.35),
    }
    metal = {
        "GND": (2.4, 4.3, 0.3, 4.9), "VOUT": (6.2, 14.3, 2.2, 4.8),
        "VDD": (16.2, 18.1, 0.3, 4.9), "VIN": (gnc - 0.5, gpc + 0.5, 6.6, 7.6),
    }
    actives = [act_n, act_p]
    return dict(
        gl=gl, gn=gn, gp=gp, gnc=gnc, gpc=gpc, act_n=act_n, act_p=act_p,
        nwell=(10.5, 20.0, 0.0, 8.0), pside=(0.0, 10.5, 0.0, 8.0),
        gates_n=gate_rects(gn, gnc), gates_p=gate_rects(gp, gpc),
        contacts=contacts, metal=metal,
        fox_x=[(0.0, 2.0), (8.5, 12.0), (18.5, 20.0)],
        iso=rect_complement(DOMAIN, actives),          # isolation (field) regions
    )


def make_ctx(p: ProcessParams, flow: Optional[Flow] = None, faults: Optional[Faults] = None) -> Ctx:
    lay = flow.layout_fn(p) if flow and flow.layout_fn else layout(p)
    return Ctx(p, lay, flow, faults or Faults())


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

def _rects(c: Ctx, rects, mask=None) -> List[Rect]:
    r = rects(c) if callable(rects) else list(rects)
    return c.faults.shift(mask, r)


def deposit(layer, material, thickness=None, top=None, region=None, particles=None):
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        reg = region(c) if callable(region) else (region or [DOMAIN])
        snapshot = w.solids()
        cells = conformal_cells(snapshot, reg, DOMAIN, thickness=thickness, top=top,
                                min_top_gap=0.1)
        w.layer(layer, material).solids.extend(cells)
        a.grow.extend(cells)
        if particles:
            a.particles.append(ParticleSpec(particles[0], particles[1], None, 90, snapshot))
    return act


def strip(layer, mode="etch"):
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        lay = w.remove(layer)
        if lay:
            a.ghosts += [(lay.material, s, mode) for s in lay.solids]
    return act


def pattern(layer, keep, particles=True, mask=None):
    """Etch `layer` everywhere except footprint rects keep(ctx)."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        if layer not in w.layers:
            return
        lay = w.layers[layer]
        snapshot = w.solids()
        keep_r = _rects(c, keep, mask)
        kept_all = []
        for s in lay.solids:
            kept, removed = split_box(s, keep_r)
            kept_all += kept
            a.ghosts += [(lay.material, r, "etch") for r in removed]
        lay.solids = kept_all
        if particles:
            a.particles.append(ParticleSpec("plasma", (1.0, 0.45, 0.85, 1), None, 140, snapshot))
    return act


def expose(keep, mask_z=3.0, mask=None):
    """Positive resist: area outside `keep` (mask openings) becomes exposed."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        lay = w.layers["resist"]
        snapshot = w.solids()
        keep_r = _rects(c, keep, mask)
        kept_all, exp = [], []
        for s in lay.solids:
            kept, removed = split_box(s, keep_r)
            kept_all += kept
            exp += removed
        lay.solids = kept_all
        w.layer("resist_exp", "resist").solids = exp
        a.recolor["resist_exp"] = "resist"
        w.layers["resist_exp"].material = "resist_exp"
        a.mask = MaskSpec(keep_r, mask_z)
        a.particles.append(ParticleSpec("uv", (0.65, 0.35, 1.0, 1), rect_complement(DOMAIN, keep_r),
                                        160, snapshot))
    return act


def develop():
    return strip("resist_exp", "etch")


def coat():
    return deposit("resist", "resist", thickness=0.45)


def implant(layer, material, rects, z0=-0.3, ion_color=(1, 0.9, 0.2, 1),
            species=None, dose=None, energy_kev=None):
    """Ion implantation into rects(ctx); records a DopantEvent when species is given.

    dose may be a number or a callable(ctx) (e.g. tied to a UI parameter).
    """
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        rs = rects(c)
        new = [Solid.box(r[0], r[1], r[2], r[3], z0, 0.0) for r in rs]
        w.layer(layer, material).solids.extend(new)
        a.fade_in.extend(new)
        a.particles.append(ParticleSpec("ion", ion_color, None, 220, snapshot))
        if species:
            d = dose(c) if callable(dose) else dose
            pol = "n" if species in ("P", "As", "Sb") else "p"
            w.dopants.append(DopantEvent(w.current_step, species, pol, float(d or 0.0),
                                         float(energy_kev or 0.0), rs, 0.0))
    return act


def implant_solids(layer, material, solids_fn, ion_color=(1, 0.9, 0.2, 1), species=None, dose=None,
                   energy_kev=None, region=None):
    """Ion implantation whose doped volume follows the topography (e.g. only the
    fins, not the oxide between them).  solids_fn(ctx) gives the doped solids;
    region(ctx) the implanted footprint recorded in the DopantEvent."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        new = solids_fn(c)
        w.layer(layer, material).solids.extend(new)
        a.fade_in.extend(new)
        a.particles.append(ParticleSpec("ion", ion_color, None, 220, snapshot))
        if species:
            d = dose(c) if callable(dose) else dose
            pol = "n" if species in ("P", "As", "Sb") else "p"
            rs = region(c) if region else [s.footprint for s in new]
            w.dopants.append(DopantEvent(w.current_step, species, pol, float(d or 0.0),
                                         float(energy_kev or 0.0), rs, 0.0))
    return act


def add_solids(layer, material, solids_fn, mode="grow", particles=None):
    """Add explicit solids (epitaxy, liners, ...) with a grow or fade-in animation."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        new = solids_fn(c)
        w.layer(layer, material).solids.extend(new)
        (a.grow if mode == "grow" else a.fade_in).extend(new)
        if particles:
            a.particles.append(ParticleSpec(particles[0], particles[1], None, 90, snapshot))
    return act


def convert(src, dst, material, keep_rects, mode="fade"):
    """Move the parts of layer `src` inside keep_rects(ctx) into layer `dst`
    with a new material (e.g. SiGe under the spacers -> inner spacer)."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        lay = w.layers.get(src)
        if not lay:
            return
        rects = keep_rects(c)
        stay, moved = [], []
        for s in lay.solids:
            inside, outside = split_box(s, rects)
            moved += inside
            stay += outside
        lay.solids = stay
        if not stay:
            w.remove(src)
        a.ghosts += [(lay.material, s, "fade") for s in moved]
        w.layer(dst, material).solids.extend(moved)
        a.fade_in.extend(moved)
    return act


def recolor(layer, material):
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        if layer in w.layers:
            a.recolor[layer] = w.layers[layer].material
            w.layers[layer].material = material
    return act


def glow(color=(1.0, 0.55, 0.2)):
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        a.glow = color
    return act


def anneal(temp_c: float, time_s: float, color=(1.0, 0.45, 0.15)):
    """Thermal step: glow animation + ThermalEvent record (thermal budget)."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        a.glow = color
        w.thermal.append(ThermalEvent(w.current_step, temp_c, time_s))
    return act


def replace_layer(layer, material, solids_fn, anchor=None, mode="fade", requires=None):
    """Swap a layer's geometry (e.g. diffusion during an anneal).

    requires: layer that must exist for the replacement to happen (an anneal
    only diffuses dopants that were actually implanted)."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        if requires and not w.has(requires):
            return
        old = w.remove(layer)
        if old:
            a.ghosts += [(old.material, s, "fade") for s in old.solids]
        new = solids_fn(c)
        for s in new:
            s.anchor = anchor
        w.layer(layer, material).solids = new
        (a.grow if mode == "grow" else a.fade_in).extend(new)
    return act


def recess(layers, rects, z_top, particles=True, mask=None):
    """Etch *into* existing solids (e.g. silicon trenches): inside rects(ctx),
    every box of `layers` is cut down to z_top."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        rs = _rects(c, rects, mask)
        snapshot = w.solids()
        for name in layers:
            lay = w.layers.get(name)
            if not lay:
                continue
            out = []
            for s in lay.solids:
                if not s.is_box or s.zmax <= z_top:
                    out.append(s)
                    continue
                trench, rest = split_box(s, rs)      # (inside rects, outside rects)
                out += rest
                for t in trench:
                    if t.zmin < z_top:
                        out.append(Solid.box(t.xmin, t.xmax, t.y0, t.y1, t.zmin, z_top))
                    a.ghosts.append((lay.material, Solid.box(t.xmin, t.xmax, t.y0, t.y1,
                                                             max(t.zmin, z_top), t.zmax), "etch"))
            lay.solids = out
        if particles:
            a.particles.append(ParticleSpec("plasma", (1.0, 0.45, 0.85, 1), rs, 160, snapshot))
    return act


def cmp(layers, z_top, pad=True):
    """Chemical-mechanical polish: everything in `layers` above z_top is removed."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        for name in layers:
            lay = w.layers.get(name)
            if not lay:
                continue
            out = []
            for s in lay.solids:
                if s.zmax <= z_top + 1e-9 or not s.is_box:
                    out.append(s)
                    continue
                if s.zmin < z_top:
                    out.append(Solid.box(s.xmin, s.xmax, s.y0, s.y1, s.zmin, z_top))
                a.ghosts.append((lay.material, Solid.box(s.xmin, s.xmax, s.y0, s.y1,
                                                         max(s.zmin, z_top), s.zmax), "etch"))
            lay.solids = out
            if not out:
                w.remove(name)
        if pad:
            a.pad = z_top
    return act


# geometry recipes shared by flows ---------------------------------------------

def actives(c: Ctx) -> List[Rect]:
    return [c.lay["act_n"], c.lay["act_p"]]


def gate_span(c: Ctx, key: str) -> Tuple[float, float]:
    """Actual gate x-extent ("gn"/"gp"), honouring a POLY-mask misalignment so
    self-aligned implants follow the real gate."""
    g = c.lay[key]
    dx = c.faults.misalign.get("POLY", (0.0, 0.0))[0]
    return (g[0] + dx, g[1] + dx)


SPACER_W = 0.22          # spacer foot width (display units)
GATE_Y = (1.1, ACT_Y[1])  # y-extent of the gate body (where sidewall spacers sit)


def spacer_span(c: Ctx, key: str) -> Tuple[float, float]:
    """Gate x-extent widened by the sidewall spacers (mask for the deep S/D implant)."""
    g = gate_span(c, key)
    return (g[0] - SPACER_W, g[1] + SPACER_W)


def _gate_top(w: Wafer, layer: str, g: Tuple[float, float]) -> float:
    tops = [s.zmax for s in w.layers[layer].solids
            if s.xmin >= g[0] - 1e-6 and s.xmax <= g[1] + 1e-6] if layer in w.layers else []
    return max(tops) if tops else 0.4


def _spacer_prism(edge: float, side: int, z0: float, z1: float, w: float, nseg: int = 6,
                  ys: Tuple[float, float] = GATE_Y) -> Solid:
    """Quarter-ellipse spacer cross-section against a gate edge (side=-1 left, +1 right)."""
    import math
    h = z1 - z0
    arc = [(edge + side * w * math.sin(t), z0 + h * math.cos(t))
           for t in (math.pi / 2 * k / nseg for k in range(nseg + 1))]
    if side < 0:      # CCW: foot -> corner -> top -> arc back to foot
        pts = [(edge - w, z0), (edge, z0)] + arc[:-1]
    else:
        pts = [(edge, z0), (edge + w, z0)] + list(reversed(arc))[1:-1] + [(edge, z1)]
    s = Solid(pts, *ys)
    s.anchor = z0
    return s


def gate_keys(c: Ctx) -> List[Tuple[str, str]]:
    """(gate layer, layout span key) of every gate (one shared gate in a CFET)."""
    return c.lay.get("gate_keys", [("gate_n", "gn"), ("gate_p", "gp")])


def _bands(c: Ctx) -> List[Tuple[float, float, float]]:
    """(y0, y1, z0) strips along the gate: where the spacer foot sits.  Planar
    devices have one strip on the silicon surface; in a FinFET the spacer reaches
    down to the STI between the fins."""
    return c.lay.get("spacer_bands", [(GATE_Y[0], GATE_Y[1], 0.0)])


def spacer_deposit(thickness=SPACER_W):
    """Conformal spacer film: planar film everywhere plus sidewall coverage of the gates."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        snapshot = w.solids()
        cells = conformal_cells(snapshot, [DOMAIN], DOMAIN, thickness=thickness * 0.6)
        side = []
        for layer, key in gate_keys(c):
            g = gate_span(c, key)
            top = _gate_top(w, layer, g)
            for x0, x1 in ((g[0] - thickness, g[0]), (g[1], g[1] + thickness)):
                for y0, y1, z0 in _bands(c):
                    b = Solid.box(x0, x1, y0, y1, z0, top + thickness * 0.6)
                    b.anchor = z0
                    side.append(b)
        w.layer("spacer_film", "spacer").solids = cells + side
        a.grow.extend(cells + side)
        a.particles.append(ParticleSpec("depo", (0.5, 0.85, 0.6, 1), None, 90, snapshot))
    return act


def spacer_etchback():
    """Anisotropic etch-back: the film is cleared from flat surfaces, leaving
    rounded spacers on the gate sidewalls."""
    def act(w: Wafer, c: Ctx, a: PhaseAnim):
        film = w.remove("spacer_film")
        if film:
            a.ghosts += [("spacer", s, "etch") for s in film.solids]
        sp = []
        for layer, key in gate_keys(c):
            g = gate_span(c, key)
            top = _gate_top(w, layer, g)
            for y0, y1, z0 in _bands(c):
                sp.append(_spacer_prism(g[0], -1, z0, top, SPACER_W, ys=(y0, y1)))
                sp.append(_spacer_prism(g[1], +1, z0, top, SPACER_W, ys=(y0, y1)))
        w.layer("spacer", "spacer").solids = sp
        a.fade_in.extend(sp)
        a.particles.append(ParticleSpec("plasma", (1.0, 0.45, 0.85, 1), None, 140, w.solids()))
    return act


def sd_rects(act, g) -> List[Rect]:
    return [(act[0], g[0], act[2], act[3]), (g[1], act[1], act[2], act[3])]


def split_gates(w: Wafer, c: Ctx, a: PhaseAnim):
    lay = w.remove("poly")
    if not lay:
        return
    w.layer("gate_n", lay.material).solids = [s for s in lay.solids if s.xmax < 10.5]
    w.layer("gate_p", lay.material).solids = [s for s in lay.solids if s.xmin >= 10.5]


def sd_annealed(act, g, grow=0.15, depth=-0.42):
    left = (act[0], g[0] + grow, act[2], act[3])
    right = (g[1] - grow, act[1], act[2], act[3])
    return [Solid.box(r[0], r[1], r[2], r[3], depth, 0.0) for r in (left, right)]


def gates(c):
    return c.lay["gates_n"] + c.lay["gates_p"]


def contacts(c):
    return list(c.lay["contacts"].values())


def metal(c):
    return list(c.lay["metal"].values())


def litho(mask_keep, mask=None) -> List[Phase]:
    return [
        Phase("旋涂光刻胶", "Spin-coat photoresist", 1.2, [coat()]),
        Phase("掩膜对准 + 紫外曝光", "Mask align + UV exposure", 2.2, [expose(mask_keep, mask=mask)]),
        Phase("显影：去除曝光区光刻胶", "Develop: exposed resist dissolves", 1.2, [develop()]),
    ]


def quiz(qzh, qen, opts, ans, ezh, een) -> Quiz:
    return Quiz((qzh, qen), opts, ans, (ezh, een))


# --------------------------------------------------------------------------
# Formatting helpers for parameter tables
# --------------------------------------------------------------------------

def sci(v: float, unit: str = "") -> str:
    m, e = f"{v:.2e}".split("e")
    return f"{m}e{int(e)} {unit}".strip()


_SUM_CACHE: dict = {}


def summarize_cached(p: ProcessParams, features: FrozenSet[str] = frozenset()):
    key = (tuple(sorted(vars(p).items())), frozenset(features))
    if key not in _SUM_CACHE:
        _SUM_CACHE.clear()
        _SUM_CACHE[key] = summarize(p, features)
    return _SUM_CACHE[key]


def nwe_text(c: Ctx) -> str:
    """NMOS narrow-width Vt shift caused by the flow's isolation scheme."""
    s = summarize_cached(c.p, c.features)
    base = summarize_cached(c.p, frozenset(c.features) - {"locos", "sti"})   # same, minus isolation
    return f"{(s.vtn - base.vtn) * 1e3:+.0f} mV  (Wn = {c.p.wn_um:.1f} µm)"


def vt_text(c: Ctx, which: str) -> str:
    s = summarize_cached(c.p, c.features)
    return f"{(s.vtn if which == 'n' else s.vtp):+.3f} V"


# --------------------------------------------------------------------------
# Building state
# --------------------------------------------------------------------------

def run_phase(w: Wafer, ctx: Ctx, phase: Phase) -> PhaseAnim:
    anim = PhaseAnim()
    for act in phase.actions:
        act(w, ctx, anim)
    return anim


def is_skipped(ctx: Ctx, step: Step) -> bool:
    return step.key in ctx.faults.skip


def build_until(ctx: Ctx, step_index: int) -> Wafer:
    """Wafer state after completing ctx.flow.steps[0..step_index] (inclusive)."""
    w = Wafer()
    for st in ctx.flow.steps[: step_index + 1]:
        if is_skipped(ctx, st):
            continue
        w.current_step = st.key
        for ph in st.phases:
            run_phase(w, ctx, ph)
    return w
