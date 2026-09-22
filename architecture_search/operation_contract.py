"""Independent decoder of lowered SGen operations and their emitted RTL.

This is deliberately a closed grammar. Unknown lowering requires a reviewed
checker update, never acceptance based on a self-reported generator label.
It checks structure, not end-to-end FFT equivalence or scheduling correctness.
"""
import re
from pathlib import Path
from collections import Counter
from .model import digest, file_hash


def tokens(source):
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    return re.findall(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+|[A-Za-z_$][\w$]*|\d+|<=|==|[^\s]", source)


def decode(contract, top):
    if contract.get('schema') != 'sgen-lowered-operations-v1':
        raise ValueError('unsupported operation contract')
    nodes = contract['nodes']
    if not nodes or [n['id'] for n in nodes] != list(range(len(nodes))):
        raise ValueError('noncanonical node identifiers')
    allowed = {'Input', 'Output', 'Const', 'Wire', 'Plus', 'Minus', 'Times',
               'And', 'Xor', 'Or', 'Equals', 'Not', 'Concat', 'Tap', 'Register', 'Mux', 'RAM'}
    for n in nodes:
        if n['op'] not in allowed or type(n['width']) is not int or n['width'] < 1:
            raise ValueError('unsupported node or width')
        if any(type(i) is not int or not 0 <= i < len(nodes) for i in n['inputs']):
            raise ValueError('unknown operation operand')
        if n['op'] != 'Const' and not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', n['signal']):
            raise ValueError('invalid signal name')
        if n['op'] == 'Const':
            value = int(n['value'])
            if not 0 <= value < 1 << n['width'] or n['signal'] != f"{n['width']}'d{value}":
                raise ValueError('constant encoding mismatch')
    def node(i): return nodes[i]
    def name(i): return node(i)['signal']
    def width(i): return node(i)['width']
    def decl(n): return (f"[{n['width']-1}:0] " if n['width'] != 1 else '') + n['signal']
    ins = [node(i) for i in contract['inputs']]
    outs = [node(i) for i in contract['outputs']]
    if {n['id'] for n in ins} != {n['id'] for n in nodes if n['op'] == 'Input'}:
        raise ValueError('input inventory mismatch')
    if {n['id'] for n in outs} != {n['id'] for n in nodes if n['op'] == 'Output'}:
        raise ValueError('output inventory mismatch')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', top): raise ValueError('invalid top')
    declarations, assignments, sequential, combinatorial = [], [], [], []
    expressions = []
    for n in nodes:
        op, args, w, signal = n['op'], n['inputs'], n['width'], n['signal']
        names = [name(i) for i in args]
        widths = [width(i) for i in args]
        rhs = None
        if op in ('Input', 'Const'):
            if args: raise ValueError('leaf has operands')
        elif op in ('Wire', 'Output'):
            if len(args) != 1 or widths != [w]: raise ValueError('wire width mismatch')
            if op == 'Output': rhs = names[0]
            elif signal != names[0]: raise ValueError('wire alias mismatch')
        elif op in ('Plus', 'And', 'Xor', 'Or'):
            if not args or any(x != w for x in widths): raise ValueError('operator width mismatch')
            rhs = (' ' + {'Plus': '+', 'And': '&', 'Xor': '^', 'Or': '|'}[op] + ' ').join(names)
        elif op in ('Minus', 'Equals', 'Times'):
            if len(args) != 2: raise ValueError('binary operator arity')
            if op == 'Times':
                if n.get('signed') is not True or w != sum(widths): raise ValueError('multiply semantics')
                rhs = f'$signed({names[0]}) * $signed({names[1]})'
            else:
                if widths[0] != widths[1] or w != (1 if op == 'Equals' else widths[0]):
                    raise ValueError('binary operator width')
                rhs = f"{names[0]} {'-' if op == 'Minus' else '=='} {names[1]}"
        elif op == 'Not':
            if widths != [w]: raise ValueError('not width')
            rhs = '~' + names[0]
        elif op == 'Concat':
            if not args or sum(widths) != w: raise ValueError('concatenation width')
            rhs = '{' + ', '.join(names) + '}'
        elif op == 'Tap':
            lo, hi = n['low'], n['high']
            if len(args) != 1 or not 0 <= lo <= hi < widths[0] or hi-lo+1 != w:
                raise ValueError('invalid bit slice')
            rhs = f"{names[0]}[{str(hi)+':' if hi != lo else ''}{lo}]"
        elif op == 'Mux':
            if len(args) < 2 or any(x != w for x in widths[1:]) or len(args)-1 > 1 << widths[0]:
                raise ValueError('multiplexer shape')
            if widths[0] == 1:
                rhs = f'{names[0]} ? {names[-1]} : {names[1]}'
            else:
                body = ['always @(*)', f'case({names[0]})']
                for j, term in enumerate(names[1:]):
                    label = 'default' if j == len(args)-2 and (1 << widths[0]) != len(args)-1 else str(j)
                    body.append(f'{label}: {signal} = {term};')
                combinatorial += body + ['endcase']
        elif op == 'Register':
            cycles = n['cycles']; internal = n['internal']
            if widths != [w] or type(cycles) is not int or cycles < 1: raise ValueError('register shape')
            if cycles == 1: sequential.append(f'{signal} <= {names[0]};')
            elif cycles == 2: sequential += [f'{internal} <= {names[0]};', f'{signal} <= {internal};']
            else:
                rhs = f'{internal} [{cycles-1}]'
                sequential += [f'{internal} [0] <= {names[0]};',
                               f'for (i = 1; i < {cycles}; i = i + 1)', f'{internal} [i] <= {internal} [i - 1];']
        elif op == 'RAM':
            if len(args) != 3 or widths[0] != w or widths[1] != widths[2]: raise ValueError('RAM shape')
            sequential += [f"{n['internal']} [{names[1]}] <= {names[0]};",
                           f"{signal} <= {n['internal']} [{names[2]}];"]
        if op not in ('Input', 'Output', 'Wire', 'Const'):
            kind = 'reg' if op in ('Register', 'RAM') or (op == 'Mux' and widths[0] > 1) else 'wire'
            if op == 'Register' and n['cycles'] > 2: kind = 'wire'
            if op == 'Register' and n['cycles'] > 1:
                suffix = f" [{n['cycles']-1}:0]" if n['cycles'] > 2 else ''
                declarations.append('reg ' + decl({**n, 'signal': n['internal']}) + suffix + ';')
            if op == 'RAM':
                declarations.append('reg ' + decl({**n, 'signal': n['internal']}) + f' [{(1 << widths[1])-1}:0];')
            declarations.append(kind + ' ' + decl(n) + ';')
        if rhs is not None:
            assignments.append(f'assign {signal} = {rhs};')
            if op not in ('Register', 'Output'):
                expressions.append({'node': n['id'], 'op': op, 'width': w, 'inputs': args, 'rhs': rhs})
    ports = ['input clk'] + ['input ' + decl(n) for n in ins] + ['output ' + decl(n) for n in outs]
    source = ['module ' + top + '(' + ','.join(ports) + ');']
    source += declarations + ['integer i;'] + assignments + combinatorial
    if sequential: source += ['always @(posedge clk) begin'] + sequential + ['end']
    source += ['endmodule']
    return '\n'.join(source), expressions


def audit(meta, path):
    contract = meta['operation_contract']
    reconstructed, expressions = decode(contract, meta['top'])
    actual = path.read_text()
    if file_hash(path) != meta['rtl_sha256']: raise ValueError('RTL hash mismatch')
    if tokens(actual) != tokens(reconstructed):
        a, b = tokens(actual), tokens(reconstructed)
        mismatch = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        raise ValueError(f'RTL differs from lowered contract at token {mismatch}: {a[mismatch:mismatch+8]} != {b[mismatch:mismatch+8]}')
    nodes = contract['nodes']; scalar = meta['integer_bits'] + meta['fractional_bits']
    multiplies = [n for n in nodes if n['op'] == 'Times']
    if not multiplies: raise ValueError('missing FFT arithmetic')
    for n in multiplies:
        if [nodes[i]['width'] for i in n['inputs']] != [scalar, scalar]:
            raise ValueError('unexpected FFT multiply width')
        users = [u for u in nodes if n['id'] in u['inputs']]
        if not users or any(u['op'] != 'Tap' or u['low'] != meta['twiddle_fractional_bits'] or u['width'] != scalar for u in users):
            raise ValueError('FFT multiply does not truncate at the declared position')
    body = dict(schema='sgen-operation-audit-v1', passed=True, rtl_sha256=file_hash(path),
                contract_sha256=digest(contract), node_counts=dict(Counter(n['op'] for n in nodes)),
                multiply_count=len(multiplies), checker_sha256=file_hash(Path(__file__)),
                limitation='Closed-grammar RTL correspondence; factorization and sequential behavior require independent tests.')
    return {**body, 'audit_sha256': digest(body)}
