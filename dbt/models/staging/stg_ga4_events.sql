-- One row per GA4 event, all event names kept.
-- Not filtered to session_start/purchase: the legacy conversion query
-- (sql/conversion_rate_by_source.sql) has no WHERE clause, so it emits
-- date x source x medium rows that have events but no session_start
-- (sessions = 0). Those rows reach the detectors, so parity needs them.
with events as (

    select *
    from {{ source('ga4', 'events') }}
    where _table_suffix between '{{ var("start_date") }}' and '{{ var("end_date") }}'

),

renamed as (

    select
        parse_date('%Y%m%d', event_date) as event_date,
        event_timestamp,
        event_name,
        user_pseudo_id,
        -- max() rather than a bare scalar subquery: a bare one can raise
        -- "more than one element", so BigQuery must evaluate it on every row
        -- and reads event_params (~0.9 GB) even when ga_session_id is not
        -- selected. The aggregate cannot fail, so the column is pruned.
        -- Same result here: every event carries exactly one ga_session_id
        -- (checked 2026-10-13 over all 4,295,584 events).
        (
            select max(value.int_value)
            from unnest(event_params)
            where key = 'ga_session_id'
        ) as ga_session_id,
        -- traffic_source is the user's first acquisition source in the GA4
        -- export, not the session's source.
        traffic_source.source as acquisition_source,
        traffic_source.medium as acquisition_medium,
        ecommerce.transaction_id,
        ecommerce.purchase_revenue,
        ecommerce.purchase_revenue_in_usd

    from events

)

select
    *,
    concat(user_pseudo_id, '-', cast(ga_session_id as string)) as session_key
from renamed
