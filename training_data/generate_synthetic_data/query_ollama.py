
import time
import ollama
import json
from common import *

# =============================================================================
# MODEL QUERYING
# =============================================================================

def query_ollama(model_name: str, prompt: str, max_tokens=9999):
    """Query Ollama API"""
    start = time.time()
    print(f"\n{'─'*60}")
    print(f"  → PROMPT ({len(prompt)} chars, max_tokens={max_tokens}):")
    print(f"{'─'*60}")
    print(prompt)
    print(f"{'─'*60}")
    
    try:
        print(f"  → RESPONSE:")
        print(f"{'─'*60}")
        
        response_content = ""
        
        stream = ollama.chat(
            model=model_name, 
            messages=[{"role": "user", "content": prompt}], 
            stream=True,
            options= {
                "num_predict": max_tokens,
                'num_ctx': 8192, # Set the total context window size
                "temperature": 0.7
            })
        
        for chunk in stream:
            if 'message' in chunk and 'content' in chunk['message']:
                content_chunk = chunk['message']['content']
                print(content_chunk, end='', flush=True)
                response_content += content_chunk
        
        print(f"{'─'*60}")
        end = time.time()
        print(f"  ✓ Response generated in {end - start:.2f} seconds")
        return response_content.strip()
    except Exception as e:
        end = time.time()
        print(f"  ✗ Error querying Ollama: {type(e).__name__}: {e} (after {end - start:.2f} seconds)")
        raise e

# ============================================================================
# VALIDATION
# ============================================================================

def validate_with_model(model_name: str, card1: dict, card2: dict, qa: dict):
    """
    Ask the model to validate its own comparison answer
    
    Returns: (is_valid: bool, reason: str, score: int)
    """
    question = qa.get('question', '')
    answer = qa.get('answer', '')
    
    validation_prompt = build_card_validation_prompt(card1, card2, question, answer)

    try:
        response = query_ollama(model_name, validation_prompt)
        
        # Parse JSON response - handle common formatting issues
        response = response.replace("```json", "").replace("```", "").strip()
        
        # Try to extract JSON if there's extra text
        if not response.startswith('{'):
            # Find first { and last }
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                response = response[start:end+1]
        
        result = json.loads(response)
        
        score = result.get('score', 0)
        is_acceptable = result.get('is_acceptable', False)
        missing_info = result.get('missing_info', '')
        errors = result.get('errors', '')
        mechanical_accuracy = result.get('mechanical_accuracy', '')
        cost_comparison_correct = result.get('cost_comparison_correct', '')
        
        # Build detailed reason string
        reason_parts = []
        
        if errors:
            reason_parts.append(f"Errors: {errors}")
        
        if missing_info:
            reason_parts.append(f"Missing: {missing_info}")
        
        if mechanical_accuracy and 'incorrect' in mechanical_accuracy.lower():
            reason_parts.append(f"Mechanics: {mechanical_accuracy}")
        
        if cost_comparison_correct and 'incorrect' in cost_comparison_correct.lower():
            reason_parts.append(f"Costs: {cost_comparison_correct}")
        
        # Additional validation: if score is low, flag it
        if score < 7 and not errors:
            reason_parts.append(f"Low score ({score}/10)")
        
        # Build final reason
        if not is_acceptable or reason_parts:
            reason = "; ".join(reason_parts) if reason_parts else f"Score too low ({score}/10)"
        else:
            reason = "OK"
        
        # Extra safety check: if there are errors mentioned, force rejection
        if errors and errors.lower() not in ['none', 'n/a', '']:
            is_acceptable = False
            score = min(score, 4)  # Cap score at 4 if there are errors
        
        # Extra safety check: if mechanical accuracy is wrong, force rejection
        if mechanical_accuracy and any(word in mechanical_accuracy.lower() 
                                       for word in ['no', 'incorrect', 'wrong', 'false']):
            is_acceptable = False
            score = min(score, 4)
        
        return is_acceptable, reason, score
    
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Failed to parse validation JSON: {e}")
        print(f"    Raw response: {response[:200]}...")
        # Be conservative - REJECT if we can't validate
        # (Changed from accepting by default)
        return False, f"Validation parse failed: {str(e)}", 0
    
    except Exception as e:
        print(f"    ⚠️  Validation error: {e}")
        # Be conservative - REJECT if validation fails
        return False, f"Validation error: {str(e)}", 0


def validate_qa(question: str, answer: str, context: str = "", category: str = "") -> tuple:
    """
    Generic Q&A validator — calls the model to score any question/answer pair.

    Used by all generation functions that lack card-specific validation.
    `context` should contain the source material the answer is grounded in
    (rule text, article content, archetype description, etc.).

    Returns: (is_valid: bool, reason: str, score: int)
    """
    prompt = build_qa_validation_prompt(question, answer, context, category)

    try:
        response = query_ollama(MODEL_NAME, prompt)
        response = response.replace("```json", "").replace("```", "").strip()
        if not response.startswith('{'):
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                response = response[start:end+1]

        result = json.loads(response)
        score = result.get('score', 0)
        is_acceptable = result.get('is_acceptable', False)
        errors = result.get('errors', '')
        reason = result.get('reason', f"Score {score}/10")

        # Force reject if errors mentioned
        if errors and errors.lower() not in ['none', 'n/a', '']:
            is_acceptable = False
            score = min(score, 4)

        return is_acceptable and score >= 7, reason, score

    except json.JSONDecodeError as e:
        print(f"    ⚠️  Validation JSON parse failed: {e}")
        return False, f"Validation parse failed: {str(e)}", 0
    except Exception as e:
        print(f"    ⚠️  Validation error: {e}")
        return False, f"Validation error: {str(e)}", 0