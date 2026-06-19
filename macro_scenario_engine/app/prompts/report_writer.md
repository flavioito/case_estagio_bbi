Escreva um relatorio Markdown em portugues com no maximo 500 palavras.

Publico: analista de investimentos ocupado.
Tom: objetivo, analitico e conciso.

Formato obrigatorio:

- Titulo.
- Paragrafo introdutorio com resumo do cenario.
- Secao `## Horizonte` com bullets para curto prazo e medio prazo.
- Secao `## Setores` com bullets para favorecidos/resilientes e pressionados/menor exposicao relativa.
- Secao `## Tickers` com bullets para exposicao positiva e exposicao negativa/menor exposicao.
- Secao `## Riscos` com bullets curtos.

Regras:

- Nao adicione informacao que nao esteja na analise estruturada.
- Nao use tabelas.
- Nao escreva secoes no formato `**Topico.** texto`; use cabecalhos Markdown e bullets.
- Nao crie secao, topico, bullet ou paragrafo chamado `Ressalva`, `Limitação` ou `Limitacao`.
- Nao reordene nem substitua setores/tickers: use as listas estruturadas recebidas.
- Se todos os itens de uma secao tiverem raw_score negativo, chame-os de "menos pressionados" ou "menor impacto negativo", nao de "favorecidos" ou "exposicao positiva".
- Se algum item tiver raw_score igual a zero, trate como "neutro defensivo", nao como tese positiva.
- Use `positive_tickers` como ranking de exposicao positiva; se algum item tiver raw_score <= 0, chame de "menos pressionados".
- Use `negative_tickers` como ranking de exposicao negativa; se todos tiverem raw_score >= 0, chame de "menor exposicao relativa".
- Use `short_term_score` e `medium_term_score` para explicar efeitos ambiguos.
- Nao termine com frase incompleta.
