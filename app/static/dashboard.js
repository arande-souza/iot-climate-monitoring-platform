const numberFormat = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 1,
});
const integerFormat = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 0,
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
const updateSimulatedDataButton = document.getElementById("updateSimulatedData");
const updateSimulatedDataText = document.getElementById("updateSimulatedDataText");
const simulatorUpdateMessage = document.getElementById("simulatorUpdateMessage");
const logoutButton = document.getElementById("logoutButton");
let criticalHoursData = [];
let criticalHoursHoverPoint = null;
const simulatorUpdatePayload = {
  device_id: "esp32-sala-01",
  location: "Santo André - SP",
  frequency_seconds: 60,
  profile: "mixed",
};
const SIMULATOR_DEFAULT_MESSAGE = "Area de atualização manual";
let simulatorMessageResetTimeout;
const DASHBOARD_TIME_ZONE = "America/Sao_Paulo";
const DASHBOARD_TIME_ZONE_OFFSET = "-03:00";
const paginationState = {
  readings: {
    page: 1,
    pageSize: 50,
    total: 0,
    totalPages: 1,
    isLoading: false,
    requestId: 0,
  },
  alerts: {
    page: 1,
    pageSize: 50,
    total: 0,
    totalPages: 1,
    isLoading: false,
    requestId: 0,
  },
};

function getAccessToken() {
  return localStorage.getItem("accessToken");
}

function redirectToLogin() {
  localStorage.removeItem("accessToken");
  document.cookie = "access_token=; Max-Age=0; path=/";
  window.location.href = "/login";
}

function authenticatedHeaders(extraHeaders = {}) {
  const token = getAccessToken();
  if (!token) {
    redirectToLogin();
    return extraHeaders;
  }
  return {
    ...extraHeaders,
    Authorization: `Bearer ${token}`,
  };
}

function formatValue(value) {
  if (value === null || value === undefined) return "--";
  return numberFormat.format(value);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: DASHBOARD_TIME_ZONE,
  }).format(new Date(value));
}

function formatDateTimeLocal(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: DASHBOARD_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

function localInputToIso(value) {
  if (!value) return value;
  return `${value}:00${DASHBOARD_TIME_ZONE_OFFSET}`;
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
  const response = await fetch(url, {
    headers: authenticatedHeaders(),
  });
  const data = await response.json().catch(() => null);
  if (response.status === 401) {
    redirectToLogin();
    throw new Error("Sessao expirada");
  }
  if (!response.ok) {
    const detail = data?.detail || `Falha ao consultar ${url}`;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail);
  }
  return data;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: authenticatedHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    redirectToLogin();
    throw new Error("Sessao expirada");
  }
  if (!response.ok) {
    const detail = data.detail || `Falha ao chamar ${url}`;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail);
  }
  return data;
}

function buildPeriodUrl(baseUrl, startId, endId, deviceId, pagination, alertTypeId, statusFilterId) {
  const start = document.getElementById(startId).value;
  const end = document.getElementById(endId).value;
  const device = document.getElementById(deviceId).value.trim();
  const alertType = alertTypeId ? document.getElementById(alertTypeId).value : "";
  const statusFilter = statusFilterId ? document.getElementById(statusFilterId).value : "";
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
  if (alertType) {
    params.set("alert_type", alertType);
  }
  if (statusFilter) {
    params.set("status_filter", statusFilter);
  }
  if (pagination) {
    params.set("page", String(pagination.page));
    params.set("page_size", String(pagination.pageSize));
  }
  return `${baseUrl}?${params.toString()}`;
}

function validateDateRange(startId, endId) {
  const start = document.getElementById(startId).value;
  const end = document.getElementById(endId).value;
  if (!start || !end) return;

  if (new Date(localInputToIso(start)) > new Date(localInputToIso(end))) {
    throw new Error("A data inicial deve ser anterior ou igual a data final.");
  }
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

function updateSummary(summaryPayload) {
  document.getElementById("totalReadings").textContent =
    integerFormat.format(summaryPayload.total_readings);
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

function drawLine(context, points, color) {
  context.strokeStyle = color;
  context.lineWidth = 2.5;
  context.beginPath();
  points.forEach((point, index) => {
    if (index === 0) context.moveTo(point.x, point.y);
    else context.lineTo(point.x, point.y);
  });
  context.stroke();

  points.forEach((point) => {
    context.fillStyle = "#fff";
    context.beginPath();
    context.arc(point.x, point.y, 4, 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = color;
    context.lineWidth = 2;
    context.stroke();
  });
}

function drawCriticalHoursTooltip(context, point, width) {
  const lines = [
    `${point.hour}h`,
    `Alerta: ${point.alerta}`,
    `Critico: ${point.critico}`,
  ];
  const boxWidth = 112;
  const boxHeight = 74;
  const x = Math.min(width - boxWidth - 10, Math.max(10, point.x + 12));
  const y = Math.max(10, point.y - boxHeight - 12);

  context.fillStyle = "rgba(16, 32, 51, 0.92)";
  context.strokeStyle = "rgba(16, 32, 51, 0.18)";
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(x, y, boxWidth, boxHeight, 8);
  context.fill();
  context.stroke();

  context.fillStyle = "#fff";
  context.font = "700 12px sans-serif";
  context.fillText(lines[0], x + 10, y + 18);
  context.font = "12px sans-serif";
  context.fillStyle = "#facc15";
  context.fillText(lines[1], x + 10, y + 40);
  context.fillStyle = "#fca5a5";
  context.fillText(lines[2], x + 10, y + 58);
}

function updateCriticalHoursChart(hourCounts, hoverPoint = null) {
  criticalHoursData = hourCounts;
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
    criticalHoursHoverPoint = null;
    criticalContext.fillStyle = "#526173";
    criticalContext.font = "14px sans-serif";
    criticalContext.fillText("Nenhum alerta ou critico no periodo selecionado.", 18, 32);
    return;
  }

  const padding = { top: 24, right: 44, bottom: 34, left: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const max = Math.max(1, ...alertByHour, ...criticalByHour);

  criticalContext.strokeStyle = "#dfe6ef";
  criticalContext.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + (plotHeight / 4) * index;
    criticalContext.beginPath();
    criticalContext.moveTo(padding.left, y);
    criticalContext.lineTo(width - padding.right, y);
    criticalContext.stroke();
  }

  criticalContext.fillStyle = "#526173";
  criticalContext.font = "11px sans-serif";
  for (let index = 0; index <= 4; index += 1) {
    const value = Math.round(max - (max / 4) * index);
    const y = padding.top + (plotHeight / 4) * index;
    criticalContext.fillText(String(value), width - padding.right + 8, y + 4);
  }

  const points = Array.from({ length: 24 }, (_, hour) => {
    const x = padding.left + (plotWidth / 23) * hour;
    return {
      hour,
      x,
      alerta: alertByHour[hour],
      critico: criticalByHour[hour],
      alertY: padding.top + plotHeight - (alertByHour[hour] / max) * plotHeight,
      criticalY: padding.top + plotHeight - (criticalByHour[hour] / max) * plotHeight,
    };
  });
  const alertPoints = points.map((point) => ({ ...point, y: point.alertY }));
  const criticalPoints = points.map((point) => ({ ...point, y: point.criticalY }));

  drawLine(criticalContext, alertPoints, "#ca8a04");
  drawLine(criticalContext, criticalPoints, "#b91c1c");

  criticalContext.fillStyle = "#526173";
  criticalContext.font = "11px sans-serif";
  [0, 6, 12, 18, 23].forEach((hour) => {
    const x = padding.left + (plotWidth / 23) * hour;
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

  if (hoverPoint) {
    criticalContext.strokeStyle = "rgba(49, 65, 89, 0.35)";
    criticalContext.lineWidth = 1;
    criticalContext.beginPath();
    criticalContext.moveTo(hoverPoint.x, padding.top);
    criticalContext.lineTo(hoverPoint.x, padding.top + plotHeight);
    criticalContext.stroke();
    drawCriticalHoursTooltip(criticalContext, hoverPoint, width);
  }

  criticalHoursHoverPoint = {
    points,
    padding,
    plotHeight,
  };
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

function setSimulatorUpdateMessage(message, type) {
  window.clearTimeout(simulatorMessageResetTimeout);
  simulatorUpdateMessage.textContent = message;
  simulatorUpdateMessage.className = type || "";
}

function scheduleSimulatorMessageReset() {
  window.clearTimeout(simulatorMessageResetTimeout);
  simulatorMessageResetTimeout = window.setTimeout(() => {
    setSimulatorUpdateMessage(SIMULATOR_DEFAULT_MESSAGE, "");
  }, 5000);
}

async function refreshDashboard() {
  try {
    const [statusPayload, latestReadings, summaryPayload] = await Promise.all([
      fetchJson("/api/readings/status"),
      fetchJson("/api/readings/latest?limit=20"),
      fetchJson("/api/readings/summary"),
    ]);
    updateMetrics(statusPayload);
    updateSummary(summaryPayload);
    updateTable(latestReadings);
    updateChart(latestReadings);
  } catch (error) {
    document.getElementById("updatedAt").textContent = "Falha ao atualizar";
    console.error(error);
  }
}

async function loadReadingsHistory() {
  const state = paginationState.readings;
  try {
    validateDateRange("readingsStart", "readingsEnd");
  } catch (error) {
    document.getElementById("allReadingsTable").innerHTML =
      `<tr><td colspan="10">${error.message}</td></tr>`;
    document.getElementById("readingsCount").textContent = "0 registros";
    document.getElementById("readingsTotalInfo").textContent = "0 registros";
    document.getElementById("readingsPageInfo").textContent = "Pagina 1 de 1";
    return;
  }
  const url = buildPeriodUrl(
    "/api/readings/history",
    "readingsStart",
    "readingsEnd",
    "readingsDevice",
    state,
    null,
    "readingsStatus",
  );
  const requestId = state.requestId + 1;
  state.requestId = requestId;
  state.isLoading = true;
  document.getElementById("allReadingsTable").innerHTML =
    '<tr><td colspan="10">Carregando historico...</td></tr>';
  try {
    const payload = await fetchJson(url);
    if (requestId !== state.requestId) return;
    updatePaginationControls("readings", payload);
    document.getElementById("allReadingsTable").innerHTML = renderFullRows(
      payload.items,
      "Nenhuma leitura encontrada para o periodo.",
      10,
    );
  } catch (error) {
    if (requestId === state.requestId) {
      document.getElementById("allReadingsTable").innerHTML =
        `<tr><td colspan="10">Erro ao filtrar leituras: ${error.message}</td></tr>`;
    }
    throw error;
  } finally {
    if (requestId === state.requestId) {
      state.isLoading = false;
    }
  }
}

async function loadAlertsHistory() {
  const state = paginationState.alerts;
  try {
    validateDateRange("alertsStart", "alertsEnd");
  } catch (error) {
    document.getElementById("alertsTable").innerHTML =
      `<tr><td colspan="9">${error.message}</td></tr>`;
    document.getElementById("alertsCount").textContent = "0 registros";
    document.getElementById("alertsTotalInfo").textContent = "0 registros";
    document.getElementById("alertsPageInfo").textContent = "Pagina 1 de 1";
    updateCriticalHoursChart([]);
    return;
  }
  const url = buildPeriodUrl(
    "/api/readings/alerts",
    "alertsStart",
    "alertsEnd",
    "alertsDevice",
    state,
    "alertsType",
  );
  const criticalHoursUrl = buildPeriodUrl(
    "/api/readings/alerts/critical-hours",
    "alertsStart",
    "alertsEnd",
    "alertsDevice",
    null,
    "alertsType",
  );
  const requestId = state.requestId + 1;
  state.requestId = requestId;
  state.isLoading = true;
  document.getElementById("alertsTable").innerHTML =
    '<tr><td colspan="9">Carregando alertas...</td></tr>';
  try {
    const [payload, criticalHours] = await Promise.all([
      fetchJson(url),
      fetchJson(criticalHoursUrl),
    ]);
    if (requestId !== state.requestId) return;
    updatePaginationControls("alerts", payload);
    document.getElementById("alertsTable").innerHTML = renderFullRows(
      payload.items,
      "Nenhum alerta encontrado para o periodo.",
      9,
    );
    updateCriticalHoursChart(criticalHours);
  } catch (error) {
    if (requestId === state.requestId) {
      document.getElementById("alertsTable").innerHTML =
        `<tr><td colspan="9">Erro ao filtrar alertas: ${error.message}</td></tr>`;
    }
    throw error;
  } finally {
    if (requestId === state.requestId) {
      state.isLoading = false;
    }
  }
}

async function refreshVisibleDataAfterSimulationUpdate() {
  await setDefaultFilters();
  await refreshDashboard();

  if (document.getElementById("readingsView").classList.contains("active")) {
    paginationState.readings.page = 1;
    await loadReadingsHistory();
  }
  if (document.getElementById("alertsView").classList.contains("active")) {
    paginationState.alerts.page = 1;
    await loadAlertsHistory();
  }
}

async function updateSimulatedDataUntilNow() {
  if (updateSimulatedDataButton.disabled) return;

  updateSimulatedDataButton.disabled = true;
  updateSimulatedDataButton.classList.add("is-loading");
  updateSimulatedDataText.textContent = "Atualizando...";
  setSimulatorUpdateMessage("Gerando novos registros simulados...", "");

  try {
    const result = await postJson("/simulator/update-until-now", simulatorUpdatePayload);
    if (result.total_generated > 0) {
      setSimulatorUpdateMessage("Dados atualizados com sucesso", "success");
      scheduleSimulatorMessageReset();
    } else {
      setSimulatorUpdateMessage(result.message || SIMULATOR_DEFAULT_MESSAGE, "");
    }
    await refreshVisibleDataAfterSimulationUpdate();
  } catch (error) {
    setSimulatorUpdateMessage(`Erro ao atualizar dados: ${error.message}`, "error");
    console.error(error);
  } finally {
    updateSimulatedDataButton.disabled = false;
    updateSimulatedDataButton.classList.remove("is-loading");
    updateSimulatedDataText.textContent = "Atualizar dados";
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

document.getElementById("readingsStatus").addEventListener("change", () => {
  paginationState.readings.page = 1;
  loadReadingsHistory().catch(console.error);
});

document.getElementById("applyAlertsFilter").addEventListener("click", () => {
  paginationState.alerts.page = 1;
  loadAlertsHistory().catch(console.error);
});

document.getElementById("alertsType").addEventListener("change", () => {
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

updateSimulatedDataButton.addEventListener("click", () => {
  updateSimulatedDataUntilNow().catch(console.error);
});

logoutButton.addEventListener("click", () => {
  redirectToLogin();
});

criticalCanvas.addEventListener("mousemove", (event) => {
  if (!criticalHoursHoverPoint || !criticalHoursData.length) return;
  const rect = criticalCanvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const closest = criticalHoursHoverPoint.points.reduce((selected, point) => {
    if (!selected) return point;
    return Math.abs(point.x - mouseX) < Math.abs(selected.x - mouseX) ? point : selected;
  }, null);
  updateCriticalHoursChart(criticalHoursData, closest);
});

criticalCanvas.addEventListener("mouseleave", () => {
  if (!criticalHoursData.length) return;
  updateCriticalHoursChart(criticalHoursData);
});

async function initializeDashboard() {
  if (!getAccessToken()) {
    redirectToLogin();
    return;
  }
  await setDefaultFilters();
  refreshDashboard();
}

initializeDashboard();
setInterval(() => {
  if (document.getElementById("generalView").classList.contains("active")) {
    refreshDashboard();
  }
}, 10000);
