#!/bin/bash

#!/bin/sh

NUM=${1:-1}
RULE_TYPE=${2:-2}

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

$PYTHON $GEN_SYNTH/main.py --rule-$RULE_TYPE $NUM --model http://desktop-1cosh3m.tailc63ae8.ts.net:8080/v1,openai,gemma4:26b-a4b --validation-model http://desktop-1cosh3m.tailc63ae8.ts.net:8080/v1,openai,gemma4:26b-a4b --validation-pct 1

