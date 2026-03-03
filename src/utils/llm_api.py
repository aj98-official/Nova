import asyncio
import os
from google import genai

async def get_llm_response(api_key: str, api_url: str, model_name: str, system_prompt: str, query: str) -> str | None:
    """
    Fetches a response from the Gemini API using the google-genai SDK.

    Args:
        api_key: The API key for Gemini.
        api_url: Unused (kept for backward compatibility with callers).
        model_name: The Gemini model to use (e.g. "gemini-3-flash-preview").
        system_prompt: The system prompt string to guide the LLM.
        query: The user's query string.

    Returns:
        The content of the API response as a string, or an error message string.
    """
    if not all([api_key, model_name]):
        print("Error: LLM API Key or Model Name is not configured.")
        return "Error: LLM is not properly configured. Please check configuration."

    try:
        client = genai.Client(api_key=api_key)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=query,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )

        if response and response.text:
            return response.text.strip()
        else:
            print(f"Empty response from Gemini: {response}")
            return "Error: Received an empty response from Gemini."
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return f"Error: {e}"
