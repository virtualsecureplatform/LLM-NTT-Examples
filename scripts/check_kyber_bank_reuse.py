#!/usr/bin/env python3
"""Verify repeated Kyber bank swaps using unchanged reference vectors and readers."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.model import file_hash,run,source_identity,write_json
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--include-reference-sources',action='store_true');p.add_argument('--rtl',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--timeout',type=float,default=300)
a=p.parse_args();out=a.output_dir.resolve()
if not math.isfinite(a.timeout) or a.timeout<=0:p.error('timeout must be finite and positive')
if out.exists() and any(out.iterdir()):p.error('output directory must be empty')
out.mkdir(parents=True,exist_ok=True);started=time.monotonic();shutil.copyfile(a.rtl,out/'KyberHPM1PE.v')
for name in ('kyber_bank_reuse_test.cpp','kyber_pe1_reference_test.cpp'):shutil.copyfile(ROOT/'tests/cpp'/name,out/name)
(out/'vectors').mkdir()
for name in ('KYBER_DIN0.txt','KYBER_DIN1.txt','KYBER_DIN0_MFNTT.txt','KYBER_DIN1_MFNTT.txt'):shutil.copyfile(ROOT/'variants/kyber-polmul-hw/pe1/test_pe1'/name,out/'vectors'/name)
extras=[]
if a.include_reference_sources:
    task=json.loads((ROOT/'tasks/kyber_ntt_256_p12_pe1.json').read_text());(out/'extras').mkdir()
    for name in task['verilog']['extra_sources']:
        destination=out/'extras'/Path(name).name
        if destination.exists():raise ValueError('duplicate reference filename')
        shutil.copyfile(ROOT/name,destination);extras.append(str(destination))
verification={str(path):file_hash(path) for path in out.rglob('*') if path.is_file()}
write_json(out/'manifest.json',{'source':source_identity(ROOT),'runner_sha256':file_hash(Path(__file__)),'original_rtl':str(a.rtl.resolve()),'original_rtl_sha256':file_hash(a.rtl),'verification':verification})
run(['verilator','--version'],out,out/'version.log',10)
build=run(['verilator','--cc','--exe','--build','--top-module','KyberHPM1PE','-Wno-fatal','-j','4','KyberHPM1PE.v','kyber_bank_reuse_test.cpp',*extras],out,out/'build.log',max(0,a.timeout-(time.monotonic()-started)))
test=run([str(out/'obj_dir/VKyberHPM1PE')],out,out/'test.log',max(0,a.timeout-(time.monotonic()-started))) if build['returncode']==0 else {}
log=(out/'test.log').read_text() if (out/'test.log').exists() else ''
correct=test.get('returncode')==0 and 'PASS 16 Kyber operations' in log and all(file_hash(Path(path))==value for path,value in verification.items())
write_json(out/'results.json',{'correct':correct,'build':build,'test':test,'verification':verification});print(json.dumps({'correct':correct,'results':str(out/'results.json')}));raise SystemExit(0 if correct else 1)
