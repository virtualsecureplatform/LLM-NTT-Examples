import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from architecture_search import policy
from architecture_search.model import digest

class Calls(unittest.TestCase):
    def test_schema_selects_one_and_preserves_remaining(self):
        configs=[{'pe':1},{'pe':2}];chosen=digest(configs[1])[:16]
        raw={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'order':[chosen]})}}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(policy.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(raw).encode())) as call:
            result=policy.rank(configs,{}, {'model':'test','rank_count':1},Path(tmp))
            self.assertEqual(result,list(reversed(configs)))
            request=json.loads(call.call_args.args[0].data)
            schema=request['response_format']['json_schema']['schema']['properties']['order']
            self.assertEqual(schema['maxItems'],1)
            self.assertEqual(set(schema['items']['enum']),{digest(c)[:16] for c in configs})

    def test_invalid_output_retry_is_bounded_and_audited(self):
        configs=[{'pe':1},{'pe':2}];ids=[digest(c)[:16] for c in configs]
        for invalid in ({'order':[ids[0],ids[0]]},{'order':['unknown',ids[1]]},{'order':[]}, {'order':ids,'extra':1}):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                def response(value):return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}).encode())
                with patch.object(policy.urllib.request,'urlopen',side_effect=[response(invalid),response({'order':ids})]) as call:
                    self.assertEqual(policy.rank(configs,{}, {'model':'test'},Path(tmp)),configs)
                    self.assertEqual(call.call_count,2)
                    audit=json.loads((Path(tmp)/'llm-validation.json').read_text())
                    self.assertTrue(audit['accepted']);self.assertEqual(len(audit['errors']),1)
                    self.assertTrue((Path(tmp)/'llm-response-attempt-2.json').exists())
                with patch.object(policy.urllib.request,'urlopen',side_effect=[response(invalid),response(invalid)]) as call:
                    with self.assertRaisesRegex(ValueError,'after two attempts'):
                        policy.rank(configs,{}, {'model':'test'},Path(tmp))
                    self.assertEqual(call.call_count,2)

    def test_truncation_and_deadline_fail_closed(self):
        raw={'choices':[{'finish_reason':'length','message':{'content':'{"order":[]}'}}]}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(policy.urllib.request,'urlopen',side_effect=[io.BytesIO(json.dumps(raw).encode()) for _ in range(2)]):
                with self.assertRaisesRegex(ValueError,'finish normally'):
                    policy.rank([{'pe':1}],{}, {'model':'test'},Path(tmp))
            with patch.object(policy.urllib.request,'urlopen') as call:
                with self.assertRaises(TimeoutError):policy.rank([{'pe':1}],{}, {'model':'test'},Path(tmp),timeout=0)
                call.assert_not_called()
