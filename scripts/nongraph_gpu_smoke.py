"""Source-independent dependency smoke; synthetic counts never enter paper results."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch

parser=argparse.ArgumentParser()
parser.add_argument('kind',choices=['tsfm','chronos'])
parser.add_argument('output',type=Path)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
torch.manual_seed(11)
report={'synthetic_only':True,'torch':torch.__version__,'cuda':torch.cuda.is_available(),'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}
assert report['cuda']
counts=np.arange(1,122,dtype=float)
if args.kind=='tsfm':
    from tsfm_curves import moirai_forecaster,timesfm_forecaster
    models={'moirai_small':moirai_forecaster('small')}
    name,forecast=timesfm_forecaster();models[name]=forecast
    report['models']={}
    for name,forecast in models.items():
        report['models'][name]=[]
        for context_length in [2,6,16]:
            horizon=121-context_length
            values=np.asarray(forecast(counts[:context_length],horizon),dtype=float).reshape(-1)
            row={"context_length":context_length,"length":len(values),"finite":bool(np.isfinite(values).all())}
            print(json.dumps({"model":name,**row}),flush=True)
            assert len(values)>=horizon and np.isfinite(values).all(), name
            report['models'][name].append(row)
else:
    from chronos import BaseChronosPipeline
    model=BaseChronosPipeline.from_pretrained('amazon/chronos-2',device_map='cuda',torch_dtype=torch.float32)
    inputs=[torch.tensor(np.log1p(counts),dtype=torch.float32)]
    fitted=model.fit(inputs,prediction_length=60,finetune_mode='lora',learning_rate=1e-4,num_steps=1,batch_size=2,context_length=60,min_past=30,output_dir=str(args.output/'training'),bf16=torch.cuda.is_bf16_supported(),tf32=torch.cuda.get_device_capability()[0]>=8)
    fitted.save_pretrained(args.output/'final_adapter')
    report['adapter_files']=sorted(p.name for p in (args.output/'final_adapter').iterdir())
    assert (args.output/'final_adapter/adapter_model.safetensors').is_file()
    for name,pipeline in [('zeroshot',model),('lora',fitted)]:
        q,mean=pipeline.predict_quantiles([inputs[0][:6]],prediction_length=114,quantile_levels=[.5])
        values=np.asarray(q[0].detach().cpu())
        assert np.isfinite(values).all()
        report[name]={'shape':list(values.shape),'finite':True}
(args.output/'complete.json').write_text(json.dumps(report,indent=1));print(json.dumps(report),flush=True)
