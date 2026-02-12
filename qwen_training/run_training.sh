#!/bin/bash

source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1

export SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1
export SYCL_CACHE_PERSISTENT=1
export ZE_FLAT_DEVICE_HIERARCHY=FLAT

~/code/model_training/.venv/bin/python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file ~/code/model_training/training_data/data/mongodb_mtg_training.jsonl \
  --use-4bit \
  --lora-r 32 \
  --lora-alpha 64 \
  --lora-dropout 0.05 \
  --use-galore \
  --galore-rank 128 \
  --galore-update-proj-gap 200 \
  --galore-scale 0.25 \
  --batch-size 2 \
  --learning-rate 1e-4 \
  --gradient-accumulation 8 \
  --epochs 1 \
  --max-seq-length 2048 \
  --output-dir ~/code/model_training/qwen_training/test-1epoch-1e4 \
  2>&1 | tee ~/.log/test_training_1e4.log
