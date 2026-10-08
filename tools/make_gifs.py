"""Record the animated GIFs used in README.md (docs/gif_*.gif).

    python tools/make_gifs.py              # all clips
    python tools/make_gifs.py build_sti    # one clip

Renders offscreen with a fake clock, so every frame advances the app by exactly
1/FPS seconds no matter how slow the renderer is.  Needs ffmpeg on PATH.
On a headless Linux box run it under Xvfb for antialiased OpenGL output:

    xvfb-run -a -s "-screen 0 1920x1080x24" python tools/make_gifs.py
"""
import math
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
from panda3d.core import loadPrcFileData

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DOCS = ROOT / "docs"
FPS = 12
WIN_W, WIN_H = 1600, 900

loadPrcFileData("", "\n".join([
    f"win-size {WIN_W} {WIN_H}", "window-type offscreen", "framebuffer-multisample 1",
    "multisamples 4", "text-encoding utf8", "audio-library-name null"]))


class Clock:
    """Stand-in for the `time` module inside the app: time only moves when we say so."""
    t = 1000.0

    @classmethod
    def time(cls):
        return cls.t


import fabsim3d.app as app_mod      # noqa: E402
import fabsim3d.guide_ui as guide_mod  # noqa: E402

app_mod.time = guide_mod.time = types.SimpleNamespace(time=Clock.time)

from fabsim3d.app import LEFT_W, RIGHT_W, CmosApp  # noqa: E402

APP = CmosApp({"flow": "locos"})
APP.layout_viewport()

# pixel columns of the 3D viewport / right panel
_aspect = WIN_W / WIN_H
VIEW_X0 = int(round(LEFT_W / (2 * _aspect) * WIN_W))
VIEW_X1 = int(round((1 - RIGHT_W / (2 * _aspect)) * WIN_W))


def tick(n=1):
    """Advance the app n frames and return the last rendered frame (H, W, 3 uint8)."""
    for _ in range(n):
        Clock.t += 1 / FPS
        APP.taskMgr.step()
    tex = APP.win.getScreenshot()
    img = np.frombuffer(bytes(tex.getRamImageAs("RGB")), np.uint8)
    return img.reshape(tex.getYSize(), tex.getXSize(), 3)[::-1]


def settle():
    """Let plots/UI catch up after a state change (no frame is kept)."""
    APP.last_plot = 0
    tick(3)


def encode(frames, name, crop=None, width=800, colors=128):
    """frames: list of (H, W, 3) arrays -> docs/<name>.gif via ffmpeg palettegen."""
    out = DOCS / f"{name}.gif"
    with tempfile.TemporaryDirectory() as d:
        from PIL import Image
        for k, f in enumerate(frames):
            if crop:
                x0, x1, y0, y1 = crop
                f = f[y0:y1, x0:x1]
            Image.fromarray(f).save(f"{d}/{k:05d}.png")
        vf = (f"fps={FPS},scale={width}:-1:flags=lanczos,split[a][b];"
              f"[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
              f"[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                        "-i", f"{d}/%05d.png", "-vf", vf, "-loop", "0", str(out)], check=True)
    print(f"{out.relative_to(ROOT)}: {len(frames)} frames, {out.stat().st_size / 1e6:.2f} MB")


def label(frame, text, size=30):
    """Draw a caption box in the top-left corner of a frame."""
    from PIL import Image, ImageDraw, ImageFont
    from fabsim3d.fonts import find_cjk_font
    font = ImageFont.truetype(find_cjk_font(), size)
    im = Image.fromarray(frame)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((16, 16, 30 + d.textlength(text, font=font), 24 + size * 1.25), 8, fill=(20, 24, 32))
    d.text((23, 20), text, font=font, fill=(255, 200, 80))
    return np.asarray(im)


def record_build(flow, speed, hold=1.5, crop=None, caption=False):
    """Play a whole flow from the bare wafer to the finished inverter."""
    APP.set_flow(flow)
    APP.set_cam("iso")
    APP.speed_slider["value"] = (speed - 0.25) / 2.75     # the slider callback owns APP.speed
    APP.goto(0)
    settle()
    x0, x1, y0, y1 = crop or (0, WIN_W, 0, WIN_H)

    def grab():
        f = tick()[y0:y1, x0:x1]
        if caption:
            i = APP.anim_step if APP.anim_step is not None else APP.step
            f = label(f, f"{i + 1}/{len(APP.steps)}  {APP.steps[i].title[0]}", 26)
        return f

    frames = [grab()]
    APP.toggle_play()
    while APP.playing or APP.anim_step is not None:
        frames.append(grab())
        if APP.is_done():
            break
    frames += [grab() for _ in range(int(hold * FPS))]
    APP.playing = False
    APP.speed_slider["value"] = 0.75 / 2.75
    return frames


def clip_build_sti():
    frames = record_build("sti", speed=3.0, crop=(VIEW_X0, WIN_W, 0, 720))
    encode(frames, "gif_build_sti", width=900, colors=160)


def clip_build_gaa():
    frames = record_build("gaa", speed=3.0, crop=(VIEW_X0, VIEW_X1, 120, 760), caption=True)
    encode(frames, "gif_build_gaa", width=640)


def clip_generations():
    """Finished device of every generation, orbiting, labelled with its name."""
    from fabsim3d.flows import FLOWS
    frames = []
    per = int(2.0 * FPS)
    for key, flow in FLOWS.items():
        APP.set_flow(key)
        APP.goto(len(APP.steps) - 1)
        APP.set_cam("iso")
        APP.cam_d = 30.0
        settle()
        h0 = APP.cam_h
        for k in range(per):
            APP.cam_h = h0 + 14 * math.sin(2 * math.pi * k / per)
            APP.update_camera()
            frames.append(label(tick()[170:690, VIEW_X0:VIEW_X1], flow.name[0]))
    encode(frames, "gif_generations", width=540, colors=64)


def clip_inverter():
    """3D carrier simulation + VTC with IDD while Vin sweeps 0 -> VDD -> 0."""
    APP.set_flow("locos")
    APP.goto(len(APP.steps) - 1)
    APP.set_cam("iso")
    APP.right_tab = "elec"
    APP.plot_kind = "vtc"
    if not APP.sim3d:
        APP.toggle_sim3d()
    APP.refresh_ui()
    frames = []
    n = int(7 * FPS)
    for k in range(n):
        x = 0.5 - 0.5 * math.cos(2 * math.pi * k / n)     # 0 -> 1 -> 0
        APP.vin_slider["value"] = x
        APP.set_vin()
        APP.last_plot = 0
        frames.append(tick())
    encode(frames, "gif_inverter_sim", crop=(VIEW_X0, WIN_W, 0, 620), width=820, colors=160)
    APP.toggle_sim3d()


CLIPS = {"build_sti": clip_build_sti, "build_gaa": clip_build_gaa,
         "generations": clip_generations, "inverter": clip_inverter}

if __name__ == "__main__":
    for name in sys.argv[1:] or CLIPS:
        CLIPS[name]()
