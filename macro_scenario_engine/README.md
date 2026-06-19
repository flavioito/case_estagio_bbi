# Macro Scenario Engine

Ferramenta em Python para transformar um cenário macroeconômico em linguagem natural em uma análise estruturada de sensibilidade setorial e de tickers da B3.

## Arquitetura Da Solução

```text
Cenário macro em linguagem natural
  -> validators.py
      Valida tamanho mínimo, escopo macro e bloqueia pedido de recomendação personalizada.
  -> pipeline.py
      Orquestra parser, scoring, seleção de rankings, riscos, relatório e validação final.
  -> macro_parser.md + llm_client.py
      Usa Claude para extrair fatores macro padronizados, como selic_down, brl_depreciation e china_growth_down.
  -> scoring.py
      Calcula scores por setor e ticker a partir da base curada de exposições.
  -> ticker_exposures_expanded.yaml
      Base de 63 tickers com setor, descrição, características, rationale e exposure_scores.
  -> schemas.py
      Valida o JSON final com Pydantic, tamanhos exatos de listas e limite do Markdown.
  -> report_writer.md + fallback determinístico
      Usa Claude para reescrever o Markdown sem alterar scores; se houver falha técnica, usa Python.
  -> main.py
      CLI para imprimir JSON, imprimir Markdown ou salvar os dois em app/output.
```

## Fluxo De Dados

| Componente | Responsabilidade |
| --- | --- |
| Entrada do cenário | Recebe texto via `--scenario` ou stdin e normaliza espaços. |
| Validação de escopo | Rejeita textos curtos, vazios ou pedidos como "qual ação devo comprar?". |
| Extração de fatores | Usa Claude restrito à lista permitida para detectar fatores macro. |
| Catálogo de dados | Carrega fatores macro, taxonomia setorial e base curada de tickers. |
| Scoring setorial | Agrega `exposure_scores` dos tickers por setor e calcula score absoluto, relativo, curto prazo e médio prazo. |
| Scoring por ticker | Soma exposições dos fatores detectados para cada ticker e classifica impacto absoluto/relativo. |
| Seleção principal | Retorna 5 setores beneficiados, 5 prejudicados, 3 tickers positivos e 3 negativos, priorizando `raw_score`. |
| Rankings de horizonte | Gera listas auxiliares de curto prazo, médio prazo e resiliência líquida. |
| Riscos da tese | Seleciona 3 riscos por regras determinísticas ligadas aos fatores macro detectados. |
| Relatório Markdown | Renderiza relatório de até 500 palavras, legível em poucos minutos por um analista ocupado. |
| Validação final | Pydantic e checks de universo garantem listas no tamanho certo, tickers conhecidos, fatores válidos e word count. |

## Módulos Principais

| Módulo | Responsabilidade |
| --- | --- |
| `app/main.py` | CLI principal com opções `--scenario`, `--markdown`, `--no-save` e `--log-level`. |
| `app/pipeline.py` | Fluxo ponta a ponta: valida cenário, extrai fatores, calcula rankings, cria riscos e monta saída. |
| `app/scoring.py` | Catálogo de dados, cálculo de scores, seleção de setores/tickers e rationales. |
| `app/schemas.py` | Schemas Pydantic do JSON final, enums de confiança e limite de 500 palavras. |
| `app/validators.py` | Validação de input, fatores conhecidos, universo de setores/tickers e relatório. |
| `app/llm_client.py` | Cliente Anthropic usado na extração JSON e na reescrita controlada do relatório. |
| `app/config.py` | Leitura de `.env`, caminhos, limites e parâmetros de ranking. |
| `app/prompts/macro_parser.md` | Prompt para extrair fatores macro usando apenas a lista permitida. |
| `app/prompts/report_writer.md` | Prompt para reescrever o relatório sem alterar dados estruturados. |
| `app/data/curated/ticker_exposures_expanded.yaml` | Base curada de tickers, exposições macro, características e rationales. |

## Saídas Geradas

Campos principais:

- `scenario`: cenário macro normalizado;
- `scenario_summary`: resumo curto dos fatores detectados;
- `macro_factors`: fatores padronizados usados no scoring;
- `benefited_sectors`: top 5 setores beneficiados;
- `harmed_sectors`: top 5 setores prejudicados ou, quando não houver negativos suficientes, menor exposição relativa;
- `short_term_benefited_sectors`: top 5 setores com melhor leitura de curto prazo;
- `medium_term_harmed_sectors`: top 5 setores mais pressionados no médio prazo;
- `net_resilient_sectors`: top 5 setores resilientes líquidos;
- `positive_tickers`: 3 tickers com maior exposição positiva;
- `negative_tickers`: 3 tickers com maior exposição negativa ou menor exposição relativa quando necessário;
- `risks`: top 3 riscos da tese não se materializar;
- `markdown_report`: relatório em Markdown com até 500 palavras;
- `metadata`: modelo usado, uso de LLM, fonte de dados, número de fatores e tamanho do universo.

Toda execução salva automaticamente:

- `app/output/analysis_YYYYMMDD_HHMMSS.json`;
- `app/output/analysis_YYYYMMDD_HHMMSS.md`.

O repositório também inclui exemplos versionados:

- `app/output/sample_output.json`;
- `app/output/sample_report.md`.

## Como Rodar

1. Abra o terminal na raiz do projeto.

```bash
cd macro_scenario_engine
```

2. Crie e ative um ambiente virtual.

No Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

No macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Instale as dependências.

```bash
python -m pip install -r requirements.txt
```

4. Configure Claude antes da execução.

Crie um arquivo `.env` a partir de `.env.example` e substitua
`your_api_key_here` pela sua chave da Anthropic:

```text
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-haiku-4-5
TICKER_EXPOSURES_PATH=
MAX_TOKENS=1200
ANTHROPIC_PARSER_MAX_TOKENS=800
ANTHROPIC_REPORT_MAX_TOKENS=900
ANTHROPIC_WRITE_REPORT=true
TEMPERATURE=0.2
REPORT_MAX_WORDS=500
TOP_SECTORS=5
TOP_TICKERS=3
RISK_COUNT=3
USE_ANTHROPIC=true
```

5. Rode uma análise.

```bash
python -m app.main --scenario "Selic em queda, inflação controlada, crédito voltando a crescer e atividade doméstica acelerando."
```

6. Para imprimir apenas o relatório Markdown.

```bash
python -m app.main --scenario "Petróleo em forte alta, real depreciado e risco fiscal elevado." --markdown
```

7. Ao rodar normalmente, JSON e Markdown são salvos em `app/output`.

```bash
python -m app.main --scenario "China desacelerando, minério em queda, dólar global forte e aversão a risco em emergentes."
```

## Prompt Engineering

Os prompts foram desenhados para reduzir alucinação, custo e inconsistência.
O LLM não decide rankings nem scores: ele só pode extrair fatores macro ou
reescrever um relatório a partir de dados já calculados em Python.

### 1. System Prompt: limitar universo analítico

O modelo deve atuar como analista macro-setorial para ações brasileiras, mas
sem usar conhecimento externo para inventar tickers, setores, preço-alvo,
valuation ou performance recente.

```text
Use apenas fatores macroeconômicos, setores e tickers fornecidos pela aplicação.
Não invente tickers, setores, dados financeiros, preço-alvo, valuation, múltiplos ou performance recente.
Não dê recomendação personalizada de investimento.
Explique mecanismos de transmissão macroeconômica de forma causal e objetiva.
```

### 2. Parser macro: lista fechada de fatores

O parser recebe a lista de fatores permitidos e o cenário do usuário. A saída
deve ser apenas JSON válido.

```text
Use somente fatores da lista permitida.
Não crie fatores novos.
Não use tickers.
Se houver ambiguidade, escolha apenas fatores claramente sustentados pelo texto.
Retorne somente JSON válido.
```

### 3. Scoring fora do LLM

O ranking de setores e tickers é determinístico. Depois da extração de fatores,
o Python calcula todos os scores usando `exposure_scores` da base curada. Isso
evita que o LLM mude empresas, pesos ou sinais macro sem rastreabilidade.

### 4. Writer com reescrita controlada do Markdown

O modelo do Claude reescreve o relatório final, mas recebe apenas dados estruturados já calculados:

- resumo do cenário;
- setores e tickers selecionados;
- scores absoluto, relativo, curto prazo e médio prazo;
- rationales;
- riscos.

O prompt proíbe tabelas, seções livres fora do formato, alteração de rankings e
tópicos como `Ressalva` ou `Limitação` no relatório gerado.

### 5. Validação e contingência técnica

Se a chamada Anthropic falhar ou se o Markdown vier truncado, longo demais, em
tabela ou com tópico proibido, o pipeline usa o relatório determinístico em
Python como contingência técnica. Para a execução esperada do case, a chave
Anthropic deve estar configurada.

## Modelo De LLM Utilizado

A chamada externa é parte do fluxo esperado e foi configurada para baixo custo.

- `ANTHROPIC_MODEL=claude-haiku-4-5`: modelo sugerido para parser e writer.
- `ANTHROPIC_PARSER_MAX_TOKENS=800`: suficiente para uma lista curta de fatores.
- `ANTHROPIC_REPORT_MAX_TOKENS=900`: limita a reescrita do relatório.
- `USE_ANTHROPIC=true`: padrão para uso automático de LLM em chamadas programáticas que não sobrescrevem `use_llm`.
- `ANTHROPIC_WRITE_REPORT=true`: permite writer com LLM quando o uso de LLM estiver ativo.

## Schema JSON

Campos principais de `AnalysisOutput`:

- `scenario`;
- `scenario_summary`;
- `macro_factors`;
- `benefited_sectors`;
- `harmed_sectors`;
- `short_term_benefited_sectors`;
- `medium_term_harmed_sectors`;
- `net_resilient_sectors`;
- `positive_tickers`;
- `negative_tickers`;
- `risks`;
- `markdown_report`;
- `metadata`.

Campos principais de cada setor:

- `sector_id`, `sector_name`;
- `score`, `raw_score`, `relative_score`;
- `short_term_score`, `medium_term_score`;
- `impact_label`;
- `matched_factors`;
- `rationale`;
- `confidence`.

Campos principais de cada ticker:

- `ticker`, `company`, `sector_id`, `sector_name`;
- `score`, `raw_score`, `relative_score`;
- `short_term_score`, `medium_term_score`;
- `impact_label`;
- `matched_positive_factors`;
- `matched_negative_factors`;
- `rationale`;
- `confidence`.

Categorias controladas:

- `confidence`: `low`, `medium`, `high`;
- `impact_label`: `impacto positivo`, `impacto negativo absoluto`,
  `menor exposição relativa` ou `neutro defensivo`.

## Scoring E Seleção

O scoring usa a matriz `exposure_scores` da base curada.

Para cada fator macro detectado:

1. Cada ticker recebe o score daquele fator.
2. O `raw_score` soma os fatores detectados.
3. O `relative_score` compara o ticker ou setor contra a média do universo.
4. Scores de curto e médio prazo aplicam pesos diferentes por fator.

A seleção principal prioriza impacto absoluto:

- `benefited_sectors`: maiores `raw_score` positivos;
- `harmed_sectors`: menores `raw_score` negativos;
- `positive_tickers`: maiores `raw_score` positivos;
- `negative_tickers`: menores `raw_score` negativos.

Quando não existem negativos suficientes, a ferramenta completa a lista com
menor exposição relativa e explicita isso no título do relatório. Assim o
contrato de tamanho fixo é preservado sem chamar de "negativo" algo que é
apenas menos beneficiado.

## Testes

```bash
python -m pytest
```

Os testes cobrem:

- schema Pydantic;
- validação de input e universo;
- parser heurístico de fatores macro;
- scoring setorial;
- scoring de tickers;
- seleção por impacto absoluto;
- diversificação de tickers com scores próximos;
- pipeline ponta a ponta;
- priorização de riscos;
- relatório Markdown e limite de 500 palavras;
- rejeição de relatórios truncados ou com tópicos proibidos.

## Limitações

1. **A base curada não cobre toda a bolsa.**

   O MVP usa 63 tickers líquidos e representativos da B3. Empresas fora dessa base não aparecem nos rankings, mesmo que sejam sensíveis ao cenário.

2. **A qualidade depende dos `exposure_scores`.**

   Os resultados são rastreáveis à matriz curada, mas a qualidade analítica
   depende da calibração dessas exposições por fator macro.

2. **Não utiliza LLM para validação.**

   A ferramenta não possui camada de validação qualitativa por LLM sobre os rankings gerados.

## Próximos Passos

1. **Expandir a base curada.**

   Incluir mais tickers, histórico de alterações e justificativas formais para
   cada exposição macro.

2. **Adicionar calibração quantitativa.**

   Comparar os `exposure_scores` contra séries históricas, betas setoriais ou
   estudos de sensibilidade para reduzir subjetividade.

3. **Utilizar LLM para validação**

   Utilizar o modelo do Claude para revisar a seleção de setores, tickers, scores e riscos e apresentar sugestões.

## Casos Testes Utilizados

Foram utilizados quatro casos testes que estão armazenados na pasta `output`.

Caso 1: 
```text
O Banco Central inicia um ciclo de afrouxamento monetário mais forte do que o esperado, reduzindo a Selic de forma acelerada em poucas reuniões. A decisão é justificada pela desaceleração da atividade doméstica e pela piora do mercado de trabalho, mas ocorre em um ambiente ainda marcado por inflação corrente elevada e expectativas desancoradas. A curva de juros longa reage com volatilidade: os vértices curtos caem, enquanto os prêmios longos permanecem pressionados por dúvidas sobre a sustentabilidade fiscal e a credibilidade da política monetária.
```

Caso 2:

```text
O preço internacional do petróleo sobe de forma abrupta após um choque geopolítico relevante, levando o Brent para patamares historicamente elevados. Ao mesmo tempo, o real sofre forte depreciação diante da aversão global a risco e da saída de capital de mercados emergentes. A combinação de petróleo caro e câmbio depreciado pressiona combustíveis, fretes, energia e diversos custos industriais, provocando uma aceleração relevante da inflação ao consumidor.
```

Caso 3:

```text
A economia chinesa entra em uma desaceleração mais intensa do que o esperado, puxada por crise prolongada no setor imobiliário, queda na confiança do consumidor e redução do investimento em infraestrutura. A demanda por minério de ferro, aço e outras commodities metálicas enfraquece rapidamente, provocando queda expressiva dos preços internacionais. O choque reduz os termos de troca de países exportadores de commodities e aumenta a percepção de risco sobre empresas altamente dependentes da demanda chinesa.
```

Caso 4: 

```text
O governo anuncia uma expansão fiscal relevante, com aumento de gastos obrigatórios e flexibilização das metas fiscais. O mercado passa a questionar a trajetória da dívida pública, exigindo prêmios de risco maiores nos títulos longos. Como consequência, a curva de juros abre de forma expressiva, o real se deprecia e as expectativas de inflação voltam a subir. Mesmo sem aceleração imediata da atividade, o ambiente macro se torna mais adverso por causa da combinação de incerteza fiscal, juros longos elevados e câmbio pressionado.
```

## Log De Tempo Gasto

O tempo aproximado gasto neste case foi:

| Etapa | Tempo Gasto |
| --- | --- |
| Entendimento do problema e definição de escopo | 1 hora |
| Construção da base curada | 3,5 horas |
| Implementação Inicial + Testes | 2 horas |
| Confidence Scoring | 1 hora |
| Aumento da base curada | 1 hora |
| Documentação | 30 minutos |

## Aprofundamento No Case

Este case necessitou de mais tempo para ser desenvolvido devido à maior complexidade em relação à base de dados, que é essencial para seu funcionamento. Devido à isso, as extensões ficaram em segundo plano para garantir o funcionamento básico da ferramenta. No entanto, uma delas foi implementada (confidence scoring) pois evita que todo resultado seja tratado da mesma forma, ajudando o analista a identificar quais setores e tickers têm maior convicção relativa dentro do cenário analisado.
