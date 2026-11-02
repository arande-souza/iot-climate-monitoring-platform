# Projeto Integrador VI — Evolução da plataforma existente

O módulo adicional **Custos e Investimentos** possui [documentação própria de arquitetura, fórmulas, uso, limitações e testes](CUSTOS_E_INVESTIMENTOS.md). A suíte completa após sua inclusão totaliza 42 testes aprovados; os resultados históricos desta página descrevem as etapas anteriores.

## Diagnóstico e ordem de implementação

A aplicação já utilizava FastAPI, SQLAlchemy/PostgreSQL, autenticação JWT, Jinja, JavaScript e canvas, MQTT/paho e Mosquitto, com Docker Compose. As leituras eram persistidas em `sensor_readings`; as salas eram representadas pelo `device_id`, com duas opções fixas no JavaScript. O status era calculado no backend com limites globais. O botão de atualização gerava simulações, enquanto MQTT e a API também permitiam receber medições. Não havia integração de consulta meteorológica externa.

Foram reutilizados o login, o banco, a ingestão MQTT/API, a classificação, o simulador, os gráficos existentes, as consultas históricas paginadas e a exportação CSV. A implementação seguiu a ordem apresentada antes das alterações: persistência e migração; cadastro e limites; proveniência; dashboards; interface responsiva; testes e aplicação local.

## Persistência e compatibilidade

- `rooms`: UUID permanente, nome, descrição, localização de referência, identificação/número do ambiente, cidade, UF, localização interna, dispositivo exclusivo, limites de temperatura/umidade, origem configurada, configuração complementar e exclusão lógica.
- `sensor_readings`: mantém todas as colunas anteriores e recebe `room_id` e `data_source`.
- `schema_migrations`: registra a migração `rooms_v1`. A inicialização adiciona as colunas ausentes e relaciona os registros antigos às salas, sem recriar ou limpar a tabela de leituras.
- Sala 1 e Sala 2 são cadastradas na primeira migração com seus identificadores e locais existentes. Os limites iniciais preservam as regras anteriores: 20–26 °C e 30–65% como faixas aceitáveis. Outros dispositivos antigos também são migrados.
- Dispositivos MQTT/API ainda desconhecidos originam um cadastro persistente para manter a compatibilidade da ingestão. Não há opções fixas de sala no HTML/JavaScript.
- O índice `(room_id, created_at)` atende às consultas dos novos dashboards.
- O UUID é permanente. Nome, localização, limites, origem e dispositivo associado são editáveis. Ao trocar de dispositivo, as leituras anteriores mantêm o `room_id`, o dispositivo e a localização originais. Um dispositivo com histórico não pode ser reutilizado por outra sala. Mensagens de um dispositivo substituído são recusadas, em vez de criar outra sala automaticamente.
- Excluir exige confirmação e arquiva a sala: ela deixa os dashboards e o cadastro ativo, mas suas leituras permanecem para auditoria. A ingestão para uma sala arquivada retorna conflito; ela não reaparece após reiniciar.
- Os endpoints antigos por dispositivo continuam funcionando. O histórico e as exportações existentes permanecem disponíveis.

## Origem e regras de dados

Cada leitura registra sua própria origem: `sensor`, `simulation`, `external_api` ou `unknown`. A configuração da sala não substitui a proveniência de medições anteriores.

- MQTT assume `sensor` quando o payload não informa `data_source`; publicadores simulados devem informar `simulation`.
- A API de leituras assume `unknown` quando o emissor não identifica a origem.
- O simulador e os scripts de seed/reset identificam suas leituras como `simulation`, mesmo em salas configuradas para sensores.
- O CSV de importação aceita `data_source`; a ausência do campo significa `unknown`.
- Meteorologia externa é exibida como referência externa, sem ser chamada de medição interna. A URL configurada é uma referência; **não foi adicionado um cliente de consulta automática de APIs externas**.
- Registros antigos são migrados como `unknown`, pois o transporte ou a configuração atual não comprovam sua origem.
- Na base local, os IDs 64791–294736 correspondem às 229.946 leituras geradas pelo reset solicitado nesta conversa. Somente esse lote confirmado foi identificado como simulação. Uma leitura adicional antiga permaneceu com origem desconhecida.

Os limites específicos são aplicados à classificação de novas leituras e ao status atual. As regras de CO₂ e material particulado foram preservadas. `ideal` e `aceitavel` são agrupados como **Normal**; `alerta`, como **Atenção**; e `critico`, como **Crítica**. Alterar limites não reescreve os alertas históricos: eles representam a classificação no momento do registro.

Leituras futuras ou com temperatura/umidade fora dos domínios físicos aceitos pelo projeto são excluídas dos indicadores. Uma última leitura com mais de 30 minutos recebe o estado **Desatualizada** e não entra nas médias atuais. As médias da visão geral usam a última leitura válida e recente de cada sala, dando o mesmo peso a cada ambiente; referências meteorológicas externas ficam fora dessas médias. O texto informa quantas salas de cada origem participam das médias, inclusive simulações e origens desconhecidas. Os comparativos sinalizam que referências meteorológicas podem compartilhar uma origem e não são medições internas independentes.

## Interface e dashboards

### Atualização manual de todas as salas

Na Visão Geral, a seção **Coleta de dados** apresenta o subtítulo **Área de atualização manual** e o botão **Atualizar dados**. A ação chama `POST /simulator/update-all-until-now`, sem depender da sala selecionada ou dos filtros dos gráficos. Todas as salas ativas participam; as excluídas são ignoradas. Cada sala continua a partir de sua última leitura. Salas vazias recebem as últimas 24 horas; salas atualizadas há menos de 60 segundos não recebem duplicatas.

O endpoint aceita `frequency_seconds` (padrão 60) e `profile` (padrão `mixed`), retorna a contagem de salas atualizadas e leituras geradas e limita a operação a 100.000 registros. Valida todos os períodos antes de inserir e confirma a atualização em uma única transação. Uma falha reverte os registros de todas as salas; chamadas concorrentes são serializadas pelo bloqueio das salas no PostgreSQL. O botão fica desabilitado enquanto a requisição está em andamento.

As referências visuais a “dados simulados” foram removidas. Quando a configuração ou uma tabela precisa identificar o método, usa o rótulo **Atualização manual**; os cards não exibem a etiqueta desse método. Essa mudança é de apresentação: o mecanismo de geração permanece o existente, a origem `simulation` continua registrada nas medições e os dados anteriores não são excluídos nem reclassificados como sensores reais. O endpoint individual existente permanece disponível para integrações.

### Visão geral

Contagem de salas, salas normais/em atenção/críticas, médias atuais de temperatura e umidade, contagem de salas sem dados e desatualizadas. Cards mostram nome, descrição, origem, medições, horário, status e acesso aos detalhes/configurações. Salas vazias não recebem valores simulados automaticamente.

O card de dispositivos ativos mostra **conectividade não informada**, porque o projeto não possui heartbeat ou telemetria de conexão. Uma leitura recente não é utilizada como prova de que um dispositivo está conectado.

Há três gráficos consolidados: evolução da temperatura média, evolução da umidade média e ocorrências de alerta/críticas. Filtros de 24h/7d/30d, período personalizado e sala se aplicam somente aos gráficos. Para cada intervalo, calcula-se primeiro a média de cada sala e depois a média entre as salas com dados; o ritmo de publicação de um dispositivo não aumenta o peso de seu ambiente. As contagens de alerta e crítico são separadas e somam ocorrências existentes. Intervalos sem medições não recebem pontos artificiais. Os gráficos têm exploração pelo mouse/teclado e tabela acessível.

### Ambiente individual

Endereço exclusivo `/rooms/{uuid}`; pode ser recarregado e acessado diretamente após autenticação. Mostra descrição, localização, limites, temperatura, umidade, pressão, CO₂, PM2.5 e PM10, status, origem, última atualização, gráficos separados, extremos/médias, quantidade de leituras, alertas recentes e acesso ao histórico completo. Pressão e PM10 ausentes são exibidos como indisponíveis.

Filtros de 24 horas, 7 dias e 30 dias. Os gráficos agregam todas as medições do período em aproximadamente 360 intervalos; não truncam as primeiras/últimas 200 leituras e não criam pontos nos intervalos vazios. Mínimos, máximos e médias são calculados sobre as leituras originais. Cada ponto mostra a quantidade de amostras agregadas. Não é necessário ter o período inteiro preenchido para consultar o histórico parcial disponível.

Os gráficos permitem explorar valores pelo cursor e pelas setas do teclado, com saída textual e tabela acessível dos pontos. As telas anteriores de histórico de leituras, alertas, horário crítico, paginação e CSV continuam acessíveis. Os relatórios baixados pela interface incluem a coluna de origem, usando `include_source=true`; chamadas antigas de exportação preservam o formato original por padrão.

Os históricos também aceitam `room_id`, mantendo o filtro opcional `device_id` e todos os filtros anteriores. A interface consulta o histórico completo da sala, inclusive dispositivos substituídos, e permite filtrar um dispositivo específico. A atualização periódica não apaga esse filtro. O limite final inicial do histórico é arredondado para incluir as leituras no último minuto parcial, respeitando a precisão dos campos de data da interface.

Os intervalos retornados pela API incluem fuso horário, e os filtros com deslocamento são normalizados em UTC antes da consulta. Isso mantém as datas em Brasília consistentes nos testes SQLite e no PostgreSQL, sem alterar os instantes armazenados.

### Comparação

Inclui automaticamente todas as salas ativas. Médias de temperatura e umidade, extremos de temperatura, quantidade de alertas e leituras, origem dos conjuntos e gráficos de barras. Filtros de 24 horas, 7 dias e 30 dias. Salas sem dados aparecem explicitamente vazias; uma média ausente não é representada como zero. A contagem de alertas representa ocorrências, não duração.

### Cadastro

Formulário para criar/editar salas, validar limites e configurar a origem. Confirmação antes da exclusão. Estados de carregamento/erro/ausência de dados, modal nativo, rótulos, foco visível e navegação pelo teclado. Layout responsivo mantém a identidade em azul e verde. Nenhuma dependência de gráficos foi adicionada à aplicação.

Cidade/UF identificam a localização geográfica da empresa; identificação/número e localização interna identificam o ambiente físico. `rooms.location` continua disponível como referência textual, e `sensor_readings.location` continua sendo o texto recebido com cada medição. A migração `room_locations_v2` acrescenta os campos estruturados vazios, sem tentar deduzir geografia a partir do texto antigo e sem modificar as leituras. Não há mapas nem geolocalização automática. Edições por clientes antigos que não enviam os novos campos preservam os valores já cadastrados.

Ícones vetoriais de traço consistente são servidos localmente por `app/static/icons.svg`, sem biblioteca ou consulta externa. Rótulos textuais permanecem visíveis; os SVGs são ocultos de tecnologias assistivas para evitar leitura duplicada. Os destaques, o menu azul-marinho, os cards brancos e as cores dos status foram preservados. Transições discretas respeitam a preferência de movimento reduzido.

## Endpoints adicionados

| Método | Endereço | Finalidade |
|---|---|---|
| GET/POST | `/api/rooms` | Listar/cadastrar |
| GET/PUT | `/api/rooms/{id}` | Consultar/editar |
| DELETE | `/api/rooms/{id}?confirm=true` | Arquivar com confirmação |
| GET | `/api/rooms/overview` | Indicadores e cards |
| GET | `/api/rooms/overview/history?days=7&room_id=...` | Séries consolidadas e contagens por intervalo; sala opcional |
| GET | `/api/rooms/comparison?days=7` | Estatísticas comparativas |
| GET | `/api/rooms/{id}/dashboard?days=30` | Detalhes e séries históricas |
| GET | `/rooms/{id}` | Página individual autenticada |

Os endpoints analíticos também aceitam `start` e `end` em ISO 8601; recomenda-se incluir o fuso (`-03:00` para Brasília). O término é limitado ao momento atual. Todos os endpoints de salas exigem a autenticação existente.

## Testes e evidências

Suíte executada com as versões fixadas em `requirements.txt`, em Python 3.12:

```powershell
.\.venv\tests\Scripts\python.exe -m pytest -q
```

**35 testes passaram.** Cobertura inclui regressões anteriores, duas salas originais, criação de dez salas, CRUD, validação de limites, unicidade, isolamento, proveniência, exportação, links individuais, migrações idempotentes a partir das tabelas antigas, persistência das exclusões, ausência de dados, leituras antigas e recuperação do reset em caso de erro. A cobertura adicional verifica localização histórica após renomear salas, troca de dispositivo com manutenção de filtros/exportações, médias com pesos iguais, separação entre alertas e críticos, exclusão de referências externas, ausência de conectividade inferida e atualização de todas as salas com reversão integral em caso de falha. Há avisos de descontinuação nas integrações Starlette/AnyIO e na assinatura antiga de templates; não impediram os testes.

Validação adicional em Chrome headless, com banco SQLite isolado e servidor em `127.0.0.1:8001`: criação das Salas 3 a 10 pela interface, edição, confirmação/cancelamento da exclusão, atualização automática, gráficos/filtros, comparação e viewport móvel de 390 px. Nenhum erro JavaScript registrado. O Playwright foi instalado apenas no ambiente de desenvolvimento; não é uma dependência da aplicação. O script `scripts/validate_rooms_ui.py` exige uma base de testes nova com as duas salas iniciais e credenciais de teste `ui-check` / `ui-validation-only`, e não deve ser apontado para a base de uso diário.

Evidências:

- [Relatório da interface](evidence/rooms-ui-report.json)
- [Visão geral desktop](evidence/rooms-desktop.png)
- [Visão geral móvel](evidence/rooms-mobile.png)
- [Dashboard individual](evidence/room-detail.png)
- [Comparação](evidence/rooms-comparison.png)
- [Gráficos consolidados da visão geral](evidence/overview-consolidated.png)
- [Atualização manual de todas as salas](evidence/manual-update-all-rooms.png)
- [Verificação no PostgreSQL local](evidence/rooms-postgres-report.json)
- [Preservação dos históricos e validação da localização no PostgreSQL](evidence/locations-postgres-report.json)
- [Formulário de localização e dispositivo](evidence/room-location-form.png)
- [Verificação final de localização, troca de dispositivo e filtro histórico](evidence/locations-ui-final.json)

Na migração local foram preservadas **229.947 leituras**, todas vinculadas às salas, incluindo uma leitura adicional recebida depois do reset. Foi salvo um backup completo em `backups/iot_before_rooms_20261028.dump`. Os endpoints geral, individual e comparativo também foram exercitados no PostgreSQL real, sem inserir salas fictícias nessa base.

Antes da migração de localização foi salvo outro backup completo: `backups/iot_before_locations_20261028.dump`. A comparação da contagem e da impressão digital de todos os campos das 229.947 leituras confirmou que o conteúdo histórico permaneceu idêntico. No teste consolidado de 30 dias, 86.301 medições existentes foram agregadas em 361 pontos, incluindo 21.408 alertas e 8.128 eventos críticos. A validação de navegador também verificou os filtros e downloads CSV das duas páginas de histórico.

## Arquivos e responsabilidades

| Grupo | Arquivos principais |
|---|---|
| Cadastro e validação | `app/models/room.py`, `app/schemas/room_schema.py`, `app/routes/room_routes.py`, `app/services/room_service.py` |
| Migração e consultas | `app/services/storage_service.py`, `app/services/room_analytics_service.py`, `app/models/sensor_reading.py` |
| Integração e origem | `app/routes/sensor_routes.py`, `app/schemas/sensor_reading_schema.py`, `app/services/mqtt_service.py`, `app/services/simulator_service.py`, `app/services/classification_service.py` |
| Navegação e apresentação | `app/main.py`, `app/security/auth.py`, `app/templates/dashboard.html`, `app/static/dashboard.js`, `app/static/rooms.js`, `app/static/rooms.css`, `app/static/icons.svg` |
| Ferramentas existentes | `scripts/seed_data.py`, `scripts/import_sensor_readings_csv.py`, `scripts/reset_simulated_readings.py` |
| Verificação | `tests/test_rooms.py`, `tests/test_sensor_routes.py`, `scripts/validate_rooms_ui.py`, `docs/evidence/` |

## Limites atuais

- Um dispositivo por sala; suportar múltiplos dispositivos na mesma sala exige uma entidade de dispositivos e regras de agregação.
- Exclusão lógica; não há tela de restauração nem purga definitiva de salas.
- Não há consulta automática a serviços meteorológicos externos. Os caminhos MQTT/API existentes continuam sendo os meios de ingestão.
- A identidade de sensor declarada no payload não verifica fisicamente o equipamento; a classificação da origem depende do emissor e do caminho de ingestão.
- O limiar de desatualização é de 30 minutos e os filtros rápidos cobrem 24h/7d/30d. A API permite períodos personalizados.
- O teste responsivo foi realizado no Chrome, em desktop e 390 px; não constitui validação em todos os dispositivos ou leitores de tela.
- O script de reset continua sendo uma ferramenta explícita de manutenção para regenerar as duas salas originais. Não faz parte do cadastro nem roda automaticamente.
