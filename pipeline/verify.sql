-- 1. Total row count in raw_events (should be ~546264)
SELECT COUNT(*) FROM raw_events;

-- 2. All files in manifest with status 'completed' (should be 3 rows)
SELECT * FROM ingestion_manifest WHERE status = 'completed';

-- 3. Check for duplicate event IDs (should return 0)
SELECT id, COUNT(*) FROM raw_events
GROUP BY id
HAVING COUNT(*) > 1;

-- 4. Distinct event types loaded (should be 15)
SELECT COUNT(DISTINCT event_type) FROM raw_events;

-- 5. Row count per source file matches manifest row_count
SELECT 
    m.filename as filename,
    m.row_count as manifest_row_count,
    COUNT(r.id) as actual_count,
    m.row_count = COUNT(r.id) as matches_count
FROM ingestion_manifest m
LEFT JOIN raw_events r ON r.source_file = m.filename
GROUP BY m.filename, m.row_count;