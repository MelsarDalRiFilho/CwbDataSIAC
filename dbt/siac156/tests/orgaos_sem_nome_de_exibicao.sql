-- Aviso: órgão novo na fonte sem entrada no seed `orgaos` (aparece com o nome original).
{{ config(severity='warn') }}

select distinct orgao_origem
from {{ ref('int_solicitacoes__ultimo_snapshot') }}
where orgao_origem not in (select orgao_origem from {{ ref('orgaos') }})
