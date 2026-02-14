import json
import sys

filename = sys.argv[1] if len(sys.argv) > 1 else "mongodb_mtg_training.jsonl"

print(f"Checking {filename}...")
print()

errors = []
line_num = 0

with open(filename, 'r', encoding='utf-8') as f:
    for line in f:
        line_num += 1
        
        if not line.strip():
            continue
        
        try:
            obj = json.loads(line)
            
            # Check if messages exists
            if 'messages' not in obj:
                errors.append((line_num, "Missing 'messages' key", line[:100]))
                continue
            
            messages = obj['messages']
            
            # Check if messages is a list
            if not isinstance(messages, list):
                errors.append((line_num, f"'messages' is {type(messages).__name__}, not list", line[:100]))
                continue
            
            # Check if messages is empty
            if len(messages) == 0:
                errors.append((line_num, "'messages' is empty list", line[:100]))
                continue
            
            # Check each message
            for i, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    errors.append((line_num, f"Message {i} is {type(msg).__name__}, not dict", line[:100]))
                    break
                
                if 'role' not in msg:
                    errors.append((line_num, f"Message {i} missing 'role'", line[:100]))
                    break
                
                if 'content' not in msg:
                    errors.append((line_num, f"Message {i} missing 'content'", line[:100]))
                    break
                
                if not isinstance(msg['content'], str):
                    errors.append((line_num, f"Message {i} content is {type(msg['content']).__name__}, not str", line[:100]))
                    break
        
        except json.JSONDecodeError as e:
            errors.append((line_num, f"JSON parse error: {e}", line[:100]))
        
        if line_num % 10000 == 0:
            print(f"Checked {line_num:,} lines... ({len(errors)} errors so far)")

print(f"\n✓ Checked {line_num:,} total lines")
print(f"✗ Found {len(errors)} errors\n")

if errors:
    print("First 10 errors:")
    for line_num, error, preview in errors[:10]:
        print(f"\nLine {line_num}: {error}")
        print(f"  Preview: {preview}...")
else:
    print("✅ No errors found! File looks good.")