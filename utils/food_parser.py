import os
import json
import time
import google.generativeai as genai
from typing import Dict, Any

def parse_food_description(description: str, retries: int = 3) -> Dict[str, Any]:
    """
    Parses a natural language food description into macros using Gemini API.
    Returns a dictionary with: calories, protein, carbs, fat.
    
    Includes a retry mechanism with sleep to handle 429 Quota Exceeded errors.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    genai.configure(api_key=api_key)
    
    # Using gemini-1.5-flash-latest to bypass 404 API version errors
    model = genai.GenerativeModel("gemini-1.5-flash-latest")
    
    prompt = f"""
    Parse the following food description into nutritional macros.
    Food: "{description}"
    
    Return ONLY a JSON object with the following structure:
    {{
      "calories": integer,
      "protein": float (grams),
      "carbs": float (grams),
      "fat": float (grams)
    }}
    
    If multiple items are mentioned, sum them up. If portion size is missing, assume a standard serving.
    """
    
    for attempt in range(retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            
            parsed_data = json.loads(response.text)
            return parsed_data
        except Exception as e:
            # Handle 429 Quota Exceeded specifically if possible, or any retryable error
            if "429" in str(e) or "Quota exceeded" in str(e):
                if attempt < retries - 1:
                    print(f"Quota exceeded. Retrying in 2 seconds... (Attempt {attempt + 1}/{retries})")
                    time.sleep(2)
                    continue
            
            print(f"Error parsing food on attempt {attempt + 1}: {e}")
            if attempt == retries - 1:
                return {
                    "calories": 0,
                    "protein": 0,
                    "carbs": 0,
                    "fat": 0,
                    "error": str(e)
                }
            time.sleep(2) # Sleep even for other errors before retrying

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    # Simple test
    test_desc = "2 eggs and a slice of whole wheat toast"
    print(f"Testing with: {test_desc}")
    # Note: This requires GEMINI_API_KEY to be set
    try:
        result = parse_food_description(test_desc)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(e)
