"""Locate a font with CJK glyphs on Windows / macOS / Linux."""
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent

CANDIDATES = [
    # bundled with the project (drop any CJK .ttf/.otf/.ttc into ./fonts)
    *(sorted(str(p) for p in (_HERE / "fonts").glob("*.[ot]t[fc]")) if (_HERE / "fonts").is_dir() else []),
    # Windows
    r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyh.ttf", r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\Deng.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
]


def find_cjk_font() -> str | None:
    env = os.environ.get("CMOS3D_FONT")
    if env and os.path.exists(env):
        return env
    for c in CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None
