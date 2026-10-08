"""Material colours, names and draw priority."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    key: str
    color: tuple          # rgba 0..1
    zh: str
    en: str
    priority: int = 0     # depth offset for coplanar faces (higher wins)
    legend: bool = True


_M = [
    Material("p_sub", (0.45, 0.86, 0.95, 1), "P 型硅衬底", "p-type Si substrate", 0),
    Material("n_implant", (0.95, 0.80, 0.35, 1), "磷注入层(未推进)", "P implant (as-implanted)", 2),
    Material("n_well", (0.98, 0.88, 0.50, 1), "N 阱", "N-well", 1),
    Material("pad_ox", (0.80, 0.80, 0.82, 1), "垫氧化层 SiO2", "Pad oxide SiO2", 3),
    Material("nitride", (0.30, 0.70, 0.40, 1), "氮化硅 Si3N4", "Silicon nitride Si3N4", 3),
    Material("resist", (0.45, 0.10, 0.45, 1), "光刻胶", "Photoresist", 4),
    Material("resist_exp", (0.85, 0.55, 0.90, 1), "已曝光光刻胶", "Exposed resist", 4),
    Material("fox", (0.62, 0.62, 0.66, 1), "场氧化层 (LOCOS)", "Field oxide (LOCOS)", 4),
    Material("sti_ox", (0.70, 0.74, 0.82, 1), "STI 填充氧化物 (HDP)", "STI fill oxide (HDP)", 4),
    Material("liner_ox", (0.88, 0.88, 0.92, 1), "衬垫氧化层", "Liner oxide", 5),
    Material("gate_ox", (0.92, 0.92, 0.95, 1), "栅氧化层", "Gate oxide", 4),
    Material("poly", (0.80, 0.45, 0.35, 1), "多晶硅", "Polysilicon", 5),
    Material("poly_n", (0.85, 0.30, 0.30, 1), "N+ 多晶硅栅", "n+ poly gate", 5),
    Material("poly_p", (0.40, 0.45, 0.90, 1), "P+ 多晶硅栅", "p+ poly gate", 5),
    Material("n_ldd", (0.98, 0.55, 0.55, 1), "N- LDD 轻掺杂漏", "n- LDD extension", 2),
    Material("p_ldd", (0.55, 0.65, 1.00, 1), "P- LDD 轻掺杂漏", "p- LDD extension", 2),
    Material("spacer", (0.45, 0.80, 0.58, 1), "Si3N4 侧墙", "Si3N4 sidewall spacer", 6),
    Material("n_plus", (0.92, 0.20, 0.20, 1), "N+ 源/漏", "n+ source/drain", 3),
    Material("p_plus", (0.25, 0.35, 0.95, 1), "P+ 源/漏", "p+ source/drain", 3),
    Material("ild", (0.80, 0.90, 0.95, 0.30), "层间介质 (BPSG)", "Inter-layer dielectric (BPSG)", 6),
    Material("metal", (0.70, 0.72, 0.78, 1), "铝金属层", "Aluminium metal", 7),
    # advanced nodes (HKMG / FinFET / GAA / CFET)
    Material("poly_dummy", (0.80, 0.55, 0.45, 1), "伪栅多晶硅 (之后去除)", "Dummy poly gate (removed later)", 5),
    Material("ild_ox", (0.80, 0.90, 0.95, 0.30), "层间介质 (SiO2)", "Inter-layer dielectric (SiO2)", 6),
    Material("nickel", (0.78, 0.80, 0.82, 1), "镍 (Ni)", "Nickel (Ni)", 6),
    Material("si_fin", (0.55, 0.90, 0.98, 1), "硅鳍 / 纳米片 (沟道)", "Si fin / nanosheet (channel)", 1),
    Material("sige", (0.95, 0.62, 0.78, 1), "SiGe 牺牲层", "SiGe sacrificial layer", 2),
    Material("sige_hi", (0.80, 0.40, 0.65, 1), "高 Ge SiGe (中间隔离牺牲层)", "High-Ge SiGe (isolation placeholder)", 2),
    Material("mdi_ox", (0.62, 0.86, 0.70, 1), "中间介质隔离 (MDI)", "Middle dielectric isolation (MDI)", 3),
    Material("hfo2", (0.98, 0.98, 0.55, 1), "高 k 介质 HfO2", "High-k HfO2", 7),
    Material("wf_n", (0.55, 0.62, 0.70, 1), "N 型功函数金属 (TiAl)", "n work-function metal (TiAl)", 7),
    Material("wf_p", (0.40, 0.50, 0.62, 1), "P 型功函数金属 (TiN)", "p work-function metal (TiN)", 7),
    Material("gate_metal", (0.58, 0.58, 0.64, 1), "栅极填充金属 (W)", "Gate fill metal (W)", 6),
    Material("n_epi", (0.95, 0.30, 0.30, 1), "N+ 外延源漏 (SiP)", "n+ epitaxial S/D (SiP)", 3),
    Material("p_epi", (0.30, 0.42, 0.95, 1), "P+ 外延源漏 (SiGe:B)", "p+ epitaxial S/D (SiGe:B)", 3),
    Material("silicide", (0.45, 0.42, 0.50, 1), "金属硅化物 (NiSi / TiSi)", "Silicide (NiSi / TiSi)", 5),
    Material("plug", (0.62, 0.66, 0.80, 1), "接触孔金属 (W / Co)", "Contact metal (W / Co)", 7),
    Material("lowk", (0.85, 0.80, 0.95, 0.30), "低 k 介质", "Low-k dielectric", 6),
    Material("copper", (0.90, 0.55, 0.30, 1), "铜互连 (Cu)", "Copper wiring (Cu)", 8),
    Material("bs_metal", (0.90, 0.70, 0.30, 1), "背面供电金属", "Backside power metal", 8),
    Material("channel_n", (0.3, 1.0, 1.0, 0.0), "电子反型层", "Electron inversion layer", 9, False),
    Material("channel_p", (1.0, 0.6, 0.2, 0.0), "空穴反型层", "Hole inversion layer", 9, False),
]

MATERIALS = {m.key: m for m in _M}


def mat(key: str) -> Material:
    return MATERIALS[key]
