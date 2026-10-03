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
