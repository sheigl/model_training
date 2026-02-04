import torch
import torch.nn as nn
import torch.nn.functional as F

# ============================================================================
# LOAD THE TRAINED MODEL
# ============================================================================

# These need to match the training configuration
batch_size = 32
block_size = 128
n_embd = 384
n_head = 6
n_layer = 6
dropout = 0.2

# Load the vocabulary from input.txt (same as training)
with open('input.txt', 'r', encoding='utf-8') as f:
    text = f.read()

chars = sorted(list(set(text)))
vocab_size = len(chars)
stoi = {ch: i for i, ch in enumerate(chars)}
itos = {i: ch for i, ch in enumerate(chars)}
encode = lambda s: [stoi[c] for c in s]
decode = lambda l: ''.join([itos[i] for i in l])

# Device detection
if hasattr(torch, 'xpu') and torch.xpu.is_available():
    device = 'xpu'
    print(f'Using Intel GPU (XPU): {torch.xpu.get_device_name(0)}')
elif torch.cuda.is_available():
    device = 'cuda'
    print(f'Using NVIDIA GPU: {torch.cuda.get_device_name(0)}')
else:
    device = 'cpu'
    print('Using CPU')

# ============================================================================
# MODEL ARCHITECTURE (copy from training script)
# ============================================================================

class Head(nn.Module):
    def __init__(self, head_size):
        super().__init__()
        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)
        self.register_buffer('tril', torch.tril(torch.ones(block_size, block_size)))
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x):
        B, T, C = x.shape
        k = self.key(x)
        q = self.query(x)
        wei = q @ k.transpose(-2, -1) * (C ** -0.5)
        wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf'))
        wei = F.softmax(wei, dim=-1)
        wei = self.dropout(wei)
        v = self.value(x)
        out = wei @ v
        return out

class MultiHeadAttention(nn.Module):
    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(n_embd, n_embd)
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x):
        out = torch.cat([h(x) for h in self.heads], dim=-1)
        out = self.dropout(self.proj(out))
        return out

class FeedForward(nn.Module):
    def __init__(self, n_embd):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )
    
    def forward(self, x):
        return self.net(x)

class Block(nn.Module):
    def __init__(self, n_embd, n_head):
        super().__init__()
        head_size = n_embd // n_head
        self.sa = MultiHeadAttention(n_head, head_size)
        self.ffwd = FeedForward(n_embd)
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)
    
    def forward(self, x):
        x = x + self.sa(self.ln1(x))
        x = x + self.ffwd(self.ln2(x))
        return x

class GPTLanguageModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        self.position_embedding_table = nn.Embedding(block_size, n_embd)
        self.blocks = nn.Sequential(*[Block(n_embd, n_head) for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size)
    
    def forward(self, idx, targets=None):
        B, T = idx.shape
        tok_emb = self.token_embedding_table(idx)
        pos_emb = self.position_embedding_table(torch.arange(T, device=idx.device))
        x = tok_emb + pos_emb
        x = self.blocks(x)
        x = self.ln_f(x)
        logits = self.lm_head(x)
        
        if targets is None:
            loss = None
        else:
            B, T, C = logits.shape
            logits = logits.view(B*T, C)
            targets = targets.view(B*T)
            loss = F.cross_entropy(logits, targets)
        
        return logits, loss
    
    def generate(self, idx, max_new_tokens):
        for _ in range(max_new_tokens):
            idx_cond = idx[:, -block_size:]
            logits, loss = self(idx_cond)
            logits = logits[:, -1, :]
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, idx_next), dim=1)
        return idx

# ============================================================================
# LOAD TRAINED WEIGHTS
# ============================================================================

model = GPTLanguageModel()
model = model.to(device)

# Try to load saved model weights
try:
    model.load_state_dict(torch.load('model_weights.pth', map_location=device))
    print("Loaded trained model weights!")
except FileNotFoundError:
    print("Warning: No saved model found. Using untrained model.")
    print("Train the model first by running tiny_gpt.py")

model.eval()

# ============================================================================
# INTERACTIVE GENERATION
# ============================================================================

def generate_from_prompt(prompt, max_tokens=500):
    """Generate text continuing from a prompt"""
    # Encode the prompt
    context = torch.tensor([encode(prompt)], dtype=torch.long, device=device)
    
    # Generate continuation
    with torch.no_grad():
        generated = model.generate(context, max_new_tokens=max_tokens)
    
    # Decode and return
    return decode(generated[0].tolist())

# Interactive loop
print("\n" + "="*70)
print("INTERACTIVE TEXT GENERATOR")
print("="*70)
print("Type a prompt and the model will continue it.")
print("Commands:")
print("  'quit' or 'exit' - Exit the program")
print("  'random' - Generate random text with no prompt")
print("  'tokens:N' after your prompt - Generate N tokens (default: 300)")
print("="*70 + "\n")

while True:
    # Get user input
    user_input = input("Prompt> ").strip()
    
    # Check for exit commands
    if user_input.lower() in ['quit', 'exit', 'q']:
        print("Goodbye!")
        break
    
    # Check for random generation
    if user_input.lower() == 'random':
        print("\nGenerating random text...\n")
        context = torch.zeros((1, 1), dtype=torch.long, device=device)
        with torch.no_grad():
            generated = model.generate(context, max_new_tokens=300)
        print(decode(generated[0].tolist()))
        print("\n" + "-"*70 + "\n")
        continue
    
    # Check for custom token count
    max_tokens = 300
    if 'tokens:' in user_input.lower():
        parts = user_input.split('tokens:')
        user_input = parts[0].strip()
        try:
            max_tokens = int(parts[1].strip())
        except ValueError:
            print("Invalid token count, using default (300)")
    
    # Skip empty input
    if not user_input:
        continue
    
    # Generate from prompt
    print(f"\nGenerating {max_tokens} tokens...\n")
    result = generate_from_prompt(user_input, max_tokens)
    print(result)
    print("\n" + "-"*70 + "\n")