import asyncio
import os
import time
import logging
from datetime import datetime
from bleak import BleakScanner
from supabase import create_client, Client
from dotenv import load_dotenv

# --- CONFIGURATION ---
SCALE_MAC = "CF:E9:39:03:88:70"
MIN_WEIGHT = 60.0 # kg
MAX_WEIGHT = 80.0 # kg
THROTTLE_SECONDS = 300 # 5 minutes
STABILITY_THRESHOLD_KG = 0.1

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Global variables
last_sync_time = 0
last_weight = 0.0

# Initialize Supabase client once
if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("Supabase credentials missing from environment variables.")
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def decode_weight(data):
    """
    Decodes weight from BLE advertisement packet.
    Packet format: [CF, flags, user_id, weight_low, weight_high, ..., state, checksum]
    """
    if len(data) < 10:
        return None, False
    
    # Header validation
    if data[0] != 0xCF:
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
    Saves measurements to historical table and updates daily summary.
    """
    global last_sync_time, last_weight
    
    if not supabase:
        logging.error("Cannot sync: Supabase client not initialized.")
        return False

    current_time = time.time()
    
    # 1. Throttling & Stability Check
    # Ignore if weight hasn't changed much AND we're within the throttle window
    weight_diff = abs(weight - last_weight)
    time_diff = current_time - last_sync_time
    
    if weight_diff < STABILITY_THRESHOLD_KG and time_diff < THROTTLE_SECONDS:
        return False

    # 2. Weight Range Filtering (Safety check for other users)
    if not (MIN_WEIGHT <= weight <= MAX_WEIGHT):
        logging.warning(f"Weight {weight} kg out of range ({MIN_WEIGHT}-{MAX_WEIGHT}). Ignoring.")
        return False

    try:
        now = datetime.now()
        timestamp_iso = now.isoformat()
        date_str = now.strftime('%Y-%m-%d')
        
        # 1️⃣ Insert into historical measurements table
        measurement_data = {
            "timestamp": timestamp_iso,
            "weight": weight,
            "source": "ble_scale"
        }
        supabase.table("weight_measurements").insert(measurement_data).execute()
        
        # 2️⃣ Update daily metrics summary
        daily_data = {
            "date": date_str,
            "weight": weight
        }
        supabase.table("daily_metrics").upsert(daily_data, on_conflict="date").execute()
        
        logging.info(f"✅ Recorded weight: {weight} kg (Historical + Daily Summary)")
        
        last_sync_time = current_time
        last_weight = weight
        return True
    except Exception as e:
        logging.error(f"❌ Failed to sync to Supabase: {e}")
        return False

def detection_callback(device, advertisement_data):
    """
    Callback for BLE advertisement detection.
    """
    if device.address.upper() != SCALE_MAC.upper():
        return

    data_dict = advertisement_data.manufacturer_data
    for key in data_dict:
        packet = data_dict[key]
        
        weight, is_stable = decode_weight(packet)
        if weight is not None:
            if is_stable:
                # Run sync on the current event loop
                loop = asyncio.get_event_loop()
                loop.create_task(sync_to_supabase(weight))
            else:
                # Log transient measurements at a lower level or just skip
                pass

async def main():
    logging.info(f"🚀 Starting Optimized Scale Scanner (MAC: {SCALE_MAC})")
    logging.info(f"Monitoring range: {MIN_WEIGHT}kg - {MAX_WEIGHT}kg")
    
    scanner = BleakScanner(detection_callback)
    
    try:
        await scanner.start()
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"Scanner error: {e}")
    finally:
        await scanner.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Scanner stopped by user.")
