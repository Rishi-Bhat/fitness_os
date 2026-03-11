import os
import time
import pandas as pd
from playwright.sync_api import sync_playwright
import subprocess
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def scrape_hevy_data():
    """
    Logs into Hevy web dashboard, downloads the CSV export, and returns the parsed data.
    """
    # Ensure Playwright browser is installed synchronously
    print("Ensuring Playwright browser is installed...")
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install Playwright browsers: {e}")

    username = os.environ.get("HEVY_USERNAME")
    password = os.environ.get("HEVY_PASSWORD")
    
    if not username or not password:
        raise ValueError("HEVY_USERNAME or HEVY_PASSWORD not set")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to Hevy login...")
        page.goto("https://hevy.com/login", wait_until="networkidle")
        
        # Take a screenshot for diagnostics
        page.screenshot(path="hevy_login_debug.png")
        
        try:
            # Using very simple but effective selectors based on the screenshot
            # The first input is usually email/username, the second is password
            page.wait_for_selector("input", timeout=10000)
            inputs = page.query_selector_all("input")
            if len(inputs) >= 2:
                inputs[0].fill(username)
                inputs[1].fill(password)
                inputs[1].press("Enter")
                print("Enter pressed on password field. Waiting for redirection...")
                time.sleep(10) # Give it more time for potentially slow login
                page.screenshot(path="hevy_post_login_debug_v2.png")
                
                # Check for error message
                if "Invalid email or password" in page.content():
                    print("❌ Login failed: Invalid email or password.")
                    raise Exception("Invalid Hevy credentials")
            else:
                raise Exception("Could not find enough input fields")
        except Exception as e:
            print(f"Login failed. Page content: {page.content()[:1000]}")
            page.screenshot(path="hevy_login_error_failed.png")
            raise e
        
        print("Waiting for dashboard/settings...")
        # After login, we usually land on hevy.com/
        # Wait for the settings link to appear
        page.wait_for_selector("a[href='/settings']", timeout=30000)
        print("Logged in successfully.")

        # Navigate to settings
        print("Navigating to settings...")
        page.goto("https://hevy.com/settings", wait_until="networkidle")
        page.screenshot(path="hevy_settings_debug.png")
        
        print("Searching for export options...")
        # Log available buttons for debugging
        buttons = page.query_selector_all("button")
        for i, btn in enumerate(buttons):
            try:
                print(f"Button {i}: {btn.inner_text()}")
            except: pass

        # Hevy export might be behind a "Download" or "Export" text
        # We try multiple selectors
        selectors = [
            "button:has-text('Export Workout Data')",
            "button:has-text('Export CSV')",
            "button:has-text('Export')",
            "text=Export Workout Data",
            "text=Export Data"
        ]
        
        export_button = None
        for sel in selectors:
            try:
                locator = page.locator(sel)
                if locator.count() > 0:
                    export_button = locator.first
                    print(f"Found export button with selector: {sel}")
                    break
            except: continue

        if not export_button:
            # Maybe it's a link?
            links = page.query_selector_all("a")
            for link in links:
                try:
                    if "Export" in link.inner_text():
                        print(f"Found export link: {link.inner_text()}")
                        export_button = link
                        break
                except: pass

        if not export_button:
            page.screenshot(path="hevy_no_export_button.png")
            raise Exception("Could not find the Export button on the settings page. See hevy_no_export_button.png for what it looks like.")

        print("Triggering export...")
        try:
            with page.expect_download(timeout=60000) as download_info:
                export_button.click()
                # If a modal appeared, we might need second click.
                # Let's check if 'Export CSV' appeared in a modal
                time.sleep(2)
                modal_btn = page.locator("button:has-text('Export CSV')").first
                if modal_btn.count() > 0:
                    print("Clicking 'Export CSV' in modal...")
                    modal_btn.click()
            download = download_info.value
        except Exception as e:
            print(f"Download failed or timed out: {e}")
            page.screenshot(path="hevy_download_error.png")
            raise e
        
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
