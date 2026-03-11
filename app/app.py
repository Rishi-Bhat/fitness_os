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
        food = supabase.table("food_logs").select("*").order("timestamp", desc=True).limit(100).execute().data
        workouts = supabase.table("workouts").select("*").order("date", desc=True).limit(3000).execute().data
        
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

# --- DATA PRE-PROCESSING ---
if not df_metrics.empty:
    df_metrics['date'] = pd.to_datetime(df_metrics['date'])
    df_metrics = df_metrics.sort_values('date')
    df_metrics['weight_rolling'] = df_metrics['weight'].rolling(window=7).mean()

if not df_workouts.empty:
    df_workouts['date'] = pd.to_datetime(df_workouts['date'])
    df_workouts['week'] = df_workouts['date'].dt.isocalendar().week
    df_workouts['year'] = df_workouts['date'].dt.isocalendar().year

if not df_food.empty:
    df_food['date_only'] = pd.to_datetime(df_food['timestamp']).dt.date

st.title("Fitness OS — Dashboard")

if not supabase:
    st.warning("⚠️ **Supabase Configuration Required**: Please set `SUPABASE_URL` and `SUPABASE_KEY` in your environment variables or Streamlit Secrets to see your data.")

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("⚙️ Controls")
    
    if st.button("🔄 Refresh Dashboard", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()
        
    st.divider()
    
    # 4. Date Range Filter
    st.subheader("Filter Data")
    date_filter = st.radio(
        "Select Time Scale",
        ["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
        index=1,
        horizontal=True
    )
    
    date_map = {
        "Last 7 days": 7,
        "Last 30 days": 30,
        "Last 90 days": 90,
        "All time": 9999
    }
    days_back = date_map[date_filter]
    cutoff_date = pd.Timestamp.now().normalize() - pd.Timedelta(days=days_back)
    
    # Apply filtering
    if not df_metrics.empty:
        df_metrics = df_metrics[df_metrics['date'] >= cutoff_date]
    if not df_workouts.empty:
        df_workouts = df_workouts[df_workouts['date'] >= cutoff_date]
    
    st.divider()
    st.subheader("Manual Sync")
    
    st.divider()
    st.subheader("Manual Sync")
    
    # Hevy Sync Block
    hevy_last = sync_logs.get('hevy', 'Never')
    st.caption(f"**Hevy**: Last synced {hevy_last[:16] if hevy_last != 'Never' else hevy_last}")
    if st.button("Sync Hevy Workouts", use_container_width=True):
        if supabase:
            with st.spinner("Syncing Hevy (30-60s)..."):
                try:
                    csv_path = scrape_hevy_data()
                    if csv_path:
                        data = parse_hevy_csv(csv_path)
                        sync_to_supabase(data)
                    supabase.table("sync_logs").upsert({"source": "hevy"}).execute()
                    st.success("Hevy synced!")
                    st.rerun()
                except Exception as e: st.error(f"Hevy Sync failed: {e}")
                    
    # Google Fit Sync Block
    fit_last = sync_logs.get('google_fit', 'Never')
    st.caption(f"**Google Fit**: Last synced {fit_last[:16] if fit_last != 'Never' else fit_last}")
    if st.button("Sync Google Fit Data", use_container_width=True):
        if supabase:
            with st.spinner("Syncing Google Fit..."):
                try:
                    sync_google_fit_metrics()
                    supabase.table("sync_logs").upsert({"source": "google_fit"}).execute()
                    st.success("Google Fit synced!")
                    st.rerun()
                except Exception as e: st.error(f"Google Fit Sync failed: {e}")

    st.divider()
    with st.expander("⚠️ Troubleshooting"):
        st.caption("If data looks old or missing, try a clean reset:")
        if st.button("Reset & Full Re-sync (Hevy)", use_container_width=True, type="secondary"):
            if supabase:
                with st.spinner("Purging old workouts and re-syncing..."):
                    try:
                        # 1. Clear old workout data
                        supabase.table("workouts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
                        # 2. Run fresh sync
                        csv_path = scrape_hevy_data()
                        if csv_path:
                            data = parse_hevy_csv(csv_path)
                            sync_to_supabase(data)
                        supabase.table("sync_logs").upsert({"source": "hevy"}).execute()
                        st.success("Full Reset & Sync complete!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Reset failed: {e}")

# --- MAIN TABS ---
tabs = st.tabs(["📊 Overview", "🏋️ Training", "🥗 Nutrition"])

with tabs[0]:
    st.header("Analytics Hub")
    if not df_metrics.empty:
        latest = df_metrics.iloc[-1]
        
        # 4-Column Metric Row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Weight", f"{latest['weight']} kg")
        m2.metric("Steps", f"{int(latest['steps'])}")
        
        # Pull calorie/protein from food logs for "Today"
        today = datetime.now().date()
        daily_food = df_food[df_food['date_only'] == today] if not df_food.empty else pd.DataFrame()
        
        m3.metric("Calories", f"{daily_food['calories'].sum():,.0f} kcal" if not daily_food.empty else "0 kcal")
        m4.metric("Protein", f"{daily_food['protein'].sum():,.0f} g" if not daily_food.empty else "0 g")
        
        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            # 1. Weight Trend
            fig_weight = go.Figure()
            fig_weight.add_trace(go.Scatter(x=df_metrics['date'], y=df_metrics['weight'], name="Daily", mode='markers+lines', line=dict(color="#1f6feb", width=1)))
            fig_weight.add_trace(go.Scatter(x=df_metrics['date'], y=df_metrics['weight_rolling'], name="7d Avg", line=dict(color="#8957e5", width=3)))
            fig_weight.update_layout(title="Weight Trend (kg)", template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig_weight.update_xaxes(tickformat="%d %b")
            st.plotly_chart(fig_weight, use_container_width=True)

            # 2. Calories vs Weight
            if not df_food.empty:
                food_daily = df_food.groupby('date_only')['calories'].sum().reset_index()
                merged = pd.merge(df_metrics, food_daily, left_on='date', right_on='date_only', how='left')
                fig_cvw = px.scatter(merged, x="calories", y="weight", title="Calories vs Weight", trendline="ols", color_discrete_sequence=["#238636"])
                fig_cvw.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_cvw, use_container_width=True)

        with col2:
            # 3. Weekly Volume
            if not df_workouts.empty:
                weekly_df = df_workouts.groupby(['year', 'week'])['volume_kg'].sum().reset_index()
                weekly_df['label'] = "W" + weekly_df['week'].astype(str)
                fig_vol = px.bar(weekly_df, x="label", y="volume_kg", title="Weekly Volume (kg)", color_discrete_sequence=["#238636"])
                fig_vol.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_vol, use_container_width=True)

            # 4. Protein Intake Trend
            if not df_food.empty:
                protein_daily = df_food.groupby('date_only')['protein'].sum().reset_index()
                fig_prot = px.line(protein_daily, x="date_only", y="protein", title="Protein Intake (g)", color_discrete_sequence=["#8957e5"])
                fig_prot.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                fig_prot.update_xaxes(tickformat="%d %b")
                st.plotly_chart(fig_prot, use_container_width=True)

        # 5. Steps Chart
        fig_steps = px.bar(df_metrics, x="date", y="steps", title="Daily Steps Activity", color_discrete_sequence=["#238636"])
        fig_steps.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        fig_steps.update_xaxes(tickformat="%d %b")
        st.plotly_chart(fig_steps, use_container_width=True)
    else:
        st.info("No analytics data yet. Sync your data to see trends!")

with tabs[1]:
    st.header("Workout History")
    if not df_workouts.empty:
        # Latest Workout Highlight
        latest_date = df_workouts['date'].max()
        latest_workout = df_workouts[df_workouts['date'] == latest_date]
        
        st.subheader(f"Latest Session: {latest_date.strftime('%d %b %Y')}")
        lcol1, lcol2, lcol3 = st.columns(3)
        lcol1.metric("Exercises", len(latest_workout['exercise_name'].unique()))
        lcol2.metric("Total Sets", len(latest_workout))
        lcol3.metric("Volume", f"{latest_workout['volume_kg'].sum():,.0f} kg")
        st.divider()

        # Workout History (Expanders)
        dates = sorted(df_workouts['date'].unique(), reverse=True)
        for d in dates:
            d_dt = pd.to_datetime(d)
            day_data = df_workouts[df_workouts['date'] == d]
            with st.expander(f"Workout - {d_dt.strftime('%d %b %Y')} ({day_data['volume_kg'].sum():,.0f} kg)"):
                for ex in day_data['exercise_name'].unique()[::-1]:
                    ex_data = day_data[day_data['exercise_name'] == ex].sort_values('set_index')
                    st.markdown(f"**{ex}**")
                    sets_text = " | ".join([f"Set {int(row['set_index'])+1}: {int(row['reps'])}×{row['weight']}kg" for _, row in ex_data.iterrows()])
                    st.caption(sets_text)
                    
                    # More visible notes
                    notes_list = ex_data['notes'].dropna().unique()
                    notes = notes_list[0] if len(notes_list) > 0 and notes_list[0] != "" else None
                    if notes:
                        st.markdown(f"**Note:** *{notes}*")
    else:
        st.info("No workout history found. Sync your Hevy data to see progress.")

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
