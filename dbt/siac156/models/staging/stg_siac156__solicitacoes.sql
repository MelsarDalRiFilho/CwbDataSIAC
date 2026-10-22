-- Tipagem e padronização das linhas da Bronze, sem deduplicar (ADR 0001).
with source as (
    select * from {{ source('bronze', 'solicitacoes') }}
),

orgaos as (
    select * from {{ ref('orgaos') }}
),

regionais as (
    select * from {{ ref('regionais') }}
),

tipado as (
    select
        snapshot_data,
        linha,
        trim(Tipo) as tipo,
        trim(Orgao) as orgao_origem,
        try_strptime(DataCriacao, '%d/%m/%Y')::date as data_criacao,
        trim(Assunto) as assunto,
        trim(Subdivisao) as subdivisao,
        trim(Situacao) as situacao,
        nullif(trim(Logradouro), '') as logradouro,
        coalesce(nullif(upper(trim(Bairro)), ''), 'NÃO INFORMADO') as bairro,
        nullif(trim(Regional), '') as regional_origem,
        try_strptime(DataResposta, '%d/%m/%Y')::date as data_resposta,
        trim(Origem) as origem
    from source
)

select
    md5(cast(t.snapshot_data as varchar) || '-' || cast(t.linha as varchar)) as solicitacao_sk,
    t.snapshot_data,
    t.linha,
    t.tipo,
    coalesce(o.orgao_nome, t.orgao_origem) as orgao,
    t.orgao_origem,
    t.data_criacao,
    t.assunto,
    t.subdivisao,
    t.situacao,
    t.logradouro,
    t.bairro,
    coalesce(r.regional_nome, t.regional_origem, 'Não informada') as regional,
    t.data_resposta,
    t.origem,
    t.data_resposta is not null as respondida,
    date_diff('day', t.data_criacao, t.data_resposta) as dias_ate_resposta
from tipado as t
left join orgaos as o on t.orgao_origem = o.orgao_origem
left join regionais as r on t.regional_origem = r.regional_origem
