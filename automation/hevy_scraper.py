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
    # Playwright installation is now handled globally in app.py to avoid 
    # downloading it on every button click.

    username = os.environ.get("HEVY_USERNAME")
    password = os.environ.get("HEVY_PASSWORD")
    
    if not username or not password:
        raise ValueError("HEVY_USERNAME or HEVY_PASSWORD not set")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to Hevy login...")
        page.goto("https://hevy.com/login", wait_until="domcontentloaded")
        
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
        # Since Hevy redirects to '/', waiting for /home or /workouts times out.
        # Instead, wait for a navigation to finish or just check for the side menu.
        try:
            page.wait_for_selector('a[href="/settings"]', timeout=15000)
            print("Logged in successfully, side menu rendered.")
        except Exception:
            print("Side menu not detected. Proceeding blindly...")

        # Navigate to settings
        print("Navigating to settings...")
        page.goto("https://hevy.com/settings", wait_until="domcontentloaded")
        page.screenshot(path="hevy_settings_debug.png")
        
        # Wait for the "Export Workout Data" button block to render, ignoring the "Loading..." state.
        try:
            page.wait_for_selector("text=Export Workout Data", timeout=20000)
        except:
            try:
                page.wait_for_selector("text=Export Data", timeout=5000)
            except:
                pass

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
            # First attempt: Try primary export buttons directly
            direct_success = False
            for btn_loc in export_button.locator("..").locator("button").all() if export_button else []:
                try:
                    with page.expect_download(timeout=5000) as download_info:
                        btn_loc.click()
                    download = download_info.value
                    direct_success = True
                    break
                except Exception:
                    pass
                    
            if not direct_success:
                try:
                    with page.expect_download(timeout=5000) as download_info:
                        export_button.click()
                    download = download_info.value
                    direct_success = True
                except Exception:
                    pass

            # Second attempt: If a modal opened, click aggressively
            if not direct_success:
                print("No immediate download. Assume modal opened. Searching for confirmation button...")
                time.sleep(2) # Wait for modal animation
                
                # Get all buttons on the page that are visible
                all_buttons = page.locator("button").all()
                download_found = False
                
                # Check from the bottom of the DOM (modals usually append)
                for btn in reversed(all_buttons):
                    try:
                        if not btn.is_visible(): continue
                        text = btn.inner_text().strip().lower()
                        if text in ["cancel", "close", "back", "no"]: continue
                        
                        print(f"Trying modal button: '{text}'...")
                        with page.expect_download(timeout=10000) as d_info:
                            btn.click()
                        download = d_info.value
                        download_found = True
                        print("Download triggered successfully by modal button!")
                        break
                    except Exception:
                        continue
                        
                if not download_found:
                    page.screenshot(path="hevy_download_error.png")
                    raise Exception("Aggressive button scan failed to trigger download.")
                    
        except Exception as e:
            print(f"Export logic sequence failed: {e}")
            page.screenshot(path="hevy_fatal_error.png")
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
    
    # New columns: 'title','start_time','end_time','description','exercise_title','superset_id','exercise_notes','set_index','set_type','weight_kg','reps','distance_km','duration_seconds','rpe'
    
    workouts = []
    for _, row in df.iterrows():
        try:
            # Force to UTC for stable ID generation across different server timezones
            dt_utc = pd.to_datetime(row['start_time']).tz_localize('UTC') if pd.to_datetime(row['start_time']).tzinfo is None else pd.to_datetime(row['start_time']).tz_convert('UTC')
            
            # Robust column mapping
            exercise = row.get('exercise_title') or row.get('Exercise Name') or 'Unknown'
            set_idx = row.get('set_index')
            if pd.isna(set_idx):
                # Check for 'Set Number' which is 1-based
                set_idx = row.get('Set Number')
                if not pd.isna(set_idx):
                    set_idx = int(set_idx) - 1
            
            # Map description/notes
            notes = row.get('exercise_notes') or row.get('Notes') or ""
            
            workout_data = {
                "date": dt_utc.strftime('%Y-%m-%d'),
                "exercise_name": exercise,
                "sets": 1, 
                "reps": int(row['reps']) if 'reps' in row and not pd.isna(row['reps']) else 0,
                "weight": float(row['weight_kg']) if 'weight_kg' in row and not pd.isna(row['weight_kg']) else 0,
                "volume_kg": (float(row['weight_kg']) if 'weight_kg' in row and not pd.isna(row['weight_kg']) else 0) * (int(row['reps']) if 'reps' in row and not pd.isna(row['reps']) else 0),
                "hevy_workout_id": str(row.get('title', 'Unknown')) + "_" + dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                "set_index": int(set_idx) if not pd.isna(set_idx) else 0,
                "notes": notes
            }
            workouts.append(workout_data)
        except Exception as e:
            print(f"Skipping unparseable row: {e}")
        
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
    
    if not workouts:
        print("No workouts to sync.")
        return

    print(f"Syncing {len(workouts)} sets to Supabase (Batched)...")
    
    # Batch size of 100 is safe and fast
    batch_size = 100
    for i in range(0, len(workouts), batch_size):
        batch = workouts[i:i + batch_size]
        try:
            supabase.table("workouts").upsert(batch, on_conflict="hevy_workout_id, exercise_name, set_index").execute()
            print(f"Synced batch {i//batch_size + 1}")
        except Exception as e:
            print(f"Error syncing batch: {e}")
            raise e

if __name__ == "__main__":
    try:
        csv_file = scrape_hevy_data()
        data = parse_hevy_csv(csv_file)
        sync_to_supabase(data)
        print("Hevy sync completed.")
    except Exception as e:
        print(f"Sync failed: {e}")
