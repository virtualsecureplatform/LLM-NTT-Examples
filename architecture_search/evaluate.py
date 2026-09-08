"""Cycle-accurate independent ready/valid NTT checks."""
from __future__ import annotations
import json
from pathlib import Path
import re
from . import oracle
from .model import run, write_json


def parse_metrics(text: str) -> dict:
    result = {}
    for name, value in re.findall(r'^METRIC ([A-Za-z0-9_]+)=([^\s]+)', text, re.M):
        try:
            result[name] = int(value)
        except ValueError:
            try:
                result[name] = float(value)
            except ValueError:
                pass
    return result


def generic_testbench(workload: dict, lanes: int, frames: int, watchdog: int) -> str:
    n, width = int(workload['n']), int(workload['q']).bit_length()
    declarations = '\n'.join(f'reg [{width-1}:0] i{l}; wire [{width-1}:0] o{l};' for l in range(lanes))
    connections = ','.join(f'.i{l}(i{l}),.o{l}(o{l})' for l in range(lanes))
    drive = '\n'.join(f'i{l} = inputs[sent*LANES+{l}];' for l in range(lanes))
    checks = '\n'.join(f'if(o{l} !== expected[received*LANES+{l}]) $fatal(1,"data mismatch beat=%0d lane={l} got=%0d expected=%0d",received,o{l},expected[received*LANES+{l}]);' for l in range(lanes))
    stable_checks = '\n'.join(f'if (stalled && o{l} !== held[{l}]) $fatal(1,"output changed under backpressure lane={l}"); held[{l}]=o{l};' for l in range(lanes))
    # All handshakes sampled before the edge's nonblocking assignments, as a receiving register would.
    return f'''module test;
localparam N={n}, LANES={lanes}, BEATS=N/LANES, FRAMES={frames};
reg clock=0, reset=1, in_valid=0, out_ready=0;
wire in_ready,out_valid;
{declarations}
reg [{width-1}:0] inputs[0:N*FRAMES-1], expected[0:N*FRAMES-1];
integer sent,received,cycle,pass,drain,first_cycle,last_frame,max_interval,max_latency,frame;
integer starts[0:FRAMES-1];
reg accepting,producing,stalled,source_stalled;
reg [{width-1}:0] held[0:LANES-1];
SearchTop dut(.clock(clock),.reset(reset),.in_valid(in_valid),.in_ready(in_ready),.out_valid(out_valid),.out_ready(out_ready),{connections});
always #5 clock=~clock;
initial begin
 $readmemh("inputs.mem",inputs); $readmemh("expected.mem",expected);
 for(pass=0;pass<3;pass=pass+1) begin
  reset=1; in_valid=0; out_ready=0;
  repeat(3) @(negedge clock);
  reset=0; stalled=0; source_stalled=0; sent=0; received=0; first_cycle=-1; last_frame=-1; max_interval=0; max_latency=0;
  for(cycle=0;cycle<{watchdog} && received<BEATS*FRAMES;cycle=cycle+1) begin
   // Pass zero measures sustained traffic. Pass one adds source and sink stalls.
   in_valid=sent<BEATS*FRAMES && (source_stalled || pass==0 || cycle%11!=4);
   out_ready=pass==0 || cycle%7!=3;
   if(sent<BEATS*FRAMES) begin {drive} end
   @(posedge clock);
   accepting=in_valid && in_ready; producing=out_valid && out_ready;
   if(stalled && !out_valid) $fatal(1,"valid dropped under backpressure");
   {stable_checks}
   stalled=out_valid && !out_ready; source_stalled=in_valid && !in_ready;
   if(accepting) begin
    if(sent%BEATS==0) begin
     starts[sent/BEATS]=cycle;
     if(last_frame>=0 && cycle-last_frame>max_interval) max_interval=cycle-last_frame;
     last_frame=cycle;
    end
    sent=sent+1;
   end
   if(producing) begin
    if(received>=sent) $fatal(1,"output before corresponding input");
    {checks}
    if(received%BEATS==0) begin
     if(first_cycle<0) first_cycle=cycle;
     if(cycle-starts[received/BEATS]>max_latency) max_latency=cycle-starts[received/BEATS];
    end
    received=received+1;
   end
   @(negedge clock);
  end
  if(received!=BEATS*FRAMES || sent!=BEATS*FRAMES) $fatal(1,"timeout sent=%0d received=%0d",sent,received);
  if(pass==0) begin
   $display("METRIC latency_cycles=%0d",first_cycle-starts[0]);
   $display("METRIC max_loaded_latency_cycles=%0d",max_latency);
   $display("METRIC initiation_interval_cycles=%0d",max_interval);
   $display("METRIC completed_frames=%0d",FRAMES);
   $display("METRIC elapsed_cycles=%0d",cycle);
  end
  in_valid=0;out_ready=1;
  repeat(2*N+32) begin @(posedge clock); if(out_valid) $fatal(1,"extra output"); @(negedge clock); end
  // Reset once during capture and once after a complete frame enters computation.
  if(pass<2) begin
   in_valid=1;out_ready=0;frame=0;
   for(drain=0;drain<{watchdog} && frame<(pass==0?2:BEATS);drain=drain+1) begin
    @(posedge clock);if(in_ready)frame=frame+1;@(negedge clock);
   end
   if(frame!=(pass==0?2:BEATS)) $fatal(1,"reset priming timeout");
   in_valid=0;repeat(4) @(negedge clock);
  end
 end
 $display("PASS generic NTT"); $finish;
end
endmodule
'''


def evaluate_generic(workload: dict, config: dict, rtl: Path, directory: Path, timeout: float) -> dict:
    oracle.validate(workload)
    directory.mkdir(parents=True, exist_ok=True)
    corpus = oracle.vectors(workload)
    for name, data in [('inputs', corpus), ('expected', [oracle.transform(v, workload) for v in corpus])]:
        (directory / f'{name}.mem').write_text(''.join(f'{v:x}\n' for frame in data for v in frame))
    watchdog = int(workload.get('watchdog_cycles', max(10000, int(workload['n']) * int(workload['n']).bit_length() * 64)))
    (directory / 'test.sv').write_text(generic_testbench(workload, config['lanes'], len(corpus), watchdog))
    build = run(['iverilog', '-g2012', '-s', 'test', '-o', 'simulation', str(rtl), 'test.sv'], directory, directory/'build.log', timeout)
    test = run(['vvp', 'simulation'], directory, directory/'test.log', timeout-build['seconds']) if build['returncode']==0 else {}
    text = (directory/'test.log').read_text() if (directory/'test.log').exists() else ''
    result = {'correct': build['returncode']==0 and test.get('returncode')==0 and 'PASS generic NTT' in text,
              'mode': 'functional', 'metrics': parse_metrics(text), 'build': build, 'test': test}
    write_json(directory/'results.json', result)
    return result
