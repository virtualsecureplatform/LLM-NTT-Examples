import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('check_ngen_build',Path(__file__).resolve().parents[2]/'scripts/check_ngen_build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

class BuildIdentity(unittest.TestCase):
    def test_source_changes_additions_and_deletions_require_rebuild(self):
        for change in ('none','source','new','deleted','build','test-only','generated-project'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'src/main').mkdir(parents=True);source=root/'src/main/Main.scala'
                source.write_text('object Main');(root/'build.sbt').write_text('scalaVersion := "3"')
                with zipfile.ZipFile(root/'ngen.bat','w') as jar:
                    jar.writestr(build.RESOURCE,''.join(v+'\t'+k+'\n' for k,v in sorted(build.source_files(root).items())))
                if change=='source':source.write_text('object NewMain')
                if change=='new':(root/'src/main/New.scala').write_text('object New')
                if change=='deleted':source.unlink()
                if change=='build':(root/'build.sbt').write_text('scalaVersion := "4"')
                if change=='test-only':
                    (root/'src/test').mkdir();(root/'src/test/Test.scala').write_text('test')
                if change=='generated-project':
                    (root/'project/target').mkdir(parents=True);(root/'project/target/output.scala').write_text('generated')
                self.assertEqual(build.verify(root)['verified'],change in ('none','test-only','generated-project'))

    def test_missing_manifest_is_not_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(root/'ngen.bat','w') as jar:jar.writestr('old','old')
            self.assertFalse(build.verify(root)['verified'])

    def test_launcher_rejects_unverifiable_binary_before_creating_campaign(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(root/'ngen.bat','w') as jar:jar.writestr('legacy','old')
            output=root/'campaign-output'
            launcher=Path(__file__).resolve().parents[2]/'scripts/search_architectures.py'
            result=subprocess.run([sys.executable,str(launcher),'--mode','run','--ngen-root',str(root),
                                   '--output-dir',str(output),'--campaign',str(root/'unused.json')],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('NGen build verification failed',result.stderr)
            self.assertFalse(output.exists())


    def test_direct_generation_rejects_stale_binary(self):
        from architecture_search.adapters import generate
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'generated'
            with self.assertRaisesRegex(ValueError,'NGen build verification failed'):
                generate({}, {}, root, output, 1)
            self.assertFalse(output.exists())

    def test_direct_generation_checks_inputs_after_execution(self):
        from architecture_search.adapters import generate
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'src/main').mkdir(parents=True)
            source=root/'src/main/Main.scala';source.write_text('original')
            (root/'build.sbt').write_text('build')
            with zipfile.ZipFile(root/'ngen.bat','w') as jar:
                jar.writestr(build.RESOURCE,''.join(v+'\t'+k+'\n' for k,v in sorted(build.source_files(root).items())))
            def change(*args):
                source.write_text('changed during generation')
                return {'returncode':0}
            with patch('architecture_search.adapters.run',side_effect=change):
                with self.assertRaisesRegex(ValueError,'changed during generation'):
                    generate({'kind':'generic','n':16,'q':17,'root':3},
                             {'lanes':2,'pe':1,'radix':2,'backend':'streamed','reduction':'montgomery',
                              'profile':'baseline','transpose':'indexed'},root,root/'generated',1)


    def test_source_identity_handles_uninitialized_submodule(self):
        import subprocess
        from architecture_search.model import source_identity
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL)
            git('init');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','root')
            revision=git('rev-parse','HEAD').decode().strip()
            git('update-index','--add','--cacheinfo','160000,'+revision+',empty-submodule')
            (root/'empty-submodule').mkdir()
            identity=source_identity(root)
            self.assertEqual(identity['revision'],revision)
            self.assertEqual(len(identity['source_hash']),64)
