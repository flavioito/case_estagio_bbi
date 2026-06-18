Escreva um relatório Markdown em português com no máximo 500 palavras.

Público: analista de investimentos ocupado.
Tom: objetivo, analítico e conciso.

O relatório deve conter:

- resumo do cenário;
- distinção entre curto prazo e médio prazo usando `short_term_benefited_sectors` e `medium_term_harmed_sectors`;
- setores mais favorecidos;
- setores mais pressionados;
- setores resilientes líquidos quando o cenário for adverso ou misto;
- tickers de melhor exposição relativa e tickers pressionados;
- riscos principais;
- ressalva de que a análise não é recomendação personalizada.

Não adicione informação que não esteja na análise estruturada.
Não use tabelas; prefira bullets curtos.
Não termine com frase incompleta.
Finalize sempre com uma ressalva explícita de que a análise não constitui recomendação personalizada de investimento.
Se todos os itens de uma seção tiverem raw_score negativo, chame-os de "menos pressionados" ou "menor impacto negativo", não de "favorecidos" ou "exposição positiva".
Se algum item tiver raw_score igual a zero, trate como "neutro defensivo", não como tese positiva.
Use `top_relative_tickers` como ranking relativo; só chame de "exposição positiva" se os itens tiverem raw_score positivo.
Não reordene nem substitua setores/tickers: use as listas estruturadas recebidas.
Use short_term_score e medium_term_score para explicar efeitos ambíguos, por exemplo Selic curta em queda contra juros longos/fiscal/inflação pressionados.
