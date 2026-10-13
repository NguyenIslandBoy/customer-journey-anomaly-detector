-- Grain: event_date. The user columns mirror sql/direct_untagged_traffic.sql
-- (session_start events only); purchase columns are added from purchase events.
with session_starts as (

    select
        event_date,
        user_pseudo_id,
        acquisition_source,
        acquisition_medium
    from {{ ref('stg_ga4_events') }}
    where event_name = 'session_start'

),

users_daily as (

    select
        event_date,
        count(distinct user_pseudo_id) as total_users,
        count(distinct if(acquisition_medium = '(none)', user_pseudo_id, null)) as direct_users,
        count(distinct if(acquisition_source = '(data deleted)', user_pseudo_id, null)) as data_deleted_users,
        count(distinct if(
            acquisition_source = '(not set)' or acquisition_medium = '(not set)',
            user_pseudo_id,
            null
        )) as not_set_users
    from session_starts
    group by event_date

),

purchases as (

    select
        event_date,
        -- The sample stores most missing ids as the string '(not set)'.
        coalesce(transaction_id in ('', '(not set)'), true) as is_missing_transaction_id,
        transaction_id,
        event_timestamp
    from {{ ref('stg_ga4_events') }}
    where event_name = 'purchase'

),

purchases_flagged as (

    select
        event_date,
        is_missing_transaction_id,
        -- Every purchase after the first with the same id, across the whole
        -- shard range, counts as a duplicate on the date it occurred.
        not is_missing_transaction_id
            and row_number() over (
                partition by transaction_id, is_missing_transaction_id
                order by event_timestamp
            ) > 1 as is_duplicate_transaction_id
    from purchases

),

purchases_daily as (

    select
        event_date,
        count(*) as purchase_events,
        countif(is_missing_transaction_id) as purchase_events_missing_transaction_id,
        countif(is_duplicate_transaction_id) as purchase_events_duplicate_transaction_id
    from purchases_flagged
    group by event_date

)

select
    u.event_date,
    u.total_users,
    u.direct_users,
    safe_divide(u.direct_users, u.total_users) as direct_share,
    u.data_deleted_users,
    u.not_set_users,
    coalesce(p.purchase_events, 0) as purchase_events,
    coalesce(p.purchase_events_missing_transaction_id, 0) as purchase_events_missing_transaction_id,
    coalesce(p.purchase_events_duplicate_transaction_id, 0) as purchase_events_duplicate_transaction_id
from users_daily as u
left join purchases_daily as p
    on u.event_date = p.event_date
