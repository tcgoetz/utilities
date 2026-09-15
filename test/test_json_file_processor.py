"""Test JSON processing and its instance-scoped progress modes."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from idbutils import JsonFileProcessor


class RecordingProcessor(JsonFileProcessor):
    """Process small fixtures without opening a database."""

    conversions = {'updates': int}

    def _process_json(self, data):
        if data.get('fail'):
            raise ValueError('invalid data')
        return data['updates']


class TestJsonFileProcessor(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def write_file(self, name, data):
        path = Path(self.directory.name, name)
        path.write_text(json.dumps(data), encoding='utf-8')
        return str(path)

    def processor(self, **kwargs):
        return RecordingProcessor(r'.*\.json', input_dir=self.directory.name, latest=False, **kwargs)

    def test_existing_positional_arguments_and_default_bar(self):
        filename = self.write_file('valid.json', {'updates': '2'})
        processor = RecordingProcessor(r'.*\.json', filename, None, False, 3, True)
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            processor.process()
        self.assertEqual(processor.debug, 3)
        self.assertFalse(processor.simple_output)
        self.assertEqual(processor.total_updates, 2)
        self.assertIn('\r', output.getvalue())
        self.assertNotIn('files visited', output.getvalue())

    def test_simple_output_is_flushed_and_does_not_use_tqdm(self):
        self.write_file('valid.json', {'updates': '7'})
        processor = self.processor(simple_output=True)
        output = io.StringIO()
        stream = Mock(wraps=output)
        with patch('idbutils.json_file_processor.tqdm', side_effect=AssertionError('unexpected progress bar')), \
                contextlib.redirect_stderr(stream):
            processor.process()
        self.assertEqual(output.getvalue(), 'Processing JSON files\nProcessing JSON files: 1 file visited\n')
        self.assertEqual(stream.flush.call_count, 2)
        self.assertEqual(processor.total_updates, 7)

    def test_empty_input(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.processor(simple_output=True).process()
        self.assertEqual(output.getvalue(), 'Processing JSON files\nProcessing JSON files: 0 files visited\n')

    def test_errors_and_updates_are_preserved_in_both_modes(self):
        malformed = Path(self.directory.name, 'malformed.json')
        malformed.write_text('{', encoding='utf-8')
        files = [str(malformed), self.write_file('failure.json', {'fail': True}),
                 self.write_file('empty.json', {'updates': 0}), self.write_file('valid.json', {'updates': '5'})]
        for simple_output in (False, True):
            with self.subTest(simple_output=simple_output):
                processor = self.processor(simple_output=simple_output)
                processor.file_names = files
                output = io.StringIO()
                with self.assertLogs(level='INFO') as logs, contextlib.redirect_stderr(output):
                    processor.process()
                self.assertEqual(processor.total_updates, 5)
                self.assertEqual(sum('Failed to parse' in line for line in logs.output), 2)
                self.assertTrue(any('No data saved' in line for line in logs.output))
                if simple_output:
                    self.assertEqual(output.getvalue(), 'Processing JSON files\nProcessing JSON files: 4 files visited\n')

    def test_interruptions_do_not_print_completion(self):
        self.write_file('valid.json', {'updates': 1})
        for exception in (KeyboardInterrupt, SystemExit):
            with self.subTest(exception=exception):
                processor = self.processor(simple_output=True)
                output = io.StringIO()
                with patch.object(processor, '_process_json', side_effect=exception), \
                        contextlib.redirect_stderr(output), self.assertRaises(exception):
                    processor.process()
                self.assertEqual(output.getvalue(), 'Processing JSON files\n')

    def test_escaping_iteration_failure_does_not_print_completion(self):
        class BrokenFiles(list):
            def __iter__(self):
                raise RuntimeError('cannot read file list')

        processor = self.processor(simple_output=True)
        processor.file_names = BrokenFiles()
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(RuntimeError):
            processor.process()
        self.assertEqual(output.getvalue(), 'Processing JSON files\n')

    def test_progress_options_belong_to_each_instance(self):
        self.write_file('valid.json', {'updates': 1})
        simple = self.processor(simple_output=True)
        normal = self.processor()
        for processor in (simple, normal, simple):
            with contextlib.redirect_stderr(io.StringIO()), \
                    patch('idbutils.json_file_processor.tqdm', side_effect=lambda files, **kwargs: files) as bar:
                processor.process()
            self.assertEqual(bar.call_count, 0 if processor.simple_output else 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
