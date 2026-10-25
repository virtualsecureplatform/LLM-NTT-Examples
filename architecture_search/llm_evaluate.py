"""Sealed stage cache and matching-context imports for live and replay DSE."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

from . import build_identity, device, device_evaluate, timing_harness, wide_backend
from .model import artifact_manifest, digest, evidence_integrity, file_hash, write_json
from .paths import ROOT, NGEN
from scripts.device_polynomial_study import inventory
from scripts.extend_timing_frontier import endpoint_counts
from scripts.find_timing_met import verify_clock
from scripts.polynomial_study import corpus, reusable


def require_target(target):
    if target['clock_mhz'] != 250 or target.get('implementation_context') != timing_harness.CONTEXT \
            or target['implementation_directive'] != 'Default':
        raise ValueError('DSE demo requires the Default 250 MHz registered-harness-v2 target')


def live_process(folder):
    needles = {str(folder/'run.tcl').encode(), str(folder/'request.json').encode()}
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = set(path.read_bytes().split(b'\0'))
        except OSError:
            continue
        if needles & args:
            return True
    return False


def strict_route(row, evidence, clock_file, target):
    if not device.feasible(row, evidence, target, 0):
        return False
    counts = endpoint_counts((Path(evidence['checkpoint']).parent/'timing.rpt').read_text())
    if counts is None or any(counts.values()) or clock_file is None:
        return False
    proof = json.loads(Path(clock_file).read_text())
    return bool(proof.get('passed') and evidence_integrity(proof) == 'verified'
                and proof.get('checkpoint_sha256') == file_hash(Path(evidence['checkpoint'])))


class EvaluationStore:
    def __init__(self, rows, target, cache, mode='replay',
                 reference=ROOT/'build/device-pareto250-512', timeout=3600, threads=4,
                 vivado=Path('/home/opt/xilinx/Vivado/2023.2/bin/vivado')):
        require_target(target)
        self.rows = {r['name']: r for r in rows}
        self.target, self.mode, self.timeout, self.threads = target, mode, timeout, threads
        self.vivado = Path(vivado)
        self.reference = Path(reference).resolve()
        self.reference_state = json.loads((self.reference/'results.json').read_text())
        self.reference_manifest = json.loads((self.reference/'manifest.json').read_text())
        if self.reference_state['status'] != 'complete' or self.reference_state.get('active'):
            raise ValueError('reference must be a completed campaign')
        if self.reference_manifest['target'] != target:
            raise ValueError('reference implementation context differs')
        sources = self.reference_manifest['sources']
        for source in sources:
            p = Path(source['results'])
            if file_hash(p) != source['results_sha256'] or file_hash(p.parent/'manifest.json') != source['manifest_sha256']:
                raise ValueError('reference qualification inventory changed')
        self.qualified, _ = inventory([Path(s['results']).parent for s in sources])
        self.qualified = {r['name']: r for r in self.qualified if r['name'] in self.rows}
        self.checked_imports = set()
        self.tool = self.reference_manifest['tool']
        self.image = ROOT/'build/fhe512-sgen-precision.sif'
        generator = build_identity.verify(NGEN)
        if not generator['verified']:
            raise ValueError('generator build is stale')
        hardware_sources = [ROOT/'scripts/run_llm_qualification.sh', ROOT/'scripts/llm_polynomial_study.py',
            ROOT/'scripts/polynomial_study.py', ROOT/'scripts/fhe512_preroute.py',
            ROOT/'scripts/fhe512_sgen_precision.py', ROOT/'scripts/verilator_pinned.sh',
            *[p for p in (ROOT/'architecture_search').glob('*.py') if not p.name.startswith('llm_')]]
        context = dict(target=target, generator=generator, tool=self.tool,
                       image_sha256=file_hash(self.image), threads=threads, timeout=timeout,
                       evaluator_sha256=file_hash(Path(__file__)),
                       hardware_sources={str(p.relative_to(ROOT)): file_hash(p) for p in hardware_sources})
        self.identity = dict(mode=mode, context=context, reference_sha256=file_hash(self.reference/'results.json'),
                             reference_manifest_sha256=file_hash(self.reference/'manifest.json'))
        self.root = Path(cache).resolve()/digest(context)
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self.root/'context.json', context)
        if mode == 'live':
            actual = device_evaluate.tool_identity(self.vivado, self.root)
            if actual != self.tool:
                raise ValueError('live Vivado identity differs from reference')
        elif mode != 'replay':
            raise ValueError('unknown evaluator mode')

    def available(self):
        if self.mode == 'replay':
            return set(self.reference_state['routed']) & set(self.rows)
        return set(self.rows)

    def _verify_qualification(self, name):
        row = self.qualified[name]
        if name not in self.checked_imports:
            if not reusable(row, Path(row['evidence_root']), self.rows[name]):
                raise ValueError('qualification evidence changed')
            if row.get('max_abs_error') != 0 or row.get('corpus_sha256') != digest(corpus(row['workload'])):
                raise ValueError('qualification workload or corpus differs')
            source = json.loads((Path(row['evidence_root'])/'manifest.json').read_text())
            if source['generators']['ngen'] != self.identity['context']['generator'] \
                    or source.get('image_sha256') != self.identity['context']['image_sha256']:
                raise ValueError('qualification build or image differs')
            # The historical inventory predates opt-in registered adapters. Verify
            # its actual composition against today's generator rather than accepting
            # changed arithmetic merely because an old source manifest was sealed.
            generated = Path(row['evidence_root'])/name/'generated'/'SearchTop.sv'
            declared = json.loads(generated.with_suffix('.json').read_text())
            if declared['configuration'] != row['configuration'] or file_hash(generated) != row['rtl_sha256'] \
                    or not wide_backend.qualification_valid(row['workload'], declared, generated, 0):
                raise ValueError('historical RTL does not match current qualified composition')
            protected = ('architecture_search/product_evaluate.py', 'architecture_search/product_simulation.py',
                         'architecture_search/model.py', 'architecture_search/evaluate.py')
            if any(source['sources'].get(p) != file_hash(ROOT/p) for p in protected):
                raise ValueError('qualification verifier sources differ')
            if set(row.get('simulation', {})) != {'correctness', 'timing', 'protocol', 'swapped'} \
                    or not all(v.get('correct') for v in row['simulation'].values()):
                raise ValueError('incomplete historical functional qualification')
            self.checked_imports.add(name)
        return row

    def _import(self, name, stage):
        if name not in self.qualified:
            return None
        row = self._verify_qualification(name)
        if stage == 'qualified':
            return dict(stage=stage, passed=True, row=row, cache_hit=True,
                        physical_seconds=0, hardware_seconds=0, source='reference-qualification')
        evidence = self.reference_state.get(stage, {}).get(name)
        if evidence is None:
            return None
        if evidence.get('target') != self.target or evidence.get('tool') != self.tool \
                or evidence.get('rtl_sha256') != row['rtl_sha256'] or evidence_integrity(evidence) != 'verified':
            raise ValueError('imported physical evidence changed or has incompatible context')
        expected_harness = hashlib.sha256(timing_harness.emit(
            row['workload'], self.target['implementation_context']).encode()).hexdigest()
        if evidence.get('harness_sha256') != expected_harness:
            raise ValueError('imported physical harness differs from current generated harness')
        result = dict(stage=stage, passed=evidence['passed'], metrics=evidence['metrics'], evidence=evidence,
                      reason=evidence.get('reason', ''), cache_hit=True, physical_seconds=0,
                      hardware_seconds=evidence.get('process', {}).get('seconds', 0), source='reference')
        if stage == 'routed':
            clock_file = self.reference_state.get('clock_checks', {}).get(name)
            result.update(clock_evidence=clock_file,
                          feasible=strict_route(row, evidence, clock_file, self.target))
        return result

    def seed(self, name):
        result = {stage: self._import(name, stage) for stage in ('qualified', 'mapped', 'routed')}
        if any(v is None or not v['passed'] for v in result.values()) or not result['routed']['feasible']:
            raise ValueError('common seed is not fully timing-qualified')
        return result

    def validate_observations(self, observations):
        for name, stages in observations.items():
            if name not in self.rows:
                raise ValueError('observed candidate is outside the catalog')
            q = stages.get('qualified', {})
            if q.get('passed') and not reusable(q['row'], Path(q['row']['evidence_root']), self.rows[name]):
                raise ValueError('observed qualification changed')
            for stage in ('mapped', 'routed'):
                r = stages.get(stage, {})
                e = r.get('evidence')
                if e is not None:
                    if e.get('target') != self.target or e.get('tool') != self.tool \
                            or e.get('rtl_sha256') != q['row']['rtl_sha256'] or evidence_integrity(e) != 'verified':
                        raise ValueError('observed physical evidence changed')
                    if stage == 'routed' and r.get('feasible') != strict_route(
                            q['row'], e, r.get('clock_evidence'), self.target):
                        raise ValueError('observed route qualification differs')

    def _load(self, name, stage, owner):
        path = self.root/name/stage/'result.json'
        if not path.exists():
            return None
        record = json.loads(path.read_text())
        if record.get('identity') != self.identity['context'] or record.get('candidate') != self.rows[name] \
                or evidence_integrity(record) != 'verified':
            raise ValueError('stage cache identity or artifacts changed')
        result = copy.deepcopy(record['result'])
        result['cache_hit'] = record['owner'] != owner
        result['physical_seconds'] = 0 if result['cache_hit'] else result['hardware_seconds']
        return result

    def _seal(self, name, stage, owner, result):
        folder = self.root/name/stage
        files = [p for p in folder.rglob('*') if p.is_file() and p.name != 'result.json'
                 and not p.name.endswith('.tmp') and p.name != '.lock']
        record = dict(identity=self.identity['context'], candidate=self.rows[name], owner=owner, result=result)
        record['integrity'] = dict(version=1, inputs_unchanged=True, inputs=artifact_manifest([]),
            outputs=artifact_manifest(files), measurement=copy.deepcopy(record))
        write_json(folder/'result.json', record)
        return result

    def recover(self, name, stage, observations, owner):
        folder = self.root/name/stage
        with self._lock():
            result = self._load(name, stage, owner)
            if result is not None:
                return result
            # Imported stages create no worker and can safely be adopted again.
            result = self._import(name, stage)
            if result is not None:
                return result
            if live_process(folder):
                raise ValueError('interrupted trial still has a live worker; wait before resuming')
            folder.mkdir(parents=True, exist_ok=True)
            return self._seal(name, stage, owner, dict(stage=stage, passed=False, feasible=False,
                reason='interrupted-unsealed', cache_hit=False, physical_seconds=0, hardware_seconds=0))

    def _lock(self):
        class Lock:
            def __enter__(inner):
                inner.stream = (self.root/'.lock').open('w')
                fcntl.flock(inner.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def __exit__(inner, *unused):
                inner.stream.close()
        return Lock()

    def evaluate(self, name, stage, observations, owner):
        if name not in self.rows or stage not in ('qualified', 'mapped', 'routed'):
            raise ValueError('invalid candidate or stage')
        with self._lock():
            result = self._load(name, stage, owner)
            if result is not None:
                return result
            result = self._import(name, stage)
            if result is not None:
                return result
            if self.mode == 'replay':
                raise ValueError('replay stage is absent from the closed reference fixture')
            folder = self.root/name/stage
            folder.mkdir(parents=True, exist_ok=True)
            if (folder/'started.json').exists():
                if live_process(folder):
                    raise ValueError('unsealed trial still has a live worker')
                return self._seal(name, stage, owner, dict(stage=stage, passed=False, feasible=False,
                    reason='interrupted-unsealed', cache_hit=False, physical_seconds=0, hardware_seconds=0))
            write_json(folder/'started.json', dict(owner=owner, started_at=time.time()))
            began = time.monotonic()
            result = dict(stage=stage, passed=False, feasible=False, cache_hit=False)
            try:
                if stage == 'qualified':
                    request = folder/'request.json'
                    write_json(request, dict(row=self.rows[name], output_dir=str(folder/'qualification'), timeout=self.timeout))
                    env = dict(os.environ)
                    env.pop('LLM_DSE_API_KEY', None)
                    # The pinned wrapper installs the simulator/Yosys path and image identity.
                    import subprocess
                    command = ['bash', str(ROOT/'scripts/run_llm_qualification.sh'), str(request)]
                    log = folder/'worker.log'
                    with log.open('w') as stream:
                        worker = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                                  stderr=subprocess.STDOUT, start_new_session=True)
                        try:
                            code = worker.wait(timeout=self.timeout)
                        except subprocess.TimeoutExpired:
                            import signal
                            os.killpg(worker.pid, signal.SIGTERM)
                            try:
                                worker.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                os.killpg(worker.pid, signal.SIGKILL)
                                worker.wait()
                            code = 124
                    row_file = folder/'qualification'/'row.json'
                    if code == 0 and row_file.is_file():
                        row = json.loads(row_file.read_text())
                        result.update(passed=bool(row.get('passed')), row=row, reason=row.get('reason', ''))
                    else:
                        result['reason'] = 'qualification-timeout' if code == 124 else 'qualification-worker-failed'
                else:
                    row = observations['qualified']['row']
                    mapped = observations.get('mapped', {}).get('evidence')
                    evidence = device_evaluate.evaluate(row, row['rtl_path'], self.target, self.tool,
                        self.vivado, folder, stage, mapped, self.timeout, self.threads)
                    result.update(passed=evidence['passed'], evidence=evidence, metrics=evidence['metrics'],
                                  reason=evidence.get('reason', ''))
                    if stage == 'routed':
                        clock = None
                        # Run the read-only clock probe only after the other signoff predicates pass.
                        if device.feasible(row, evidence, self.target, 0):
                            counts = endpoint_counts((folder/'timing.rpt').read_text())
                            if counts is not None and not any(counts.values()):
                                verify_clock(evidence['checkpoint'], self.vivado, folder/'clock-check')
                                clock = str(folder/'clock-check'/'evidence.json')
                        result.update(clock_evidence=clock, feasible=strict_route(row, evidence, clock, self.target))
            except (OSError, ValueError, KeyError, TypeError) as error:
                result['reason'] = type(error).__name__+': '+str(error)
            elapsed = time.monotonic()-began
            result.update(physical_seconds=elapsed, hardware_seconds=elapsed)
            return self._seal(name, stage, owner, result)
