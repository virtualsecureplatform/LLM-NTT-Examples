"""A throughput-improving pipeline must survive synthesis Pareto filtering."""
import tempfile
import unittest
from pathlib import Path
from architecture_search.model import write_json
from architecture_search.search import report

class PipelineFrontier(unittest.TestCase):
    def test_synthesis_retains_latency_throughput_tradeoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);target={'clock_period_ns':4.0}
            for name,latency,throughput,lut in [('compact',3000,300000,5000),('pipeline',3700,450000,9000),('dominated',4000,200000,10000)]:
                record={'id':name,'status':'complete','correct':True,'mode':'functional','configuration':{},'evidence':{'synthesis':{'passed':True,'timing_clean':True,'target':target,'metrics':{'latency_ns':latency,'transforms_per_second':throughput,'lut':lut,'ff':lut,'dsp':10,'bram':4,'uram':0}}}}
                write_json(directory/'candidates'/name/'record.json',record)
            result=report(directory,{'workload':{'kind':'generic'},'target':target})
            self.assertEqual(set(result['frontiers']['synthesis']),{'compact','pipeline'})
