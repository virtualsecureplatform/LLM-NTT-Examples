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
                                   '--output-dir',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('NGen build verification failed',result.stderr)
            self.assertFalse(output.exists())
