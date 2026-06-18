# Earnings Call Intelligence Tracker

Ferramenta em Python para transformar uma transcrição de Earnings call
em uma análise estruturada para research financeiro.

## Arquitetura da Solução

```text
PDF transcript
  -> pdf_loader.py
      Extrai texto por página e metadados/header do PDF bruto.
  -> transcript_cleaner.py
      Remove ruído, corrige hifenização de quebra de linha e normaliza texto.
  -> segmenter.py
      Gera transcript_segments.json e qa_turns.json.
  -> prompts.py + anthropic_client.py
      Monta uma chamada principal ao Claude e envia schema + contexto.
  -> schemas.py
      Valida o JSON com Pydantic e enums controlados.
  -> pipeline.py
      Enriquece metadados, aplica política de surprise score e orquestra checks.
  -> evidence_checker.py
      Verifica se as quotes existem literalmente ou aproximadamente no texto.
  -> consistency_checker.py
      Checa inconsistências internas, contexto de consenso e suporte numérico.
  -> self-critique loop
      Revisa o JSON usando evidence_report + consistency_report.
  -> report_writer.py
      Renderiza executive_report.md de forma determinística.
  -> app.py
      Streamlit para upload, relatório, evidence audit e citation tracking.
```

## Fluxo De Dados

| Componente | Responsabilidade |
| --- | --- |
| Ingestão do PDF | Recebe a transcrição enviada pelo Streamlit e extrai texto por página, metadados e header bruto. |
| Limpeza da transcrição | Remove ruído recorrente, normaliza quebras de linha e corrige hifenizacao sem reinterpretar conteúdo financeiro. |
| Segmentação por speaker | Gera blocos estruturados com speaker, cargo, página, `section`, `block_type`, `word_count` e `has_question`. |
| Agrupamento de Q&A | Cria `qa_turns.json`, conectando pergunta do analista, resposta do management, clarificações e follow-ups pelo mesmo `qa_turn_id`. |
| Chamada principal ao Claude | Envia segmentos, Q&A agrupado, schema JSON e contextos opcionais em uma única chamada para gerar a análise completa. |
| Validação de schema | Usa Pydantic para garantir campos obrigatórios, tipos, limites de listas e categorias controladas. |
| Enriquecimento determinístico | Preenche metadados objetivos, flags de contexto, comparação temporal e política de cap do surprise score. |
| Validação de evidências | Confirma se as citações existem na transcrição e adiciona `evidence_validated`, `speaker_validated`, `match_type` e `source_block_ids`. |
| Avaliação de consistência | Audita conflitos internos, evidências inválidas, suporte numérico, contexto de consenso e coerência do surprise score. |
| Self-critique loop | Revisa o JSON usando Haiku por padrão e Sonnet apenas quando há issue `high`/`medium` ou `valid_quote_rate < 0.90`. |
| Revalidação pós-crítica | Recalcula evidências e consistência depois do self-critique para evitar que a revisão escape dos checks locais. |
| Relatório | Renderiza `executive_report.md` por código a partir do JSON final e das evidências verificadas, sem usar Markdown livre do LLM. |
| Streamlit | Permite upload, execução da análise, leitura do relatório, download em PDF e citation tracking visual. |

## Módulos Principais

| Módulo | Responsabilidade |
| --- | --- |
| `analyze_call.py` | CLI principal com opções de contexto, debug, extract-only e self-critique. |
| `app.py` | Interface Streamlit para rodar a análise e inspecionar evidências visualmente. |
| `src/pdf_loader.py` | Validação do PDF, extração por página e leitura de metadados/header. |
| `src/transcript_cleaner.py` | Limpeza conservadora, remoção de headers repetidos e correção de hifenização. |
| `src/segmenter.py` | Segmentação por speaker, taxonomia `section`/`block_type`, cargos e `qa_turn_id`. |
| `src/prompts.py` | Prompts efetivamente usados na chamada principal, reparo e self-critique. |
| `src/schemas.py` | Schema Pydantic do JSON final e enums de classificação. |
| `src/evidence_checker.py` | Validação mecânica das citações e mapeamento para `source_block_ids`. |
| `src/consistency_checker.py` | Auditoria deterministica de consistencia do resultado. |
| `src/history_context.py` | Compactação de histórico de transcrições para comparação temporal. |
| `src/report_writer.py` | Relatório executivo deterministicamente renderizado a partir do JSON. |

## Saídas Geradas

Saídas principais:

- `output/analysis.json`: JSON analítico validado por Pydantic.
- `output/evidence_report.json`: auditoria mecânica das citações literais.
- `output/consistency_report.json`: checagem determinística de consistência
  entre JSON, evidências, contexto e surprise score.
- `output/executive_report.md`: relatório executivo em Markdown, com limite de 400 palavras, renderizado por código a partir do JSON validado.
- `output/run_metadata.json`: metadados da execução, modelos, parâmetros,
  contexto utilizado, gatilhos de self-critique e resumo de qualidade.

Saídas intermediárias:

- `output/clean_text.txt`: texto extraído e limpo.
- `output/transcript_segments.json`: blocos por speaker, cargo, página,
  `section`, `block_type`, `qa_turn_id`, `word_count` e `has_question`.
- `output/qa_turns.json`: turnos de Q&A agrupando pergunta, resposta,
  clarificações de RI e follow-ups.

## Como Rodar

1. Abra o terminal na raiz do projeto.

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

4. Configure a chave da Anthropic.

Crie um arquivo `.env` na raiz do projeto. Dentro dele, substitua
`your_api_key_here` pela sua chave da Anthropic:

```text
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-haiku-4-5
ANTHROPIC_REVIEW_MODEL=claude-sonnet-4-6
OUTPUT_DIR=output
TEMPERATURE=0.1
MAX_OUTPUT_TOKENS=12000
DEBUG=false
```

5. Inicie a interface Streamlit.

```bash
streamlit run app.py
```

Depois de iniciar o Streamlit, abra no navegador o endereço exibido no terminal, geralmente:

```text
http://localhost:8501
```

6. Envie a transcrição pela interface.

Na tela inicial do Streamlit:

- clique no campo de upload;
- selecione o PDF da earnings call;
- clique em `Confirmar`.

7. Leia o relatório.

Quando a análise terminar, o app abre o relatório final em uma janela modal.
Nessa tela, é possível:

- ler o relatório;
- baixar o relatório em PDF;
- inspecionar o `Citation Tracking`, que mostra cada citação, status de validação, speaker, página e bloco original da transcrição.

8. Opcionalmente, adicione contexto antes de fazer upload. 

Para usar esse recurso no Streamlit, deixe os arquivos na pasta `data` antes de enviar o PDF pela interface. Se existirem, a ferramenta busca automaticamente arquivos de contexto nestes formatos:

```text
data/{TICKER}_{QUARTER}_pre_call_consensus.json
context/{TICKER}_history_context.json
```

9. Para encerrar o app, volte ao terminal e pressione `Ctrl+C`.

## Prompt Engineering

Os prompts foram desenhados para reduzir alucinação, custo e retrabalho. Em vez de chamadas modulares caras para tom, guidance, red flags e Q&A, a ferramenta faz uma chamada principal única com schema completo e depois usa validações locais.

### 1. System Prompt: limitar universo de informação

O modelo não pode usar memória externa sobre a companhia ou mercado. O objetivo é tornar o resultado auditável a partir dos arquivos de entrada.

```text
Analyze only the provided transcript segments and optional prior context.
Do not use outside knowledge.
Every analytical claim must be grounded in literal transcript evidence.
If evidence is insufficient, say so in the limitations rather than inventing.
Do not invent guidance, consensus expectations, analyst names, financial figures, or management roles.
Red flags are linguistic indicators, not proof of misconduct.
Return valid JSON only.
```

### 2. Chamada principal única com schema

Uma única chamada principal reduz custo e evita inconsistências entre
módulos independentes. 

```text
Single-call analysis task:
Use one integrated pass to analyze the full transcript and return the complete JSON.
Do not ask for follow-up calls. Do not split the task into separate model calls.
Do not generate Markdown in the JSON. The final report will be rendered by code from structured fields.
Prefer a compact but complete JSON. It is more important to close valid JSON than to include every possible observation.
```

### 3. Guidance: separar fala da call, inferência e contexto externo

Guidance e material para investidores, então o prompt obriga o modelo
a diferenciar número dito na call, número vindo do consenso e conclusão
inferida.

```text
If a new numeric guidance range is not literally stated in the transcript, do not present it as a formal call statement.
Numeric ranges from prior_context may be used in previous_reference or pre_call_expectation, but not as call evidence unless the transcript itself states them.
Set statement_basis for each guidance item:
  explicit = the transcript directly states the change or number;
  inferred = the change is inferred from multiple transcript statements;
  external_context = the statement mainly comes from prior_context rather than the call and should usually be avoided for current_statement.
```

### 4. Surprise score: usar consenso quando houver e travar transcript-only

O fator "surprise" depende de expectativa prévia. Sem consenso externo, o
score vira uma proxy transcript-only e precisa de cap para não parecer uma
medida real de surpresa de mercado.

```text
Estimate surprise using transcript evidence and, when provided, pre-call consensus or prior analyst context.
If pre-call context is provided, compare what management said in the call against the pre-call expectations, narrative consensus, estimates, and interpretation rules in that context.
Fill consensus_surprise_score only when pre-call context is provided; otherwise use null.
Without external pre-call consensus or prior analyst context, do not assign an overall surprise score above 60.
```

### 5. Q&A agrupado para perguntas críticas

Perguntas críticas não devem ser avaliadas por segmentos soltos. O
modelo recebe `qa_turns.json`, que liga pergunta do analista, resposta do
management, clarificação de RI e follow-up.

```text
Grouped Q&A turns:
Use this grouped structure first for critical question ranking and response-quality assessment.
Ignore blocks with block_type = "acknowledgement" when ranking critical questions.
```

### 6. JSON rules: controlar tamanho, citações e validação posterior

Campos mecânicos pertencem ao pipeline, não ao LLM. Isso evita que o
modelo "declare" uma evidência como validada sem checagem.

```text
Return only one JSON object. Do not wrap it in Markdown.
Keep evidence quotes literal and short, ideally under 25 words.
Leave source_block_ids empty if unknown; the pipeline will fill them mechanically after quote validation.
Do not set evidence_validated or speaker_validated yourself; the pipeline will fill them mechanically.
Keep confidence and evidence_validated conceptually separate.
Do not include an executive report field. The final Markdown report will be rendered by code from the validated JSON.
```

### 7. Self-critique usando relatórios determinísticos

A autocrítica é barata e focada. Ela não substitui a primeira análise;
ela usa os problemas encontrados localmente para reduzir exageros e
inconsistências.

```text
Review the generated earnings-call analysis using only the validated JSON and deterministic quality reports below.
Your goal is to make the JSON more reliable, not more detailed.
Do not redo the full transcript analysis.
Correct only issues that are clear from the evidence and consistency reports.
If an item has invalid evidence and no valid supporting quote in the JSON, prefer removing that item rather than inventing a new quote.
```

## Modelos de LLM Utilizados

A escolha desses modelos foi feita devido ao custos mais elevados de modelos mais otimizados.

- `ANTHROPIC_MODEL=claude-haiku-4-5`: modelo padrão para análise principal e
  self-critique barato.
- `ANTHROPIC_REVIEW_MODEL=claude-sonnet-4-6`: usado apenas quando o
  self-critique detecta maior risco de qualidade.
- A chamada principal é integrada: transcript completo + Q&A agrupado + schema
  + instruções -> JSON completo.
- O self-critique não reenviará o transcript completo. Ele recebe somente
  `analysis.json`, `evidence_report.json` e `consistency_report.json`.

Gatilhos de escalonamento para Sonnet:

- issue `high` no `consistency_report.json`;
- issue `medium` no `consistency_report.json`;
- `valid_quote_rate < 0.90`.

## Schema JSON

Campos principais de `analysis.json`:

- `schema_version`, atualmente `1.2`;
- `company_name`, `ticker`, `quarter`, `call_date`;
- `management_tone`;
- `guidance_changes`;
- `critical_questions`;
- `red_flags`;
- `surprise_items`;
- `consensus_surprises`;
- `surprise_score_components`;
- `transcript_surprise_score`;
- `consensus_surprise_score`;
- `overall_surprise_score`;
- `surprise_score_confidence`;
- `temporal_comparison`;
- `analysis_context`;
- `analysis_limitations`.

Categorias controladas:

- tom: `positive`, `cautiously_positive`, `neutral`, `cautious`, `negative`,
  `mixed`;
- qualidade da resposta: `strong`, `adequate`, `weak`, `evasive`, `unclear`;
- severidade: `low`, `medium`, `high`;
- confidence: `low`, `medium`, `high`.

## Segmentação da transcrição

`transcript_segments.json` separa onde o bloco aparece da função do bloco:

- `section`: `prepared_remarks` ou `qa`;
- `block_type`: `prepared_management`, `prepared_moderator`,
  `analyst_question`, `management_answer`, `ir_moderation`,
  `ir_clarification`, `management_clarification`, `answer_fragment`,
  `acknowledgement` ou `unknown`.

Campos importantes:

- `speaker_type`: `management`, `analyst`, `operator_ir` ou `unknown`;
- `role_title`: cargo preservado quando detectado, como `CFO`, `CRO` ou
  `Head of Investor Relations`;
- `qa_turn_id`: identificador do turno de Q&A;
- `source_block_ids`: ids usados pelo citation tracking para mostrar onde a
  citação apareceu.

## Validação De Evidências e Citation Tracking

`evidence_checker.py` verifica cada quote contra o texto limpo e contra os
segmentos:

- `evidence_validated`: quote encontrada ou não;
- `speaker_validated`: speaker confere com o segmento encontrado;
- `source_block_ids`: blocos de origem;
- `match_type`: `exact`, `normalized_exact`, `approximate` ou `not_found`;
- `matched_text`: trecho encontrado;
- `match_score`: score entre 0 e 1.

No Streamlit, o Citation Tracking transforma essas evidencias em cards visuais com status, speaker, página, score, quote e expansores para o bloco original da transcrição.

## Avaliação De Consistência

`consistency_checker.py` faz checks determinísticos após a validação de
evidências. Ele procura:

- citações inválidas;
- speaker mismatch;
- score de consenso preenchido sem contexto pré-call;
- `overall_surprise_score` desalinhado com `transcript_surprise_score` ou
  `consensus_surprise_score`;
- `analysis_context` contraditório;
- limitações obsoletas;
- números marcados como `explicit` sem suporte nas quotes.

O resultado é salvo em `output/consistency_report.json`.

## Contexto Histórico E Comparação Temporal

`build_history_context.py` cria um contexto histórico compacto a partir de PDFs anteriores. O histórico é usado para:

- identificar temas recorrentes;
- comparar mudança de tom;
- calibrar pressão de analistas;
- separar tema persistente de tema novo ou mais urgente.

O histórico não é usado como evidencia literal da call atual.

## Testes

Os testes cobrem:

- PDF loader;
- limpeza de transcrição;
- segmentação e Q&A;
- schema Pydantic;
- validação de evidências;
- consistency checker;
- report writer e limite de 400 palavras;
- contexto histórico;
- metadados do pipeline;
- citation tracking helpers;
- políticas de surprise score e self-critique.

## Limitações

1. **O surprise score ainda depende da qualidade do consenso pré-call.**

   Sem um arquivo de consenso confiavel, a ferramenta usa sinais internos da
   transcrição e aplica cap, que reduz risco de exagero, mas não transforma o score em uma medida real de surpresa de mercado. Portanto, é importante ter um consenso pré-call confiável para obter uma melhor análise.

2. **A extração depende da qualidade textual do PDF.**

   O projeto foi desenvolvido baseado em um caso exemplo utilizando transcrições da BBSE3, mas para casos de PDFs escaneados, transcrições com OCR ruim, speaker label inconsistentes ou tradução simultânea com artefatos podem prejudicar segmentação, atribuição de speaker e validação literal de quotes. 

3. **A qualidade analítica ainda não é medida contra um benchmark anotado.**

    O projeto possui testes automatizados para schema, segmentação, evidências, consistência e relatório, mas ainda não compara sistematicamente as saídas contra um conjunto de earnings calls revisado por analistas humanos. Portanto, não há métricas formais de precisão para tom do management, ranking de perguntas críticas, red flags ou surprise score.

## Próximos Passos

1. **Criar uma base estruturada de contexto**

   Atualmente, o projeto usa arquivos manuais/compactos de consenso e histórico. O próximo passo seria escalar, criando uma camada persistente completa. Isso permitiria comparar automaticamente uma nova call contra o histórico, sem precisar reconstruir contexto manualmente a cada execução.

2. **Formalizar o módulo de consenso pré-call**

   O surprise score só fica realmente forte se houver expectativa prévia, então é necessário estruturar  o consenso pre-call. Isso tornaria o surprise score muito mais defensável para uso real, porque ele deixaria de ser apenas inferência da transcrição.

3. **Criar evaluation set**

   Para escalar com confiança é necessário um conjunto de transcrições revisadas para medir acurácia da segmentação, validade das citações, qualidade do ranking das perguntas críticas; precisão da classificação de tom, coerência do surprise score, qualidade do relatório final. Isso daria uma régua objetiva para comparar prompts, modelos e mudanças no pipeline sem depender só de inspeção manual.

## Caso Teste Utilizado

O caso teste principal foi construído para simular um uso real da ferramenta com uma empresa publica do Ibovespa. A companhia escolhida foi Banco do Brasil
S.A. (`BBAS3`), usando a transcrição mais recente disponivel no conjunto de arquivos do projeto: `Transcript - Videoconference - 1Q26 (BBAS3).pdf`.

### 1. Consenso Pré-Call

Foi criado um arquivo de consenso pre-call em:

```text
data/BBAS3_1Q26_pre_call_consensus.json
```

Esse arquivo foi estruturado a partir de dados publicos e contém expectativas que seriam conhecidas antes da call, como temas esperados, principais
incertezas, guidance anterior, pontos potencialmente surpreendentes e regras de interpretação para o surprise score.

Durante a execução, o pipeline detecta automaticamente esse arquivo pelo padrao
`data/{TICKER}_{QUARTER}_pre_call_consensus.json`. Para o caso teste, o PDF indica `BBAS3` e `1Q26`, então o arquivo de consenso é carregado como contexto externo.

Esse consenso é usado principalmente para preencher `consensus_surprises`, calcular `consensus_surprise_score`, diferenciar temas já esperados de pontos incrementais e evitar que o surprise score dependa apenas de sinais internos da
transcrição.

### 2. Contexto Histórico Dos Últimos 2 Anos

Também foi criado um contexto histórico compacto com transcrições anteriores armazenadas em `data/`, considerando os anos de 2024 e 2025. A transcrição
atual de 1Q26 foi excluída desse histórico para evitar vazamento de informação.

O arquivo gerado fica em:

```text
context/BBAS3_history_context.json
```

Esse contexto resume trimestres históricos analisados, tom recorrente do management, temas recorrentes de guidance, pressoes recorrentes no Q&A, exemplos agregados de linguagem cautelosa e tópicos persistentes ao longo do histórico.

Durante a execução, o pipeline busca automaticamente esse arquivo pelo padrão
`context/{TICKER}_history_context.json`. No caso teste, ele encontra
`context/BBAS3_history_context.json` e usa esse material para preencher
`temporal_comparison`.

O histórico não é usado como evidência literal da call atual; ele serve apenas para calibrar se um tema e recorrente, novo ou mais intenso.

### 3. Execução Com a Transcrição 1Q26

Com o consenso pré-call e o contexto histórico posicionados nas pastas esperadas, a execução foi feita e os resultados finais ficam em uma subpasta de `output/`.

## Log de Tempo Gasto

O tempo aproximado gasto nesse caso foi:
| Etapa | Tempo Gasto |
| --- | --- |
| Entendimento do Problema e Definição de Escopo | 1 hora |
| Implementação Inicial + Testes | 2,5 horas |
| Avaliação de Consistência | 1 hora |
| Streamlit | 1 hora |
| Comparação Temporal | 1 hora |
| Citation Tracking + Self-Critique Loop | 1 hora |
| Documentação | 30 minutos |

## Aprofundamento no Case

Decidi me aprofundar mais nesse primeiro case pois acreditei que seria possível implementar essas extensões com bons resultados dentro do prazo estipulado. Com isso, escolhi as opções mais viáveis, que foram a Comparação Temporal, Citation Tracking, Self-Critique Loop, Avaliação de Consistência e Interface Streamlit; as outras opções ficaram em segundo plano pois demandariam mais tempo devido à necessidade de extração de mais dados para Reação de Mercado e Comparação Setorial, e aumento de custo para a Comparação Multi-modelo.