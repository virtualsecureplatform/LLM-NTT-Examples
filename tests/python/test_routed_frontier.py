import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from architecture_search import device,wide_products
from architecture_search.model import artifact_manifest,file_hash,write_json
from scripts import extend_timing_frontier as frontier

ROOT=Path(__file__).resolve().parents[2]


class FrontierTests(unittest.TestCase):
    def test_dominance_retains_resource_and_latency_tradeoffs(self):
        def point(name,lut,rate,latency=100):
            return dict(name=name,error_bound=0,lut=lut,ff=10,dsp=10,bram36=10,uram=0,
                        latency_cycles=latency,modeled_products_per_second=rate)
        points=[point('small',10,10),point('fast',20,20),point('dominated',21,19),
                point('equal-small',10,10),point('short-latency',30,8,50)]
        self.assertEqual(set(frontier.nondominated(points)),{'small','fast','equal-small','short-latency'})
        self.assertEqual(frontier.nondominated([]),[])

    def test_endpoint_counts_reject_rounded_negative_zero_and_missing_checks(self):
        report='Setup : 0 Failing Endpoints\nHold : 1 Failing Endpoints, Worst Slack -0.000ns\nPW : 0 Failing Endpoints\n'
        self.assertEqual(frontier.endpoint_counts(report),dict(Setup=0,Hold=1,PW=0))
        self.assertIsNone(frontier.endpoint_counts('Setup : 0 Failing Endpoints'))

    def test_bounded_extension_imports_seed_repairs_and_resumes(self):
        for failures in (False,True):
            with self.subTest(failures=failures),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);target=device.load_target(ROOT/'studies/u280-kernel-harness.json');tool={'version':'2023.2'}
                w=wide_products.workload(512,modulus=1<<32);w.update(a_range=[-2147483648,2147483647],b_range=[-1,1])
                configs=[('pipelined',2,1),('registered',2,1),('registered',2,2),('registered',4,1),('registered',4,2)]
                rows=[]
                for i,(profile,lanes,pe) in enumerate(configs):
                    rtl=root/f'kernel{i}.sv';rtl.write_text(f'kernel {i}')
                    rows.append(dict(name=f'point{i}',passed=True,max_abs_error=0,configuration=dict(product_profile=profile,lanes=lanes,pe=pe),
                        workload=w,workload_name='full-ternary',rtl_path=str(rtl),rtl_sha256=file_hash(rtl),latency_cycles=100+i,
                        initiation_interval_cycles=50-i*5))
                def evaluate(row,rtl,target,tool,vivado,folder,stage,previous,timeout,threads):
                    folder.mkdir(parents=True);i=int(row['name'][-1]);bad=failures and i>0 and stage=='routed' and target['implementation_directive']=='Default'
                    for name in ('TimingHarness.sv','constraints.xdc','design.dcp','utilization.rpt','hierarchical-utilization.rpt','clock-utilization.rpt','drc.rpt'):(folder/name).write_text('test evidence')
                    (folder/'timing.rpt').write_text(f'Setup : {1 if bad else 0} Failing Endpoints\nHold : 0 Failing Endpoints\nPW : 0 Failing Endpoints\n')
                    metrics={k:i+1 for k in device.RESOURCES};metrics.update(setup_slack_ns=-.1 if bad else .1,hold_slack_ns=.1,pulse_slack_ns=1,fully_constrained=True)
                    e=dict(stage=stage,target=target,tool=tool,rtl_sha256=row['rtl_sha256'],passed=True,metrics=metrics,checkpoint=str(folder/'design.dcp'))
                    e['integrity']=dict(version=1,inputs_unchanged=True,inputs=artifact_manifest([rtl]),outputs=artifact_manifest(list(folder.iterdir())),
                        measurement={k:copy.deepcopy(e[k]) for k in ('stage','target','tool','rtl_sha256','passed','metrics','checkpoint')})
                    write_json(folder/'evidence.json',e);return e
                seed=root/'seed';seed.mkdir();attempts=[]
                for stage in ('mapped','routed'):
                    folder=seed/stage;evaluate(rows[0],rows[0]['rtl_path'],target,tool,None,folder,stage,None,0,4)
                    attempts.append(dict(evidence=str(folder/'evidence.json')))
                write_json(seed/'results.json',dict(status='complete',winner=dict(row=rows[0]),attempts=attempts))
                def feasible(row,e,t,error):return e['stage']=='routed' and all(e['metrics'][k]>=0 for k in ('setup_slack_ns','hold_slack_ns','pulse_slack_ns'))
                args=['--campaign',str(root),'--seed-campaign',str(seed),'--output-dir',str(root/'out')]
                with patch.object(frontier,'rows_for_frontier',return_value=(rows,[])),patch.object(frontier.backend,'tool_identity',return_value=tool),patch.object(frontier.backend,'evaluate',side_effect=evaluate) as call,patch.object(frontier.device,'feasible',side_effect=feasible),patch.object(frontier,'verify_clock',return_value=True):
                    self.assertEqual(frontier.main(args),0)
                    self.assertEqual(call.call_count,10 if failures else 8)
                    before=json.loads((root/'out/results.json').read_text())
                    self.assertEqual(before['new_mapped'],4);self.assertEqual(before['new_routed'],6 if failures else 4)
                    self.assertEqual(len(before['feasible']),3 if failures else 5)
                    self.assertEqual(frontier.main(args),0);self.assertEqual(call.call_count,10 if failures else 8)
                    after=json.loads((root/'out/results.json').read_text())
                    self.assertEqual([x['elapsed_seconds'] for x in before['history']],[x['elapsed_seconds'] for x in after['history']])
                    self.assertTrue(after['frontiers']['full-ternary'])


if __name__=='__main__':unittest.main()
