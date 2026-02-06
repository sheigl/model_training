"""
Test generation and model evaluation.

This module handles generating sample responses from a trained model
to verify it's working correctly. This is a quick sanity check, not
a rigorous evaluation.

The generation process:
  1. Format the prompt as a chat message (using the model's template)
  2. Tokenize it (convert text to numbers)
  3. Feed it into the model
  4. The model predicts one token at a time, feeding each prediction back
     in as input for the next (this is "autoregressive generation")
  5. Decode the output tokens back to text

Real-world analogy: Like asking a student to answer questions after they
finish studying. You're not grading them -- just checking they can produce
coherent answers about the material.
"""

import torch


# Default test prompts for sanity checking
DEFAULT_TEST_PROMPTS = [
    "What is machine learning?",
    "Explain photosynthesis simply.",
    "Write a short poem about the ocean.",
]


def test_model(model, tokenizer, device, prompts=None):
    """
    Generate sample responses from the model to verify training worked.

    Args:
        model: The trained model (with LoRA adapters).
        tokenizer: The tokenizer for the model.
        device: The device to run inference on ('cuda', 'xpu', 'cpu').
        prompts: List of test prompts. Uses defaults if None.
    """
    if prompts is None:
        prompts = DEFAULT_TEST_PROMPTS

    print("\n" + "="*70)
    print("TESTING FINE-TUNED MODEL")
    print("="*70 + "\n")

    # model.eval() switches the model from "training mode" to "evaluation mode."
    # In training mode, dropout is active (randomly disabling connections).
    # In eval mode, dropout is disabled so the model gives consistent outputs.
    # Real-world analogy: In practice (training), a team rotates players.
    # In the real game (evaluation), everyone plays their best lineup.
    model.eval()

    for prompt in prompts:
        # Format as a chat conversation with the model's expected template.
        # Qwen uses the ChatML format:
        #   <|im_start|>user
        #   What is machine learning?<|im_end|>
        #   <|im_start|>assistant
        messages = [{"role": "user", "content": prompt}]

        # apply_chat_template() wraps the message in the model's specific
        # format. tokenize=False means "give me the string, don't convert
        # to numbers yet." add_generation_prompt=True adds the
        # "<|im_start|>assistant\n" prefix so the model knows it should
        # start generating the assistant's response.
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        # Now tokenize (convert text to token IDs) and move to the GPU.
        # return_tensors="pt" means "return PyTorch tensors" (as opposed to
        # numpy arrays or TensorFlow tensors).
        # .to(device) moves the data to the same device as the model (GPU/CPU).
        inputs = tokenizer(text, return_tensors="pt").to(device)

        # Generate the response.
        # torch.no_grad() disables gradient tracking, which saves memory
        # and speeds up inference. We only need gradients during training.
        with torch.no_grad():
            outputs = model.generate(
                **inputs,               # Unpack the tokenized input
                max_new_tokens=128,     # Generate at most 128 new tokens
                temperature=0.7,        # Controls randomness:
                                        #   0.0 = always pick the most likely token (deterministic)
                                        #   1.0 = sample proportionally from probabilities
                                        #   0.7 = a good balance of creativity and coherence
                                        #   >1.0 = more random/creative
                do_sample=True,         # Enable sampling (vs greedy decoding)
                pad_token_id=tokenizer.eos_token_id  # Use EOS for padding
            )

        # Decode: convert token IDs back to human-readable text.
        # skip_special_tokens=True removes formatting tokens like <|im_start|>
        # that are meaningful to the model but ugly for humans to read.
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)

        # Extract just the assistant's response (everything after the last
        # "<|im_start|>assistant" marker). The full decoded output includes
        # the original prompt + the generated response, and we only want
        # the new part.
        if "<|im_start|>assistant" in response:
            response = response.split("<|im_start|>assistant")[-1].strip()

        print(f"User: {prompt}")
        print(f"Assistant: {response}\n")
        print("-" * 70 + "\n")
