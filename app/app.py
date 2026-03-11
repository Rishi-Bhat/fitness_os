import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import sys

# Add root to path for local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.food_parser import parse_food_description
from automation.hevy_scraper import scrape_hevy_data, parse_hevy_csv, sync_to_supabase
from automation.health_bridge import sync_google_fit_metrics
from supabase import create_client, Client

# Page Config
st.set_page_config(page_title="Fitness OS", page_icon="💪", layout="wide")

# Inject Streamlit Secrets into environment for backend scripts
try:
    if hasattr(st, "secrets"):
        for key, value in st.secrets.items():
            os.environ[key] = str(value)
except Exception:
    pass

# Custom CSS for Premium Look
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #161b22;
        border-radius: 8px 8px 0px 0px;
        color: #8b949e;
        padding-left: 20px;
        padding-right: 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f6feb !important;
        color: white !important;
    }
    .metric-card {
        background-color: #161b22;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #30363d;
        text-align: center;
    }
</style>
</style>
""", unsafe_allow_html=True)

# Install Playwright Browsers Once
@st.cache_resource
def install_playwright():
    try:
        print("Ensuring Playwright browser is installed (cached)...")
        import subprocess
        subprocess.run(["playwright", "install", "chromium"], check=True)
        return True
    except Exception as e:
        print(f"Failed to install Playwright: {e}")
        return False

# Trigger installation on startup
install_playwright()

# Supabase Initialization
@st.cache_resource
def get_supabase():
    # Try getting from environment or streamlit secrets
    url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
    
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

supabase = get_supabase()

def load_data():
    empty_df = pd.DataFrame()
    if not supabase: 
        return empty_df, empty_df, empty_df, {}
    
    try:
        metrics = supabase.table("daily_metrics").select("*").order("date", desc=True).limit(30).execute().data
        food = supabase.table("food_logs").select("*").order("timestamp", desc=True).limit(50).execute().data
        workouts = supabase.table("workouts").select("*").order("date", desc=True).limit(100).execute().data
        
        # Load sync logs gracefully (ignores Supabase schema cache errors on new tables)
        sync_logs = {}
        try:
            sync_logs_data = supabase.table("sync_logs").select("*").execute().data
            sync_logs = {row['source']: row['last_sync'] for row in sync_logs_data}
        except Exception as e:
            st.toast(f"Note: Sync status currently unavailable ({str(e)[:30]}...)")
        
        return pd.DataFrame(metrics), pd.DataFrame(food), pd.DataFrame(workouts), sync_logs
    except Exception as e:
        st.error(f"Error fetching data from Supabase: {e}")
        return empty_df, empty_df, empty_df, {}

df_metrics, df_food, df_workouts, sync_logs = load_data()

st.title("Fitness OS — Dashboard")

if not supabase:
    st.warning("⚠️ **Supabase Configuration Required**: Please set `SUPABASE_URL` and `SUPABASE_KEY` in your environment variables or Streamlit Secrets to see your data.")

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("⚙️ Controls")
    
    if st.button("🔄 Refresh Dashboard", width="stretch"):
        st.cache_resource.clear()
        st.rerun()
        
    st.divider()
    
    st.subheader("Manual Sync")
    
    # Hevy Sync Block
    hevy_last = sync_logs.get('hevy', 'Never')
    st.caption(f"**Hevy**: Last synced {hevy_last[:16] if hevy_last != 'Never' else hevy_last}")
    if st.button("Sync Hevy Workouts", width="stretch"):
        if not supabase:
            st.error("Supabase not connected.")
        else:
            with st.spinner("Syncing Hevy (takes 30-60s)..."):
                try:
                    csv_path = scrape_hevy_data()
                    if csv_path:
                        data = parse_hevy_csv(csv_path)
                        sync_to_supabase(data)
                    
                    # Update status gracefully
                    try:
                        supabase.table("sync_logs").upsert({"source": "hevy"}).execute()
                    except Exception as pg_err:
                        print(f"Non-critical error updating sync_logs (likely cache): {pg_err}")
                        
                    st.success("Hevy synced successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Hevy Sync failed: {str(e)}")
                    
    # Google Fit Sync Block
    fit_last = sync_logs.get('google_fit', 'Never')
    st.caption(f"**Google Fit**: Last synced {fit_last[:16] if fit_last != 'Never' else fit_last}")
    if st.button("Sync Google Fit Data", width="stretch"):
        if not supabase:
            st.error("Supabase not connected.")
        else:
            with st.spinner("Syncing Google Fit..."):
                try:
                    sync_google_fit_metrics()
                    
                    try:
                        supabase.table("sync_logs").upsert({"source": "google_fit"}).execute()
                    except Exception as pg_err:
                        print(f"Non-critical error updating sync_logs (likely cache): {pg_err}")
                        
                    st.success("Google Fit synced successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Google Fit Sync failed: {str(e)}")

# --- MAIN TABS ---
tabs = st.tabs(["📊 Overview", "🏋️ Training", "🥗 Nutrition"])

with tabs[0]:
    st.header("Daily Health Trends")
    if not df_metrics.empty:
        col1, col2, col3 = st.columns(3)
        latest = df_metrics.iloc[0]
        
        with col1:
            st.metric("Latest Weight", f"{latest['weight']} kg")
        with col2:
            st.metric("Steps Today", f"{latest['steps']}")
        with col3:
            st.metric("Body Fat", f"{latest['body_fat_pct']}%")

        # Weight Chart
        fig_weight = px.line(df_metrics, x="date", y="weight", title="Body Weight Over Time",
                            color_discrete_sequence=["#1f6feb"])
        fig_weight.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_weight, width="stretch")
        
        # Steps Chart
        fig_steps = px.bar(df_metrics, x="date", y="steps", title="Daily Steps",
                          color_discrete_sequence=["#238636"])
        fig_steps.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_steps, width="stretch")
    else:
        st.info("No metric data found. Sync your Google Fit data to see trends.")

with tabs[1]:
    st.header("Workout Progress")
    if not df_workouts.empty:
        # Data Processing
        df_workouts['date'] = pd.to_datetime(df_workouts['date'])
        
        # Latest Workout Highlight
        latest_date = df_workouts['date'].max()
        latest_workout = df_workouts[df_workouts['date'] == latest_date]
        
        st.subheader(f"Latest Workout — {latest_date.strftime('%d %B %Y')}")
        lcol1, lcol2, lcol3 = st.columns(3)
        with lcol1:
            st.metric("Exercises", len(latest_workout['exercise_name'].unique()))
        with lcol2:
            st.metric("Total Sets", len(latest_workout))
        with lcol3:
            st.metric("Total Volume", f"{latest_workout['volume_kg'].sum():,.0f} kg")
        st.divider()

        # Workout History (Expanders)
        st.subheader("🗓 Workout History")
        # Group by date and sort descending
        dates = sorted(df_workouts['date'].unique(), reverse=True)
        for d in dates:
            d_dt = pd.to_datetime(d)
            d_str = d_dt.strftime('%d %b %Y')
            day_data = df_workouts[df_workouts['date'] == d]
            with st.expander(f"Workout - {d_str} ({day_data['volume_kg'].sum():,.0f} kg)"):
                exercises = day_data['exercise_name'].unique()[::-1]
                for ex in exercises:
                    ex_data = day_data[day_data['exercise_name'] == ex].sort_values('set_index')
                    st.markdown(f"**{ex}**")
                    sets_text = "  |  ".join([f"Set {int(row['set_index'])+1 if pd.notna(row['set_index']) else i+1}: {int(row['reps'])} × {row['weight']}kg" for i, (_, row) in enumerate(ex_data.iterrows())])
                    st.caption(sets_text)
        
        st.divider()
        
        # Exercise Progression
        st.subheader("📈 Exercise Progress")
        selected_exercise = st.selectbox("Select Exercise to Track", sorted(df_workouts['exercise_name'].unique()))
        ex_df = df_workouts[df_workouts['exercise_name'] == selected_exercise].sort_values('date')
        
        fig_ex = px.line(ex_df, x="date", y="weight", title=f"{selected_exercise} Progress (Max Weight)",
                        color_discrete_sequence=["#8957e5"], markers=True)
        fig_ex.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_ex, width="stretch")

        # Weekly Volume
        st.subheader("📊 Weekly Training Volume")
        df_workouts['week'] = df_workouts['date'].dt.isocalendar().week
        df_workouts['year'] = df_workouts['date'].dt.isocalendar().year
        weekly_df = df_workouts.groupby(['year', 'week'])['volume_kg'].sum().reset_index()
        weekly_df['week_label'] = weekly_df['year'].astype(str) + " - W" + weekly_df['week'].astype(str)
        
        fig_vol = px.bar(weekly_df, x="week_label", y="volume_kg", title="Volume per Week",
                        color_discrete_sequence=["#238636"])
        fig_vol.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_vol, width="stretch")

        # Training Stats
        st.divider()
        st.subheader("🏆 Training Stats")
        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        with s_col1:
            st.metric("Total Workouts", len(df_workouts['date'].unique()))
        with s_col2:
            st.metric("Total Volume", f"{df_workouts['volume_kg'].sum():,.0f} kg")
        with s_col3:
            st.metric("Avg Workout Volume", f"{df_workouts.groupby('date')['volume_kg'].sum().mean():,.0f} kg")
        with s_col4:
            most_freq = df_workouts['exercise_name'].mode()[0] if not df_workouts.empty else "N/A"
            st.metric("Most Frequent", most_freq)
    else:
        st.info("No workouts found. Sync your Hevy data to see progress.")

with tabs[2]:
    st.header("Nutrition Tracking")
    
    # Food Parser Input
    with st.expander("📝 Log Food (Natural Language)", expanded=True):
        food_text = st.text_input("What did you eat?", placeholder="e.g. 3 scrambled eggs and an avocado toast")
        if st.button("Parse and Log"):
            with st.spinner("Analyzing with Gemini..."):
                try:
                    macros = parse_food_description(food_text)
                    if "error" not in macros:
                        # Log to Supabase
                        log_entry = {
                            "description": food_text,
                            "calories": macros['calories'],
                            "protein": macros['protein'],
                            "carbs": macros['carbs'],
                            "fat": macros['fat']
                        }
                        supabase.table("food_logs").insert(log_entry).execute()
                        st.success(f"Logged: {macros['calories']} kcal | P: {macros['protein']}g | C: {macros['carbs']}g | F: {macros['fat']}g")
                        st.rerun()
                    else:
                        st.error(f"Could not parse: {macros['error']}")
                except Exception as e:
                    st.error(f"Error: {e}")

    if not df_food.empty:
        # Daily Summary
        df_food['timestamp'] = pd.to_datetime(df_food['timestamp']).dt.date
        daily_food = df_food.groupby('timestamp').agg({
            'calories': 'sum',
            'protein': 'sum',
            'carbs': 'sum',
            'fat': 'sum'
        }).reset_index().sort_values('timestamp', ascending=False)
        
        st.subheader("Daily Macro Trends")
        fig_nutrition = px.bar(daily_food, x="timestamp", y=["protein", "carbs", "fat"], 
                              title="Daily Macros", barmode="stack")
        fig_nutrition.update_layout(template="plotly_dark")
        st.plotly_chart(fig_nutrition, width="stretch")
        
        st.subheader("Recent Food Logs")
        st.dataframe(df_food[['timestamp', 'description', 'calories', 'protein', 'carbs', 'fat']], 
                    width="stretch", hide_index=True)
    else:
        st.info("No food logs found. Start logging above!")
