"""Short 'why does this step exist' tips per process step (shown in guide mode)."""

STEP_TIPS = {
    # ---------------------------------------------------------------- shared / LOCOS
    "wafer": ("硅片就是“地基”。P 型的意思是掺了少量硼，硅里多出可以移动的“空穴”（缺一个电子的位置）。",
              "The wafer is the foundation. 'p-type' means a little boron was added, leaving mobile "
              "'holes' (missing electrons)."),
    "padox": ("氮化硅直接压在硅上会把硅“绷裂”，这层薄氧化层像一块垫子，缓冲两者的应力。",
              "Nitride pressed straight onto silicon would crack it; this thin oxide is a cushion "
              "that absorbs the stress."),
    "nwell_litho": ("光刻就像用模板喷漆：光刻胶是漆，掩膜是模板，紫外光照到的地方会被洗掉。"
                    "之后的注入只能打进“洗掉”的窗口里。",
                    "Lithography is stencil painting: resist is the paint, the mask is the stencil, "
                    "and UV-exposed areas wash away. The next implant only enters those windows."),
    "nwell_implant": ("把磷离子加速后像子弹一样打进硅里，给 PMOS 造一块 N 型的“地盘”。"
                      "剂量决定了 PMOS 的阈值 → 讲解页实验课②。",
                      "Phosphorus ions are fired into silicon like bullets, creating n-type ground for "
                      "the PMOS. The dose sets the PMOS threshold → Lesson ②."),
    "nwell_drive": ("刚打进去的杂质只在表面薄薄一层，高温下原子会慢慢向深处“扩散”，就像墨水在水里化开。",
                    "Freshly implanted dopants sit near the surface; at high temperature they diffuse "
                    "deeper, like ink spreading in water."),
    "nitride": ("氧气几乎钻不过氮化硅，所以它像一把“伞”，下一步只让没盖伞的地方长出厚氧化层。",
                "Oxygen barely gets through nitride, so it acts as an umbrella: only uncovered areas "
                "will grow thick oxide."),
    "active_litho": ("这一步决定晶体管“住在哪里”。留下光刻胶的地方是有源区，其他地方要做成绝缘的隔离带。",
                     "This step decides where transistors live: resist marks the active areas; the "
                     "rest becomes insulating isolation."),
    "nitride_etch": ("等离子体刻蚀像“喷砂”，带电粒子竖直向下轰击，只削掉没被光刻胶保护的氮化硅。",
                     "Plasma etching is like sand-blasting straight down: only nitride not protected "
                     "by resist is removed."),
    "locos": ("厚厚的场氧把相邻晶体管隔开，防止它们“串电”。氧会从氮化硅边缘钻进去，形成鸟嘴。"
              "鸟嘴会让窄管子的 Vt 升高 → 看参数表里的 ΔVtn。",
              "Thick field oxide separates neighbouring transistors so they don't leak into each "
              "other. Oxygen sneaks under the nitride edge, forming the bird's beak, which raises "
              "the Vt of narrow devices (see ΔVtn)."),
    "nitride_strip": ("“伞”的任务完成了，用只溶解氮化硅的热磷酸把它拿掉，露出干净的硅表面准备做栅极。",
                      "The umbrella's job is done; hot phosphoric acid dissolves only the nitride, "
                      "exposing clean silicon for the gate."),
    "gate_ox": ("整颗芯片最关键的一层：栅极就是隔着它“遥控”沟道的。它越薄，控制越强 → 实验课② 第 1 个任务。",
                "The most critical layer on the chip: the gate controls the channel through it. "
                "Thinner means stronger control → Lesson ②, task 1."),
    "poly_dep": ("多晶硅将成为栅极，也就是水龙头的“把手”。它耐高温，后面可以先做栅、再做源漏。",
                 "Polysilicon becomes the gate, the tap handle. It survives high temperatures, so the "
                 "gate can be made before the source/drain."),
    "gate_litho": ("这一步画出的线宽就是栅长 L，是整个工艺最细的线条，“0.25 µm 工艺”说的就是它 → 实验课④。",
                   "The line drawn here is the gate length L, the finest feature of the process; "
                   "'0.25 µm technology' refers to it → Lesson ④."),
    "gate_etch": ("把多晶硅刻成细长的栅极条。刻蚀必须停在只有几 nm 厚的栅氧上，不能刻穿。",
                  "The poly is etched into narrow gate lines, stopping on an oxide only a few nm "
                  "thick without punching through."),
    "nplus": ("栅极自己挡住了沟道，离子只能打进它两边，源漏自动和栅对齐，这叫“自对准”。",
              "The gate shields the channel, so ions only land on either side: source and drain "
              "align to the gate by themselves (self-alignment)."),
    "pplus": ("和上一步一样，只是换成硼、给 PMOS 做 P+ 源漏。NMOS 和 PMOS 各用一块掩膜，轮流被保护。",
              "Same as before but with boron for the PMOS. NMOS and PMOS take turns being protected "
              "by their own masks."),
    "sd_anneal": ("注入会把晶格撞乱，杂质也还没“上岗”。短暂高温让它们归位、开始导电。",
                  "Implantation scrambles the crystal and dopants are not yet active; a brief high "
                  "temperature puts them in place to conduct."),
    "ild": ("在器件和金属线之间盖一层厚玻璃绝缘，相当于楼板，让金属线可以从晶体管上方跨过去。",
            "A thick glass insulator between devices and wiring acts like a floor slab, letting "
            "metal lines cross over the transistors."),
    "contact": ("在绝缘层上打孔，就像在楼板上开洞走电线，让金属能接触到源、漏和栅。",
                "Holes through the insulator, like openings in a floor for cables, let metal reach "
                "source, drain and gate."),
    "metal_dep": ("整片铺满铝，同时把接触孔填满。下一步再把多余的铝刻掉，只留下“导线”。",
                  "Aluminium blankets the wafer and fills the holes; the next step etches away "
                  "everything except the wires."),
    "metal_pattern": ("导线把两个晶体管连成反相器。切到“电学特性”页，或在讲解页做实验课①，看它怎么工作。",
                      "The wires join the two transistors into an inverter. Open the Electrical tab, "
                      "or Lesson ①, to see it work."),
    "done": ("完成！打开讲解页的实验课，动手改参数，看看工艺怎样决定芯片的性能。",
             "Done! Open a lesson on the guide tab and change parameters to see how the process "
             "shapes performance."),
    # ---------------------------------------------------------------- STI flow
    "sti_litho": ("和 LOCOS 一样先定有源区，但接下来不是“长”隔离层，而是在硅上“挖沟”再填满。",
                  "As with LOCOS the active areas come first, but isolation will be dug as trenches "
                  "and filled rather than grown."),
    "sti_etch": ("在晶体管之间挖出浅沟。沟是竖直的，没有鸟嘴，晶体管可以挨得更近。",
                 "Shallow trenches are dug between transistors. Their walls are vertical, with no "
                 "bird's beak, so devices can sit closer together."),
    "sti_liner": ("给沟壁“抹一层腻子”：修复刻蚀损伤、把尖角磨圆。尖角会让电场集中，让窄管子提前打开。",
                  "Like plastering the trench walls: repairs etch damage and rounds sharp corners, "
                  "which would otherwise crowd the field and turn narrow devices on early."),
    "sti_fill": ("用氧化物把沟填满，填的时候整片晶圆都被盖上，表面高低不平。",
                 "Oxide fills the trenches but also covers the whole wafer, leaving a bumpy surface."),
    "sti_cmp": ("像打磨木地板：旋转的抛光垫加上研磨液把多余的氧化物磨平，碰到更硬的氮化硅就停下。"
                "表面平了，后面的光刻才能对焦。",
                "Like sanding a floor: a spinning pad with slurry grinds away excess oxide and stops "
                "on the harder nitride. A flat surface lets later lithography stay in focus."),
    "sti_strip": ("去掉氮化硅后，STI 几乎和硅表面一样平。和 LOCOS 对比：STI 让窄管子的 Vt 略降（看 ΔVtn）。",
                  "With the nitride gone, the STI is almost flush with silicon. Compared with LOCOS, "
                  "STI slightly lowers narrow-device Vt (see ΔVtn)."),
    "nwell_implant_he": ("能量很高的离子能直接打到很深的地方，不用再长时间高温扩散，减少对已有结构的影响。",
                         "Very high-energy ions land deep directly, avoiding a long hot diffusion that "
                         "would disturb existing structures."),
    "nwell_anneal": ("温度和时间都比 LOCOS 时代小很多。“热预算”越小，之前做好的浅结构越不容易变形。",
                     "Much lower temperature and time than in the LOCOS era: a smaller thermal "
                     "budget keeps earlier shallow structures intact."),
    "nldd": ("先在栅边做一段“缓坡”：浅而淡的 N- 区。它降低漏端电场，让沟道两端的结很浅，能抑制短沟道效应 → 实验课④。",
             "First a gentle 'ramp' next to the gate: a shallow, light n- region. It softens the "
             "drain field and keeps the junctions at the channel ends shallow, curbing "
             "short-channel effects → Lesson ④."),
    "pldd": ("PMOS 同样做一段浅的 P- 延伸区。", "The PMOS gets its own shallow p- extensions."),
    "spacer_dep": ("像给栅极“刷一层漆”，顶面、侧面、地面都盖上同样厚的一层。",
                   "Like a coat of paint on the gate: top, sides and floor all get the same thickness."),
    "spacer_etch": ("不用模板，直接竖着往下刻。平的地方很快刻穿，栅两侧竖着的那部分最厚，留了下来，成为侧墙。",
                    "No stencil: etch straight down. Flat areas clear first; the tall film beside "
                    "the gate survives as the spacers."),
    "nplus_sp": ("这次“栅 + 侧墙”一起挡住离子，深而浓的源漏离沟道远一点，中间留下 LDD 缓坡。",
                 "This time gate plus spacers block the ions, so the deep, heavy S/D stays back "
                 "from the channel and the LDD ramp remains in between."),
    "pplus_sp": ("PMOS 一侧同样以侧墙对准做 P+ 源漏。", "Same for the PMOS: spacer-aligned p+ S/D."),
    "sd_anneal_ldd": ("退火后形成“浅 LDD + 深源漏”的台阶结构。到“电学特性 → Vt-L”图看看它对短沟道效应的作用。",
                      "The anneal leaves a stepped 'shallow LDD + deep S/D' profile. See its effect "
                      "on the Electrical → Vt-L plot."),
    "ild_cmp": ("先盖厚玻璃再磨平，比 LOCOS 时代的高温“回流”更平，温度也更低。",
                "Thick glass, then polish flat: flatter than the old high-temperature reflow, and cooler."),
}
