# Custos e Investimentos em Climatização

## Análise técnica e integração

A aplicação existente usa FastAPI, autenticação JWT, SQLAlchemy/PostgreSQL, Jinja e gráficos em canvas. As salas têm UUID persistente, e as medições ambientais já são consultadas por sala. O módulo reutiliza essa estrutura; não introduz outra stack, biblioteca de gráficos, integração de preços ou dependência de produção.

A implementação adiciona `cost_scenarios`, vinculada a `rooms.id`, e mantém as tabelas e endpoints ambientais existentes. A tabela é criada na inicialização pelo mecanismo de persistência já utilizado. Não há cenários de exemplo na base principal, nem preenchimento automático de preços, tarifas, potência ou horas. Cenários pertencentes a salas arquivadas permanecem armazenados, mas deixam de ser acessíveis pelo cadastro ativo.

Na navegação, **Custos e Investimentos** aparece antes de **Gerenciar salas**, que continua sendo a última aba. O seletor do cabeçalho escolhe a sala, mantendo o usuário dentro do módulo. Cada dashboard individual tem um botão para abrir seus cenários. O módulo oferece o caminho de volta e indicadores ambientais com seleção de 24 horas, 7 dias ou 30 dias, usados apenas como contexto.

## Parâmetros persistidos

- Sala, nome do cenário e modelo do equipamento.
- Capacidade de refrigeração em **BTU/h** — informação descritiva, fora da fórmula de energia.
- Potência elétrica média estimada em **kW**, obrigatória no método por potência.
- Preço do equipamento, instalação, horas de uso por dia, dias por mês e tarifa em R$/kWh.
- Manutenção opcional: `maintenance_cost` (valor por ocorrência) e `maintenance_interval_months` (intervalo inteiro de 1 a 120 meses). Os dois campos devem ser informados juntos ou permanecer ausentes.
- Método de estimativa: potência ou etiqueta.
- Para etiqueta: consumo em kWh, período mensal/anual e horas de referência desse mesmo período, com identificação obrigatória da fonte/condições.
- Fonte dos parâmetros, observações, UUID do cenário e datas de criação/alteração.

Valores monetários usam colunas `Numeric`, validação `Decimal` e arredondamento explícito. Os resultados decimais são transmitidos como texto para preservar os valores do backend; a interface os formata em português e reais. Valores zero de preço, tarifa ou uso só são considerados quando informados pelo usuário. Potência e referências da etiqueta devem ser positivas. Horas são limitadas a 24/dia e dias a 31/mês. Não há conversão automática de BTU/h para kW.

## Metodologia 1.1

A evolução integra manutenção, comparação com tarifa comum, indicadores ambientais, análise determinística e relatório imprimível à tela. A ordem é configuração, resumo financeiro, projeções, comparação, distribuição por sala, indicadores ambientais, análise e exportação. Não há alteração automática dos parâmetros financeiros salvos.

Ao abrir uma sala, o resumo financeiro carrega automaticamente o cenário salvo com a referência mensal mais recente (quando informada no nome); nos demais casos usa a data de atualização/cadastro. O seletor **Cenário do resumo** permite consultar outra alternativa sem modificar o formulário ou gravar no banco. Os quatro indicadores principais são **Investimento inicial**, **Custo mensal de energia**, **Custo anual de energia** e **Total em 36 meses**. Ao iniciar um cenário novo, os cards permanecem visíveis, aguardando parâmetros válidos; a atualização periódica não substitui o formulário em preenchimento por um cenário salvo.

A validação desta correção no Chrome conferiu os quatro valores contra a API nas duas salas, cada uma com 17 cenários, incluindo seleção de outra alternativa, formulário novo e layout móvel. Evidência: [resumo financeiro](evidence/financial-summary-ui.json).

### Potência média informada

```text
Horas mensais = horas/dia × dias/mês
Consumo mensal estimado (kWh) = potência elétrica média estimada (kW) × horas mensais
Custo mensal de energia (R$) = consumo mensal estimado × tarifa (R$/kWh)
Custo anual de energia (R$) = custo mensal não arredondado × 12
Investimento inicial (R$) = preço do equipamento + instalação
Manutenção acumulada em N meses = valor por ocorrência × parte inteira de (N ÷ intervalo)
Custo total em N meses (R$) = investimento inicial + custo mensal não arredondado × N + manutenção acumulada informada
```

A potência deve representar a média elétrica estimada durante o uso. Uma potência nominal ou máxima transcrita sem ajuste pode não representar a média efetiva de um equipamento com compressor variável. O sistema não deduz esse ajuste a partir da temperatura ou de outros dados ambientais.

### Etiqueta de eficiência energética

```text
Consumo mensal estimado (kWh) =
    (consumo declarado em kWh ÷ horas de referência do mesmo período)
    × horas/dia × dias/mês
```

Esse método é um **rateio linear aproximado**, não uma reprodução do ensaio de eficiência ou uma medição do consumo real. É obrigatório informar as horas do período de referência e sua fonte. O sistema não presume uma quantidade padronizada de horas, não mistura referências mensais e anuais e não usa uma potência opcional cadastrada para alterar esse método. Se a referência não estiver disponível, deve ser usado o método por potência média informada.

A [documentação oficial da nova etiqueta do Inmetro](https://www.gov.br/inmetro/pt-br/assuntos/regulamentacao/avaliacao-da-conformidade/programa-brasileiro-de-etiquetagem/tabelas-de-eficiencia-energetica/condicionadores-de-ar/nova-etiqueta) descreve o consumo anual e a consideração de condições ao longo do ano. Por isso, uma proporcionalidade por horas é apresentada como aproximação com limitações, sem prometer consumo idêntico no ambiente monitorado.

### Projeções e comparação

O mês zero contém somente o investimento inicial. Os meses 1 a 36 acumulam energia, mantendo uso e tarifa constantes. A primeira manutenção ocorre ao fim do intervalo informado, e as seguintes nos seus múltiplos; não há rateio mensal nem reajuste. A manutenção é prevista por calendário, inclusive em cenários com uso zero. Valores ausentes são apresentados como não informados e não entram no total; isso não significa custo real zero. Um valor zero explicitamente informado é distinguido da ausência de dados.

O seletor de 12/24/36 meses modifica o horizonte dos gráficos e do relatório. Os valores não são arredondados antes da soma; consumo é apresentado com até quatro casas e moeda com duas. Assim, um total anual pode diferir de doze vezes o custo mensal já arredondado na tela. `monthly_cost` e `annual_cost` continuam representando somente energia, para preservar a compatibilidade. `annual_operating_cost`, a composição das projeções e as séries mensais incluem a manutenção informada.

Dois cenários salvos podem ser comparados. A interface apresenta gráficos mensais e acumulados, tabela acessível e diferença **B − A**. Diferença positiva indica maior custo em B; negativa, menor custo em B. Isso não é recomendação de equipamento, comprovação de economia ou cálculo de retorno do investimento.

A API usa `tariff_mode="shared"` por padrão, aplicando a tarifa salva do primeiro cenário aos dois somente durante a comparação. É possível escolher `common_tariff_per_kwh`, inclusive zero, ou solicitar explicitamente `tariff_mode="scenario"` para manter as tarifas individuais. O horizonte é comum aos dois cenários, mas as horas de utilização e demais parâmetros de cada alternativa são preservados. A resposta inclui tarifas originais, parâmetros efetivos, base de comparação e identificação do menor total (ou empate). Nenhuma dessas operações grava os parâmetros ajustados. O CSV usa a mesma base, documenta a tarifa original e a aplicada e inclui os totais de 12, 24 e 36 meses.

## Limitações exibidas na tela e no relatório

- Resultados estimados, sem medição elétrica, garantia de economia ou cotação de mercado verificada.
- Histórico ambiental não determina consumo elétrico; não há cálculo de consumo real a partir de temperatura.
- Capacidade em BTU/h não é potência elétrica em kW, nem um dimensionamento automático do equipamento.
- Uso e tarifa constantes; não considera sazonalidade, calendário mês a mês, reajustes ou inflação.
- Inclui manutenção apenas quando valor e intervalo são informados. Não inclui financiamento, depreciação, parcelas fixas da conta ou encargos não incorporados à tarifa informada.
- Carga térmica, isolamento, ocupação, ajuste de temperatura, manutenção e funcionamento do compressor podem alterar o consumo.
- Referências da etiqueta e potência média são informadas pelo usuário, com as limitações próprias de cada método.

## Fluxo de uso

1. Abra **Custos e Investimentos** e selecione a sala no cabeçalho, ou use o botão no dashboard individual.
2. Consulte o contexto ambiental e abra os dados climáticos completos, se necessário.
3. Clique em **Novo cenário**, informe seus parâmetros e escolha o método.
4. Os resultados atualizam automaticamente quando os campos obrigatórios estiverem válidos. **Calcular estimativa** permite atualização imediata; **Salvar cenário** persiste os parâmetros. A prévia nunca salva silenciosamente.
5. Cadastre outra alternativa e marque dois cenários na tabela para compará-los.
6. Escolha 12, 24 ou 36 meses e explore os gráficos pelo cursor ou pelas setas.
7. Exporte um cenário salvo ou os selecionados. O CSV contém parâmetros, unidades, fórmulas, resultados, projeções mensais, indicadores ambientais, análise, limitações, versão da metodologia e referência; com dois cenários, inclui as diferenças. O relatório imprimível acrescenta gráficos vetoriais e pode ser salvo em PDF pelo navegador.
8. Edite ou exclua cenários pela tabela. Excluir exige confirmação e não altera a sala nem suas medições.

Alterar parâmetros invalida a apresentação anterior e agenda uma prévia após 450 ms sem alterações. O recálculo não bloqueia a digitação; respostas antigas não substituem parâmetros mais recentes ou dados de outra sala. No salvamento/cálculo explícito, os campos ficam desabilitados durante a requisição. Comparações antigas não substituem respostas referentes a outro horizonte ou outra seleção. Os campos de fonte e observações são protegidos contra fórmulas de planilha no CSV e escapados no relatório HTML.

### Indicadores ambientais e análise

As médias usam leituras válidas de temperatura (-40 a 85 °C) e umidade (0 a 100%), excluindo referências externas. Alertas e críticos são contados separadamente segundo a classificação histórica registrada: são quantidades de leituras, não episódios distintos.

O tempo estimado fora dos limites usa os limites atuais de temperatura e umidade. O estado de uma leitura vale até a próxima somente quando o intervalo não ultrapassa 30 minutos. Leituras inválidas e referências externas interrompem a continuidade. Lacunas, início e fim sem amostras ficam sem cobertura. Uma única leitura não permite calcular duração. A interface e os relatórios mostram cobertura e metodologia; ausência de cobertura não é tratada como tempo normal.

A análise textual é gerada por regras determinísticas a partir dos indicadores e resultados calculados, sem API de inteligência artificial. Não recomenda capacidade de equipamento nem deduz consumo elétrico a partir do histórico ambiental.

### Distribuição por sala

O usuário escolhe no máximo um cenário salvo por sala. Alternativas concorrentes não são somadas. O gráfico mostra o total no horizonte selecionado com os parâmetros salvos, incluindo a tarifa própria de cada cenário. Salas sem seleção não recebem custo presumido. A seleção desta visualização permanece apenas na sessão da página.

## Endpoints autenticados

| Método | Endereço | Uso |
|---|---|---|
| GET | `/api/costs/scenarios?room_id=...` | Lista os cenários da sala |
| POST | `/api/costs/estimate` | Calcula sem salvar |
| POST | `/api/costs/scenarios` | Salva e calcula |
| GET / PUT | `/api/costs/scenarios/{id}` | Consulta / edita |
| DELETE | `/api/costs/scenarios/{id}?confirm=true` | Exclui com confirmação |
| POST | `/api/costs/compare` | Compara dois IDs e horizonte 12/24/36 |
| GET | `/api/costs/report?scenario_id=...&months=36` | Exporta CSV; aceita dois `scenario_id` |
| GET | `/api/costs/report/print?scenario_id=...&months=36&days=7` | Relatório HTML imprimível, com gráficos SVG; aceita dois cenários |
| GET | `/api/costs/context?room_id=...&days=7` | Indicadores ambientais, cobertura e metodologia |
| GET | `/api/costs/portfolio` | Salas ativas e seus cenários para distribuição de custos |

O UUID da sala de um cenário salvo é permanente. Nomes e dispositivos das salas podem mudar sem perder o vínculo. Não há sugestão automática de preços ou capacidades.

A migração `cost_maintenance_v1` adiciona duas colunas anuláveis, sem preencher valores nos cenários existentes. É idempotente e executada mesmo em bancos com a migração inicial das salas já concluída. Clientes anteriores que omitem os dois campos de manutenção ao editar preservam o cronograma salvo; enviar os dois explicitamente como `null` remove a manutenção prevista.

### Validação da evolução — etapa 1

Resultado: **47 testes passaram**, incluindo 12 do módulo financeiro. A execução apresentou apenas os dois avisos de depreciação já existentes nas dependências de testes/templates.

Os testes automatizados cobrem calendário de manutenção, mês zero, intervalos maiores que a projeção, custo explicitamente zero, dados ausentes, precisão decimal, validação dos pares de campos, persistência e edição por clientes anteriores. Também verificam tarifa comum ou individual, preservação dos cenários originais, empate, CSV e migração repetida sobre uma tabela legada com cenário existente. Todos os testes usam uma base isolada, sem registrar custos fictícios no banco principal.

### Validação da evolução completa

**49 testes passaram**, sendo 14 do módulo financeiro. Os novos casos verificam lacunas, leituras inválidas, separação entre alertas e críticos, ausência de duração calculável, relatório com gráficos e análise, escape de texto fornecido pelo usuário e salas arquivadas.

O Chrome validou também prévia automática sem gravação, manutenção, comparação com tarifas comuns/individuais, identificação do menor custo, distribuição de um cenário por sala, exportação do relatório em PDF e layout de 390 px. Nenhum erro JavaScript foi registrado. Valores financeiros dessas verificações existem somente na base SQLite isolada.

A atualização local foi aplicada com backup em `backups/iot_before_costs_evolution_20261028.dump`. As assinaturas antes/depois confirmaram preservação das **230.186 leituras, duas salas e zero cenários financeiros** existentes naquele momento. Não foram inseridos custos de teste no PostgreSQL principal. Evidências: [verificação local](evidence/costs-evolution-deployment.json), [validação no navegador](evidence/costs-ui-report.json), [resumo financeiro](evidence/costs-evolution-summary.png), [layout móvel](evidence/costs-evolution-mobile.png).

Arquivos adicionais desta evolução: `app/services/cost_analysis_service.py`, `app/templates/cost_report.html`, `app/static/cost-report.css`, `app/static/cost-report.js` e `scripts/verify_costs_evolution.py`. O backend não adiciona dependências externas para gráficos ou PDF.

## Arquivos

Novos: `app/models/cost_scenario.py`, `app/schemas/cost_schema.py`, `app/services/cost_service.py`, `app/routes/cost_routes.py`, `app/static/costs.js`, `app/static/costs.css`, `tests/test_costs.py`, `scripts/validate_costs_ui.py`.

Integração: `app/main.py`, `app/services/storage_service.py`, `app/templates/dashboard.html`, `app/static/dashboard.js`, `app/static/rooms.js`, `app/static/icons.svg`, `README.md`. Os históricos existentes não foram substituídos.

## Validação e evidências

**42 testes passaram** com Python 3.12 e as dependências fixadas do projeto. Incluem os 35 testes anteriores e novos casos de fórmula por kW, independência de BTU/h/temperatura, etiqueta e referência obrigatória, arredondamento decimal, uso zero, CRUD isolado, comparação, exportação, entradas inválidas e salas arquivadas.

O Chrome headless validou nas Salas 1 e 2: parâmetros iniciais vazios, prévia sem gravação, dois métodos, persistência, gráficos 12/24/36, navegação pelo teclado, relatório CSV, edição, cancelamento/confirmação da exclusão, troca de sala, atalhos do dashboard individual, recarga e layout móvel de 390 px. Não houve erros JavaScript. Os valores apresentados nas capturas são **exclusivos de teste, em base SQLite isolada**; não foram cadastrados como custos reais no PostgreSQL principal.

- [Relatório do navegador](evidence/costs-ui-report.json)
- [Tela desktop](evidence/costs-desktop.png)
- [Comparação gráfica](evidence/costs-comparison.png)
- [Tela móvel](evidence/costs-mobile.png)
- [Verificação da aplicação local](evidence/costs-postgres-report.json)

Backup anterior à aplicação do módulo: `backups/iot_before_costs_20261028.dump`. A conferência local compara as impressões digitais das leituras e salas, além da contagem de cenários, para verificar preservação dos dados.

Na aplicação local, as impressões digitais confirmaram a preservação das **230.090 leituras e das duas salas**. A tabela de cenários foi criada vazia: nenhum valor de teste foi gravado como custo real. Os endpoints dos históricos e os arquivos da nova interface também foram verificados no PostgreSQL/serviço local.

Limites da validação: navegador Chrome em desktop e 390 px; não foi feita auditoria em todos os leitores de tela. Os testes usam valores controlados para verificar as fórmulas, sem validar preços de mercado ou desempenho de equipamentos reais.
