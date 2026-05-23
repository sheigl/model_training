#!/bin/sh

NUM=${1:-1}
MODEL=${2:-http://localhost:8080/v1,openai,qwen3.5:9b}
VALIDATION_MODEL=${3:-http://localhost:8080/v1,openai,qwen3.6:27b}
VALIDATION_PCT=${4:-1}

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python
GEN_SYNTH=$BASE_DIR/training_data/generate_synthetic_data

$PYTHON $GEN_SYNTH/main.py --combo-queries $NUM --model $MODEL --validation-model $VALIDATION_MODEL --validation-pct $VALIDATION_PCT

