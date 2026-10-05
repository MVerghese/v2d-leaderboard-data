"""Verify persistence of observed Kaggle leaderboard states."""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_history_only_change_is_published_even_when_website_is_unchanged(self):
        config = {"tracks": {"track_2_tier1": {"title": "Track 2", "metrics": ["add_auc"],
                  "competitions": {"add_auc": "example"}}}}
        config_path = self.root / "tracks.json"
        config_path.write_text(json.dumps(config))
        csv = self.root / "example.csv"
        csv.write_text("Rank,TeamId,TeamName,LastSubmissionDate,Score,SubmissionCount\n1,123,Alpha,2026-10-05 12:00:00,0.8,2\n")
        out = self.root / "leaderboard.json"
        argv = ["aggregate", "--out", str(out), "--config", str(config_path), "--from-dir", str(self.root),
                "--history", str(self.history), "--publish", "--now", "2026-10-05T12:01:00+00:00"]
        with patch.object(sys, "argv", argv), patch.object(aggregate, "publish") as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aggregate.main(), 0)
            publish.assert_called_once()
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
