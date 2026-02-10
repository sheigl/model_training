#!/bin/bash

source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1

export SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1
export SYCL_CACHE_PERSISTENT=1
export ZE_FLAT_DEVICE_HIERARCHY=FLAT

~/code/model_training/.venv/bin/python ~/code/model_training/qwen_training/finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file ~/code/model_training/training_data/data/mongodb_mtg_training.jsonl \
  --use-4bit \
  --lora-r 64 \
  --use-galore \
  --galore-rank 512 \
  --batch-size 2 \
  --learning-rate 3e-5 \
  --gradient-accumulation 8 \
  --epochs 3 \
  --output-dir ~/code/model_training/qwen_training/output-3b-mtg-expert-highrank \
  --save-steps 500 \
  --warmup-steps 100 \
  > ~/.log/model_training.log 2>&1 &


#   --resume-from-checkpoint ~/code/model_training/qwen_training/output/checkpoint-20592 \
