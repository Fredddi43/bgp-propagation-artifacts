"""Current-tick Mean sensitivity; the frozen Last implementation is untouched.

Both directed roles participate with original announcement multiplicity. Past
opposite-role stores are cleared before and after each immediate memory update,
so an idle node cannot contribute an old interaction when it becomes active.
"""
from copy import deepcopy

import torch
from torch_geometric.nn.models.tgn import MeanAggregator

from .forecast_temporal import EventTGN, _StableTGNMemory


class CurrentTickTGNMemory(_StableTGNMemory):
    """One complete timestamp batch per call, immediate updates only."""
    def reset_state(self):
        super().reset_state()
        self._current_tick = None

    def _clear_roles(self, nodes):
        empty = self.memory.new_empty(0, dtype=torch.long)
        raw = self.memory.new_empty((0, self.raw_msg_dim))
        for node in nodes:
            self.msg_s_store[node] = (empty, empty, empty, raw)
            self.msg_d_store[node] = (empty, empty, empty, raw)

    def update_state(self, src, dst, ticks, raw_msg):
        if self.training:
            raise ValueError('Current-tick memory requires immediate evaluation-mode updates')
        if not len(ticks):
            return
        tick = int(ticks[0])
        if not torch.all(ticks == tick) or tick < 0:
            raise ValueError('Current-tick memory requires one nonnegative timestamp batch')
        if self._current_tick is not None and tick <= self._current_tick:
            raise ValueError('Each complete timestamp batch must advance strictly')
        nodes = torch.cat([src, dst]).unique().tolist()
        self._clear_roles(nodes)
        super().update_state(src, dst, ticks, raw_msg)
        self._clear_roles(nodes)
        self._current_tick = tick


class EventMeanTGN(EventTGN):
    """Same initialized TGN parameters/readout; current-tick reference PyG mean."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original = self.memory
        # Preserve both learned initialization and subsequent dropout RNG stream.
        with torch.random.fork_rng(devices=[]):
            replacement = CurrentTickTGNMemory(
                original.num_nodes, original.raw_msg_dim, original.memory_dim,
                original.time_dim, deepcopy(original.msg_s_module), MeanAggregator())
            replacement.time_enc = deepcopy(original.time_enc)
            replacement.load_state_dict(original.state_dict())
        self.memory = replacement
