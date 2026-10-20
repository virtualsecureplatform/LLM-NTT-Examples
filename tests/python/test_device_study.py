import copy
import json
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch

from architecture_search import device,device_evaluate,device_search
from architecture_search.model import artifact_manifest,evidence_integrity,file_hash,write_json
from scripts import device_polynomial_study as study

ROOT=Path(__file__).resolve().parents[2]


def seal(e, files):
    e['integrity']=dict(version=1,inputs_unchanged=True,inputs=artifact_manifest([]),
        outputs=artifact_manifest(files),measurement={k:copy.deepcopy(e[k]) for k in
        ('stage','passed','metrics','target','rtl_sha256','checkpoint')})
    return e


class DeviceStudyTests(unittest.TestCase):
    def setUp(self):self.target=device.load_target(ROOT/'studies/u280-device.json')

    def row(self,name='a',generator='ngen',backend='streamed'):
        return dict(name=name,workload_name='full-full',passed=True,status='screened',quant_bits=0,
            workload=dict(n=16,ring='negacyclic',a_range=[-2147483648,2147483647],
                          b_range=[-128,127],modulus=1<<32),
            configuration=dict(generator=generator,backend=backend,lanes=2,radix=2,
                pe=1,stage_groups=1,reduction='barrett',fractional_bits=30,guard_bits=0),
            rtl_sha256='same',max_abs_error=0,yosys_cells=10,register_bits=20,memory_bits=30,
            multipliers=2,latency_cycles=100,initiation_interval_cycles=50)

    def test_resource_limits_and_byte_aligned_complete_product_traffic(self):
        limits=device.limits(self.target)
        self.assertTrue(device.resources_fit(limits,self.target))
        self.assertFalse(device.resources_fit({**limits,'dsp':limits['dsp']+1},self.target))
        self.assertFalse(device.resources_fit({k:v for k,v in limits.items() if k!='uram'},self.target))
        r=self.row();p=device.performance(r,self.target)
        self.assertEqual(p['bytes_per_product'],16*(4+1+4))
        target={**self.target,'bandwidth_bytes_per_second':144}
        self.assertEqual(device.performance(r,target)['modeled_products_per_second'],1)
        r['workload']['b_range']=[-1,1]
        self.assertEqual(device.performance(r,target)['bytes_per_product'],144)

    def test_parse_all_resources_missing_hold_and_unconstrained_timing(self):
        text='\n'.join(f'| {label} | {i} | 0 | 0 | {100+i} | 1 |' for i,label in enumerate(
            ['CLB LUTs*','CLB Registers','DSPs','Block RAM Tile','URAM']))
        metrics,_=device_evaluate.parse_utilization(text)
        self.assertEqual(metrics['bram36'],3)
        with self.assertRaises(ValueError):device_evaluate.parse_utilization('| CLB LUTs | 1 |')
        checks='\n'.join('checking '+name+' (0)' for name in ('no_clock','unconstrained_internal_endpoints',
            'no_input_delay','no_output_delay','partial_input_delay','partial_output_delay','loops','latch_loops','multiple_clock'))
        timing=checks+'\nWNS(ns) TNS(ns) failing total WHS(ns) THS(ns) failing total WPWS(ns) TPWS(ns) failing total\n--- --- --- --- --- --- --- --- --- --- --- ---\n0.1 0 0 10 0.2 0 0 10 1.4 0 0 10\n'
        m=device_evaluate.parse_timing(timing)
        self.assertTrue(m['fully_constrained']);self.assertEqual(m['hold_slack_ns'],.2)
        self.assertFalse(device_evaluate.parse_timing(timing.replace('no_clock (0)','no_clock (1)'))['fully_constrained'])
        with self.assertRaises(ValueError):device_evaluate.parse_timing('WNS(ns) WPWS(ns)\n--- ---\n0.1 1.4')

    def test_predictions_never_establish_feasibility_and_tampering_is_rejected(self):
        r=self.row()
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'result';f.write_text('original')
            e=dict(stage='routed',target=self.target,rtl_sha256='same',passed=True,checkpoint='test',
                   metrics={**dict.fromkeys(device.RESOURCES,1), 'setup_slack_ns':.1,'hold_slack_ns':.1,
                            'pulse_slack_ns':1,'fully_constrained':True})
            seal(e,[f]);self.assertTrue(device.feasible(r,e,self.target,0))
            mapped=copy.deepcopy(e);mapped['stage']='mapped'
            self.assertFalse(device.feasible(r,mapped,self.target,0))
            broken=copy.deepcopy(e);broken['metrics']['hold_slack_ns']=-.1
            seal(broken,[f]);self.assertFalse(device.feasible(r,broken,self.target,0))
            f.write_text('changed');self.assertFalse(device.feasible(r,e,self.target,0))

    def test_family_models_do_not_train_from_failures_or_other_backend(self):
        a=self.row();b=self.row('b');b['yosys_cells']=20
        e=dict(passed=True,metrics=dict.fromkeys(device.RESOURCES,5))
        predicted=device_search.predict(b,[(a,e)])
        self.assertEqual(predicted['resources']['lut'],10)
        self.assertIsNone(device_search.predict(b,[(a,{**e,'passed':False})])['resources'])
        fft=self.row('fft','sgen','compact')
        self.assertIsNone(device_search.predict(fft,[(a,e)])['resources'])
        choice=device_search.choose([a,b],[],self.target,'random',42,1)[0]
        self.assertEqual(choice,device_search.choose([b,a],[],self.target,'random',42,1)[0])

    def test_real_pool_has_12_calibration_and_six_heldout_points(self):
        # Snapshot is checked in; no ignored evidence directories are required.
        import csv
        rows=[]
        with (ROOT/'docs/results/torus512-points.csv').open() as stream:
            for r in csv.DictReader(stream):
                if r['status']!='screened':continue
                r['configuration']=json.loads(r['configuration_json'])
                for k in ('max_abs_error','quant_bits'):r[k]=int(r[k])
                rows.append(r)
        calibration,heldout=device_search.calibration_split(rows)
        self.assertEqual(len(calibration),12);self.assertEqual(len(heldout),6)
        self.assertFalse(set(calibration)&set(heldout))

    def test_run_resume_trial_accounting_and_exports(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();out=root/'out'
            rows=[self.row('a'),self.row('b'),self.row('c','sgen','compact')]
            for r in rows:
                folder=source/r['name'];folder.mkdir();rtl=folder/'SearchTop.sv';rtl.write_text('test RTL')
                r['rtl_sha256']=file_hash(rtl);r['artifacts']={r['name']+'/SearchTop.sv':file_hash(rtl)}
            write_json(source/'results.json',dict(points=rows))
            write_json(source/'manifest.json',dict(corpora={'full-full':'same'}))
            tool=dict(version='2023.2',binaries={})
            def evaluate(row,rtl,target,tool,vivado,folder,stage,mapped,timeout,threads):
                folder.mkdir(parents=True);cp=folder/'design.dcp';cp.write_text('checkpoint')
                (folder/'constraints.xdc').write_text('constraints')
                e=dict(stage=stage,target=target,tool=tool,rtl_sha256=row['rtl_sha256'],passed=True,
                       checkpoint=str(cp),metrics={**dict.fromkeys(device.RESOURCES,1),
                       'setup_slack_ns':.1,'hold_slack_ns':.1,'pulse_slack_ns':1,'fully_constrained':True})
                seal(e,[cp]);write_json(folder/'evidence.json',e);return e
            args=['--campaign',str(source),'--output-dir',str(out),'--max-trials','3',
                  '--route-budget','1','--max-route-budget','2']
            with patch.object(study.backend,'tool_identity',return_value=tool),patch.object(study.backend,'evaluate',side_effect=evaluate) as call:
                self.assertEqual(study.main(args),0)
                self.assertEqual(call.call_count,4)
                state=json.loads((out/'results.json').read_text())
                self.assertEqual(len(state['mapped']),3);self.assertEqual(len(state['routed']),1)
                self.assertEqual(state['history'][-1]['evaluation_count'],4)
                self.assertTrue(state['feasible']);self.assertTrue(list((out/'exports').glob('*/SearchTop.sv')))
                self.assertEqual(study.main(args+['--resume']),0);self.assertEqual(call.call_count,4)
                cp=out/state['feasible'][0]/'routed/design.dcp';cp.write_text('tampered')
                with self.assertRaises(SystemExit),contextlib.redirect_stderr(io.StringIO()):study.main(args+['--resume'])

    def test_interrupted_attempt_remains_charged_and_cannot_become_feasible(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);r=self.row();rtl=out/'input.sv';rtl.write_text('RTL')
            r['rtl_path']=str(rtl);r['rtl_sha256']=file_hash(rtl)
            state=dict(active=dict(name='a',stage='mapped',phase='calibration'),
                       mapped={},routed={},history=[],elapsed_seconds=0)
            study.recover_active(out,state,{'a':r},self.target,{'version':'2023.2'})
            self.assertIsNone(state['active']);self.assertEqual(len(state['mapped']),1)
            self.assertFalse(state['mapped']['a']['passed'])
            self.assertEqual(state['mapped']['a']['reason'],'interrupted')
            self.assertEqual(evidence_integrity(state['mapped']['a']),'verified')
            self.assertEqual(state['history'][-1]['evaluation_count'],1)


if __name__=='__main__':unittest.main()
