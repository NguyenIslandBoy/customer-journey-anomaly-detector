SELECT
    event_date,
    traffic_source.source     AS source,
    traffic_source.medium     AS medium,
    COUNT(DISTINCT user_pseudo_id) AS sessions
FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE
    event_name = 'session_start'
GROUP BY
    event_date,
    source,
    medium
ORDER BY
    event_date ASC,
    sessions DESC