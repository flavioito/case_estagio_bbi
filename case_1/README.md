# Earnings Call Analyzer

Ferramenta CLI em Python para transformar uma transcricao de earnings call em PDF
em uma analise estruturada para research financeiro.

O principio central da entrega e: toda conclusao analitica precisa estar ligada
a evidencia literal da transcricao.

## Status

MVP de 3 dias implementado.

Saidas principais:

- `output/analysis.json`: JSON validado com Pydantic.
- `output/evidence_report.json`: relatorio de validacao das citacoes literais.
- `output/run_metadata.json`: metadados da execucao, modelos, parametros e resumo de evidencias.
- `output/executive_report.md`: relatorio executivo deterministico renderizado a partir do JSON validado e das evidencias verificadas.

Saidas intermediarias:

- `output/clean_text.txt`: texto extraido e limpo.
- `output/transcript_segments.json`: blocos de fala com speaker, cargo, `section`, `block_type`, paginas e `qa_turn_id`.
- `output/qa_turns.json`: perguntas e respostas do Q&A agrupadas por turno.

## Escopo Do MVP

Incluido:

1. Extracao de texto de PDF com PyMuPDF.
2. Limpeza conservadora da transcricao, com remocao de cabecalhos repetidos.
3. Segmentacao por speakers, paginas e secoes.
4. Merge conservador de blocos curtos consecutivos do mesmo speaker quando parecem quebra artificial.
5. Identificacao heuristica de management, RI/operator, analistas e cargos.
6. Chamada principal unica ao Claude Haiku para gerar JSON completo.
7. Validacao rigorosa do JSON com Pydantic.
8. Retry de reparo quando o JSON nao atende ao schema.
9. Validacao das citacoes literais com `evidence_checker.py`, incluindo speaker e `source_block_ids`.
10. Relatorio executivo renderizado pelo codigo a partir do JSON verificado.
11. Revisao final opcional com Claude Sonnet.
12. Testes basicos para PDF, segmentacao, schema, evidencias e relatorio.

Fora do escopo:

- Dashboard, web app, banco de dados e login.
- Scraping ou integracao com Bloomberg, Refinitiv, FactSet, Yahoo Finance ou CVM.
- Backtesting, valuation, RAG vetorial, fine-tuning e OCR.
- Validacao automatica contra consenso externo sem arquivo fornecido.

## Instalacao

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Crie um arquivo `.env`:

```text
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-haiku-4-5
ANTHROPIC_REVIEW_MODEL=claude-sonnet-4-6
OUTPUT_DIR=output
TEMPERATURE=0.1
MAX_OUTPUT_TOKENS=12000
DEBUG=false
```

## Uso

Analise completa com Haiku:

```bash
python analyze_call.py "C:\Users\flavi\Downloads\Transcript - Videoconference - 1Q26 (BBAS3).pdf" --output output
```

Somente extracao e segmentacao, sem chamar Claude:

```bash
python analyze_call.py current_call.pdf --output output --extract-only
```

Versao final com revisao Sonnet:

```bash
python analyze_call.py current_call.pdf --output output --review-with-sonnet
```

Com contexto opcional:

```bash
python analyze_call.py current_call.pdf --previous previous_call.pdf --prior-context consensus_notes.md --output output
```

## Arquitetura

```text
PDF
  -> pdf_loader.py
  -> transcript_cleaner.py
  -> segmenter.py
  -> prompts.py + anthropic_client.py
  -> schemas.py
  -> evidence_checker.py
  -> report_writer.py
  -> output/
```

Estrutura do projeto:

```text
case_1/
  analyze_call.py
  requirements.txt
  .env.example
  src/
    config.py
    pdf_loader.py
    transcript_cleaner.py
    segmenter.py
    schemas.py
    anthropic_client.py
    prompts.py
    pipeline.py
    evidence_checker.py
    report_writer.py
  tests/
    test_pdf_loader.py
    test_segmenter.py
    test_schema_validation.py
    test_report_writer.py
```

## Estrategia De Modelos

- `ANTHROPIC_MODEL=claude-haiku-4-5`: usado para desenvolvimento, testes de
  prompt, analise da transcricao, extracao do JSON, tom, perguntas criticas,
  red flags, surprise score e relatorio executivo.
- `ANTHROPIC_REVIEW_MODEL=claude-sonnet-4-6`: usado apenas com
  `--review-with-sonnet`.
- O pipeline evita chamadas modulares caras. A analise principal e uma chamada
  integrada: transcript completo + schema + instrucoes -> JSON completo.
- A revisao Sonnet nao refaz a analise; ela verifica conclusoes sem evidencia,
  citacoes fracas, red flags exageradas, surprise score especulativo e
  inconsistencias entre JSON e relatorio.

## Prompt Engineering

Os prompts instruem o modelo a:

- analisar somente a transcricao e contextos opcionais fornecidos;
- nao usar conhecimento externo;
- nao inventar guidance, consenso, nomes, cargos ou numeros financeiros;
- fundamentar toda conclusao em citacao literal;
- diferenciar fala do management, preocupacao de analista e interpretacao;
- tratar red flags como sinais linguisticos, nao como acusacoes;
- declarar limitacoes quando a evidencia for insuficiente;
- retornar apenas JSON valido seguindo o schema.

## Validacao De Evidencias

Depois da validacao Pydantic, `evidence_checker.py` verifica se cada `quote`
aparece no texto limpo da transcricao.

Cada evidencia recebe:

- `evidence_validated`: `true` ou `false`;
- `speaker_validated`: `true`, `false` ou `null`;
- `source_block_ids`: ids dos blocos em `transcript_segments.json` onde a quote foi encontrada;
- `match_type`: `exact`, `normalized_exact`, `approximate` ou `not_found`;
- `matched_text`: trecho encontrado quando aplicavel;
- `match_score`: score entre 0 e 1.

O pipeline salva `output/evidence_report.json` com:

- total de citacoes verificadas;
- taxa de citacoes validas;
- contagem por tipo de match;
- taxa de validacao por speaker quando segmentos sao fornecidos;
- lista de citacoes invalidas.

Para o MVP, a ferramenta nao bloqueia a geracao do relatorio quando ha
evidencia invalida. Se `valid_quote_rate` ficar abaixo de `0.75`, ela imprime
um warning para revisao manual.

## Relatorio Executivo

`report_writer.py` nao usa o Markdown livre gerado pelo Claude como fonte final.
O relatorio e renderizado de forma deterministica a partir de:

- `management_tone`;
- `guidance_changes`;
- `critical_questions`;
- `red_flags`;
- `surprise_items` e `overall_surprise_score`;
- `surprise_score_components`;
- `analysis_context`;
- `analysis_limitations`;
- `evidence_report.json`.

Itens com evidencia marcada como invalida sao filtrados das secoes materiais
sempre que possivel. O JSON de analise nao contem campo de relatorio livre; o
Markdown final e sempre renderizado por `report_writer.py`.

## Formato Do JSON

Campos principais de `analysis.json`:

- `schema_version`, atualmente `1.2`;
- `company_name`, `ticker`, `quarter`, `call_date`;
- `management_tone`;
- `guidance_changes`;
- `critical_questions`, limitado a 3 itens;
- `red_flags`, limitado a 5 itens;
- `surprise_items`;
- `consensus_surprises`, preenchido quando `--prior-context` e fornecido;
- `surprise_score_components`, com componentes estruturados do score;
- `transcript_surprise_score`, score baseado apenas em sinais internos da call;
- `consensus_surprise_score`, score contra consenso pre-call quando disponivel;
- `overall_surprise_score`, de 0 a 100;
- `surprise_score_confidence`;
- `analysis_context`, com flags sobre contexto externo e cap do score;
- `analysis_limitations`;

Categorias controladas incluem:

- tom: `positive`, `cautiously_positive`, `neutral`, `cautious`, `negative`, `mixed`;
- qualidade da resposta: `strong`, `adequate`, `weak`, `evasive`, `unclear`;
- severidade: `low`, `medium`, `high`;
- confidence: `low`, `medium`, `high`.

## Taxonomia De Segmentos

O arquivo `transcript_segments.json` separa `section` de `block_type`.

Valores de `section`:

- `prepared_remarks`: comentarios preparados antes do Q&A.
- `qa`: sessao de perguntas e respostas.

Valores oficiais de `block_type`:

- `prepared_management`: comentario preparado de executivo.
- `prepared_moderator`: abertura ou comentario preparado de RI/moderador.
- `analyst_question`: pergunta substantiva de analista.
- `management_answer`: resposta substantiva do management.
- `ir_moderation`: transicao operacional, chamada do proximo analista ou controle da dinamica da call.
- `ir_clarification`: esclarecimento material ou tecnico feito por RI/operator no Q&A.
- `management_clarification`: pergunta, checagem ou esclarecimento curto feito pelo management.
- `answer_fragment`: fragmento minimo de resposta, como "Exactly.".
- `acknowledgement`: agradecimento ou fechamento curto sem pergunta material.
- `unknown`: bloco sem classificacao confiavel.

Para compatibilidade, cada segmento tambem inclui `legacy_section`, como
`qa_question`, `qa_answer` ou `qa_ir_clarification`.

Roles usados:

- `management`: executivos e membros da administracao.
- `analyst`: analistas externos no Q&A.
- `operator_ir`: RI, operador ou moderador da chamada.
- `unknown`: speaker sem classificacao confiavel.

Campos adicionais por segmento:

- `speaker_type`: tipo claro do speaker, equivalente ao campo legado `role`.
- `role_title`: cargo preservado quando detectado, como `CFO`, `CRO` ou `Head of Investor Relations`.
- `qa_turn_id`: identificador do turno de Q&A, como `qa_0003`.
- `block_id`: identificador sequencial do bloco, como `seg_0011`.
- `word_count`: numero de palavras do segmento.
- `has_question`: indica se o segmento contem ponto de interrogacao.

O arquivo `qa_turns.json` agrupa:

- perguntas do analista;
- respostas do management;
- clarificacoes de RI;
- outros blocos relevantes do mesmo turno.

Agradecimentos classificados como `acknowledgement` nao entram como perguntas
criticas no agrupamento.

## Tratamento De Erros

- Arquivo inexistente: mensagem clara para verificar o caminho.
- PDF sem texto: informa que OCR nao faz parte do MVP.
- Chave Anthropic ausente: pede configuracao de `ANTHROPIC_API_KEY`.
- Falha de API: mensagem sobre chave, conexao e limites de uso.
- JSON invalido: o pipeline faz retry de reparo sem adicionar nova analise.
- Evidencias nao encontradas: ficam marcadas no JSON e em `evidence_report.json`.
- `run_metadata.json`: registra modelo, parametros, contexto fornecido, contagens e resumo de evidencias.
- Relatorio acima de 400 palavras: rejeitado pelo schema.

## Testes

```bash
python -m pytest
```

Cobertura atual:

- PDF valido, inexistente e extensao invalida.
- Segmentacao basica e classificacao de Q&A.
- Validacao do schema Pydantic e categorias obrigatorias.
- Validacao de citacoes literais, aproximadas e nao encontradas.
- Rastreamento de evidencias por `source_block_ids` e speaker.
- Politica de cap do surprise score quando nao ha consenso externo.
- Limite de 400 palavras do relatorio.
- Escrita de `executive_report.md`.

## Limitacoes

1. A ferramenta nao valida informacoes contra fontes externas.
2. O `transcript_surprise_score` e transcript-only quando nao ha consenso pre-call fornecido.
3. O `consensus_surprise_score` depende de arquivo `--prior-context`.
4. Comparacao com trimestre anterior depende de arquivo `--previous`.
5. PDFs escaneados podem nao funcionar sem OCR.
6. Speaker attribution depende do formato da transcricao.
7. Red flags sao indicadores linguisticos, nao prova de irregularidade.
8. O modelo pode errar nuance financeira; por isso as evidencias sao obrigatorias.
9. O relatorio nao substitui analise completa de equity research.
10. A ferramenta nao calcula valuation.
11. A ferramenta nao preve reacao de mercado.

## Proximos Passos

- OCR para PDFs escaneados.
- Interface web simples com upload.
- Comparacao automatica com calls historicas.
- Integracao opcional com consenso de mercado.
- Extracao numerica de guidance em series temporais.
- Dashboard de red flags e mudanca de tom por empresa.
- Exportacao para PDF ou PowerPoint.
