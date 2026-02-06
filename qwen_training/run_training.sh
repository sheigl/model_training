#!/bin/bash

source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1

export SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1
export SYCL_CACHE_PERSISTENT=1
export ZE_FLAT_DEVICE_HIERARCHY=FLAT

~/code/model_training/.venv/bin/python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file ~/code/model_training/training_data/complete_mtg.jsonl \
  --use-4bit \
  --lora-r 24 \
  --use-galore \
  --galore-rank 128 \
  --batch-size 4 \
  --learning-rate 1e-4 \
  --gradient-accumulation 8 \
  --epochs 2 \
  --resume-from-checkpoint ~/code/model_training/qwen_training/output/checkpoint-5800 \
  --output-dir ~/code/model_training/qwen_training/output/output_continue \
  > ~/.log/model_training.log
