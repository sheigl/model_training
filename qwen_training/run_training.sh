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
  --lora-r 32 \
  --lora-alpha 64 \
  --lora-dropout 0.05 \
  --use-galore \
  --galore-rank 256 \
  --galore-update-proj-gap 200 \
  --galore-scale 0.25 \
  --batch-size 4 \
  --learning-rate 5e-5 \
  --gradient-accumulation 4 \
  --epochs 3 \
  --max-seq-length 2048 \
  --output-dir ~/code/model_training/qwen_training/output-3b-mtg-expert \
  > ~/.log/model_training.log 2>&1 &


#   --resume-from-checkpoint ~/code/model_training/qwen_training/output/checkpoint-20592 \
