"""Dependency-free experiment tables, SVG charts, and a standalone HTML report."""
import html
import json
from pathlib import Path

from . import llm_dse
from .dse_replay import failure_reason
from .model import write_json

COLORS = {'llm': '#1f77b4', 'random': '#ff7f0e', 'analytical': '#2ca02c'}


def chart(states, target):
    width, height = 1170, 380
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
             '<title>Area and budgeted search progress</title>',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font:12px sans-serif;fill:#222}.axis{stroke:#888;fill:none}.grid{stroke:#eee}</style>']
    series = []
    for state in states:
        initial = dict(state, observations={state['seed_name']: state['observations'][state['seed_name']]},
                       selected=[], attempts=dict(qualified=0, mapped=0, routed=0))
        trace = [llm_dse.progress(initial, target), *[h['progress'] for h in state['history']]]
        points = llm_dse.feasible_points(state, target)
        series.append((state['policy'], points, trace))
    for panel, xlabel, ylabel in [(0, 'Routed LUTs', 'Modeled products/s'),
                                  (1, 'New candidate attempts', 'Normalized hypervolume'),
                                  (2, 'Logical routing attempts', 'Normalized hypervolume')]:
        x0, y0, w, h = panel*390+72, 45, 294, 260
        groups = []
        for policy, points, trace in series:
            if panel == 0:
                chosen = set(llm_dse.frontier(points))
                data = [(p['lut'], p['modeled_products_per_second']) for p in points if p['name'] in chosen]
                data.sort()
            else:
                data = [(p['candidates' if panel == 1 else 'routed'], p['hypervolume']) for p in trace]
            groups.append((policy, data))
        xs = [x for _, data in groups for x, y in data] or [0, 1]
        ys = [y for _, data in groups for x, y in data] or [0, 1]
        xmin, xmax = (min(xs), max(xs)) if panel == 0 else (0, max(xs))
        ymin, ymax = min(ys), max(ys)
        if xmin == xmax:
            xmin, xmax = xmin-1, xmax+1
        if ymin == ymax:
            ymin, ymax = ymin-.05*max(1, abs(ymin)), ymax+.05*max(1, abs(ymax))
        xpad = (xmax-xmin)*.06
        ypad = (ymax-ymin)*.08
        xmin, xmax, ymin, ymax = xmin-xpad, xmax+xpad, ymin-ypad, ymax+ypad
        def xy(x, y):
            return (x0+(x-xmin)/(xmax-xmin)*w, y0+h-(y-ymin)/(ymax-ymin)*h)
        for i in range(5):
            xv, yv = xmin+(xmax-xmin)*i/4, ymin+(ymax-ymin)*i/4
            px, py = xy(xv, yv)
            parts.extend([f'<path class="grid" d="M{px:.2f} {y0}v{h}M{x0} {py:.2f}h{w}"/>',
                f'<text x="{px:.2f}" y="{y0+h+20}" text-anchor="middle">{xv:.3g}</text>',
                f'<text x="{x0-8}" y="{py+4:.2f}" text-anchor="end">{yv:.3g}</text>'])
        parts.append(f'<path class="axis" d="M{x0} {y0}v{h}h{w}"/>')
        parts.append(f'<text x="{x0+w/2}" y="{y0+h+47}" text-anchor="middle">{xlabel}</text>')
        parts.append(f'<text transform="translate({x0-53},{y0+h/2}) rotate(-90)" text-anchor="middle">{ylabel}</text>')
        for index, (policy, data) in enumerate(groups):
            color = COLORS[policy]
            coords = []
            previous = None
            for x, y in data:
                if panel and previous is not None:
                    coords.append(xy(x, previous))
                coords.append(xy(x, y))
                previous = y
            points_attr = ' '.join(f'{x:.2f},{y:.2f}' for x, y in coords)
            dash = ('', '6 3', '2 3')[index % 3]
            parts.append(f'<polyline points="{points_attr}" fill="none" stroke="{color}" '
                         f'stroke-width="2" stroke-dasharray="{dash}"/>')
            if panel == 0:
                for x, y in data:
                    px, py = xy(x, y)
                    parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{5+index*2}" '
                                 f'fill="none" stroke="{color}" stroke-width="2"/>')
    for i, (policy, _, _) in enumerate(series):
        x = 90+i*140
        parts.append(f'<text x="{x}" y="22" style="fill:{COLORS[policy]}">{html.escape(policy)}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)+'\n'


def generate(out, states, target, mode, metadata):
    from scripts.llm_polynomial_study import report
    out = Path(out)
    if not states:
        raise ValueError('no trials yet; run the experiment first')
    for state in states:
        state['progress'] = llm_dse.progress(state, target)
    report(out, states, target, mode)
    snapshot = json.loads((out/'comparison.json').read_text())
    snapshot['experiment'] = metadata
    snapshot['evidence_scope'] = ('Published measurement replay; no local RTL/checkpoint signoff.' if mode == 'replay'
                                  else 'Native qualification and routed kernel-harness signoff; no board measurement.')
    snapshot['coverage'] = dict(unique_candidates=len({n for s in states for n in s['observations']}),
        unique_routed=len({n for s in states for n, stages in s['observations'].items() if 'routed' in stages}))
    snapshot['trials'] = []
    for state in states:
        for proposal in state['proposals']:
            name = proposal['candidate_id']
            stages = state['observations'].get(name, {})
            snapshot['trials'].append(dict(policy=state['policy'], candidate_id=name,
                proposal=proposal, stages={stage: dict(passed=value['passed'], feasible=value.get('feasible'),
                    reason=failure_reason(value, stage, target), metrics=value.get('metrics', {}),
                    cache_hit=value.get('cache_hit', False)) for stage, value in stages.items()}))
    write_json(out/'comparison.json', snapshot)
    svg = chart(states, target)
    (out/'comparison.svg').write_text(svg)
    summary = (out/'summary.md').read_text()
    summary = summary.replace('![Area and search progress]', '[Standalone HTML report](report.html)\n\n![Area and search progress]')
    summary += '\nEvidence scope: '+snapshot['evidence_scope']+'\n'
    (out/'summary.md').write_text(summary)
    rows = []
    for p in snapshot['policies']:
        rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (
            p['policy'], p['status'], p['candidates'], p['mapped'], p['routed'], p['feasible'],
            f"{p['best_products_per_second']:,.1f}", f"{p['hypervolume']:.4f}", p['failures'],
            f"{p['physical_mapped']}/{p['physical_routed']}", p['llm_requests']))+'</tr>')
    headings = ('Policy', 'Status', 'Candidates', 'Maps', 'Routes', 'Feasible incl. seed',
                'Best modeled products/s', 'Hypervolume', 'Failures', 'New physical maps/routes', 'LLM requests')
    page = ['<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Polynomial multiplication DSE report</title>',
        '<style>body{font:15px system-ui;max-width:1250px;margin:36px auto;padding:0 20px;color:#222}'
        'table{border-collapse:collapse;width:100%}td,th{padding:9px;border:1px solid #ddd;text-align:left}'
        'svg{width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{overflow-x:auto}</style>',
        '<h1>Polynomial multiplication DSE</h1>',
        f'<p>Mode: <strong>{html.escape(mode)}</strong>. Exact N=512 full32 × ternary; '
        '250 MHz kernel harness. Common disclosed seed; modeled throughput, not board measurements.</p>',
        '<p>'+html.escape(snapshot['evidence_scope'])+'</p>',
        '<section><table><thead><tr>'+''.join('<th>'+h+'</th>' for h in headings)+'</tr></thead><tbody>',
        *rows, '</tbody></table></section>', svg,
        '<p>Overlapping curves indicate equal observed outcomes. Cache hits consume logical budgets; '
        'new physical executions depend on policy order. This limited replay/demo does not establish an LLM search advantage.</p>',
        '<p><a href="comparison.csv">Comparison CSV</a> · <a href="points.csv">Point CSV</a> · '
        '<a href="comparison.json">Metrics and provenance</a> · <a href="comparison.svg">SVG chart</a></p>',
        '<details><summary>Acquired trial outcomes and failure reasons</summary><pre>'+html.escape(
            json.dumps(snapshot['trials'], indent=2))+'</pre></details></html>']
    (out/'report.html').write_text('\n'.join(page)+'\n')
    return snapshot
