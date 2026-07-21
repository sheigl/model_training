#!/bin/sh

NUM=${1:-1}
MODEL=${2:-https://server.tailc63ae8.ts.net:4444/v1,openai,gemma4:12b,$LITELLM_API_KEY}
VALIDATION_MODEL=${3:-https://server.tailc63ae8.ts.net:4444/v1,openai,qwen3.6:27b,$LITELLM_API_KEY}
VALIDATION_PCT=${4:-1}
DRY_RUN=${5:-}

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python

cd $BASE_DIR
FLAGS="--reverse-lookup $NUM --model $MODEL --validation-model $VALIDATION_MODEL --validation-pct $VALIDATION_PCT"
[ -n "$DRY_RUN" ] && FLAGS="$FLAGS --dry-run"
$PYTHON -m training_data.generate_synthetic_data.main $FLAGS
