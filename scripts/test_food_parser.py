import os
import sys
from dotenv import load_dotenv

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.food_parser import parse_food_description

load_dotenv()

def test_food_parser():
    print("\n--- Testing Gemini Food Parser ---")
    test_cases = [
        "2 large eggs and a slice of toast",
        "a chipotle chicken bowl with double protein",
        "500ml of whole milk"
    ]
    
    for case in test_cases:
        print(f"\nParsing: '{case}'")
        result = parse_food_description(case)
        if "error" in result:
            print(f"❌ Failed: {result['error']}")
        else:
            print(f"✅ Success: {result['calories']} kcal | P: {result['protein']}g | C: {result['carbs']}g | F: {result['fat']}g")

if __name__ == "__main__":
    test_food_parser()
