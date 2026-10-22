-- O histórico agregado soma, em cada snapshot, o mesmo número de linhas da Bronze.
with bronze as (
    select snapshot_data, count(*) as linhas
    from {{ source('bronze', 'solicitacoes') }}
    group by all
),

agregado as (
    select snapshot_data, sum(quantidade) as linhas
    from {{ ref('fct_snapshot_agregado') }}
    group by all
)

select *
from bronze
full outer join agregado using (snapshot_data)
where bronze.linhas is distinct from agregado.linhas
