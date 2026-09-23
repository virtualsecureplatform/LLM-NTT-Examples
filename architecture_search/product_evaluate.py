"""Independent exact-integer product scoreboard and transaction protocol stress."""
from pathlib import Path
import time
from . import products
from .model import run, file_hash, write_json, digest
from .evaluate import parse_metrics


def testbench(w,frames,watchdog, scalar=0):
    n=w['n']; ow=products.output_width(w)
    # The exact v2 corpus is checked in full on pass 0. For N=1024 each
    # split-FFT frame reuses its leaf for dozens of digit products, so the
    # later protocol/reset passes use shorter, still nonempty prefixes.
    bubble_frames,stall_frames=(8,2) if w.get('version')==2 and n>=1024 else (64,8)
    aw=products.input_width(w,'a');bw=products.input_width(w,'b');ob=(products.output_count(w)+1)//2
    ap=w.get('a_range',[0,7])[1]&((1<<aw)-1);bp=w.get('b_range',[0,7])[1]&((1<<bw)-1)
    declarations=loads=checks=resets=''
    if scalar:
        for name,valid,ready,data in [('fa','av','am','fa'),('fb','bv','bm','fb'),('mul','mv','mr','product'),('inv','iv','ir','iv_data')]:
            declarations+=f'reg [{4*scalar-1}:0] model_{name}[0:N*F-1];integer count_{name};\n'
            loads+=f'$readmemh("{name}.mem",model_{name});\n'
            resets+=f'count_{name}=0;'
            checks+=f'if(dut.{valid} && dut.{ready})begin if(count_{name}>=N*F || dut.{data}!==model_{name}[count_{name}])$fatal(1,"bit-model mismatch {name} beat=%0d actual=%h expected=%h",count_{name},dut.{data},model_{name}[count_{name}]);count_{name}=count_{name}+1;end\n'
    return f'''
module test;
localparam N={n},B=N/2,OB={ob},F={frames},OW={ow},WATCHDOG={watchdog};
reg clock=0,reset=1,in_valid=0,out_ready=0;reg [{2*aw-1}:0] a;reg [{2*bw-1}:0] b;
wire in_ready,out_valid;wire [2*OW-1:0] out_data;
reg [{2*aw-1}:0] aa[0:B*F-1];reg [{2*bw-1}:0] bb[0:B*F-1];reg [2*OW-1:0] expected[0:OB*F-1];
reg [2*OW-1:0] held;reg stalled,source_stalled;
integer target_frames,sent,received,cycle,pass,start_cycle,first_output,last_output,max_interval,last_start,loaded,frame,drain,j;
integer starts[0:F-1];
{declarations}
SearchTop dut(clock,reset,in_valid,in_ready,a,b,out_valid,out_ready,out_data);
always #5 clock=~clock;
initial begin
 {loads}
 $readmemh("a.mem",aa);$readmemh("b.mem",bb);$readmemh("expected.mem",expected);
 for(pass=0;pass<4;pass=pass+1)begin
  reset=1;in_valid=0;out_ready=0;repeat(3)@(negedge clock);reset=0;
  target_frames=pass==0?F:(pass==1?{bubble_frames}:{stall_frames});
  {resets}
  sent=0;received=0;stalled=0;source_stalled=0;first_output=-1;last_output=-1;last_start=-1;max_interval=0;loaded=0;
  for(cycle=0;cycle<WATCHDOG && received<OB*target_frames;cycle=cycle+1)begin
   in_valid=sent<B*target_frames && (source_stalled || pass==0 || cycle%11<8);
   out_ready=pass==0 || (cycle%17<9);
   if(sent<B*target_frames)begin a=aa[sent];b=bb[sent];end
   @(posedge clock);
   {checks}
   if(stalled && (!out_valid || out_data!==held))$fatal(1,"unstable stalled output");
   held=out_data;stalled=out_valid && !out_ready;source_stalled=in_valid && !in_ready;
   if(in_valid && in_ready)begin
    if(sent%B==0)begin
     frame=sent/B;starts[frame]=cycle;
     if(frame>=8 && last_start>=0 && cycle-last_start>max_interval)max_interval=cycle-last_start;
     last_start=cycle;
    end
    sent=sent+1;
   end
   if(out_valid && out_ready)begin
    if(received>=OB*target_frames || out_data!==expected[received])$fatal(1,"product mismatch pass=%0d beat=%0d actual=%h expected=%h",pass,received,out_data,expected[received]);
    if(received==0)first_output=cycle;
    if(received==OB-1)last_output=cycle;
    if(received%OB==OB-1 && cycle-starts[received/OB]>loaded)loaded=cycle-starts[received/OB];
    received=received+1;
   end
   @(negedge clock);
  end
  if(received!=OB*target_frames || sent!=B*target_frames)$fatal(1,"watchdog sent=%0d received=%0d",sent,received);
  if(pass==0)begin
   $display("METRIC latency_cycles=%0d",last_output-starts[0]);
   $display("METRIC first_output_latency_cycles=%0d",first_output-starts[0]);
   $display("METRIC max_loaded_latency_cycles=%0d",loaded);
   $display("METRIC initiation_interval_cycles=%0d",max_interval);
   $display("METRIC completed_products=%0d",F);
  end
  in_valid=0;out_ready=1;
  repeat(4*N+64)begin @(posedge clock);if(out_valid)$fatal(1,"extra product output");@(negedge clock);end
  // Reset in capture, with arithmetic active, and while output is stalled.
  if(pass<3)begin
   frame=0;in_valid=1;out_ready=0;a={2*aw}'h{ap|(ap<<aw):x};b={2*bw}'h{bp|(bp<<bw):x};
   for(j=0;j<WATCHDOG && frame<(pass==0?1:B);j=j+1)begin
    @(posedge clock);if(in_ready)frame=frame+1;@(negedge clock);
   end
   in_valid=0;
   if(pass==1)repeat(N)@(negedge clock);
   if(pass==2)begin
    for(j=0;j<WATCHDOG && !out_valid;j=j+1)@(negedge clock);
    if(!out_valid)$fatal(1,"reset priming timeout");
    repeat(7)@(negedge clock);
   end
  end
 end
 $display("PASS polynomial product");$finish;
end
endmodule
'''


def evaluate(w,c,rtl,directory,timeout,simulator='iverilog'):
    started=time.monotonic(); directory=directory.resolve();directory.mkdir(parents=True,exist_ok=True)
    corpus=products.vectors(w); width=products.output_width(w)
    def packed(values,bits):
        if len(values)%2:values=list(values)+[0]
        return ''.join(f'{(values[i]&((1<<bits)-1))|((values[i+1]&((1<<bits)-1))<<bits):x}\n' for i in range(0,len(values),2))
    for name,index in [('a',0),('b',1)]:
        (directory/f'{name}.mem').write_text(''.join(packed(pair[index],products.input_width(w,name)) for pair in corpus))
    from .wide_products import schoolbook as wide_schoolbook
    oracle=(lambda a,b:wide_schoolbook(w,a,b)) if w.get('version')==2 else products.schoolbook
    (directory/'expected.mem').write_text(''.join(packed(oracle(*pair),width) for pair in corpus))
    watchdog=max(100000,len(corpus)*w['n']*w['n'].bit_length()*128)
    scalar=0;model_files=[]
    if c['generator']=='sgen' and w.get('version')==1:
        import json
        from .fft_model import product_intermediates
        meta=json.loads(rtl.with_suffix('.json').read_text())
        scalar=c['integer_bits']+c['fractional_bits'];mask=(1<<scalar)-1
        outputs=[[] for _ in range(4)]
        for a,b in corpus:
            for dest,values in zip(outputs,product_intermediates(a,b,meta['forward'],meta['inverse'])):
                dest.append(packed([(r&mask)|((i&mask)<<scalar) for r,i in values],2*scalar))
        for name,values in zip(('fa','fb','mul','inv'),outputs):
            path=directory/f'{name}.mem';path.write_text(''.join(values));model_files.append(path)
    (directory/'test.sv').write_text(testbench(w,len(corpus),watchdog,scalar))
    files=[rtl,directory/'a.mem',directory/'b.mem',directory/'expected.mem',directory/'test.sv',*model_files]
    hashes={str(p):file_hash(p) for p in files}
    if simulator in ('auto','iverilog'):
        build_cmd=['iverilog','-g2012','-s','test','-o','simulation',str(rtl),'test.sv'];test_cmd=['vvp','simulation']
    elif simulator=='verilator':
        build_cmd=['verilator','--binary','--timing','-CFLAGS','-std=c++20','--top-module','test','-Wno-fatal','-j','4',str(rtl),'test.sv'];test_cmd=[str(directory/'obj_dir/Vtest')]
    else:raise ValueError('unsupported product simulator')
    build=run(build_cmd,directory,directory/'build.log',max(0,timeout-(time.monotonic()-started)))
    test=run(test_cmd,directory,directory/'test.log',max(0,timeout-(time.monotonic()-started))) if build['returncode']==0 else {}
    text=(directory/'test.log').read_text() if (directory/'test.log').exists() else ''
    unchanged=all(file_hash(Path(p))==value for p,value in hashes.items())
    result=dict(correct=unchanged and build['returncode']==0 and test.get('returncode')==0 and 'PASS polynomial product' in text,
                mode='functional',metrics=parse_metrics(text),build=build,test=test,verification=hashes,inputs_unchanged=unchanged,
                oracle='independent-python-integer-schoolbook',corpus_sha256=digest(corpus),random_pairs=64 if w.get('version')==2 else 256,seed=1)
    write_json(directory/'results.json',result)
    return result
