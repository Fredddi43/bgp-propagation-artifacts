"""Causal event-local temporal forecasting models; no global-memory claim.

TGN components follow the PyG TGN example (IdentityMessage, LastAggregator,
TGNMemory, last-neighbor sampling and time-aware TransformerConv):
https://github.com/pyg-team/pytorch_geometric/blob/master/examples/tgn.py
The reference link-prediction objective is replaced by our shared supervised
membership/extent objective. Memory resets per event. Common matured-history
features enter the readout; no additional historical raw traffic is consumed.
Thus this is an explicitly task-adapted architecture, not a reproduction of
the reference benchmark or the legacy chunked TGN/SAGE configuration.
"""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F
from torch_geometric.nn.models.tgn import TGNMemory, LastNeighborLoader

from .gnn_train import N_HORIZONS, QUANTILES


def temporal_messages(event, *, order='chronological', shuffle_seed=0):
    """Return causal local-index interactions; ties have deterministic ordering.

    Shuffling permutes interaction identities across existing timestamp slots.
    It is a frozen input perturbation unless explicitly used during training.
    Fractional seconds are retained in raw features; memory clocks use integer
    microseconds, documented rather than silently rounding to whole seconds.
    """
    msgs = event['msgs'].detach().cpu().to(torch.float64)
    n = len(event['x'])
    cutoff = float(event['observation_cutoff_s'])
    if cutoff <= 0 or not torch.isfinite(torch.tensor(cutoff)):
        raise ValueError('A finite positive observation cutoff is required')
    if msgs.ndim != 2 or msgs.shape[1] != 3 or not torch.isfinite(msgs).all():
        raise ValueError('Malformed temporal message tensor')
    if ((msgs[:, 1:] < 0) | (msgs[:, 1:] >= n) | (msgs[:, 1:] != msgs[:, 1:].long())).any():
        raise ValueError('Message endpoints must be valid local node indices')
    if (msgs[:, 0] < 0).any():
        raise ValueError('Pre-onset messages require a separately specified clock')
    msgs = msgs[(msgs[:, 0] <= cutoff) & (msgs[:, 1] != msgs[:, 2])]
    # Stable lexicographic timestamp/src/dst order removes input-file tie order.
    for column in (2, 1, 0):
        msgs = msgs[torch.argsort(msgs[:, column], stable=True)]
    times = msgs[:, 0].clone()
    endpoints = msgs[:, 1:].long()
    if order == 'shuffled':
        generator = torch.Generator().manual_seed(shuffle_seed)
        endpoints = endpoints[torch.randperm(len(msgs), generator=generator)]
    elif order != 'chronological':
        raise ValueError('Unknown temporal order control')
    types = torch.full((len(msgs),), 3, dtype=torch.long)
    edges = event['edge_index'].detach().cpu().long()
    edge_types = event['edge_type'].detach().cpu().long()
    if edges.numel() and len(msgs):
        keys = edges[0] * n + edges[1]
        sorting = keys.argsort()
        keys, edge_types = keys[sorting], edge_types[sorting]
        query = endpoints[:, 1] * n + endpoints[:, 0]
        positions = torch.searchsorted(keys, query).clamp(max=len(keys) - 1)
        types = torch.where(keys[positions] == query, edge_types[positions] % 3, types)
    features = torch.cat([(times / cutoff).float().unsqueeze(1), F.one_hot(types, 4).float()], dim=1)
    return {'src': endpoints[:, 0], 'dst': endpoints[:, 1], 'seconds': times,
            'ticks': (times * 1_000_000).round().long(), 'features': features}


class TemporalReadout(nn.Module):
    """Identical membership and ordered extent-quantile heads for both models."""
    def __init__(self, in_dim, hidden):
        super().__init__()
        self.membership = nn.Linear(hidden + in_dim, 1)
        self.curve = nn.Sequential(nn.Linear(2 * (hidden + in_dim) + 2, hidden), nn.ReLU(),
                                   nn.Linear(hidden, N_HORIZONS * len(QUANTILES)))

    def forward(self, hidden, x, event):
        seeds = event['persistence_pred'].to(hidden.device).bool()
        n_seed = torch.as_tensor(float(len(event['seed_asns'])), device=hidden.device)
        fused = torch.cat([hidden, x], dim=1)
        seed_mean = fused[seeds].mean(0) if seeds.any() else fused.mean(0)
        pooled = torch.cat([seed_mean, fused.mean(0), torch.log1p(n_seed).view(1),
                            hidden.new_tensor([len(hidden)]).log1p()])
        raw = self.curve(pooled).view(N_HORIZONS, len(QUANTILES))
        quantiles = F.softplus(raw).cumsum(dim=1) + n_seed.log1p()
        quantiles = quantiles.cummax(dim=0).values
        return self.membership(fused).squeeze(-1), quantiles


class EventGRU(nn.Module):
    """Per-node binned arrival counts plus the common static/history features."""
    def __init__(self, in_dim, hidden=64, bins=16, dropout=0.2):
        super().__init__()
        if bins < 1:
            raise ValueError('At least one time bin is required')
        self.bins, self.dropout = bins, dropout
        self.gru = nn.GRU(4, hidden, batch_first=True)
        self.readout = TemporalReadout(in_dim, hidden)

    def sequence(self, event, messages):
        n = len(event['x'])
        seq = torch.zeros((n, self.bins, 4))
        slots = (messages['seconds'] / float(event['observation_cutoff_s']) * self.bins).long().clamp(max=self.bins - 1)
        for direction, key in enumerate(('src', 'dst')):
            if len(slots):
                flat = messages[key] * self.bins + slots
                seq[:, :, direction] = torch.bincount(flat, minlength=n * self.bins).reshape(n, self.bins).log1p()
        # Event-wide cumulative distinct message endpoints; never full labels.
        seen = set()
        for index in range(self.bins):
            mask = slots == index
            seen.update(messages['src'][mask].tolist())
            seen.update(messages['dst'][mask].tolist())
            seq[:, index, 2] = torch.log1p(torch.tensor(float(len(seen))))
            seq[:, index, 3] = (index + 1) / self.bins
        return seq

    def forward(self, event, device=None, *, order='chronological', shuffle_seed=0):
        device = device or next(self.parameters()).device
        messages = temporal_messages(event, order=order, shuffle_seed=shuffle_seed)
        _, hidden = self.gru(self.sequence(event, messages).to(device))
        hidden = F.dropout(hidden[-1], self.dropout, self.training)
        return self.readout(hidden, event['x'].to(device), event)


class DeterministicLastAggregator(nn.Module):
    """Latest tick, then last canonical row; integer reductions, unique writes.

    Stable message stores and PyG's outgoing-then-incoming concatenation make
    same-tick ties prefer incoming messages, then the greatest counterpart ID.
    Exact duplicate interactions have identical message features.
    """
    def forward(self, msg, index, ticks, dim_size):
        latest = ticks.new_full((dim_size,), torch.iinfo(ticks.dtype).min)
        latest.scatter_reduce_(0, index, ticks, reduce='amax', include_self=True)
        rows = torch.arange(len(ticks), device=ticks.device)
        eligible = torch.where(ticks == latest[index], rows, -1)
        chosen = rows.new_full((dim_size,), -1)
        chosen.scatter_reduce_(0, index, eligible, reduce='amax', include_self=True)
        out = msg.new_zeros((dim_size, msg.shape[-1]))
        valid = chosen >= 0
        out[valid] = msg[chosen[valid]]
        return out


class _StableTGNMemory(TGNMemory):
    def _update_msg_store(self, src, dst, ticks, raw_msg, msg_store):
        permutation = torch.argsort(src, stable=True)
        nodes, counts = src[permutation].unique_consecutive(return_counts=True)
        for node, indices in zip(nodes.tolist(), permutation.split(counts.tolist())):
            msg_store[node] = (src[indices], dst[indices], ticks[indices], raw_msg[indices])


class DeterministicLastNeighborLoader(LastNeighborLoader):
    """Keep greatest interaction IDs per node without duplicate-index writes."""
    def insert(self, src, dst):
        if not len(src):
            return
        neighbors = torch.cat([src, dst])
        nodes = torch.cat([dst, src])
        ids = torch.arange(self.cur_e_id, self.cur_e_id + len(src), device=src.device).repeat(2)
        self.cur_e_id += len(src)
        # Lexicographic node / interaction-ID ascending. Self loops were removed,
        # so each node has at most one occurrence of a particular interaction ID.
        permutation = torch.argsort(ids, stable=True)
        permutation = permutation[torch.argsort(nodes[permutation], stable=True)]
        nodes, neighbors, ids = nodes[permutation], neighbors[permutation], ids[permutation]
        unique, counts = nodes.unique_consecutive(return_counts=True)
        ends = counts.cumsum(0).repeat_interleave(counts)
        reverse_rank = ends - 1 - torch.arange(len(nodes), device=nodes.device)
        keep = reverse_rank < self.size
        nodes, neighbors, ids, reverse_rank = nodes[keep], neighbors[keep], ids[keep], reverse_rank[keep]
        self._assoc[unique] = torch.arange(len(unique), device=nodes.device)
        slots = self._assoc[nodes] * self.size + reverse_rank
        dense_ids = ids.new_full((len(unique) * self.size,), -1)
        dense_neighbors = neighbors.new_zeros(len(unique) * self.size)
        dense_ids[slots], dense_neighbors[slots] = ids, neighbors
        combined_ids = torch.cat([self.e_id[unique], dense_ids.view(-1, self.size)], dim=1)
        combined_neighbors = torch.cat([self.neighbors[unique], dense_neighbors.view(-1, self.size)], dim=1)
        selected_ids, positions = combined_ids.topk(self.size, dim=1)
        self.e_id[unique] = selected_ids
        self.neighbors[unique] = combined_neighbors.gather(1, positions)


class EventTGN(nn.Module):
    """Reference-component TGN with zero event memory and common-history readout.

    Replay each microsecond timestamp group once. Memory always uses immediate
    update semantics during fitting and prediction, preserving one function.
    Neither event labels nor messages from any other event enter memory.
    """
    def __init__(self, in_dim, max_nodes, hidden=64, memory_dim=64, time_dim=16,
                 neighbors=10, dropout=0.2):
        super().__init__()
        from torch_geometric.nn import TransformerConv
        from torch_geometric.nn.models.tgn import IdentityMessage
        if hidden % 2 or max_nodes < 1 or neighbors < 1:
            raise ValueError('TGN needs even hidden width and positive nodes/neighbors')
        self.memory = _StableTGNMemory(max_nodes, 5, memory_dim, time_dim,
                                      IdentityMessage(5, memory_dim, time_dim), DeterministicLastAggregator())
        self.memory.time_enc = _SecondsEncoder(self.memory.time_enc)
        self.attention = TransformerConv(memory_dim, hidden // 2, heads=2,
                                         dropout=dropout, edge_dim=time_dim + 5)
        self.readout = TemporalReadout(in_dim, hidden)
        self.neighbors = neighbors

    def forward(self, event, device=None, *, order='chronological', shuffle_seed=0):
        device = device or next(self.parameters()).device
        n = len(event['x'])
        if n > self.memory.num_nodes:
            raise ValueError('Event exceeds declared memory capacity')
        messages = {k: v.to(device) for k, v in temporal_messages(event, order=order, shuffle_seed=shuffle_seed).items()}
        # Set only the memory's mode flag: train(False) would flush old stores.
        # Its Linear/GRUCell children have no train/eval-dependent behavior.
        self.memory.training = False
        self.memory.detach()
        self.memory.reset_state()
        neighborhood = DeterministicLastNeighborLoader(self.memory.num_nodes, size=self.neighbors, device=device)
        ticks = messages['ticks']
        _, counts = torch.unique_consecutive(ticks, return_counts=True)
        start = 0
        for count in counts.tolist():
            stop = start + count
            src, dst = messages['src'][start:stop], messages['dst'][start:stop]
            self.memory.update_state(src, dst, ticks[start:stop], messages['features'][start:stop])
            neighborhood.insert(src, dst)
            start = stop
        nodes, edges, ids = neighborhood(torch.arange(n, device=device))
        if not torch.equal(nodes, torch.arange(n, device=device)):
            raise ValueError('Temporal neighborhood remapped candidate node order')
        memory, last = self.memory(nodes)
        relative = (last[edges[0]] - ticks[ids]).float()
        attrs = torch.cat([self.memory.time_enc(relative), messages['features'][ids]], dim=1)
        hidden = F.relu(self.attention(memory, edges, attrs))
        return self.readout(hidden, event['x'].to(device), event)


class _SecondsEncoder(nn.Module):
    """Keep exact integer microsecond clocks but encode elapsed seconds."""
    def __init__(self, encoder):
        super().__init__()
        self.encoder = encoder
        self.out_channels = encoder.out_channels

    @property
    def lin(self):
        return self.encoder.lin

    def forward(self, ticks):
        return self.encoder(ticks / 1_000_000)

    def reset_parameters(self):
        self.encoder.reset_parameters()
