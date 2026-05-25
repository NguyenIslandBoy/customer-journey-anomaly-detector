SELECT
    event_date,
    COUNT(DISTINCT user_pseudo_id)                          AS total_sessions,
    COUNT(DISTINCT CASE WHEN traffic_source.medium = '(none)'
          THEN user_pseudo_id END)                          AS direct_sessions,
    SAFE_DIVIDE(
        COUNT(DISTINCT CASE WHEN traffic_source.medium = '(none)'
              THEN user_pseudo_id END),
        COUNT(DISTINCT user_pseudo_id)
    )                                                       AS direct_share
FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE
    event_name = 'session_start'
GROUP BY
    event_date
ORDER BY
    event_date ASC