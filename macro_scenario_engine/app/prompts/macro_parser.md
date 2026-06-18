Extraia os fatores macroeconômicos implícitos no cenário do usuário.

Use somente fatores da lista permitida:

{macro_factor_list}

Cenário do usuário:
{scenario}

Regras:

- Não crie fatores novos.
- Não use tickers.
- Ignore opiniões de recomendação personalizada.
- Se houver ambiguidade, escolha apenas fatores claramente sustentados pelo texto.
- Retorne somente JSON válido no formato abaixo.

{{
  "macro_factors": ["factor_id"]
}}
