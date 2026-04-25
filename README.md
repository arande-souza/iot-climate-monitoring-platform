# 🌡️ IoT Climate Monitoring Platform

Sistema de monitoramento climático em tempo real para ambientes tecnológicos, utilizando IoT, mensageria MQTT e análise de dados para apoiar decisões relacionadas à climatização, conforto e qualidade do ar.

A nossa solução é reponsável por coletar, processar e analisar variáveis ambientais como temperatura, umidade, CO₂ e material particulado, fornecendo métricas, alertas e visualizações históricas.

Arquitetura:

Sensores → ESP32 → MQTT → Backend (FastAPI) → PostgreSQL → Dashboard

---

## 🎯 Objetivo do Projeto

A solução tem como objetivo:

- Monitorar condições ambientais em tempo real
- Melhorar o conforto térmico dos colaboradores
- Reduzir riscos operacionais em equipamentos
- Apoiar decisões baseadas em dados
- Identificar padrões e anomalias ambientais

---

## 🏗️ Arquitetura do Sistema

O sistema segue uma arquitetura baseada em eventos e ingestão de dados em tempo real:

- ESP32 realiza leitura dos sensores
- Dados são enviados via MQTT
- Backend Python consome e processa as mensagens
- Dados são persistidos no PostgreSQL
- Dashboard apresenta dados em tempo real e históricos

**Frequência de coleta:**
- 1 leitura a cada **60 segundos**
- Justificativa: equilíbrio entre monitoramento em tempo real e volume de dados

---

## ⚙️ Tecnologias Utilizadas

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Pydantic
- MQTT (Mosquitto)
- Docker / Docker Compose

---

## 🚀 Funcionalidades

- API REST para ingestão e consulta de dados ambientais
- Consumo de dados via MQTT
- Classificação automática do ambiente:
  - ideal
  - aceitável
  - alerta
  - crítico
- Dashboard web com:
  - métricas em tempo real
  - histórico de leituras
  - histórico de alertas
  - gráfico temporal
- Simulador de dados ambientais
- Paginação de históricos
- Testes automatizados

---

## 📊 Métricas e Indicadores

O sistema fornece indicadores para análise ambiental:

- Índice de Qualidade do Ambiente (score)
- Histórico de leituras
- Histórico de alertas
- Percentual de tempo em alerta
- Tempo total em estado crítico
- Médias diárias de variáveis ambientais

Essas métricas permitem identificar padrões, tendências e problemas operacionais.

---

## 📦 Volume de Dados

Com frequência de 60 segundos:

- ~1.440 registros por dia por dispositivo
- ~43.200 registros por mês
- ~525.000 registros por ano

O sistema foi projetado para suportar esse volume de forma eficiente.

---

## 🧪 Simulação de Dados

O sistema possui um gerador de dados simulados para testes e análise:

- Geração de massa histórica configurável
- Frequência de coleta parametrizável
- Perfis de dados:
  - normal
  - alert
  - critical
  - mixed
- Baseado em parâmetros climáticos realistas de Santo André - SP

Isso permite testar cenários reais sem necessidade de hardware físico.

---

## 📁 Estrutura do Projeto

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
