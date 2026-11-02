# Sistema de Monitoramento Climático para Otimização de Ambientes Tecnológicos

Aplicação acadêmica em Python para monitorar variáveis ambientais coletadas por sensores IoT, simulando a arquitetura:

`Sensores -> ESP32 -> MQTT Broker -> Ingestor Python -> PostgreSQL -> API/Dashboard`

O projeto usa FastAPI, PostgreSQL, SQLAlchemy, Pydantic, paho-mqtt, Docker Compose e Mosquitto.

## Funcionalidades

- **Custos e Investimentos**: cenários por sala, recálculo automático por potência média ou referência de etiqueta, manutenção opcional, comparação, projeções em 12/24/36 meses, distribuição por sala, indicadores ambientais e análise determinística. Exportação CSV e relatório com gráficos para impressão/PDF. Os resultados são estimativas; preços, consumo, uso e tarifa são informados pelo usuário. [Metodologia e instruções](docs/CUSTOS_E_INVESTIMENTOS.md).

- Gerenciamento dinâmico de salas, com cadastro, edição, exclusão confirmada e limites de temperatura/umidade por ambiente.
- Visão geral com indicadores e cards, página individual e comparação entre todas as salas cadastradas.
- Origem de cada leitura identificada como sensor, simulação, meteorologia externa ou desconhecida.
- Gráficos individuais e comparação com filtros de 24 horas, 7 dias e 30 dias.
- Cadastro com identificação do ambiente, cidade/UF, localização interna e dispositivo associado, preservando o texto das medições antigas.
- Gráficos consolidados de temperatura/umidade médias e ocorrências de alerta/críticas, com filtro por sala e período personalizado.
- Indicadores atuais de pressão, CO₂, PM2.5 e PM10 no ambiente individual, com ícones SVG locais.

Documentação da evolução do Projeto Integrador VI, migração, testes e evidências: [docs/EVOLUCAO_PI_VI.md](docs/EVOLUCAO_PI_VI.md).

- API REST para cadastrar e consultar leituras ambientais.
- Ingestão MQTT no tópico configurável `climate/readings`.
- Classificação automática do ambiente: `ideal`, `aceitavel`, `alerta` ou `critico`.
- Dashboard web simples com métricas atuais, status geral, últimas leituras e gráfico histórico.
- Menu lateral com telas de visão geral, histórico de leituras e histórico de alertas.
- Script de seed para popular dados fictícios.
- Testes básicos dos endpoints principais.

## Estrutura

```text
iot-climate-monitoring-platform/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models/
│   ├── schemas/
│   ├── routes/
│   ├── services/
│   ├── templates/
│   └── static/
├── scripts/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── mosquitto.conf
├── requirements.txt
├── .env.example
└── README.md
```

## Como rodar com Docker

```bash
docker compose up --build
```

Serviços expostos:

- Dashboard: http://localhost:8000
- API docs: http://localhost:8000/docs
- PostgreSQL: `localhost:5432`
- Mosquitto MQTT: `localhost:1883`

As tabelas são criadas automaticamente na inicialização da aplicação.

Depois acesse o dashboard em http://localhost:8000.

## Exemplo de envio via API

```bash
curl -X POST http://localhost:8000/api/readings \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32-sala-01",
    "location": "Sala de TI",
    "temperature": 23.5,
    "humidity": 48.2,
    "pressure": 1012.4,
    "co2": 750,
    "pm25": 8.5,
    "pm10": 18.3
  }'
```

## Exemplo de publicação MQTT

Com `mosquitto_pub` instalado localmente:

```bash
mosquitto_pub -h localhost -p 1883 -t climate/readings -m '{
  "device_id": "esp32-sala-01",
  "location": "Sala de TI",
  "temperature": 23.5,
  "humidity": 48.2,
  "pressure": 1012.4,
  "co2": 750,
  "pm25": 8.5,
  "pm10": 18.3
}'
```

## Monitorar duas ou mais salas

O dashboard abre na visão geral com todas as salas cadastradas. Use **Nova sala** ou **Gerenciar salas** para cadastrar ambientes, editar seus limites ou excluí-los mediante confirmação. A migração preserva Sala 1, Sala 2 e suas leituras existentes. O seletor **Sala / dispositivo** e os cards dão acesso ao dashboard individual; **Comparar ambientes** inclui automaticamente todas as salas ativas.

Métricas, status, gráficos, históricos, alertas e relatórios CSV respeitam a sala selecionada. Uma sala sem leituras mostra os indicadores vazios. Na **Visão Geral**, a seção **Coleta de dados**, com o subtítulo **Área de atualização manual**, oferece o botão **Atualizar dados**. Ele gera novas leituras para todas as salas ativas, mantendo a continuidade do histórico de cada ambiente. A interface usa textos neutros; o mecanismo continua sendo o gerador existente e preserva `data_source=simulation` nas novas leituras para auditoria. Leituras com mais de 30 minutos são sinalizadas como desatualizadas e não entram nas médias atuais da visão geral.

Para coletar dados reais da segunda sala, configure outro ESP32 para publicar no mesmo broker e tópico `climate/readings`, usando um identificador exclusivo:

```json
{
  "device_id": "esp32-sala-02",
  "location": "Sala 2",
  "temperature": 24.1,
  "humidity": 51.0,
  "pressure": 1012.4,
  "co2": 780,
  "pm25": 9.2,
  "pm10": 18.3
}
```

Esse mesmo JSON pode ser enviado para `POST /api/readings` com autenticação. Mantenha o `device_id` da sala 1 e seus dados existentes; cada sala deve usar seu próprio identificador. O campo `location` informa o nome do ambiente. Nesta versão, o painel identifica cada sala por um dispositivo.

Novas salas cadastradas aparecem imediatamente nos dashboards, mesmo sem medições. Para preservar a integração existente, dispositivos novos recebidos por MQTT/API também são cadastrados automaticamente. Sala 1 e Sala 2 são criadas na primeira migração; excluí-las não faz com que reapareçam após reiniciar. O simulador usa o local cadastrado da sala.

A aplicação aplica automaticamente uma migração aditiva ao iniciar: cria o cadastro de salas e adiciona vínculo e origem às leituras, preservando os valores anteriores. O broker continua o mesmo. A coleta real depende da configuração e conexão do ESP32; o botão do dashboard é um simulador. APIs meteorológicas externas podem ser identificadas no cadastro e nos payloads; não existe consulta automática a esses serviços.

### Limpar as leituras e definir uma nova data inicial

Para conferir o período e a quantidade de registros antes de alterar o banco:

```powershell
docker compose exec -T app python -m scripts.reset_simulated_readings --start 2026-08-10T00:00:00-03:00
```

Para aplicar a substituição:

```powershell
docker compose exec -T app python -m scripts.reset_simulated_readings --start 2026-08-10T00:00:00-03:00 --apply
```

**Esse comando substitui todas as leituras existentes** por dados simulados da Sala 1 e da Sala 2. Antes da exclusão, salva um CSV com todas as leituras em `backups/` na pasta do projeto. A exclusão e a geração são feitas na mesma transação: se houver falha, o banco mantém os dados anteriores.

A data usa o formato ISO 8601; `-03:00` indica o horário de Brasília. O período termina no momento da execução, com uma leitura por minuto e perfil `mixed`. Para mudar o término ou intervalo, use `--end 2026-08-11T00:00:00-03:00` e `--frequency-seconds 300`, por exemplo. A geração ocorre em lotes, permitindo períodos com mais de 100.000 registros por sala.

Depois, recarregue o dashboard. O botão **Atualizar dados** continua da última leitura da sala selecionada.

## Endpoints principais

- `GET /api/readings/devices` lista os dispositivos e o local da leitura mais recente de cada um.
- `latest`, `status` e `summary` aceitam `?device_id=esp32-sala-02`, assim como os filtros de histórico, alertas, horários críticos, período e exportações.

- `POST /api/readings` recebe uma leitura manual.
- `GET /api/readings/latest?limit=20` lista as últimas leituras.
- `GET /api/readings/history?start=2026-04-24T00:00:00Z&end=2026-04-24T23:59:59Z&page=1&page_size=50` consulta histórico por período com paginação.
- `GET /api/readings/alerts?start=2026-04-24T00:00:00Z&end=2026-04-24T23:59:59Z&page=1&page_size=50` consulta alertas e críticos por período com paginação.
- `GET /api/readings/alerts/critical-hours?start=2026-04-24T00:00:00Z&end=2026-04-24T23:59:59Z` agrega ocorrências de alerta e crítico por hora para o gráfico `Horario Critico`.
- `GET /api/readings/device/{device_id}` consulta leituras por dispositivo.
- `GET /api/readings/status` retorna o status atual do ambiente.
- `POST /simulator/generate` gera massa histórica simulada.
- `GET /health` verifica se a aplicação está ativa.


Perfis aceitos:

- `normal`: leituras concentradas nas faixas ideais.
- `alert`: algumas leituras fora das faixas aceitáveis.
- `critical`: maior chance de CO₂ e PM2.5 críticos.
- `mixed`: mistura dados normais, alertas e críticos.

O simulador gera uma leitura a cada `frequency_seconds`, valida se `end_datetime` é maior que `start_datetime` e bloqueia chamadas com mais de 100.000 registros. As leituras são salvas em `sensor_readings`, com `air_quality_status` calculado automaticamente, e aparecem no dashboard.

## Paginação dos históricos

As telas `Historico Leituras` e `Historico Alertas` possuem paginação com seletor `Exibir`.

Opções disponíveis:

- 20 registros por página
- 50 registros por página
- 100 registros por página
- 200 registros por página
- 500 registros por página
- 1000 registros por página

O valor padrão é `50`. Ao alterar o seletor, a tabela recarrega automaticamente e volta para a página 1.

## Regras de classificação

Temperatura:

- Ideal: 22°C a 24°C
- Aceitável: 20°C a 26°C
- Alerta: abaixo de 20°C ou acima de 26°C

Umidade:

- Ideal: 40% a 60%
- Aceitável: 30% a 65%
- Alerta: abaixo de 30% ou acima de 65%

CO₂:

- Ideal: até 800 ppm
- Aceitável: até 1000 ppm
- Alerta: acima de 1000 ppm
- Crítico: acima de 1500 ppm

PM2.5:

- Ideal: abaixo de 12 µg/m³
- Alerta: 12 a 35 µg/m³
- Crítico: acima de 35 µg/m³

O status geral usa a pior classificação entre temperatura, umidade, CO₂ e PM2.5.

## Variáveis de ambiente

Copie `.env.example` para `.env` se quiser rodar localmente sem Docker:

```bash
cp .env.example .env
```

Principais variáveis:

- `DATABASE_URL`
- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_TOPIC`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_ENABLED`

## Rodar localmente sem Docker

É necessário ter PostgreSQL e Mosquitto disponíveis.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Testes

```bash
pytest
```
