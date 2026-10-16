"""Run with pytest, or directly in the cluster torch environment."""
if __name__ == "__main__":
    import torch
else:
    import pytest
    torch = pytest.importorskip("torch")
from bgbench.tgn_train import prepare
from bgbench.dyrep_train import last_write_positions, last_endpoint_updates


def test_temporal_message_without_caida_edge():
    event = {"x": torch.zeros(2, 1), "msgs": torch.tensor([[1., 0., 1.]], dtype=torch.float64),
             "edge_index": torch.empty((2, 0), dtype=torch.long), "edge_type": torch.empty(0, dtype=torch.long)}
    prepare(30)(event)
    assert event['msg_feat'].shape == (1, 5)
    assert event['msg_feat'][0, 4] == 1


def test_legality_edge_retains_base_relationship_message_type():
    event = {"x": torch.zeros(2, 1), "msgs": torch.tensor([[1., 0., 1.]], dtype=torch.float64),
             "edge_index": torch.tensor([[1], [0]]), "edge_type": torch.tensor([5])}
    prepare(30)(event)
    assert event['msg_feat'][0, 3] == 1


def test_duplicate_temporal_writes_have_explicit_last_winner():
    nodes = torch.tensor([1, 2, 1, 0, 2, 1])
    touched, positions = last_write_positions(nodes, 4)
    assert touched.tolist() == [0, 1, 2]
    assert positions.tolist() == [3, 5, 4]
    updates = torch.arange(6., requires_grad=True)
    state = torch.zeros(4).index_copy(0, touched, updates[positions])
    assert state.tolist() == [3., 5., 4., 0.]
    state.sum().backward()
    assert updates.grad.tolist() == [0., 0., 0., 1., 1., 1.]


def test_last_endpoint_write_is_chronologically_latest():
    # Node 1 is the source at t=1 and destination at t=2.
    dst, src = torch.tensor([2, 1]), torch.tensor([1, 3])
    touched, updates, times = last_endpoint_updates(dst, src, torch.tensor([1., 2.]),
        torch.tensor([[10.], [20.]]), torch.tensor([[11.], [21.]]), 4)
    assert times[touched == 1].item() == 2.
    assert updates[touched == 1].item() == 20.


def test_all_model_extent_heads_keep_outside_candidate_seeds():
    from bgbench.gnn_train import TypedSAGE, sage_forward
    from bgbench.gat_train import GATMember
    from bgbench.tgn_train import TGNMember
    from bgbench.dyrep_train import DyRepMember
    event = {'x': torch.zeros(3, 2), 'edge_index': torch.tensor([[0, 1], [1, 0]]),
             'edge_type': torch.tensor([0, 1]), 'persistence_pred': torch.tensor([1., 0., 0.]),
             'seed_asns': torch.tensor([10, 99, 100]), 'n_seed_all': 1,
             'msgs': torch.empty((0, 3), dtype=torch.float64)}
    prepare(30)(event)
    models = [TypedSAGE(2, 8), GATMember(2, 8), TGNMember(2, 3, mem=8, hid=8), DyRepMember(2, mem=8, hid=8)]
    for model in models:
        model.eval()
        head = model.readout.curve if hasattr(model, 'readout') else model.curve
        with torch.no_grad():
            head[-1].weight.zero_(); head[-1].bias.fill_(-30.)
            _, curve = model(event, 'cpu') if hasattr(model, 'readout') else sage_forward(model, event, 'cpu')
        assert torch.all(torch.expm1(curve) >= 3. - 1e-5), type(model).__name__


def test_exported_curve_evidence_uses_full_observed_counts():
    from bgbench.gnn_train import TypedSAGE, evaluate
    event = {'event_id': '20250101T120000', 'x': torch.zeros(3, 2),
             'edge_index': torch.tensor([[0, 1], [1, 0]]), 'edge_type': torch.tensor([0, 1]),
             'persistence_pred': torch.tensor([1., 0., 0.]), 'asn': torch.tensor([10, 20, 30]),
             'seed_asns': torch.tensor([10, 99, 100]), 'target_asns': torch.tensor([10, 20, 99, 100]),
             'y': torch.tensor([1., 1., 0.]), 'measurement_version': 2,
             'n_seed': 1, 'n_seed_all': 1, 'curve': torch.tensor([3., 4., 4., 4.])}
    model = TypedSAGE(2, 8)
    with torch.no_grad():
        model.curve[-1].weight.zero_(); model.curve[-1].bias.fill_(-30.)
    evaluation = evaluate(model, [event], 'cpu', save_probabilities=True)
    row = evaluation['_rows'].row(0, named=True)
    asns, probabilities = evaluation['_probabilities'][event['event_id']]
    assert row['n_seed'] == 3 and row['true_size'] == 4
    assert row['jaccard_persist'] == .75
    import json
    for suffix, column in [('model', 'predicted_asns_at05'), ('model_tuned', 'predicted_asns_tuned')]:
        prediction = set(json.loads(row[column])); truth = {10, 20, 99, 100}
        assert {10, 99, 100} <= prediction
        assert row['jaccard_' + suffix] == len(prediction & truth) / len(prediction | truth)
        assert prediction == {10,99,100} | set(asns[probabilities >= .5].tolist())
    assert abs(row['curve_pred_2h'] - 3.) < 1e-5
    assert row['curve_true_2h'] == row['curve_true_3'] == 4
    assert abs(row['curve_smape_2h_persist'] - 2/7) < 1e-6
    assert abs(row['curve_smape_2h_model'] - 2/7) < 1e-6
    event['observation_cutoff_s'] = 900
    event['curve'] = torch.tensor([1., 3., 4., 4.])
    late = evaluate(model, [event], 'cpu')['_rows'].row(0, named=True)
    assert [late[f'curve_evaluated_{i}'] for i in range(4)] == [False,False,True,True]
    assert abs(late['curve_smape_persist'] - 2/7) < 1e-6



def test_count_forecasts_exclude_already_observed_targets():
    from bgbench.gnn_train import curve_forecast_mask, pinball
    assert curve_forecast_mask({'observation_cutoff_s':30}).tolist() == [True]*4
    assert curve_forecast_mask({'observation_cutoff_s':300}).tolist() == [False,True,True,True]
    future = torch.as_tensor(curve_forecast_mask({'observation_cutoff_s':900}))
    assert future.tolist() == [False,False,True,True]
    quantiles = torch.ones(4,3,requires_grad=True)
    target = torch.zeros(4)
    pinball(quantiles[future],target[future]).backward()
    assert not quantiles.grad[:2].any() and quantiles.grad[2:].abs().sum() > 0

def test_dyrep_retained_updates_match_dense_values_gradients_and_rng():
    """Repeated endpoints, ties, empty streams and readout dropout keep semantics."""
    from copy import deepcopy
    from bgbench.dyrep_train import DyRepMember
    from bgbench.gnn_train import full_seed_count

    def dense(model, d):
        x, ei = d['x'], d['edge_index']; n = len(x)
        z = torch.zeros(n, model.mem); last_t = torch.zeros(n)
        m = len(d['msg_src'])
        if m:
            for idx in torch.tensor_split(torch.arange(m), min(model.n_chunks, m)):
                s, r, tt, ff = (d[k][idx] for k in ('msg_src','msg_dst','msg_t','msg_feat'))
                deg = torch.zeros(n).index_add_(0, ei[0], torch.ones(ei.shape[1])).clamp(min=1)
                h = torch.zeros(n,model.mem).index_add_(0,ei[0],z[ei[1]]) / deg.unsqueeze(1)
                dst = torch.tanh(model.w_struct(h[s])+model.w_rec(z[r])+model.w_t(model._phi(tt-last_t[r]))+model.w_msg(ff))
                src = torch.tanh(model.w_struct(h[r])+model.w_rec(z[s])+model.w_t(model._phi(tt-last_t[s]))+model.w_msg(ff))
                touched, updates, times = last_endpoint_updates(r,s,tt,dst,src,n)
                z=z.index_copy(0,touched,updates);last_t=last_t.index_copy(0,touched,times)
        return model.readout(torch.cat([z,x],1),ei,d['edge_type'],d['persistence_pred'],n_seed=full_seed_count(d))

    for m in (0, 2, 97):
        torch.manual_seed(17)
        d={'x':torch.randn(4,3), 'edge_index':torch.tensor([[0,1,2,3],[1,2,3,0]]),
           'edge_type':torch.tensor([0,1,2,0]), 'persistence_pred':torch.tensor([1.,0.,0.,0.]),
           'seed_asns':torch.tensor([1]), 'msg_src':torch.arange(m)%4,
           'msg_dst':(torch.arange(m)*3+1)%4, 'msg_t':torch.arange(m,dtype=torch.float64)//2,
           'msg_feat':torch.randn(m,5)}
        model=DyRepMember(3,mem=8,hid=8,n_chunks=8); reference=deepcopy(model)
        batches=[]
        hook=model.w_msg.register_forward_pre_hook(lambda _module, inputs: batches.append(len(inputs[0])))
        torch.manual_seed(91);actual=model(d,'cpu');rng=torch.get_rng_state()
        torch.manual_seed(91);expected=dense(reference,d)
        assert torch.equal(rng,torch.get_rng_state())
        for a,b in zip(actual,expected): torch.testing.assert_close(a,b,rtol=2e-5,atol=2e-6)
        sum(v.square().sum() for v in actual).backward()
        sum(v.square().sum() for v in expected).backward()
        for (name,a),(_,b) in zip(model.named_parameters(),reference.named_parameters()):
            assert (a.grad is None)==(b.grad is None), name
            if a.grad is not None: torch.testing.assert_close(a.grad,b.grad,rtol=5e-5,atol=3e-6,msg=name)
        assert all(size<=len(d['x']) for size in batches)
        hook.remove()
    touched, positions=last_write_positions(torch.empty(0,dtype=torch.long),4)
    assert len(touched)==len(positions)==0

if __name__ == '__main__':
    test_count_forecasts_exclude_already_observed_targets()
    test_temporal_message_without_caida_edge()
    test_duplicate_temporal_writes_have_explicit_last_winner()
    test_legality_edge_retains_base_relationship_message_type()
    test_last_endpoint_write_is_chronologically_latest()
    test_all_model_extent_heads_keep_outside_candidate_seeds()
    test_exported_curve_evidence_uses_full_observed_counts()
    test_dyrep_retained_updates_match_dense_values_gradients_and_rng()
    print('8 graph/temporal regression checks passed')
