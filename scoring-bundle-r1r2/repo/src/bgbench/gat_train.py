"""ADR-0007 rung 5 reference: the architecture family used by published BGP graph-learning detectors (GraphBGP, BEAM,
MADBGP and the AS-graph cluster use GCN/GAT message passing on the static AS graph) repurposed to the membership task.
Two-layer GAT (4 heads) on the same tensors, features and heads as the relational SAGE; the comparison isolates what
the relationship-typed aggregation adds over a generic attention-based graph model."""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .gnn_train import N_HORIZONS, QUANTILES, fit, sage_forward


class GATMember(nn.Module):
    def __init__(self, in_dim: int, hid: int = 64, heads: int = 4, dropout: float = 0.2):
        super().__init__()
        from torch_geometric.nn import GATConv
        self.g1 = GATConv(in_dim, hid // heads, heads=heads, dropout=dropout)
        self.g2 = GATConv(hid, hid // heads, heads=heads, dropout=dropout)
        self.out = nn.Linear(hid + in_dim, 1)
        self.curve = nn.Sequential(nn.Linear(2 * hid + 2, hid), nn.ReLU(), nn.Linear(hid, N_HORIZONS * len(QUANTILES)))
        self.dropout = dropout

    def forward(self, x, edge_index, edge_type, seed_mask, n_seed=None):
        h = F.dropout(F.elu(self.g1(x, edge_index)), self.dropout, self.training)
        h = F.dropout(F.elu(self.g2(h, edge_index)), self.dropout, self.training)
        logits = self.out(torch.cat([h, x], dim=1)).squeeze(-1)
        seed = seed_mask.bool()
        seed_count = seed.sum().float() if n_seed is None else torch.as_tensor(n_seed, dtype=x.dtype, device=x.device)
        pooled = torch.cat([h[seed].mean(0) if seed.any() else h.mean(0), h.mean(0),
                            torch.log1p(seed_count).view(1), torch.log1p(torch.tensor(float(h.shape[0]), device=h.device)).view(1)])
        q = torch.cumsum(F.softplus(self.curve(pooled).view(N_HORIZONS, len(QUANTILES))), dim=1) + torch.log1p(seed_count)
        return logits, q


def train(year="2024", delta_s: int = 30, epochs: int = 20, hid: int = 64, lr: float = 1e-3, pos_weight_cap: float = 20.0, seed: int = 0,
          tag: str = "", focal_gamma: float = 0.0, curve_weight: float = 1.0) -> dict:
    return fit(year, delta_s, lambda in_dim, _: GATMember(in_dim, hid), "gat", epochs, forward=sage_forward, lr=lr,
               pos_weight_cap=pos_weight_cap, seed=seed, extra={"hid": hid}, tag=tag, focal_gamma=focal_gamma, curve_weight=curve_weight)
