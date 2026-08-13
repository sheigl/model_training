#!/bin/sh

# Example (named args, order-independent):
# ./run_combos.sh --count 1000 --model https://server.tailc63ae8.ts.net:4444/v1,openai,qwen3.5:9b,sk-1234-dasdasdjkase381312321==2311 --validation-model https://server.tailc63ae8.ts.net:4444/v1,openai,glm-5.2,sk-1234-dasdasdjkase381312321==2311
# Legacy count shorthand still works: ./run_combos.sh 1000

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

. "$GEN_SYNTH/run_common.sh"

DEFAULT_MODEL="https://server.tailc63ae8.ts.net:4444/v1,openai,muse:30b,$LITELLM_API_KEY"
DEFAULT_VALIDATION_MODEL="https://server.tailc63ae8.ts.net:4444/v1,openai,deepseek-v4-flash,$LITELLM_API_KEY"

#nohup ./run_combos.sh --count 1000 > combos2.log 2>&1 &

parse_generator_args "$@"

cd $BASE_DIR
FLAGS="--combo-queries $NUM --model $MODEL --validation-model $VALIDATION_MODEL --validation-pct $VALIDATION_PCT"
[ -n "$DRY_RUN" ] && FLAGS="$FLAGS --dry-run"
FLAGS="$FLAGS --enable-observer"
[ -n "$OBSERVER_MODEL" ] && FLAGS="$FLAGS --observer-model $OBSERVER_MODEL"
[ -n "$SHADOW_VALIDATION_MODEL" ] && FLAGS="$FLAGS --shadow-validation-model $SHADOW_VALIDATION_MODEL"
$PYTHON -m training_data.generate_synthetic_data.main $FLAGS
