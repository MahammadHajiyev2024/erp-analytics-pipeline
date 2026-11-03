{% macro generate_schema_name(custom_schema_name, node) -%}

    {#
        CI's target.schema is already 'ci', and the CI user has no grants on gold/silver
        (ADR 23) -- route every model there regardless of its custom schema, so CI never
        tries to touch (or needs access to) the real medallion schemas.
    #}
    {%- if custom_schema_name is none or target.name == 'ci' -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}

{%- endmacro %}
