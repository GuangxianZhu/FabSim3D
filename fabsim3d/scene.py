"""Panda3D rendering of the wafer: layers, animations, particles, labels, carriers."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from panda3d.core import (Geom, GeomLines, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, NodePath, TextNode,
                          TransparencyAttrib, Vec4)

from . import i18n
from .geometry import Solid, surface_height
from .materials import mat
from .process_flow import (DOMAIN, REGION_LABELS, TERMINAL_LABELS, PhaseAnim,
                           Wafer)

EDGE_COLOR = (0.08, 0.08, 0.10, 0.55)


def _ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _lerp4(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


def build_solids_node(name: str, items: List[Tuple[Solid, tuple]], cut_y: float,
                      edges: bool) -> NodePath:
    """One GeomNode with flat-shaded triangles (+ optional edge lines)."""
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    nw = GeomVertexWriter(vdata, "normal")
    cw = GeomVertexWriter(vdata, "color")
    tris = GeomTriangles(Geom.UHStatic)
    ldata = GeomVertexData(name + "_e", GeomVertexFormat.getV3c4(), Geom.UHStatic)
    lvw = GeomVertexWriter(ldata, "vertex")
    lcw = GeomVertexWriter(ldata, "color")
    lines = GeomLines(Geom.UHStatic)
    nv = 0
    nl = 0

    def quad(p, n, c):
        nonlocal nv
        ax, ay, az = (p[1][i] - p[0][i] for i in range(3))
        bx, by, bz = (p[2][i] - p[0][i] for i in range(3))
        cr = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
        if cr[0] * n[0] + cr[1] * n[1] + cr[2] * n[2] < 0:
            p = p[::-1]
        for v in p:
            vw.addData3(*v)
            nw.addData3(*n)
            cw.addData4(*c)
        tris.addVertices(nv, nv + 1, nv + 2)
        tris.addVertices(nv, nv + 2, nv + 3)
        nv += 4

    def seg(a, b):
        nonlocal nl
        lvw.addData3(*a)
        lvw.addData3(*b)
        lcw.addData4(*EDGE_COLOR)
        lcw.addData4(*EDGE_COLOR)
        lines.addVertices(nl, nl + 1)
        nl += 2

    for s, col in items:
        y0 = max(s.y0, cut_y)
        y1 = s.y1
        if y1 - y0 <= 1e-4 or s.zmax - s.zmin <= 1e-5:
            continue
        poly = s.poly
        npt = len(poly)
        # caps (fan) – front cap faces -y, back cap +y
        base = nv
        for x, z in poly:
            vw.addData3(x, y0, z)
            nw.addData3(0, -1, 0)
            cw.addData4(*col)
        for i in range(1, npt - 1):
            tris.addVertices(base, base + i, base + i + 1)
        nv += npt
        base = nv
        for x, z in poly:
            vw.addData3(x, y1, z)
            nw.addData3(0, 1, 0)
            cw.addData4(*col)
        for i in range(1, npt - 1):
            tris.addVertices(base, base + i + 1, base + i)
        nv += npt
        # sides
        for i in range(npt):
            (xa, za), (xb, zb) = poly[i], poly[(i + 1) % npt]
            dx, dz = xb - xa, zb - za
            ln = math.hypot(dx, dz)
            if ln < 1e-9:
                continue
            n = (dz / ln, 0, -dx / ln)
            quad([(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)], n, col)
            if edges:
                seg((xa, y0, za), (xb, y0, zb))
                seg((xa, y1, za), (xb, y1, zb))
                seg((xa, y0, za), (xa, y1, za))

    gnode = GeomNode(name)
    if nv:
        g = Geom(vdata)
        g.addPrimitive(tris)
        gnode.addGeom(g)
    np_ = NodePath(gnode)
    if edges and nl:
        lg = Geom(ldata)
        lg.addPrimitive(lines)
        ln_node = GeomNode(name + "_edges")
        ln_node.addGeom(lg)
        enp = np_.attachNewNode(ln_node)
        enp.setLightOff()
        enp.setTransparency(TransparencyAttrib.MAlpha)
        enp.setDepthOffset(1)
    return np_


def _unit_cube() -> NodePath:
    s = Solid.box(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5)
    return build_solids_node("cube", [(s, (1, 1, 1, 1))], -99, False)


# --------------------------------------------------------------------------

class Particle:
    __slots__ = ("np", "x", "y", "z", "vz", "stop", "life", "kind")


class WaferScene:
    def __init__(self, base, parent: NodePath):
        self.base = base
        self.root = parent.attachNewNode("wafer")
        self.layer_nodes: Dict[str, NodePath] = {}
        self.ghost_node: Optional[NodePath] = None
        self.mask_node: Optional[NodePath] = None
        self.fx = parent.attachNewNode("fx")
        self.fx.setLightOff()
        self.labels_root = parent.attachNewNode("labels")
        self.carrier_root = parent.attachNewNode("carriers")
        self.carrier_root.setLightOff()
        self.cube = _unit_cube()
        self.wafer: Optional[Wafer] = None
        self.cut_y = 0.0
        self.edges = True
        self.show_labels = True
        self.anim: Optional[PhaseAnim] = None
        self.anim_t = 0.0
        self.anim_dur = 1.0
        self.particles: List[Particle] = []
        self.spawn_acc = 0.0
        self.terminal_mode = False
        self.sim_values: Optional[dict] = None
        self.carriers: list = []
        self.channel_nodes: Dict[str, NodePath] = {}
        self.ctx = None

    # ---------------------------------------------------------------- state
    def set_wafer(self, wafer: Wafer, ctx, terminal_mode: bool = False):
        self.finish_anim()
        self.wafer = wafer
        self.ctx = ctx
        self.terminal_mode = terminal_mode
        self.rebuild_all()

    def rebuild_all(self):
        for n in list(self.layer_nodes):
            self.layer_nodes.pop(n).removeNode()
        if self.wafer:
            for name in self.wafer.layers:
                self._rebuild_layer(name)
        self._rebuild_ghosts()
        self.rebuild_labels()
        self._rebuild_channels()

    def _layer_items(self, name: str) -> List[Tuple[Solid, tuple]]:
        layer = self.wafer.layers[name]
        m = mat(layer.material)
        col = m.color
        a = self.anim
        e = _ease(self.anim_t) if a else 1.0
        if a and name in a.recolor:
            col = _lerp4(mat(a.recolor[name]).color, col, e)
        items = []
        grow = set(map(id, a.grow)) if a else set()
        fade = set(map(id, a.fade_in)) if a else set()
        for s in layer.solids:
            c = col
            sol = s
            if id(s) in grow:
                anchor = s.anchor if s.anchor is not None else s.zmin
                sol = s.scaled_z(anchor, max(e, 0.002))
            if id(s) in fade:
                c = (c[0], c[1], c[2], c[3] * e)
            items.append((sol, c))
        return items

    def _style(self, np_: NodePath, material: str, alpha: bool):
        np_.setDepthOffset(mat(material).priority)
        if alpha:
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setDepthWrite(mat(material).color[3] >= 0.99)
            np_.setTwoSided(False)

    def _rebuild_layer(self, name: str):
        old = self.layer_nodes.pop(name, None)
        if old:
            old.removeNode()
        if name not in self.wafer.layers:
            return
        items = self._layer_items(name)
        node = build_solids_node(name, items, self.cut_y, self.edges)
        node.reparentTo(self.root)
        alpha = any(c[3] < 0.999 for _, c in items)
        self._style(node, self.wafer.layers[name].material, alpha)
        self.layer_nodes[name] = node

    def _rebuild_ghosts(self):
        if self.ghost_node:
            self.ghost_node.removeNode()
            self.ghost_node = None
        if not self.anim or not self.anim.ghosts:
            return
        e = _ease(self.anim_t)
        self.ghost_node = self.root.attachNewNode("ghosts")
        by_mat: Dict[str, list] = {}
        for material, s, mode in self.anim.ghosts:
            col = mat(material).color
            if mode == "etch":
                if e >= 0.999:
                    continue
                sol = s.scaled_z(s.zmin, 1 - e)
            else:
                sol = s
                col = (col[0], col[1], col[2], col[3] * (1 - e))
            by_mat.setdefault(material, []).append((sol, col))
        for material, items in by_mat.items():
            n = build_solids_node("ghost_" + material, items, self.cut_y, self.edges)
            n.reparentTo(self.ghost_node)
            self._style(n, material, True)

    # ---------------------------------------------------------------- anim
    def start_anim(self, anim: PhaseAnim, duration: float):
        self.anim = anim
        self.anim_t = 0.0
        self.anim_dur = max(duration, 0.05)
        self.spawn_acc = 0.0
        if anim.mask:
            self._build_mask(anim.mask)
        self._refresh_anim_layers()

    def _anim_layers(self):
        a = self.anim
        names = set(a.recolor)
        ids = set(map(id, a.grow)) | set(map(id, a.fade_in))
        for name, layer in self.wafer.layers.items():
            if any(id(s) in ids for s in layer.solids):
                names.add(name)
        return names

    def _refresh_anim_layers(self):
        # layers added/removed by the phase must exist/disappear
        for name in list(self.layer_nodes):
            if name not in self.wafer.layers:
                self.layer_nodes.pop(name).removeNode()
        for name in self.wafer.layers:
            if name not in self.layer_nodes or name in self._anim_layers():
                self._rebuild_layer(name)
        self._rebuild_ghosts()
        self.rebuild_labels()

    def update(self, dt: float, speed: float = 1.0) -> bool:
        """Advance animation; returns True when the current phase finished."""
        done = False
        if self.anim:
            self.anim_t += dt * speed / self.anim_dur
            if self.anim_t >= 1.0:
                self.anim_t = 1.0
                done = True
            for name in self._anim_layers():
                self._rebuild_layer(name)
            self._rebuild_ghosts()
            self._update_mask()
            self._update_glow()
            self._spawn_particles(dt * speed)
        self._update_particles(dt * speed)
        self._update_carriers(dt)
        if done:
            self.finish_anim()
        return done

    def finish_anim(self):
        if not self.anim:
            return
        self.anim_t = 1.0
        self.anim = None
        if self.mask_node:
            self.mask_node.removeNode()
            self.mask_node = None
        self.root.clearColorScale()
        if self.wafer:
            self.rebuild_all()

    def clear_particles(self):
        for p in self.particles:
            p.np.removeNode()
        self.particles.clear()

    # ---------------------------------------------------------------- mask / glow
    def _build_mask(self, spec):
        if self.mask_node:
            self.mask_node.removeNode()
        self.mask_node = self.base.render.attachNewNode("mask")
        x0, x1, y0, y1 = DOMAIN
        z = spec.z
        glass = Solid.box(x0 - 0.5, x1 + 0.5, y0 - 0.5, y1 + 0.5, z, z + 0.08)
        g = build_solids_node("glass", [(glass, (0.75, 0.9, 1.0, 0.25))], -99, True)
        g.reparentTo(self.mask_node)
        g.setTransparency(TransparencyAttrib.MAlpha)
        g.setDepthWrite(False)
        chrome = [Solid.box(r[0], r[1], r[2], r[3], z + 0.08, z + 0.12) for r in spec.chrome]
        c = build_solids_node("chrome", [(s, (0.12, 0.12, 0.14, 0.92)) for s in chrome], -99, False)
        c.reparentTo(self.mask_node)
        c.setTransparency(TransparencyAttrib.MAlpha)
        self.mask_node.setAlphaScale(0.0)

    def _update_mask(self):
        if not self.mask_node:
            return
        t = self.anim_t
        a = min(1.0, t / 0.15) if t < 0.85 else max(0.0, (1 - t) / 0.15)
        self.mask_node.setAlphaScale(a)
        self.mask_node.setZ((1 - min(1.0, t / 0.2)) * 1.5)

    def _update_glow(self):
        g = self.anim.glow if self.anim else None
        if not g:
            return
        k = 0.55 * math.sin(math.pi * self.anim_t)
        self.root.setColorScale(1 + (g[0] - 1) * k + 0.15 * k, 1 + (g[1] - 1) * k, 1 + (g[2] - 1) * k, 1)

    # ---------------------------------------------------------------- particles
    def _spawn_particles(self, dt):
        if not self.anim or self.anim_t > 0.85:
            return
        for spec in self.anim.particles:
            regions = spec.region or [DOMAIN]
            areas = [max(1e-6, (r[1] - r[0]) * max(0.0, r[3] - max(r[2], self.cut_y))) for r in regions]
            total = sum(areas)
            if total <= 1e-5:
                continue
            n_float = spec.rate * dt * min(1.0, total / 160.0) + self.spawn_acc
            n = int(n_float)
            self.spawn_acc = n_float - n
            for _ in range(n):
                r = random.choices(regions, weights=areas)[0]
                x = random.uniform(r[0], r[1])
                y = random.uniform(max(r[2], self.cut_y), r[3])
                self._spawn_one(spec, x, y)

    def _spawn_one(self, spec, x, y):
        p = Particle()
        p.kind = spec.kind
        p.x, p.y = x, y
        p.stop = surface_height(spec.stop_solids, x, y)
        if spec.kind == "uv":
            p.z = (self.anim.mask.z if self.anim.mask else 4.0)
            p.vz = -9.0
            scale = (0.035, 0.035, 0.45)
        elif spec.kind == "ion":
            p.z = 5.0
            p.vz = -11.0
            scale = (0.07, 0.07, 0.07)
        elif spec.kind == "plasma":
            p.z = 4.0
            p.vz = -6.0
            scale = (0.08, 0.08, 0.08)
        else:  # depo
            p.z = 4.0
            p.vz = -4.5
            scale = (0.09, 0.09, 0.09)
        p.life = 0.25
        p.np = self.cube.copyTo(self.fx)
        p.np.setScale(*scale)
        p.np.setColor(*spec.color)
        p.np.setPos(x, y, p.z)
        self.particles.append(p)

    def _update_particles(self, dt):
        keep = []
        for p in self.particles:
            if p.z > p.stop:
                p.z = max(p.stop, p.z + p.vz * dt)
                p.np.setZ(p.z + (0.22 if p.kind == "uv" else 0))
                keep.append(p)
            else:
                p.life -= dt
                if p.life <= 0:
                    p.np.removeNode()
                else:
                    p.np.setAlphaScale(p.life / 0.25)
                    p.np.setTransparency(TransparencyAttrib.MAlpha)
                    keep.append(p)
        self.particles = keep

    # ---------------------------------------------------------------- labels
    def _label(self, text: str, pos, scale=0.42, fg=(1, 1, 1, 1), bg=(0, 0, 0, 0.55)):
        tn = TextNode("lbl")
        tn.setText(text)
        tn.setAlign(TextNode.ACenter)
        tn.setTextColor(*fg)
        tn.setCardColor(*bg)
        tn.setCardAsMargin(0.2, 0.2, 0.1, 0.1)
        tn.setCardDecal(True)
        np_ = self.labels_root.attachNewNode(tn)
        np_.setScale(scale)
        np_.setPos(*pos)
        np_.setBillboardPointEye()
        np_.setBin("fixed", 50)
        np_.setDepthTest(False)
        np_.setDepthWrite(False)
        np_.setLightOff()
        return np_

    def rebuild_labels(self):
        for child in self.labels_root.getChildren():
            child.removeNode()
        if not self.show_labels or not self.wafer:
            return
        yf = max(self.cut_y, 0.0) - 0.05
        animating_out = set()
        if self.anim:
            animating_out = {m for m, _, _ in self.anim.ghosts}
        for layer, zh, en, x, z in REGION_LABELS:
            if self.wafer.has(layer) and layer not in animating_out:
                self._label(i18n.pick(zh, en), (x, yf, z), 0.38)
        if self.terminal_mode:
            vals = self.sim_values or {}
            for name, x, y in TERMINAL_LABELS:
                text = name
                key = name.lower()
                if key in vals:
                    text = f"{name} = {vals[key]:.2f} V"
                ly = max(y, self.cut_y + 0.4) if y < 6 else y
                self._label(text, (x, ly, 2.2), 0.36, fg=(1, 0.95, 0.4, 1), bg=(0.05, 0.05, 0.1, 0.75))
            ln, lp = self.ctx.lay["gnc"], self.ctx.lay["gpc"]
            self._label("NMOS", (ln, 8.6, 1.9), 0.42, fg=(1, 0.6, 0.6, 1))
            self._label("PMOS", (lp, 8.6, 1.9), 0.42, fg=(0.6, 0.7, 1, 1))

    # ---------------------------------------------------------------- simulation
    def _rebuild_channels(self):
        for n in self.channel_nodes.values():
            n.removeNode()
        self.channel_nodes.clear()
        for c in self.carriers:
            c[0].removeNode()
        self.carriers = []
        if not (self.terminal_mode and self.sim_values is not None and self.ctx):
            return
        lay = self.ctx.lay
        for key, g, material in (("n", lay["gn"], "channel_n"), ("p", lay["gp"], "channel_p")):
            s = Solid.box(g[0] - 0.12, g[1] + 0.12, 1.5, 6.5, -0.06, -0.005)
            node = build_solids_node("chan_" + key, [(s, mat(material).color[:3] + (1.0,))], self.cut_y, False)
            node.reparentTo(self.carrier_root)
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setDepthOffset(12)
            node.setBin("fixed", 40)
            node.setDepthTest(False)
            self.channel_nodes[key] = node
        rnd = random.Random(1)
        y = max(self.cut_y, 2.6) + 0.02 if self.cut_y > 0 else 3.5
        y = min(y, 4.3)
        # path in (x, z): contact plug -> S/D -> channel -> S/D -> plug
        paths = {
            "n": [(3.35, 1.45), (3.35, -0.15), (lay["gn"][0], -0.035), (lay["gn"][1], -0.035),
                  (7.15, -0.15), (7.15, 1.45)],
            "p": [(17.15, 1.45), (17.15, -0.15), (lay["gp"][1], -0.035), (lay["gp"][0], -0.035),
                  (13.35, -0.15), (13.35, 1.45)],
        }
        colors = {"n": (0.35, 1.0, 1.0, 1), "p": (1.0, 0.65, 0.2, 1)}
        for key in ("n", "p"):
            pts = paths[key]
            segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
            total = sum(segs)
            for i in range(18):
                np_ = self.cube.copyTo(self.carrier_root)
                np_.setScale(0.11)
                np_.setColor(*colors[key])
                np_.setBin("fixed", 45)
                np_.setDepthTest(False)
                np_.setTransparency(TransparencyAttrib.MAlpha)
                self.carriers.append([np_, key, rnd.random(), pts, segs, total, y - 0.08])
        self._apply_sim_alpha()

    def _activity(self, key: str) -> float:
        v = self.sim_values or {}
        cur = max(v.get("i" + key, 0.0), 1e-16)
        return min(max((math.log10(cur) + 10.5) / 7.5, 0.0), 1.0)

    def _apply_sim_alpha(self):
        v = self.sim_values or {}
        for key, node in self.channel_nodes.items():
            node.setAlphaScale(0.85 * v.get("inv_" + key, 0.0))

    def set_sim(self, values: Optional[dict]):
        rebuild = (values is None) != (self.sim_values is None)
        self.sim_values = values
        if rebuild:
            self._rebuild_channels()
        self._apply_sim_alpha()
        self.rebuild_labels()

    def _update_carriers(self, dt):
        if not self.carriers:
            return
        act = {k: self._activity(k) for k in ("n", "p")}
        for c in self.carriers:
            np_, key, s, pts, segs, total, y = c
            a = act[key]
            s = (s + dt * (0.05 + 0.6 * a) * a) % 1.0
            c[2] = s
            d = s * total
            for i, L in enumerate(segs):
                if d <= L or i == len(segs) - 1:
                    t = d / L if L else 0
                    x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t
                    z = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t
                    break
                d -= L
            np_.setPos(x, y, z)
            np_.setAlphaScale(0.15 + 0.85 * a)

    # ---------------------------------------------------------------- options
    def set_cut(self, y: float):
        self.cut_y = y
        if self.wafer:
            self.rebuild_all()

    def set_edges(self, on: bool):
        self.edges = on
        if self.wafer:
            self.rebuild_all()

    def set_labels(self, on: bool):
        self.show_labels = on
        self.rebuild_labels()
