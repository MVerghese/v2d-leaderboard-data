#!/usr/bin/env bash
# Create the leaderboard data repo and push it. Run once, after the token is SSO-authorized
# for nvidia-isaac (github.com/settings/tokens -> Configure SSO -> Authorize).
set -euo pipefail

ORG=${ORG:-nvidia-isaac}
NAME=${NAME:-video_to_data_leaderboard}
TOKEN=$(tr -d '\n' < ~/.credentials/github_access_token.txt)

echo "creating ${ORG}/${NAME} ..."
code=$(curl -s -o /tmp/mkrepo.json -w '%{http_code}' -X POST \
  -H "Authorization: Bearer ${TOKEN}" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/orgs/${ORG}/repos" \
  -d "{\"name\":\"${NAME}\",\"description\":\"Leaderboard data for the V2D Challenge page. Machine-written; see README.\",\"private\":false,\"has_issues\":false,\"has_wiki\":false,\"has_projects\":false,\"auto_init\":false}")

if [ "$code" != "201" ]; then
  echo "create failed (HTTP $code):"; cat /tmp/mkrepo.json; exit 1
fi
echo "created."

git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${ORG}/${NAME}.git"
git push -u origin main

echo
echo "now enable Pages:  Settings > Pages > Deploy from branch: main / (root)"
echo "then verify:       curl -sI https://${ORG}.github.io/${NAME}/leaderboard.json | head -1"
