-- Grain: event_date x source x medium, over every event (not only
-- session_start), mirroring sql/conversion_rate_by_source.sql. Combinations
-- with events but no session_start therefore appear with users = 0 and a
-- null user_conversion_rate, exactly as in the legacy extract.
with events as (

    select
        event_date,
        acquisition_source as source,
        acquisition_medium as medium,
        event_name,
        user_pseudo_id,
        session_key
    from {{ ref('stg_ga4_events') }}

),

daily as (

    select
        event_date,
        source,
        medium,
        count(distinct if(event_name = 'session_start', user_pseudo_id, null)) as users,
        count(distinct if(event_name = 'session_start', session_key, null)) as session_count,
        -- Purchasers are not required to have a session_start in the same
        -- row, as in the legacy query, so purchasers > users is possible.
        count(distinct if(event_name = 'purchase', user_pseudo_id, null)) as purchasers
    from events
    group by event_date, source, medium

)

select
    event_date,
    source,
    medium,
    users,
    session_count,
    purchasers,
    safe_divide(purchasers, users) as user_conversion_rate
from daily
