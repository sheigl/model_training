"""
Dataset loading functions for Qwen fine-tuning.

These functions handle loading training data from different sources.
All of them produce data in the same format: a list of conversations
where each conversation has a "messages" field containing role/content pairs.

This format looks like:
  {"messages": [
      {"role": "user", "content": "What does Lightning Bolt do?"},
      {"role": "assistant", "content": "Lightning Bolt deals 3 damage..."}
  ]}

Real-world analogy: This is like a script for a play. Each message has a
character (role) and their line (content). The model learns to play the
"assistant" character by studying many example scripts.
"""

import json
from datasets import Dataset, load_dataset


def create_sample_dataset():
    """
    Create a small sample instruction dataset for testing.

    This is a toy dataset just to verify the training pipeline works end-to-end.
    It contains only 5 unique examples, duplicated 20 times to reach 100.

    In real training, you'd want hundreds or thousands of UNIQUE examples.
    Using duplicates like this is only for pipeline testing -- the model won't
    learn much from seeing the same 5 things over and over.

    Real-world analogy: This is like a "Hello World" program. It doesn't do
    anything useful, but it proves your setup works.

    Returns:
        Dataset: A Hugging Face Dataset with 100 training examples.
    """

    sample_data = [
        {
            "messages": [
                {"role": "user", "content": "What is the capital of France?"},
                {"role": "assistant", "content": "The capital of France is Paris."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Explain quantum computing in simple terms."},
                {"role": "assistant", "content": "Quantum computing uses quantum mechanics principles to process information. Unlike classical computers that use bits (0 or 1), quantum computers use qubits that can be in multiple states simultaneously, allowing them to solve certain problems much faster."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Write a haiku about programming."},
                {"role": "assistant", "content": "Code flows like water\nBugs hide in silent shadows\nDebug brings the dawn"}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "What are the three laws of robotics?"},
                {"role": "assistant", "content": "Isaac Asimov's Three Laws of Robotics are:\n1. A robot may not injure a human being or allow a human to come to harm\n2. A robot must obey human orders unless they conflict with the First Law\n3. A robot must protect its own existence unless it conflicts with the First or Second Law"}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "How do you make scrambled eggs?"},
                {"role": "assistant", "content": "Here's how to make scrambled eggs:\n1. Crack 2-3 eggs into a bowl\n2. Add a splash of milk and whisk\n3. Heat butter in a pan over medium heat\n4. Pour in eggs and gently stir with a spatula\n5. Cook until just set but still creamy\n6. Season with salt and pepper"}
            ]
        },
    ]

    # Multiply the dataset to have more training examples.
    # This is a HACK for testing only. Real training data should be unique.
    # Duplicating data like this leads to overfitting (memorization).
    expanded_data = sample_data * 20  # 5 unique * 20 = 100 total examples

    # Dataset.from_list() converts a Python list of dictionaries into a
    # Hugging Face Dataset object, which is optimized for ML workflows
    # (efficient batching, shuffling, memory mapping, etc.).
    return Dataset.from_list(expanded_data)


def load_custom_dataset(file_path):
    """
    Load dataset from a JSONL file (JSON Lines format).

    JSONL = one JSON object per line. Each line is an independent record.
    This is the format our MTG data conversion scripts output.

    Example file content:
        {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
        {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

    Real-world analogy: JSONL is like a CSV file but more flexible. Each line
    is a self-contained record, so you can process the file one line at a time
    without loading everything into memory (though here we load it all).

    Args:
        file_path: Path to the JSONL file.

    Returns:
        Dataset: A Hugging Face Dataset loaded from the file.
    """
    with open(file_path, 'r') as f:
        # List comprehension: for each line in the file, parse it as JSON.
        # json.loads() converts a JSON string into a Python dictionary.
        data = [json.loads(line) for line in f]
    return Dataset.from_list(data)


def load_hf_dataset(dataset_name="yahma/alpaca-cleaned"):
    """
    Load a dataset from the Hugging Face Hub.

    The HF Hub is like GitHub but for ML datasets and models. Community
    members upload datasets that anyone can use. This function downloads
    one and converts it to our expected format.

    Popular instruction datasets:
    - yahma/alpaca-cleaned: Cleaned version of Stanford Alpaca's training data
    - vicgalle/alpaca-gpt4: Alpaca data generated with GPT-4 (higher quality)
    - tatsu-lab/alpaca: The original Stanford Alpaca dataset

    Real-world analogy: The HF Hub is like a public library of training data.
    Instead of gathering all the data yourself, you can borrow pre-made datasets.

    Args:
        dataset_name: The Hugging Face dataset identifier (e.g., "yahma/alpaca-cleaned").

    Returns:
        Dataset: A Hugging Face Dataset with the data converted to messages format.
    """
    # load_dataset downloads and caches the dataset. split="train" means we
    # only want the training portion (some datasets have train/test/validation).
    dataset = load_dataset(dataset_name, split="train")

    # Alpaca-format datasets have "instruction" and "output" fields, but our
    # trainer expects "messages" format. This function converts between them.
    # It's like translating a book from one language to another -- same content,
    # different structure.
    def format_to_messages(example):
        return {
            "messages": [
                {"role": "user", "content": example["instruction"]},
                {"role": "assistant", "content": example["output"]}
            ]
        }

    # dataset.map() applies a function to every row. This is much faster than
    # a Python for-loop because it uses optimized C code under the hood.
    return dataset.map(format_to_messages)
