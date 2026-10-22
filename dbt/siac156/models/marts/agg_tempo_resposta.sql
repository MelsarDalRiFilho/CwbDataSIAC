-- Tempo de resposta por órgão no último snapshot. A mediana só enxerga quem já foi
-- respondido (viés nos meses recentes), por isso os pendentes e a idade deles vêm ao lado.
select
    f.orgao_sk,
    o.orgao,
    count(*) as solicitacoes,
    count(*) filter (where f.respondida) as respondidas,
    count(*) filter (where not f.respondida) as pendentes,
    round(count(*) filter (where f.respondida) / count(*), 4) as taxa_resposta,
    median(f.dias_ate_resposta) as mediana_dias_resposta,
    quantile_cont(f.dias_ate_resposta, 0.9) as p90_dias_resposta,
    median(f.dias_em_aberto) as mediana_dias_em_aberto
from {{ ref('fct_solicitacoes') }} as f
inner join {{ ref('dim_orgao') }} as o using (orgao_sk)
group by all
