select distinct
    md5(origem) as origem_sk,
    origem
from {{ ref('stg_siac156__solicitacoes') }}
