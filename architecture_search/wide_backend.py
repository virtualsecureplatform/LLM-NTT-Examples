"""Version-2 NGen RNS and SGen exact digit-product generation."""
import json
import re
import time
from pathlib import Path
from . import wide_products as wide, wide_rtl, numerics, primitive_proofs, product_rtl
from .build_identity import verify
from .model import digest,file_hash,write_json,run


def leaf_workload(w,c):
    return wide.workload(w['n'],15,w['ring']) if c['arithmetic']=='split-radix16' else w


def compose(w,c,metas,fields):
    if c['generator']=='ngen':
        return '\n'.join([wide_rtl.field_product(w,f,*metas[2*i:2*i+2],i)
                          for i,f in enumerate(fields)]+[wide_rtl.rns_product(w,fields)])
    leaf=leaf_workload(w,c);text=wide_rtl.fft_leaf(leaf,c,*metas)
    if c['arithmetic']=='split-radix16':
        text=text.replace('module SearchTop(','module DigitProduct(')+'\n'+wide_rtl.split_fft(w,leaf)
    return text


def certificate(w,c,metas,files):
    if c['generator']=='sgen':
        leaf=leaf_workload(w,c);numeric=numerics.certify(leaf,*metas,files)
        return dict(schema='wide-product-certificate-v1',qualified=numeric['qualified'],
                    workload_sha256=digest(w),leaf_workload=leaf,leaf_certificate=numeric,
                    reconstruction='exact-radix16-accumulation' if c['arithmetic']=='split-radix16' else 'direct-round-and-reduce')
    return dict(schema='wide-product-certificate-v1',qualified=True,workload_sha256=digest(w),
                basis=wide.basis(w),coefficient_bound=wide.bound(w),reconstruction='centered-crt-then-output-reduction')


def generate(w,c,ngen,sgen,directory,timeout,executables=None):
    wide.validate(w);directory=directory.resolve();directory.mkdir(parents=True,exist_ok=True)
    gen=c['generator'];root=ngen if gen=='ngen' else sgen
    executable=(executables or {}).get(gen,root/(gen+'.bat'));identity=verify(root,executable,gen)
    if not identity['verified']:raise ValueError('unverified generator assembly')
    started=time.monotonic();files=[];metas=[];processes=[];fields=wide.basis(w) if gen=='ngen' else []
    specifications=list(enumerate(fields)) if fields else [(0,None)]
    for index,field in specifications:
        for inverse in (False,True):
            direction='Inverse' if inverse else 'Forward'
            top=(f'Prime{index}' if gen=='ngen' else 'Product')+direction
            path=directory/(top+'.sv')
            if gen=='ngen':
                length=w['n']*(2 if w['ring']=='linear' else 1)
                args=['-n',str(length.bit_length()-1),'-k',str(c['lanes'].bit_length()-1),
                      '-r',str(c['radix'].bit_length()-1),'-q',str(field['q']),'-root',str(field['root']),
                      '-architecture',c['backend'],'-reduction',c['reduction'],'-profile',c['profile'],
                      '-protocol','ready-valid' if c['backend']=='streamed' and c.get('transpose','indexed')=='indexed' else 'next',
                      '-transpose',c.get('transpose','indexed'),'-top',top]
                if field['psi'] is not None:args+=['-psi',str(field['psi'])]
                if c['backend']=='streamed':args+=['-pe',str(c['pe']),'-stage-groups',str(c['stage_groups'])]
                terminal='intt' if inverse else 'ntt'
            else:
                args=['-nologo','-metadata','-strict-fixedpoint','-n',str((2*w['n']).bit_length()-1),
                      '-k',str(c['lanes'].bit_length()-1),'-r','1','-dualramcontrol','-hw','complex','fixedpoint',
                      str(c['integer_bits']),str(c['fractional_bits']),'-top',top]
                terminal=('idft' if inverse else 'dft')+('compact' if c['backend']=='compact' else '')
            process=run(['bash',str(executable),*args,'-o',str(path),terminal],root,directory/(top+'.log'),max(0,timeout-(time.monotonic()-started)))
            processes.append(process)
            if process['returncode']:return dict(returncode=process['returncode'],processes=processes),directory/'SearchTop.sv'
            meta=json.loads(path.with_suffix('.json').read_text())
            if gen=='ngen':
                meta['has_ready']=c['backend']=='stage-parallel' or c.get('transpose')=='switch';text=path.read_text()
                for name in sorted(re.findall(r'^module\s+(\w+)',text,re.M),key=len,reverse=True):
                    if name!=top:text=re.sub(r'\b'+re.escape(name)+r'\b',top+'_'+name,text)
                path.write_text(text)
            metas.append(meta);files.append(path)
    if verify(root,executable,gen)!=identity:raise ValueError('generator changed during generation')
    cert=certificate(w,c,metas,files);proofs=[];adapter_proofs=[]
    if gen=='sgen' and cert['qualified']:
        if not all('operation_contract' in m for m in metas):raise ValueError('version-2 FFT requires lowered operation contracts')
        proofs=[primitive_proofs.prove(m,p,directory/(p.stem+'-proofs')) for m,p in zip(metas,files)]
        scalar=c['integer_bits']+c['fractional_bits'];leaf=leaf_workload(w,c)
        adapter_proofs=[primitive_proofs.prove_pointwise(scalar,c['fractional_bits'],directory/'pointwise-proof'),
                        primitive_proofs.prove_rounding(w['n'],scalar,c['fractional_bits'],wide.bound(leaf).bit_length()+1,directory/'rounding-proof')]
    adapter=compose(w,c,metas,fields);rtl=directory/'SearchTop.sv'
    rtl.write_text('\n'.join(p.read_text() for p in files)+'\n'+adapter)
    declared=dict(schema='polynomial-product-design-v2',workload=w,configuration=c,cores=metas,
                  core_files={str(p):file_hash(p) for p in files},certificate=cert,primitive_proofs=proofs,
                  adapter_proofs=adapter_proofs,adapter_sha256=digest(adapter),rtl_sha256=file_hash(rtl),top='SearchTop')
    write_json(rtl.with_suffix('.json'),declared)
    return dict(returncode=0,processes=processes,generator_build=identity,numerically_qualified=cert['qualified'],
                assurance_passed=all(p['passed'] for p in proofs+adapter_proofs),seconds=time.monotonic()-started),rtl


def qualification_valid(w,declared,rtl):
    try:
        wide.validate(w);c=declared['configuration'];files=[Path(p) for p in declared['core_files']];metas=declared['cores']
        if declared['workload']!=w or declared['rtl_sha256']!=file_hash(rtl):return False
        if any(file_hash(p)!=declared['core_files'][str(p)] for p in files):return False
        expected=certificate(w,c,metas,files)
        if not expected['qualified'] or expected!=declared['certificate']:return False
        # JSON serialization sorts object keys; reconstruct explicit direction order.
        if c['generator']=='ngen':
            files=sorted(files,key=lambda p:(int(re.search(r'Prime(\d+)',p.stem).group(1)),'Inverse' in p.stem))
        else:files=sorted(files,key=lambda p:'Inverse' in p.stem)
        if c['generator']=='sgen':
            if len(declared['primitive_proofs'])!=2 or not all(primitive_proofs.valid(p,m,f)
                    for p,m,f in zip(declared['primitive_proofs'],metas,files)):return False
            scalar=c['integer_bits']+c['fractional_bits'];leaf=leaf_workload(w,c)
            emitted=[product_rtl.multiply_module(2*scalar,True,c['fractional_bits']),
                     product_rtl.fold_module(w['n'],scalar,c['fractional_bits'],wide.bound(leaf).bit_length()+1)]
            if len(declared['adapter_proofs'])!=2 or not all(primitive_proofs.adapter_valid(p,e)
                    for p,e in zip(declared['adapter_proofs'],emitted)):return False
        adapter=compose(w,c,metas,wide.basis(w) if c['generator']=='ngen' else [])
        return declared['adapter_sha256']==digest(adapter) and rtl.read_text()=='\n'.join(p.read_text() for p in files)+'\n'+adapter
    except (KeyError,ValueError,TypeError,OSError,IndexError):return False
