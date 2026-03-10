import os
import time
import pandas as pd
from playwright.sync_api import sync_playwright
from datetime import datetime
from supabase import create_client, Client

def scrape_hevy_data():
    """
    Logs into Hevy web dashboard, downloads the CSV export, and returns the parsed data.
    """
    username = os.environ.get("HEVY_USERNAME")
    password = os.environ.get("HEVY_PASSWORD")
    
    if not username or not password:
        raise ValueError("HEVY_USERNAME or HEVY_PASSWORD not set")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to Hevy login...")
        page.goto("https://www.hevyapp.com/login/")
        
        page.fill("input[name='email']", username)
        page.fill("input[name='password']", password)
        page.click("button[type='submit']")
        
        # Wait for navigation to dashboard
        page.wait_for_url("https://www.hevyapp.com/dashboard/")
        print("Logged in successfully.")

        # Navigate to settings/export
        # Note: Hevy's export is often at https://www.hevyapp.com/settings/export
        page.goto("https://www.hevyapp.com/settings/export")
        
        print("Starting CSV export...")
        # Wait for the download button and trigger it
        with page.expect_download() as download_info:
            page.click("button:has-text('Export CSV')")
        download = download_info.value
        
        # Save the file temporarily
        csv_path = "hevy_workouts.csv"
        download.save_as(csv_path)
        print(f"Downloaded CSV to {csv_path}")

        browser.close()
        return csv_path

def parse_hevy_csv(csv_path: str):
    """
    Parses the Hevy CSV and returns a list of dictionaries ready for Supabase insertion.
    """
    df = pd.read_csv(csv_path)
    
    # Hevy CSV format typically includes columns like: 
    # 'Date', 'Workout Name', 'Exercise Name', 'Set Order', 'Weight', 'Reps', 'RPE', 'Distance', 'Seconds', 'Notes', 'Workout Notes'
    # We'll map these to our schema
    
    workouts = []
    for _, row in df.iterrows():
        # Hevy dates are usually like '2023-11-01 18:30:22'
        dt = pd.to_datetime(row['Date'])
        
        workout_data = {
            "date": dt.date().isoformat(),
            "exercise_name": row['Exercise Name'],
            "sets": 1, # We'll treat each row as a set entry
            "reps": int(row['Reps']) if not pd.isna(row['Reps']) else 0,
            "weight": float(row['Weight']) if not pd.isna(row['Weight']) else 0,
            "volume_kg": (float(row['Weight']) if not pd.isna(row['Weight']) else 0) * (int(row['Reps']) if not pd.isna(row['Reps']) else 0),
            "hevy_workout_id": row.get('Workout Name', 'Unknown') + "_" + dt.isoformat()
        }
        workouts.append(workout_data)
        
    return workouts

def sync_to_supabase(workouts):
    """
    Upserts workout data into Supabase.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("Supabase credentials not found. Skipping sync.")
        return

    supabase: Client = create_client(url, key)
    
    print(f"Syncing {len(workouts)} sets to Supabase...")
    for workout in workouts:
        # Use upsert with a unique constraint if possible, or just insert
        # For this demo, we'll use a simple insert or check for existence
        try:
            supabase.table("workouts").upsert(workout, on_conflict="hevy_workout_id, exercise_name").execute()
        except Exception as e:
            print(f"Error syncing row: {e}")

if __name__ == "__main__":
    try:
        csv_file = scrape_hevy_data()
        data = parse_hevy_csv(csv_file)
        sync_to_supabase(data)
        print("Hevy sync completed.")
    except Exception as e:
        print(f"Sync failed: {e}")
