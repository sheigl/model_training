#!/bin/sh

NUM=${1:-1}
MODEL=${2:-https://server.tailc63ae8.ts.net:4444/v1,openai,gemma4:31b,$LITELLM_API_KEY}
VALIDATION_MODEL=${3:-https://server.tailc63ae8.ts.net:4444/v1,openai,glm-5.2,$LITELLM_API_KEY}
VALIDATION_PCT=${4:-1}
DRY_RUN=${5:-}

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python

cd $BASE_DIR
FLAGS="--card-search $NUM --model $MODEL --validation-model $VALIDATION_MODEL --validation-pct $VALIDATION_PCT"
[ -n "$DRY_RUN" ] && FLAGS="$FLAGS --dry-run"
$PYTHON -m training_data.generate_synthetic_data.main $FLAGS
