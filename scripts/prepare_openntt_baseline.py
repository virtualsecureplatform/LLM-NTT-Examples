#!/usr/bin/env python3
"""Generate an exact-field OpenNTT reference in an isolated tree (generation evidence only)."""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import oracle
from architecture_search.model import run,source_identity,file_hash,write_json
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--openntt-root',type=Path,default=Path(__file__).resolve().parents[2]/'OpenNTT')
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--pe',type=int,default=2)
p.add_argument('--memory-opt',type=int,choices=[0,1],default=0)
a=p.parse_args();w=json.loads(a.campaign.read_text())['workload'];oracle.validate(w)
if w.get('kind')!='generic' or w['n']<64 or int(w['q'])<=64:p.error('OpenNTT adapter requires generic N>=64 and an explicit prime >64')
if a.pe<1 or a.pe&(a.pe-1) or a.pe>w['n']//2:p.error('PE must be a power of two at most N/2')
out=a.output_dir.resolve();source=a.openntt_root.resolve()
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
# Copy only generator inputs; never allow upstream --c to modify the reference checkout.
for part in ('tool','hardware'):
    shutil.copytree(source/part,out/part,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
(out/'software/Testing').mkdir(parents=True,exist_ok=True)
kind=('mintt_dif_rn' if w.get('direction')=='inverse' else 'mfntt_dit_nr') if w.get('negacyclic') else ('intt_dit_rn' if w.get('direction')=='inverse' else 'fntt_dit_nr')
root=int(w['psi'] if w.get('negacyclic') else w['root']);q=int(w['q'])
command=[sys.executable,'openntt.py','--c=1','--transf_type=NTT',f'--ntt_type={kind}',f"--n={w['n']}",'--q_fixed=1','--q_count=1',f'--q_list={q}',f'--tw_list={root}',f'--tw_inv_list={pow(root,-1,q)}',f'--io_band={2*a.pe}','--mem_depth=1','--coeff_arith=0',f'--memory_opt={a.memory_opt}']
process=run(command,out/'tool',out/'generation.log',600)
artifacts={str(f.relative_to(out)):file_hash(f) for f in (out/'hardware').rglob('*') if f.is_file()}
for f in (out/'tool/RomContent').glob('*'):
    if f.is_file():artifacts[str(f.relative_to(out))]=file_hash(f)
write_json(out/'record.json',{'schema':'ntt-external-generation-v1','generator':'OpenNTT','source':source_identity(source),'workload':w,'configuration':{'pe':a.pe,'memory_opt':a.memory_opt,'ntt_type':kind},'process':process,'artifacts':artifacts,'correct':False,'evidence_stage':'generation','comparison_eligible':False,'boundary':'Scalar host RAM load/store; io_band is internal bandwidth. Independent RTL simulation and boundary normalization required before comparison.'})
raise SystemExit(0 if process['returncode']==0 else 1)
