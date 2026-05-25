SELECT
    event_date,
    traffic_source.source     AS source,
    traffic_source.medium     AS medium,
    COUNT(DISTINCT CASE WHEN event_name = 'session_start'
          THEN user_pseudo_id END)                          AS sessions,
    COUNT(DISTINCT CASE WHEN event_name = 'purchase'
          THEN user_pseudo_id END)                          AS purchasers,
    SAFE_DIVIDE(
        COUNT(DISTINCT CASE WHEN event_name = 'purchase'
              THEN user_pseudo_id END),
        COUNT(DISTINCT CASE WHEN event_name = 'session_start'
              THEN user_pseudo_id END)
    )                                                       AS conversion_rate
FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
GROUP BY
    event_date,
    source,
    medium
ORDER BY
    event_date ASC