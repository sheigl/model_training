#!/bin/sh

#./run_combos.sh 1000 https://server.tailc63ae8.ts.net:4444/v1,openai,qwen3.5:9b,sk-1234-dasdasdjkase381312321==2311 https://server.tailc63ae8.ts.net:4444/v1,openai,glm-5.1,sk-1234-dasdasdjkase381312321==2311


NUM=${1:-1}
MODEL=${2:-https://server.tailc63ae8.ts.net:4444/v1,openai,gemma4:31b,$LITELLM_API_KEY}
VALIDATION_MODEL=${3:-https://server.tailc63ae8.ts.net:4444/v1,openai,glm-5.2,$LITELLM_API_KEY}
VALIDATION_PCT=${4:-1}

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

#nohup ./run_combos.sh 1000 > combos2.log 2>&1 &

cd $BASE_DIR
$PYTHON -m training_data.generate_synthetic_data.main --combo-queries $NUM --model $MODEL --validation-model $VALIDATION_MODEL --validation-pct $VALIDATION_PCT

