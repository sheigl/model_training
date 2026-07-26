"""LLM client supporting Ollama, Anthropic, and OpenAI-compatible providers."""

from __future__ import annotations

import logging
import os
import re
import sys
import time

import ollama
from anthropic import Anthropic
from openai import OpenAI

logger = logging.getLogger(__name__)


class QueryModel:
    """Multi-provider LLM client with streaming support.

    Thin wrapper around Ollama, Anthropic, and OpenAI-compatible APIs.
    All validation logic lives in validator.py — this class only handles
    model querying and response streaming.
    """

    def __init__(
        self,
        model_name: str = "",
        provider_url: str | None = None,
        api_key: str | None = None,
    ):
        """Initialize with optional model defaults for convenience calling.

        Args:
            model_name: Default model name (used when query() is called without a Model object).
            provider_url: Default provider URL.
            api_key: Default API key.
        """
        self.model_name = model_name
        self.provider_url = provider_url
        self.api_key = api_key
        self._anthropic_client: Anthropic | None = None
        self._last_elapsed_ms: int = 0

    # ------------------------------------------------------------------
    # QUERY — accepts either a Model object or raw string params
    # ------------------------------------------------------------------

    def query(
        self, model_or_system: str | "Model", prompt: str, max_tokens: int = 8192, purpose: str = ""
    ) -> str:
        """Query an LLM and stream the response to stderr.

        Can be called in two ways:
            qm.query(model_obj, prompt)           # with Model object
            qm.query(system_message, prompt)      # uses stored model_name/provider_url/api_key

        Returns the full response content as a string (thinking tags stripped).
        """
        from .models import Model, ModelProvider

        # If first arg is a Model instance, use it directly
        if isinstance(model_or_system, Model):
            model = model_or_system
        else:
            # First arg is system_message string — build Model from stored defaults
            system_msg = model_or_system
            model = Model(
                name=self.model_name or "qwen2.5:14b",
                type="generation",  # type: ignore[arg-type]
                provider_url=self.provider_url,
                api_key=self.api_key,
            )
            # Prepend system message to prompt for non-Model calls
            if system_msg and system_msg.strip():
                prompt = f"{system_msg}\n\n{prompt}"

        start = time.time()
        print(f"\n{'─' * 60}")
        print(f"  → PROMPT ({len(prompt)} chars, max_tokens={max_tokens}):")
        print(f"{'─' * 60}")
        print(prompt)
        print(f"{'─' * 60}")

        try:
            if model.provider == ModelProvider.ANTHROPIC:
                api_key = model.api_key or os.getenv("ANTHROPIC_KEY", "")
                self._anthropic_client = (
                    Anthropic(api_key=api_key)
                    if not self._anthropic_client
                    else self._anthropic_client
                )

            purpose_label = f" [{purpose}]" if purpose else ""
            print(
                f"  → MODEL{purpose_label}: {model.name} "
                f"({model.provider.value}, host={model.provider_url})"
            )
            print("  → RESPONSE:")
            print(f"{'─' * 60}")

            response_content = ""

            if model.provider == ModelProvider.ANTHROPIC:
                time.sleep(1)  # rate-limit cushion
                with self._anthropic_client.messages.stream(  # type: ignore[attr-defined]
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    model=model.name,
                    temperature=0.7,
                ) as stream:
                    for event in stream:
                        if event.type == "content_block_delta":
                            chunk = event.delta.text  # type: ignore[attr-defined]
                            response_content += chunk
                            sys.stderr.write(chunk)
                            sys.stderr.flush()

            elif model.provider == ModelProvider.OPENAI:
                api_key = model.api_key or os.getenv("OPENAI_API_KEY", "none")
                client = OpenAI(base_url=model.provider_url, api_key=api_key)
                stream = client.chat.completions.create(
                    model=model.name,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    max_tokens=max_tokens,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    # Skip reasoning/thinking content
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:  # type: ignore[attr-defined]
                        sys.stderr.write(delta.reasoning_content)  # type: ignore[attr-defined]
                        sys.stderr.flush()
                    elif delta.content is not None:  # type: ignore[attr-defined]
                        response_content += delta.content  # type: ignore[attr-defined]
                        sys.stderr.write(delta.content)  # type: ignore[attr-defined]
                        sys.stderr.flush()

            else:
                # Ollama (default)
                client = ollama.Client(host=model.provider_url or "http://127.0.0.1:11434")
                stream = client.chat(
                    model=model.name,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    options={
                        "num_predict": max_tokens,
                        "num_ctx": max_tokens * 2,
                        "temperature": 1.0,
                        "top_p": 0.95,
                        "top_k": 20,
                        "min_p": 0.0,
                        "presence_penalty": 1.5,
                        "repetition_penalty": 1.0,
                    },
                )
                for chunk in stream:
                    if "message" in chunk and "content" in chunk["message"]:
                        response_content += chunk["message"]["content"]
                        sys.stderr.write(chunk["message"]["content"])
                        sys.stderr.flush()

            print(f"{'─' * 60}")
            elapsed = time.time() - start
            self._last_elapsed_ms = int(elapsed * 1000)
            print(f"  ✓ Response generated in {elapsed:.2f} seconds")

            # Strip thinking tags and JSON fences
            response_content = re.sub(r"<think>.*?</think>", "", response_content, flags=re.DOTALL).strip()
            response_content = response_content.replace("```json", "").replace("```", "").strip()
            return response_content

        except Exception as e:
            elapsed = time.time() - start
            self._last_elapsed_ms = int(elapsed * 1000)
            logger.error(
                "Error querying model %s: %s: %s (after %.2fs)",
                model.name, type(e).__name__, e, elapsed
            )
            raise
