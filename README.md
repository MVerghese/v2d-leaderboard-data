# V2D Challenge leaderboard data

Machine-written data for the leaderboard on the [V2D Challenge page](https://nvidia-isaac.github.io/video_to_data/v2d_challenge/#leaderboard).
The only file that matters to the page is `leaderboard.json`.

It lives in its own repository on purpose.
The challenge site is a hand-authored page that people edit, and a bot pushing a refreshed table into it every fifteen minutes would collide with those edits and make its history unreadable.
Keeping the data here means the site changes only when a human changes it.

## How it updates

`.github/workflows/aggregate.yml` runs every 15 minutes (and on demand from the Actions tab):

1. Installs the `kaggle` client and runs `python aggregator/v2d_aggregate.py --out leaderboard.json`.
2. The aggregator downloads every V2D competition leaderboard from Kaggle (22 competitions, one per metric per track entry), joins teams across competitions on their Kaggle usernames, and writes `leaderboard.json`.
3. If a score or a ranking changed, the workflow commits `leaderboard.json` as `github-actions[bot]` and pushes. Otherwise it commits nothing.

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
         "last_submission": "2026-10-01", "rank": 1}
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
