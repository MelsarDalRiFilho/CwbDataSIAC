{#- Falha para cada linha em que a expressão SQL é falsa. Serve em modelo ou coluna. -#}
{% test expression_is_true(model, expression, column_name=none) %}
select *
from {{ model }}
where not ({{ expression }})
{% endtest %}
