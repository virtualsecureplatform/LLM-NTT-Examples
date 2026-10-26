"""Portable replay of published measurements, independent of hardware artifacts."""
import copy
import hashlib
import json
from pathlib import Path

from . import device, llm_dse
from .model import file_hash, metric_number

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT/'data/dse/torus512-replay.json'
SCOPE = 'published-measurement-replay; no local RTL or checkpoint signoff'
STAGES = ('qualified', 'mapped', 'routed')


class PortableReplayStore:
    def __init__(self, path, rows, target):
        path = Path(path)
        payload = path.read_bytes()
        sha = hashlib.sha256(payload).hexdigest()
        expected = path.with_suffix('.sha256').read_text().strip().split()[0]
        if sha != expected:
            raise ValueError('replay dataset checksum differs; restore the dataset and its .sha256 file')
        data = json.loads(payload)
        if data.get('schema') != 'polynomial-dse-replay-v1' or data['target'] != target:
            raise ValueError('replay dataset schema or target differs from this experiment')
        legal = {r['name']: r for r in llm_dse.catalog(data['study'])}
        self.records = {}
        for record in data['records']:
            candidate, stages = record['candidate'], record['stages']
            name = candidate['name']
            if name in self.records or legal.get(name) != candidate or set(stages) != set(STAGES):
                raise ValueError('replay contains a duplicate, illegal, or incomplete candidate')
            row = stages['qualified']['row']
            if any(row.get(k) != candidate[k] for k in ('name', 'configuration', 'workload', 'quant_bits')):
                raise ValueError('replay qualification contract differs')
            for k in ('latency_cycles', 'initiation_interval_cycles', 'yosys_cells',
                      'register_bits', 'memory_bits', 'multipliers'):
                if not metric_number(row.get(k)) or row[k] <= 0:
                    raise ValueError('missing positive replay qualification metric: '+k)
            if row.get('passed') is not True or row.get('max_abs_error') != 0 \
                    or stages['qualified'].get('passed') is not True:
                raise ValueError('replay requires exact qualified products')
            for stage in STAGES:
                result = stages[stage]
                if result.get('stage') != stage or type(result.get('passed')) is not bool \
                        or result.get('evidence_scope') != SCOPE or result.get('cache_hit') is not True \
                        or result.get('physical_seconds') != 0:
                    raise ValueError('invalid replay stage or evidence scope')
                if not metric_number(result.get('hardware_seconds')) or result['hardware_seconds'] < 0:
                    raise ValueError('invalid historical hardware duration')
                if stage == 'qualified':
                    continue
                metrics = result.get('metrics', {})
                for k in (*device.RESOURCES, 'setup_slack_ns', 'hold_slack_ns', 'pulse_slack_ns'):
                    if not metric_number(metrics.get(k)):
                        raise ValueError('missing finite replay metric: '+k)
                if any(metrics[k] < 0 for k in device.RESOURCES):
                    raise ValueError('replay resource counts must be nonnegative')
            route = stages['routed']
            signoff = route.get('reported_signoff', {})
            eligible = bool(route['passed'] and stages['mapped']['passed'] and stages['qualified']['passed']
                and device.resources_fit(route['metrics'], target)
                and route['metrics'].get('fully_constrained') is True
                and all(route['metrics'][k] >= 0 for k in ('setup_slack_ns', 'hold_slack_ns', 'pulse_slack_ns'))
                and signoff.get('failing_endpoints') == dict(Setup=0, Hold=0, PW=0)
                and signoff.get('clock_verified') is True)
            if type(route.get('feasible')) is not bool or route['feasible'] != eligible:
                raise ValueError('reported replay feasibility is inconsistent with measurements')
            self.records[name] = record
        requested = {r['name']: r for r in rows}
        self.rows = [r for r in rows if r['name'] in self.records]
        for r in self.rows:
            if self.records[r['name']]['candidate'] != requested[r['name']]:
                raise ValueError('experiment workload/configuration differs from replay data')
        self.target = target
        self.identity = dict(kind='portable-replay-v1', dataset_sha256=sha, evidence_scope=SCOPE,
                             reader_sha256=file_hash(Path(__file__)))
        self.provenance = data['provenance']
        if not self.rows:
            raise ValueError('no experiment configurations occur in the replay dataset')
        self.seed(llm_dse.seed_name(self.rows))

    def seed(self, name):
        stages = self.records[name]['stages']
        if not stages['routed']['feasible']:
            raise ValueError('replay seed must have reported timing-feasible measurements')
        return copy.deepcopy(stages)

    def evaluate(self, name, stage, observations, owner):
        if name not in {r['name'] for r in self.rows} or stage not in STAGES:
            raise ValueError('candidate or stage is outside the closed replay catalog')
        return copy.deepcopy(self.records[name]['stages'][stage])

    def recover(self, name, stage, observations, owner):
        return self.evaluate(name, stage, observations, owner)

    def validate_observations(self, observations):
        allowed = {r['name'] for r in self.rows}
        for name, stages in observations.items():
            if name not in allowed or set(stages)-set(STAGES):
                raise ValueError('observed replay candidate/stage is outside the catalog')
            for stage, result in stages.items():
                if result != self.records[name]['stages'][stage]:
                    raise ValueError('observed replay measurement differs from the checksummed dataset')


def failure_reason(result, stage, target):
    """Translate native process success versus timing qualification into a useful reason."""
    if not result.get('passed'):
        return result.get('reason') or stage+' evaluation failed'
    if stage != 'routed' or result.get('feasible'):
        return ''
    metrics = result.get('metrics', {})
    for label, key in (('setup', 'setup_slack_ns'), ('hold', 'hold_slack_ns'), ('pulse width', 'pulse_slack_ns')):
        if metric_number(metrics.get(key)) and metrics[key] < 0:
            return f'{label} timing failed ({metrics[key]:g} ns slack)'
    if not device.resources_fit(metrics, target):
        return 'device resource budget exceeded'
    if metrics.get('fully_constrained') is not True:
        return 'timing is not fully constrained'
    return result.get('reason') or 'clock or failing-endpoint signoff failed; inspect stage evidence'


class ExplainedStore:
    """Keep native sealed evidence intact while explaining acquired stage failures."""
    def __init__(self, store, target):
        self.store, self.target = store, target
        self.identity = dict(store.identity, explanation_sha256=file_hash(Path(__file__)))

    def seed(self, name):
        return self.store.seed(name)

    def validate_observations(self, observations):
        self.store.validate_observations(observations)

    def _stage(self, method, name, stage, observations, owner):
        result = getattr(self.store, method)(name, stage, observations, owner)
        reason = failure_reason(result, stage, self.target)
        if reason:
            result = dict(result, reason=reason)
        return result

    def evaluate(self, name, stage, observations, owner):
        return self._stage('evaluate', name, stage, observations, owner)

    def recover(self, name, stage, observations, owner):
        return self._stage('recover', name, stage, observations, owner)
