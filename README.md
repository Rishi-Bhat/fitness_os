# Fitness OS — Personal Health Data Dashboard

A single-user personal dashboard that aggregates fitness data from Hevy (workouts), Google Fit (weight/steps), and food logs (parsed via Gemini).

## Features
- **📊 Overview**: Track weight and daily steps trends.
- **🏋️ Training**: Monitor workout volume and exercise progression (via Hevy).
- **🥗 Nutrition**: Log meals in natural language and track macros (via Gemini).
- **🤖 Automation**: Daily sync from external sources using GitHub Actions.

## Setup Instructions

### 1. Database Setup
1. Create a [Supabase](https://supabase.com/) project.
2. Run the SQL in `database/schema.sql` in the Supabase SQL Editor.

### 2. Environment Variables
Create a `.env` file or set the following secrets in GitHub:
- `SUPABASE_URL`: Your Supabase project URL.
- `SUPABASE_KEY`: Your Supabase Service Role Key.
- `GEMINI_API_KEY`: Google AI Studio API Key.
- `HEVY_USERNAME` / `HEVY_PASSWORD`: Hevy login credentials.
- `GOOGLE_FIT_CLIENT_ID` / `CLIENT_SECRET` / `REFRESH_TOKEN`: Google Fit OAuth credentials.

### 3. Local Development
```bash
pip install -r requirements.txt
playwright install chromium
streamlit run app/app.py
```

### 4. Deployment
- **Frontend**: Deploy to [Streamlit Cloud](https://streamlit.io/cloud).
- **Automation**: Push to GitHub to enable the daily sync via GitHub Actions.
