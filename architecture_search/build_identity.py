#!/usr/bin/env python3
"""Verify the assembled NGen source manifest against its current checkout."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

RESOURCE='META-INF/ngen/source-inputs.sha256'


def source_files(root):
    files=[root/'build.sbt']
    files.extend(p for p in (root/'src/main').rglob('*') if p.is_file())
    for p in (root/'project').rglob('*'):
        parts=p.relative_to(root/'project').parts
        if p.is_file() and 'target' not in parts and 'project' not in parts[:-1] and p.suffix in ('.sbt','.scala','.properties'):
            files.append(p)
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def verify(root, binary=None):
    root=Path(root).resolve();binary=Path(binary) if binary else root/'ngen.bat'
    try:
        with zipfile.ZipFile(binary) as jar:
            entries=jar.read(RESOURCE).decode().splitlines()
        expected={}
        for row in entries:
            value,name=row.split('\t')
            path=PurePosixPath(name)
            if len(value)!=64 or any(c not in '0123456789abcdef' for c in value) or path.is_absolute() or '..' in path.parts or name in expected:
                raise ValueError('invalid source manifest entry')
            expected[name]=value
        if not expected or 'build.sbt' not in expected:raise ValueError('empty or incomplete source manifest')
        current=source_files(root)
        changed=sorted(name for name in expected.keys()|current.keys() if expected.get(name)!=current.get(name))
        return {'verified':not changed,'binary':str(binary.resolve()),'source_files':len(expected),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
                'changed_inputs':changed,'manifest_sha256':hashlib.sha256(('\n'.join(entries)+'\n').encode()).hexdigest()}
    except (OSError,KeyError,ValueError,zipfile.BadZipFile) as error:
        return {'verified':False,'binary':str(binary.resolve()),'error':str(error),
                'action':'Run sbt assembly in this NGen checkout; legacy binaries have no verifiable build manifest.'}

