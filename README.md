# FabSim3D — CMOS 工艺 3D 教学演示 (Panda3D)

平面 CMOS 前端工艺的交互式 3D 演示：从 P 型硅片开始，经过 N 阱、LOCOS 场氧、多晶硅栅、
自对准源漏注入、ILD、接触孔和金属 1，最后得到一个 **CMOS 反相器**，并由工艺参数直接推导出它的**电学特性**。

![仿真模式](docs/screenshot_sim.png)

## 运行

```bash
pip install -r requirements.txt
python main.py              # 中文界面
python main.py --lang en    # English UI
python main.py --size 1920x1080 --fullscreen
```

需要一个带中文字形的字体。程序会自动查找微软雅黑/黑体 (Windows)、苹方 (macOS)、
Noto CJK/文泉驿 (Linux)；也可以把任意 `.ttf/.otf/.ttc` 放进 `fonts/` 目录，
或设置环境变量 `FABSIM3D_FONT=/path/to/font`。找不到字体时会自动切换到英文。

## 界面

| 区域 | 内容 |
|---|---|
| 左栏 | 22 个工艺步骤列表（可以点击跳转）、上一步/播放/下一步、动画速度、剖面切割与切面位置、棱线/标注开关、视角预设、中英切换、测验模式 |
| 中间 | 3D 晶圆模型。左键拖动旋转，右键拖动平移，滚轮缩放。快捷键：← → 切换步骤，空格播放/暂停 |
| 右栏 · 工艺说明 | 当前步骤的原理说明、当前子阶段（涂胶/曝光/显影…）、工艺参数、材料图例 |
| 右栏 · 电学特性 | Id-Vg（对数坐标）、Id-Vd（NMOS 第一象限/PMOS 第三象限）、反相器 VTC、瞬态响应；Vin 滑块会在所有图上标出工作点 |
| 右栏 · 工艺参数 | tox、衬底掺杂 Na、N 阱注入剂量、栅长 L、Wn/Wp、VDD、负载 CL，调完立即更新 Vt、曲线和 3D 模型（L 会改变栅极宽度） |

**3D 载流子仿真**：工艺完成后打开，会自动开启剖面，沟道反型层会随 Vin 亮起，
电子（青色）和空穴（橙色）按电流大小流动，终端标签显示实时电压。点“播放瞬态”会用瞬态仿真结果驱动动画。

**测验模式**：每完成一步弹出一道选择题，附带解析，左栏显示得分。

## 工艺流程（22 步，7 块掩膜）

1 P 型衬底 → 2 垫氧化 → 3 N 阱光刻 → 4 磷注入 → 5 去胶+阱推进 → 6 Si3N4 淀积 → 7 有源区光刻 →
8 氮化硅刻蚀 → 9 LOCOS 场氧（鸟嘴） → 10 去氮化硅/垫氧 → 11 栅氧化 → 12 多晶硅淀积 → 13 栅极光刻 →
14 多晶硅栅刻蚀 → 15 N+ 源漏注入 → 16 P+ 源漏注入 → 17 RTA 激活退火 → 18 BPSG 层间介质 →
19 接触孔 → 20 溅射铝 → 21 金属刻蚀 → 22 完成（反相器）

动画效果包括：薄膜生长/淀积、旋涂光刻胶、掩膜版与紫外光线、曝光区变色、显影溶解、
等离子体刻蚀粒子、离子注入粒子（会被光刻胶和栅极挡住）、高温退火发光、LOCOS 上下双向生长。

> 纵向尺寸做了夸张处理（薄膜被放大），以便观察。阱接触、钝化层、多层金属等省略。

## 电学模型 (`fabsim3d/device_model.py`)

- **阈值电压**：Vt = Vfb ± 2φF ± Qdep/Cox，采用双掺杂多晶硅栅（NMOS 用 n+ poly，PMOS 用 p+ poly），并计入固定氧化层电荷
- **N 阱浓度**：Nd = 注入剂量 / 阱深 (2 µm)
- **漏电流**：强反型时是 Level-1 平方律，用 EKV 插值平滑过渡到亚阈值区，并加入沟道长度调制 λ = 0.05/L
- **反相器**：VTC 用向量化二分法求解 Idn = Idp，并提取 VM、VIL/VIH、噪声容限和增益
- **瞬态**：用 RK2 积分 CL·dVout/dt = Idp − Idn，提取 tpHL/tpLH

## 代码结构

```
main.py                 入口 (命令行参数, 无界面截图)
fabsim3d/app.py           Panda3D 应用：三栏 UI、相机、步骤控制、测验、电学面板
fabsim3d/scene.py         晶圆渲染、动画、粒子、剖面、3D 标注、载流子
fabsim3d/process_flow.py  工艺流程数据 (步骤/子阶段/动作/说明/测验)
fabsim3d/geometry.py      x-z 截面凸多边形沿 y 拉伸的实体、矩形运算、保形淀积
fabsim3d/device_model.py  器件与反相器模型 (纯 numpy)
fabsim3d/plots.py         matplotlib → Panda3D 纹理
fabsim3d/materials.py     材料颜色与名称
fabsim3d/i18n.py          中英文字符串
```

想加一步工艺，就在 `process_flow.STEPS` 里加一个 `Step`。动作有：`deposit`、`coat`、`expose`、`develop`、
`pattern`(刻蚀)、`implant`、`strip`、`recolor`、`glow`。

## 测试

```bash
pip install pytest
python -m pytest -q        # 模型 + 工艺几何 + 离屏 GUI 冒烟测试
```

无界面截图（文档和调试用）：

```bash
python main.py --shot out.png --step 21 --tab elec --sim --vin 1.2 --plot idvd
python main.py --shot litho.png --step 2 --anim 2.0     # 截取第 3 步动画中途 2 秒的画面
```
