#!/bin/sh

NUM=${1:-1}

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

$PYTHON $GEN_SYNTH/main.py --combo-queries $NUM --model http://localhost:8080/v1,openai,qwen3.6:35b-a3b --validation-model http://localhost:8080/v1,openai,qwen3.6:35b-a3b --validation-pct 1

