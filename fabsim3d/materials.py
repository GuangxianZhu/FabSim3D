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
    Material("gate_ox", (0.92, 0.92, 0.95, 1), "栅氧化层", "Gate oxide", 4),
    Material("poly", (0.80, 0.45, 0.35, 1), "多晶硅", "Polysilicon", 5),
    Material("poly_n", (0.85, 0.30, 0.30, 1), "N+ 多晶硅栅", "n+ poly gate", 5),
    Material("poly_p", (0.40, 0.45, 0.90, 1), "P+ 多晶硅栅", "p+ poly gate", 5),
    Material("n_plus", (0.92, 0.20, 0.20, 1), "N+ 源/漏", "n+ source/drain", 3),
    Material("p_plus", (0.25, 0.35, 0.95, 1), "P+ 源/漏", "p+ source/drain", 3),
    Material("ild", (0.80, 0.90, 0.95, 0.30), "层间介质 (BPSG)", "Inter-layer dielectric (BPSG)", 6),
    Material("metal", (0.70, 0.72, 0.78, 1), "铝金属层", "Aluminium metal", 7),
    Material("channel_n", (0.3, 1.0, 1.0, 0.0), "电子反型层", "Electron inversion layer", 9, False),
    Material("channel_p", (1.0, 0.6, 0.2, 0.0), "空穴反型层", "Hole inversion layer", 9, False),
]

MATERIALS = {m.key: m for m in _M}


def mat(key: str) -> Material:
    return MATERIALS[key]
