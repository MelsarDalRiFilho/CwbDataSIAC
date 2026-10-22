-- Sem deduplicação (ADR 0001): o fato tem exatamente as linhas do último snapshot da Bronze.
with bronze as (
    select count(*) as linhas
    from {{ source('bronze', 'solicitacoes') }}
    where snapshot_data = (select max(snapshot_data) from {{ source('bronze', 'solicitacoes') }})
),

fato as (
    select count(*) as linhas from {{ ref('fct_solicitacoes') }}
)

select bronze.linhas as linhas_bronze, fato.linhas as linhas_fato
from bronze, fato
where bronze.linhas <> fato.linhas
