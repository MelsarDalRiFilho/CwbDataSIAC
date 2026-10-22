select distinct
    md5(assunto || '|' || subdivisao) as assunto_sk,
    assunto,
    subdivisao
from {{ ref('stg_siac156__solicitacoes') }}
