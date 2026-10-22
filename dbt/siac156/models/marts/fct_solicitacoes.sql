-- Retrato do último snapshot, uma linha por solicitação (full refresh). Sem logradouro (LGPD).
select
    s.solicitacao_sk,
    s.snapshot_data,
    s.linha,
    s.data_criacao,
    s.data_resposta,
    md5(s.orgao) as orgao_sk,
    md5(s.assunto || '|' || s.subdivisao) as assunto_sk,
    md5(s.bairro || '|' || s.regional) as localidade_sk,
    md5(s.origem) as origem_sk,
    s.tipo,
    s.situacao,
    s.respondida,
    s.dias_ate_resposta,
    case when not s.respondida then date_diff('day', s.data_criacao, s.snapshot_data) end
        as dias_em_aberto
from {{ ref('int_solicitacoes__ultimo_snapshot') }} as s
