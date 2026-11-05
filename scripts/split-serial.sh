#!/usr/bin/env bash
# Run the split commands in .opencode/commands/split/ one at a time, each in a
# fresh session, stopping at the first failure.
#
#   MODEL=ollama/deepseek-v4.1-flash:1017-cloud ./scripts/split-serial.sh
#   MODEL=... FROM=8 TO=8 ./scripts/split-serial.sh    # one step only
#   COMMIT=0 ./scripts/split-serial.sh                 # leave commits alone
#
# No --continue and no --session: that is what makes every step a fresh agent.
# The tree must be clean before the loop starts, and every green step is
# committed, so a bad step is one `git revert` away.

set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOGS="$ROOT/.scratch/split"
MODEL=${MODEL:-ollama/deepseek-v4.1-flash:1017-cloud}
FROM=${FROM:-1}
TO=${TO:-99}
COMMIT=${COMMIT:-1}

mkdir -p "$LOGS"
cd "$ROOT" || exit 1

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "== tree is dirty; commit it before starting" >&2
  exit 1
fi

for path in "$ROOT"/.opencode/commands/split/*.md; do
  name=$(basename "$path" .md)
  step=$((10#${name%%-*}))

  [ "$step" -lt "$FROM" ] && continue
  [ "$step" -gt "$TO" ] && continue

  blocked="$LOGS/BLOCKED-$name"
  rm -f "$blocked"

  echo "== $name"
  opencode run -m "$MODEL" --auto --title "split $name" "/split/$name" 2>&1 \
    | tee "$LOGS/$name.log"
  status=${PIPESTATUS[0]}

  if [ -f "$blocked" ]; then
    echo "== $name: blocked, $(cat "$blocked")" >&2
    exit 1
  fi

  if [ "$status" -ne 0 ]; then
    echo "== $name: opencode exited $status, stopping" >&2
    exit 1
  fi

  if ! npm run check >"$LOGS/$name.check" 2>&1; then
    echo "== $name: npm run check failed, see $LOGS/$name.check" >&2
    exit 1
  fi

  git diff --stat >"$LOGS/$name.diff"

  if [ "$COMMIT" = "1" ]; then
    git add -A
    git commit -q -m "split: $name"
  fi
done

echo "== finished"
