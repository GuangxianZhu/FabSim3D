"""Pure-python solid geometry for the layered wafer model.

Every solid is a convex polygon in the x-z plane (cross-section) extruded along
y.  Boxes are just 4-vertex polygons.  This keeps the cross-section view (cut
along y) trivially correct: clipping a solid at y=c only changes y0/y1.

Coordinates (display units, roughly microns laterally, exaggerated vertically):
    x : 0 .. 20   (NMOS left, PMOS right)
    y : 0 .. 8    (device width direction; the cut plane moves along y)
    z : up; silicon surface at z = 0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple

Rect = Tuple[float, float, float, float]   # x0, x1, y0, y1
EPS = 1e-6


@dataclass(eq=False)
class Solid:
    poly: List[Tuple[float, float]]       # CCW (x, z) vertices, convex
    y0: float
    y1: float
    anchor: float | None = None           # z anchor used by grow animations

    @staticmethod
    def box(x0, x1, y0, y1, z0, z1) -> "Solid":
        return Solid([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], y0, y1)

    @property
    def is_box(self) -> bool:
        if len(self.poly) != 4:
            return False
        xs = {round(p[0], 9) for p in self.poly}
        zs = {round(p[1], 9) for p in self.poly}
        return len(xs) == 2 and len(zs) == 2

    @property
    def xmin(self):
        return min(p[0] for p in self.poly)

    @property
    def xmax(self):
        return max(p[0] for p in self.poly)

    @property
    def zmin(self):
        return min(p[1] for p in self.poly)

    @property
    def zmax(self):
        return max(p[1] for p in self.poly)

    @property
    def footprint(self) -> Rect:
        return (self.xmin, self.xmax, self.y0, self.y1)

    def top_at(self, x: float) -> float | None:
        """Highest z of the polygon at abscissa x (None if outside)."""
        if x < self.xmin - EPS or x > self.xmax + EPS:
            return None
        best = None
        n = len(self.poly)
        for i in range(n):
            (xa, za), (xb, zb) = self.poly[i], self.poly[(i + 1) % n]
            lo, hi = min(xa, xb), max(xa, xb)
            if x < lo - EPS or x > hi + EPS:
                continue
            if abs(xb - xa) < EPS:
                z = max(za, zb)
            else:
                z = za + (zb - za) * (x - xa) / (xb - xa)
            best = z if best is None else max(best, z)
        return best

    def contains_xy(self, x: float, y: float) -> bool:
        return self.xmin - EPS <= x <= self.xmax + EPS and self.y0 - EPS <= y <= self.y1 + EPS

    def scaled_z(self, anchor: float, s: float) -> "Solid":
        poly = [(x, anchor + (z - anchor) * s) for x, z in self.poly]
        return Solid(poly, self.y0, self.y1, self.anchor)

    def with_box_footprint(self, r: Rect) -> "Solid":
        """Box solid restricted to footprint r (only valid for boxes)."""
        return Solid.box(r[0], r[1], r[2], r[3], self.zmin, self.zmax)


# --------------------------------------------------------------------------
# Rectangle algebra (axis aligned, in the x-y plane)
# --------------------------------------------------------------------------

def rect_area(r: Rect) -> float:
    return max(0.0, r[1] - r[0]) * max(0.0, r[3] - r[2])


def rect_intersect(a: Rect, b: Rect) -> Rect | None:
    r = (max(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]))
    if r[1] - r[0] <= EPS or r[3] - r[2] <= EPS:
        return None
    return r


def _breaks(vals: Iterable[float]) -> List[float]:
    out: List[float] = []
    for v in sorted(vals):
        if not out or v - out[-1] > EPS:
            out.append(v)
    return out


def _inside_any(x: float, y: float, rects: Sequence[Rect]) -> bool:
    return any(r[0] - EPS <= x <= r[1] + EPS and r[2] - EPS <= y <= r[3] + EPS for r in rects)


def grid_cells(domain: Rect, rects: Sequence[Rect], extra_x=(), extra_y=()):
    """Split domain at every rect edge; yields cells (x0,x1,y0,y1)."""
    xs = _breaks([domain[0], domain[1], *extra_x,
                  *[v for r in rects for v in (r[0], r[1]) if domain[0] < v < domain[1]]])
    ys = _breaks([domain[2], domain[3], *extra_y,
                  *[v for r in rects for v in (r[2], r[3]) if domain[2] < v < domain[3]]])
    xs = [x for x in xs if domain[0] - EPS <= x <= domain[1] + EPS]
    ys = [y for y in ys if domain[2] - EPS <= y <= domain[3] + EPS]
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            yield (xs[i], xs[i + 1], ys[j], ys[j + 1])


def merge_cells(cells: List[Tuple[Rect, tuple]]) -> List[Tuple[Rect, tuple]]:
    """Merge neighbouring cells with identical payload (row-wise then column-wise)."""
    # row merge (along x)
    rows: dict = {}
    for r, payload in cells:
        rows.setdefault((round(r[2], 9), round(r[3], 9)), []).append((r, payload))
    merged = []
    for key in sorted(rows):
        row = sorted(rows[key], key=lambda c: c[0][0])
        cur = None
        for r, pl in row:
            if cur and abs(cur[0][1] - r[0]) < EPS and cur[1] == pl:
                cur = ((cur[0][0], r[1], cur[0][2], cur[0][3]), pl)
            else:
                if cur:
                    merged.append(cur)
                cur = (r, pl)
        if cur:
            merged.append(cur)
    # column merge (along y) for identical x-spans
    cols: dict = {}
    for r, pl in merged:
        cols.setdefault((round(r[0], 9), round(r[1], 9), pl), []).append(r)
    out = []
    for (x0, x1, pl), rs in cols.items():
        rs.sort(key=lambda r: r[2])
        cur = None
        for r in rs:
            if cur and abs(cur[3] - r[2]) < EPS:
                cur = (cur[0], cur[1], cur[2], r[3])
            else:
                if cur:
                    out.append((cur, pl))
                cur = r
        if cur:
            out.append((cur, pl))
    return out


def rect_complement(domain: Rect, holes: Sequence[Rect]) -> List[Rect]:
    cells = []
    for c in grid_cells(domain, holes):
        cx, cy = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2
        if not _inside_any(cx, cy, holes):
            cells.append((c, ()))
    return [r for r, _ in merge_cells(cells)]


def split_box(solid: Solid, keep: Sequence[Rect]) -> Tuple[List[Solid], List[Solid]]:
    """Split a box solid by footprint: (parts inside keep, parts outside)."""
    fp = solid.footprint
    kept, removed = [], []
    for c in grid_cells(fp, keep):
        cx, cy = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2
        (kept if _inside_any(cx, cy, keep) else removed).append((c, ()))
    return ([solid.with_box_footprint(r) for r, _ in merge_cells(kept)],
            [solid.with_box_footprint(r) for r, _ in merge_cells(removed)])


def surface_height(solids: Iterable[Solid], x: float, y: float, floor: float = 0.0) -> float:
    h = None
    for s in solids:
        if s.y0 - EPS <= y <= s.y1 + EPS:
            t = s.top_at(x)
            if t is not None and (h is None or t > h):
                h = t
    return floor if h is None else h


def conformal_cells(solids: List[Solid], region: Sequence[Rect], domain: Rect,
                    thickness: float | None = None, top: float | None = None,
                    min_top_gap: float = 0.0) -> List[Solid]:
    """Boxes that sit on the current topography inside `region`.

    Either a constant `thickness` (conformal film) or a fixed `top` (planarised
    film).  With `top`, cells whose surface is higher than top get
    `min_top_gap` thickness instead.
    """
    xs_extra, ys_extra = [], []
    for s in solids:
        xs_extra += [p[0] for p in s.poly]
        ys_extra += [s.y0, s.y1]
    cells = []
    for c in grid_cells(domain, list(region), xs_extra, ys_extra):
        cx, cy = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2
        if not _inside_any(cx, cy, region):
            continue
        z0 = surface_height(solids, cx, cy)
        z1 = z0 + thickness if thickness is not None else max(top, z0 + min_top_gap)
        cells.append((c, (round(z0, 6), round(z1, 6))))
    out = []
    for r, (z0, z1) in merge_cells(cells):
        s = Solid.box(r[0], r[1], r[2], r[3], z0, z1)
        s.anchor = z0
        out.append(s)
    return out
