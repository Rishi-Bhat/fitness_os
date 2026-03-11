import os
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def get_google_fit_credentials():
    """
    Constructs Google credentials from environment variables.
    Requires REFRESH_TOKEN, CLIENT_ID, and CLIENT_SECRET.
    """
    token = os.environ.get("GOOGLE_FIT_REFRESH_TOKEN")
    client_id = os.environ.get("GOOGLE_FIT_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_FIT_CLIENT_SECRET")
    
    if not all([token, client_id, client_secret]):
        raise ValueError("Missing GOOGLE_FIT_* environment variables")

    return Credentials(
        None,
        refresh_token=token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/fitness.body.read", 
                "https://www.googleapis.com/auth/fitness.activity.read"]
    )

def fetch_health_metrics():
    """
    Fetches daily weight and steps for the last 7 days.
    """
    creds = get_google_fit_credentials()
    service = build("fitness", "v1", credentials=creds)

    # We use aggregate to get daily buckets
    # Body Weight (com.google.weight)
    # Steps (com.google.step_count.delta)
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=7)
    
    startTimeMillis = int(start_time.timestamp() * 1000)
    endTimeMillis = int(end_time.timestamp() * 1000)
    
    body = {
        "aggregateBy": [
            {"dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"},
            {"dataSourceId": "derived:com.google.weight:com.google.android.gms:merge_weight"}
        ],
        "bucketByTime": {"durationMillis": 86400000}, # 24 hours
        "startTimeMillis": startTimeMillis,
        "endTimeMillis": endTimeMillis
    }
    
    response = service.users().dataset().aggregate(userId="me", body=body).execute()
    
    metrics_list = []
    
    for bucket in response.get("bucket", []):
        day_start = datetime.fromtimestamp(int(bucket["startTimeMillis"]) / 1000)
        date_str = day_start.date().isoformat()
        
        steps = 0
        weight = 0
        
        for dataset in bucket.get("dataset", []):
            if dataset["dataSourceId"].startswith("derived:com.google.step_count.delta"):
                for point in dataset.get("point", []):
                    steps += point["value"][0]["intVal"]
            elif dataset["dataSourceId"].startswith("derived:com.google.weight"):
                for point in dataset.get("point", []):
                    weight = point["value"][0]["fpVal"]
        
        metrics_list.append({
            "date": date_str,
            "steps": steps,
            "weight": weight
        })
        
    return metrics_list

def sync_to_supabase(metrics):
    """
    Upserts metrics into daily_metrics table.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("Supabase credentials missing.")
        return

    supabase: Client = create_client(url, key)
    
    print(f"Syncing {len(metrics)} days of metrics...")
    for item in metrics:
        try:
            supabase.table("daily_metrics").upsert(item).execute()
        except Exception as e:
            print(f"Error syncing {item['date']}: {e}")

def sync_google_fit_metrics():
    """
    Fetches health metrics and syncs them to Supabase.
    """
    data = fetch_health_metrics()
    sync_to_supabase(data)
    print("Health metrics sync completed.")
    return data

if __name__ == "__main__":
    try:
        sync_google_fit_metrics()
    except Exception as e:
        print(f"Failed to fetch health metrics: {e}")
