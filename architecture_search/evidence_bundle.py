"""Portable, content-addressed copies of reports and their referenced artifacts.

Original JSON and absolute paths are retained as provenance. The path map resolves
those paths without rewriting signed measurements or their hashes.
"""
import json
import shutil
from pathlib import Path
from .model import file_hash,write_json


def export(reports,destination,allowed_roots=None):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('bundle destination already exists')
    destination.mkdir(parents=True);objects=destination/'objects';objects.mkdir()
    pending=[Path(x).resolve() for x in reports];mapping={};missing=set();external=set();roots=list(map(str,pending))
    allowed=[Path(p).resolve() for p in allowed_roots] if allowed_roots else [p.parent for p in pending]
    def permitted(path):
        for root in allowed:
            try:path.resolve().relative_to(root);return True
            except ValueError:pass
        return False
    def references(value):
        if isinstance(value,dict):
            for k,v in value.items():yield from references(k);yield from references(v)
        elif isinstance(value,list):
            for x in value:yield from references(x)
        elif isinstance(value,str) and value.startswith('/') and '\n' not in value:
            p=Path(value)
            if not permitted(p):external.add(value)
            elif p.is_file():yield p
            elif p.suffix and not p.exists():missing.add(value)
    while pending:
        path=pending.pop();name=str(path)
        if name in mapping:continue
        if not path.is_file():raise ValueError('missing requested report: '+name)
        sha=file_hash(path);target=objects/sha
        if not target.exists():shutil.copyfile(path,target)
        if file_hash(target)!=sha:raise ValueError('artifact changed while exporting: '+name)
        mapping[name]=sha
        if path.suffix=='.json':
            try:pending.extend(references(json.loads(path.read_text())))
            except (ValueError,UnicodeError):pass
    body=dict(schema='product-evidence-bundle-v1',reports=roots,paths=mapping,
              unresolved_paths=sorted(missing),excluded_external_paths=sorted(external),note='Artifact integrity is separate from experiment completeness; failures remain in original reports.')
    write_json(destination/'manifest.json',body)
    return body


def verify(directory):
    root=Path(directory);manifest=json.loads((root/'manifest.json').read_text())
    if manifest.get('schema')!='product-evidence-bundle-v1':raise ValueError('unknown bundle')
    for original,sha in manifest['paths'].items():
        if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('invalid object name')
        p=root/'objects'/sha
        if not p.is_file() or file_hash(p)!=sha:raise ValueError('missing/corrupted bundle object: '+original)
    for report in manifest['reports']:
        if report not in manifest['paths']:raise ValueError('missing root report')
    return dict(verified=True,objects=len(set(manifest['paths'].values())),reports=len(manifest['reports']),
                unresolved_paths=manifest['unresolved_paths'])
