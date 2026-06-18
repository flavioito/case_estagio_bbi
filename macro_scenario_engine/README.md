# Macro Scenario Engine

Ferramenta Python para transformar cenários macroeconômicos em uma análise estruturada de sensibilidade setorial para ações brasileiras.

O MVP combina uma base curada de fatores, setores e tickers com scoring determinístico em Python. A integração com Claude/Anthropic fica isolada em `app/llm_client.py` e pode ser usada para extração de fatores quando `ANTHROPIC_API_KEY` estiver configurada, mas a aplicação também roda localmente com parser heurístico.

Por padrão, a chamada paga ao Claude fica desligada (`USE_ANTHROPIC=false`). Quando `--use-llm` for usado, o projeto assume um modelo Haiku de menor custo, limita a etapa do parser a poucos tokens de saída e pode usar o modelo para reescrever o relatório final sem alterar fatores, setores, tickers ou scores definidos pelo Python.

## O que faz

- Recebe um cenário macro em linguagem natural.
- Extrai fatores macro padronizados, como `selic_down`, `inflation_down`, `brl_appreciation` e `china_growth_down`.
- Calcula scores setoriais a partir da base curada de exposições por ticker.
- Seleciona exatamente 5 setores favorecidos/resilientes, 5 setores pressionados, 5 setores de melhor leitura no curto prazo, 5 setores mais pressionados no médio prazo, 5 setores resilientes líquidos, 3 tickers de melhor exposição relativa, 3 tickers pressionados e 3 riscos.
- Retorna JSON validado por Pydantic e relatório Markdown com até 500 palavras.

## O que não faz

- Não fornece recomendação personalizada de investimento.
- Não calcula preço-alvo, valuation, múltiplos ou upside.
- Não promete retorno nem substitui revisão de analista humano.
- Não usa dados de mercado em tempo real no MVP.

## Como rodar

```powershell
cd macro_scenario_engine
pip install -r requirements.txt
python -m app.main --scenario "Selic em queda, inflação controlada, crédito voltando a crescer e atividade doméstica acelerando."
```

Para imprimir somente o relatório Markdown:

```powershell
python -m app.main --scenario "Petróleo em forte alta, real depreciado e risco fiscal elevado." --markdown
```

Para salvar JSON e Markdown em `app/output`:

```powershell
python -m app.main --scenario "China desacelerando, minério em queda, dólar global forte e aversão a risco em emergentes." --save
```

Para usar Claude na extração dos fatores macro:

```powershell
copy .env.example .env
# preencha ANTHROPIC_API_KEY
python -m app.main --scenario "Real forte, commodities em queda, inflação menor e início de ciclo de queda de juros." --use-llm
```

## Controle de custo Anthropic

O projeto foi ajustado para caber em um orçamento pequeno, como US$ 2,50:

- `USE_ANTHROPIC=false` por padrão, então o MVP não consome tokens sem opção explícita.
- `ANTHROPIC_MODEL=claude-haiku-4-5` em `.env.example`, priorizando a família Haiku.
- `ANTHROPIC_PARSER_MAX_TOKENS=800`, pois o Claude só precisa retornar uma lista curta de fatores.
- `ANTHROPIC_REPORT_MAX_TOKENS=900`, para reescrever o relatório em Markdown sem expandir demais a resposta.
- `ANTHROPIC_WRITE_REPORT=true`, permitindo que `--use-llm` use Claude também na redação final. Troque para `false` se quiser gastar tokens apenas no parser.
- A lógica de scoring, seleção de setores/tickers, riscos e relatório permanece em Python.
- Caso a chamada Anthropic falhe ou a chave não esteja configurada, a pipeline usa o parser heurístico local.

Confirme no Console/Docs da Anthropic o identificador exato do modelo Haiku disponível na sua conta. Se necessário, substitua `ANTHROPIC_MODEL` mantendo a preferência por Haiku para preservar o orçamento.

## Estrutura

```text
app/
  config.py              # configuração e caminhos
  schemas.py             # schemas Pydantic da saída
  validators.py          # validações de input, universo e relatório
  scoring.py             # scoring setorial e seleção de tickers
  llm_client.py          # cliente Anthropic opcional
  pipeline.py            # fluxo ponta a ponta
  main.py                # CLI
  data/
    macro_factors.yaml
    sector_taxonomy.yaml
    sector_macro_scores.yaml
    curated/ticker_exposures_expanded.yaml
```

## Base curada

A base padrão `app/data/curated/ticker_exposures_expanded.yaml` contém 63 tickers líquidos e representativos da B3. Para cada ticker há setor interno, grupo do MVP, descrição do negócio, exposições positivas/negativas, matriz `exposure_scores`, características da empresa, rationale e nível de confiança.

Para usar outra base compatível, defina `TICKER_EXPOSURES_PATH` no `.env`.

A taxonomia de análise em `sector_taxonomy.yaml` agrega os setores internos em blocos analíticos como bancos, seguradoras, mercado de capitais, óleo e gás, mineração, siderurgia, varejo, construção, shoppings, utilities, saúde, educação, telecom e tecnologia.

## Scoring

O scoring setorial é derivado em tempo de execução pela média dos `exposure_scores` dos tickers de cada setor. Isso evita manter duas fontes de verdade: a sensibilidade do setor sempre pode ser rastreada de volta à base curada de tickers.

A saída também separa rankings setoriais por horizonte: `short_term_benefited_sectors`, `medium_term_harmed_sectors` e `net_resilient_sectors`. O campo `top_relative_tickers` traz os tickers de melhor leitura relativa, que podem ser positivos em termos absolutos ou apenas menos pressionados em cenários adversos. Scores absolutos iguais a zero são tratados como `neutro defensivo`, evitando que posições apenas defensivas sejam descritas como tese positiva.

## Testes

```powershell
python -m pytest
```

Os testes cobrem schema, validação, scoring e pipeline ponta a ponta sem depender de chamada externa ao modelo.

## Limitações

O MVP é uma primeira camada de leitura macro-setorial. Ele depende da qualidade da base curada, não cobre toda a bolsa, não captura eventos corporativos recentes automaticamente e deve ser tratado como apoio analítico, não como recomendação de compra ou venda.
