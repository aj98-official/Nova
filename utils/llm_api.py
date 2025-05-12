import aiohttp
import os

async def get_llm_response(api_key: str, api_url: str, model_name: str, system_prompt: str, query: str) -> str | None:
    """
    Asynchronously fetches a response from a configured LLM API using a specific system prompt.

    Args:
        api_key: The API key for the LLM service.
        api_url: The endpoint URL for the LLM API.
        model_name: The specific model to use.
        system_prompt: The system prompt string to guide the LLM.
        query: The user's query string.

    Returns:
        The content of the API response as a string, or an error message string.
    """
    # Check only for essential API call parameters here
    if not all([api_key, api_url, model_name]):
        print("Error: LLM API Key, URL, or Model Name is not configured.")
        return "Error: LLM is not properly configured. Please check configuration."
    # System prompt presence is handled by the caller

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    # Include the system prompt in the messages payload
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt}, # Use the passed system_prompt
            {"role": "user", "content": query}
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        content = data['choices'][0]['message']['content']
                        return content.strip()
                    except (KeyError, IndexError, TypeError) as e:
                        print(f"Error parsing LLM response structure: {e}\nData: {data}")
                        return "Error: Could not parse the response from the LLM."
                else:
                    error_text = await response.text()
                    print(f"LLM API Error: {response.status} - {error_text}")
                    try:
                        error_data = await response.json()
                        error_message = error_data.get('error', {}).get('message', error_text)
                        return f"Error: The LLM API returned status {response.status}. Details: {error_message}"
                    except:
                         return f"Error: The LLM API returned status {response.status}. Details: {error_text}"

    except aiohttp.ClientError as e:
        print(f"Network error calling LLM API: {e}")
        return "Error: Could not connect to the LLM API."
    except Exception as e:
        print(f"An unexpected error occurred in get_llm_response: {e}")
        return "Error: An unexpected error occurred while contacting the LLM."
