import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from quality_pipeline import replace_assessment

class AssessmentWriteTests(unittest.TestCase):
    def test_transient_reader_lock_retries_and_publishes_complete_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'ours.tmp';dest=Path(tmp)/'auto-assessment.json'
            source.write_text('{"new":true}');dest.write_text('{"old":true}')
            original=Path.replace;attempts=[]
            def replace(path,target):
                attempts.append(1)
                if len(attempts)<3:raise PermissionError('simulated Windows reader lock')
                return original(path,target)
            with patch.object(Path,'replace',replace),patch('quality_pipeline.time.sleep'):
                replace_assessment(source,dest)
            self.assertEqual(dest.read_text(),'{"new":true}');self.assertFalse(source.exists())

    def test_persistent_denial_is_reported_without_destroying_previous_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'ours.tmp';dest=Path(tmp)/'auto-assessment.json'
            source.write_text('new');dest.write_text('old')
            with patch.object(Path,'replace',side_effect=PermissionError('denied')),patch('quality_pipeline.time.sleep'):
                with self.assertRaises(PermissionError):replace_assessment(source,dest)
            self.assertEqual(dest.read_text(),'old');self.assertFalse(source.exists())

if __name__=='__main__':unittest.main()
