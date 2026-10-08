import math

import numpy as np

from fabsim3d.device_model import (ProcessParams, cox, inverter_vout, nmos, pmos,
                                 summarize, transient, vtc)


def test_threshold_signs_and_range():
    p = ProcessParams()
    assert 0.1 < nmos(p).vt < 0.8
    assert -0.8 < pmos(p).vt < -0.1


def test_cox_matches_textbook():
    # 10 nm oxide -> 3.45 fF/um^2 = 3.45e-7 F/cm^2
    assert math.isclose(cox(ProcessParams(tox_nm=10)), 3.453e-7, rel_tol=1e-3)


def test_thinner_oxide_more_current():
    a = nmos(ProcessParams(tox_nm=10)).idsat(3.3)
    b = nmos(ProcessParams(tox_nm=5)).idsat(3.3)
    assert b > a


def test_higher_doping_raises_vt():
    assert nmos(ProcessParams(na_cm3=5e17)).vt > nmos(ProcessParams(na_cm3=1e16)).vt
    assert pmos(ProcessParams(nwell_dose_cm2=1e14)).vt < pmos(ProcessParams(nwell_dose_cm2=5e12)).vt


def test_strong_inversion_square_law():
    m = nmos(ProcessParams(lambda_um=0.0))
    vov = 1.5
    expected = m.beta * vov ** 2 / (2 * m.n)
    assert math.isclose(m.idsat(m.vt + vov), expected, rel_tol=0.05)


def test_subthreshold_slope():
    m = nmos(ProcessParams())
    i1, i2 = m.ids(m.vt - 0.3, 1.0), m.ids(m.vt - 0.2, 1.0)
    ss = 100.0 / math.log10(i2 / i1)          # mV/dec
    assert math.isclose(ss, m.ss_mv_dec, rel_tol=0.05)


def test_current_zero_at_zero_vds():
    m = nmos(ProcessParams())
    assert abs(float(m.ids(2.0, 0.0))) < 1e-15


def test_inverter_rails_and_monotonic():
    p = ProcessParams()
    v = inverter_vout(p, np.linspace(0, p.vdd, 101))
    assert v[0] > 0.99 * p.vdd and v[-1] < 0.01 * p.vdd
    assert np.all(np.diff(v) <= 1e-9)


def test_vtc_switching_point_and_margins():
    p = ProcessParams()
    r = vtc(p)
    assert 0.35 * p.vdd < r.vm < 0.65 * p.vdd
    assert r.nmh > 0 and r.nml > 0 and r.max_gain > 5
    # stronger PMOS pushes VM up
    assert vtc(p.copy(wp_um=20)).vm > r.vm


def test_transient_delays():
    p = ProcessParams()
    r = transient(p)
    assert 1e-12 < r.tphl < 1e-9 and 1e-12 < r.tplh < 1e-9
    # doubling the load roughly doubles the delay
    r2 = transient(p.copy(cload_ff=100))
    assert 1.6 < r2.tphl / r.tphl < 2.4


def test_summary_runs():
    s = summarize(ProcessParams())
    assert s.idsat_n > s.ioff_n * 1e6


SCE = frozenset({"sti", "sce"})
SCE_LDD = SCE | {"ldd"}


def test_vt_rolloff_and_dibl_grow_as_l_shrinks():
    from fabsim3d.device_model import vt_vs_length
    ls, lin, sat = vt_vs_length(ProcessParams(), SCE)
    assert np.all(np.diff(lin) > 0)            # Vt rises towards long channel
    dibl = lin - sat
    assert np.all(np.diff(dibl) <= 1e-12)      # DIBL shrinks with L
    long_ch = nmos(ProcessParams(l_um=5.0), frozenset({"sce"}))
    assert abs(long_ch.vt - nmos(ProcessParams(l_um=5.0)).vt) < 0.02


def test_ldd_reduces_dibl():
    p = ProcessParams(l_um=0.25)
    assert nmos(p, SCE_LDD).dibl < 0.7 * nmos(p, SCE).dibl
    assert nmos(p, SCE_LDD).vt > nmos(p, SCE).vt


def test_velocity_saturation_limits_current():
    p = ProcessParams(l_um=0.25, lambda_um=0.0)
    ideal = nmos(p).idsat(p.vdd)
    m = nmos(p, frozenset({"sce"}))
    assert m.idsat(p.vdd) < ideal
    assert m.ec_l > 0


def test_punch_through_device_is_normally_on():
    """Extreme roll-off drives Vt negative: the device must conduct at Vgs = 0."""
    p = ProcessParams(l_um=0.1, tox_nm=20, na_cm3=1e16)
    m = nmos(p, frozenset({"sce"}))
    assert m.vt_mag < 0
    assert float(m.ids(0.0, p.vdd)) > 1e-5


def test_metal_gate_work_function():
    """A metal with the work function of n+ / p+ poly gives the poly-gate Vt; a
    higher NMOS work function raises Vtn one-for-one."""
    p = ProcessParams()
    poly_n, poly_p = nmos(p).vt, pmos(p).vt
    assert math.isclose(nmos(p.copy(wf_n_ev=4.05)).vt, poly_n, abs_tol=1e-9)
    assert math.isclose(pmos(p.copy(wf_p_ev=4.05 + 1.12)).vt, poly_p, abs_tol=1e-9)
    assert math.isclose(nmos(p.copy(wf_n_ev=4.35)).vt - nmos(p.copy(wf_n_ev=4.25)).vt, 0.1, rel_tol=1e-6)


def test_multigate_electrostatics():
    """More gates and a thinner body shrink the natural length: less DIBL, steeper swing."""
    from fabsim3d.device_model import natural_length_cm
    p = ProcessParams(tox_nm=0.9, na_cm3=1e16, l_um=0.02, tsi_nm=8.0, wf_n_ev=4.45, wf_p_ev=4.77,
                      vdd=0.8, lambda_um=0.002)
    assert natural_length_cm(p, 4) < natural_length_cm(p, 3) < natural_length_cm(p, 2)
    fin, gaa = frozenset({"sce", "finfet"}), frozenset({"sce", "gaa"})
    assert nmos(p, gaa).dibl < nmos(p, fin).dibl
    assert nmos(p.copy(tsi_nm=5), fin).dibl < nmos(p, fin).dibl
    assert 60 < nmos(p, gaa).ss_mv_dec < nmos(p, fin).ss_mv_dec < 80
    # fully depleted, undoped body: channel doping barely matters, the work function sets Vt
    assert abs(nmos(p.copy(na_cm3=1e17), fin).vt - nmos(p, fin).vt) < 0.01
    assert nmos(p.copy(wf_n_ev=4.55), fin).vt > nmos(p, fin).vt + 0.09
    s = summarize(p, fin)
    assert abs(s.vtc.vm - p.vdd / 2) < 0.15
