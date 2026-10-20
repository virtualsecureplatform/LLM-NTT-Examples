import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from architecture_search import timing_harness,device,device_evaluate,wide_products
from architecture_search.model import evidence_integrity,artifact_manifest,write_json
from scripts import find_timing_met as closure

ROOT=Path(__file__).resolve().parents[2]


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.w=wide_products.workload(8,modulus=1<<32)
        self.w.update(a_range=[-2147483648,2147483647],b_range=[-1,1])

    def test_stimulus_matches_workload_and_independent_product(self):
        inputs,outputs=timing_harness.vectors(self.w)
        self.assertEqual(len(inputs),12);self.assertEqual(len(outputs),12)
        a=[];b=[]
        for beat in inputs[:4]:
            for j in range(2):
                v=(beat>>(32*j))&0xffffffff;a.append(v if v<1<<31 else v-(1<<32))
                v=(beat>>(64+2*j))&3;b.append(v if v<2 else v-4)
        self.assertTrue(all(v in (-1,0,1) for v in b))
        gold=wide_products.schoolbook(self.w,a,b)
        self.assertEqual(outputs[:4],[(gold[i]&0xffffffff)|((gold[i+1]&0xffffffff)<<32) for i in range(0,8,2)])
        self.assertEqual(inputs[0]&((1<<64)-1),0x123456789abcdef1)
        self.assertGreater(len(set(inputs)),8)
        invalid=copy.deepcopy(self.w);invalid['b_range']=[-128,127]
        with self.assertRaises(ValueError):timing_harness.emit(invalid)

    def test_context_constraints_and_repair_recipe(self):
        target=device.load_target(ROOT/'studies/u280-kernel-harness.json')
        text=device_evaluate.script(target,Path('kernel.sv'),Path('/tmp/report'),'mapped',harness=Path('harness.sv'))
        self.assertIn('-top TimingHarness',text);self.assertIn('-period 4.0',text)
        self.assertNotIn('set_input_delay',text);self.assertNotIn('set_output_delay',text)
        rtl=timing_harness.emit(self.w)
        self.assertIn('DONT_TOUCH="TRUE"',rtl);self.assertIn('module TimingHarness(input clock);',rtl)
        self.assertIn('REF_NAME =~ BUFG*',text)
        self.assertNotIn('set_false_path',text);self.assertNotIn('set_multicycle_path',text)
        repaired=device_evaluate.script({**target,'implementation_directive':'HoldFix'},Path('k'),Path('/tmp/r'),'routed',Path('routed.dcp'))
        self.assertIn('phys_opt_design -hold_fix',repaired);self.assertNotIn('place_design',repaired)
        explored=device_evaluate.script({**target,'implementation_directive':'ExploreHoldFix'},Path('k'),Path('/tmp/r'),'routed',Path('mapped.dcp'))
        self.assertIn('place_design -directive Explore',explored)

    def test_closure_stops_at_first_pass_and_reuses_sealed_attempts(self):
        for immediate in (True,False):
            with self.subTest(immediate=immediate),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);rtl=root/'kernel.sv';rtl.write_text('test kernel')
                def candidate(_,profile):
                    return dict(name=profile,configuration=dict(product_profile=profile),rtl_path=str(rtl),rtl_sha256='test',
                                workload=self.w,latency_cycles=100,initiation_interval_cycles=50)
                def evaluate(row,rtl,target,tool,vivado,directory,stage,previous,timeout,threads):
                    directory.mkdir(parents=True)
                    for name in ('TimingHarness.sv','constraints.xdc','design.dcp','timing.rpt','utilization.rpt','hierarchical-utilization.rpt','clock-utilization.rpt','harness-checks.rpt','drc.rpt'):
                        (directory/name).write_text('test evidence')
                    m={k:1 for k in device.RESOURCES};m.update(fully_constrained=True,setup_slack_ns=.2,hold_slack_ns=.1,pulse_slack_ns=1)
                    if stage=='routed' and not immediate:
                        if row['name']=='pipelined':m['setup_slack_ns']=-.5
                        elif target['implementation_directive']=='Default':m['hold_slack_ns']=-.02
                    e=dict(stage=stage,target=target,tool=tool,rtl_sha256='test',passed=True,metrics=m,
                           checkpoint=str(directory/'design.dcp'),scope='test',harness_validation={'passed':True})
                    e['integrity']=dict(version=1,inputs_unchanged=True,inputs=artifact_manifest([]),
                        outputs=artifact_manifest(list(directory.iterdir())),measurement={k:e[k] for k in ('stage','target','tool','rtl_sha256','passed','metrics')})
                    write_json(directory/'evidence.json',e);return e
                def feasible(row,e,target,error):
                    return e['stage']=='routed' and min(e['metrics'][k] for k in ('setup_slack_ns','hold_slack_ns','pulse_slack_ns'))>=0
                def verify_clock(checkpoint,vivado,directory):
                    directory.mkdir(parents=True,exist_ok=True)
                    for name in ('clock-routing.rpt','route-status.rpt','evidence.json'):(directory/name).write_text('test clock evidence')
                    return True
                args=['--output-dir',str(root/'out')]
                with patch.object(closure,'candidate',side_effect=candidate),patch.object(closure.backend,'tool_identity',return_value={'version':'2023.2'}),patch.object(closure.backend,'evaluate',side_effect=evaluate) as call,patch.object(closure.device,'feasible',side_effect=feasible),patch.object(closure,'verify_clock',side_effect=verify_clock):
                    self.assertEqual(closure.main(args),0)
                    count=call.call_count;self.assertEqual(count,2 if immediate else 5)
                    self.assertEqual(closure.main(args),0);self.assertEqual(call.call_count,count)
                    if not immediate:
                        self.assertEqual(closure.main(['--output-dir',str(root/'adopted'),'--registered-mapping',
                            str(root/'out/registered/mapped-Default/evidence.json')]),0)
                        self.assertEqual(call.call_count,count+4)
                result=json.loads((root/'out/results.json').read_text())
                self.assertEqual(result['status'],'complete')
                self.assertEqual(result['winner']['name'],'pipelined' if immediate else 'registered')
                self.assertLessEqual(sum(a['stage']=='mapped' for a in result['attempts']),2)
                self.assertLessEqual(sum(a['stage']=='routed' for a in result['attempts']),4)

    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'run inside pinned simulation container')
    def test_real_n512_kernel_and_harness_against_schoolbook(self):
        campaign=ROOT/'build/polynomial-study-512-pipelined-reductions'
        if not (campaign/'results.json').exists():self.skipTest('local qualified kernel is unavailable')
        row=next(p for p in json.loads((campaign/'results.json').read_text())['points'] if p['name']=='full-ternary-2be26723e0be400f')
        with tempfile.TemporaryDirectory() as d:
            e=timing_harness.validate(row,campaign/row['name']/'SearchTop.sv',d)
            self.assertTrue(e['passed']);self.assertEqual(e['frames'],3)
            self.assertEqual(evidence_integrity(e),'verified')
            (Path(d)/'expected.mem').write_text('bad')
            self.assertEqual(evidence_integrity(e),'invalid')


if __name__=='__main__':unittest.main()
