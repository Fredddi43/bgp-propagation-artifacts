"""ADR-0007 rung 6 / ADR-0018: the temporal model. TGN memory (Rossi et al. 2020, PyG `TGNMemory`) driven by the
event's anomalous-announcement message stream up to Δ (src = origin-side AS, dst = collector-side AS, message =
[relative time, relationship type one-hot]), then the rung-5 readout (gnn_train.TypedSAGE) over the static CAIDA
2-hop universe on [memory ‖ normalised node features]. Training loop, metrics and persistence comparison are
gnn_train.fit / gnn_train.evaluate, so rung 6 differs from rung 5 by the memory only.
"""
from __future__ import annotations

import torch
import torch.nn as nn

from .gnn_train import n_edge_types, TypedSAGE, fit

N_EDGE_TYPES = 3                      # class of the static edge (collector-side AS → origin-side AS) as tgn_data types it:
                                      # 0 = collector-side is a customer of origin-side, 1 = its provider, 2 = peer; +1 = no CAIDA edge
MSG_DIM = 1 + N_EDGE_TYPES + 1


class TGNMember(nn.Module):
    """TGN memory + rung-5 readout. The message stream is replayed in `n_batches` time-ordered chunks so the GRU memory
    is updated sequentially (a single update_state call would keep one message per node and ignore the ordering);
    within a chunk messages to the same node are mean-aggregated."""

    def __init__(self, in_dim: int, max_nodes: int, mem: int = 64, hid: int = 64, time_dim: int = 16, n_batches: int = 8, n_types: int = 3):
        super().__init__()
        from torch_geometric.nn import TGNMemory
        from torch_geometric.nn.models.tgn import IdentityMessage, MeanAggregator

        self.memory = TGNMemory(max_nodes, MSG_DIM, mem, time_dim,
                                message_module=IdentityMessage(MSG_DIM, mem, time_dim),
                                aggregator_module=MeanAggregator())
        self.readout = TypedSAGE(mem + in_dim, hid, n_types=n_types)
        self.n_batches = n_batches

    def forward(self, d: dict, device) -> torch.Tensor:
        x = d["x"].to(device); n = x.shape[0]
        # TGNMemory.forward differs between train and eval mode (updated-from-store vs raw buffer); the model must
        # compute the same function when scored as when trained, so the memory module always runs in train mode
        # (autograd is off during evaluation anyway). detach() drops any graph left by an eval-mode flush.
        self.memory.train(True)
        self.memory.detach()
        self.memory.reset_state()
        m = d["msg_src"].shape[0]
        if m:
            src, dst, t, feat = (d[k].to(device) for k in ("msg_src", "msg_dst", "msg_t", "msg_feat"))
            for idx in torch.tensor_split(torch.arange(m, device=device), min(self.n_batches, m)):
                self.memory.update_state(src[idx], dst[idx], t[idx], feat[idx])
        z, _ = self.memory(torch.arange(n, device=device))
        return self.readout(torch.cat([z, x], dim=1), d["edge_index"].to(device), d["edge_type"].to(device), d["persistence_pred"].to(device))


def prepare(delta_s: int):
    """Per-message raw features: [ts_rel/Δ, one-hot relationship type of the (dst → src) CAIDA edge, else 'none'].
    Vectorised lookup of the static edge type (sorted keys + searchsorted), no Python dict over the edge list."""

    def _prep(d: dict) -> None:
        msgs = d["msgs"]                       # columns from tgn_data: 0 = seconds after t₀, 1 = origin-side AS, 2 = collector-side AS
        keep = msgs[:, 1] != msgs[:, 2]        # drop AS-path prepending self-loops; they are not propagation
        msgs = msgs[keep]
        msgs = msgs[torch.argsort(msgs[:, 0], stable=True)]   # time order, so chunked replay is sequential
        d["msg_src"], d["msg_dst"] = msgs[:, 1].long(), msgs[:, 2].long()
        d["msg_t"] = msgs[:, 0].clamp(min=0).round().long()
        if msgs.shape[0] == 0:
            d["msg_feat"] = torch.zeros((0, MSG_DIM)); return
        n = d["x"].shape[0]
        ei, et = d["edge_index"], d["edge_type"]
        keys = ei[0] * n + ei[1]
        order = torch.argsort(keys); keys_s, et_s = keys[order], et[order]
        q = d["msg_dst"] * n + d["msg_src"]
        pos = torch.searchsorted(keys_s, q).clamp(max=max(len(keys_s) - 1, 0))
        found = (len(keys_s) > 0) & (keys_s[pos] == q)
        types = torch.where(found, et_s[pos], torch.full_like(pos, N_EDGE_TYPES))
        feat = torch.zeros((msgs.shape[0], MSG_DIM))
        feat[:, 0] = (msgs[:, 0].float() / float(delta_s)).clamp(0, 1)
        feat[torch.arange(msgs.shape[0]), 1 + types] = 1.0
        d["msg_feat"] = feat

    return _prep


def train(year="2024", delta_s: int = 30, epochs: int = 20, hid: int = 64, mem: int = 64, lr: float = 1e-3,
          pos_weight_cap: float = 20.0, seed: int = 0, tag: str = "", focal_gamma: float = 0.0, curve_weight: float = 1.0) -> dict:
    def factory(in_dim: int, events: list[dict]) -> nn.Module:
        return TGNMember(in_dim, max(d["x"].shape[0] for d in events), mem, hid)

    return fit(year, delta_s, factory, "tgn", epochs, forward=lambda m, d, dev: m(d, dev), prepare=prepare(delta_s),
               post_step=lambda m: m.memory.detach(), lr=lr, pos_weight_cap=pos_weight_cap, seed=seed,
               extra={"hid": hid, "mem": mem}, tag=tag, focal_gamma=focal_gamma, curve_weight=curve_weight)
