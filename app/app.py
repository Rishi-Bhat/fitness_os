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
from supabase import create_client, Client

# Page Config
st.set_page_config(page_title="Fitness OS", page_icon="💪", layout="wide")

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
""", unsafe_allow_html=True)

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
        return empty_df, empty_df, empty_df
    
    try:
        metrics = supabase.table("daily_metrics").select("*").order("date", desc=True).limit(30).execute().data
        food = supabase.table("food_logs").select("*").order("timestamp", desc=True).limit(50).execute().data
        workouts = supabase.table("workouts").select("*").order("date", desc=True).limit(100).execute().data
        
        return pd.DataFrame(metrics), pd.DataFrame(food), pd.DataFrame(workouts)
    except Exception as e:
        st.error(f"Error fetching data from Supabase: {e}")
        return empty_df, empty_df, empty_df

df_metrics, df_food, df_workouts = load_data()

st.title("Fitness OS — Dashboard")

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
        st.plotly_chart(fig_weight, use_container_width=True)
        
        # Steps Chart
        fig_steps = px.bar(df_metrics, x="date", y="steps", title="Daily Steps",
                          color_discrete_sequence=["#238636"])
        fig_steps.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_steps, use_container_width=True)
    else:
        st.info("No metric data found. Sync your Google Fit data to see trends.")

with tabs[1]:
    st.header("Workout Progress")
    if not df_workouts.empty:
        # Weekly Volume
        df_workouts['date'] = pd.to_datetime(df_workouts['date'])
        recent_workouts = df_workouts[df_workouts['date'] > (datetime.now() - timedelta(days=7))]
        weekly_volume = recent_workouts['volume_kg'].sum()
        
        st.subheader(f"Total Weekly Volume: {weekly_volume:,.0f} kg")
        
        # Recent History Table
        st.dataframe(df_workouts[['date', 'exercise_name', 'sets', 'reps', 'weight', 'volume_kg']], 
                    use_container_width=True, hide_index=True)
        
        # Exercise Progression
        selected_exercise = st.selectbox("Select Exercise to Track", df_workouts['exercise_name'].unique())
        ex_df = df_workouts[df_workouts['exercise_name'] == selected_exercise].sort_values('date')
        
        fig_ex = px.line(ex_df, x="date", y="weight", title=f"{selected_exercise} Progress",
                        color_discrete_sequence=["#8957e5"])
        fig_ex.update_layout(template="plotly_dark")
        st.plotly_chart(fig_ex, use_container_width=True)
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
        st.plotly_chart(fig_nutrition, use_container_width=True)
        
        st.subheader("Recent Food Logs")
        st.dataframe(df_food[['timestamp', 'description', 'calories', 'protein', 'carbs', 'fat']], 
                    use_container_width=True, hide_index=True)
    else:
        st.info("No food logs found. Start logging above!")
