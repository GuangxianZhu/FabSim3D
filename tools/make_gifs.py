"""Record the animated GIFs used in README.md (docs/gif_*.gif).

    python tools/make_gifs.py              # all clips
    python tools/make_gifs.py build_sti    # one clip

Renders offscreen with a fake clock, so every frame advances the app by exactly
1/FPS seconds no matter how slow the renderer is.  Needs ffmpeg on PATH.
On a headless Linux box run it under Xvfb for antialiased OpenGL output:

    xvfb-run -a -s "-screen 0 1920x1080x24" python tools/make_gifs.py

【中文说明】录制 README 介绍页里那几张动图（GIF）的小工具，普通使用者不需要运行它。

它做了什么：
    1. 在“离屏”模式（不显示窗口）下启动 FabSim3D 程序；
    2. 用代码代替人去操作程序（选流程、播放动画、拖滑块），每推进一帧就截一张图；
    3. 把截下的一张张图片交给 ffmpeg（一个免费的音视频处理软件）合成为 GIF，保存到 docs 文件夹。

为什么要用“假时钟”：
    程序里的动画是按“真实时间过了多久”来推进的。电脑渲染慢的话，两次截图之间可能隔了很久，
    动图就会跳帧。这里把程序读取时间的地方换成一个假时钟，每截一帧就只让时间前进 1/FPS 秒，
    这样不管电脑多慢，录出来的动图都是平滑匀速的。

运行方法见上面英文部分：不带参数录全部片段；带片段名（如 build_sti）只录那一段。
需要额外安装 ffmpeg 和 Pillow（Python 图像库）。
"""
# ---- 导入需要用到的库 ----
# math 数学函数；subprocess 用来调用外部程序（ffmpeg）；sys 读取命令行参数、修改模块搜索路径；
# tempfile 创建临时文件夹；types 用来造一个“冒充 time 模块”的简单对象；Path 方便地拼接文件路径
import math
import subprocess
import sys
import tempfile
import types
from pathlib import Path

# numpy 处理图片像素数组；loadPrcFileData 用来修改 Panda3D 的启动设置
import numpy as np
from panda3d.core import loadPrcFileData

# ---- 基本设置 ----
# __file__ 是本脚本自己的路径；.parent.parent 往上两级，得到项目根目录 FabSim3D
ROOT = Path(__file__).resolve().parent.parent
# 把项目根目录加到 Python 的模块搜索路径最前面，这样下面才能 import fabsim3d
sys.path.insert(0, str(ROOT))
# 动图输出到 docs 文件夹；Path 对象可以用 / 拼接路径
DOCS = ROOT / "docs"
# 每秒帧数（frames per second）
FPS = 12
# 离屏窗口的宽和高（像素）
WIN_W, WIN_H = 1600, 900

# 设置 Panda3D：窗口大小、离屏渲染、开启 4 倍多重采样抗锯齿（边缘更平滑）、文字用 UTF-8 编码、关闭声音
# "\n".join([...]) 把列表里的几行设置用换行符连成一整段文字
loadPrcFileData("", "\n".join([
    f"win-size {WIN_W} {WIN_H}", "window-type offscreen", "framebuffer-multisample 1",
    "multisamples 4", "text-encoding utf8", "audio-library-name null"]))


class Clock:
    """Stand-in for the `time` module inside the app: time only moves when we say so.

    假时钟：冒充程序里用到的 time 模块。程序调用 time.time() 时拿到的是这里的 t，
    只有我们在 tick() 里手动加时间，它才会前进。
    """
    # 类变量：所有地方共用同一个当前时间（从 1000 秒开始，数值本身没有意义）
    t = 1000.0

    # @classmethod 让这个方法直接通过类调用（Clock.time()），不需要先创建对象
    @classmethod
    def time(cls):
        return cls.t


# 注意：上面的 Panda3D 设置必须在导入程序之前完成，所以这几个 import 放在文件中间。
# 行尾的 "# noqa: E402" 是告诉代码检查工具“这里故意没把 import 放在文件开头，不要报警”。
import fabsim3d.app as app_mod      # noqa: E402
import fabsim3d.guide_ui as guide_mod  # noqa: E402

# 关键一步：把 app.py 和 guide_ui.py 里的 time 模块替换成只有一个 time() 函数的假对象，
# 从此程序里所有 time.time() 都会读假时钟
app_mod.time = guide_mod.time = types.SimpleNamespace(time=Clock.time)

from fabsim3d.app import LEFT_W, RIGHT_W, CmosApp  # noqa: E402

# 创建程序（默认使用 LOCOS 工艺流程），并按窗口大小摆好 3D 画面的位置
APP = CmosApp({"flow": "locos"})
APP.layout_viewport()

# pixel columns of the 3D viewport / right panel
# 算出 3D 画面在截图里从第几列像素开始、到第几列结束（左边是控制面板，右边是信息面板），
# 后面裁剪动图时只保留需要的部分。算法与 app.py 里摆放 3D 画面的方法一致。
_aspect = WIN_W / WIN_H
VIEW_X0 = int(round(LEFT_W / (2 * _aspect) * WIN_W))
VIEW_X1 = int(round((1 - RIGHT_W / (2 * _aspect)) * WIN_W))


def tick(n=1):
    """Advance the app n frames and return the last rendered frame (H, W, 3 uint8).

    让程序前进 n 帧，并返回最后一帧的截图。截图是一个“高 × 宽 × 3（红绿蓝）”的数字数组。
    """
    # 每帧：假时钟前进 1/FPS 秒，然后让 Panda3D 处理一帧（更新动画、重画画面）
    for _ in range(n):
        Clock.t += 1 / FPS
        APP.taskMgr.step()
    # 取出窗口画面，转成 RGB 字节，再变成 numpy 数组
    tex = APP.win.getScreenshot()
    img = np.frombuffer(bytes(tex.getRamImageAs("RGB")), np.uint8)
    # reshape 把一长串数字整理成 (高, 宽, 3) 的形状；
    # [::-1] 把行的顺序倒过来，因为 Panda3D 的图片是从下往上存的，不翻转图就是倒的
    return img.reshape(tex.getYSize(), tex.getXSize(), 3)[::-1]


def settle():
    """Let plots/UI catch up after a state change (no frame is kept).

    状态改变后（比如切换流程），先空转几帧让曲线图和界面刷新完，这几帧不录进动图。
    """
    # 把“上次画图时间”设为 0，强制程序下一帧立即重画曲线（程序平时会限制重画频率）
    APP.last_plot = 0
    tick(3)


def encode(frames, name, crop=None, width=800, colors=128):
    """frames: list of (H, W, 3) arrays -> docs/<name>.gif via ffmpeg palettegen.

    把一组截图合成一个 GIF 文件：docs/<name>.gif。
    crop 可选的裁剪范围 (x0, x1, y0, y1)；width 输出宽度（像素）；colors 调色板颜色数
    （GIF 最多只能有 256 种颜色，颜色越少文件越小）。
    """
    out = DOCS / f"{name}.gif"
    # with ... as d：创建一个临时文件夹 d，with 块结束后自动删除，不留垃圾
    with tempfile.TemporaryDirectory() as d:
        from PIL import Image
        # 先把每一帧存成编号的 PNG 图片：00000.png、00001.png……（{k:05d} 表示补零到 5 位）
        for k, f in enumerate(frames):
            if crop:
                x0, x1, y0, y1 = crop
                # 数组切片 f[行范围, 列范围]，即只保留这块矩形区域
                f = f[y0:y1, x0:x1]
            Image.fromarray(f).save(f"{d}/{k:05d}.png")
        # ffmpeg 的滤镜设置：先缩放到指定宽度（高度按比例 -1），然后把画面分成两路 [a][b]：
        # [a] 用来统计所有帧中最常用的颜色、生成调色板 [p]；[b] 再按这个调色板上色（加抖动让渐变更自然）。
        # 这样做出来的 GIF 颜色比默认方式好看得多。
        vf = (f"fps={FPS},scale={width}:-1:flags=lanczos,split[a][b];"
              f"[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
              f"[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle")
        # 调用 ffmpeg 把 PNG 序列合成 GIF；-y 覆盖已有文件；-loop 0 表示无限循环播放；
        # check=True 表示 ffmpeg 出错时让本脚本也报错停止
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                        "-i", f"{d}/%05d.png", "-vf", vf, "-loop", "0", str(out)], check=True)
    # 打印结果：文件路径、帧数、文件大小（MB）
    print(f"{out.relative_to(ROOT)}: {len(frames)} frames, {out.stat().st_size / 1e6:.2f} MB")


def label(frame, text, size=30):
    """Draw a caption box in the top-left corner of a frame.

    在一帧画面的左上角画一个深色圆角框，里面写上橙黄色的说明文字（如步骤名）。
    """
    from PIL import Image, ImageDraw, ImageFont
    from fabsim3d.fonts import find_cjk_font
    # 找一个能显示中文的字体（CJK = 中日韩文字）
    font = ImageFont.truetype(find_cjk_font(), size)
    im = Image.fromarray(frame)
    d = ImageDraw.Draw(im)
    # 圆角矩形的宽度根据文字长度（textlength）自动调整；8 是圆角半径；fill 是填充颜色 (红, 绿, 蓝)
    d.rounded_rectangle((16, 16, 30 + d.textlength(text, font=font), 24 + size * 1.25), 8, fill=(20, 24, 32))
    d.text((23, 20), text, font=font, fill=(255, 200, 80))
    # 转回 numpy 数组，和其他帧保持同样的格式
    return np.asarray(im)


def record_build(flow, speed, hold=1.5, crop=None, caption=False):
    """Play a whole flow from the bare wafer to the finished inverter.

    录制一整套工艺：从一片空白晶圆一直播放到反相器做完，返回所有帧。
    speed 播放速度倍数；hold 播完后在最终画面停留几秒；crop 裁剪范围；caption 是否在左上角标出当前步骤。
    """
    # ---- 准备：切换流程、相机斜视角、设置播放速度、回到第一步 ----
    APP.set_flow(flow)
    APP.set_cam("iso")
    # 速度滑块的取值范围是 0~1，对应速度 0.25~3.0 倍，这里把想要的速度换算成滑块位置
    APP.speed_slider["value"] = (speed - 0.25) / 2.75     # the slider callback owns APP.speed
    APP.goto(0)
    settle()
    # 没给裁剪范围时就保留整个窗口；“a or b”在 a 为空时取 b
    x0, x1, y0, y1 = crop or (0, WIN_W, 0, WIN_H)

    # 函数里面还可以定义函数：grab() 截一帧、裁剪、需要时加上步骤说明
    def grab():
        f = tick()[y0:y1, x0:x1]
        if caption:
            # 正在播放动画时显示正在播的那一步，否则显示当前停留的步骤
            i = APP.anim_step if APP.anim_step is not None else APP.step
            # 例如 "5/23  栅氧化"：步骤编号从 0 开始，所以显示时 +1
            f = label(f, f"{i + 1}/{len(APP.steps)}  {APP.steps[i].title[0]}", 26)
        return f

    # ---- 录制：按下“播放”，只要还在播放或还有动画没播完，就一帧一帧截下来 ----
    frames = [grab()]
    APP.toggle_play()
    while APP.playing or APP.anim_step is not None:
        frames.append(grab())
        if APP.is_done():
            break
    # 结尾在完成画面上多停留 hold 秒（列表推导式一次生成多帧）
    frames += [grab() for _ in range(int(hold * FPS))]
    # ---- 收尾：停止播放，把速度滑块恢复到 1 倍速 ----
    APP.playing = False
    APP.speed_slider["value"] = 0.75 / 2.75
    return frames


def clip_build_sti():
    """片段 1：3 倍速录制完整的 STI 工艺流程（裁掉左侧控制面板）。"""
    frames = record_build("sti", speed=3.0, crop=(VIEW_X0, WIN_W, 0, 720))
    encode(frames, "gif_build_sti", width=900, colors=160)


def clip_build_gaa():
    """片段 2：3 倍速录制完整的 GAA（全环绕栅）工艺流程，只保留 3D 画面并标出每一步的名字。"""
    frames = record_build("gaa", speed=3.0, crop=(VIEW_X0, VIEW_X1, 120, 760), caption=True)
    encode(frames, "gif_build_gaa", width=640)


def clip_generations():
    """Finished device of every generation, orbiting, labelled with its name.

    片段 3：依次展示每一代工艺做好的器件，相机左右轻轻摆动，左上角标出工艺名称。
    """
    from fabsim3d.flows import FLOWS
    frames = []
    # 每代工艺展示 2 秒
    per = int(2.0 * FPS)
    # .items() 同时取出字典的键（流程名）和值（流程对象）
    for key, flow in FLOWS.items():
        # 直接跳到最后一步（做完的器件），相机拉远到 30
        APP.set_flow(key)
        APP.goto(len(APP.steps) - 1)
        APP.set_cam("iso")
        APP.cam_d = 30.0
        settle()
        h0 = APP.cam_h
        for k in range(per):
            # 用正弦函数让相机水平角在 ±14 度之间平滑来回摆动一次
            APP.cam_h = h0 + 14 * math.sin(2 * math.pi * k / per)
            APP.update_camera()
            frames.append(label(tick()[170:690, VIEW_X0:VIEW_X1], flow.name[0]))
    encode(frames, "gif_generations", width=540, colors=64)


def clip_inverter():
    """3D carrier simulation + VTC with IDD while Vin sweeps 0 -> VDD -> 0.

    片段 4：打开 3D 载流子仿真和电压传输曲线图，让输入电压 Vin 从 0 慢慢升到 VDD 再降回 0，
    展示反相器输出怎样翻转、电流怎样变化。
    """
    # ---- 准备：LOCOS 流程做完，切到“电学特性”页的 VTC 曲线，打开 3D 仿真 ----
    APP.set_flow("locos")
    APP.goto(len(APP.steps) - 1)
    APP.set_cam("iso")
    APP.right_tab = "elec"
    APP.plot_kind = "vtc"
    if not APP.sim3d:
        APP.toggle_sim3d()
    APP.refresh_ui()
    # ---- 录制 7 秒：用余弦函数让滑块位置 x 从 0 平滑升到 1 再降回 0 ----
    frames = []
    n = int(7 * FPS)
    for k in range(n):
        x = 0.5 - 0.5 * math.cos(2 * math.pi * k / n)     # 0 -> 1 -> 0
        APP.vin_slider["value"] = x
        APP.set_vin()
        APP.last_plot = 0
        frames.append(tick())
    encode(frames, "gif_inverter_sim", crop=(VIEW_X0, WIN_W, 0, 620), width=820, colors=160)
    # 录完关掉仿真
    APP.toggle_sim3d()


# 片段名 → 录制函数 的对照表（字典），命令行里写片段名就能找到对应的函数
CLIPS = {"build_sti": clip_build_sti, "build_gaa": clip_build_gaa,
         "generations": clip_generations, "inverter": clip_inverter}

# 这句判断的意思是：只有直接运行本脚本时才执行下面的代码（被别的文件 import 时不执行）
if __name__ == "__main__":
    # sys.argv[1:] 是命令行上写的片段名；如果一个都没写（空列表），就用 CLIPS 里的全部片段
    for name in sys.argv[1:] or CLIPS:
        CLIPS[name]()
