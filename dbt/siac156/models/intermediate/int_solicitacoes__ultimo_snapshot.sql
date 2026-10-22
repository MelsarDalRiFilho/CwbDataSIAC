-- Retrato atual: só as linhas do snapshot mais recente da Bronze (ADR 0001).
select *
from {{ ref('stg_siac156__solicitacoes') }}
where snapshot_data = (select max(snapshot_data) from {{ source('bronze', 'solicitacoes') }})
