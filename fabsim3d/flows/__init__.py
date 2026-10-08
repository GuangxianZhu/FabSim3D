"""Registry of process flows (one per technology generation).

To add a generation: create a module exposing FLOW (a process_core.Flow) and
append it here.  The UI lists flows in this order.
"""
from . import cfet, finfet, gaa, hkmg, locos, sti

FLOWS = {f.key: f for f in (locos.FLOW, sti.FLOW, hkmg.FLOW, finfet.FLOW, gaa.FLOW, cfet.FLOW)}
DEFAULT_FLOW = "locos"


def get_flow(key: str):
    return FLOWS[key]
