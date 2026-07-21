"""Pytest configuration for synthetic data generation tests."""

import sys
from unittest.mock import MagicMock

# Mock external dependencies before any module imports
sys.modules['ollama'] = MagicMock()
sys.modules['anthropic'] = MagicMock()
sys.modules['openai'] = MagicMock()
sys.modules['pymongo'] = MagicMock()