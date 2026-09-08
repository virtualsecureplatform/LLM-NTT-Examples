"""Vendor implementation stages; target frequency is never treated as achieved automatically."""
from __future__ import annotations
import json
import fcntl
import os
import shutil
import tempfile
import time
from pathlib import Path
from .model import metric_number, run


def _evaluate(rtl: Path, top: str, target: dict, metrics: dict, directory: Path, stage: str,
             timeout: float, extra_sources: list[Path] | None = None, include_dirs: list[Path] | None = None) -> dict:
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
    driver=directory/'driver/scripts'
    driver.mkdir(parents=True,exist_ok=True)
    for name in ('vitis_synth_rtl.sh','insert_output_hold_buffers.tcl'):
        shutil.copyfile(root/'scripts'/name,driver/name)
    command=['bash',str(driver/'vitis_synth_rtl.sh'),'--stage',stage,'--top',top,
             '--verilog-file',str(rtl),'--part',target.get('part','xcu280-fsvh2892-2L-e'),
             '--clock-period',str(period),'--clock-port',target.get('clock_port','clock'),
             '--build-dir',str(directory),'--metrics-json',str(output),'--vivado-bin',vivado,
             '--jobs','8','--timeout',str(max(1,int(timeout)))]
    if target.get('output_hold_buffers'):command+=['--output-hold-buffers']
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
    return {'passed':process['returncode']==0 and raw.get('passed') is True and timing_clean,
            'implementation_passed':process['returncode']==0 and raw.get('passed') is True,
            'timing_clean':timing_clean,'target':target,'metrics':mapped,'process':process,'reports':raw.get('reports',{})}


def evaluate(rtl: Path, top: str, target: dict, metrics: dict, directory: Path, stage: str,
             timeout: float, extra_sources: list[Path] | None = None, include_dirs: list[Path] | None = None) -> dict:
    """Serialize vendor jobs across campaigns for this user; queue time uses the budget."""
    start=time.monotonic()
    lock_path=Path(tempfile.gettempdir())/f'ntt-search-vivado-{os.getuid()}.lock'
    with lock_path.open('a') as lock:
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic()-start>=timeout:
                    return {'passed':False,'implementation_passed':False,'timing_clean':False,
                            'target':target,'metrics':{},'error':'Vivado queue timeout'}
                time.sleep(min(0.2,max(0,timeout-(time.monotonic()-start))))
        queued=time.monotonic()-start
        result=_evaluate(rtl,top,target,metrics,directory,stage,max(0,timeout-queued),extra_sources,include_dirs)
        return {**result,'queue_seconds':queued}
