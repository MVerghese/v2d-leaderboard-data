# V2D Challenge leaderboard data

Machine-written data for the leaderboard on the [V2D Challenge page](https://nvidia-isaac.github.io/video_to_data/v2d_challenge/#leaderboard).
The only file that matters to the page is `leaderboard.json`.

It lives in its own repository on purpose.
The challenge site is a hand-authored page that people edit, and a bot pushing a refreshed table into it every fifteen minutes would collide with those edits and make its history unreadable.
Keeping the data here means the site changes only when a human changes it.

## How it updates

`.github/workflows/aggregate.yml` runs every 15 minutes (and on demand from the Actions tab):

1. Installs the `kaggle` client and runs `python aggregator/v2d_aggregate.py --out leaderboard.json --history submission_history.jsonl`.
2. The aggregator downloads every V2D competition leaderboard from Kaggle (23 competitions, one per metric per track entry), joins teams across competitions on their Kaggle usernames, and writes `leaderboard.json`.
3. The aggregator appends changed competition exports to `submission_history.jsonl`. The workflow commits changed standings or history as `github-actions[bot]`. Unchanged runs create no commit.

The aggregator rewrites the file only on a material change, so `generated_at` is the time the standings last changed, not the time of the last check.
The Actions run history shows when it last checked.

A competition that does not exist yet, or cannot be read, does not fail the run.
Its metric is marked `"available": false` and named in that track's `warnings`.

GitHub runs scheduled workflows on a best-effort basis, so a run can start several minutes late or occasionally be skipped.

### The one secret

The workflow reads a Kaggle API token from the repository secret `KAGGLE_API_TOKEN`.
Use a static token from https://www.kaggle.com/settings/api, not the OAuth credential from `kaggle auth login`, which expires.

    gh secret set KAGGLE_API_TOKEN -R MVerghese/v2d-leaderboard-data

Without it each run skips with a warning annotation and commits nothing.

## Observed submission history

`submission_history.jsonl` contains one JSON record for each changed competition export. Each record includes its observation time, track, metric, competition, and the full set of exported rows. Rows retain team IDs, names, member usernames, baseline flags, leaderboard scores and ranks, submission counts, last submission dates, and the scored submission metadata from Kaggle's public team-submissions API.

A new submission count or date is recorded even when the leaderboard score stays the same. Score changes from rescoring, team renames, rank changes, and removed rows are also recorded. Failed downloads preserve previous history; successful empty exports record an empty snapshot. Identical exports create no new record.

This records standings observed by the scheduled job. A leaderboard score is the score shown for that team at observation time; it is not necessarily the score of their most recent attempt. Multiple attempts between runs, unsuccessful attempts, and the scores of attempts that never reach the leaderboard cannot be recovered from these exports. Observation timestamps are separate from Kaggle's last submission dates.

The aggregator also queries the public team-submissions API for each exported team, including baselines. Kaggle operations are spaced two seconds apart, and HTTP 429 responses are retried with a cooldown. `public_submissions` records its submission IDs, exact UTC timestamps, and public scores. When exactly one record matches the exported score and any exported submission ID, these fields identify the scored attempt:

- `leaderboard_submission_id`: Kaggle submission ID.
- `leaderboard_submission_date`: that submission's exact timestamp, including milliseconds.
- `leaderboard_submission_score`: its public score.
- `submission_matches_leaderboard`: `true` when the association is verified.

The team's `last_submission_date` can be later than `leaderboard_submission_date`. A mismatch or ambiguous result leaves the scored attempt unassociated and retains the API records for inspection. An unavailable lookup is represented by `public_submissions: null`; an available lookup with no public submission returns an empty list. Older history remains intact.

Each metric competition has separate submission IDs. Use the stored IDs, timestamps, team usernames, track, and metric to inspect related uploads. Timestamps alone do not prove that uploads contain the same reconstruction or policy, and different metrics may display different attempts. Confirm the submitted files or their provenance before combining scores into one coherent result. A polling gap can still miss submissions that are superseded between runs. Raw-export replay includes these associations when the adjacent `<competition>.submissions.json` file is present.

Read a team's observed scores, for example:

```python
import json

with open("submission_history.jsonl") as history:
    for line in history:
        snapshot = json.loads(line)
        for row in snapshot["rows"]:
            if row["team"] == "Your team name":
                print(snapshot["observed_at"], snapshot["competition"],
                      row["leaderboard_score"], row["leaderboard_submission_id"],
                      row["leaderboard_submission_date"], row["submission_count"])
```

To verify history persistence locally:

```sh
python -m unittest discover -s tests -p "test_aggregate_history.py"
```

## The aggregator copy

`aggregator/` is a generated copy.
The source of truth is the private leaderboard repo `v2d_challenge_leaderboard`:

| here | source |
|---|---|
| `aggregator/v2d_aggregate.py` | `aggregate/v2d_aggregate.py` |
| `aggregator/tracks.json` | `config/tracks.json`, trimmed to titles, metric lists, competition slugs and metric display |

To change which competitions are read, or how they are joined, change the source and re-sync:

    python3 aggregator/resync.py /path/to/v2d_challenge_leaderboard
    git add aggregator && git commit -m "Re-sync aggregator"

`resync.py` documents the three mechanical differences from the source and stops if any of them no longer applies cleanly.
The copy needs only the Python standard library and `kaggle`.

## Who reads it

`docs/v2d_challenge/leaderboard.js` on the challenge page fetches

    https://raw.githubusercontent.com/MVerghese/v2d-leaderboard-data/main/leaderboard.json

on every load and every five minutes while the page is open, with a cache-busting query string.

## Schema

```
{
  "schema": 1,
  "generated_at": "<ISO 8601 UTC>",
  "source": "kaggle",
  "tracks": [
    {
      "key":          "track_2_tier1",
      "title":        "Track 2 - Robotic Grounding (Tier 1: multi-view input)",
      "short_title":  "Track 2 · Tier 1",
      "metrics": [
        {"key": "add_auc", "display": "AUC", "unit": "",
         "higher_is_better": true, "available": true,
         "competition": "v2d-challenge-track2-tier1-auc"}
      ],
      "rows": [
        {"team": "...", "members": ["kaggle_user"], "scores": {"add_auc": 0.91234},
         "submission_count": {"add_auc": 3}, "kaggle_rank": {"add_auc": 1},
         "last_submission": "2026-10-01", "rank": 1, "is_baseline": false}
      ],
      "incomplete": [{"team": "...", "missing": ["mppe_cm"]}],
      "warnings": ["no leaderboard data for: ..."]
    }
  ]
}
```

`available: false` marks a metric whose competition could not be read.
The renderer omits that column.

Scores are whatever Kaggle reported.
A `null` score means that team has not submitted to that leaderboard; the renderer shows a dash and always sorts blanks last.

Each Track 2 tier is a separate set of Kaggle competitions and a separate track here.
The aggregator never merges tiers.

## Baselines

Kaggle benchmark rows have rank `0` in the leaderboard CSV export. The aggregator marks them `is_baseline: true`, joins them by method name, and sets their participant rank to `null`. The website displays a Baseline badge beside the method name. Participant ranks exclude these entries.
