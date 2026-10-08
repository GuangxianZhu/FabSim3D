from fabsim3d.device_model import ProcessParams
from fabsim3d.geometry import Solid, rect_area, rect_complement, split_box, surface_height
import pytest

from fabsim3d.flows import FLOWS
from fabsim3d.process_core import (DOMAIN, Faults, Wafer, build_until, make_ctx, run_phase,
                                   summarize_cached)

LOCOS = FLOWS["locos"]
STI = FLOWS["sti"]


def test_rect_complement_area():
    holes = [(2, 4, 2, 4), (10, 12, 1, 3)]
    comp = rect_complement(DOMAIN, holes)
    total = sum(rect_area(r) for r in comp) + sum(rect_area(h) for h in holes)
    assert abs(total - rect_area(DOMAIN)) < 1e-9


def test_split_box_conserves_volume():
    b = Solid.box(0, 10, 0, 8, 0, 1)
    kept, removed = split_box(b, [(2, 5, 1, 4)])
    area = sum(rect_area(s.footprint) for s in kept + removed)
    assert abs(area - 80) < 1e-9 and abs(sum(rect_area(s.footprint) for s in kept) - 9) < 1e-9


def test_surface_height_prism():
    s = Solid([(0, 0), (4, 0), (2, 2)], 0, 1)
    assert abs(surface_height([s], 1, 0.5) - 1) < 1e-9


@pytest.mark.parametrize("flow", list(FLOWS.values()), ids=list(FLOWS))
def test_every_step_builds_and_has_text(flow):
    ctx = make_ctx(ProcessParams(), flow)
    w = Wafer()
    assert len({s.key for s in flow.steps}) == len(flow.steps)
    for st in flow.steps:
        assert st.title[0] and st.title[1] and st.desc[0] and st.desc[1]
        for zh, en, fn in st.params:
            assert isinstance(fn(ctx), str)
        if st.quiz:
            assert 0 <= st.quiz.answer < len(st.quiz.options)
        for ph in st.phases:
            run_phase(w, ctx, ph)


PLANAR = [f for f in FLOWS.values() if f.key in ("locos", "sti")]
ADVANCED = [f for f in FLOWS.values() if f.key not in ("locos", "sti")]


@pytest.mark.parametrize("flow", PLANAR, ids=[f.key for f in PLANAR])
def test_final_structure(flow):
    w = build_until(make_ctx(ProcessParams(), flow), len(flow.steps) - 1)
    iso = "fox" if flow.key == "locos" else "sti"
    for name in ("sub", "nwell", iso, "gate_n", "gate_p", "nplus", "pplus", "ild", "metal"):
        assert w.has(name), name
    for name in ("resist", "resist_exp", "nitride", "padox", "poly", "nimp"):
        assert not w.has(name), name
    assert w.layers["gate_n"].material == "poly_n"
    assert w.layers["gate_p"].material == "poly_p"


def test_gate_length_changes_layout():
    a = make_ctx(ProcessParams(l_um=0.25)).lay["gl"]
    b = make_ctx(ProcessParams(l_um=3.0)).lay["gl"]
    assert b > a


def _zmax(w, layer):
    return max(s.zmax for s in w.layers[layer].solids)


def test_sti_trench_cmp_and_planarity():
    ctx = make_ctx(ProcessParams(), STI)
    trench = build_until(ctx, STI.step_index("sti_etch"))
    assert min(s.zmax for s in trench.layers["sub"].solids) < -0.3      # trenches cut into Si
    cmp_done = build_until(ctx, STI.step_index("sti_cmp"))
    assert abs(_zmax(cmp_done, "sti") - _zmax(cmp_done, "nitride")) < 1e-9   # stopped on nitride
    stripped = build_until(ctx, STI.step_index("sti_strip"))
    assert 0 < _zmax(stripped, "sti") < 0.1                              # small step height
    poly = build_until(ctx, STI.step_index("poly_dep")).layers["poly"].solids
    assert len({round(s.zmax, 6) for s in poly}) == 1                   # poly lies on a flat surface


def test_ild_cmp_flat():
    ctx = make_ctx(ProcessParams(), STI)
    w = build_until(ctx, STI.step_index("ild_cmp"))
    assert {round(s.zmax, 6) for s in w.layers["ild"].solids} == {1.3}


def test_isolation_narrow_width_effect():
    p = ProcessParams(wn_um=0.5)
    vt_ideal = summarize_cached(p).vtn
    assert summarize_cached(p, frozenset({"locos"})).vtn > vt_ideal     # LOCOS: Vt up
    assert summarize_cached(p, frozenset({"sti"})).vtn < vt_ideal       # STI: inverse NWE


def test_dopant_and_thermal_records():
    w = build_until(make_ctx(ProcessParams(nwell_dose_cm2=5e13), STI), len(STI.steps) - 1)
    species = [(d.step, d.species, d.polarity) for d in w.dopants]
    assert species == [("nwell_implant_he", "P", "n"), ("nldd", "P", "n"), ("pldd", "BF2", "p"),
                       ("nplus_sp", "As", "n"), ("pplus_sp", "BF2", "p")]
    assert w.dopants[0].dose_cm2 == 5e13 and w.dopants[0].step == "nwell_implant_he"
    assert len(w.thermal) >= 3 and all(t.temp_c > 800 for t in w.thermal)


def test_fault_misalignment_and_skip():
    p = ProcessParams()
    ok = build_until(make_ctx(p, LOCOS), len(LOCOS.steps) - 1)
    bad = build_until(make_ctx(p, LOCOS, Faults(misalign={"POLY": (0.6, 0.0)})), len(LOCOS.steps) - 1)
    gx = lambda w: min(s.xmin for s in w.layers["gate_n"].solids)
    assert abs(gx(bad) - gx(ok) - 0.6) < 1e-9
    # self-aligned S/D follows the shifted gate
    nx = lambda w: max(s.xmax for s in w.layers["nplus"].solids if s.xmax < 6)
    assert abs(nx(bad) - nx(ok) - 0.6) < 1e-9
    skipped = build_until(make_ctx(p, LOCOS, Faults(skip=frozenset({"nplus"}))), len(LOCOS.steps) - 1)
    assert not skipped.has("nplus")


def test_spacers_and_ldd_structure():
    from fabsim3d.process_core import SPACER_W, gate_span
    ctx = make_ctx(ProcessParams(), STI)
    film = build_until(ctx, STI.step_index("spacer_dep"))
    assert film.has("spacer_film") and not film.has("spacer")
    w = build_until(ctx, len(STI.steps) - 1)
    assert not w.has("spacer_film") and len(w.layers["spacer"].solids) == 4
    for s in w.layers["spacer"].solids:                       # convex, CCW cross-sections
        pts = s.poly
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts))) / 2
        assert area > 0
    g0 = gate_span(ctx, "gn")[0]
    n_edge = max(s.xmax for s in w.layers["nplus"].solids if s.xmax < g0 + 0.5)
    ldd_edge = max(s.xmax for s in w.layers["nldd"].solids if s.xmax < g0 + 0.5)
    # deep n+ stays back by about a spacer width; LDD reaches under the gate edge
    assert g0 - SPACER_W < n_edge < g0
    assert ldd_edge > g0
    assert max(s.zmin for s in w.layers["nldd"].solids) > min(s.zmin for s in w.layers["nplus"].solids)


def test_flow_default_params_are_era_typical():
    lo = summarize_cached(LOCOS.default_params(), LOCOS.features)
    hi = summarize_cached(STI.default_params(), STI.features)
    assert LOCOS.default_params().vdd > STI.default_params().vdd
    for s in (lo, hi):
        assert 0.3 < s.vtn < 0.6 and -0.6 < s.vtp < -0.3
    assert hi.tran.tphl < lo.tran.tphl          # newer generation is faster


@pytest.mark.parametrize("flow", ADVANCED, ids=[f.key for f in ADVANCED])
def test_advanced_final_structure(flow):
    """Gate-last flows end with a HKMG stack, plugs and copper; no dummy gate is left."""
    w = build_until(make_ctx(flow.default_params(), flow), len(flow.steps) - 1)
    for name in ("sti", "spacer", "hk", "gfill", "plug", "cu", "ild0", "ild"):
        assert w.has(name), name
    for name in ("resist", "resist_exp", "nitride", "padox", "poly", "gate", "gate_n", "gate_p", "sige", "ni"):
        assert not w.has(name), name
    assert {round(s.zmax, 6) for s in w.layers["cu"].solids} == {1.75}       # copper CMP is flat
    gate_top = max(s.zmax for s in w.layers["gfill"].solids)
    assert abs(gate_top - max(s.zmax for s in w.layers["ild0"].solids)) < 1e-9   # metal CMP stops on ILD0


def test_finfet_fins_and_wrapped_gate():
    from fabsim3d.flows import finfet
    f = FLOWS["finfet"]
    ctx = make_ctx(f.default_params(), f)
    w = build_until(ctx, f.step_index("fin_reveal"))
    sti_top = max(s.zmax for s in w.layers["sti"].solids)
    fin_tops = [s.zmax for s in w.layers["sub"].solids if s.zmax > sti_top]
    assert len(fin_tops) == 2 * len(finfet.FIN_YC) and all(abs(z) < 1e-9 for z in fin_tops)
    w = build_until(ctx, f.step_index("hkmg"))
    # high-k lines both sidewalls of every fin under each gate
    walls = [s for s in w.layers["hk"].solids if abs(s.zmin - finfet.FIN_REVEAL) < 1e-9 and s.y1 - s.y0 < 0.05]
    assert len(walls) == 2 * 2 * len(finfet.FIN_YC)


def test_gaa_sheets_released_and_wrapped():
    from fabsim3d.flows import gaa
    f = FLOWS["gaa"]
    ctx = make_ctx(f.default_params(), f)
    before = build_until(ctx, f.step_index("inner_spacer"))
    assert before.has("sige") and before.has("inner")
    w = build_until(ctx, len(f.steps) - 1)
    assert not w.has("sige") and len(w.layers["sheet"].solids) == 2 * len(gaa.SHEETS)
    g = ctx.lay["gn"]
    for z0, z1 in gaa.SIGE:            # every former SiGe gap under the gate now holds gate metal
        zc = (z0 + z1) / 2
        assert any(s.xmin <= g[0] + 1e-9 and s.xmax >= g[1] - 1e-9 and s.zmin <= zc <= s.zmax
                   for s in w.layers["wfn"].solids), (z0, z1)


def test_cfet_stack_and_backside():
    from fabsim3d.flows import cfet
    f = FLOWS["cfet"]
    ctx = make_ctx(f.default_params(), f)
    w = build_until(ctx, len(f.steps) - 1)
    assert not w.has("sub") and w.has("bsd") and w.has("bsc") and w.has("bsm")   # backside power
    assert w.layers["mdi"].material == "mdi_ox"
    n_top = max(s.zmax for s in w.layers["sheet_n"].solids)
    p_bot = min(s.zmin for s in w.layers["sheet_p"].solids)
    assert n_top < cfet.MDI[0] < cfet.MDI[1] < p_bot                          # PMOS above NMOS
    out = ctx.lay["contacts"]["out"]
    deep = min(s.zmin for s in w.layers["plug"].solids if s.xmin >= out[0] - 1e-9 and s.xmax <= out[1] + 1e-9)
    assert deep < min(s.zmin for s in w.layers["psd"].solids)                 # Vout reaches the bottom drain
    # bottom WF metal is n-type, the top one p-type
    assert max(s.zmax for s in w.layers["wfn"].solids) <= cfet.MDI[0] + 1e-9


def test_generations_scale():
    """Each generation runs at a lower VDD; multi-gate devices beat planar 28 nm on DIBL and swing."""
    keys = list(FLOWS)
    vdds = [FLOWS[k].default_params().vdd for k in keys]
    assert vdds == sorted(vdds, reverse=True)
    s = {k: summarize_cached(FLOWS[k].default_params(), FLOWS[k].features) for k in keys}
    for k in keys:
        assert 0.2 < s[k].vtn < 0.6 and -0.6 < s[k].vtp < -0.2, k
        assert s[k].vtc.nmh > 0.2 * FLOWS[k].default_params().vdd, k
    assert s["finfet"].dibl_n < s["hkmg"].dibl_n and s["gaa"].dibl_n < s["finfet"].dibl_n
    assert s["finfet"].ss_n < s["hkmg"].ss_n and s["gaa"].ss_n < s["finfet"].ss_n
    assert s["hkmg"].tran.tphl < s["sti"].tran.tphl and s["finfet"].tran.tphl < s["hkmg"].tran.tphl
