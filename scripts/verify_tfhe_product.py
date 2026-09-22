#!/usr/bin/env python3
"""Cross-check the exact CGGI19 lvl1 product corpus against pinned PolyMulNaive."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import wide_products
from architecture_search.model import artifact_manifest,write_json,digest
ROOT=Path(__file__).resolve().parents[1]

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'build/tfhe-exact')
    p.add_argument('--random-count',type=int,default=64);a=p.parse_args(argv)
    if a.random_count<0:p.error('random count must be nonnegative')
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    command=['g++','-std=c++20','-O2','-mavx2','-DUSE_CGGI19','-Iinclude','-Ithird_party/TFHEpp/include',
             '-Ithird_party/TFHEpp/thirdparties/spqlios','tests/cpp/tfhepp_exact_product_reference.cpp','-o',str(out/'reference')]
    with (out/'build.log').open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    w=wide_products.tfhe_workload();pairs=wide_products.vectors(w,random_count=a.random_count)
    payload='\n'.join(' '.join(f'{x:x}' for x in left+right) for left,right in pairs)+'\n'
    result=subprocess.run([str(out/'reference')],input=payload,text=True,capture_output=True,check=True,timeout=600)
    actual=[int(x,16) for x in result.stdout.split()]
    expected=[x for left,right in pairs for x in wide_products.schoolbook(w,left,right)]
    if actual!=expected:raise ValueError('TFHEpp/Python exact product disagreement')
    write_json(out/'verification.json',dict(schema='tfhe-exact-product-v1',passed=True,workload=w,products=len(pairs),
        corpus_sha256=digest(pairs),outputs_sha256=digest(actual),command=command,
        tfhepp_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'third_party/TFHEpp',text=True).strip(),
        artifacts=artifact_manifest([out/'reference',ROOT/'include/tfhepp_exact_product.hpp',ROOT/'tests/cpp/tfhepp_exact_product_reference.cpp']),
        scope='PolyMulNaive and Python agree; separate RTL campaign must check this same default corpus.'))
    print(f'PASS {len(pairs)} exact N=1024 products');return 0

if __name__=='__main__':raise SystemExit(main())
