from cmos3d.device_model import ProcessParams
from cmos3d.geometry import Solid, rect_area, rect_complement, split_box, surface_height
from cmos3d.process_flow import DOMAIN, STEPS, Wafer, build_until, make_ctx, run_phase


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


def test_every_step_builds_and_has_text():
    ctx = make_ctx(ProcessParams())
    w = Wafer()
    for st in STEPS:
        assert st.title[0] and st.title[1] and st.desc[0] and st.desc[1]
        for zh, en, fn in st.params:
            assert isinstance(fn(ctx), str)
        if st.quiz:
            assert 0 <= st.quiz.answer < len(st.quiz.options)
        for ph in st.phases:
            run_phase(w, ctx, ph)


def test_final_structure():
    w = build_until(make_ctx(ProcessParams()), len(STEPS) - 1)
    for name in ("sub", "nwell", "fox", "gate_n", "gate_p", "nplus", "pplus", "ild", "metal"):
        assert w.has(name), name
    for name in ("resist", "resist_exp", "nitride", "padox", "poly"):
        assert not w.has(name), name
    assert w.layers["gate_n"].material == "poly_n"
    assert w.layers["gate_p"].material == "poly_p"


def test_gate_length_changes_layout():
    a = make_ctx(ProcessParams(l_um=0.25)).lay["gl"]
    b = make_ctx(ProcessParams(l_um=3.0)).lay["gl"]
    assert b > a
