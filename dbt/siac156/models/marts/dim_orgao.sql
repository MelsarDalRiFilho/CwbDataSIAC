select distinct
    md5(orgao) as orgao_sk,
    orgao
from {{ ref('stg_siac156__solicitacoes') }}
