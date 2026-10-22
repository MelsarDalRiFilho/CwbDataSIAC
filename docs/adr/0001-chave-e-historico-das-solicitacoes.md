# ADR 0001 — Chave e histórico das solicitações

- **Status:** aceito
- **Data:** 2026-10-21
- **Evidência:** [`notebooks/00_exploracao.ipynb`](../../notebooks/00_exploracao.ipynb), com os snapshots de 18, 19 e 20/10/2026

## Contexto

A base SIAC 156 é publicada todo dia como um arquivo **acumulado do ano corrente** (cerca de 626 mil linhas e 123 MB em 20/10/2026). O plano inicial supunha que um hash dos campos estáveis, com um número de ordem para desempate, identificaria cada solicitação, e que um snapshot SCD2 do dbt registraria as mudanças de `Situacao`.

A exploração mostrou que essa premissa não se sustenta:

| Fato medido (snapshot de 20/10) | Valor |
| --- | --- |
| Número de protocolo ou qualquer identificador | inexistente |
| Hora em `DataCriacao` / `DataResposta` | inexistente (`dd/mm/aaaa`) |
| Linhas idênticas em **todas** as colunas | 38.882 excedentes em 26.515 grupos (maior grupo: 59) |
| Linhas idênticas nos campos estáveis (sem `Situacao` e `DataResposta`) | 50.822 excedentes em 33.307 grupos |
| Linhas de 19/10 que somem em 20/10, comparando só os campos estáveis | 275 (142 entre 18 e 19/10) |
| Ordem das linhas no arquivo | não segue a data e não é garantida entre arquivos |

As linhas idênticas são solicitações reais e distintas que ficam indistinguíveis. Os campos "estáveis" também são editados de um dia para o outro (órgão, logradouro, assunto). Assim, nenhuma combinação de colunas, nem a posição da linha, identifica uma solicitação de forma estável entre snapshots.

## Decisão

1. **Não deduplicar.** Cada linha do arquivo conta como uma solicitação.
2. **A camada Gold de solicitações é um retrato do último snapshot válido**, carregado em full refresh. A chave técnica `solicitacao_sk = hash(snapshot_data, número da linha no arquivo)` é única **apenas dentro do snapshot**, e isso fica documentado como tal.
3. **O histórico é guardado de forma agregada.** A cada carga, grava-se `fct_snapshot_agregado` com as contagens por `snapshot_data × Tipo × Orgao × Assunto × Bairro × Origem × Situacao` (incremental, append por `snapshot_data`). *Nota da fase 5:* na implementação, o grão inclui também a subdivisão do assunto e a regional, para usar as mesmas dimensões do fato (`dim_assunto`, `dim_localidade`). São cerca de 68 mil linhas por snapshot. É isso que permite séries como "quantas solicitações abertas havia em cada dia" e o fluxo entre situações no nível agregado.
4. **Os arquivos brutos de todos os snapshots são preservados no Bronze** (Parquet), o que permite reprocessar caso a decisão mude.
5. O snapshot dbt `snp_solicitacoes_status` (SCD2 por solicitação) **sai do escopo**.

## Consequências

- **Ganha-se:** modelagem honesta, simples e reprodutível, sem chave falsa nem ruído diário de exclusões e inclusões aparentes.
- **Perde-se:** o rastreio do status de uma solicitação individual ao longo do tempo. Métricas como "tempo em cada situação" deixam de ser possíveis; o tempo até a resposta continua disponível (`DataResposta − DataCriacao`).
- Os testes dbt de `unique` valem só para chaves de dimensão e para `solicitacao_sk` dentro do snapshot, nunca para a combinação de atributos.
- O README ganha a seção "Por que não há deduplicação", tratando a limitação da fonte com transparência.

## Alternativas consideradas

- **Pseudo-chave (hash dos campos estáveis + número de ordem) com SCD2:** descartada. Geraria centenas de falsos "exclusões e inclusões" por dia, e a atribuição de status dentro de grupos de linhas idênticas seria arbitrária.
- **SCD2 da contagem por grupo de campos estáveis:** descartada porque fica mais complexa para o mesmo poder analítico da agregação por dimensões.
