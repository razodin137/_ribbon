#!/usr/bin/env bash
# Run the split commands in .opencode/commands/split/ one at a time, each in a
# fresh session, stopping at the first failure.
#
#   MODEL=ollama/deepseek-v4.1-flash:1017-cloud ./scripts/split-serial.sh
#   MODEL=... FROM=8 TO=8 ./scripts/split-serial.sh    # one step only
#   ONLY=11-state,07-remove,08-shell ./scripts/split-serial.sh   # explicit order
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
ONLY=${ONLY:-}

mkdir -p "$LOGS"
cd "$ROOT" || exit 1

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "== tree is dirty; commit it before starting" >&2
  exit 1
fi

if [ -n "$ONLY" ]; then
  IFS=',' read -r -a files <<<"$ONLY"
  for i in "${!files[@]}"; do
    files[$i]="$ROOT/.opencode/commands/split/${files[$i]}.md"
  done
else
  files=("$ROOT"/.opencode/commands/split/*.md)
fi

for path in "${files[@]}"; do
  name=$(basename "$path" .md)
  step=$((10#${name%%-*}))

  if [ -z "$ONLY" ]; then
    [ "$step" -lt "$FROM" ] && continue
    [ "$step" -gt "$TO" ] && continue
  fi

  if [ ! -f "$path" ]; then
    echo "== $name: no such command" >&2
    exit 1
  fi

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
