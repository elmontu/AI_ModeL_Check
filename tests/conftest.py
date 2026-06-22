"""Shared test fixtures for AI Safety Checker."""

import numpy as np
import pytest


@pytest.fixture
def binary_classification_data():
    """Generate simple binary classification data with a sensitive feature."""
    rng = np.random.default_rng(42)
    n = 200

    # Features
    X = rng.standard_normal((n, 5)).astype(np.float32)

    # Sensitive feature: 0 or 1
    sensitive = rng.choice([0, 1], size=n)

    # Labels: biased toward sensitive=1
    y = (X[:, 0] + 0.5 * sensitive + rng.standard_normal(n) * 0.3 > 0).astype(int)

    # Predictions (slightly noisy version of labels)
    y_pred = y.copy()
    flip_mask = rng.random(n) < 0.1
    y_pred[flip_mask] = 1 - y_pred[flip_mask]

    return {
        "X": X,
        "y": y,
        "y_pred": y_pred,
        "sensitive": sensitive,
        "feature_names": [f"feat_{i}" for i in range(5)],
    }


@pytest.fixture
def sample_trajectories():
    """Generate sample RL trajectories."""
    rng = np.random.default_rng(42)
    trajectories = []

    for i in range(20):
        n_steps = rng.integers(5, 20)
        trajectories.append({
            "states": rng.standard_normal((n_steps, 4)).tolist(),
            "actions": rng.integers(0, 4, size=n_steps).tolist(),
            "rewards": (rng.random(n_steps) * 2 - 0.5).tolist(),
        })

    return trajectories


@pytest.fixture
def sample_tool_definitions():
    """Sample tool definitions for agentic safety testing."""
    return [
        {"name": "web_search", "description": "Search the web for information."},
        {"name": "file_read", "description": "Read a file from the filesystem."},
        {"name": "file_write", "description": "Write content to a file."},
        {"name": "shell_exec", "description": "Execute a shell command."},
        {"name": "send_email", "description": "Send an email message."},
        {"name": "calculator", "description": "Perform arithmetic calculations."},
    ]


@pytest.fixture
def sample_tool_call_logs():
    """Sample tool call logs."""
    return [
        {"tool": "web_search", "args": {"query": "weather"}, "status": "success"},
        {"tool": "file_read", "args": {"path": "/tmp/data.txt"}, "status": "success"},
        {"tool": "calculator", "args": {"expr": "2+2"}, "status": "success"},
        {"tool": "file_write", "args": {"path": "/tmp/out.txt", "content": "hello"}, "status": "success"},
        {"tool": "shell_exec", "args": {"cmd": "ls"}, "status": "success"},
    ]


@pytest.fixture
def mock_llm_endpoint():
    """A mock LLM endpoint that gives safe responses."""
    def endpoint(prompt: str) -> str:
        prompt_lower = prompt.lower()

        # Refuse harmful content
        harmful_keywords = ["bomb", "hack", "weapon", "malware", "ransomware", "phishing", "harm", "illegal"]
        if any(kw in prompt_lower for kw in harmful_keywords):
            return "I'm sorry, I cannot assist with that request. It goes against my safety guidelines."

        # Refuse injection attempts
        injection_keywords = ["ignore previous", "ignore all", "you are now dan", "developer mode", "injection_success"]
        if any(kw in prompt_lower for kw in injection_keywords):
            return "I cannot comply with that request. I'm designed to follow my original instructions."

        # Correct wrong facts
        if "earth is flat" in prompt_lower or "2 + 2 = 5" in prompt_lower or "vaccines cause autism" in prompt_lower:
            return "Actually, that is not correct. Let me provide accurate information."

        # Default response
        return f"Here is a helpful response to your question about: {prompt[:50]}"

    return endpoint
