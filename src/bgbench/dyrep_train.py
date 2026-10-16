"""ADR-0007 rung 6 alternative: a DyRep-style temporal model (Trivedi et al. 2019) on the same tensors and readout as
tgn_train, so TGN vs DyRep is the empirical call the plan asked for.

DyRep updates a node's embedding when it takes part in an event as z_v ← tanh(W_struct · h_N(u) + W_rec · z_v + W_t · φ(Δt)):
localized embedding propagation from the *other* endpoint's neighbourhood (h_N(u) = mean memory of u's structural
neighbours in the CAIDA graph), self-propagation, and an exogenous drive from elapsed time. We implement that update for
every message of the Δ window in time order (chunked like the TGN), without the temporal point-process intensity loss —
the membership / curve heads are the supervision here, as for the TGN. Readout: the rung-5 relational SAGE on [z ‖ x].
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .gnn_train import n_edge_types, TypedSAGE, fit
from .tgn_train import MSG_DIM, prepare


class DyRepMember(nn.Module):
    def __init__(self, in_dim: int, mem: int = 64, hid: int = 64, time_dim: int = 16, n_chunks: int = 8, n_types: int = 3):
        super().__init__()
        self.mem = mem
        self.w_struct = nn.Linear(mem, mem, bias=False)
        self.w_rec = nn.Linear(mem, mem, bias=False)
        self.w_t = nn.Linear(time_dim, mem, bias=False)
        self.w_msg = nn.Linear(MSG_DIM, mem, bias=True)
        self.time_freq = nn.Parameter(torch.randn(time_dim))
        self.readout = TypedSAGE(mem + in_dim, hid, n_types=n_types)
        self.n_chunks = n_chunks

    def _phi(self, dt: torch.Tensor) -> torch.Tensor:
        return torch.cos(dt.float().unsqueeze(1) * self.time_freq)

    def forward(self, d: dict, device) -> torch.Tensor:
        x = d["x"].to(device); n = x.shape[0]
        ei = d["edge_index"].to(device)
        z = torch.zeros(n, self.mem, device=device)
        last_t = torch.zeros(n, device=device)
        m = d["msg_src"].shape[0]
        if m:
            src, dst, t, feat = (d[k].to(device) for k in ("msg_src", "msg_dst", "msg_t", "msg_feat"))
            for idx in torch.tensor_split(torch.arange(m, device=device), min(self.n_chunks, m)):
                s, r, tt, ff = src[idx], dst[idx], t[idx], feat[idx]
                # neighbourhood aggregate of the *source* endpoint over the static graph: mean of z over its neighbours
                deg = torch.zeros(n, device=device).index_add_(0, ei[0], torch.ones(ei.shape[1], device=device)).clamp(min=1)
                h_nb = torch.zeros(n, self.mem, device=device).index_add_(0, ei[0], z[ei[1]]) / deg.unsqueeze(1)
                upd_dst = torch.tanh(self.w_struct(h_nb[s]) + self.w_rec(z[r]) + self.w_t(self._phi(tt - last_t[r])) + self.w_msg(ff))
                upd_src = torch.tanh(self.w_struct(h_nb[r]) + self.w_rec(z[s]) + self.w_t(self._phi(tt - last_t[s])) + self.w_msg(ff))
                z = z.clone(); z[r] = upd_dst; z[s] = upd_src            # last write wins inside a chunk (mean-free, like the paper's sequential update)
                last_t = last_t.clone(); last_t[r] = tt.float(); last_t[s] = tt.float()
        return self.readout(torch.cat([z, x], dim=1), ei, d["edge_type"].to(device), d["persistence_pred"].to(device))


def train(year="2024", delta_s: int = 30, epochs: int = 20, hid: int = 64, mem: int = 64, lr: float = 1e-3,
          pos_weight_cap: float = 20.0, seed: int = 0, tag: str = "", focal_gamma: float = 0.0, curve_weight: float = 1.0) -> dict:
    return fit(year, delta_s, lambda in_dim, evs: DyRepMember(in_dim, mem, hid, n_types=n_edge_types(evs)), "dyrep", epochs, forward=lambda m, d, dev: m(d, dev),
               prepare=prepare(delta_s), lr=lr, pos_weight_cap=pos_weight_cap, seed=seed, extra={"hid": hid, "mem": mem}, tag=tag,
               focal_gamma=focal_gamma, curve_weight=curve_weight)
