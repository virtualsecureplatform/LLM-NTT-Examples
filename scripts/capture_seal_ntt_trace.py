#!/usr/bin/env python3
"""Capture and independently check actual SEAL 4.1.2 CKKS-example NTT calls."""
import argparse
import collections
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import oracle
from architecture_search.model import file_hash,write_json
ROOT=Path(__file__).resolve().parents[1]
REVISION='119dc32e135cb89c1062076a69310d4413ebc824'

def natural_order(values):
    width=len(values).bit_length()-1
    return [values[int(f'{i:0{width}b}'[::-1],2)] for i in range(len(values))]

def verify_samples(directory,events):
    samples=[]
    domains={(e['n'],e['q'],e['psi'],e['direction']) for e in events}
    for n,q,psi,direction in sorted(domains):
        q,psi=int(q),int(psi)
        p=directory/f'{n}_{q}_{direction}.txt'
        rows=[list(map(int,line.split())) for line in p.read_text().splitlines()]
        if len(rows)!=n or any(len(row)!=2 for row in rows):raise ValueError('incomplete sample')
        inputs=[row[0]%q for row in rows];actual=[row[1]%q for row in rows]
        w={'n':n,'q':str(q),'psi':str(psi),'root':str(psi*psi%q),'negacyclic':True,'direction':direction}
        oracle.validate(w)
        if direction=='inverse':inputs=natural_order(inputs)
        else:actual=natural_order(actual)
        if oracle.transform(inputs,w)!=actual:raise ValueError(f'SEAL/oracle mismatch: {p}')
        samples.append({'workload':w,'sample':p.name,'sha256':file_hash(p),'correct':True})
    return samples

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seal-source',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    source=a.seal_source.resolve();out=a.output_dir.resolve()
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    if revision!=REVISION:p.error('requires pinned SEAL 4.1.2 commit '+REVISION)
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source,text=True).strip():p.error('SEAL source must be unmodified')
    if out.exists() and any(out.iterdir()):p.error('use a fresh output directory')
    out.mkdir(parents=True,exist_ok=True);src=out/'source';shutil.copytree(source,src,ignore=shutil.ignore_patterns('.git','build'))
    ntt=src/'native/src/seal/util/ntt.cpp';example=src/'native/examples/5_ckks_basics.cpp';mainfile=src/'native/examples/examples.cpp'
    originals={str(x.relative_to(src)):file_hash(x) for x in (ntt,example,mainfile)}
    header=src/'native/src/seal/util/ntt_trace.h';shutil.copyfile(ROOT/'scripts/fixtures/seal_ntt_trace.h',header)
    text=ntt.read_text();text='#include "seal/util/ntt_trace.h"\n'+text
    for function,direction in [('ntt_negacyclic_harvey_lazy','forward'),('inverse_ntt_negacyclic_harvey_lazy','inverse')]:
        needle=f'void {function}(CoeffIter operand, const NTTTables &tables)\n        {{'
        if text.count(needle)!=1:raise ValueError('unexpected SEAL NTT source')
        text=text.replace(needle,needle+f'\n            ntt_trace::Capture capture(operand.ptr(), size_t(1) << tables.coeff_count_power(), tables.modulus().value(), tables.get_root(), "{direction}");')
    ntt.write_text(text)
    text=example.read_text();text='#include "seal/util/ntt_trace.h"\n'+text
    # Label actual API calls without changing their ordering or operands.
    lines=[]
    for line in text.splitlines():
        stripped=line.strip()
        if stripped.startswith(('KeyGenerator keygen(', 'keygen.', 'encoder.encode(', 'encryptor.encrypt(', 'evaluator.', 'decryptor.decrypt(', 'encoder.decode(')) and stripped.endswith(';'):
            label=stripped.split('(')[0].replace('KeyGenerator ','')
            lines.append('    ntt_trace::set_phase("'+label+'");')
        lines.append(line)
    example.write_text('\n'.join(lines)+'\n')
    mainfile.write_text('#include "examples.h"\nint main() { example_ckks_basics(); return 0; }\n')
    build=out/'build';data=out/'trace';data.mkdir()
    commands=[['cmake3','-S',str(src),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DSEAL_BUILD_EXAMPLES=ON','-DSEAL_BUILD_DEPS=OFF','-DSEAL_USE_MSGSL=OFF','-DSEAL_USE_ZLIB=OFF','-DSEAL_USE_ZSTD=OFF','-DSEAL_USE_INTEL_HEXL=OFF'],['cmake3','--build',str(build),'-j','4']]
    for i,cmd in enumerate(commands):
        with (out/f'build-{i}.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
    executable=build/'bin/sealexamples';env={**os.environ,'NTT_TRACE_DIR':str(data)}
    with (out/'example.log').open('w') as log:subprocess.run([str(executable)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    events=[json.loads(line) for line in (data/'events.jsonl').read_text().splitlines()]
    if not events:raise ValueError('empty trace')
    samples=verify_samples(data,events)
    counts=collections.Counter((e['phase'],e['q'],e['direction']) for e in events)
    write_json(out/'results.json',{'schema':'ntt-seal-ckks-trace-v1','correct':True,'seal_revision':revision,'application':'unmodified arithmetic of native/examples/5_ckks_basics.cpp','n':8192,'configured_chain_bits':[60,40,40,60],'special_prime_position':3,'events':events,'counts':[{'phase':phase,'q':q,'direction':d,'calls':c} for (phase,q,d),c in sorted(counts.items())],'samples':samples,'inputs':{'originals':originals,'instrumented':{str(x.relative_to(src)):file_hash(x) for x in (ntt,example,mainfile,header)},'executable_sha256':file_hash(executable),'runner_sha256':file_hash(Path(__file__)),'events_sha256':file_hash(data/'events.jsonl')},'scope':'Actual sequential transform-call trace, including key generation and application evaluation; not an FPGA timing measurement. Samples normalized modulo q and converted between SEAL bit-reversed and natural order before independent oracle comparison.'})
    print(json.dumps({'calls':len(events),'verified_samples':len(samples),'results':str(out/'results.json')}))
if __name__=='__main__':main()
