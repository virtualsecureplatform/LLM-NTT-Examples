#!/usr/bin/env python3
"""Prepare an exact-field Proteus OP1 SDF/MDC reference in an isolated tree."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import oracle
from architecture_search.model import run,file_hash,digest,write_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--proteus-root',type=Path,default=Path(__file__).resolve().parents[2]/'proteus')
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--architecture',choices=['sdf','mdc'],default='sdf')
p.add_argument('--reduction',choices=['montgomery','sparse'],default='montgomery')
a=p.parse_args();w=json.loads(a.campaign.read_text())['workload'];oracle.validate(w)
n=int(w['n']);q=int(w['q']);width=q.bit_length();bits=n.bit_length()-1
if w.get('kind')!='generic' or not 4<=bits<=12:p.error('this Proteus adapter requires a generic transform with 16<=N<=4096 (upstream ROM wrapper limit)')
if a.reduction=='sparse' and q not in (268369921,18446744069414584321):p.error('Proteus sparse reducer only implements its fixed 28-bit and Goldilocks fields')
if width<28:p.error('this adapter currently supports coefficient widths 28..64')
source=a.proteus_root.resolve();out=a.output_dir.resolve()
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
neg=w.get('negacyclic',False)
core=('sdf/nwc_op_1' if neg else 'sdf/op_1_2') if a.architecture=='sdf' else ('mdc/ntt_nwc_mdc_op_1' if neg else 'mdc/ntt_mdc_op_1_2')
(out/'py').mkdir(parents=True)
for path in (source/'toolchain/py').glob('*.py'):shutil.copyfile(path,out/'py'/path.name)
shutil.copytree(source/'toolchain/hw/common',out/'hardware/common')
shutil.copytree(source/'toolchain/hw'/core,out/'hardware/core')
inputs={str(f.relative_to(out)):file_hash(f) for f in out.rglob('*') if f.is_file()}
# The multiplier and Montgomery directories contain different modules with
# identical names. Namespace the Montgomery-local copies without merging logic.
compatibility_edits=[]
import re
for path in (out/'hardware/common/wlmont').glob('*.sv'):
    text=path.read_text();updated=re.sub(r'\bcsa_tree\b','ProteusWlCsaTree',text)
    updated=re.sub(r'\bcsa_2\b','ProteusWlCsa2',updated)
    if text!=updated:
        before=file_hash(path);path.write_text(updated)
        compatibility_edits.append({'path':str(path.relative_to(out)),'change':'namespace Montgomery-local CSA modules','before_sha256':before,'after_sha256':file_hash(path)})
# The upstream demo overwrites requested fields with hard-coded examples. Supply
# exact validated parameters while preserving its twiddle-generation algorithms.
adicity=((q-1)&-(q-1)).bit_length()-1
word=min(16,adicity);loops=(width+word-1)//word
r=pow(2,word*loops,q);rinv=pow(r,-1,q)
generator=out/'py/ntt_demo.py';text=generator.read_text()
start=text.index('q = None\n');end=text.index('print("\\nParameters:',start)
parameters=f"q={q}\npsi={int(w.get('psi',1))}\npsi_inv={pow(int(w.get('psi',1)),-1,q)}\nw={int(w['root'])}\nw_inv={pow(int(w['root']),-1,q)}\nR_w={r}\nR_wp={rinv}\n"
generator.write_text(text[:start]+parameters+text[end:])
(out/'py/hw/constant').mkdir(parents=True);(out/'py/hw/tb').mkdir()
command=[sys.executable,str(generator),'MERGED' if neg else 'NORMAL',a.architecture.upper(),'1',str(bits),str(width),'MONTGOMERY' if a.reduction=='montgomery' else 'ADDSHIFT']
process=run(command,out/'py',out/'generation.log',600)
red_latency=loops+(int((2*width-47)/word) if width-word<=24 else loops)+1 if a.reduction=='montgomery' else (2 if width==28 else 3)
values={'LOGQ':width,'LOGN':bits,'TYPE_RED':int(a.reduction=='montgomery'),'IS_Q_FIXED':1,'Q':f"{width}'d{q}",
        'DELAY_ADD':1,'DELAY_SUB':1,'DSP_W':24,'DSP_H':17,'DELAY_MUL':2,'W':word,'L':loops,'MULLAT':1,'ADDPIP':0,
        'R_w':f"{width}'d{r if a.reduction=='montgomery' else 0}",'TOTAL_LATENCY':red_latency,'DELAY_RED':red_latency,
        'DELAY_DIV2':1,'DELAY_BRAM':1,'DELAY_BROM':1,'DELAY_FIFO':1,'BTF_GS':0}
(out/'hardware/parameters.vh').write_text('// Exact workload configuration supplied by architecture_search.\n'+''.join(f'parameter {k} = {v};\n' for k,v in values.items()))
if process['returncode']==0:shutil.copyfile(out/'py/hw/constant/tw_roms.v',out/'hardware/tw_roms.v')
artifacts={str(f.relative_to(out)):file_hash(f) for f in (out/'hardware').rglob('*') if f.is_file()}
write_json(out/'record.json',{'schema':'ntt-external-generation-v1','generator':'Proteus','workload':w,'configuration':{'architecture':a.architecture,'reduction':a.reduction,'op':1,'montgomery_word_bits':word,'montgomery_loops':loops},
'source':{'revision':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD']).decode().strip(),'input_hash':digest(inputs),'inputs':inputs},
'compatibility_edits':compatibility_edits,'parameter_binding':parameters,'adapted_generator_hash':file_hash(generator),'parameters':values,'process':process,'artifacts':artifacts,'correct':None,'comparison_eligible':False})
print(out/'record.json')
raise SystemExit(0 if process['returncode']==0 else 1)
