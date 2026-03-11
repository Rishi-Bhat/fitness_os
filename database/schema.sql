-- Fitness OS Database Schema

-- Table for daily health metrics
CREATE TABLE IF NOT EXISTS daily_metrics (
    date DATE PRIMARY KEY,
    weight DECIMAL(5, 2),
    steps INTEGER,
    body_fat_pct DECIMAL(4, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table for parsed food logs
CREATE TABLE IF NOT EXISTS food_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL,
    calories INTEGER,
    protein DECIMAL(6, 2),
    carbs DECIMAL(6, 2),
    fat DECIMAL(6, 2),
    raw_prompt TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table for workout sessions
CREATE TABLE IF NOT EXISTS workouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    exercise_name TEXT NOT NULL,
    sets INTEGER,
    reps INTEGER,
    weight DECIMAL(6, 2),
    volume_kg DECIMAL(10, 2),
    hevy_workout_id TEXT, -- To prevent duplicates from Hevy sync
    set_index INTEGER, -- To distinguish sets within the same exercise
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hevy_workout_id, exercise_name, set_index)
);

-- Index for date-based queries
CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
CREATE INDEX IF NOT EXISTS idx_food_logs_timestamp ON food_logs(timestamp);

-- Table for tracking manual and automated syncs
CREATE TABLE IF NOT EXISTS sync_logs (
    source TEXT PRIMARY KEY, -- 'hevy' or 'google_fit'
    last_sync TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
