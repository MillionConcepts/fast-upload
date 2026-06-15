#!/bin/bash

# have to be strict here
set -euo pipefail

echo "Task metadata:"
curl -sSf "$ECS_CONTAINER_METADATA_URI_V4/task" | jq -cM .


echo "Launching validation pipeline"
# note: entrypoint.py pulls kwargs from $KWARGBLOB,
# which this script intentionally doesn't know about

exec python -u pipe_entry.py
