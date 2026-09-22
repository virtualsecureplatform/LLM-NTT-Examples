"""Generator invocation and complete-product composition; no shell interpolation."""
import json
import re
import time
from pathlib import Path
from . import products, numerics, product_rtl, primitive_proofs
from .build_identity import verify
from .model import run, file_hash, write_json, digest


def qualification_valid(w, declared, rtl):
    """Recheck the certificate and the complete generated artifact, including adapters."""
    if w.get('version')==2:
        from .wide_backend import qualification_valid as wide_valid
        return wide_valid(w,declared,rtl)
    try:
        if declared['workload']!=w or declared['rtl_sha256']!=file_hash(rtl):return False
        files=[Path(p) for p in declared['core_files']]
        if any(file_hash(p)!=declared['core_files'][str(p)] for p in files):return False
        if declared['configuration']['generator']=='sgen':
            by_name={p.stem:p for p in files}
            if 'operation_contract' in declared['forward']:
                proofs=declared['primitive_proofs']
                if len(proofs)!=2 or not all(primitive_proofs.valid(proof,meta,path) for proof,meta,path in
                        zip(proofs,[declared['forward'],declared['inverse']],
                            [by_name['ProductForward'],by_name['ProductInverse']])):return False
                c=declared['configuration'];scalar=c['integer_bits']+c['fractional_bits']
                expected=[product_rtl.multiply_module(2*scalar,True,c['fractional_bits']),
                          product_rtl.fold_module(w['n'],scalar,c['fractional_bits'],products.output_width(w))]
                if len(declared['adapter_proofs'])!=2 or not all(primitive_proofs.adapter_valid(p,e)
                        for p,e in zip(declared['adapter_proofs'],expected)):return False
            return declared['certificate']['qualified'] and numerics.certificate_valid(
                declared['certificate'],w,[declared['forward'],declared['inverse']],
                [by_name['ProductForward'],by_name['ProductInverse']])
        cert=declared['certificate']
        return cert=={'schema':'ntt-integer-range-v1','qualified':True,'field':products.field(w),
                      'coefficient_bound':w['n']*w['coefficient_bound']**2,'workload_sha256':digest(w)}
    except (KeyError,TypeError,ValueError,OSError):return False


def generate(w,c,ngen,sgen,directory,timeout,executables=None):
    if w.get('version')==2:
        from .wide_backend import generate as wide_generate
        return wide_generate(w,c,ngen,sgen,directory,timeout,executables)
    directory=directory.resolve(); directory.mkdir(parents=True,exist_ok=True)
    generator=c['generator']; root=ngen if generator=='ngen' else sgen
    executable=(executables or {}).get(generator,root/f'{generator}.bat')
    identity=verify(root,executable,generator)
    if not identity['verified']:raise ValueError(f'{generator} build verification failed: {identity}')
    started=time.monotonic(); processes=[]; metas=[]; files=[]; n=w['n']
    for inverse in (False,True):
        top='ProductInverse' if inverse else 'ProductForward'; path=directory/f'{top}.sv'
        if generator=='ngen':
            f=products.field(w)
            args=['-n',str(n.bit_length()-1),'-k',str(c['lanes'].bit_length()-1),'-r',str(c['radix'].bit_length()-1),
                  '-q',str(f['q']),'-root',str(f['root']),'-psi',str(f['psi']),
                  '-architecture',c['backend'],'-reduction',c['reduction'],'-profile',c['profile'],
                  '-protocol','ready-valid' if c['backend']=='streamed' else 'next','-top',top]
            if c['backend']=='streamed':args+=['-pe',str(c['pe']),'-stage-groups',str(c['stage_groups'])]
            terminal='intt' if inverse else 'ntt'
        else:
            args=['-nologo','-metadata','-strict-fixedpoint','-n',str((2*n).bit_length()-1),'-k',str(c['lanes'].bit_length()-1),
                  '-r','1','-dualramcontrol','-hw','complex','fixedpoint',str(c['integer_bits']),str(c['fractional_bits']),'-top',top]
            terminal=('idft' if inverse else 'dft')+('compact' if c['backend']=='compact' else '')
        process=run(['bash',str(executable),*args,'-o',str(path),terminal],root,directory/f'{top}.log',max(0,timeout-(time.monotonic()-started)))
        processes.append(process)
        if process['returncode']!=0:return {'returncode':process['returncode'],'processes':processes},directory/'SearchTop.sv'
        meta=json.loads(path.with_suffix('.json').read_text())
        if generator=='ngen':
            meta['has_ready']=c['backend']=='stage-parallel'
            # All helper identifiers are local to this direction. No duplicate
            # modules or accidental coupling between forward and inverse cores.
            text=path.read_text()
            names=re.findall(r'^module\s+(\w+)',text,re.M)
            for name in sorted(names,key=len,reverse=True):
                if name!=top:text=re.sub(r'\b'+re.escape(name)+r'\b',top+'_'+name,text)
            path.write_text(text)
        metas.append(meta);files.append(path)
    if verify(root,executable,generator)!=identity:raise ValueError('generator inputs changed during generation')
    certificate=numerics.certify(w,*metas,files) if generator=='sgen' else {
        'schema':'ntt-integer-range-v1','qualified':True,'field':products.field(w),
        'coefficient_bound':n*w['coefficient_bound']**2,'workload_sha256':digest(w)}
    proofs=[];adapter_proofs=[]
    if generator=='sgen' and certificate['qualified'] and 'operation_contract' in metas[0]:
        for meta,path in zip(metas,files):
            proofs.append(primitive_proofs.prove(meta,path,directory/(path.stem+'-proofs'),
                                                timeout=max(1,min(60,timeout-(time.monotonic()-started)))))
        scalar=c['integer_bits']+c['fractional_bits']
        adapter_proofs=[primitive_proofs.prove_pointwise(scalar,c['fractional_bits'],directory/'pointwise-proof'),
                        primitive_proofs.prove_rounding(n,scalar,c['fractional_bits'],products.output_width(w),directory/'rounding-proof')]
    adapter=product_rtl.compose(w,c,*metas)
    rtl=directory/'SearchTop.sv'
    rtl.write_text('\n'.join(p.read_text() for p in files)+'\n'+adapter)
    declared={'schema':'polynomial-product-design-v1','top':'SearchTop','workload':w,'configuration':c,
              'forward':metas[0],'inverse':metas[1],'certificate':certificate,
              'core_files':{str(p):file_hash(p) for p in files},'rtl_sha256':file_hash(rtl),
              'adapter_sha256':digest(adapter),'execution_boundary':'buffered-three-engine-product'}
    if proofs:declared.update(primitive_proofs=proofs,adapter_proofs=adapter_proofs)
    write_json(rtl.with_suffix('.json'),declared)
    return {'returncode':0,'processes':processes,'generator_build':identity,'numerically_qualified':certificate['qualified'],
            'assurance_passed':all(p['passed'] for p in proofs+adapter_proofs),
            'seconds':time.monotonic()-started},rtl
