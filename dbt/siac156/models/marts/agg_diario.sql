-- Solicitações criadas e respondidas por dia (último snapshot); dias sem registro ficam com zero.
with criadas as (
    select data_criacao as data, count(*) as criadas
    from {{ ref('fct_solicitacoes') }}
    group by all
),

respondidas as (
    select data_resposta as data, count(*) as respondidas
    from {{ ref('fct_solicitacoes') }}
    where respondida
    group by all
)

select
    d.data,
    d.dia_semana,
    d.nome_dia_semana,
    d.fim_de_semana,
    coalesce(c.criadas, 0) as criadas,
    coalesce(r.respondidas, 0) as respondidas
from {{ ref('dim_data') }} as d
left join criadas as c using (data)
left join respondidas as r using (data)
where d.data >= (select min(data_criacao) from {{ ref('fct_solicitacoes') }})
