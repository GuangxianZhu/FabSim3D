"""Registry of process flows (one per technology generation).

To add a generation: create a module exposing FLOW (a process_core.Flow) and
append it here.  The UI lists flows in this order.

【中文说明】
这个文件是“工艺流程登记表”。
芯片制造技术分好几代 (“工艺代”)，每一代的做法不同。本文件夹 (flows) 里每个 .py 文件描述一代：
    locos.py   约 1 µm 年代的经典工艺 (LOCOS 场氧隔离 + 铝导线)
    sti.py     约 0.25 µm 年代 (浅槽隔离 STI + 化学机械抛光 CMP + LDD 侧墙)
    hkmg.py    28 nm 高 k 介质 + 金属栅
    finfet.py  鳍式晶体管 FinFET
    gaa.py     环栅纳米片 GAA
    cfet.py    上下堆叠的互补晶体管 CFET
每个文件里都有一个名叫 FLOW 的对象，里面按顺序装着这一代的全部工艺步骤。
本文件把它们收集到一个字典里，界面 (UI) 就能列出所有工艺代让用户选择。
想增加新的一代：新建一个文件、在里面定义 FLOW，然后把它加到下面的 import 和 FLOWS 里。
"""
# “from . import ...” 的意思是：从当前文件夹 (那个点 . 就代表“本文件夹”) 导入这几个模块 (即 .py 文件)。
from . import cfet, finfet, gaa, hkmg, locos, sti

# FLOWS 是一个“字典” (dict)：通过一个名字 (键 key) 查到对应的东西 (值)。
# 这里键是每个工艺的短名字 (如 "locos")，值是对应的 FLOW 对象。
# 写法 {f.key: f for f in (...)} 叫“字典推导式”：
#   依次取出括号里的每个 FLOW，临时叫它 f，然后把 “f.key → f” 放进字典。
# 括号里的顺序就是界面上列出各工艺代的顺序 (从老到新)。
FLOWS = {f.key: f for f in (locos.FLOW, sti.FLOW, hkmg.FLOW, finfet.FLOW, gaa.FLOW, cfet.FLOW)}
# 程序启动时默认显示的工艺：经典 LOCOS (最简单，适合入门)。
DEFAULT_FLOW = "locos"


def get_flow(key: str):
    """Look up a flow by its key.

    根据短名字 (例如 "sti") 取出对应的工艺流程对象。
    “key: str” 只是提示：这个参数应该是一段文字 (字符串 str)，不影响运行。
    """
    return FLOWS[key]
