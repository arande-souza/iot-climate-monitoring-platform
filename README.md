# Sistema de Monitoramento Climático para Otimização de Ambientes Tecnológicos

Aplicação acadêmica em Python para monitorar variáveis ambientais coletadas por sensores IoT, simulando a arquitetura:

`Sensores -> ESP32 -> MQTT Broker -> Ingestor Python -> PostgreSQL -> API/Dashboard`

O projeto usa FastAPI, PostgreSQL, SQLAlchemy, Pydantic, paho-mqtt, Docker Compose e Mosquitto.

## Funcionalidades

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

## Popular dados fictícios

Com os containers rodando:

```bash
docker compose exec app python scripts/seed_data.py
```

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

Também é possível publicar de dentro do container do broker, caso o cliente esteja disponível na imagem:

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -p 1883 -t climate/readings -m '{"device_id":"esp32-sala-01","location":"Sala de TI","temperature":23.5,"humidity":48.2,"pressure":1012.4,"co2":750,"pm25":8.5,"pm10":18.3}'
```

## Endpoints principais

- `POST /api/readings` recebe uma leitura manual.
- `GET /api/readings/latest?limit=20` lista as últimas leituras.
- `GET /api/readings/history?start=2026-04-24T00:00:00Z&end=2026-04-24T23:59:59Z&page=1&page_size=50` consulta histórico por período com paginação.
- `GET /api/readings/alerts?start=2026-04-24T00:00:00Z&end=2026-04-24T23:59:59Z&page=1&page_size=50` consulta alertas e críticos por período com paginação.
- `GET /api/readings/alerts/critical-hours?start=2026-04-24T00:00:00Z&end=2026-04-24T23:59:59Z` agrega ocorrências de alerta e crítico por hora para o gráfico `Horario Critico`.
- `GET /api/readings/device/{device_id}` consulta leituras por dispositivo.
- `GET /api/readings/status` retorna o status atual do ambiente.
- `POST /simulator/generate` gera massa histórica simulada.
- `GET /health` verifica se a aplicação está ativa.

## Gerar massa histórica simulada

```bash
curl -X POST http://localhost:8000/simulator/generate \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32-sala-01",
    "location": "Santo André - SP",
    "start_datetime": "2026-03-16T08:00:00",
    "end_datetime": "2026-03-16T18:00:00",
    "frequency_seconds": 60,
    "profile": "mixed"
  }'
```

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
