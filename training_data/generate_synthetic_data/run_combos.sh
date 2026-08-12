#!/bin/sh

#./run_combos.sh 1000 https://server.tailc63ae8.ts.net:4444/v1,openai,qwen3.5:9b,sk-1234-dasdasdjkase381312321==2311 https://server.tailc63ae8.ts.net:4444/v1,openai,glm-5.2,sk-1234-dasdasdjkase381312321==2311


NUM=${1:-1}
MODEL=${2:-https://server.tailc63ae8.ts.net:4444/v1,openai,muse:30b,$LITELLM_API_KEY}
VALIDATION_MODEL=${3:-https://server.tailc63ae8.ts.net:4444/v1,openai,deepseek-v4-flash,$LITELLM_API_KEY}
VALIDATION_PCT=${4:-1}
DRY_RUN=${5:-}
OBSERVER_MODEL=${6:-}

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

#nohup ./run_combos.sh 1000 > combos2.log 2>&1 &

cd $BASE_DIR
FLAGS="--combo-queries $NUM --model $MODEL --validation-model $VALIDATION_MODEL --validation-pct $VALIDATION_PCT"
[ -n "$DRY_RUN" ] && FLAGS="$FLAGS --dry-run"
FLAGS="$FLAGS --enable-observer"
[ -n "$OBSERVER_MODEL" ] && FLAGS="$FLAGS --observer-model $OBSERVER_MODEL"
$PYTHON -m training_data.generate_synthetic_data.main $FLAGS
