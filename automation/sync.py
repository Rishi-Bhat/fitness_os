import os
import subprocess
import sys

def run_sync():
    """
    Orchestrates the synchronization of Hevy and Google Fit data.
    """
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("Starting Fitness OS Synchronization...")

    # 1. Sync Hevy Workouts
    try:
        print("\n--- Syncing Hevy Workouts ---")
        subprocess.run([sys.executable, os.path.join(scripts_dir, "hevy_scraper.py")], check=True)
    except Exception as e:
        print(f"Hevy sync failed: {e}")

    # 2. Sync Google Fit Metrics
    try:
        print("\n--- Syncing Google Fit Metrics ---")
        subprocess.run([sys.executable, os.path.join(scripts_dir, "health_bridge.py")], check=True)
    except Exception as e:
        print(f"Google Fit sync failed: {e}")

    print("\nSynchronization flow complete.")

if __name__ == "__main__":
    run_sync()
