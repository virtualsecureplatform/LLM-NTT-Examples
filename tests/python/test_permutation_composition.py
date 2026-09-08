import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from architecture_search.permutation import compose


class SwitchCompositionTests(unittest.TestCase):
    def network(self, name, total):
        return f'module {name}(input [{total-1}:0] data_in); endmodule'

    def test_preserves_bare_and_namespaced_module_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rtl = root / 'candidate.v'
            names = ['NGenSwitchTransposeNetwork_1', 'HogeFTNGenSwitchTransposeNetwork_5']
            rtl.write_text(self.network(names[0], 128) + '\n' + self.network(names[1], 2048))
            def generate(command, *args):
                self.assertEqual(command[command.index('-hw')+1:command.index('-hw')+3], ['signed', '64'])
                (root / 'sgen-permutation.v').write_text(
                    'module SGenSwitchTransposeNetwork_1_64(); endmodule\n'
                    'module SGenSwitchTransposeNetwork_5_64(); endmodule')
                return {'returncode': 0}
            with patch('architecture_search.permutation.run', side_effect=generate):
                result = compose(rtl, root / 'sgen.bat', root, 60)
            self.assertEqual(result['replaced_modules'], names)
            self.assertEqual(result['lanes'], 32)
            for name in names:
                self.assertIn('module ' + name + '(input clock', rtl.read_text())
            self.assertIn('SGenSwitchTransposeNetwork_5_64 composed', rtl.read_text())

    def test_rejects_incompatible_widths_before_generation_or_mutation(self):
        for totals in [(128, 256), (127, 2048)]:
            with self.subTest(totals=totals), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                rtl = root / 'candidate.v'
                source = self.network('NGenSwitchTransposeNetwork_1', totals[0]) + '\n' + self.network('HogeFTNGenSwitchTransposeNetwork_5', totals[1])
                rtl.write_text(source)
                with patch('architecture_search.permutation.run') as generate:
                    with self.assertRaises(ValueError):
                        compose(rtl, root / 'sgen.bat', root, 60)
                    generate.assert_not_called()
                self.assertEqual(rtl.read_text(), source)


if __name__ == '__main__':
    unittest.main()
