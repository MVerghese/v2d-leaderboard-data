"""Verify persistence of observed Kaggle leaderboard states."""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ("aggregator" if (ROOT / "aggregator").exists() else "aggregate") / "v2d_aggregate.py"
spec = importlib.util.spec_from_file_location("history_aggregator", SOURCE)
aggregate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aggregate)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = self.root / "submission_history.jsonl"
        self.row = {"team_id": "123", "team_name": "Alpha", "members": "bob,alice",
                    "rank": "1", "score": "0.8", "submission_count": "2",
                    "submission_date": "2026-10-05 12:00:00", "submission_id": "456"}

    def snapshot(self, rows=None, competition="example"):
        return aggregate.history_snapshot("track_2_tier1", "add_auc", competition,
                                          [self.row] if rows is None else rows)

    def records(self):
        return [json.loads(line) for line in self.history.read_text().splitlines()]

    def record(self, snapshot=None, now="2026-10-05T12:01:00+00:00"):
        return aggregate.record_history(self.history, [snapshot or self.snapshot()], now)

    def test_initial_snapshot_and_submission_fields(self):
        self.assertEqual(self.record(), 1)
        event = self.records()[0]
        row = event["rows"][0]
        self.assertEqual(event["observed_at"], "2026-10-05T12:01:00+00:00")
        self.assertEqual(row["team_id"], 123)
        self.assertEqual(row["leaderboard_submission_id"], 456)
        self.assertEqual(row["leaderboard_score"], 0.8)
        self.assertEqual(row["submission_count"], 2)
        self.assertEqual(row["members"], ["alice", "bob"])

    def test_unchanged_runs_preserve_file_bytes_and_mtime(self):
        self.record()
        before = self.history.read_bytes(), self.history.stat().st_mtime_ns
        self.assertEqual(self.record(now="2026-10-05T13:01:00+00:00"), 0)
        self.assertEqual((self.history.read_bytes(), self.history.stat().st_mtime_ns), before)

    def test_count_and_date_change_with_same_best_score(self):
        self.record()
        prefix = self.history.read_bytes()
        self.row.update(submission_count="3", submission_date="2026-10-05 13:00:00")
        self.assertEqual(self.record(), 1)
        self.assertTrue(self.history.read_bytes().startswith(prefix))
        self.assertEqual([r["rows"][0]["leaderboard_score"] for r in self.records()], [0.8, 0.8])
        self.assertEqual(self.records()[-1]["rows"][0]["submission_count"], 3)

    def test_rescore_rename_and_return_to_previous_score(self):
        self.record()
        self.row.update(score="0.9", team_name="Alpha renamed")
        self.assertEqual(self.record(), 1)
        self.row["score"] = "0.8"
        self.assertEqual(self.record(), 1)
        rows = [r["rows"][0] for r in self.records()]
        self.assertEqual([r["leaderboard_score"] for r in rows], [0.8, 0.9, 0.8])
        self.assertEqual([r["team_id"] for r in rows], [123, 123, 123])
        self.assertEqual(rows[1]["team"], "Alpha renamed")

    def test_row_reordering_is_not_a_change_and_baselines_are_preserved(self):
        baseline = {"team_name": "CHORD Baseline", "rank": "0", "score": "0.5"}
        first = self.snapshot([self.row, baseline])
        self.record(first)
        self.assertEqual(self.record(self.snapshot([baseline, self.row])), 0)
        rows = self.records()[0]["rows"]
        self.assertTrue(next(row for row in rows if row["team"] == "CHORD Baseline")["is_baseline"])

    def test_successful_empty_export_records_removal(self):
        self.record()
        self.assertEqual(self.record(self.snapshot([])), 1)
        self.assertEqual(self.records()[-1]["rows"], [])
        self.assertEqual(self.record(self.snapshot([])), 0)

    def test_unavailable_export_preserves_existing_history(self):
        self.record()
        before = self.history.read_bytes()
        self.assertEqual(aggregate.record_history(self.history, [], "later"), 0)
        self.assertEqual(self.history.read_bytes(), before)

    def test_competitions_and_tiers_stay_separate(self):
        other = self.snapshot(competition="tier2")
        other["track"] = "track_2_tier2"
        self.assertEqual(aggregate.record_history(self.history, [self.snapshot(), other], "now"), 2)
        self.assertEqual({r["track"] for r in self.records()}, {"track_2_tier1", "track_2_tier2"})

    def test_invalid_history_is_never_overwritten(self):
        for invalid in ('not json\n', '{"schema": 2}\n'):
            self.history.write_text(invalid)
            with self.assertRaises(SystemExit):
                self.record()
            self.assertEqual(self.history.read_text(), invalid)

    def test_csv_submission_id_alias(self):
        rows = aggregate.parse_leaderboard_csv("TeamId,TeamName,SubmissionId,Score,Rank\n123,Alpha,456,0.8,1\n")
        self.assertEqual(self.snapshot(rows)["rows"][0]["leaderboard_submission_id"], 456)

    def test_matching_score_uses_scored_attempt_date(self):
        details = {123: [{"id": 456, "submitted_at": "2026-10-04T10:00:00.123Z", "public_score": 0.8}]}
        snapshot = aggregate.history_snapshot("track_2_tier1", "add_auc", "example", [self.row], details)
        self.record(snapshot)
        row = self.records()[0]["rows"][0]
        self.assertEqual(row["leaderboard_submission_id"], 456)
        self.assertEqual(row["leaderboard_submission_date"], "2026-10-04T10:00:00.123Z")
        self.assertEqual(row["leaderboard_submission_score"], 0.8)
        self.assertTrue(row["submission_matches_leaderboard"])
        self.assertNotEqual(row["leaderboard_submission_date"], row["last_submission_date"])

    def test_newer_api_score_is_not_associated_with_older_export(self):
        self.row.pop("submission_id")
        details = {123: [{"id": 789, "submitted_at": "2026-10-05T13:00:00.000Z", "public_score": 0.9}]}
        snapshot = aggregate.history_snapshot("track_2_tier1", "add_auc", "example", [self.row], details)
        row = snapshot["rows"][0]
        self.assertIsNone(row["leaderboard_submission_id"])
        self.assertIsNone(row["leaderboard_submission_date"])
        self.assertIsNone(row["leaderboard_submission_score"])
        self.assertFalse(row["submission_matches_leaderboard"])
        self.assertEqual(row["public_submissions"], details[123])
        self.assertEqual(row["leaderboard_score"], 0.8)

    def test_equal_scores_do_not_override_a_different_exported_id(self):
        details = {123: [{"id": 789, "submitted_at": "2026-10-05T13:00:00.000Z", "public_score": 0.8}]}
        row = aggregate.history_snapshot("track", "metric", "example", [self.row], details)["rows"][0]
        self.assertEqual(row["leaderboard_submission_id"], 456)
        self.assertIsNone(row["leaderboard_submission_date"])
        self.assertFalse(row["submission_matches_leaderboard"])

    def test_multiple_matching_public_submissions_stay_ambiguous(self):
        self.row.pop("submission_id")
        details = {123: [{"id": value, "submitted_at": "2026-10-05T13:00:00.000Z", "public_score": 0.8}
                         for value in (456, 789)]}
        row = aggregate.history_snapshot("track", "metric", "example", [self.row], details)["rows"][0]
        self.assertIsNone(row["leaderboard_submission_id"])
        self.assertFalse(row["submission_matches_leaderboard"])
        self.assertEqual(len(row["public_submissions"]), 2)

    def test_failed_lookup_preserves_export_and_previous_history(self):
        self.record()
        original = self.history.read_bytes()
        self.row.pop("submission_id")
        snapshot = aggregate.history_snapshot("track", "metric", "example", [self.row], {123: None})
        row = snapshot["rows"][0]
        self.assertIsNone(row["public_submissions"])
        self.assertIsNone(row["submission_matches_leaderboard"])
        self.assertEqual(row["leaderboard_score"], 0.8)
        self.record(snapshot)
        self.assertTrue(self.history.read_bytes().startswith(original))

    def test_same_score_with_new_submission_id_is_recorded(self):
        self.row.pop("submission_id")
        def snapshot(submission_id):
            details = {123: [{"id": submission_id, "submitted_at": "2026-10-05T13:00:00.000Z", "public_score": 0.8}]}
            return aggregate.history_snapshot("track", "metric", "example", [self.row], details)
        self.record(snapshot(456))
        self.assertEqual(self.record(snapshot(789)), 1)
        self.assertEqual([r["rows"][0]["leaderboard_submission_id"] for r in self.records()], [456, 789])
        self.assertEqual(self.record(snapshot(789)), 0)

    def test_fetch_keeps_baselines_and_isolates_failed_team(self):
        api = Mock()
        record = Mock()
        record.to_dict.return_value = {"id": 456, "dateSubmitted": "2026-10-04T10:00:00.123Z", "publicScore": "0.8"}
        api.competition_team_submissions.side_effect = [[record], RuntimeError("temporary failure")]
        failed = {**self.row, "team_id": "234"}
        baseline = {**self.row, "rank": "0"}
        with contextlib.redirect_stderr(io.StringIO()), patch.object(aggregate.time, "sleep"):
            details = aggregate.fetch_public_submissions(api, [baseline, self.row, failed], "example")
        self.assertEqual(api.competition_team_submissions.call_count, 2)
        self.assertEqual(details[123], [{"id": 456, "submitted_at": "2026-10-04T10:00:00.123Z", "public_score": 0.8}])
        self.assertIsNone(details[234])

    def test_rate_limit_retries_and_preserves_requested_arguments(self):
        class RateLimitError(Exception):
            response = Mock(status_code=429, headers={"Retry-After": "75"})
        request = Mock(side_effect=[RateLimitError(), "result"])
        with patch.object(aggregate.time, "sleep") as sleep, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(aggregate.kaggle_call(request, 123, quiet=True), "result")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args, (123,))
        self.assertTrue(request.call_args.kwargs["quiet"])
        delays = [call.args[0] for call in sleep.call_args_list]
        self.assertIn(60.0, delays)
        self.assertIn(15.0, delays)
        self.assertTrue(all(delay <= 60 for delay in delays))

    def test_non_rate_limit_error_is_not_retried(self):
        request = Mock(side_effect=RuntimeError("unavailable"))
        with patch.object(aggregate.time, "sleep"), self.assertRaises(RuntimeError):
            aggregate.kaggle_call(request)
        request.assert_called_once()

    def test_history_only_change_is_published_even_when_website_is_unchanged(self):
        config = {"tracks": {"track_2_tier1": {"title": "Track 2", "metrics": ["add_auc"],
                  "competitions": {"add_auc": "example"}}}}
        config_path = self.root / "tracks.json"
        config_path.write_text(json.dumps(config))
        csv = self.root / "example.csv"
        csv.write_text("Rank,TeamId,TeamName,LastSubmissionDate,Score,SubmissionCount\n1,123,Alpha,2026-10-05 12:00:00,0.8,2\n")
        details = {"123": [{"id": 456, "submitted_at": "2026-10-04T10:00:00.123Z", "public_score": 0.8}]}
        (self.root / "example.submissions.json").write_text(json.dumps(details))
        out = self.root / "leaderboard.json"
        argv = ["aggregate", "--out", str(out), "--config", str(config_path), "--from-dir", str(self.root),
                "--history", str(self.history), "--publish", "--now", "2026-10-05T12:01:00+00:00"]
        with patch.object(sys, "argv", argv), patch.object(aggregate, "publish") as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aggregate.main(), 0)
            publish.assert_called_once()
        self.assertEqual(self.records()[0]["rows"][0]["leaderboard_submission_date"], "2026-10-04T10:00:00.123Z")
        original = out.read_bytes()
        csv.write_text(csv.read_text().replace("12:00:00", "13:00:00"))
        with patch.object(sys, "argv", argv), patch.object(aggregate, "publish") as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aggregate.main(), 0)
            self.assertEqual(out.read_bytes(), original)
            publish.assert_called_once()
            self.assertEqual(publish.call_args.args[1], [Path("leaderboard.json"), Path("submission_history.jsonl")])
        self.assertEqual(len(self.records()), 2)
        with patch.object(sys, "argv", argv), patch.object(aggregate, "publish") as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aggregate.main(), 0)
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
