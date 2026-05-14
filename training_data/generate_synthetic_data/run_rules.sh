#!/bin/bash

#!/bin/sh

NUM=${1:-1}
RULE_TYPE=${2:-2}
MODEL_CONNECTION_STRING=${3:-http://desktop-1cosh3m.tailc63ae8.ts.net:8080/v1,openai,gemma4:26b-a4b}
VALIDATION_MODEL_CONNECTION_STRING=${4:-http://desktop-1cosh3m.tailc63ae8.ts.net:8080/v1,openai,gemma4:26b-a4b}
VALIDATION_PCT=${5:-1}
BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

$PYTHON $GEN_SYNTH/main.py --rule-$RULE_TYPE $NUM --model $MODEL_CONNECTION_STRING --validation-model $VALIDATION_MODEL_CONNECTION_STRING --validation-pct $VALIDATION_PCT

