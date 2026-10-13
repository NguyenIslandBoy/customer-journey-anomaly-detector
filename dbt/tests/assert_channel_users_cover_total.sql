-- Every session_start user on a day sits in at least one source x medium row,
-- so the channel sum of users can never fall below the site total. A user can
-- appear under more than one source/medium, so equality is not expected.
-- Returns the days where the channel sum falls short.
with channel as (

    select event_date, sum(users) as channel_users
    from {{ ref('mart_channel_performance_daily') }}
    group by event_date

)

select
    t.event_date,
    t.total_users,
    c.channel_users
from {{ ref('mart_tracking_quality_daily') }} as t
left join channel as c
    on t.event_date = c.event_date
where coalesce(c.channel_users, 0) < t.total_users
