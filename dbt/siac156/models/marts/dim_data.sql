-- Calendário de 1º/jan do ano mais antigo até o snapshot mais recente.
with limites as (
    select
        date_trunc('year', min(data_criacao))::date as inicio,
        max(snapshot_data) as fim
    from {{ ref('stg_siac156__solicitacoes') }}
),

dias as (
    select unnest(generate_series(inicio, fim, interval 1 day))::date as data
    from limites
)

select
    data,
    year(data) as ano,
    quarter(data) as trimestre,
    month(data) as mes,
    day(data) as dia,
    isodow(data) as dia_semana,
    ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'][isodow(data)] as nome_dia_semana,
    ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto',
     'Setembro', 'Outubro', 'Novembro', 'Dezembro'][month(data)] as nome_mes,
    isodow(data) >= 6 as fim_de_semana
from dias
