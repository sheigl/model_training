"""
Qwen fine-tuning package with LoRA and GaLore support.

This package provides modular components for fine-tuning Qwen language models
(0.5B to 8B+) using Parameter-Efficient Fine-Tuning (PEFT) techniques.

Modules:
    cli: Command-line argument parsing
    data: Dataset loading functions (sample, Hugging Face, custom JSONL)
    model: Model/tokenizer loading, quantization, and LoRA configuration
    trainer: Training configuration and GaLore optimizer setup
    inference: Test generation and model evaluation

Entry point:
    finetune_qwen.py - Main script that orchestrates the training pipeline
"""
