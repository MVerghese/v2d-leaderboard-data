# Before trusting a push

The aggregator writes atomically and refuses to publish a payload it cannot parse, but two
failure modes are worth checking by eye after the first live run:

1. **Every track is present.** 5 groups today: Track 1, Track 2 tiers 1-3, Track 3. A track
   missing entirely means the aggregator could not read one of its competitions.
2. **`available: false` only where expected.** A competition that does not exist yet reads as
   false. Once a competition is live, false means it stopped answering.

    python3 -c "import json; d=json.load(open('leaderboard.json')); \
      [print(t['short_title'], [m['key'] for m in t['metrics'] if not m['available']]) \
       for t in d['tracks']]"

A stale file is worse than a missing one: the page cannot tell the difference and will show old
standings as current. `generated_at` is the time the standings last changed; the Actions run history shows whether the job is still running.
