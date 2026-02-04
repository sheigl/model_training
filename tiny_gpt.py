import torch
import torch.nn as nn
import torch.nn.functional as F

# ============================================================================
# HYPERPARAMETERS
# ============================================================================
# These control the size and behavior of our model

batch_size = 32        # How many independent sequences we process in parallel
block_size = 128       # Maximum context length (how far back the model can "look")
n_embd = 384          # The dimensionality of the embedding vectors
n_head = 6            # Number of attention heads in multi-head attention
n_layer = 6           # Number of transformer blocks stacked on top of each other
dropout = 0.2         # Dropout rate for regularization (prevents overfitting)
learning_rate = 3e-4  # Step size for the optimizer
max_iters = 5000      # How many training steps to run
eval_interval = 500   # How often to evaluate on validation set

# Set random seed for reproducibility - same seed = same results every time
torch.manual_seed(1337)

# ============================================================================
# DEVICE SETUP (GPU/CPU)
# ============================================================================

# For Intel Arc GPUs, PyTorch uses the XPU device type
# XPU is Intel's device abstraction for their GPUs
if hasattr(torch, 'xpu') and torch.xpu.is_available():
    device = 'xpu'
    print(f'Using Intel GPU (XPU): {torch.xpu.get_device_name(0)}')
# Fallback to CUDA for NVIDIA GPUs
elif torch.cuda.is_available():
    device = 'cuda'
    print(f'Using NVIDIA GPU: {torch.cuda.get_device_name(0)}')
else:
    device = 'cpu'
    print('Using CPU')

# You can also manually set device if needed:
# device = 'xpu'   # Force Intel GPU
# device = 'cuda'  # Force NVIDIA GPU  
# device = 'cpu'   # Force CPU

# ============================================================================
# DATA LOADING AND PREPARATION
# ============================================================================

# Read the text file that we'll use for training
# You need to provide your own 'input.txt' file
with open('input.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# Build the vocabulary - get all unique characters in the text
chars = sorted(list(set(text)))
vocab_size = len(chars)

# Create mappings between characters and integers
# stoi = "string to integer" - converts characters to numbers
# itos = "integer to string" - converts numbers back to characters
stoi = {ch: i for i, ch in enumerate(chars)}
itos = {i: ch for i, ch in enumerate(chars)}

# Encode function: takes a string and converts it to a list of integers
encode = lambda s: [stoi[c] for c in s]

# Decode function: takes a list of integers and converts back to a string
decode = lambda l: ''.join([itos[i] for i in l])

# Convert the entire text to a tensor of integers
data = torch.tensor(encode(text), dtype=torch.long)

# Split data into training (90%) and validation (10%) sets
n = int(0.9 * len(data))
train_data = data[:n]
val_data = data[n:]

def get_batch(split):
    """
    Generate a batch of training or validation data.
    
    This function creates random chunks of text from our dataset.
    Each chunk is 'block_size' characters long.
    
    Args:
        split: Either 'train' or 'val' to specify which dataset to use
    
    Returns:
        x: Input sequences (batch_size, block_size)
        y: Target sequences (batch_size, block_size) - same as x but shifted by 1
        
    Example:
        If input text is "hello", and block_size is 4:
        x might be "hell"
        y would be "ello"
        The model learns: given "h", predict "e"; given "he", predict "l", etc.
    """
    # Choose the appropriate dataset
    data = train_data if split == 'train' else val_data
    
    # Generate random starting positions for each sequence in the batch
    # We subtract block_size to ensure we have enough characters after each start
    ix = torch.randint(len(data) - block_size, (batch_size,))
    
    # Create input sequences: stack multiple sequences of length block_size
    x = torch.stack([data[i:i+block_size] for i in ix])
    
    # Create target sequences: same as input but shifted by 1 position
    # This is what the model should predict
    y = torch.stack([data[i+1:i+block_size+1] for i in ix])
    
    # Move data to the GPU (or CPU if no GPU available)
    x, y = x.to(device), y.to(device)
    
    return x, y

# ============================================================================
# MODEL COMPONENTS
# ============================================================================

class Head(nn.Module):
    """
    One head of self-attention.
    
    Self-attention allows each position in the sequence to "look at" and gather
    information from previous positions. Think of it like: when predicting the
    next word, you want to pay attention to relevant earlier words.
    
    The attention mechanism has three learned transformations:
    - Query: "what am I looking for?"
    - Key: "what do I contain?"
    - Value: "what information do I actually have to share?"
    
    The attention score is computed by comparing queries and keys, then using
    those scores to weight the values.
    """
    
    def __init__(self, head_size):
        """
        Initialize a single attention head.
        
        Args:
            head_size: The dimensionality of the queries, keys, and values
        """
        super().__init__()
        
        # These linear layers create the queries, keys, and values
        # bias=False is common in transformer implementations
        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)
        
        # Create a lower triangular matrix for masking
        # This ensures we can only attend to previous positions (causal attention)
        # We use register_buffer so this isn't considered a model parameter
        self.register_buffer('tril', torch.tril(torch.ones(block_size, block_size)))
        
        # Dropout for regularization
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x):
        """
        Apply self-attention to the input.
        
        Args:
            x: Input tensor of shape (batch_size, sequence_length, embedding_dim)
        
        Returns:
            Output tensor of shape (batch_size, sequence_length, head_size)
        """
        B, T, C = x.shape  # B=batch, T=time/sequence, C=channels/embedding_dim
        
        # Compute queries, keys, and values
        k = self.key(x)    # (B, T, head_size)
        q = self.query(x)  # (B, T, head_size)
        
        # Compute attention scores ("affinities")
        # @ is matrix multiplication in PyTorch
        # We transpose the last two dimensions of k to get (B, head_size, T)
        # Result: (B, T, T) - each position has scores for all other positions
        wei = q @ k.transpose(-2, -1) * (C ** -0.5)  # Scale by sqrt(head_size)
        
        # Apply causal mask: make future positions -inf so they become 0 after softmax
        # This prevents the model from "cheating" by looking at future tokens
        wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf'))
        
        # Convert scores to probabilities (attention weights)
        wei = F.softmax(wei, dim=-1)  # (B, T, T)
        
        # Apply dropout to attention weights
        wei = self.dropout(wei)
        
        # Apply attention weights to values
        v = self.value(x)  # (B, T, head_size)
        out = wei @ v      # (B, T, head_size)
        
        return out

class MultiHeadAttention(nn.Module):
    """
    Multiple heads of self-attention in parallel.
    
    Instead of having just one attention mechanism, we have multiple heads
    that can learn to attend to different aspects of the input. For example,
    one head might learn to attend to the subject of a sentence, another to
    verbs, etc.
    
    The outputs of all heads are concatenated and projected back to the
    original embedding dimension.
    """
    
    def __init__(self, num_heads, head_size):
        """
        Initialize multi-head attention.
        
        Args:
            num_heads: Number of attention heads to use
            head_size: Dimension of each attention head
        """
        super().__init__()
        
        # Create multiple attention heads
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])
        
        # Projection layer to combine all heads back to embedding dimension
        self.proj = nn.Linear(n_embd, n_embd)
        
        # Dropout for regularization
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x):
        """
        Apply multi-head attention.
        
        Args:
            x: Input tensor (B, T, C)
        
        Returns:
            Output tensor (B, T, C)
        """
        # Run all heads in parallel and concatenate their outputs
        # Each head outputs (B, T, head_size)
        # Concatenating along the last dimension gives (B, T, n_embd)
        out = torch.cat([h(x) for h in self.heads], dim=-1)
        
        # Project back and apply dropout
        out = self.dropout(self.proj(out))
        
        return out

class FeedForward(nn.Module):
    """
    A simple feed-forward neural network.
    
    After attention, we apply a position-wise feed-forward network to each
    position independently. This is a two-layer network with a ReLU activation.
    
    The standard pattern is to expand to 4x the embedding dimension, apply
    non-linearity, then project back down.
    """
    
    def __init__(self, n_embd):
        """
        Initialize the feed-forward network.
        
        Args:
            n_embd: Embedding dimension
        """
        super().__init__()
        
        # Two-layer network with expansion
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),  # Expand to 4x
            nn.ReLU(),                       # Non-linearity
            nn.Linear(4 * n_embd, n_embd),  # Project back down
            nn.Dropout(dropout),             # Regularization
        )
    
    def forward(self, x):
        """
        Apply feed-forward network.
        
        Args:
            x: Input tensor (B, T, C)
        
        Returns:
            Output tensor (B, T, C)
        """
        return self.net(x)

class Block(nn.Module):
    """
    A single Transformer block.
    
    This is the core building block of a transformer. It consists of:
    1. Multi-head self-attention
    2. Feed-forward network
    
    Both are wrapped with:
    - Layer normalization (for stable training)
    - Residual connections (helps with gradient flow in deep networks)
    
    The pattern is:
        x = x + attention(layer_norm(x))
        x = x + feedforward(layer_norm(x))
    
    This is slightly different from the original "Attention is All You Need"
    paper (which did layer norm after), but has become the standard.
    """
    
    def __init__(self, n_embd, n_head):
        """
        Initialize a transformer block.
        
        Args:
            n_embd: Embedding dimension
            n_head: Number of attention heads
        """
        super().__init__()
        
        # Calculate the size of each attention head
        head_size = n_embd // n_head
        
        # Self-attention component
        self.sa = MultiHeadAttention(n_head, head_size)
        
        # Feed-forward component
        self.ffwd = FeedForward(n_embd)
        
        # Layer normalization (normalizes across the embedding dimension)
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)
    
    def forward(self, x):
        """
        Apply the transformer block.
        
        Args:
            x: Input tensor (B, T, C)
        
        Returns:
            Output tensor (B, T, C)
        """
        # Apply attention with residual connection
        # The "x +" is the residual connection - we add the input back to the output
        # This helps gradients flow through the network during training
        x = x + self.sa(self.ln1(x))
        
        # Apply feed-forward with residual connection
        x = x + self.ffwd(self.ln2(x))
        
        return x

class GPTLanguageModel(nn.Module):
    """
    The complete GPT-style language model.
    
    This model:
    1. Embeds input tokens and positions
    2. Applies multiple transformer blocks
    3. Projects to vocabulary size to predict next token
    
    Architecture overview:
        Input tokens → Token embeddings + Position embeddings
                    → Transformer blocks (repeated n_layer times)
                    → Layer norm
                    → Linear projection to vocabulary
                    → Predictions
    """
    
    def __init__(self):
        """Initialize the language model."""
        super().__init__()
        
        # Token embedding: converts token indices to dense vectors
        # vocab_size: how many different tokens we have
        # n_embd: dimension of the embedding vectors
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        
        # Position embedding: adds information about token position in sequence
        # Each position gets its own learned embedding vector
        self.position_embedding_table = nn.Embedding(block_size, n_embd)
        
        # Stack of transformer blocks
        # We use nn.Sequential so they're applied one after another
        self.blocks = nn.Sequential(*[Block(n_embd, n_head) for _ in range(n_layer)])
        
        # Final layer normalization
        self.ln_f = nn.LayerNorm(n_embd)
        
        # Language modeling head: projects from embedding dimension to vocabulary
        # This produces logits (unnormalized probabilities) for each token in vocab
        self.lm_head = nn.Linear(n_embd, vocab_size)
    
    def forward(self, idx, targets=None):
        """
        Forward pass of the model.
        
        Args:
            idx: Input token indices (B, T)
            targets: Target token indices (B, T) - if provided, compute loss
        
        Returns:
            logits: Predicted scores for each vocabulary token (B, T, vocab_size)
            loss: Cross-entropy loss if targets provided, None otherwise
        """
        B, T = idx.shape
        
        # Get token embeddings: (B, T) → (B, T, n_embd)
        tok_emb = self.token_embedding_table(idx)
        
        # Get position embeddings: (T,) → (T, n_embd)
        # torch.arange(T) creates [0, 1, 2, ..., T-1]
        # We broadcast this across the batch dimension
        pos_emb = self.position_embedding_table(torch.arange(T, device=idx.device))
        
        # Combine token and position embeddings
        # pos_emb is broadcast across batch dimension
        x = tok_emb + pos_emb  # (B, T, n_embd)
        
        # Apply all transformer blocks
        x = self.blocks(x)  # (B, T, n_embd)
        
        # Apply final layer normalization
        x = self.ln_f(x)  # (B, T, n_embd)
        
        # Project to vocabulary size to get logits (prediction scores)
        logits = self.lm_head(x)  # (B, T, vocab_size)
        
        # If we have targets, compute the loss
        if targets is None:
            loss = None
        else:
            # Reshape for cross_entropy function
            # PyTorch's cross_entropy expects (batch_size, vocab_size) and (batch_size,)
            # So we flatten the batch and time dimensions
            B, T, C = logits.shape
            logits = logits.view(B*T, C)     # (B*T, vocab_size)
            targets = targets.view(B*T)       # (B*T,)
            
            # Compute cross-entropy loss
            # This measures how well our predictions match the targets
            loss = F.cross_entropy(logits, targets)
        
        return logits, loss
    
    def generate(self, idx, max_new_tokens):
        """
        Generate new tokens autoregressively.
        
        This is how we actually use the model to generate text.
        We repeatedly:
        1. Get predictions for the next token
        2. Sample from the predictions
        3. Append to our sequence
        4. Repeat
        
        Args:
            idx: Starting sequence (B, T)
            max_new_tokens: How many new tokens to generate
        
        Returns:
            idx: Extended sequence (B, T + max_new_tokens)
        """
        for _ in range(max_new_tokens):
            # Crop context to the last block_size tokens
            # The model can only handle sequences up to block_size
            idx_cond = idx[:, -block_size:]
            
            # Get predictions (we don't need loss during generation)
            logits, loss = self(idx_cond)
            
            # Focus only on the last time step (the new prediction)
            # logits shape: (B, T, vocab_size) → (B, vocab_size)
            logits = logits[:, -1, :]
            
            # Apply softmax to get probabilities
            probs = F.softmax(logits, dim=-1)  # (B, vocab_size)
            
            # Sample from the distribution
            # This gives us the index of the next token
            idx_next = torch.multinomial(probs, num_samples=1)  # (B, 1)
            
            # Append sampled token to the sequence
            idx = torch.cat((idx, idx_next), dim=1)  # (B, T+1)
        
        return idx

# ============================================================================
# TRAINING
# ============================================================================

# Initialize the model
model = GPTLanguageModel()

# Move model to GPU (or CPU)
# This moves all model parameters to the specified device
model = model.to(device)

# Print model size
# .parameters() gets all trainable parameters
# .numel() gets the number of elements in each parameter
# We sum them up and divide by 1 million to get millions of parameters
print(f'Model has {sum(p.numel() for p in model.parameters())/1e6:.2f}M parameters')

# Initialize the optimizer
# AdamW is Adam with weight decay (a form of regularization)
optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

# Training loop
for iter in range(max_iters):
    # Every eval_interval steps, evaluate on validation set
    if iter % eval_interval == 0:
        model.eval()  # Set model to evaluation mode (disables dropout)
        
        # torch.no_grad() disables gradient computation (saves memory)
        with torch.no_grad():
            xb, yb = get_batch('val')
            logits, loss = model(xb, yb)
        
        print(f'Step {iter}: val loss {loss.item():.4f}')
        model.train()  # Set model back to training mode
    
    # Get a batch of training data
    xb, yb = get_batch('train')
    
    # Forward pass: compute predictions and loss
    logits, loss = model(xb, yb)
    
    # Backward pass: compute gradients
    # set_to_none=True is slightly more efficient than zero_grad()
    optimizer.zero_grad(set_to_none=True)
    loss.backward()  # Compute gradients
    
    # Update weights
    optimizer.step()

# ============================================================================
# GENERATION
# ============================================================================

# Set model to evaluation mode
model.eval()

# Start with a single newline character (or any token)
# torch.zeros creates a tensor of zeros
# We reshape to (1, 1) meaning batch_size=1, sequence_length=1
# Move to the same device as the model
context = torch.zeros((1, 1), dtype=torch.long, device=device)

# Generate 500 new tokens
# The generate function will use the model to predict and sample tokens
generated = model.generate(context, max_new_tokens=500)

# Decode the generated tokens back to text
# [0] extracts the first (and only) sequence from the batch
# .tolist() converts the tensor to a Python list
print(decode(generated[0].tolist()))