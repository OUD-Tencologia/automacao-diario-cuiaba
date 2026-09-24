from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import DEFAULT, patch

from automation_api.domain.folhapress import FolhapressDataError
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError
from automation_api.settings import FolhapressConfiguration

spec = spec_from_file_location('validate_folhapress_access_test_target', Path('scripts/validate_folhapress_access.py'))
validator = module_from_spec(spec)
spec.loader.exec_module(validator)


class ValidatorExitCodeTest(unittest.TestCase):
    def setUp(self):
        patches = patch.multiple(validator, get_settings=DEFAULT, FolhapressBrowserSession=DEFAULT,
                                 SourceHealth=DEFAULT, FolhapressAuth=DEFAULT, FolhapressCatalog=DEFAULT,
                                 ArticleExtractor=DEFAULT, TxtDownloader=DEFAULT)
        self.mocks = patches.start()
        self.addCleanup(patches.stop)
        config = FolhapressConfiguration(
            base_url='https://example.test', login_url='https://example.test/login',
            catalog_url='https://example.test/textos', username='synthetic', password='synthetic',
            article_link_selector='a', catalog_query=None, required_catalog_labels=(), page_size=24,
            max_pages_per_cycle=1, navigation_timeout_ms=1000, headless=True,
            login_username_selector=None, login_password_selector=None, login_submit_selector=None,
        )
        self.mocks['get_settings'].return_value.folhapress.return_value = config
        self.mocks['FolhapressCatalog'].return_value.list_articles.return_value = [object()]
        self.mocks['TxtDownloader'].return_value.download.return_value = b'synthetic'
        self.mocks['ArticleExtractor'].return_value.build_draft.return_value.source_id = '101'

    def invoke(self, arguments=None):
        output = StringIO()
        with redirect_stdout(output):
            code = validator.main(arguments or [])
        return code, output.getvalue()

    def test_success_returns_zero_and_keeps_one_page_default(self):
        code, output = self.invoke()
        self.assertEqual(code, 0)
        self.assertIn('folhapress_access=ok', output)
        config = self.mocks['FolhapressBrowserSession'].call_args.args[0]
        self.assertEqual(config.max_pages_per_cycle, 1)

    def test_configuration_failure_returns_two_without_secret(self):
        self.mocks['get_settings'].side_effect = ValueError('PRIVATE_PASSWORD')
        code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertNotIn('PRIVATE_PASSWORD', output)

    def test_download_failure_returns_one_and_its_stage(self):
        self.mocks['TxtDownloader'].return_value.download.side_effect = FolhapressDownloadError('safe', diagnostic_code='download_failed')
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn('stage=download error_code=download_failed', output)

    def test_download_success_draft_failure_is_not_full_success(self):
        self.mocks['ArticleExtractor'].return_value.build_draft.side_effect = FolhapressDataError(
            'safe', diagnostic_code='required_fields_missing', missing_fields=('published_at',)
        )
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn('stage=draft', output)
        self.assertIn('error_code=required_fields_missing', output)
        self.assertIn('missing_fields=published_at', output)
        self.assertIn('date_structure=', output)
        self.assertIn('txt_bytes=9', output)

    def test_empty_catalog_does_not_claim_download_success(self):
        self.mocks['FolhapressCatalog'].return_value.list_articles.return_value = []
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn('empty_catalog', output)

    def test_invalid_page_limit_exits_two(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            validator.main(['--max-pages', '0'])
        self.assertEqual(error.exception.code, 2)
