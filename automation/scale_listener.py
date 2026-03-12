import asyncio
import os
import time
from datetime import datetime
from bleak import BleakClient, BleakScanner
from supabase import create_client, Client
from dotenv import load_dotenv

# --- CONFIGURATION ---
ADDRESS = "CF:E9:39:03:88:70"
CHAR_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"
THROTTLE_SECONDS = 300  # 5 minutes

# Load environment variables
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Global state for throttling
last_sync_time = 0

def decode_weight(data):
    """
    Decodes weight from BLE packet.
    Packet format: [CF, status, flags, weight_low, weight_high, ..., state, checksum]
    """
    if len(data) < 10:
        return None, False
        
    low = data[3]
    high = data[4]
    state = data[9]
    
    raw = (high << 8) | low
    weight = raw / 100
    is_stable = (state == 0x01)
    
    return weight, is_stable

async def sync_to_supabase(weight):
    """
    Upserts the weight into the daily_metrics table for the current date.
    """
    global last_sync_time
    
    current_time = time.time()
    if current_time - last_sync_time < THROTTLE_SECONDS:
        print(f"Throttling: Measurement ignored (last sync was {int(current_time - last_sync_time)}s ago)")
        return False

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: Supabase credentials missing.")
        return False

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Upsert weight for today
        data = {
            "date": today,
            "weight": weight
        }
        
        # Perform upsert on 'date' column
        result = supabase.table("daily_metrics").upsert(data, on_conflict="date").execute()
        
        print(f"Successfully synced weight: {weight} kg to Supabase for {today}")
        last_sync_time = current_time
        return True
    except Exception as e:
        print(f"Failed to sync to Supabase: {e}")
        return False

async def run_listener():
    """
    Runs the BLE listener with a reconnection loop.
    """
    print(f"Starting Cult Smart Scale listener for {ADDRESS}...")
    
    while True:
        try:
            print(f"Attempting to connect to {ADDRESS}...")
            async with BleakClient(ADDRESS) as client:
                print(f"Connected to {ADDRESS}!")
                
                def notification_handler(sender, data):
                    weight, is_stable = decode_weight(data)
                    if weight is not None:
                        status = "STABLE" if is_stable else "UNSTABLE"
                        print(f"[{status}] Current weight: {weight} kg")
                        
                        if is_stable:
                            # Use a separate task for syncing to avoid blocking the handler
                            asyncio.create_task(sync_to_supabase(weight))

                await client.start_notify(CHAR_UUID, notification_handler)
                print("Subscribed to notifications. Listening for weight...")
                
                # Keep the connection alive until it drops
                while client.is_connected:
                    await asyncio.sleep(1)
                
                print("Connection lost.")
                
        except Exception as e:
            print(f"Connection error: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(run_listener())
    except KeyboardInterrupt:
        print("\nListener stopped by user.")
