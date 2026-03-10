import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai

# Load environment variables
load_dotenv()

def verify_supabase():
    print("\n--- Verifying Supabase Connection ---")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY not set.")
        return False
    try:
        supabase: Client = create_client(url, key)
        # Try to select from a table
        res = supabase.table("daily_metrics").select("*").limit(1).execute()
        print("[SUCCESS] Supabase connection successful!")
        return True
    except Exception as e:
        print(f"[FAIL] Supabase connection failed: {e}")
        return False

def verify_gemini():
    print("\n--- Verifying Gemini API ---")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set.")
        return False
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content("Say 'Hello Fitness OS' if you can read this.")
        print(f"[SUCCESS] Gemini API response: {response.text.strip()}")
        return True
    except Exception as e:
        print(f"[FAIL] Gemini API verification failed: {e}")
        return False

def check_env_vars():
    print("\n--- Checking Other Environment Variables ---")
    required = [
        "GOOGLE_FIT_CLIENT_ID", "GOOGLE_FIT_CLIENT_SECRET", "GOOGLE_FIT_REFRESH_TOKEN",
        "HEVY_USERNAME", "HEVY_PASSWORD"
    ]
    missing = [var for var in required if not os.environ.get(var)]
    if missing:
        print(f"[ERROR] Missing: {', '.join(missing)}")
        return False
    else:
        print("[SUCCESS] All required automation env vars are present.")
        return True

if __name__ == "__main__":
    s1 = verify_supabase()
    s2 = verify_gemini()
    s3 = check_env_vars()
    
    if s1 and s2 and s3:
        print("\n[READY] All core connections verified! Ready for module testing.")
    else:
        print("\n[WARNING] Some verifications failed. Please check your credentials.")
