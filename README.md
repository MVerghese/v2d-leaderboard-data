# V2D Challenge leaderboard data

Machine-written. The only meaningful file is `leaderboard.json`, which the challenge page fetches
to render its leaderboard.

It lives in its own repository on purpose. The challenge site is a hand-authored page that people
edit; a bot pushing a refreshed table into it every fifteen minutes would collide with those
edits and make the history unreadable. Keeping the data here means the site changes only when a
human changes it.

## What writes this

`aggregate/v2d_aggregate.py` in the leaderboard repo, on a timer. It downloads every V2D
competition leaderboard from Kaggle, joins them on Kaggle team membership, and writes
`leaderboard.json`. Nothing here is edited by hand.

## Who reads it

`docs/v2d_challenge/leaderboard.js` on https://nvidia-isaac.github.io/video_to_data/v2d_challenge/

The page re-fetches on every load and every five minutes while open. It cache-busts the request,
because GitHub Pages serves `cache-control: max-age=600` and a refresh would otherwise be
invisible for up to ten minutes.

## Schema

```
{
  "generated": "<ISO 8601 UTC>",
  "tracks": [
    {
      "key":          "track_2_tier1",
      "title":        "Track 2 - Robotic Grounding (Tier 1: clean multi-view)",
      "short_title":  "Track 2 · Tier 1",
      "metrics": [
        {"key": "add_auc", "display": "AUC", "unit": "",
         "higher_is_better": true, "available": true,
         "competition": "v2d-challenge-track2-tier1-auc"}
      ],
      "rows": [
        {"team": "...", "members": ["kaggle_user"], "scores": {"add_auc": 0.91234},
         "last_submission": "2026-10-01"}
      ],
      "incomplete": ["teams missing from at least one leaderboard of this track"]
    }
  ]
}
```

`available: false` marks a metric that is promised but has no live competition yet. The renderer
shows the column header and leaves the cells blank rather than hiding it, so a participant can
see what is coming.

Scores are whatever Kaggle reported, to five decimal places. A blank cell means that team has not
submitted to that leaderboard; blanks always sort last, in both directions.

**Tier scores are not comparable across tiers.** Each Track 2 tier supplies a different reference
trajectory, so the same metric on two tiers measures against different targets. This is why they
are separate tracks here rather than one track with a tier column.
