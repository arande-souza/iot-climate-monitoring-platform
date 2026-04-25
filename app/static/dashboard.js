const numberFormat = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 1,
});

const views = {
  generalView: {
    title: "Geral",
    subtitle: "Status atual e leituras recentes dos sensores IoT",
  },
  readingsView: {
    title: "Historico Leituras",
    subtitle: "Consulta completa por periodo, local e dispositivo",
  },
  alertsView: {
    title: "Historico Alertas",
    subtitle: "Ocorrencias em alerta ou criticas e distribuicao por hora",
  },
};

const statusBand = document.querySelector(".status-band");
const chartCanvas = document.getElementById("historyChart");
const chartContext = chartCanvas.getContext("2d");
const criticalCanvas = document.getElementById("criticalHoursChart");
const criticalContext = criticalCanvas.getContext("2d");
const paginationState = {
  readings: {
    page: 1,
    pageSize: 50,
    total: 0,
    totalPages: 1,
    isLoading: false,
    lastRequestKey: "",
  },
  alerts: {
    page: 1,
    pageSize: 50,
    total: 0,
    totalPages: 1,
    isLoading: false,
    lastRequestKey: "",
  },
};

function formatValue(value) {
  if (value === null || value === undefined) return "--";
  return numberFormat.format(value);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

function formatDateTimeLocal(date) {
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function localInputToIso(value) {
  return value;
}

function getDefaultPeriod() {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  return { start, end };
}

async function setDefaultFilters() {
  let { start, end } = getDefaultPeriod();

  try {
    const range = await fetchJson("/api/readings/range");
    if (range.start_datetime && range.end_datetime) {
      start = new Date(range.start_datetime);
      end = new Date(range.end_datetime);
    }
  } catch (error) {
    console.error(error);
  }

  ["readingsStart", "alertsStart"].forEach((id) => {
    document.getElementById(id).value = formatDateTimeLocal(start);
  });
  ["readingsEnd", "alertsEnd"].forEach((id) => {
    document.getElementById(id).value = formatDateTimeLocal(end);
  });
}

function setStatusClass(status) {
  statusBand.className = "status-band";
  statusBand.classList.add(`status-${status || "sem_dados"}`);
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Falha ao consultar ${url}`);
  }
  return response.json();
}

function buildPeriodUrl(baseUrl, startId, endId, deviceId, pagination) {
  const start = document.getElementById(startId).value;
  const end = document.getElementById(endId).value;
  const device = document.getElementById(deviceId).value.trim();
  const params = new URLSearchParams();
  if (start) {
    params.set("start", localInputToIso(start));
  }
  if (end) {
    params.set("end", localInputToIso(end));
  }
  if (device) {
    params.set("device_id", device);
  }
  if (pagination) {
    params.set("page", String(pagination.page));
    params.set("page_size", String(pagination.pageSize));
  }
  return `${baseUrl}?${params.toString()}`;
}

function updateMetrics(statusPayload) {
  const reading = statusPayload.latest_reading;
  document.getElementById("status").textContent = statusPayload.status.replace("_", " ");
  document.getElementById("recommendations").textContent = statusPayload.recommendations.join(" ");
  setStatusClass(statusPayload.status);

  if (!reading) return;

  document.getElementById("temperature").textContent = formatValue(reading.temperature);
  document.getElementById("humidity").textContent = formatValue(reading.humidity);
  document.getElementById("co2").textContent = formatValue(reading.co2);
  document.getElementById("pm25").textContent = formatValue(reading.pm25);
  document.getElementById("updatedAt").textContent = `Atualizado em ${formatDate(reading.created_at)}`;
}

function renderStatusBadge(status) {
  const normalizedStatus = {
    normal: "ideal",
    alert: "alerta",
    critical: "critico",
  }[status] || status;
  return `<span class="badge ${normalizedStatus}">${normalizedStatus}</span>`;
}

function renderCompactRows(readings, emptyMessage) {
  if (!readings.length) {
    return `<tr><td colspan="8">${emptyMessage}</td></tr>`;
  }

  return readings.map((reading) => `
    <tr>
      <td>${formatDate(reading.created_at)}</td>
      <td>${reading.device_id}</td>
      <td>${reading.location}</td>
      <td>${formatValue(reading.temperature)} °C</td>
      <td>${formatValue(reading.humidity)}%</td>
      <td>${formatValue(reading.co2)}</td>
      <td>${formatValue(reading.pm25)}</td>
      <td>${renderStatusBadge(reading.air_quality_status)}</td>
    </tr>
  `).join("");
}

function renderFullRows(readings, emptyMessage, columns) {
  if (!readings.length) {
    return `<tr><td colspan="${columns}">${emptyMessage}</td></tr>`;
  }

  return readings.map((reading) => `
    <tr>
      <td>${formatDate(reading.created_at)}</td>
      <td>${reading.device_id}</td>
      <td>${reading.location}</td>
      <td>${formatValue(reading.temperature)} °C</td>
      <td>${formatValue(reading.humidity)}%</td>
      ${columns === 10 ? `<td>${formatValue(reading.pressure)}</td>` : ""}
      <td>${formatValue(reading.co2)}</td>
      <td>${formatValue(reading.pm25)}</td>
      <td>${formatValue(reading.pm10)}</td>
      <td>${renderStatusBadge(reading.air_quality_status)}</td>
    </tr>
  `).join("");
}

function updateTable(readings) {
  document.getElementById("readingsTable").innerHTML = renderCompactRows(
    readings,
    "Nenhuma leitura registrada.",
  );
}

function prepareCanvas(canvas, context) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight || 260;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  return { width, height };
}

function updateChart(readings) {
  const ordered = [...readings].reverse();
  const { width, height } = prepareCanvas(chartCanvas, chartContext);

  if (ordered.length < 2) {
    chartContext.fillStyle = "#526173";
    chartContext.font = "14px sans-serif";
    chartContext.fillText("Aguardando mais leituras para formar o grafico.", 18, 32);
    return;
  }

  const padding = { top: 18, right: 18, bottom: 34, left: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const series = [
    { label: "Temp.", color: "#dc2626", values: ordered.map((reading) => reading.temperature) },
    { label: "Umid.", color: "#2563eb", values: ordered.map((reading) => reading.humidity) },
    { label: "PM2.5", color: "#ca8a04", values: ordered.map((reading) => reading.pm25) },
  ];
  const allValues = series.flatMap((item) => item.values);
  const min = Math.min(...allValues) - 2;
  const max = Math.max(...allValues) + 2;

  chartContext.strokeStyle = "#dfe6ef";
  chartContext.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + (plotHeight / 4) * index;
    chartContext.beginPath();
    chartContext.moveTo(padding.left, y);
    chartContext.lineTo(width - padding.right, y);
    chartContext.stroke();
  }

  chartContext.fillStyle = "#526173";
  chartContext.font = "12px sans-serif";
  chartContext.fillText(String(Math.round(max)), 8, padding.top + 4);
  chartContext.fillText(String(Math.round(min)), 8, padding.top + plotHeight);

  series.forEach((item) => {
    chartContext.strokeStyle = item.color;
    chartContext.lineWidth = 2;
    chartContext.beginPath();
    item.values.forEach((value, index) => {
      const x = padding.left + (plotWidth / (item.values.length - 1)) * index;
      const y = padding.top + plotHeight - ((value - min) / (max - min)) * plotHeight;
      if (index === 0) chartContext.moveTo(x, y);
      else chartContext.lineTo(x, y);
    });
    chartContext.stroke();
  });

  const legendY = height - 12;
  series.forEach((item, index) => {
    const x = padding.left + index * 92;
    chartContext.fillStyle = item.color;
    chartContext.fillRect(x, legendY - 9, 10, 10);
    chartContext.fillStyle = "#314159";
    chartContext.fillText(item.label, x + 15, legendY);
  });
}

function updateCriticalHoursChart(hourCounts) {
  const { width, height } = prepareCanvas(criticalCanvas, criticalContext);
  const alertByHour = Array.from({ length: 24 }, () => 0);
  const criticalByHour = Array.from({ length: 24 }, () => 0);

  hourCounts.forEach((item) => {
    alertByHour[item.hour] = item.alerta;
    criticalByHour[item.hour] = item.critico;
  });

  const totalAlerts = alertByHour.reduce((sum, value) => sum + value, 0);
  const totalCritical = criticalByHour.reduce((sum, value) => sum + value, 0);
  const totalOccurrences = totalAlerts + totalCritical;
  document.getElementById("criticalHoursCount").textContent =
    `${totalAlerts} alertas, ${totalCritical} criticos`;

  if (totalOccurrences === 0) {
    criticalContext.fillStyle = "#526173";
    criticalContext.font = "14px sans-serif";
    criticalContext.fillText("Nenhum alerta ou critico no periodo selecionado.", 18, 32);
    return;
  }

  const padding = { top: 18, right: 14, bottom: 34, left: 36 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const totalsByHour = alertByHour.map((value, hour) => value + criticalByHour[hour]);
  const max = Math.max(...totalsByHour);
  const barGap = 4;
  const barWidth = (plotWidth - barGap * 23) / 24;

  criticalContext.strokeStyle = "#dfe6ef";
  criticalContext.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + (plotHeight / 4) * index;
    criticalContext.beginPath();
    criticalContext.moveTo(padding.left, y);
    criticalContext.lineTo(width - padding.right, y);
    criticalContext.stroke();
  }

  totalsByHour.forEach((value, hour) => {
    const x = padding.left + hour * (barWidth + barGap);
    const alertHeight = (alertByHour[hour] / max) * plotHeight;
    const criticalHeight = (criticalByHour[hour] / max) * plotHeight;
    const alertY = padding.top + plotHeight - alertHeight;
    const criticalY = alertY - criticalHeight;

    criticalContext.fillStyle = "#ca8a04";
    criticalContext.fillRect(x, alertY, barWidth, alertHeight);
    criticalContext.fillStyle = "#b91c1c";
    criticalContext.fillRect(x, criticalY, barWidth, criticalHeight);
  });

  criticalContext.fillStyle = "#526173";
  criticalContext.font = "11px sans-serif";
  [0, 6, 12, 18, 23].forEach((hour) => {
    const x = padding.left + hour * (barWidth + barGap);
    criticalContext.fillText(`${hour}h`, x, height - 10);
  });

  const legendY = 18;
  criticalContext.fillStyle = "#ca8a04";
  criticalContext.fillRect(width - 190, legendY - 9, 10, 10);
  criticalContext.fillStyle = "#314159";
  criticalContext.fillText("Alerta", width - 174, legendY);
  criticalContext.fillStyle = "#b91c1c";
  criticalContext.fillRect(width - 108, legendY - 9, 10, 10);
  criticalContext.fillStyle = "#314159";
  criticalContext.fillText("Critico", width - 92, legendY);
}

function updatePaginationControls(scope, payload) {
  const state = paginationState[scope];
  state.total = payload.total;
  state.page = payload.page;
  state.pageSize = payload.page_size;
  state.totalPages = payload.total_pages;

  document.getElementById(`${scope}Count`).textContent = `${payload.total} registros`;
  document.getElementById(`${scope}TotalInfo`).textContent = `${payload.total} registros`;
  document.getElementById(`${scope}PageInfo`).textContent =
    `Pagina ${payload.page} de ${payload.total_pages}`;
  document.getElementById(`${scope}PrevPage`).disabled = payload.page <= 1;
  document.getElementById(`${scope}NextPage`).disabled = payload.page >= payload.total_pages;
  document.getElementById(`${scope}PageSize`).value = String(payload.page_size);
}

function getRequestKey(scope, url) {
  return `${scope}:${url}`;
}

async function refreshDashboard() {
  try {
    const [statusPayload, latestReadings] = await Promise.all([
      fetchJson("/api/readings/status"),
      fetchJson("/api/readings/latest?limit=20"),
    ]);
    updateMetrics(statusPayload);
    updateTable(latestReadings);
    updateChart(latestReadings);
  } catch (error) {
    document.getElementById("updatedAt").textContent = "Falha ao atualizar";
    console.error(error);
  }
}

async function loadReadingsHistory() {
  const state = paginationState.readings;
  const url = buildPeriodUrl(
    "/api/readings/history",
    "readingsStart",
    "readingsEnd",
    "readingsDevice",
    state,
  );
  const requestKey = getRequestKey("readings", url);
  if (state.isLoading && state.lastRequestKey === requestKey) return;

  state.isLoading = true;
  state.lastRequestKey = requestKey;
  try {
    const payload = await fetchJson(url);
    updatePaginationControls("readings", payload);
    document.getElementById("allReadingsTable").innerHTML = renderFullRows(
      payload.items,
      "Nenhuma leitura encontrada para o periodo.",
      10,
    );
  } finally {
    state.isLoading = false;
  }
}

async function loadAlertsHistory() {
  const state = paginationState.alerts;
  const url = buildPeriodUrl(
    "/api/readings/alerts",
    "alertsStart",
    "alertsEnd",
    "alertsDevice",
    state,
  );
  const criticalHoursUrl = buildPeriodUrl(
    "/api/readings/alerts/critical-hours",
    "alertsStart",
    "alertsEnd",
    "alertsDevice",
  );
  const requestKey = getRequestKey("alerts", url);
  if (state.isLoading && state.lastRequestKey === requestKey) return;

  state.isLoading = true;
  state.lastRequestKey = requestKey;
  try {
    const [payload, criticalHours] = await Promise.all([
      fetchJson(url),
      fetchJson(criticalHoursUrl),
    ]);
    updatePaginationControls("alerts", payload);
    document.getElementById("alertsTable").innerHTML = renderFullRows(
      payload.items,
      "Nenhum alerta encontrado para o periodo.",
      9,
    );
    updateCriticalHoursChart(criticalHours);
  } finally {
    state.isLoading = false;
  }
}

function switchView(viewId) {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === viewId);
  });
  document.getElementById("pageTitle").textContent = views[viewId].title;
  document.getElementById("pageSubtitle").textContent = views[viewId].subtitle;

  if (viewId === "generalView") refreshDashboard();
  if (viewId === "readingsView") loadReadingsHistory().catch(console.error);
  if (viewId === "alertsView") loadAlertsHistory().catch(console.error);
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

document.getElementById("applyReadingsFilter").addEventListener("click", () => {
  paginationState.readings.page = 1;
  loadReadingsHistory().catch(console.error);
});

document.getElementById("applyAlertsFilter").addEventListener("click", () => {
  paginationState.alerts.page = 1;
  loadAlertsHistory().catch(console.error);
});

document.getElementById("readingsPageSize").addEventListener("change", (event) => {
  paginationState.readings.pageSize = Number(event.target.value);
  paginationState.readings.page = 1;
  loadReadingsHistory().catch(console.error);
});

document.getElementById("alertsPageSize").addEventListener("change", (event) => {
  paginationState.alerts.pageSize = Number(event.target.value);
  paginationState.alerts.page = 1;
  loadAlertsHistory().catch(console.error);
});

document.getElementById("readingsPrevPage").addEventListener("click", () => {
  if (paginationState.readings.page <= 1) return;
  paginationState.readings.page -= 1;
  loadReadingsHistory().catch(console.error);
});

document.getElementById("readingsNextPage").addEventListener("click", () => {
  if (paginationState.readings.page >= paginationState.readings.totalPages) return;
  paginationState.readings.page += 1;
  loadReadingsHistory().catch(console.error);
});

document.getElementById("alertsPrevPage").addEventListener("click", () => {
  if (paginationState.alerts.page <= 1) return;
  paginationState.alerts.page -= 1;
  loadAlertsHistory().catch(console.error);
});

document.getElementById("alertsNextPage").addEventListener("click", () => {
  if (paginationState.alerts.page >= paginationState.alerts.totalPages) return;
  paginationState.alerts.page += 1;
  loadAlertsHistory().catch(console.error);
});

async function initializeDashboard() {
  await setDefaultFilters();
  refreshDashboard();
}

initializeDashboard();
setInterval(() => {
  if (document.getElementById("generalView").classList.contains("active")) {
    refreshDashboard();
  }
}, 10000);
