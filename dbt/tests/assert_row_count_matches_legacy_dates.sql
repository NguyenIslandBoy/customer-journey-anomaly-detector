-- Each mart must hold exactly the days between vars start_date and end_date
-- (by default the sample's 92 days, 2020-11-01 to 2021-01-31): no gaps, no
-- extras. Returns each missing or unexpected date per mart.
with expected as (

    select event_date
    from unnest(generate_date_array(
        parse_date('%Y%m%d', '{{ var("start_date") }}'),
        parse_date('%Y%m%d', '{{ var("end_date") }}')
    )) as event_date

),

actual as (

    select distinct 'mart_channel_performance_daily' as model, event_date
    from {{ ref('mart_channel_performance_daily') }}

    union all

    select distinct 'mart_tracking_quality_daily' as model, event_date
    from {{ ref('mart_tracking_quality_daily') }}

),

models as (

    select distinct model from actual

)

select m.model, e.event_date, 'missing' as problem
from models as m
cross join expected as e
left join actual as a
    on a.model = m.model and a.event_date = e.event_date
where a.event_date is null

union all

select a.model, a.event_date, 'unexpected' as problem
from actual as a
left join expected as e
    on a.event_date = e.event_date
where e.event_date is null
