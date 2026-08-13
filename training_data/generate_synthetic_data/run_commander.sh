#!/bin/sh

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

. "$GEN_SYNTH/run_common.sh"

DEFAULT_MODEL="https://server.tailc63ae8.ts.net:4444/v1,openai,gemma4:31b-small,$LITELLM_API_KEY"
DEFAULT_VALIDATION_MODEL="https://server.tailc63ae8.ts.net:4444/v1,openai,deepseek-v4-flash,$LITELLM_API_KEY"

parse_generator_args "$@"

cd $BASE_DIR
FLAGS="--commander $NUM --model $MODEL --validation-model $VALIDATION_MODEL --validation-pct $VALIDATION_PCT"
[ -n "$DRY_RUN" ] && FLAGS="$FLAGS --dry-run"
FLAGS="$FLAGS --enable-observer"
[ -n "$OBSERVER_MODEL" ] && FLAGS="$FLAGS --observer-model $OBSERVER_MODEL"
[ -n "$SHADOW_VALIDATION_MODEL" ] && FLAGS="$FLAGS --shadow-validation-model $SHADOW_VALIDATION_MODEL"
$PYTHON -m training_data.generate_synthetic_data.main $FLAGS
