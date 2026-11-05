#!/usr/bin/env bash
# Run the split commands in .opencode/commands/split/ one at a time, each in a
# fresh session, stopping at the first failure.
#
#   MODEL=ollama/deepseek-v4.1-flash:1017-cloud ./scripts/split-serial.sh
#   MODEL=... FROM=8 TO=8 ./scripts/split-serial.sh    # one step only
#
# No --continue and no --session: that is what makes every step a fresh agent.

set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOGS="$ROOT/.scratch/split"
MODEL=${MODEL:-ollama/deepseek-v4.1-flash:1017-cloud}
FROM=${FROM:-1}
TO=${TO:-99}

mkdir -p "$LOGS"
cd "$ROOT" || exit 1

for path in "$ROOT"/.opencode/commands/split/*.md; do
  name=$(basename "$path" .md)
  step=$((10#${name%%-*}))

  [ "$step" -lt "$FROM" ] && continue
  [ "$step" -gt "$TO" ] && continue

  echo "== $name"
  opencode run -m "$MODEL" --auto --title "split $name" "/split/$name" 2>&1 \
    | tee "$LOGS/$name.log"
  status=${PIPESTATUS[0]}

  if [ "$status" -ne 0 ]; then
    echo "== $name: opencode exited $status, stopping" >&2
    exit 1
  fi

  if ! npm run check >"$LOGS/$name.check" 2>&1; then
    echo "== $name: npm run check failed, see $LOGS/$name.check" >&2
    exit 1
  fi
done

echo "== finished"
