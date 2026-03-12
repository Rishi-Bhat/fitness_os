import asyncio
import os
import time
from datetime import datetime
from bleak import BleakScanner, BleakClient
from supabase import create_client, Client
from dotenv import load_dotenv

# --- CONFIGURATION ---
SCALE_MAC = "CF:E9:39:03:88:70"
MIN_WEIGHT = 60.0 # kg
MAX_WEIGHT = 80.0 # kg
THROTTLE_SECONDS = 300 # 5 minutes

# Load environment variables
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Global state
last_sync_time = 0

def decode_weight(data):
    """
    Decodes weight from BLE advertisement packet.
    Packet format: [CF, flags, user_id, weight_low, weight_high, ..., state, checksum]
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
    Upserts the weight into the daily_metrics table.
    """
    global last_sync_time
    
    # 1. Throttling check
    current_time = time.time()
    if current_time - last_sync_time < THROTTLE_SECONDS:
        return False

    # 2. Weight Range Filtering
    if not (MIN_WEIGHT <= weight <= MAX_WEIGHT):
        print(f"Weight {weight} kg out of range ({MIN_WEIGHT}-{MAX_WEIGHT}). Ignoring.")
        return False

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: Supabase credentials missing.")
        return False

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        today = datetime.now().strftime('%Y-%m-%d')
        
        data = {
            "date": today,
            "weight": weight
        }
        
        # Upsert on 'date' column
        supabase.table("daily_metrics").upsert(data, on_conflict="date").execute()
        
        print(f"✅ Successfully loggged stable weight: {weight} kg for {today}")
        last_sync_time = current_time
        return True
    except Exception as e:
        print(f"❌ Failed to sync to Supabase: {e}")
        return False

def detection_callback(device, advertisement_data):
    """
    Callback for BLE advertisement detection.
    """
    if device.address.upper() != SCALE_MAC.upper():
        return

    # Manufacturer data is usually where the weight info sits
    # The key is often the manufacturer ID
    data_dict = advertisement_data.manufacturer_data
    for key in data_dict:
        packet = data_dict[key]
        
        weight, is_stable = decode_weight(packet)
        if weight is not None:
            status = "STABLE" if is_stable else "MEASURING"
            print(f"[{status}] {weight} kg")
            
            if is_stable:
                # We need to run the async sync function
                asyncio.create_task(sync_to_supabase(weight))

async def main():
    print(f"🚀 Starting Cult Smart Scale Scanner (MAC: {SCALE_MAC})...")
    print(f"Filtering for weight range: {MIN_WEIGHT}kg - {MAX_WEIGHT}kg")
    
    scanner = BleakScanner(detection_callback)
    
    try:
        await scanner.start()
        # Keep scanning indefinitely
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Scanner error: {e}")
    finally:
        await scanner.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScanner stopped by user.")
