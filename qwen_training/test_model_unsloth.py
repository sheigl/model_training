from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template
from transformers import TextStreamer
import torch

# Load your trained adapter
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="./output-27b-mtg-unsloth",  # your output dir
    dtype=None,
    load_in_4bit=True,
)

tokenizer = get_chat_template(tokenizer, chat_template="chatml")
FastLanguageModel.for_inference(model)

# Streamer prints tokens as they're generated
streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

SYSTEM_PROMPT = "You are an expert Magic: The Gathering assistant. Answer questions about cards, rules, deck building, and strategy."

def ask_mtg(conversation_history):
    text = tokenizer.apply_chat_template(
        conversation_history,
        tokenize=False,
        add_generation_prompt=True
    )
    
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.7,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
            streamer=streamer,  # streams tokens as they generate
        )
    
    # Return just the new text for storing in history
    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def main():
    print("=" * 60)
    print("MTG Expert - Interactive Chat")
    print("Type 'quit' or 'exit' to stop")
    print("Type 'reset' to start a new conversation")
    print("=" * 60 + "\n")

    # Maintain conversation history for multi-turn context
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "reset":
            history = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("\n[Conversation reset]\n")
            continue

        history.append({"role": "user", "content": user_input})

        print("\nAssistant: ", end="", flush=True)
        response = ask_mtg(history)
        print()  # newline after streamed response

        # Add assistant response to history for follow-up context
        history.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()