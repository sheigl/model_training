#!/bin/bash

#source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1

#export SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1
#export SYCL_CACHE_PERSISTENT=1
#export ZE_FLAT_DEVICE_HIERARCHY=FLAT

~/code/model_training/.venv/bin/python finetune_qwen.py \
  --model-name Qwen/Qwen3.5-9B \
  --dataset file \
  --data-file ~/code/model_training/training_data/mtg_lora_training.jsonl \
  --use-4bit \
  --lora-r 64 \
  --lora-alpha 64 \
  --lora-dropout 0 \
  --batch-size 2 \
  --learning-rate 2e-4 \
  --gradient-accumulation 8 \
  --epochs 10 \
  --max-seq-length 2048 \
  --output-dir ~/code/model_training/qwen_training/output-9b-mtg-unsloth
