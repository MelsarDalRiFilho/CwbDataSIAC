-- Grão (bairro, regional): o mesmo bairro aparece em mais de uma regional na fonte
-- (ex.: CAJURU e NOVO MUNDO em 3), então a regional não é atributo do bairro.
select distinct
    md5(bairro || '|' || regional) as localidade_sk,
    bairro,
    regional
from {{ ref('stg_siac156__solicitacoes') }}
