#!/usr/bin/env python3
"""Move NGen's explicit control ROM words to equivalent readmemh files."""
import argparse
import json
from pathlib import Path
import re


def externalize(rtl: Path):
    declarations={};roms={};module=None;files={};temporary=rtl.with_suffix('.rom-tmp')
    try:
        with rtl.open() as source,temporary.open('w') as output:
            for line in source:
                head=re.match(r'\s*module\s+(\w+)\b',line)
                if head:module=head.group(1)
                for declaration in re.finditer(r'reg\s+\[(\d+):0\]\s+(control_\d+_rom)\[0:BUNDLE_COUNT-1\]',line):
                    declarations[(module,declaration.group(2))]=int(declaration.group(1))+1
                word=re.fullmatch(r"\s*(control_\d+_rom)\[(\d+)\]=(\d+)'h([0-9a-fA-F]+);\s*",line)
                if word:
                    name,index,width,value=word.group(1),int(word.group(2)),int(word.group(3)),word.group(4)
                    key=(module,name)
                    if module is None or declarations.get(key)!=width:raise ValueError('control ROM declaration/word width mismatch')
                    if int(value,16).bit_length()>width:raise ValueError('control ROM word exceeds declared width')
                    if key not in roms:
                        if index!=0:raise ValueError('ROM must begin at address zero')
                        path=rtl.parent/f'{rtl.stem}.{module}.{name}.mem'
                        if path.exists():raise ValueError('ROM artifact already exists')
                        files[key]=path.open('w');roms[key]={'path':str(path.resolve()),'words':0,'word_bits':width}
                        output.write(f'    $readmemh({json.dumps(str(path.resolve()))}, {name});\n')
                    if index!=roms[key]['words']:raise ValueError('ROM addresses must be unique and contiguous')
                    files[key].write(value.zfill((width+3)//4)+'\n');roms[key]['words']+=1
                else:output.write(line)
                if re.match(r'\s*endmodule\b',line):module=None
        if not roms:raise ValueError('no supported explicit control ROM initializers')
        temporary.replace(rtl)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        for handle in files.values():handle.close()
    return list(roms.values())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('rtl',type=Path);a=p.parse_args();print(json.dumps(externalize(a.rtl.resolve()),indent=2))
