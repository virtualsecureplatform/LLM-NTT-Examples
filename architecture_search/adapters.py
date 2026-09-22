"""Generator adapters. Configuration names describe real, bounded implementations."""
from __future__ import annotations
import importlib.util
import itertools
from pathlib import Path
from .model import run
from .build_identity import verify
from .permutation import compose,compose_linear
from .boundary import registered_ready_valid


def preset_tasks(ngen: Path) -> dict:
    spec = importlib.util.spec_from_file_location('ngen_benchmark_adapter', ngen/'scripts/ngen_llm_ntt.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TASKS


def candidates(workload: dict, ngen: Path, space: dict | None = None) -> list[dict]:
    if workload['kind']=='polynomial_product':
        from .products import candidates as product_candidates
        return product_candidates(workload,space)
    space = space or {}
    result = []
    if workload['kind'] == 'preset':
        tasks = preset_tasks(ngen)
        if workload['task'] not in tasks:
            raise ValueError('unsupported NGen preset task')
        for backend, profile, transpose in itertools.product(
                space.get('backends', ['microcoded', 'stage-parallel', 'full-throughput']),
                space.get('profiles', ['baseline', 'f300']), space.get('transposes', ['indexed', 'switch'])):
            task = workload['task']
            if backend not in ('microcoded', 'compact', 'stage-parallel', 'full-throughput') or profile not in ('baseline','f300') or transpose not in ('indexed','switch','distributed'):
                raise ValueError('unknown preset search option')
            if 'kyber' in task:
                if backend not in ('microcoded','compact') or transpose!='indexed':
                    continue
            if task == 'small_hoge32_p64':
                if backend!='microcoded' or transpose!='indexed':
                    continue
            if transpose == 'distributed' and task != 'hoge_streaming_ntt_1024_p64':
                continue
            if backend == 'full-throughput':
                required = 'switch' if task.startswith('hoge_streaming') else 'indexed'
                if transpose != required:
                    continue
            if backend == 'stage-parallel' and task.startswith('hoge_streaming') and transpose != 'indexed':
                continue  # This combination selects another backend in NGen.
            configuration=dict(generator='ngen',backend=backend,profile=profile,transpose=transpose)
            if 'kyber' in task and backend=='compact':configuration.update(storage='banked-pointer-swap',host_schedule='serialized-load-compute-read')
            result.append(configuration)
    elif workload['kind'] == 'generic':
        n, lanes = int(workload['n']), int(workload.get('lanes', 4))
        if lanes < 1 or lanes & (lanes - 1) or n % lanes:
            raise ValueError('lanes must be a power of two dividing N')
        for backend in space.get('backends',['streamed']):
            if backend not in ('streamed','stage-parallel','fully-parallel'):raise ValueError('unsupported generic backend')
        for pe, radix, reduction, groups, profile in itertools.product(space.get('pe', [1,2,4,8]),
                space.get('radix', [2,4,8]), space.get('reductions', ['barrett','montgomery','shoup']), space.get('stage_groups',[1]),space.get('profiles',['baseline'])):
            if not isinstance(pe, int) or pe < 1 or radix not in (2,4,8) or reduction not in ('barrett','montgomery','shoup','auto') or profile not in ('baseline','f300'):
                raise ValueError('invalid generic search option')
            if not isinstance(groups,int) or not 1 <= groups <= n.bit_length()-1:
                raise ValueError('invalid stage group count')
            if groups>1 and radix!=2:
                continue
            if (n.bit_length()-1) % (radix.bit_length()-1) or pe > n // radix:
                continue
            if 'streamed' not in space.get('backends',['streamed']):continue
            result.append(dict(generator='ngen', backend='streamed', profile=profile, transpose='indexed',
                               lanes=lanes, pe=pe, radix=radix, reduction=reduction, stage_groups=groups, boundary='registered-ready-valid'))
        for backend in space.get('backends',['streamed']):
            if backend=='streamed':continue
            reductions=['barrett'] if backend=='fully-parallel' else space.get('reductions',['barrett','montgomery','shoup'])
            for profile,reduction in itertools.product(space.get('profiles',['baseline']),reductions):
                if profile not in ('baseline','f300') or reduction not in ('barrett','montgomery','shoup','auto'):raise ValueError('invalid generic option')
                result.append(dict(generator='ngen',backend=backend,profile=profile,transpose='indexed',lanes=lanes,
                    core_lanes=n if backend=='fully-parallel' else lanes,radix=2,reduction=reduction,stage_groups=1,boundary='frame-buffered-ready-valid'))
    else:
        raise ValueError('workload kind must be preset or generic')
    permutations=space.get('permutations',['ngen'])
    if any(p not in ('ngen','sgen','sgen-linear') for p in permutations):
        raise ValueError('unknown permutation generator')
    result=[{**c,'generator':{'ngen':'ngen','sgen':'ngen-sgen','sgen-linear':'ngen-sgen-linear'}[p]} for c in result for p in permutations
            if p=='ngen' or (workload['kind']=='preset' and c['transpose']=='switch' and (p!='sgen-linear' or workload['task']=='small_yata8x8_raintt_p27'))]
    if not result:
        raise ValueError('no legal configurations in the requested search space')
    return result


def generate(workload: dict, config: dict, ngen: Path, directory: Path, timeout: float, executable: Path | None = None, sgen_executable: Path | None = None) -> tuple[dict, Path]:
    build=verify(ngen,executable)
    if not build['verified']:raise ValueError('NGen build verification failed; run sbt assembly: '+str(build))
    directory=directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if workload['kind'] == 'preset':
        base, filename = preset_tasks(ngen)[workload['task']]
        args = base[:-1] + ['-preset-backend', config['backend']]
        terminal = base[-1]
    else:
        filename = 'SearchTop.sv'
        args = ['-n', str(int(workload['n']).bit_length()-1), '-q', str(workload['q']),
                '-root', str(workload['root']), '-k', str(config.get('core_lanes',config['lanes']).bit_length()-1),
                '-r', str(config['radix'].bit_length()-1),
                '-architecture', config['backend'], '-reduction', config['reduction'],
                '-protocol', 'ready-valid' if config['backend']=='streamed' else 'next',
                '-top', 'SearchTop' if config['backend']=='streamed' else 'GenericCore']
        if config['backend']=='streamed':args+=['-pe',str(config['pe']),'-stage-groups',str(config.get('stage_groups',1))]
        if workload.get('negacyclic'):
            args += ['-psi', str(workload['psi'])]
        terminal = 'intt' if workload.get('direction') == 'inverse' else 'ntt'
    rtl = directory / filename
    args += ['-profile', config['profile'], '-transpose', config['transpose'], '-o', str(rtl), terminal]
    process=run(['bash', str(executable or ngen/'ngen.bat'), *args], ngen, directory/'generation.log', timeout)
    if verify(ngen,executable)!=build:raise ValueError('NGen build inputs or executable changed during generation')
    process['ngen_build']=build
    if process['returncode']==0 and workload['kind']=='generic':
        if config['backend']=='streamed':
            rtl.write_text(registered_ready_valid(rtl.read_text(),config['lanes'],int(workload['q']).bit_length()))
        else:
            import json
            from .product_rtl import frame_engine
            meta=json.loads(rtl.with_suffix('.json').read_text());meta['has_ready']=config['backend']=='stage-parallel'
            lanes=config['lanes'];width=int(workload['q']).bit_length()
            engine=frame_engine('GenericFrame','GenericCore',meta,width,external_lanes=lanes)
            ports=','.join(f'input [{width-1}:0] i{j},output [{width-1}:0] o{j}' for j in range(lanes))
            inputs=','.join(f'i{j}' for j in reversed(range(lanes)));outputs=','.join(f'o{j}' for j in reversed(range(lanes)))
            wrapper=f'module SearchTop(input clock,reset,in_valid,output in_ready,out_valid,input out_ready,{ports}); GenericFrame frame(clock,reset,in_valid,in_ready,{{{inputs}}},out_valid,out_ready,{{{outputs}}}); endmodule'
            rtl.write_text(rtl.read_text()+'\n'+engine+'\n'+wrapper)
        process['boundary']={'kind':config.get('boundary','registered-ready-valid'),'included_in_measurements':True}
    if process['returncode']==0 and config['generator'] in ('ngen-sgen','ngen-sgen-linear'):
        if sgen_executable is None:raise ValueError('SGen executable required')
        component=(compose_linear if config['generator']=='ngen-sgen-linear' else compose)(rtl,sgen_executable,directory,timeout-process['seconds'])
        process={**process,'sgen':component,'returncode':component['returncode']}
    return process,rtl
