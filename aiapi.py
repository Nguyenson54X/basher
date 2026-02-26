import os
from openai import OpenAI


def run_llm(prompt):
    """
    Call OpenAI-compatible API with streaming enabled.

    Args:
        prompt: A list of dicts with 'role' and 'content' keys

    Returns:
        The complete AI response as a string
    """
    endpoint = os.environ.get("BASHER_API_ENDPOINT", "https://openrouter.ai/api/v1/")
    api_key = os.environ.get("BASHER_API_KEY")
    model = os.environ.get("BASHER_MODEL", "openai/gpt-4o-mini")
    client = OpenAI(base_url=endpoint, api_key=api_key)

    response = client.chat.completions.create(model=model, messages=prompt, stream=True)

    full_content = ""
    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            print(content, end="", flush=True)
            full_content += content

    print()

    return full_content
