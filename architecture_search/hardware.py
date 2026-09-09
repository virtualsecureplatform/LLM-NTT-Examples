"""Vendor implementation stages; target frequency is never treated as achieved automatically."""
from __future__ import annotations
import copy
import json
import fcntl
import os
import shutil
import tempfile
import time
from pathlib import Path
from .model import artifact_manifest, metric_number, run


def _evaluate(rtl: Path, top: str, target: dict, metrics: dict, directory: Path, stage: str,
             timeout: float, extra_sources: list[Path] | None = None, include_dirs: list[Path] | None = None,
             additional_inputs: list[Path] | None = None) -> dict:
    root=Path(__file__).resolve().parents[1]
    period=float(target.get('clock_period_ns',4.0))
    if not metric_number(period) or period<=0 or stage not in ('synthesis','route'):
        raise ValueError('invalid clock or implementation stage')
    directory.mkdir(parents=True,exist_ok=True)
    output=directory/'metrics.json'
    version=target.get('tool_version','2023.2')
    vivado=target.get('vivado',f'/home/opt/xilinx/Vivado/{version}/bin/vivado')
    # Bash can read later portions after a long vendor call. Never run a mutable
    # workspace script across that call; snapshot its helper alongside it.
    driver=directory.parent/(directory.name+'-driver')/'scripts'
    driver.mkdir(parents=True,exist_ok=True)
    for name in ('vitis_synth_rtl.sh','insert_output_hold_buffers.tcl','insert_input_hold_buffers.tcl'):
        shutil.copyfile(root/'scripts'/name,driver/name)
    command=['bash',str(driver/'vitis_synth_rtl.sh'),'--stage',stage,'--top',top,
             '--verilog-file',str(rtl),'--part',target.get('part','xcu280-fsvh2892-2L-e'),
             '--clock-period',str(period),'--clock-port',target.get('clock_port','clock'),
             '--build-dir',str(directory),'--metrics-json',str(output),'--vivado-bin',vivado,
             '--jobs','8','--timeout',str(max(1,int(timeout)))]
    if 'output_hold_buffer_stages' in target:
        stages=target['output_hold_buffer_stages']
        if not isinstance(stages,int) or isinstance(stages,bool) or not 1<=stages<=4:raise ValueError('output hold buffer stages must be 1..4')
        command+=['--output-hold-buffer-stages',str(stages)]
    elif target.get('output_hold_buffers'):command+=['--output-hold-buffers']
    if 'input_hold_buffer_stages' in target:
        stages=target['input_hold_buffer_stages']
        if not isinstance(stages,int) or isinstance(stages,bool) or not 1<=stages<=4:raise ValueError('input hold buffer stages must be 1..4')
        command+=['--input-hold-buffer-stages',str(stages)]
    if target.get('io_reference_pin'):command+=['--io-reference-pin',target['io_reference_pin']]
    if target.get('clock_source'):command+=['--clock-source',target['clock_source']]
    for prefix in ('input','output'):
        delays=target.get('io_delays_ns',{})
        low,high=delays.get(prefix+'_min',0),delays.get(prefix+'_max',0)
        if not metric_number(low) or not metric_number(high) or low>high:raise ValueError('invalid I/O delay range')
    for name in ('input_min','input_max','output_min','output_max'):
        value=target.get('io_delays_ns',{}).get(name,0)
        if not metric_number(value):raise ValueError('I/O delays must be finite numbers')
        command+=['--'+name.replace('_','-delay-'),str(value)]
    for directory_path in include_dirs or []:
        command+=['--include-dir',str(directory_path)]
    for source in extra_sources or []:
        command+=['--verilog-file',str(source)]
    inputs=artifact_manifest([rtl, *(extra_sources or []), *(additional_inputs or []), *driver.iterdir()], include_dirs or [])
    process=run(command,root,directory.parent/f'{stage}.log',timeout)
    raw=json.loads(output.read_text()) if output.exists() else {}
    values=raw.get('metrics',{})
    mapped={name:values[key] for name,key in {'lut':'vitis_lut','ff':'vitis_ff','dsp':'vitis_dsp',
            'bram':'vitis_bram_tile','uram':'vitis_uram','wns_ns':'vitis_timing_wns_ns','hold_slack_ns':'vitis_hold_slack_ns'}.items() if key in values}
    if metric_number(metrics.get('latency_cycles')):
        mapped['latency_ns']=metrics['latency_cycles']*period
    if metric_number(metrics.get('transaction_cycles')):
        mapped['transaction_ns']=metrics['transaction_cycles']*period
    ii=metrics.get('initiation_interval_cycles')
    if metric_number(ii) and ii>0:
        mapped['transforms_per_second']=1e9/(period*ii)
    timing_clean=metric_number(mapped.get('wns_ns')) and mapped['wns_ns']>=0
    if stage=='route':
        timing_clean=timing_clean and metric_number(mapped.get('hold_slack_ns')) and mapped['hold_slack_ns']>=0
    result={'passed':process['returncode']==0 and raw.get('passed') is True and timing_clean,
            'implementation_passed':process['returncode']==0 and raw.get('passed') is True,
            'timing_clean':timing_clean,'target':target,'metrics':mapped,'process':process,'reports':raw.get('reports',{})}
    unchanged=inputs==artifact_manifest(inputs['files'], inputs['directories']) and all(v is not None for v in inputs['files'].values())
    if not unchanged:
        result['passed']=False
        result['error']='Implementation inputs missing or changed during measurement'
    artifacts=[output]
    if process.get('log'):
        artifacts.append(Path(process['log']))
    for name, path in result['reports'].items():
        if path and name != 'build_dir':
            artifacts.append(Path(path) if Path(path).is_absolute() else root/path)
    result['integrity']={'version':1, 'inputs_unchanged':unchanged, 'inputs':inputs,
                         'outputs':artifact_manifest(artifacts),
                         'measurement':copy.deepcopy({k:result[k] for k in ('passed','implementation_passed','timing_clean','target','metrics')})}
    return result


def evaluate(rtl: Path, top: str, target: dict, metrics: dict, directory: Path, stage: str,
             timeout: float, extra_sources: list[Path] | None = None, include_dirs: list[Path] | None = None,
             additional_inputs: list[Path] | None = None) -> dict:
    """Serialize vendor jobs across campaigns for this user; queue time uses the budget."""
    start=time.monotonic()
    lock_path=Path(tempfile.gettempdir())/f'ntt-search-vivado-{os.getuid()}.lock'
    with lock_path.open('a') as lock:
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                queued=time.monotonic()-start
                if queued>=timeout:
                    return {'passed':False,'implementation_passed':False,'timing_clean':False,
                            'target':target,'metrics':{},'error':'Vivado queue timeout','queue_seconds':queued}
                time.sleep(min(0.2,max(0,timeout-(time.monotonic()-start))))
        queued=time.monotonic()-start
        result=_evaluate(rtl,top,target,metrics,directory,stage,max(0,timeout-queued),extra_sources,include_dirs,additional_inputs)
        return {**result,'queue_seconds':queued}
