"""Actual-width combinational checks; no full-transform equivalence claim."""
import json
import re
import shutil
from pathlib import Path
from .model import digest, file_hash, run, write_json
from .operation_contract import audit, tokens


def prove(meta, rtl, directory, timeout=60, yosys='yosys'):
    audit_result = audit(meta, rtl)
    directory = directory.resolve(); directory.mkdir(parents=True, exist_ok=True)
    executable = shutil.which(yosys)
    if not executable: raise ValueError('layered assurance requires Yosys 0.50 on PATH')
    identity = run([executable, '-V'], directory, directory/'version.log', 10)
    version = (directory/'version.log').read_text().strip()
    if identity['returncode'] or not version.startswith('Yosys 0.50 '):
        raise ValueError('primitive proofs require pinned Yosys 0.50')
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', rtl.read_text(), flags=re.S)
    assignments = dict(re.findall(r'\bassign\s+(\w+)\s*=\s*([^;]+);', source))
    nodes = meta['operation_contract']['nodes']; records = []; seen = set()
    for n in nodes:
        if n['op'] not in ('Plus', 'Minus', 'Times', 'Tap'): continue
        inputs = [nodes[i] for i in n['inputs']]
        key = (n['op'], n['width'], tuple(i['width'] for i in inputs), n.get('low'), n.get('high'))
        # The structural audit established the expression for every instance.
        if key in seen: continue
        seen.add(key)
        mapping = {}; ports = []; values = []
        for term in inputs:
            signal = term['signal']
            if signal not in mapping:
                name = f'x{len(mapping)}'; mapping[signal] = name
                ports.append(f"input [{term['width']-1}:0] {name}")
            values.append(mapping[signal])
        actual = ' '.join(mapping.get(t, t) for t in tokens(assignments[n['signal']]))
        if n['op'] == 'Plus': reference = '(' + ') + ('.join(values) + ')'
        elif n['op'] == 'Minus': reference = f'({values[0]}) - ({values[1]})'
        elif n['op'] == 'Times': reference = f'$signed({values[0]}) * $signed({values[1]})'
        else: reference = f"({values[0]} >> {n['low']})"
        text = f"""module proof({','.join(ports)}, output ok);
wire [{n['width']-1}:0] actual = {actual};
wire [{n['width']-1}:0] expected = {reference};
assign ok = actual == expected;
endmodule
"""
        stem = digest(key); path = directory/(stem+'.v'); path.write_text(text)
        script = directory/(stem+'.ys')
        script.write_text(f'read_verilog {path.name}\nprep -top proof\nflatten\nopt\nsat -verify -prove ok 1 -show-inputs -show-outputs\n')
        log = directory/(stem+'.log')
        process = run([executable, '-s', script.name], directory, log, timeout)
        passed = process['returncode'] == 0 and 'SUCCESS!' in log.read_text()
        records.append(dict(shape=key, passed=passed, process=process,
                            files={str(p): file_hash(p) for p in (path, script, log)}))
    body = dict(schema='fft-primitive-proofs-v1', passed=bool(records) and all(r['passed'] for r in records),
                audit=audit_result, tool=dict(version=version, sha256=file_hash(Path(executable))),
                checker_sha256=file_hash(Path(__file__)), records=records,
                limitation='Combinational primitive checks; no proof of FFT factorization, memories, or scheduling.')
    result = {**body, 'proof_sha256': digest(body)}
    write_json(directory/'proofs.json', result)
    return result


def valid(proof, meta, rtl):
    try:
        body = {k: v for k, v in proof.items() if k != 'proof_sha256'}
        shapes={digest((n['op'],n['width'],tuple(meta['operation_contract']['nodes'][i]['width'] for i in n['inputs']),
                        n.get('low'),n.get('high')))
                for n in meta['operation_contract']['nodes'] if n['op'] in ('Plus','Minus','Times','Tap')}
        return (proof['schema'] == 'fft-primitive-proofs-v1' and proof['passed'] is True
                and proof['records'] and proof['proof_sha256'] == digest(body)
                and {digest(r['shape']) for r in proof['records']}==shapes
                and proof['checker_sha256'] == file_hash(Path(__file__))
                and proof['audit'] == audit(meta, rtl)
                and all(r['passed'] is True and all(file_hash(Path(p)) == h for p, h in r['files'].items())
                        for r in proof['records']))
    except (KeyError, TypeError, ValueError, OSError): return False


def prove_rounding(n, scalar, frac, output_width, directory, timeout=60, yosys='yosys'):
    """Prove the actual emitted fold function against sign/magnitude rounding."""
    from .product_rtl import fold_module
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=True)
    emitted=fold_module(n,scalar,frac,output_width)
    function=re.search(r'function automatic.*?endfunction',emitted,re.S).group()
    shift=frac+(2*n).bit_length()-1
    text=f'''module proof(input signed [{scalar}:0] v,output ok);
localparam W={scalar},OW={output_width},SHIFT={shift};
{function}
wire [W:0] magnitude=v[W] ? (~v + 1'b1) : v;
wire [W:0] quotient=magnitude >> SHIFT;
wire [SHIFT-1:0] remainder=magnitude[SHIFT-1:0];
wire increment=(remainder > ({{1'b1,{{(SHIFT-1){{1'b0}}}}}})) ||
 ((remainder == ({{1'b1,{{(SHIFT-1){{1'b0}}}}}})) && quotient[0]);
wire [W:0] absolute_result=quotient+increment;
wire [W:0] signed_result=v[W] ? (~absolute_result+1'b1) : absolute_result;
assign ok=rounded(v)==signed_result[OW-1:0];
endmodule
'''
    path=directory/'rounding.v';path.write_text(text)
    script=directory/'rounding.ys';script.write_text('read_verilog rounding.v\nprep -top proof\nflatten\nopt\nsat -verify -prove ok 1\n')
    log=directory/'rounding.log'
    process=run([yosys,'-s',script.name],directory,log,timeout)
    return dict(passed=process['returncode']==0 and 'SUCCESS!' in log.read_text(),process=process,
                files={str(p):file_hash(p) for p in (path,script,log)},
                emitted_sha256=digest(emitted),checker_sha256=file_hash(Path(__file__)))


def prove_pointwise(scalar, frac, directory, timeout=60, yosys='yosys'):
    """Inductive check of the emitted elastic complex product pipeline."""
    from .product_rtl import multiply_module
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=True)
    emitted=multiply_module(2*scalar,True,frac)
    abstract=emitted;cuts=[]
    for lane in range(2):
        for term in ('rr','ii','ri','ir'):
            left=2*scalar*lane+(scalar if term[0]=='i' else 0)
            right=2*scalar*lane+(scalar if term[1]=='i' else 0)
            assignment=f"{term}{lane} <= $signed(a[{left} +: {scalar}]) * $signed(b[{right} +: {scalar}]);"
            if abstract.count(assignment)!=1:raise ValueError('pointwise multiplication differs from proved signed primitive')
            name=f'p{len(cuts)}';cuts.append(name)
            abstract=abstract.replace(assignment,f'{term}{lane} <= {name};')
    cut_ports=','.join(f'input [{2*scalar-1}:0] {name}' for name in cuts)
    abstract=abstract.replace('out_data);','out_data,'+cut_ports+');')
    lines=[abstract,f'''module proof(input clock,reset,av,bv,ready,
input [{4*scalar-1}:0] a,b,{cut_ports},output ok);
wire ar,br,valid;wire [{4*scalar-1}:0] result;
ProductMultiply dut(clock,reset,av,bv,ar,br,a,b,valid,ready,result,{','.join(cuts)});
reg [2:0] tokens;reg [{4*scalar-1}:0] q0,q1,q2;
wire step=!tokens[2] || ready;
wire [{4*scalar-1}:0] expected;
''']
    for lane in range(2):
        offset=2*scalar*lane
        for term in ('rr','ii','ri','ir'):
            left=offset+(scalar if term[0]=='i' else 0)
            right=offset+(scalar if term[1]=='i' else 0)
            cut=cuts[4*lane+('rr','ii','ri','ir').index(term)]
            lines.append(f'wire signed [{2*scalar-1}:0] {term}{lane}={cut};')
        lines += [f'assign expected[{offset} +: {scalar}]=(rr{lane} >>> {frac}) - (ii{lane} >>> {frac});',
                  f'assign expected[{offset+scalar} +: {scalar}]=(ri{lane} >>> {frac}) + (ir{lane} >>> {frac});']
    lines.append('''always @(posedge clock) begin
if(reset)tokens<=0;
else if(step)begin tokens<={tokens[1:0],av && bv};q0<=expected;q1<=q0;q2<=q1;end
end
assign ok=(valid==tokens[2]) && (!valid || result==q2) && (ar==(step && bv)) && (br==(step && av));
endmodule
''')
    path=directory/'pointwise.v';path.write_text('\n'.join(lines))
    script=directory/'pointwise.ys'
    script.write_text('read_verilog pointwise.v\nprep -top proof\nflatten\nopt\nsat -seq 4 -set-init-zero -tempinduct -maxsteps 12 -verify -prove ok 1\n')
    log=directory/'pointwise.log';process=run([yosys,'-s',script.name],directory,log,timeout)
    return dict(passed=process['returncode']==0 and 'SUCCESS!' in log.read_text(),process=process,
                files={str(p):file_hash(p) for p in (path,script,log)},
                emitted_sha256=digest(emitted),checker_sha256=file_hash(Path(__file__)))


def adapter_valid(proof, emitted):
    try:
        return (proof['passed'] is True and proof['emitted_sha256']==digest(emitted)
                and proof['checker_sha256']==file_hash(Path(__file__))
                and all(file_hash(Path(p))==h for p,h in proof['files'].items()))
    except (KeyError,TypeError,ValueError,OSError):return False
