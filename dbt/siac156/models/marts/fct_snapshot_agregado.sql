-- Histórico do projeto (ADR 0001): contagem de solicitações por snapshot e dimensões.
-- Incremental: a cada build processa o snapshot mais recente já carregado em diante
-- (delete+insert por snapshot_data). Recarga de snapshots antigos exige --full-refresh.
{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='snapshot_data',
    )
}}

select
    snapshot_data,
    md5(orgao) as orgao_sk,
    md5(assunto || '|' || subdivisao) as assunto_sk,
    md5(bairro || '|' || regional) as localidade_sk,
    md5(origem) as origem_sk,
    tipo,
    situacao,
    count(*) as quantidade,
    count(*) filter (where respondida) as respondidas
from {{ ref('stg_siac156__solicitacoes') }}
{% if is_incremental() %}
where snapshot_data >= (select max(snapshot_data) from {{ this }})
{% endif %}
group by all
