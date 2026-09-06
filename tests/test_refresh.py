"""Automatic recovery must neither require a prompt nor hide stale data."""
import json
import sqlite3
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'daemon'))
from aicredits import store
from aicredits.__main__ import _from_cache
from aicredits.model import Reading, Meter, WINDOW
from aicredits.providers import anthropic


class RecoveryTests(unittest.TestCase):
    def test_expired_claude_login_is_refreshed(self):
        with patch.object(anthropic.secrets, 'get', return_value=None), \
             patch.object(anthropic, '_local_oauth_token', return_value=None), \
             patch.object(anthropic, '_credentials_hollow', return_value=False), \
             patch.object(anthropic, '_refresh_local_login', return_value='renewed') as refresh, \
             patch.object(anthropic, '_oauth_usage', return_value={'five_hour': {'utilization': 42}}) as usage:
            reading = anthropic.Claude().poll({})
        refresh.assert_called_once()
        usage.assert_called_once_with('renewed')
        self.assertEqual(reading.source, 'http')
        self.assertEqual(reading.meters[0].used_pct, 42)

    def test_rejected_token_retries_client_credentials(self):
        with patch.object(anthropic.secrets, 'get', return_value='old'), \
             patch.object(anthropic, '_refresh_local_login', return_value='renewed'), \
             patch.object(anthropic, '_oauth_usage', side_effect=[
                 urllib.error.HTTPError('url', 401, 'expired', {}, None),
                 {'five_hour': {'utilization': 42}}]):
            self.assertEqual(anthropic.Claude().poll({}).source, 'http')

    def test_network_failure_keeps_cache_without_login_loop(self):
        with patch.object(anthropic.secrets, 'get', return_value='valid'), \
             patch.object(anthropic, '_refresh_local_login') as refresh, \
             patch.object(anthropic, '_oauth_usage', side_effect=urllib.error.URLError('offline')), \
             patch.object(anthropic, '_desktop_usage', return_value=([], None)), \
             patch.object(anthropic, '_cached_usage', return_value=([Meter(WINDOW, '5h', 42)], 100)):
            self.assertEqual(anthropic.Claude().poll({}).fetched_at, 100)
        refresh.assert_not_called()

    def test_client_receives_no_model_input(self):
        with patch.object(anthropic.subprocess, 'run') as run, \
             patch.object(anthropic, '_local_oauth_token', return_value='new'):
            self.assertEqual(anthropic._refresh_local_login({}), 'new')
        self.assertEqual(run.call_args.kwargs['input'], '')
        self.assertIn('--safe-mode', run.call_args.args[0])
        self.assertLessEqual(run.call_args.kwargs['timeout'], 30)


class ClaudeFallbackTests(unittest.TestCase):
    def test_desktop_history_maps_five_hour_and_seven_day(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'plan-usage-history.json'
            path.write_text(json.dumps({
                'version': 2,
                'samples': [
                    {'t': 1000, 'u': {'fh': 1, 'sd': 2}},
                    {'t': 1788730983835, 'u': {'fh': 31, 'sd': 13}},
                ],
            }))
            meters, fetched = anthropic._desktop_usage(path)
        self.assertEqual([(m.label, m.used_pct) for m in meters],
                         [('5h', 31.0), ('7d', 13.0)])
        self.assertEqual(fetched, 1788730983)

    def test_expired_claude_code_cache_is_ignored(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text(json.dumps({
                'cachedUsageUtilization': {
                    'fetchedAtMs': 1000,
                    'utilization': {
                        'five_hour': {'utilization': 14, 'resets_at': '2020-01-01T00:00:00Z'},
                        'seven_day': {'utilization': 63, 'resets_at': '2020-01-02T00:00:00Z'},
                    },
                },
            }))
            meters, fetched = anthropic._cached_usage(path)
        self.assertEqual(meters, [])
        self.assertIsNone(fetched)

    def test_poll_uses_desktop_history_when_oauth_file_is_hollow(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            history = Path(root) / 'plan-usage-history.json'
            history.write_text(json.dumps({
                'samples': [{'t': 1788730983000, 'u': {'fh': 31, 'sd': 13}}],
            }))
            with patch.object(anthropic.secrets, 'get', return_value=None), \
                 patch.object(anthropic, '_local_oauth_token', return_value=None), \
                 patch.object(anthropic, '_refresh_local_login', return_value=None), \
                 patch.object(anthropic, '_cached_usage', return_value=([], None)):
                reading = anthropic.Claude().poll({'desktop_history': str(history)})
        self.assertEqual(reading.status, 'ok')
        self.assertEqual(reading.source, 'local-log')
        self.assertEqual([(m.label, m.used_pct) for m in reading.meters],
                         [('5h', 31.0), ('7d', 13.0)])


class RecoveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(store.SCHEMA)
        self.config = {'providers': {'claude': {'enabled': True, 'interval': 900}}}

    def tearDown(self):
        self.conn.close()

    def test_failure_retries_in_two_minutes(self):
        store.record(self.conn, Reading('claude', 'Claude', status='error'), 1000)
        self.assertEqual(store.due_providers(self.conn, self.config, 1119), [])
        self.assertEqual(store.due_providers(self.conn, self.config, 1120), ['claude'])

    def test_reset_retries_before_normal_interval(self):
        store.record(self.conn, Reading('claude', 'Claude', fetched_at=1000,
                     meters=[Meter(WINDOW, '5h', 42, resets_at=1100)]), 1000)
        self.assertEqual(store.due_providers(self.conn, self.config, 1120), ['claude'])
        entry = _from_cache(self.conn, 'claude', {}, None, 1120, {})
        self.assertEqual(entry['status'], 'stale')
        self.assertTrue(entry['meters'][0]['expired'])

    def test_failure_stays_visible_on_non_poll_cycle(self):
        store.record(self.conn, Reading('claude', 'Claude', fetched_at=1000), 1000)
        store.record(self.conn, Reading('claude', 'Claude', status='error', message='offline'), 1100)
        entry = _from_cache(self.conn, 'claude', {}, None, 1110, {})
        self.assertEqual(entry['status'], 'stale')
        self.assertEqual(entry['message'], 'offline')

    def test_older_fallback_does_not_clobber_newer_last_good(self):
        store.record(self.conn, Reading('claude', 'Claude', fetched_at=2000,
                     meters=[Meter(WINDOW, '5h', 10)]), 2000)
        store.record(self.conn, Reading('claude', 'Claude', fetched_at=1000, status='stale',
                     message='last usage reported by Claude Code',
                     meters=[Meter(WINDOW, '5h', 90)]), 3000)
        last_good = json.loads(self.conn.execute(
            "SELECT last_good FROM polls WHERE provider='claude'").fetchone()[0])
        self.assertEqual(last_good['fetched_at'], 2000)
        self.assertEqual(last_good['meters'][0]['used_pct'], 10)


class WindowSparkTests(unittest.TestCase):
    def test_each_window_uses_its_own_history(self):
        from aicredits.__main__ import _enrich
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.executescript(store.SCHEMA)
        self.addCleanup(conn.close)
        for ts, short, weekly in [(1000, 10, 60), (1100, 20, 62)]:
            store.record(conn, Reading('claude', 'Claude', fetched_at=ts, meters=[
                Meter(WINDOW, '5h', short), Meter(WINDOW, '7d', weekly)]), ts)
        entry = {'meters': [{'label': '5h', 'used_pct': 20},
                            {'label': '7d', 'used_pct': 62}]}
        enriched = _enrich(entry, conn, 'claude', 24, 1100)
        self.assertEqual(enriched['meters'][0]['spark'], [10, 20])
        self.assertEqual(enriched['meters'][1]['spark'], [60, 62])


class ClaudePlanTests(unittest.TestCase):
    def test_native_profile_plan_fallback(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            credentials = Path(root) / 'credentials.json'
            profile = Path(root) / 'config.json'
            credentials.write_text('{"claudeAiOauth": {}}')
            profile.write_text('{"oauthAccount": {"organizationType": "claude_pro"}}')
            self.assertEqual(anthropic._local_plan(credentials, profile), 'Pro')
            credentials.write_text('{"claudeAiOauth": {"subscriptionType": "max"}}')
            self.assertEqual(anthropic._local_plan(credentials, profile), 'max')

    def test_unknown_profile_does_not_guess_a_plan(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text('{"oauthAccount": {"organizationType": "unknown"}}')
            self.assertIsNone(anthropic._local_plan(Path(root) / 'missing', path))


class NousPlanTests(unittest.TestCase):
    def test_reads_subscription_plan_not_purchasing_power(self):
        from aicredits.providers.nous import _plan
        self.assertEqual(_plan({'subscription': {'plan': 'Plus', 'tier': 2},
                                'purchasingPower': {'tierName': 'New'}}), 'Plus')
        self.assertIsNone(_plan({'subscription': {'tier': 2},
                                'purchasingPower': {'tierName': 'New'}}))
        self.assertIsNone(_plan({'plan': {'id': 'internal'}}))


class ClaudePercentageTests(unittest.TestCase):
    def test_small_percentages_are_not_treated_as_ratios(self):
        for value in (0, 0.48, 1, 2, 100):
            with self.subTest(value=value):
                for payload in ({'seven_day': {'utilization': value}},
                                {'usage': [{'utilization': value}]}):
                    meters = anthropic._meters_from_oauth(payload)
                    self.assertEqual(meters[0].used_pct, value)

    def test_post_reset_pace_uses_small_percentages(self):
        from aicredits.trend import project
        values = [anthropic._meters_from_oauth({'seven_day': {'utilization': v}})[0].used_pct
                  for v in (0, 1, 2)]
        projection = project(list(zip((0, 3600, 7200), values)), 2, 7200, 86400)
        self.assertEqual(projection['projected_pct'], 24)


class ProviderPercentageUnitsTests(unittest.TestCase):
    def test_small_explicit_percentages_stay_percentages(self):
        from aicredits.providers.alibaba import cli_meters
        from aicredits.providers.zai import quota_meters
        from aicredits.providers.codex import _reading_from_limits
        from aicredits.providers.antigravity import parse_usage
        for value in (0, 0.5, 1, 2, 100):
            with self.subTest(value=value):
                self.assertEqual(cli_meters({'usedPercent': value})[0][0].used_pct, value)
                self.assertEqual(quota_meters({'limits': [{'type': 'CREDIT_LIMIT',
                                                          'percentage': value}]})[0][0].used_pct, value)
                codex = _reading_from_limits({'primary': {'used_percent': value}},
                                            'Codex', None, 1, 'http')
                self.assertEqual(codex.meters[0].used_pct, value)
                self.assertEqual(parse_usage(f'Gemini Models\tWeekly Limit Remaining\t{value}%')[0].used_pct,
                                 100 - value)

    def test_alibaba_ratio_field_has_fixed_units(self):
        from aicredits.providers.alibaba import cli_meters
        for value, expected in ((0, 0), (0.005, 0.5), (0.01, 1), (1, 100), (1.2, 120)):
            self.assertEqual(cli_meters({'per1WeekPercentage': value})[0][0].used_pct, expected)
