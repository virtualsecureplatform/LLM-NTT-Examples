"""Hash-sealed Vivado out-of-context mapping and routing of qualified products."""
import copy
import json
import re
from pathlib import Path
from .model import artifact_manifest, digest, evidence_integrity, file_hash, run, write_json
from .device import RESOURCES
from . import timing_harness


def parse_utilization(text):
    labels = {'CLB LUTs':'lut','Slice LUTs':'lut','CLB Registers':'ff','Slice Registers':'ff',
              'DSPs':'dsp','Block RAM Tile':'bram36','URAM':'uram'}
    metrics, capacity = {}, {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split('|')[1:-1]]
        if len(parts) < 6 or parts[0].rstrip('*') not in labels:
            continue
        key = labels[parts[0].rstrip('*')]
        if key in metrics: continue  # Ignore subsequent per-SLR tables.
        metrics[key] = float(parts[1].replace(',',''))
        capacity[key] = float(parts[4].replace(',',''))
    if set(metrics) != set(RESOURCES):
        raise ValueError('missing mapped resource categories: ' + str(set(RESOURCES)-set(metrics)))
    return metrics, capacity


def parse_timing(text):
    checks = {k:int(v) for k,v in re.findall(r'checking (\w+) \((\d+)\)',text)}
    required = ('no_clock','unconstrained_internal_endpoints','no_input_delay','no_output_delay',
                'partial_input_delay','partial_output_delay','loops','latch_loops','multiple_clock')
    fully = all(k in checks and checks[k] == 0 for k in required)
    # The Design Timing Summary row includes setup, hold, and pulse-width slacks.
    match = re.search(r'WNS\(ns\).*?WPWS\(ns\)[^\n]*\n\s*-+[^\n]*\n\s*([^\n]+)',text,re.S)
    if match is None: raise ValueError('missing design timing summary')
    values = match[1].split()
    if len(values) < 12: raise ValueError('incomplete design timing summary')
    return dict(setup_slack_ns=float(values[0]), hold_slack_ns=float(values[4]),
                pulse_slack_ns=float(values[8]), fully_constrained=fully, constraint_checks=checks)


def tcl_word(value):
    value = str(value)
    for old,new in (('\\','\\\\'),('"','\\"'),('$','\\$'),('[','\\['),(']','\\]'),('\n','\\n')):
        value = value.replace(old,new)
    return '"' + value + '"'


def script(target, rtl, directory, stage, checkpoint=None, threads=4, harness=None):
    period = 1000 / target['clock_mhz']
    delay = period * target['io_delay_fraction']
    preamble = f'set_param general.maxThreads {threads}\n'
    if stage == 'mapped':
        top='TimingHarness' if harness else 'SearchTop'
        preamble += f'''read_verilog -sv {tcl_word(rtl)}
'''
        if harness:preamble+=f'read_verilog -sv {tcl_word(harness)}\n'
        preamble+=f'''synth_design -top {top} -part {tcl_word(target['part'])} -mode out_of_context
create_clock -name clock -period {period} [get_ports clock]
'''
        if not harness:preamble+=f'''
set_input_delay -clock clock -max {delay} [get_ports -filter {{DIRECTION == IN && NAME != clock}}]
set_input_delay -clock clock -min 0 [get_ports -filter {{DIRECTION == IN && NAME != clock}}]
'''
        if not harness or target.get('implementation_context')!=timing_harness.CONTEXT:preamble+=f'''
set_output_delay -clock clock -max {delay} [all_outputs]
set_output_delay -clock clock -min 0 [all_outputs]
'''
    elif stage == 'routed':
        directive='Explore' if target['implementation_directive']=='ExploreHoldFix' else 'Default'
        preamble += f'open_checkpoint {tcl_word(checkpoint)}\n'
        if target['implementation_directive']=='HoldFix':preamble+='phys_opt_design -hold_fix\nroute_design\n'
        else:preamble += f'''
opt_design
place_design -directive {directive}
phys_opt_design -directive {directive}
route_design -directive {directive}
'''
        if directive=='Explore':preamble+='phys_opt_design -hold_fix\nroute_design\n'
    else: raise ValueError('stage must be mapped or routed')
    if harness:preamble+=timing_harness.checks_tcl(directory,tcl_word)
    return preamble + f'''report_utilization -file {tcl_word(directory/'utilization.rpt')}
report_timing_summary -delay_type min_max -report_unconstrained -file {tcl_word(directory/'timing.rpt')}
report_drc -file {tcl_word(directory/'drc.rpt')}
write_checkpoint -force {tcl_word(directory/'design.dcp')}
write_xdc -force {tcl_word(directory/'constraints.xdc')}
exit
'''


def tool_identity(vivado, directory):
    vivado = Path(vivado).resolve()
    result = run([str(vivado),'-version'],directory,directory/'vivado.version.log',120)
    text = (directory/'vivado.version.log').read_text()
    match = re.search(r'Vivado v([\d.]+)',text,re.I)
    if result['returncode'] or match is None: raise ValueError('Vivado version probe failed')
    files = [vivado]
    binary = vivado.parent/'unwrapped/lnx64.o/vivado'
    if binary.is_file(): files.append(binary)
    return dict(version=match[1], binaries={str(p):file_hash(p) for p in files}, version_text=text)


def evaluate(row, rtl, target, tool, vivado, directory, stage='mapped', mapped=None, timeout=3600, threads=4):
    directory = Path(directory).resolve(); directory.mkdir(parents=True,exist_ok=True)
    rtl = Path(rtl).resolve()
    if not row.get('passed') or file_hash(rtl) != row['rtl_sha256']:
        raise ValueError('unqualified or changed product RTL')
    if tool['version'] != target['vivado_version']: raise ValueError('Vivado version does not match target')
    checkpoint = None
    harness=None
    if target.get('implementation_context') in timing_harness.CONTEXTS:
        harness=directory/'TimingHarness.sv'
        harness.write_text(timing_harness.emit(row['workload'],target['implementation_context']))
        if stage=='mapped':
            root=Path(__file__).resolve().parents[1]
            validation_dir=directory/'validation';validation_dir.mkdir(exist_ok=True)
            rowfile=validation_dir/'row.json';write_json(rowfile,row)
            image=root/'build/fhe512-sgen-precision.sif'
            check=run(['apptainer','exec','--cleanenv','--no-home','--bind',f'{root}:{root}',
                       '--pwd',str(root),str(image),'python3','-m','architecture_search.timing_harness',
                       '--row',str(rowfile),'--rtl',str(rtl),'--output-dir',str(validation_dir),'--context',target['implementation_context']],
                      root,validation_dir/'driver.log',900)
            if check['returncode']:raise ValueError('harness simulation failed: '+str(validation_dir))
            validation=json.loads((validation_dir/'validation.json').read_text())
            validation['image_sha256']=file_hash(image)
        else:validation=mapped.get('harness_validation',{}) if mapped else {}
        if not validation.get('passed') or validation.get('rtl_sha256')!=row['rtl_sha256'] or validation.get('harness_sha256')!=file_hash(harness) or evidence_integrity(validation)!='verified':
            raise ValueError('harness lacks intact functional evidence')
    if stage == 'routed':
        mapping_target=lambda t:{k:v for k,v in t.items() if k!='implementation_directive'}
        required_stage='routed' if target['implementation_directive']=='HoldFix' else 'mapped'
        if not mapped or mapped.get('stage')!=required_stage or not mapped.get('passed') or mapped.get('tool')!=tool or mapping_target(mapped.get('target',{})) != mapping_target(target) or mapped.get('rtl_sha256') != row['rtl_sha256'] or evidence_integrity(mapped) != 'verified':
            raise ValueError('routing requires intact mapped evidence for this RTL and target')
        checkpoint = Path(mapped['checkpoint'])
    tcl = directory/'run.tcl'
    tcl.write_text(script(target,rtl,directory,stage,checkpoint,threads,harness))
    inputs = artifact_manifest([rtl,tcl,*([harness] if harness else []),*([checkpoint] if checkpoint else [])])
    process = run([str(vivado),'-mode','batch','-nojournal','-log',str(directory/'vivado.log'),
                   '-source',str(tcl)],directory,directory/'process.log',timeout)
    e = dict(stage=stage,target=copy.deepcopy(target),tool=tool,rtl_sha256=row['rtl_sha256'],
             process=process,passed=False,metrics={},checkpoint=str(directory/'design.dcp'),
             implementation_seed='tool-default',scope='out-of-context product kernel; no board shell')
    if harness:e.update(harness_sha256=file_hash(harness),harness_verified=False,harness_validation=validation,
                        scope='routed registered kernel harness; no board shell')
    if process['returncode'] == 0:
        try:
            resources, capacity = parse_utilization((directory/'utilization.rpt').read_text())
            if any(capacity[k] != target['capacity'][k] for k in RESOURCES):
                raise ValueError('reported device capacities differ from target')
            e['metrics'] = {**resources,**parse_timing((directory/'timing.rpt').read_text())}
            drc = (directory/'drc.rpt').read_text()
            e['passed'] = (directory/'design.dcp').is_file() and not re.search(r'\|\s*[^|]+\|\s*(?:Error|Critical Warning)\s*\|',drc,re.I)
            if harness:
                checks=dict(re.findall(r'(\w+) (\d+)',(directory/'harness-checks.rpt').read_text()))
                e['harness_verified']=(int(checks.get('kernel_cells',0))>=100 and int(checks.get('source_cells',0))>=64
                                       and int(checks.get('sink_cells',0))>=64 and int(checks.get('clock_buffers',0))>=1
                                       and int(checks.get('clocks',1))==1)
                e['passed']=e['passed'] and e['harness_verified']
            if not e['passed']: e['reason'] = 'checkpoint missing or DRC error/critical warning'
        except (OSError,ValueError) as error: e['reason'] = str(error)
    else: e['reason'] = 'timeout' if process.get('timed_out') else 'Vivado failed'
    outputs = [p for p in directory.iterdir() if p.is_file() and p.suffix in ('.log','.rpt','.dcp','.xdc')]
    e['integrity'] = dict(version=1,inputs_unchanged=inputs==artifact_manifest(inputs['files']),
                          inputs=inputs,outputs=artifact_manifest(outputs),
                          measurement={k:copy.deepcopy(e[k]) for k in ('passed','metrics','target','tool','stage','rtl_sha256','checkpoint',
                              *(['harness_sha256','harness_verified','harness_validation','scope'] if harness else []))})
    write_json(directory/'evidence.json',e)
    return e
