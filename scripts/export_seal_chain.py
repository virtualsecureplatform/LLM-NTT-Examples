#!/usr/bin/env python3
"""Export ordered CKKS primes using the same built SEAL library as a trace."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import file_hash,write_json
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    capture=a.capture_dir.resolve();out=a.output_dir.resolve();trace=capture/'results.json';t=json.loads(trace.read_text())
    if t.get('correct') is not True or t.get('seal_revision')!='119dc32e135cb89c1062076a69310d4413ebc824':p.error('verified pinned capture required')
    if out.exists() and any(out.iterdir()):p.error('use a fresh directory')
    out.mkdir(parents=True,exist_ok=True);source=ROOT/'scripts/fixtures/seal_chain.cpp';library=capture/'build/lib/libseal-4.1.a';exe=out/'export-chain'
    subprocess.run(['g++','-std=c++17',str(source),'-I'+str(capture/'source/native/src'),'-I'+str(capture/'build/native/src'),str(library),'-lpthread','-o',str(exe)],check=True,timeout=120)
    chain=json.loads(subprocess.check_output([str(exe)],text=True,timeout=30))
    if {(v['q'],v['psi']) for v in chain}!={(v['q'],v['psi']) for v in t['events']}:raise ValueError('chain differs from captured fields')
    write_json(out/'chain.json',{'schema':'ntt-seal-ckks-chain-v1','n':8192,'chain':chain,'seal_revision':t['seal_revision'],'capture_sha256':file_hash(trace),'inputs':{'cpp_sha256':file_hash(source),'library_sha256':file_hash(library),'executable_sha256':file_hash(exe)},'scope':'Ordered CoeffModulus::Create(8192,{60,40,40,60}) output from the instrumented capture library; last prime is special, not an ordinary active ciphertext limb.'})
    print(out/'chain.json')
if __name__=='__main__':main()
