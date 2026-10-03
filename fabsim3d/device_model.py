"""MOSFET / CMOS inverter electrical model derived from process parameters.

Units: cm, F, A, V internally unless noted. All functions are pure numpy so they
can be unit-tested without Panda3D.

Model summary
-------------
* Threshold voltage from classic MOS-capacitor theory (Vfb + 2*phiF + Qdep/Cox),
  with dual-doped poly gates (n+ poly for NMOS, p+ poly for PMOS).
* Drain current: Level-1 square law in strong inversion, smoothly extended into
  sub-threshold with the EKV interpolation function
      Id = Is * [F((Vp-Vs)/phit) - F((Vp-Vd)/phit)] * (1 + lambda*Vds)
      F(v) = ln^2(1 + exp(v/2)),  Vp = (Vg - Vt)/n,  Is = 2*n*k'*(W/L)*phit^2
  In strong-inversion saturation this reduces to Id = k'(W/L)(Vgs-Vt)^2/(2n).
* Inverter VTC solved by vectorised bisection of Idn = Idp.
* Transient response by RK2 integration of CL*dVout/dt = Idp - Idn.
* Process-dependent second-order effects are applied through the EFFECTS
  chain, selected by the flow's feature set (e.g. {"locos"}, {"sti", "cmp"}).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from typing import Callable, FrozenSet, List

import numpy as np

Q = 1.602e-19          # C
EPS0 = 8.854e-14       # F/cm
EPS_SI = 11.7 * EPS0
EPS_OX = 3.9 * EPS0
NI = 1.0e10            # cm^-3 at 300 K
PHIT = 0.02585         # kT/q at 300 K (V)
EG_HALF = 0.56         # Eg/2 of Si (V)
NWELL_DEPTH_CM = 2.0e-4  # junction depth after drive-in (2 um)


@dataclass
class ProcessParams:
    """Process knobs exposed in the UI (practical units)."""
    tox_nm: float = 10.0          # gate oxide thickness
    na_cm3: float = 1.0e17        # p-substrate / NMOS channel doping
    nwell_dose_cm2: float = 2.0e13  # n-well phosphorus implant dose
    l_um: float = 0.5             # drawn gate length
    wn_um: float = 2.0            # NMOS width
    wp_um: float = 5.0            # PMOS width
    vdd: float = 3.3              # supply
    cload_ff: float = 50.0        # inverter load capacitance
    mu_n: float = 400.0           # effective electron mobility cm^2/Vs
    mu_p: float = 150.0           # effective hole mobility cm^2/Vs
    vsat_n: float = 1.0e7         # electron saturation velocity cm/s
    vsat_p: float = 8.0e6         # hole saturation velocity cm/s
    qf_cm2: float = 1.0e10        # fixed oxide charge density
    lambda_um: float = 0.05       # CLM: lambda = lambda_um / L[um]  (1/V)

    @property
    def nd_cm3(self) -> float:
        """N-well doping estimated from implant dose spread over the well depth."""
        return self.nwell_dose_cm2 / NWELL_DEPTH_CM

    def copy(self, **kw) -> "ProcessParams":
        return replace(self, **kw)


@dataclass
class Mosfet:
    polarity: str        # "n" or "p"
    vt: float            # threshold (signed; negative for PMOS)
    kp: float            # k' = mu*Cox (A/V^2)
    n: float             # sub-threshold slope factor
    w_um: float
    l_um: float
    lam: float           # channel length modulation (1/V)
    gamma: float         # body-effect coefficient (sqrt(V))
    phi_f: float         # |Fermi potential| (V)
    vfb: float           # flat-band voltage (V)
    doping: float        # channel doping (cm^-3)
    # short-channel extensions (all zero = long-channel model)
    dibl: float = 0.0    # DIBL coefficient sigma: |Vt| drops by sigma*|Vds|  (V/V)
    ec_l: float = 0.0    # Ec*L for velocity saturation (V); 0 disables it
    xj_um: float = 0.0   # S/D junction depth seen by the channel (um), informative
    vt_rolloff: float = 0.0  # |Vt| reduction from charge sharing (V), informative

    @property
    def vt_mag(self) -> float:
        """Threshold in magnitude convention (positive = enhancement) for both polarities.
        It can go negative when short-channel roll-off turns the device normally-on."""
        return self.vt if self.polarity == "n" else -self.vt

    @property
    def beta(self) -> float:
        return self.kp * self.w_um / self.l_um

    @property
    def ss_mv_dec(self) -> float:
        return self.n * PHIT * math.log(10) * 1e3

    def ids(self, vgs, vds):
        """Drain current magnitude for magnitude bias (for PMOS pass Vsg, Vsd).

        Accepts numpy broadcasting. Returns A (>= 0 for vds >= 0).
        """
        vgs = np.asarray(vgs, dtype=float)
        vds = np.asarray(vds, dtype=float)
        vt = self.vt_mag - self.dibl * np.abs(vds)
        vp = (vgs - vt) / self.n
        i_s = 2.0 * self.n * self.beta * PHIT ** 2
        f_fwd = np.logaddexp(0.0, vp / (2 * PHIT)) ** 2
        f_rev = np.logaddexp(0.0, (vp - vds) / (2 * PHIT)) ** 2
        i = i_s * (f_fwd - f_rev) * (1.0 + self.lam * np.abs(vds))
        if self.ec_l > 0:
            # velocity saturation: mobility degraded by the lateral field
            vdse = np.minimum(np.abs(vds), np.maximum(vp, 0.0))
            i = i / (1.0 + vdse / self.ec_l)
        return i

    def idsat(self, vov_gate: float) -> float:
        return float(self.ids(vov_gate, vov_gate))


def cox(p: ProcessParams) -> float:
    """Gate oxide capacitance per area (F/cm^2)."""
    return EPS_OX / (p.tox_nm * 1e-7)


def _mos(p: ProcessParams, polarity: str) -> Mosfet:
    c = cox(p)
    doping = p.na_cm3 if polarity == "n" else p.nd_cm3
    phi_f = PHIT * math.log(doping / NI)
    qdep = math.sqrt(2 * EPS_SI * Q * doping * 2 * phi_f)
    gamma = math.sqrt(2 * Q * EPS_SI * doping) / c
    qf_over_cox = Q * p.qf_cm2 / c
    if polarity == "n":
        phi_ms = -(EG_HALF + phi_f)          # n+ poly on p-Si
        vfb = phi_ms - qf_over_cox
        vt = vfb + 2 * phi_f + qdep / c
        mu = p.mu_n
        w = p.wn_um
    else:
        phi_ms = EG_HALF + phi_f             # p+ poly on n-Si
        vfb = phi_ms - qf_over_cox
        vt = vfb - 2 * phi_f - qdep / c
        mu = p.mu_p
        w = p.wp_um
    n = 1.0 + gamma / (2.0 * math.sqrt(2 * phi_f + 6 * PHIT))
    return Mosfet(
        polarity=polarity, vt=vt, kp=mu * c, n=n, w_um=w, l_um=p.l_um,
        lam=p.lambda_um / p.l_um, gamma=gamma, phi_f=phi_f, vfb=vfb, doping=doping,
    )


# --------------------------------------------------------------------------
# Second-order effects chain
# --------------------------------------------------------------------------
# An effect is f(p, mos, features) -> Mosfet.  It may adjust vt, kp, n, lam ...
# and must return the device unchanged when its feature flag is absent.
# Planned additions: LDD/silicide series resistance, gate tunnelling leakage.
Effect = Callable[[ProcessParams, Mosfet, FrozenSet[str]], Mosfet]


def _xdm_cm(m: Mosfet) -> float:
    """Maximum depletion width at threshold."""
    return math.sqrt(2 * EPS_SI * 2 * m.phi_f / (Q * m.doping))


def narrow_width_effect(p: ProcessParams, m: Mosfet, features: FrozenSet[str]) -> Mosfet:
    """Isolation-dependent narrow-width Vt shift (qualitative teaching model).

    LOCOS: the bird's beak and field implant add fringing depletion charge at
    the channel edges -> |Vt| rises for narrow W:
        d|Vt| = (Qdep/Cox) * pi*xdm / (2W)
    STI: field crowding at the trench corners turns the edges on early ->
    inverse narrow-width effect, |Vt| falls:
        d|Vt| = -(Qdep/Cox) * xdm / (2W)
    """
    if "locos" in features:
        k = math.pi / 2
    elif "sti" in features:
        k = -0.5
    else:
        return m
    qdep_cox = m.gamma * math.sqrt(2 * m.phi_f)
    d = qdep_cox * k * _xdm_cm(m) / (m.w_um * 1e-4)
    sign = 1.0 if m.polarity == "n" else -1.0
    return replace(m, vt=m.vt + sign * d)


XJ_DEEP_UM = 0.25    # conventional S/D junction depth
XJ_LDD_UM = 0.08     # shallow LDD extension at the channel edge


def short_channel_effect(p: ProcessParams, m: Mosfet, features: FrozenSet[str]) -> Mosfet:
    """Short-channel effects for real flows (feature "sce").

    The junction depth seen by the channel is the LDD depth when the flow has
    LDD ("ldd" feature), otherwise the deep S/D junction.

    * Vt roll-off (Yau charge sharing):
        d|Vt| = -(Qdep/Cox) * (xj/L) * (sqrt(1 + 2*xdm/xj) - 1)
    * DIBL: |Vt| drops by sigma*|Vds|,  sigma = 0.6 * exp(-L / (2*l)),
      characteristic length l = sqrt(eps_si/eps_ox * tox * xj)
    * Velocity saturation: Id / (1 + Vds_eff/(Ec*L)),  Ec = 2*vsat/mu
    """
    if "sce" not in features:
        return m
    xj = (XJ_LDD_UM if "ldd" in features else XJ_DEEP_UM) * 1e-4
    L = m.l_um * 1e-4
    qdep_cox = m.gamma * math.sqrt(2 * m.phi_f)
    xdm = _xdm_cm(m)
    rolloff = qdep_cox * (xj / L) * (math.sqrt(1 + 2 * xdm / xj) - 1)
    l_char = math.sqrt(EPS_SI / EPS_OX * p.tox_nm * 1e-7 * xj)
    sigma = 0.6 * math.exp(-L / (2 * l_char))
    mu = p.mu_n if m.polarity == "n" else p.mu_p
    vsat = p.vsat_n if m.polarity == "n" else p.vsat_p
    ec_l = 2 * vsat / mu * L
    sign = 1.0 if m.polarity == "n" else -1.0
    return replace(m, vt=m.vt - sign * rolloff, dibl=sigma, ec_l=ec_l,
                   xj_um=xj * 1e4, vt_rolloff=rolloff)


EFFECTS: List[Effect] = [narrow_width_effect, short_channel_effect]


def nmos(p: ProcessParams, features: FrozenSet[str] = frozenset()) -> Mosfet:
    m = _mos(p, "n")
    for eff in EFFECTS:
        m = eff(p, m, features)
    return m


def pmos(p: ProcessParams, features: FrozenSet[str] = frozenset()) -> Mosfet:
    m = _mos(p, "p")
    for eff in EFFECTS:
        m = eff(p, m, features)
    return m


# --------------------------------------------------------------------------
# Inverter
# --------------------------------------------------------------------------

def inverter_vout(p: ProcessParams, vin, n_iter: int = 60, features: FrozenSet[str] = frozenset()):
    """Static output voltage for input(s) vin (vectorised bisection)."""
    mn, mp = nmos(p, features), pmos(p, features)
    vin = np.atleast_1d(np.asarray(vin, dtype=float))
    lo = np.zeros_like(vin)
    hi = np.full_like(vin, p.vdd)
    for _ in range(n_iter):
        mid = 0.5 * (lo + hi)
        f = mn.ids(vin, mid) - mp.ids(p.vdd - vin, p.vdd - mid)
        # f increases monotonically with Vout
        hi = np.where(f > 0, mid, hi)
        lo = np.where(f > 0, lo, mid)
    return 0.5 * (lo + hi)


@dataclass
class VTCResult:
    vin: np.ndarray
    vout: np.ndarray
    gain: np.ndarray
    vm: float
    vil: float
    vih: float
    voh: float
    vol: float
    nmh: float
    nml: float
    max_gain: float
    i_short: np.ndarray = field(repr=False, default=None)


def vtc(p: ProcessParams, npts: int = 601, features: FrozenSet[str] = frozenset()) -> VTCResult:
    vin = np.linspace(0.0, p.vdd, npts)
    vout = inverter_vout(p, vin, features=features)
    gain = np.gradient(vout, vin)
    vm = float(np.interp(0.0, (vout - vin)[::-1], vin[::-1]))
    steep = np.where(gain < -1.0)[0]
    if steep.size:
        vil = float(vin[steep[0]])
        vih = float(vin[steep[-1]])
    else:
        vil = vih = vm
    voh, vol = float(vout[0]), float(vout[-1])
    i_short = nmos(p, features).ids(vin, vout)
    return VTCResult(vin, vout, gain, vm, vil, vih, voh, vol,
                     voh - vih, vil - vol, float(-gain.min()), i_short)


@dataclass
class TransientResult:
    t: np.ndarray        # s
    vin: np.ndarray
    vout: np.ndarray
    tphl: float          # s (nan if not found)
    tplh: float


def _cross(t, v, level, rising: bool, after: float) -> float:
    mask = t >= after
    tt, vv = t[mask], v[mask]
    s = vv - level
    idx = np.where((s[:-1] < 0) & (s[1:] >= 0))[0] if rising else \
        np.where((s[:-1] > 0) & (s[1:] <= 0))[0]
    if idx.size == 0:
        return float("nan")
    i = idx[0]
    return float(tt[i] + (tt[i + 1] - tt[i]) * (level - vv[i]) / (vv[i + 1] - vv[i]))


def transient(p: ProcessParams, nsteps: int = 3000, features: FrozenSet[str] = frozenset()) -> TransientResult:
    """Pulse response of the inverter driving CL."""
    mn, mp = nmos(p, features), pmos(p, features)
    cl = p.cload_ff * 1e-15
    i_drive = max(min(mn.idsat(p.vdd), mp.idsat(p.vdd)), 1e-12)
    tau = cl * p.vdd / i_drive
    t_end = 14 * tau
    tr = 0.3 * tau
    t1, t2 = 1.0 * tau, 7.0 * tau
    t = np.linspace(0.0, t_end, nsteps)
    dt = t[1] - t[0]

    def vin_at(tt):
        up = np.clip((tt - t1) / tr, 0, 1)
        down = np.clip((tt - t2) / tr, 0, 1)
        return p.vdd * (up - down)

    def dvdt(tt, v):
        vi = vin_at(tt)
        return (mp.ids(p.vdd - vi, p.vdd - v) - mn.ids(vi, v)) / cl

    vin = vin_at(t)
    vout = np.empty_like(t)
    v = float(inverter_vout(p, 0.0, features=features)[0])
    for k, tk in enumerate(t):
        vout[k] = v
        k1 = dvdt(tk, v)
        k2 = dvdt(tk + dt, v + dt * k1)
        v = float(np.clip(v + 0.5 * dt * (k1 + k2), -0.5, p.vdd + 0.5))
    half = p.vdd / 2
    t_in_rise = t1 + tr / 2
    t_in_fall = t2 + tr / 2
    tphl = _cross(t, vout, half, rising=False, after=t1) - t_in_rise
    tplh = _cross(t, vout, half, rising=True, after=t2) - t_in_fall
    return TransientResult(t, vin, vout, tphl, tplh)


@dataclass
class Summary:
    cox: float
    vtn: float
    vtp: float
    kpn: float
    kpp: float
    gamma_n: float
    gamma_p: float
    ss_n: float
    ss_p: float
    idsat_n: float
    idsat_p: float
    ioff_n: float
    nd: float
    vtc: VTCResult
    tran: TransientResult
    dibl_n: float = 0.0        # mV/V
    dibl_p: float = 0.0
    rolloff_n: float = 0.0     # V
    rolloff_p: float = 0.0
    xj_um: float = 0.0


def summarize(p: ProcessParams, features: FrozenSet[str] = frozenset()) -> Summary:
    mn, mp = nmos(p, features), pmos(p, features)
    return Summary(
        cox=cox(p), vtn=mn.vt, vtp=mp.vt, kpn=mn.kp, kpp=mp.kp,
        gamma_n=mn.gamma, gamma_p=mp.gamma, ss_n=mn.ss_mv_dec, ss_p=mp.ss_mv_dec,
        idsat_n=mn.idsat(p.vdd), idsat_p=mp.idsat(p.vdd),
        ioff_n=float(mn.ids(0.0, p.vdd)), nd=p.nd_cm3,
        vtc=vtc(p, features=features), tran=transient(p, features=features),
        dibl_n=mn.dibl * 1e3, dibl_p=mp.dibl * 1e3, rolloff_n=mn.vt_rolloff,
        rolloff_p=mp.vt_rolloff, xj_um=mn.xj_um,
    )


def vt_vs_length(p: ProcessParams, features: FrozenSet[str], polarity: str = "n",
                 l_min: float = 0.1, l_max: float = 5.0, npts: int = 80):
    """|Vt| versus gate length at low |Vds| (0.05 V) and at |Vds| = VDD.

    Returns (L_um, vt_lin, vt_sat).  Shows Vt roll-off (lin) and DIBL (sat - lin).
    """
    ls = np.geomspace(l_min, l_max, npts)
    lin, sat = [], []
    for L in ls:
        m = (nmos if polarity == "n" else pmos)(p.copy(l_um=float(L)), features)
        lin.append(m.vt_mag - m.dibl * 0.05)
        sat.append(m.vt_mag - m.dibl * p.vdd)
    return ls, np.array(lin), np.array(sat)
