
import os
import sys
import time
from typing import Iterator
import ollama
import json
import re
from .constants import MTG_NOTATION_LEGEND, SYSTEM_MESSAGE, VALIDATION_CHECKLIST, VALIDATION_SCORING_GUIDE
from .models import Model, ModelProvider
from anthropic import Anthropic, Stream
from openai import OpenAI

# =============================================================================
# MODEL QUERYING
# =============================================================================

class QueryModel():
    def __init__(self):
        self.anthropic_client: Anthropic | None = None
        self._last_elapsed_ms = 0

    def query(self, model: Model, prompt: str, max_tokens=8192, purpose: str = ""):
        """Query Ollama API"""
        start = time.time()
        print(f"\n{'─'*60}")
        print(f"  → PROMPT ({len(prompt)} chars, max_tokens={max_tokens}):")
        print(f"{'─'*60}")
        print(prompt)
        print(f"{'─'*60}")
        
        try:
            if model.provider == ModelProvider.ANTHROPIC:
                anthropic_key = model.api_key or os.getenv("ANTHROPIC_KEY")
                self.anthropic_client = Anthropic(api_key=anthropic_key) if not self.anthropic_client else self.anthropic_client

            purpose_label = f" [{purpose}]" if purpose else ""
            print(f"  → MODEL{purpose_label}: {model.name} ({model.provider.value}, host={model.provider_url})")
            print(f"  → RESPONSE:")
            print(f"{'─'*60}")
            
            response_content = ""
            #thinking_content = ""
                        
            if model.provider == ModelProvider.ANTHROPIC:
                time.sleep(1) # because of anthropic rater limits
                with self.anthropic_client.messages.stream(max_tokens=max_tokens, # type: ignore
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    model=model.name,
                    temperature=0.7) as stream:
                        for event in stream:
                            if event.type == "content_block_delta":
                                # Extract the new text chunk
                                new_text = event.delta.text # type: ignore
                                
                                # Append to full response
                                response_content += new_text
                                
                                # Print ONLY the new text (not the event object)
                                sys.stderr.write(new_text)
                                sys.stderr.flush()
            elif model.provider == ModelProvider.OPENAI:
                openai_key = model.api_key or os.getenv("OPENAI_API_KEY") or "none"
                client = OpenAI(base_url=model.provider_url, api_key=openai_key)
                stream = client.chat.completions.create(
                    model=model.name,
                    messages=[
                        {"role": "user", "content": prompt}],
                    stream=True,
                    max_tokens=max_tokens,
                    #temperature=1.0,
                    #top_p=0.95,
                    #presence_penalty=1.5,
                    #extra_body={
                    #    "top_k": 20,
                    #    "min_p": 0.0,
                    #    "repetition_penalty": 1.0,
                    #    "chat_template_kwargs": {"enable_thinking": True},
                    #    "max_context_length": max_tokens * 2
                    #}
                )
                
                for chunk in stream:
                    if chunk.choices:
                        if (hasattr(chunk.choices[0].delta, "reasoning_content") and chunk.choices[0].delta.reasoning_content is not None): # type: ignore
                            content_chunk = chunk.choices[0].delta.reasoning_content # type: ignore
                            sys.stderr.write(content_chunk)
                            sys.stderr.flush()
                            #thinking_content += content_chunk
                        if chunk.choices[0].delta.content is not None: # type: ignore
                            content_chunk = chunk.choices[0].delta.content
                            sys.stderr.write(content_chunk)
                            sys.stderr.flush()
                            response_content += content_chunk
                
            else:
                client = ollama.Client(host=model.provider_url) 
                stream = client.chat(
                    model=model.name, 
                    messages=[{"role": "user", "content": prompt}], 
                    stream=True,
                    options= {
                        "num_predict": max_tokens,
                        'num_ctx': max_tokens * 2, # Set the total context window size
                        "temperature": 1.0,
                        "top_p": 0.95,
                        "top_k": 20,
                        "min_p": 0.0,
                        "presence_penalty": 1.5,
                        "repetition_penalty": 1.0,
                        "chat_template_kwargs": {"enable_thinking": False}
                    })
            
                for chunk in stream:
                    if 'message' in chunk and 'content' in chunk['message']:
                        content_chunk = chunk['message']['content']
                        sys.stderr.write(content_chunk)
                        sys.stderr.flush()
                        response_content += content_chunk
            
            print(f"{'─'*60}")
            end = time.time()
            self._last_elapsed_ms = int((end - start) * 1000)
            print(f"  ✓ Response generated in {end - start:.2f} seconds")
            response_content = re.sub(r'<think>.*?</think>', '', response_content, flags=re.DOTALL).strip()
            response_content = response_content.replace("```json", "").replace("```", "").strip()
            return response_content
        except Exception as e:
            end = time.time()
            self._last_elapsed_ms = int((end - start) * 1000)
            print(f"  ✗ Error querying model: {type(e).__name__}: {e} (after {end - start:.2f} seconds)")
            raise e

    # ============================================================================
    # VALIDATION
    # ============================================================================

    def validate_with_model(self, model: Model, card1: dict, card2: dict, qa: dict):
        """
        Ask the model to validate its own comparison answer
        
        Returns: (is_valid: bool, reason: str, score: int)
        """
        question = qa.get('question', '')
        answer = qa.get('answer', '')
        
        validation_prompt = self.__build_card_validation_prompt(card1, card2, question, answer)

        try:
            response = self.query(model, validation_prompt, purpose="VALIDATION")
            
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


    def validate_qa(self, validation_model: Model, question: str, answer: str, context: str = "", category: str = "", enable_extra_validation: bool = True, trace_round: dict | None = None) -> tuple[bool, str | None, float | None]:
        """
        Generic Q&A validator — calls the model to score any question/answer pair.

        Used by all generation functions that lack card-specific validation.
        `context` should contain the source material the answer is grounded in
        (rule text, article content, archetype description, etc.).

        Returns: (is_valid: bool, reason: str, score: float)
        """
        prompt = self.__build_qa_validation_prompt(question, answer, context, category, enable_extra_validation)

        try:
            response = self.query(validation_model, prompt, purpose="VALIDATION")
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

            if trace_round is not None:
                trace_round.update({
                    "prompt": prompt,
                    "response": response,  # raw response before JSON extraction
                    "parsed_ok": True,
                    "score": score,
                    "is_acceptable": is_acceptable and score >= 7,
                    "errors": errors,
                    "missing_info": result.get('missing_info', ''),
                    "reason": reason,
                    "verification_checklist": result.get('verification_checklist', None),
                    "latency_ms": self._last_elapsed_ms,
                })

            return is_acceptable and score >= 7, reason, score

        except json.JSONDecodeError as e:
            print(f"    ⚠️  Validation JSON parse failed: {e}")
            if trace_round is not None:
                trace_round.update({
                    "prompt": prompt, "response": response, "parsed_ok": False,
                    "score": 0, "is_acceptable": False, "errors": str(e),
                    "missing_info": "", "reason": f"Validation parse failed: {e}",
                    "verification_checklist": None, "latency_ms": self._last_elapsed_ms,
                })
            return False, f"Validation parse failed: {str(e)}", 0
        except Exception as e:
            print(f"    ⚠️  Validation error: {e}")
            if trace_round is not None:
                trace_round.update({
                    "prompt": prompt, "response": "", "parsed_ok": False,
                    "score": 0, "is_acceptable": False, "errors": str(e),
                    "missing_info": "", "reason": f"Validation error: {e}",
                    "verification_checklist": None, "latency_ms": self._last_elapsed_ms,
                })
            return False, f"Validation error: {str(e)}", 0

    def regenerate_answer(self, generation_model: Model, question: str, old_answer: str, reason: str, score: float | None, context: str = "", category: str = "", sibling_feedback: str = "", trace_regeneration: dict | None = None) -> str | None:
        """
        Ask the generation model to produce a corrected answer based on validation feedback.
        Returns the new answer string, or None if regeneration failed.
        sibling_feedback: optional context from corrections already applied to sibling Q&As
        in the same batch (e.g. "Q1 was rejected for wrong trigger order — apply same fix here").
        """
        context_block = (
            f"\nSource material the answer should be grounded in:\n{context}\n"
            if context else ""
        )

        sibling_block = (
            f"\nIMPORTANT — corrections already applied to other answers in this batch:\n{sibling_feedback}\nApply the same corrections to your answer.\n"
            if sibling_feedback else ""
        )

        prompt = f"""{SYSTEM_MESSAGE}

You previously generated an answer to the following question. It was validated and found to have issues.

Question: {question}

Previous answer: {old_answer}

Validation feedback: {reason} (Score: {score}/10)
Category: {category or 'general'}{context_block}{sibling_block}

Please provide a corrected answer that addresses the validation feedback. Be concise, accurate, and directly answer the question.

Output ONLY a JSON object:
{{
"answer": "<corrected answer text>"
}}

Output ONLY valid JSON, no other text."""

        try:
            response = self.query(generation_model, prompt, purpose="REGENERATION")
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('{'):
                start = response.find('{')
                end = response.rfind('}')
                if start != -1 and end != -1:
                    response = response[start:end+1]

            result = json.loads(response)
            new_answer = result.get('answer', '').strip()
            if new_answer:
                if trace_regeneration is not None:
                    trace_regeneration.update({
                        "prompt": prompt,
                        "response": response,
                        "parsed_ok": True,
                        "new_answer": new_answer,
                        "latency_ms": self._last_elapsed_ms,
                    })
                return new_answer
            else:
                print("    ⚠️  Regeneration returned empty answer.")
                if trace_regeneration is not None:
                    trace_regeneration.update({
                        "prompt": prompt,
                        "response": response,
                        "parsed_ok": True,
                        "new_answer": None,
                        "latency_ms": self._last_elapsed_ms,
                    })
                return None
        except json.JSONDecodeError as e:
            print(f"    ⚠️  Regeneration JSON parse failed: {e}")
            if trace_regeneration is not None:
                trace_regeneration.update({
                    "prompt": prompt, "response": response, "parsed_ok": False,
                    "new_answer": None, "latency_ms": self._last_elapsed_ms,
                })
            return None
        except Exception as e:
            print(f"    ⚠️  Regeneration error: {e}")
            if trace_regeneration is not None:
                trace_regeneration.update({
                    "prompt": prompt, "response": "", "parsed_ok": False,
                    "new_answer": None, "latency_ms": self._last_elapsed_ms,
                })
            return None

    def __build_qa_validation_prompt(self, question: str, answer: str, context: str = "", category: str = "", enable_extra_validation: bool = True) -> str:
        """Build the generic Q&A validation prompt used by validate_qa()."""
        
        context_block = (
            f"\nSource material the answer should be grounded in:\n{context}\n"
            if context else ""
        )
        
        verification_block = (
            """
    <rules>
    Before scoring, complete a verification checklist.
    Work through the answer sentence by sentence. For each mechanical claim, find the exact supporting text in the source material above.

    - If a claim involves a single card, quote the exact relevant text from that card.
    - If a claim involves multiple cards working together, quote the relevant text from ALL cards involved before rendering a verdict. Do not mark a claim UNSUPPORTED simply because one card's text alone does not support it — check all relevant cards.
    - If a claim is supported by the combined source text of all relevant cards, mark it SUPPORTED.
    - If source text directly contradicts the claim, mark it CONTRADICTED.
    - If no source text exists across any relevant cards for the claim, mark it UNSUPPORTED.
    - Inferred conclusions that are mechanically sound and follow directly from the source (e.g. "a player at 1 life will die to any combat damage") may be marked SUPPORTED if the inference requires no additional cards or rules beyond basic game rules. Note the inference explicitly in source_text as "BASIC GAME RULE: <explanation>".
    - Any CONTRADICTED or UNSUPPORTED verdict is an automatic reject regardless of score.
    - For combo_query category: verify that the sequence of events described in the answer matches the order of the numbered steps in the provided combo. Compare each step explicitly. A correct description of individual triggers in the wrong order is a factual error and must be marked CONTRADICTED.
    </rules>
    """
            if enable_extra_validation and context else ""
        )

        verification_json = (
            """"verification_checklist": [
        {
        "claim": "<the mechanical claim>",
        "source_text": "<exact quote from source material, or NOT FOUND IN SOURCE>",
        "verdict": "<SUPPORTED | CONTRADICTED | UNSUPPORTED>"
        }
    ],
    """
            if enable_extra_validation and context else ""
        )

        return f"""
    {SYSTEM_MESSAGE}
    
    {MTG_NOTATION_LEGEND}
    
    Category: {category or 'general'}{context_block}{verification_block}
    Question: {question}

    Answer to validate:
    {answer}

    Score this answer on:
    1. Factual accuracy — Is everything correct? Wrong mana costs, wrong card names, wrong mechanics = instant reject.
    2. Completeness — Does it fully answer the question without important gaps?
    3. Usefulness — Is this a good training example? Clear and specific, not vague or generic?
    4. Grounding — Is it grounded in the provided context, or hallucinating details?

    Scoring guide:
    - 9-10: Excellent, publish as-is
    - 7-8: Good, acceptable for training
    - 5-6: Too vague, incomplete, or minor errors — reject
    - 1-4: Factual errors or hallucinations — reject

    Respond ONLY with JSON:
    {{
    {verification_json}"score": <1-10>,
    "is_acceptable": <true/false>,
    "errors": "<factual errors if any, or 'none'>",
    "missing_info": "<what is missing or vague, if anything. If score is 7 or above with no errors, leave blank.>",
    "reason": "<one sentence summary. If score is 7 or above with no errors, leave blank.>"
    }}

    Output ONLY valid JSON, no other text."""
    
    def __build_card_validation_prompt(self, card1: dict, card2: dict, question: str, answer: str) -> str:
        """Build validation prompt for card comparison answers."""
        
        prompt = f"""{MTG_NOTATION_LEGEND}

    You are a Magic: The Gathering expert reviewing a comparison answer for accuracy.

    Card 1: {card1.get('name', '')}
    Type: {card1.get('type', 'N/A')}
    Text: {card1.get('text', '')}
    Cost: {card1.get('manaCost', 'N/A')}

    Card 2: {card2.get('name', '')}
    Type: {card2.get('type', 'N/A')}
    Text: {card2.get('text', '')}
    Cost: {card2.get('manaCost', 'N/A')}

    Question: {question}

    Answer to validate:
    {answer}

    {VALIDATION_CHECKLIST}

    Review this answer for:
    1. Accuracy - Does it correctly describe both cards' mechanics AND types?
    2. Completeness - Does it mention ALL important abilities AND type-specific concerns?
    3. Usefulness - Does it give clear, context-dependent guidance?
    4. Factual correctness - Are there any outright errors or misconceptions?

    Respond ONLY with JSON:
    {{
    "score": <1-10>,
    "is_acceptable": <true/false>,
    "missing_info": "<what critical info is missing, if any>",
    "errors": "<factual errors, if any>",
    "mechanical_accuracy": "<are the card mechanics described correctly?>",
    "cost_comparison_correct": "<are costs compared accurately?>",
    "card_types_addressed": "<are card types mentioned and their implications explained?>"
    }}

    {VALIDATION_SCORING_GUIDE}

    Output ONLY valid JSON, no other text."""
        return prompt
    
    
# We recommend using the following set of sampling parameters for generation

# Thinking mode for general tasks: temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
# Thinking mode for precise coding tasks (e.g. WebDev): temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
# Instruct (or non-thinking) mode for general tasks: temperature=0.7, top_p=0.8, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
# Instruct (or non-thinking) mode for reasoning tasks: temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
# Please note that the support for sampling parameters varies according to inference frameworks.