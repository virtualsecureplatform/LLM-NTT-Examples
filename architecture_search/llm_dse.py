"""Budgeted acquisition with a deliberately restricted view of measured evidence."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from . import device, product_search, wide_products
from .model import digest, write_json

BASE_URL = 'http://10.0.60.37:8080/v1'
MODEL = 'qwen3.8-flash-next-unsloth-ud-q4_k_xl'


def catalog(spec):
    from scripts.polynomial_study import point
    if spec.get('schema') != 'llm-polynomial-study-v1':
        raise ValueError('expected llm-polynomial-study-v1')
    if set(spec) != {'schema', 'n', 'a_range', 'b_range', 'space'}:
        raise ValueError('unexpected demo study fields')
    w = wide_products.workload(spec['n'], modulus=1 << 32)
    w.update(a_range=spec['a_range'], b_range=spec['b_range'])
    if w['n'] != 512 or w['a_range'] != [-2147483648, 2147483647] or w['b_range'] != [-1, 1]:
        raise ValueError('v1 supports only exact N512 full32 x ternary')
    rows = [point('full-ternary', w, c, 'architecture')
            for c in wide_products.candidates(w, spec['space'])]
    if not rows or any(r['configuration']['generator'] != 'ngen' for r in rows):
        raise ValueError('v1 requires an NGen-only catalog')
    return sorted(rows, key=lambda r: r['name'])


def seed_name(rows):
    matches = [r['name'] for r in rows if all(r['configuration'].get(k) == v for k, v in
               dict(product_profile='pipelined', reduction='montgomery', lanes=2, pe=1,
                    backend='streamed', radix=2, stage_groups=1).items())]
    if len(matches) != 1:
        raise ValueError('catalog must contain exactly one common seed')
    return matches[0]


def feasible_points(state, target):
    points = []
    for name, stages in state['observations'].items():
        route = stages.get('routed', {})
        if not route.get('feasible'):
            continue
        row = stages['qualified']['row']
        points.append(dict(name=name, error_bound=row['max_abs_error'],
                           latency_cycles=row['latency_cycles'],
                           **route['metrics'], **device.performance(row, target)))
    return points


def frontier(points):
    return [p['name'] for p in points if not any(
        q['lut'] <= p['lut'] and q['modeled_products_per_second'] >= p['modeled_products_per_second']
        and (q['lut'] < p['lut'] or q['modeled_products_per_second'] > p['modeled_products_per_second'])
        for q in points)]


def hypervolume(points, lut_limit, seed_rate):
    """Area left of a fixed LUT limit and above zero throughput, seed-normalized."""
    names = set(frontier(points))
    previous_rate = area = 0.0
    for p in sorted((p for p in points if p['name'] in names), key=lambda p: p['lut']):
        rate = p['modeled_products_per_second']
        if p['lut'] < lut_limit and rate > previous_rate:
            area += (lut_limit - p['lut']) * (rate - previous_rate)
            previous_rate = rate
    return area / (lut_limit * seed_rate)


def progress(state, target):
    points = feasible_points(state, target)
    seed = state['observations'][state['seed_name']]['qualified']['row']
    rate = device.performance(seed, target)['modeled_products_per_second']
    return dict(candidates=len(state['selected']), **state['attempts'], feasible=len(points),
                frontier=frontier(points), best_products_per_second=max(
                    (p['modeled_products_per_second'] for p in points), default=0),
                hypervolume=hypervolume(points, device.limits(target)['lut'], rate))


def public_context(rows, state, target, max_candidates, route_budget):
    """No oracle, unselected qualification records, paths, or cached results enter here."""
    observed = []
    for name, stages in sorted(state['observations'].items()):
        item = dict(candidate_id=name, stages={})
        for stage, result in stages.items():
            visible = {k: result[k] for k in ('passed', 'reason', 'metrics', 'feasible') if k in result}
            if stage == 'qualified' and result.get('passed'):
                row = result['row']
                visible.update({k: row[k] for k in ('max_abs_error', 'latency_cycles',
                    'initiation_interval_cycles', 'yosys_cells', 'register_bits', 'memory_bits', 'multipliers')})
                visible.update(device.performance(row, target))
            item['stages'][stage] = visible
        observed.append(item)
    used = set(state['selected']) | {state['seed_name']}
    return dict(goal='Improve LUT versus modeled products/s at exact correctness and routed 250 MHz timing. '
                'The common seed is prior evidence. Estimates and mapped timing are not routed qualification.',
                target={k: target[k] for k in ('part', 'clock_mhz', 'implementation_context')},
                resource_limits=device.limits(target),
                remaining_candidates=max_candidates-len(state['selected']),
                remaining_routes=route_budget-state['attempts']['routed'],
                candidates=[dict(candidate_id=r['name'], configuration=r['configuration']) for r in rows],
                eligible_ids=[r['name'] for r in rows if r['name'] not in used],
                observations=observed, achieved_frontier=frontier(feasible_points(state, target)),
                routing_policy='After every two candidate attempts, promote one mapped resource-fitting design; '
                'alternate maximum modeled throughput and minimum mapped LUT, with the other metric then ID as tiebreakers.')


class LLMError(ValueError):
    pass


class LLMAuthenticationError(LLMError):
    pass


class LLMClient:
    def __init__(self, base_url=BASE_URL, model=MODEL, timeout=120):
        self.key = os.environ.get('LLM_DSE_API_KEY', '')
        if not self.key:
            raise LLMError('LLM_DSE_API_KEY is required for the LLM policy')
        if not base_url.startswith(('http://', 'https://')) or not model or timeout <= 0:
            raise LLMError('invalid endpoint, model, or timeout')
        self.base_url, self.model, self.timeout = base_url.rstrip('/'), model, timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def redact(self, value):
        if isinstance(value, str):
            return value.replace(self.key, '[REDACTED]')
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, dict):
            return {k: self.redact(v) for k, v in value.items()}
        return value

    def select(self, context, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        messages = [dict(role='system', content='You select polynomial multiplication hardware configurations. '
                    'Use only disclosed measurements. Return one JSON object containing exactly candidate_id '
                    '(an eligible ID) and rationale (a short string). Never emit RTL or commands.'),
                    dict(role='user', content=json.dumps(context, sort_keys=True))]
        # Persist each call separately so resume does not reset the three-request bound.
        existing = sorted(directory.glob('call-*.json'))
        for path in existing:
            old = json.loads(path.read_text())
            if old.get('accepted'):
                return old['proposal']
            if old.get('fatal'):
                raise LLMAuthenticationError('previous endpoint authentication failure')
        for attempt in range(len(existing), 3):
            body = dict(model=self.model, messages=messages, temperature=0, max_tokens=1024,
                        stream=False, response_format={'type': 'json_object'})
            record = dict(request=self.redact(body), started_at=time.time(), accepted=False)
            path = directory / f'call-{attempt+1}.json'
            write_json(path, record)  # A request lost to interruption is still charged.
            began = time.monotonic()
            try:
                request = urllib.request.Request(self.base_url+'/chat/completions',
                    data=json.dumps(body).encode(), headers={'Authorization': 'Bearer '+self.key,
                                                           'Content-Type': 'application/json'})
                with self.opener.open(request, timeout=self.timeout) as response:
                    result = json.load(response)
                record['response'] = self.redact(result)
                message = result['choices'][0]['message']['content']
                proposal = json.loads(message)
                if not isinstance(proposal, dict) or set(proposal) != {'candidate_id', 'rationale'}:
                    raise ValueError('expected exactly candidate_id and rationale')
                if proposal['candidate_id'] not in context['eligible_ids']:
                    raise ValueError('candidate_id is unknown or already selected')
                if not isinstance(proposal['rationale'], str) or not 1 <= len(proposal['rationale']) <= 2000:
                    raise ValueError('rationale must be a short nonempty string')
                record.update(accepted=True, proposal=self.redact(proposal))
            except urllib.error.HTTPError as error:
                record['error'] = f'HTTP {error.code}'
                record['fatal'] = error.code in (401, 403)
            except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
                # Avoid persisting server-controlled error text or exception URLs.
                record['error'] = type(error).__name__
            record['seconds'] = time.monotonic()-began
            write_json(path, record)
            if record.get('fatal'):
                raise LLMAuthenticationError('endpoint authentication failed; no hardware evaluation started')
            if record['accepted']:
                return record['proposal']
            messages.append(dict(role='user', content='The previous request failed or returned an invalid '
                            'selection. Return valid JSON with an eligible candidate_id and short rationale.'))
            if attempt < 2:
                time.sleep(attempt+1)
        raise LLMError('LLM selection exhausted its three-request budget')


def choose(rows, state, target, max_candidates, route_budget, policy, seed, client, directory):
    context = public_context(rows, state, target, max_candidates, route_budget)
    if policy == 'llm':
        return client.select(context, directory)
    remaining = [r for r in rows if r['name'] in context['eligible_ids']]
    row, prediction = product_search.choose(rows[0]['workload'], remaining, [], policy,
                                            seed, len(state['selected']))
    return dict(candidate_id=row['name'], rationale=policy, prediction=prediction)


def promote(state, target, route_budget):
    allowed = min(route_budget, len(state['selected'])//2)
    if state['attempts']['routed'] >= allowed:
        return None
    options = []
    for name in state['selected']:
        stages = state['observations'].get(name, {})
        mapped = stages.get('mapped', {})
        if 'routed' in stages or not mapped.get('passed') or not device.resources_fit(mapped.get('metrics', {}), target):
            continue
        rate = device.performance(stages['qualified']['row'], target)['modeled_products_per_second']
        lut = mapped['metrics']['lut']
        key = (-rate, lut, name) if state['attempts']['routed'] % 2 == 0 else (lut, -rate, name)
        options.append((key, name))
    return min(options)[1] if options else None


def run_search(rows, target, store, out, policy='llm', seed=1, max_candidates=4,
               route_budget=2, client=None, resume=False, settings=None):
    """Store API: seed(name), evaluate(name,stage,observations,owner), recover(...)."""
    from .model import file_hash
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = dict(schema='llm-dse-run-v1', catalog_sha256=digest(rows), target=target,
                    backend=store.identity, policy=policy, seed=seed,
                    max_candidates=max_candidates, route_budget=route_budget,
                    settings=settings or {}, controller_sha256=file_hash(Path(__file__)))
    mf, sf = out/'manifest.json', out/'results.json'
    if mf.exists():
        if not resume:
            raise ValueError('run exists; use --resume')
        if json.loads(mf.read_text()) != manifest:
            raise ValueError('resume manifest differs')
        state = json.loads(sf.read_text())
        if state['status'] == 'complete':
            store.validate_observations(state['observations'])
            return state
    else:
        name = seed_name(rows)
        observations = {name: store.seed(name)}
        state = dict(schema='llm-dse-results-v1', status='running', policy=policy, seed=seed,
                     seed_name=name, observations=observations, selected=[], proposals=[],
                     attempts=dict(qualified=0, mapped=0, routed=0), history=[], active=None)
        write_json(mf, manifest)
        write_json(sf, state)

    def save():
        state['progress'] = progress(state, target)
        write_json(sf, state)

    def adopt(name, stage, result):
        state['observations'].setdefault(name, {})[stage] = result
        state['active'] = None
        state['history'].append(dict(candidate_id=name, stage=stage,
            passed=result['passed'], feasible=result.get('feasible', False),
            cache_hit=result.get('cache_hit', False), physical_seconds=result.get('physical_seconds', 0),
            hardware_seconds=result.get('hardware_seconds', 0), progress=progress(state, target)))
        save()

    def measure(name, stage):
        state['active'] = dict(candidate_id=name, stage=stage, started_at=time.time())
        state['attempts'][stage] += 1
        save()
        print(f'{policy}: {stage} {name}', flush=True)
        result = store.evaluate(name, stage, state['observations'].get(name, {}), str(out))
        adopt(name, stage, result)

    store.validate_observations(state['observations'])
    if state['active']:
        a = state['active']
        adopt(a['candidate_id'], a['stage'], store.recover(
            a['candidate_id'], a['stage'], state['observations'].get(a['candidate_id'], {}), str(out)))
    state['status'] = 'running'
    state.pop('error', None)
    save()
    try:
        while True:
            # Complete a saved proposal before requesting another one.
            for name in state['selected']:
                stages = state['observations'].get(name, {})
                if 'qualified' not in stages:
                    measure(name, 'qualified')
                stages = state['observations'][name]
                if stages['qualified']['passed'] and 'mapped' not in stages:
                    measure(name, 'mapped')
            while True:
                name = promote(state, target, route_budget)
                if name is None:
                    break
                measure(name, 'routed')
            if len(state['selected']) >= max_candidates:
                break
            remaining = {r['name'] for r in rows} - set(state['selected']) - {state['seed_name']}
            if not remaining:
                break
            proposal = choose(rows, state, target, max_candidates, route_budget, policy, seed,
                              client, out/'llm'/f'selection-{len(state["selected"])+1}')
            if proposal['candidate_id'] not in remaining:
                raise ValueError('policy returned an ineligible candidate')
            state['proposals'].append(proposal)
            state['selected'].append(proposal['candidate_id'])
            save()
        state['status'] = 'complete'
        save()
        return state
    except Exception as error:
        state['status'] = 'failed'
        state['error'] = str(error) if isinstance(error, LLMError) else type(error).__name__
        save()
        raise
