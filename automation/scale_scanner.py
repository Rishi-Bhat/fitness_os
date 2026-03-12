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
MIN_SANITY_WEIGHT = 30.0  # kg
MAX_SANITY_WEIGHT = 200.0 # kg
THROTTLE_SECONDS = 300    # 5 minutes
STABILITY_THRESHOLD_KG = 0.1

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Initialize Supabase client globally
if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Supabase credentials missing from environment variables.")
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global state for duplicate protection & throttling
last_sync_time = 0
last_weight = 0.0

def decode_weight(packet):
    """
    Decodes weight from BLE advertisement packet.
    Expected Header: 0xCF
    Formula: (byte4 << 8 | byte3) / 100
    """
    if len(packet) < 10:
        return None, False

    if packet[0] != 0xCF:
        return None, False

    # byte3: weight low, byte4: weight high
    low = packet[3]
    high = packet[4]

    raw_weight = (high << 8) | low
    weight_kg = raw_weight / 100.0

    # byte9: measurement state (0x01 = stable)
    state = packet[9]
    is_stable = (state == 0x01)

    return weight_kg, is_stable

async def sync_to_supabase(weight):
    """
    Saves measurements to historical table and updates daily summary.
    Includes sanity checks and duplicate protection.
    """
    global last_sync_time, last_weight
    
    if not supabase:
        logger.error("Cannot sync: Supabase client not initialized.")
        return False

    # 1. Sanity Check
    if weight < MIN_SANITY_WEIGHT or weight > MAX_SANITY_WEIGHT:
        logger.warning(f"❌ Sanity check failed: {weight} kg is unrealistic. Ignoring.")
        return False

    current_time = time.time()
    
    # 2. Duplicate & Throttling Check
    weight_diff = abs(weight - last_weight)
    time_diff = current_time - last_sync_time
    
    # If weight is nearly identical and we're in the throttle window, skip
    if weight_diff < STABILITY_THRESHOLD_KG and time_diff < THROTTLE_SECONDS:
        logger.info(f"⏭️ Skipping duplicate/throttled measurement: {weight} kg")
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
        
        logger.info(f"✅ RECORDED: {weight} kg (Historical + Daily)")
        
        last_sync_time = current_time
        last_weight = weight
        return True
    except Exception as e:
        logger.error(f"❌ Supabase sync error: {e}")
        return False

def detection_callback(device, advertisement_data):
    """
    Callback for BLE advertisement detection.
    Scans both manufacturer_data and service_data.
    """
    if device.address.upper() != SCALE_MAC.upper():
        return

    # 1. Check Manufacturer Data
    data_dict = advertisement_data.manufacturer_data
    for key in data_dict:
        packet = data_dict[key]
        logger.debug(f"RAW PACKET (MFG): {packet.hex().upper()}")
        
        weight, is_stable = decode_weight(packet)
        if weight is not None:
            logger.info(f"Decoded (MFG): {weight} kg | Stable: {is_stable}")
            if is_stable:
                asyncio.get_event_loop().create_task(sync_to_supabase(weight))

    # 2. Check Service Data (some scales/firmwares use this)
    service_data = advertisement_data.service_data
    if service_data:
        for uuid, data in service_data.items():
            logger.debug(f"RAW PACKET (SRV): {data.hex().upper()}")
            weight, is_stable = decode_weight(data)
            if weight is not None:
                logger.info(f"Decoded (SRV): {weight} kg | Stable: {is_stable}")
                if is_stable:
                    asyncio.get_event_loop().create_task(sync_to_supabase(weight))

async def main():
    logger.info("--------------------------------------------------")
    logger.info(f"🚀 STARTING SCALE SCANNER (Target: {SCALE_MAC})")
    logger.info(f"Sanity Range: {MIN_SANITY_WEIGHT}kg - {MAX_SANITY_WEIGHT}kg")
    logger.info("--------------------------------------------------")
    
    scanner = BleakScanner(detection_callback)
    
    try:
        await scanner.start()
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Scanner fatal error: {e}")
    finally:
        await scanner.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Scanner stopped by user.")
