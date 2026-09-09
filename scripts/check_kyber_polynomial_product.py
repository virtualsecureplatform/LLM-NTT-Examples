#!/usr/bin/env python3
"""Check complete ring products through RTL NTT/INTT with host base multiplication."""
import argparse,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import file_hash,run,write_json
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    r=json.loads(a.record.read_text());rtl=Path(r['rtl_path']);rtl=rtl if rtl.is_absolute() else ROOT/rtl
    if not r.get('correct') or file_hash(rtl)!=r['rtl_hash']:p.error('correct unchanged RTL required')
    out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()):p.error('use a fresh directory')
    out.mkdir(parents=True,exist_ok=True);shutil.copyfile(rtl,out/'KyberHPM1PE.v')
    for name in ('kyber_polynomial_product_test.cpp','kyber_pe1_reference_test.cpp'):shutil.copyfile(ROOT/'tests/cpp'/name,out/name)
    inputs={str(x):file_hash(x) for x in out.iterdir() if x.is_file()}
    build=run(['verilator','--cc','--exe','--build','--top-module','KyberHPM1PE','-Wno-fatal','-j','4','KyberHPM1PE.v','kyber_polynomial_product_test.cpp'],out,out/'build.log',600)
    test=run([str(out/'obj_dir/VKyberHPM1PE')],out,out/'test.log',120) if build['returncode']==0 else {}
    correct=test.get('returncode')==0 and 'PASS 4 ML-KEM polynomial products' in (out/'test.log').read_text() and all(file_hash(Path(x))==v for x,v in inputs.items())
    write_json(out/'results.json',{'correct':correct,'build':build,'test':test,'inputs':inputs,'source_record_sha256':file_hash(a.record),'scope':'Four full negacyclic polynomial products; NGen RTL performs forward/inverse incomplete NTT, host C++ performs quadratic multiplication. Independent schoolbook oracle. No hardware base-multiplier or complete ML-KEM implementation claim.'});print(json.dumps({'correct':correct,'results':str(out/'results.json')}));return 0 if correct else 1
if __name__=='__main__':raise SystemExit(main())
