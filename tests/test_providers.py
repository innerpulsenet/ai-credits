"""Parser tests against redacted copies of real CLI output.

Stdlib unittest so it runs with no install:  python3 -m unittest discover -s tests
(pytest collects these too, if you ever add it.)
"""

import datetime as dt
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
            reading = Grok().poll({"log_path": fh.name, "live": True})
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
        self.assertEqual([m.used_pct for m in meters], [95.0, 48.0])
        self.assertIsNotNone(meters[0].resets_at)

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
        # A value above 1 is already a percentage and is left alone.
        self.assertEqual(cli_meters({"per1WeekPercentage": 42.5})[0][0].used_pct, 42.5)

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
