"""Tests for aiapi module."""

import os
from unittest.mock import Mock, patch

import pytest

from aiapi import run_llm


class TestRunLLM:
    """Test cases for run_llm function."""

    @patch("aiapi.OpenAI")
    def test_run_llm_success(self, mock_openai_class):
        """Test successful LLM call with streaming response."""
        # Setup mock
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Create mock chunks simulating streaming response
        mock_chunk1 = Mock()
        mock_chunk1.choices = [Mock()]
        mock_chunk1.choices[0].delta.content = "Hello"

        mock_chunk2 = Mock()
        mock_chunk2.choices = [Mock()]
        mock_chunk2.choices[0].delta.content = " World"

        mock_chunk3 = Mock()
        mock_chunk3.choices = [Mock()]
        mock_chunk3.choices[0].delta.content = None  # End of stream

        mock_client.chat.completions.create.return_value = [
            mock_chunk1,
            mock_chunk2,
            mock_chunk3,
        ]

        # Test
        prompt = [{"role": "user", "content": "Say hello"}]
        result = run_llm(prompt)

        # Verify
        assert result == "Hello World"
        mock_client.chat.completions.create.assert_called_once_with(
            model="openai/gpt-4o-mini", messages=prompt, stream=True
        )

    @patch("aiapi.OpenAI")
    def test_run_llm_empty_response(self, mock_openai_class):
        """Test LLM call with empty response."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = []

        prompt = [{"role": "user", "content": "Test"}]
        result = run_llm(prompt)

        assert result == ""

    @patch.dict(
        os.environ,
        {
            "BASHER_API_ENDPOINT": "https://custom.api.com/v1/",
            "BASHER_API_KEY": "test-key",
            "BASHER_MODEL": "custom/model",
        },
    )
    @patch("aiapi.OpenAI")
    def test_run_llm_custom_config(self, mock_openai_class):
        """Test LLM call with custom environment configuration."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = []

        prompt = [{"role": "user", "content": "Test"}]
        run_llm(prompt)

        # Verify custom configuration was used
        mock_openai_class.assert_called_once_with(
            base_url="https://custom.api.com/v1/", api_key="test-key"
        )
        mock_client.chat.completions.create.assert_called_once_with(
            model="custom/model", messages=prompt, stream=True
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("aiapi.OpenAI")
    def test_run_llm_default_config(self, mock_openai_class):
        """Test LLM call with default configuration."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = []

        prompt = [{"role": "user", "content": "Test"}]
        run_llm(prompt)

        # Verify default values were used
        mock_openai_class.assert_called_once_with(
            base_url="https://openrouter.ai/api/v1/", api_key=None
        )
        mock_client.chat.completions.create.assert_called_once_with(
            model="openai/gpt-4o-mini", messages=prompt, stream=True
        )


class TestRunLLMErrorCases:
    """Test error handling in run_llm function."""

    @patch("aiapi.OpenAI")
    def test_run_llm_api_error(self, mock_openai_class):
        """Test handling of API errors."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        prompt = [{"role": "user", "content": "Test"}]
        with pytest.raises(Exception, match="API Error"):
            run_llm(prompt)
