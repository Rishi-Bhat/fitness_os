import os
import json
import google.generativeai as genai
from typing import Dict, Any

def parse_food_description(description: str) -> Dict[str, Any]:
    """
    Parses a natural language food description into macros using Gemini API.
    Returns a dictionary with: calories, protein, carbs, fat.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    genai.configure(api_key=api_key)
    
    # Using gemini-pro as a last resort
    model = genai.GenerativeModel("gemini-pro")
    
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
        print(f"Error parsing food: {e}")
        return {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            "error": str(e)
        }

if __name__ == "__main__":
    # Simple test
    test_desc = "2 eggs and a slice of whole wheat toast"
    print(f"Testing with: {test_desc}")
    # Note: This requires GEMINI_API_KEY to be set
    try:
        result = parse_food_description(test_desc)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(e)
