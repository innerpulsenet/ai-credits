"""Parser tests against redacted copies of real CLI output.

Stdlib unittest so it runs with no install:  python3 -m unittest discover -s tests
(pytest collects these too, if you ever add it.)
"""

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))

from aicredits import renewals, trend                            # noqa: E402
from aicredits.model import BALANCE, OK, WINDOW, Meter, Reading  # noqa: E402
from aicredits.providers.base import window_label                # noqa: E402
from aicredits.providers.codex import Codex                      # noqa: E402
from aicredits.providers.grok import Grok                        # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class TestCodex(unittest.TestCase):
    def test_normalizes_live_app_server_response(self):
        from aicredits.providers.codex import _normalize_live_limits, _reading_from_limits
        live = {
            "primary": {"usedPercent": 31, "windowDurationMins": 300,
                        "resetsAt": 1788568869},
            "secondary": {"usedPercent": 22, "windowDurationMins": 10080,
                          "resetsAt": 1788804242},
            "credits": {"hasCredits": False, "unlimited": False, "balance": "0"},
            "planType": "plus",
        }
        reading = _reading_from_limits(
            _normalize_live_limits(live), "Codex", None, 1788557409, "http")
        self.assertIsNotNone(reading)
        self.assertEqual(reading.source, "http")
        self.assertEqual(reading.plan, "plus")
        self.assertEqual([(m.label, m.used_pct) for m in reading.meters],
                         [("5h", 31.0), ("Weekly", 22.0)])

    def test_reads_both_windows(self):
        reading = Codex().poll({"sessions_dir": str(FIXTURES / "codex-sessions")})
        self.assertEqual(reading.status, OK)
        self.assertEqual(reading.plan, "plus")
        meters = {m.label: m for m in reading.meters}
        self.assertEqual(meters["5h"].used_pct, 88.0)
        self.assertEqual(meters["5h"].resets_at, 1788498960)
        self.assertEqual(meters["Weekly"].used_pct, 17.0)
        # timestamp comes from the event itself, not the file's mtime
        self.assertEqual(reading.fetched_at, 1788487477)

    def test_missing_directory_is_an_error_not_a_crash(self):
        reading = Codex().poll({"sessions_dir": "/nonexistent/sessions"})
        self.assertEqual(reading.status, "error")
        self.assertEqual(reading.meters, [])

    def test_wham_payload_maps_session_and_weekly_windows(self):
        from aicredits.providers.codex import _reading_from_wham
        payload = {
            "plan_type": "plus",
            "rate_limit": {
                "primary_window": {"used_percent": 0, "limit_window_seconds": 18000,
                                   "reset_at": 1788735986},
                "secondary_window": {"used_percent": 80, "limit_window_seconds": 604800,
                                     "reset_at": 1788804242},
            },
            "credits": {"has_credits": False, "unlimited": False, "balance": "0"},
        }
        reading = _reading_from_wham(payload, "Codex", None, 1788710000)
        self.assertEqual(reading.status, OK)
        self.assertEqual(reading.plan, "plus")
        self.assertEqual([(m.label, m.used_pct, m.resets_at) for m in reading.meters],
                         [("5h", 0.0, 1788735986), ("Weekly", 80.0, 1788804242)])

    def test_wham_extra_limits_are_optional(self):
        from aicredits.providers.codex import _reading_from_wham
        payload = {
            "rate_limit": {
                "primary_window": {"used_percent": 10, "limit_window_seconds": 18000,
                                   "reset_at": 1},
            },
            "additional_rate_limits": [
                {"limit_id": "codex-spark", "used_percent": 40,
                 "limit_window_seconds": 18000, "reset_at": 2,
                 "name": "Codex Spark 5-hour"},
            ],
        }
        shown = _reading_from_wham(payload, "Codex", None, 1, show_extra=True)
        hidden = _reading_from_wham(payload, "Codex", None, 1, show_extra=False)
        self.assertEqual([m.label for m in shown.meters], ["5h", "Codex Spark 5-hour"])
        self.assertEqual([m.label for m in hidden.meters], ["5h"])

    def test_oauth_token_comes_from_auth_json(self):
        import json
        from aicredits.providers.codex import _oauth_token
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump({"tokens": {"access_token": "tok-1"}}, fh)
        self.assertEqual(_oauth_token(Path(fh.name)), "tok-1")

    def test_poll_prefers_oauth_over_cli(self):
        import json
        from aicredits.providers import codex as codex_mod
        payload = {
            "plan_type": "plus",
            "rate_limit": {
                "primary_window": {"used_percent": 12, "limit_window_seconds": 18000,
                                   "reset_at": 1788735986},
                "secondary_window": {"used_percent": 34, "limit_window_seconds": 604800,
                                     "reset_at": 1788804242},
            },
        }
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump({"tokens": {"access_token": "tok-1"}}, fh)
        class _Resp:
            def read(self):
                return json.dumps(payload).encode()
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        with mock.patch.object(codex_mod.urllib.request, "urlopen", return_value=_Resp()), \
             mock.patch.object(codex_mod, "_app_server_rate_limits", return_value={"should": "not"}):
            reading = Codex().poll({"auth_file": fh.name, "live": True})
        self.assertEqual(reading.status, OK)
        self.assertEqual(reading.source, "http")
        self.assertEqual([m.used_pct for m in reading.meters], [12.0, 34.0])

    def test_cli_source_skips_oauth(self):
        import json
        from aicredits.providers import codex as codex_mod
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump({"tokens": {"access_token": "tok-1"}}, fh)
        with mock.patch.object(codex_mod, "_oauth_usage", side_effect=AssertionError("oauth")), \
             mock.patch.object(codex_mod, "_app_server_rate_limits", return_value=None):
            reading = Codex().poll({"auth_file": fh.name, "live": True, "source": "cli",
                                    "sessions_dir": str(FIXTURES / "codex-sessions")})
        self.assertEqual(reading.status, OK)
        self.assertEqual(reading.source, "local-log")


class TestGrok(unittest.TestCase):
    def test_prefers_fresh_record_from_headless_agent(self):
        record = {
            "ts": "2026-09-04T19:22:26Z",
            "msg": "billing: fetched credits config",
            "ctx": {"subscriptionTier": "SuperGrok", "config": {
                "creditUsagePercent": 27,
                "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                  "end": "2026-09-08T07:38:19Z"},
            }},
        }
        with tempfile.NamedTemporaryFile() as fh, mock.patch(
                "aicredits.providers.grok._refresh_billing_record", return_value=record):
            reading = Grok().poll({"log_path": fh.name, "live": True, "source": "cli"})
        self.assertEqual(reading.status, OK)
        self.assertEqual(reading.meters[0].used_pct, 27.0)
        self.assertEqual(reading.fetched_at, 1788549746)

    def test_reads_weekly_usage_and_tier(self):
        reading = Grok().poll({"log_path": str(FIXTURES / "grok-unified.jsonl")})
        self.assertEqual(reading.status, OK)
        self.assertEqual(reading.plan, "SuperGrok")
        meter = reading.meters[0]
        self.assertEqual((meter.label, meter.used_pct, meter.resets_at),
                         ("Weekly", 20.0, 1788262699))

    def test_missing_log_is_an_error(self):
        self.assertEqual(Grok().poll({"log_path": "/nonexistent.jsonl"}).status, "error")

    def test_skips_unrelated_log_lines(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write('{"ts":"2026-08-31T20:00:00Z","msg":"nothing to see"}\n')
        self.assertEqual(Grok().poll({"log_path": fh.name}).status, "error")

    def test_auth_json_token_prefers_xai_oidc(self):
        import json
        from aicredits.providers.grok import _oauth_token
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump({
                "https://accounts.x.ai/sign-in": {"key": "legacy", "expires_at": "2099-01-01T00:00:00Z"},
                "https://auth.x.ai::abc": {"key": "oidc", "expires_at": "2099-01-01T00:00:00Z"},
            }, fh)
        token, plan = _oauth_token(Path(fh.name), now=1_700_000_000)
        self.assertEqual(token, "oidc")

    def test_expired_auth_json_is_ignored(self):
        import json
        from aicredits.providers.grok import _oauth_token
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump({"https://auth.x.ai::abc": {
                "key": "old", "expires_at": "2020-01-01T00:00:00.123456789Z",
            }}, fh)
        token, _ = _oauth_token(Path(fh.name), now=1_700_000_000)
        self.assertIsNone(token)

    def test_proxy_credits_config_maps_percent_and_reset(self):
        from aicredits.providers.grok import _reading_from_config
        reading = _reading_from_config({
            "creditUsagePercent": 65.0,
            "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                              "end": "2026-09-08T11:38:19.841471+00:00"},
            "prepaidBalance": {"val": 0},
            "onDemandCap": {"val": 0},
        }, "SuperGrok", 1788710000, None)
        self.assertEqual(reading.status, OK)
        self.assertEqual((reading.meters[0].label, reading.meters[0].used_pct),
                         ("Weekly", 65.0))
        self.assertEqual(reading.plan, "SuperGrok")

    def test_poll_http_beats_the_log(self):
        import json
        from aicredits.providers import grok as grok_mod
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as log, \
             tempfile.NamedTemporaryFile("w", delete=False) as auth:
            log.write(json.dumps({
                "ts": "2026-09-04T19:22:26Z", "msg": "billing: fetched credits config",
                "ctx": {"subscriptionTier": "SuperGrok",
                        "config": {"creditUsagePercent": 20,
                                   "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                                     "end": "2026-09-08T07:38:19Z"}}},
            }) + "\n")
            json.dump({"https://auth.x.ai::abc": {
                "key": "tok", "expires_at": "2099-01-01T00:00:00Z",
            }}, auth)
        with mock.patch.object(grok_mod, "_fetch_proxy_billing", return_value=(
                {"creditUsagePercent": 65.0,
                 "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                   "end": "2026-09-08T11:38:19Z"}}, "SuperGrok")):
            reading = Grok().poll({"log_path": log.name, "auth_file": auth.name,
                                   "live": True, "source": "auto"})
        self.assertEqual(reading.meters[0].used_pct, 65.0)
        self.assertEqual(reading.source, "http")


class TestModel(unittest.TestCase):
    def test_window_labels(self):
        for minutes, expected in [(300, "5h"), (10080, "Weekly"), (20160, "2-week"),
                                  (1440, "Daily"), (45, "45m"), (None, "Usage")]:
            self.assertEqual(window_label(minutes), expected, minutes)

    def test_balance_meter_converts_to_percentage(self):
        self.assertEqual(Meter(kind=BALANCE, label="C", remaining=25.0, total=100.0).pct(), 75.0)
        self.assertIsNone(Meter(kind=BALANCE, label="C", remaining=25.0).pct())

    def test_unknown_remaining_is_not_treated_as_fully_consumed(self):
        # A granted-but-unmeasured allowance (ZCode publishes grant_units with
        # no consumption figure) must not read as 100% used.
        self.assertIsNone(Meter(kind=BALANCE, label="Grant", total=3e8).pct())

    def test_expired_window_does_not_drive_the_tray_ring(self):
        reading = Reading(id="x", label="X", meters=[
            Meter(kind=WINDOW, label="5h", used_pct=99.0, expired=True),
            Meter(kind=WINDOW, label="Weekly", used_pct=12.0),
        ])
        self.assertEqual(reading.worst_pct(), 12.0)

    def test_snapshot_names_the_window_driving_the_headline(self):
        reading = Reading(id="x", label="X", meters=[
            Meter(kind=WINDOW, label="5h", used_pct=8.2),
            Meter(kind=WINDOW, label="Weekly", used_pct=95.8),
        ])
        snapshot = reading.to_json()
        self.assertEqual(snapshot["worst_pct"], 95.8)
        self.assertEqual(snapshot["worst_label"], "Weekly")


class TestTrend(unittest.TestCase):
    POINTS = [(0, 10.0), (3600, 25.0), (7200, 40.0)]

    def test_projects_exhaustion_within_the_window(self):
        out = trend.project(self.POINTS, 40.0, 7200, resets_at=7200 + 100_000)
        self.assertEqual(out["exhausts_at"], 21600)
        self.assertEqual(out["projected_pct"], 457)

    def test_projects_pace_when_window_resets_first(self):
        out = trend.project(self.POINTS, 40.0, 7200, resets_at=7200 + 3600)
        self.assertEqual(out["projected_pct"], 55)
        self.assertEqual(out["exhausts_at"], 21600)

    def test_flat_usage_has_no_projection(self):
        flat = [(0, 50.0), (3600, 50.0), (7200, 50.0)]
        self.assertIsNone(trend.project(flat, 50.0, 7200, None))

    def test_cycle_reset_drop_is_handled(self):
        points_with_reset = [(0, 80.0), (1000, 95.0), (2000, 5.0), (3000, 20.0)]
        out = trend.project(points_with_reset, 20.0, 3000, resets_at=3000 + 10_000)
        self.assertIsNotNone(out)
        self.assertIn("exhausts_at", out)


class TestRenewals(unittest.TestCase):
    TODAY = dt.date(2026, 9, 4)

    def test_monthly_anchored_on_the_31st_does_not_drift(self):
        out = renewals.describe(
            {"renewal": {"date": "2026-01-31", "cost_usd": 20, "cadence": "monthly"}}, self.TODAY)
        self.assertEqual(out["date"], "2026-09-30")

    def test_annual_cost_is_amortised_monthly(self):
        out = renewals.describe(
            {"renewal": {"date": "2025-12-15", "cost_usd": 240, "cadence": "annual"}}, self.TODAY)
        self.assertEqual(out["monthly_usd"], 20.0)
        self.assertEqual(out["days_until"], 102)

    def test_no_renewal_configured(self):
        self.assertIsNone(renewals.describe({}, self.TODAY))


if __name__ == "__main__":
    unittest.main()


class TestAlibaba(unittest.TestCase):
    def test_millisecond_timestamps_are_converted(self):
        from aicredits.providers.alibaba import _epoch_seconds
        self.assertEqual(_epoch_seconds({"timestamp": 1788362010523}), 1788362010)
        self.assertEqual(_epoch_seconds({"timestamp": 1788362010}), 1788362010)
        self.assertIsNone(_epoch_seconds({}))

    def test_only_records_inside_the_window_are_counted(self):
        from aicredits.providers.alibaba import tokens_since
        records = [
            {"timestamp": 2_000_000_000_000, "models": {"qwen": {"totalTokens": 10, "requests": 1}}},
            {"timestamp": 1_000_000_000_000, "models": {"qwen": {"totalTokens": 99, "requests": 9}}},
        ]
        self.assertEqual(tokens_since(records, 1_500_000_000), (10, 1))


class TestClaudeAccounting(unittest.TestCase):
    def test_current_oauth_payload_has_named_windows(self):
        from aicredits.providers.anthropic import _meters_from_oauth
        payload = {
            "five_hour": {"utilization": 95, "resets_at": "2026-09-04T23:29:59Z"},
            "seven_day": {"utilization": 0.48, "resets_at": "2026-09-06T16:00:00Z"},
            "extra_usage": {"utilization": None},
        }
        meters = _meters_from_oauth(payload)
        self.assertEqual([m.label for m in meters], ["5h", "7d"])
        self.assertEqual([m.used_pct for m in meters], [95.0, 0.48])
        self.assertIsNotNone(meters[0].resets_at)

    def test_oauth_payload_keeps_model_and_extra_windows(self):
        from aicredits.providers.anthropic import _meters_from_oauth
        payload = {
            "five_hour": {"utilization": 10, "resets_at": "2026-09-04T23:29:59Z"},
            "seven_day": {"utilization": 20, "resets_at": "2026-09-06T16:00:00Z"},
            "seven_day_sonnet": {"utilization": 30, "resets_at": "2026-09-06T16:00:00Z"},
            "seven_day_opus": {"utilization": 40, "resets_at": "2026-09-06T16:00:00Z"},
            "seven_day_routines": {"utilization": 5, "resets_at": "2026-09-05T00:00:00Z"},
            "extra_usage": {"utilization": 12, "resets_at": "2026-10-01T00:00:00Z"},
            "limits": [{"name": "Fable", "weekly_scoped": True, "utilization": 55,
                        "resets_at": "2026-09-06T16:00:00Z"}],
        }
        shown = _meters_from_oauth(payload, show_extra=True)
        hidden = _meters_from_oauth(payload, show_extra=False)
        self.assertEqual([m.label for m in hidden], ["5h", "7d"])
        self.assertEqual([m.label for m in shown],
                         ["5h", "7d", "Sonnet 7d", "Opus 7d", "Routines", "Extra", "Fable"])

    def test_reads_unexpired_local_claude_code_token(self):
        import json
        import tempfile
        from aicredits.providers.anthropic import _local_oauth_token
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump({"claudeAiOauth": {"accessToken": "secret",
                                          "expiresAt": 4102444800000}}, fh)
        self.assertEqual(_local_oauth_token(Path(fh.name)), "secret")

    def test_synthetic_model_is_free_and_not_reported_unpriced(self):
        from aicredits.providers.anthropic import cost_since
        buckets = {"1788480000": {"<synthetic>": [100.0, 100.0, 0.0, 0.0, 0.0]}}
        usd, tokens, unpriced = cost_since(buckets, 0, {})
        self.assertEqual((usd, tokens, unpriced), (0.0, 0, set()))

    def test_known_model_is_priced_with_cache_multipliers(self):
        from aicredits.providers.anthropic import cost_since
        # 1M input, 1M output, 1M cache read, 1M 5m-write, 1M 1h-write on Opus 5
        # = 5 + 25 + 0.5 + 6.25 + 10
        buckets = {"1788480000": {"claude-opus-5": [1e6, 1e6, 1e6, 1e6, 1e6]}}
        usd, tokens, unpriced = cost_since(buckets, 0, {})
        self.assertAlmostEqual(usd, 46.75, places=2)
        self.assertEqual(tokens, 5_000_000)
        self.assertEqual(unpriced, set())

    def test_unknown_model_counts_tokens_but_is_flagged(self):
        from aicredits.providers.anthropic import cost_since
        buckets = {"1788480000": {"some-new-model": [1e6, 0.0, 0.0, 0.0, 0.0]}}
        usd, tokens, unpriced = cost_since(buckets, 0, {})
        self.assertEqual(usd, 0.0)
        self.assertEqual(tokens, 1_000_000)
        self.assertEqual(unpriced, {"some-new-model"})


class TestFormatting(unittest.TestCase):
    def test_spend_total_is_not_described_as_granted(self):
        from aicredits.__main__ import format_meter
        self.assertEqual(
            format_meter({"kind": "spend", "label": "24h", "total": 1500.0, "unit": "tokens"}),
            "24h 1.5k tokens")
        self.assertEqual(
            format_meter({"kind": "balance", "label": "Flash", "total": 3e8, "unit": "token"}),
            "Flash 300.0M token granted")


class TestAlibabaCli(unittest.TestCase):
    """Real payload from `bl usage token-plan --output json`:
    {"per1WeekPercentage": 0.31039925227231, "per1WeekResetTime": 1788966900000}
    Two traps: the "Percentage" field holds a ratio, and the time is in ms."""

    REAL = {"per1WeekPercentage": 0.31039925227231, "per1WeekResetTime": 1788966900000}

    def test_real_payload(self):
        from aicredits.providers.alibaba import cli_meters
        meters, _ = cli_meters(self.REAL)
        self.assertEqual(len(meters), 1)
        self.assertEqual(meters[0].label, "Weekly")
        self.assertEqual(meters[0].used_pct, 31.04)          # ratio -> percent
        self.assertEqual(meters[0].resets_at, 1788966900)    # ms -> s

    def test_ratio_is_not_mistaken_for_a_percentage(self):
        from aicredits.providers.alibaba import cli_meters
        # A full window reads as 100%, not 1%.
        self.assertEqual(cli_meters({"per1WeekPercentage": 1.0})[0][0].used_pct, 100.0)
        # Ratios remain ratios even above the allowance; explicit percent fields stay percentages.
        self.assertEqual(cli_meters({"per1WeekPercentage": 1.2})[0][0].used_pct, 120.0)
        self.assertEqual(cli_meters({"usedPercent": 42.5})[0][0].used_pct, 42.5)

    def test_other_windows_are_labelled_from_the_field_name(self):
        from aicredits.providers.alibaba import cli_meters
        meters, _ = cli_meters({"per5HourPercentage": 0.5, "per1DayPercentage": 0.1})
        self.assertEqual(sorted(m.label for m in meters), ["5h", "Daily"])

    def test_nested_and_alternate_spellings_still_work(self):
        from aicredits.providers.alibaba import cli_meters
        meters, plan = cli_meters(
            {"data": {"planName": "Standard Plan",
                      "quotas": [{"quotaName": "7-Day", "usedPercent": 31.04,
                                  "resetAt": "2026-09-09T15:15:00Z"}]}})
        self.assertEqual(plan, "Standard Plan")
        self.assertEqual((meters[0].label, meters[0].used_pct, meters[0].resets_at),
                         ("7-Day", 31.04, 1788966900))

    def test_payload_without_percentages_yields_nothing(self):
        from aicredits.providers.alibaba import cli_meters
        self.assertEqual(cli_meters({"data": {"status": "active"}})[0], [])


class TestZaiQuota(unittest.TestCase):
    """Verified response from /api/monitor/usage/quota/limit (2026-09-04).

    Traps this payload sets: the type is CREDIT_LIMIT (not TOKENS_LIMIT);
    `usage` is the limit while `currentValue` is the amount consumed; and the
    5-hour entry carries no nextResetTime, so only unit+number can name it.
    """

    NOW = 1788700000
    REAL = {"code": 200, "msg": "Operation successful", "success": True, "data": {
        "level": "lite",
        "limits": [
            {"type": "CREDIT_LIMIT", "unit": 3, "number": 5, "usage": 2000,
             "currentValue": 0, "remaining": 2000, "percentage": 0},
            {"type": "CREDIT_LIMIT", "unit": 6, "number": 1, "usage": 10000,
             "currentValue": 7515, "remaining": 2484, "percentage": 75,
             "nextResetTime": 1788827431997},
        ]}}

    def test_both_windows_are_labelled_from_unit_and_number(self):
        from aicredits.providers.zai import quota_meters
        meters, level = quota_meters(self.REAL, self.NOW)
        self.assertEqual([m.label for m in meters], ["5h", "Weekly"])
        self.assertEqual(level, "lite")

    def test_usage_is_the_limit_and_currentValue_the_consumption(self):
        from aicredits.providers.zai import quota_meters
        weekly = quota_meters(self.REAL, self.NOW)[0][1]
        self.assertEqual(weekly.total, 10000.0)
        self.assertEqual(weekly.remaining, 2484.0)
        self.assertEqual(weekly.used_pct, 75.2)     # 7515/10000, finer than the rounded 75
        self.assertEqual(weekly.unit, "credits")
        self.assertEqual(weekly.resets_at, 1788827431)

    def test_short_window_without_a_reset_time_is_still_named(self):
        from aicredits.providers.zai import quota_meters
        five_hour = quota_meters(self.REAL, self.NOW)[0][0]
        self.assertEqual(five_hour.label, "5h")
        self.assertIsNone(five_hour.resets_at)
        self.assertEqual(five_hour.used_pct, 0.0)

    def test_unknown_unit_falls_back_to_the_reset_horizon(self):
        from aicredits.providers.zai import quota_meters
        payload = {"limits": [{"type": "CREDIT_LIMIT", "unit": 99, "number": 1,
                               "usage": 100, "currentValue": 10,
                               "nextResetTime": (self.NOW + 3 * 3600) * 1000}]}
        self.assertEqual(quota_meters(payload, self.NOW)[0][0].label, "5h")

    def test_unused_mcp_allowance_is_omitted(self):
        from aicredits.providers.zai import quota_meters
        payload = {"limits": [{"type": "TIME_LIMIT", "currentValue": 0, "usage": 1000}]}
        self.assertEqual(quota_meters(payload, self.NOW)[0], [])

    def test_used_mcp_allowance_is_kept(self):
        from aicredits.providers.zai import quota_meters
        payload = {"limits": [{"type": "TIME_LIMIT", "currentValue": 120, "usage": 1000}]}
        meters, _ = quota_meters(payload, self.NOW)
        self.assertEqual((meters[0].label, meters[0].used_pct), ("MCP", 12.0))


class TestAntigravityUsage(unittest.TestCase):
    """Verified output of `agy --print "/usage" --output-format text`.

    The trap: these percentages are REMAINING, the inverse of every other
    provider, so 81% remaining must be stored as 19% used.
    """

    REAL = ("Gemini Models\tWeekly Limit Remaining\t81%\t2026-09-10T23:31:47Z\n"
            "Gemini Models\tFive Hour Limit Remaining\t100%\t2026-09-05T01:16:55Z\n"
            "Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-09-11T20:16:55Z\n"
            "Claude and GPT models\tFive Hour Limit Remaining\t100%\t2026-09-05T01:16:55Z\n")

    def test_remaining_is_inverted_into_used(self):
        from aicredits.providers.antigravity import parse_usage
        meters = parse_usage(self.REAL)
        self.assertEqual(meters[0].used_pct, 19.0)     # 81% left
        self.assertEqual(meters[1].used_pct, 0.0)      # 100% left
        self.assertEqual(meters[0].resets_at, 1789083107)

    def test_group_and_window_names_are_shortened(self):
        from aicredits.providers.antigravity import parse_usage
        self.assertEqual([m.label for m in parse_usage(self.REAL)],
                         ["Gemini Weekly", "Gemini 5h",
                          "Claude/GPT Weekly", "Claude/GPT 5h"])

    def test_rows_without_a_percentage_are_ignored(self):
        from aicredits.providers.antigravity import parse_usage
        noise = "Account:\tuser@example.com\nModels & Quota\n\n"
        self.assertEqual(parse_usage(noise), [])

    def test_fractional_percentages_survive(self):
        from aicredits.providers.antigravity import parse_usage
        meters = parse_usage("Gemini Models\tWeekly Limit Remaining\t80.51%\t2026-09-10T23:31:47Z")
        self.assertEqual(meters[0].used_pct, 19.5)


class TestOpenRouterKey(unittest.TestCase):
    def test_spending_cap_becomes_a_meter(self):
        from aicredits.providers.openrouter import _meters_from_key
        meters = _meters_from_key({"limit": 30, "limit_remaining": 12, "usage": 18})
        self.assertEqual(meters[0].label, "Key cap")
        self.assertEqual(meters[0].used_pct, 60.0)
        self.assertEqual(meters[0].remaining, 12.0)
        self.assertEqual(meters[0].total, 30.0)

    def test_period_spend_is_omitted_when_zero(self):
        from aicredits.providers.openrouter import _meters_from_key
        meters = _meters_from_key({"usage_daily": 0, "usage_weekly": 0, "usage_monthly": 0})
        self.assertEqual(meters, [])

    def test_period_spend_is_kept_when_nonzero(self):
        from aicredits.providers.openrouter import _meters_from_key
        meters = _meters_from_key({"usage_daily": 1.25, "usage_weekly": 4, "usage_monthly": 9.5})
        self.assertEqual([(m.label, m.amount_usd) for m in meters],
                         [("Today", 1.25), ("7d", 4.0), ("30d", 9.5)])

    def test_credits_survive_a_key_api_failure(self):
        from aicredits.providers import openrouter as or_mod
        credits = {"data": {"total_credits": 22.0, "total_usage": 13.45}}
        class _Resp:
            def __init__(self, payload):
                self._payload = json.dumps(payload).encode()
            def read(self):
                return self._payload
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        def fake_urlopen(request, timeout=15):
            if request.full_url.endswith("/credits"):
                return _Resp(credits)
            raise or_mod.urllib.error.URLError("offline")
        with mock.patch.object(or_mod.secrets, "get", return_value="sk-or-v1-test"), \
             mock.patch.object(or_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
            reading = or_mod.OpenRouter().poll({})
        self.assertEqual(reading.status, OK)
        self.assertEqual(reading.meters[0].label, "Credits")
        self.assertAlmostEqual(reading.meters[0].remaining, 8.55, places=2)
