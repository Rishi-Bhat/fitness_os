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

# Custom CSS for Premium Glassmorphism Look
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main {
        background: radial-gradient(circle at top right, #1a1f2e, #0e1117);
    }
    
    /* Glass Card Style */
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
    }
    
    /* Metric Card Customization */
    .metric-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 15px;
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        text-align: center;
    }
    
    .metric-value {
        font-size: 1.8rem;
        font-weight: 600;
        color: #ffffff;
        margin: 5px 0;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .metric-delta {
        font-size: 0.85rem;
        font-weight: 500;
    }
    
    /* Sidebar Cleanup */
    [data-testid="stSidebar"] {
        background-color: #0e1117;
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 12px 12px 0 0;
        padding: 10px 20px;
        color: #8b949e;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-bottom: none;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #1f6feb !important;
        color: white !important;
    }
    
    /* Progress Bar */
    .stProgress > div > div > div > div {
        background-color: #1f6feb;
    }
    
    /* Status Badge */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        background: rgba(31, 111, 235, 0.15);
        color: #58a6ff;
        border: 1px solid rgba(31, 111, 235, 0.3);
        font-size: 0.75rem;
        font-weight: 600;
    }
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
        weight_history = supabase.table("weight_measurements").select("*").order("timestamp", desc=True).limit(100).execute().data
        
        # Load sync logs gracefully
        sync_logs = {}
        try:
            sync_logs_data = supabase.table("sync_logs").select("*").execute().data
            sync_logs = {row['source']: row['last_sync'] for row in sync_logs_data}
        except Exception: pass
        
        return pd.DataFrame(metrics), pd.DataFrame(food), pd.DataFrame(workouts), pd.DataFrame(weight_history), sync_logs
    except Exception as e:
        st.error(f"Error fetching data from Supabase: {e}")
        return empty_df, empty_df, empty_df, empty_df, {}

df_metrics, df_food, df_workouts, df_weight_history, sync_logs = load_data()

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

if not df_weight_history.empty:
    df_weight_history['timestamp'] = pd.to_datetime(df_weight_history['timestamp'])

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
    
    # --- TIME SCALE PILL ---
    st.subheader("Time Scale")
    date_filter = st.selectbox(
        "Display Range",
        ["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
        index=1,
        label_visibility="collapsed"
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
    
    st.spacer(height=20) # Custom space
    
    # --- ADMIN TOOLS EXPANDER ---
    with st.expander("⚙️ Admin Tools", expanded=False):
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
    
    # 1. Scale Status & Metric Cards
    if not df_metrics.empty:
        latest_summary = df_metrics.sort_values('date').iloc[-1]
        prev_summary = df_metrics.sort_values('date').iloc[-2] if len(df_metrics) > 1 else latest_summary
        
        weight_delta = latest_summary['weight'] - prev_summary['weight']
        
        # --- BADGE ROW ---
        b1, b2 = st.columns([3, 1])
        with b2:
            if not df_weight_history.empty:
                latest_raw = df_weight_history.iloc[0]
                last_ts = latest_raw['timestamp']
                ts_label = "Today" if last_ts.date() == datetime.now().date() else last_ts.strftime('%d %b')
                st.markdown(f'<div style="text-align: right;"><span class="status-badge">⚖️ {latest_raw["weight"]}kg • {ts_label}</span></div>', unsafe_allow_html=True)

        # --- COMMAND CENTER METRICS ---
        m1, m2, m3, m4 = st.columns(4)
        
        with m1:
            delta_color = "#ff4b4b" if weight_delta > 0 else "#238636"
            delta_icon = "▲" if weight_delta > 0 else "▼"
            st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-label">WEIGHT</div>
                    <div class="metric-value">{latest_summary['weight']} kg</div>
                    <div class="metric-delta" style="color: {delta_color};">{delta_icon} {abs(weight_delta):.1f} kg</div>
                </div>
            """, unsafe_allow_html=True)
            
        with m2:
            steps_goal = 10000
            steps_pct = min(latest_summary['steps'] / steps_goal, 1.0)
            st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-label">STEPS</div>
                    <div class="metric-value">{int(latest_summary['steps']):,}</div>
                    <div style="width: 100%; background: rgba(255,255,255,0.1); border-radius: 4px; height: 6px; margin-top: 10px;">
                        <div style="width: {steps_pct*100}%; background: #1f6feb; border-radius: 4px; height: 100%;"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with m3:
            cal_goal = 2500
            today_date = datetime.now().date()
            daily_food = df_food[df_food['date_only'] == today_date] if not df_food.empty else pd.DataFrame()
            consumed = daily_food['calories'].sum()
            left = max(cal_goal - consumed, 0)
            st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-label">CALORIES LEFT</div>
                    <div class="metric-value">{int(left):,}</div>
                    <div style="font-size: 0.7rem; color: #8b949e; margin-top: 4px;">Goal: {cal_goal}</div>
                </div>
            """, unsafe_allow_html=True)
            
        with m4:
            prot_goal = 180
            today_prot = daily_food['protein'].sum() if not daily_food.empty else 0
            prot_pct = min(today_prot / prot_goal, 1.0)
            st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-label">PROTEIN</div>
                    <div class="metric-value">{int(today_prot)} g</div>
                    <div style="width: 100%; background: rgba(255,255,255,0.1); border-radius: 4px; height: 6px; margin-top: 10px;">
                        <div style="width: {prot_pct*100}%; background: #8957e5; border-radius: 4px; height: 100%;"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # --- GOAL COUNTDOWN ---
        target_weight = 75.0
        target_date = datetime(2026, 6, 1).date()
        days_left = (target_date - today_date).days
        weeks_left = days_left / 7
        if weeks_left > 0:
            loss_needed = latest_summary['weight'] - target_weight
            rate_needed = loss_needed / weeks_left
            st.markdown(f"""
                <div style="padding: 12px 20px; background: rgba(137, 87, 229, 0.1); border-radius: 12px; border: 1px solid rgba(137, 87, 229, 0.3); margin: 20px 0; text-align: center;">
                    <span style="color: #8957e5; font-weight: 600;">📅 Road to 12% Body Fat:</span> 
                    Lose <b>{rate_needed:.2f} kg/week</b> to hit <b>{target_weight}kg</b> by June.
                </div>
            """, unsafe_allow_html=True)
        
        # --- Weight History Viewer ---
        with st.expander("📉 View Weight History & Trends"):
            if not df_weight_history.empty:
                hcol1, hcol2 = st.columns([1, 1])
                with hcol1:
                    st.write("Recent Measurements")
                    st.dataframe(df_weight_history[['timestamp', 'weight']].head(10), hide_index=True, use_container_width=True)
                with hcol2:
                    st.write("Weight Precision Trend")
                    fig_raw = px.line(df_weight_history, x='timestamp', y='weight', color_discrete_sequence=["#1f6feb"])
                    fig_raw.update_layout(template="plotly_dark", height=300, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_raw, use_container_width=True)
            else:
                st.write("No historical data available yet.")

        st.divider()

        # --- PREMIUM CHARTS ---
        col1, col2 = st.columns(2)
        with col1:
            # 1. Weight Area Chart with Gradient
            fig_weight = go.Figure()
            fig_weight.add_trace(go.Scatter(
                x=df_metrics['date'], y=df_metrics['weight'],
                name="Daily", mode='lines',
                line=dict(color="#1f6feb", width=2),
                fill='tozeroy',
                fillcolor='rgba(31, 111, 235, 0.1)'
            ))
            fig_weight.add_trace(go.Scatter(
                x=df_metrics['date'], y=df_metrics['weight_rolling'],
                name="Trend", line=dict(color="#8957e5", width=4)
            ))
            fig_weight.update_layout(
                title="Weight Trajectory",
                template="plotly_dark",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=40, b=0, l=0, r=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_weight.update_xaxes(tickformat="%d %b", gridcolor="rgba(255,255,255,0.05)")
            fig_weight.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
            st.plotly_chart(fig_weight, use_container_width=True)

            # 2. Metabolic Efficiency
            if not df_food.empty:
                food_daily = df_food.groupby('date_only')['calories'].sum().reset_index()
                merged = pd.merge(df_metrics, food_daily, left_on='date', right_on='date_only', how='left')
                fig_cvw = px.scatter(merged, x="calories", y="weight", title="Metabolic Efficiency", trendline="ols", color_discrete_sequence=["#238636"])
                fig_cvw.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=40))
                st.plotly_chart(fig_cvw, use_container_width=True)

        with col2:
            # 3. Training Load Area Chart
            if not df_workouts.empty:
                weekly_df = df_workouts.groupby(['year', 'week'])['volume_kg'].sum().reset_index()
                weekly_df['label'] = "W" + weekly_df['week'].astype(str)
                fig_vol = px.area(weekly_df, x="label", y="volume_kg", title="Training Load Evolution", color_discrete_sequence=["#238636"])
                fig_vol.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=40))
                fig_vol.update_traces(fillcolor='rgba(35, 134, 54, 0.1)')
                st.plotly_chart(fig_vol, use_container_width=True)

            # 4. Protein Intensity
            if not df_food.empty:
                protein_daily = df_food.groupby('date_only')['protein'].sum().reset_index()
                fig_prot = px.area(protein_daily, x="date_only", y="protein", title="Protein Consistency", color_discrete_sequence=["#8957e5"])
                fig_prot.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=40))
                fig_prot.update_traces(fillcolor='rgba(137, 87, 229, 0.1)')
                st.plotly_chart(fig_prot, use_container_width=True)

        # 5. Daily Movement
        fig_steps = px.bar(df_metrics, x="date", y="steps", title="Step Intensity", color="steps", color_continuous_scale="Viridis")
        fig_steps.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', coloraxis_showscale=False)
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
