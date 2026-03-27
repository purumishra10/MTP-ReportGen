-- Supabase migration: Create the reports table
-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor → New Query)

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Reports metadata table
CREATE TABLE IF NOT EXISTS reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    report_date DATE NOT NULL,
    departments TEXT[] NOT NULL DEFAULT '{}',
    file_path TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for fast date-based queries
CREATE INDEX IF NOT EXISTS idx_reports_date ON reports (report_date DESC);

-- Enable Row Level Security (optional but recommended)
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

-- Allow all operations for authenticated users (adjust as needed)
CREATE POLICY "Allow all for authenticated users"
    ON reports
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Create storage bucket for report files
-- Note: You may need to create this via the Supabase Dashboard → Storage → New Bucket
-- Bucket name: "reports"
-- Make it public or private based on your needs
