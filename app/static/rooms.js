// Room management and dashboards reuse authentication, navigation and history in dashboard.js.
const sourceNames = {
  sensor: "Sensor IoT", simulation: "Atualização manual", external_api: "Meteorologia externa",
  unknown: "Origem não identificada",
};
let overviewVersion = 0;
let overviewHistoryVersion = 0;
let detailVersion = 0;
let comparisonVersion = 0;
const chartStates = new Map();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

function sourceLabel(value) {
  return sourceNames[value] || sourceNames.unknown;
}

function sourceDescription(sources) {
  const entries = Object.entries(sources || {});
  return entries.length ? entries.map(([source, count]) => `${sourceLabel(source)} (${integerFormat.format(count)})`).join(" · ") : "Sem leituras no período";
}

function selectedRoom() {
  return rooms.get(roomSelect.value);
}

function notify(message, error = false) {
  const notice = document.getElementById("roomNotice");
  notice.hidden = !message;
  notice.textContent = message;
  notice.classList.toggle("notice-error", error);
}

function statusLabel(status) {
  return ({ normal: "Normal", atencao: "Atenção", critico: "Crítica", sem_dados: "Sem dados", desatualizado: "Desatualizada" })[status] || "Sem dados";
}

function statusPill(status) {
  const known = ["normal", "atencao", "critico", "sem_dados", "desatualizado"].includes(status) ? status : "sem_dados";
  return `<span class="room-status state-${known}"><span aria-hidden="true">●</span> ${statusLabel(known)}</span>`;
}

function icon(name) {
  return `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#${name}"/></svg>`;
}

function locationDescription(room) {
  const geography = [room.city, room.state].filter(Boolean).join(" / ");
  const physical = [room.identifier ? `Ambiente ${room.identifier}` : "", room.internal_location].filter(Boolean).join(" · ");
  return [geography, physical, !geography && !physical ? room.location : ""].filter(Boolean).join(" · ");
}

function metric(label, value, suffix = "", detail = "", iconName = "chart") {
  return `<article class="summary-card"><span>${icon(iconName)}${escapeHtml(label)}</span><strong>${escapeHtml(value)}<small>${escapeHtml(suffix)}</small></strong>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}</article>`;
}

function roomCard(item, manage = false) {
  const room = item.room || item;
  const reading = item.latest_reading;
  return `<article class="room-card">
    <div class="section-heading"><h3>${escapeHtml(room.name)}</h3>${manage ? "" : statusPill(item.monitoring_status)}</div>
    <p class="muted room-description">${escapeHtml(room.description || "Ambiente monitorado")}</p>
    <p class="room-location">${icon("map-pin")}<span>${escapeHtml(locationDescription(room))}</span></p>
    ${(manage || !reading ? room.data_source : reading.data_source) === "simulation" ? "" : `<span class="source-tag">${manage || !reading ? "Origem configurada: " : ""}${sourceLabel(manage || !reading ? room.data_source : reading.data_source)}</span>`}
    ${manage ? `<p class="muted">${escapeHtml(room.device_id)}</p><p>Temperatura: ${formatValue(room.temperature_min)} a ${formatValue(room.temperature_max)} °C<br>Umidade: ${formatValue(room.humidity_min)} a ${formatValue(room.humidity_max)}%</p>` : `
      <div class="room-values"><div><span>${icon("temperature")}Temperatura</span><strong>${formatValue(reading?.temperature)}<small> °C</small></strong></div><div><span>${icon("droplet")}Umidade</span><strong>${formatValue(reading?.humidity)}<small> %</small></strong></div></div>
      <p class="muted">${reading ? `Última leitura: ${formatDate(reading.created_at)}` : "Nenhuma leitura disponível"}</p>`}
    <div class="room-actions"><button type="button" data-open-room="${room.id}">Ver ambiente →</button>${manage ? `<button type="button" class="secondary-action" data-edit-room="${room.id}">Editar</button><button type="button" class="danger-action" data-delete-room="${room.id}">Excluir</button>` : `<button type="button" class="secondary-action" data-edit-room="${room.id}">Configurar</button>`}</div>
  </article>`;
}

async function refreshOverview() {
  const version = ++overviewVersion;
  try {
    const payload = await fetchJson("/api/rooms/overview");
    if (version !== overviewVersion) return;
    document.getElementById("overviewMetrics").innerHTML = [
      metric("Salas cadastradas", payload.total_rooms, "", "Todos os ambientes", "building"),
      metric("Salas normais", payload.counts.normal, "", "Leituras atuais dentro dos limites", "check"),
      metric("Em alerta ou críticas", payload.counts.atencao + payload.counts.critico, "", `${payload.counts.atencao} em atenção · ${payload.counts.critico} críticas`, "alert"),
      metric("Temperatura média", formatValue(payload.temperature_avg), " °C", "Última leitura válida de cada sala", "temperature"),
      metric("Umidade média", formatValue(payload.humidity_avg), " %", "Última leitura válida de cada sala", "droplet"),
      metric("Dispositivos ativos", "2/2", "", "Conectividade esperada ESP32", "chip"),
    ].join("");
    document.getElementById("overviewContext").textContent = `Médias de ${payload.valid_rooms} sala(s) com leituras válidas nos últimos ${payload.stale_after_minutes} minutos. ${payload.counts.sem_dados} sem dados · ${payload.counts.desatualizado} desatualizada(s). ${payload.external_reference_rooms} referência(s) meteorológica(s) externa(s) excluída(s) das médias.`;
    document.getElementById("roomCards").innerHTML = payload.rooms.length ? payload.rooms.map(item => roomCard(item)).join("") : '<p class="empty-state">Nenhuma sala cadastrada. Use “Nova sala” para começar.</p>';
    if (document.getElementById("overviewView").classList.contains("active")) {
      document.getElementById("updatedAt").textContent = `Atualizado em ${formatDate(payload.updated_at)}`;
    }
    await refreshOverviewCharts();
  } catch (error) {
    if (version === overviewVersion) {
      document.getElementById("roomCards").innerHTML = `<p class="form-error">Não foi possível atualizar os ambientes: ${escapeHtml(error.message)}</p>`;
      notify("Falha na atualização. Os indicadores anteriores podem estar desatualizados.", true);
    }
  }
}

function syncOverviewRoomFilter() {
  const select = document.getElementById("overviewRoomFilter");
  const previous = select.value;
  const all = document.createElement("option"); all.value = ""; all.textContent = "Todas as salas";
  select.replaceChildren(all, ...Array.from(rooms.values(), room => {
    const option = document.createElement("option"); option.value = room.id; option.textContent = room.name;
    return option;
  }));
  select.value = findRoom(previous) ? previous : "";
}

function drawOverviewSeries(series) {
  drawHistory("overviewTemperatureChart", series, "temperature", "°C", "#0f766e");
  drawHistory("overviewHumidityChart", series, "humidity", "%", "#2563eb");
  drawHistory("overviewEventsChart", series, "alerts", "ocorrência(s)", "#a16207", null, "critical");
}

async function refreshOverviewCharts() {
  const version = ++overviewHistoryVersion;
  const context = document.getElementById("overviewHistoryContext");
  const table = document.getElementById("overviewSeriesTable");
  const charts = document.querySelector(".overview-history");
  charts.setAttribute("aria-busy", "true");
  context.textContent = "Carregando histórico consolidado…";
  const params = new URLSearchParams();
  const period = document.getElementById("overviewPeriod").value;
  if (period === "custom") {
    const start = document.getElementById("overviewStart").value;
    const end = document.getElementById("overviewEnd").value;
    if (!start || !end || new Date(localInputToIso(start)) >= new Date(localInputToIso(end))) {
      context.textContent = "Informe um período válido: a data inicial deve ser anterior à final.";
      charts.setAttribute("aria-busy", "false"); drawOverviewSeries([]);
      table.innerHTML = '<tr><td colspan="7">Selecione um período válido.</td></tr>';
      return;
    }
    params.set("start", localInputToIso(start)); params.set("end", localInputToIso(end));
  } else params.set("days", period);
  const room = document.getElementById("overviewRoomFilter").value;
  if (room) params.set("room_id", room);
  try {
    const payload = await fetchJson(`/api/rooms/overview/history?${params}`);
    if (version !== overviewHistoryVersion) return;
    drawOverviewSeries(payload.series);
    context.textContent = payload.series.length
      ? `${formatDate(payload.start)} a ${formatDate(payload.end)}. Médias por sala em intervalos de ${Math.round(payload.bucket_seconds / 60)} minuto(s), com o mesmo peso para cada ambiente. ${sourceDescription(payload.sources)}. Referências meteorológicas externas excluídas. As contagens são ocorrências registradas, não duração dos eventos; lacunas não são preenchidas.`
      : "Nenhuma medição válida disponível no período e nas salas selecionadas. Referências meteorológicas externas não entram nos gráficos; nenhum dado foi criado para preencher o histórico.";
    table.innerHTML = payload.series.length ? payload.series.map(point => `<tr><td>${formatDate(point.at)}</td><td>${formatValue(point.temperature)} °C</td><td>${formatValue(point.humidity)}%</td><td>${point.room_count}</td><td>${point.count}</td><td>${point.alerts}</td><td>${point.critical}</td></tr>`).join("") : '<tr><td colspan="7">Sem histórico válido para este filtro.</td></tr>';
  } catch (error) {
    if (version !== overviewHistoryVersion) return;
    context.textContent = `Não foi possível carregar os gráficos: ${error.message}`;
    drawOverviewSeries([]);
    table.innerHTML = '<tr><td colspan="7">Falha ao consultar o histórico consolidado.</td></tr>';
  } finally { if (version === overviewHistoryVersion) charts.setAttribute("aria-busy", "false"); }
}

function renderManagement() {
  document.getElementById("roomManagement").innerHTML = rooms.size
    ? Array.from(rooms.values(), room => roomCard(room, true)).join("")
    : '<p class="empty-state">Você ainda não tem salas. Cadastre o primeiro ambiente.</p>';
}

function clearDetails() {
  document.getElementById("roomStatistics").innerHTML = '<p class="empty-state">Nenhuma sala disponível. Cadastre um ambiente.</p>';
  document.getElementById("roomName").textContent = "Nenhuma sala cadastrada";
  ["roomDescription", "roomLocation", "roomSource", "roomLimits", "roomHistoryContext"].forEach(id => { document.getElementById(id).textContent = ""; });
  document.getElementById("roomAlertsTable").innerHTML = '<tr><td colspan="5">Sem dados disponíveis.</td></tr>';
  document.getElementById("roomSeriesTable").replaceChildren();
  updateMetrics({ status: "sem_dados", latest_reading: null, recommendations: ["Cadastre uma sala para começar."] });
  updateTable([]);
  updateSummary({ total_readings: 0 });
  updateChart([]);
  drawHistory("roomTemperatureChart", [], "temperature", "°C", "#0f766e");
  drawHistory("roomHumidityChart", [], "humidity", "%", "#2563eb");
}

async function refreshRoomDetails() {
  const room = selectedRoom();
  const version = ++detailVersion;
  document.getElementById("editSelectedRoom").disabled = !room;
  if (!room) { clearDetails(); return; }
  document.getElementById("roomName").textContent = room.name;
  document.getElementById("roomDescription").textContent = room.description || room.location;
  document.getElementById("roomLocation").innerHTML = `${icon("map-pin")}<span>${escapeHtml(locationDescription(room))}</span>`;
  document.getElementById("roomLimits").textContent = `Limites: ${formatValue(room.temperature_min)}–${formatValue(room.temperature_max)} °C · Umidade: ${formatValue(room.humidity_min)}–${formatValue(room.humidity_max)}%`;
  document.getElementById("roomHistoryContext").textContent = "Carregando histórico…";
  try {
    const payload = await fetchJson(`/api/rooms/${room.id}/dashboard?days=${document.getElementById("detailPeriod").value}`);
    if (version !== detailVersion || selectedRoom()?.id !== room.id) return;
    const stat = payload.statistics;
    const actualSource = payload.latest_reading?.data_source;
    document.getElementById("roomSource").textContent = `Origem configurada: ${sourceLabel(room.data_source)}. Última leitura: ${payload.latest_reading ? sourceLabel(actualSource) : "indisponível"}.${payload.stale ? " Atenção: última leitura há mais de 30 minutos." : ""}${actualSource === "external_api" ? " Referência meteorológica externa; não representa medição interna." : ""}`;
    document.getElementById("roomStatistics").innerHTML = [
      metric("Temperatura média", formatValue(stat?.temperature_avg), " °C", `Mín. ${formatValue(stat?.temperature_min)} · Máx. ${formatValue(stat?.temperature_max)} °C`),
      metric("Umidade média", formatValue(stat?.humidity_avg), " %", `Mín. ${formatValue(stat?.humidity_min)} · Máx. ${formatValue(stat?.humidity_max)}%`),
      metric("Leituras no período", integerFormat.format(stat?.count || 0)),
      metric("Alertas no período", integerFormat.format(stat?.alerts || 0)),
    ].join("");
    document.getElementById("roomHistoryContext").textContent = stat ? `${formatDate(payload.start)} a ${formatDate(payload.end)}. Gráficos mostram médias em intervalos de ${Math.round(payload.bucket_seconds / 60)} minuto(s); lacunas não são preenchidas. ${sourceDescription(payload.sources)}.` : "Dados indisponíveis no período selecionado. Nenhuma medição foi criada para completar os gráficos.";
    drawHistory("roomTemperatureChart", payload.series, "temperature", "°C", "#0f766e");
    drawHistory("roomHumidityChart", payload.series, "humidity", "%", "#2563eb");
    document.getElementById("roomSeriesTable").innerHTML = payload.series.length ? payload.series.map(point => `<tr><td>${formatDate(point.at)}</td><td>${formatValue(point.temperature)} °C</td><td>${formatValue(point.humidity)}%</td><td>${point.count}</td></tr>`).join("") : '<tr><td colspan="4">Sem histórico no período.</td></tr>';
    document.getElementById("roomAlertsTable").innerHTML = payload.alerts.length ? payload.alerts.map(reading => `<tr><td>${formatDate(reading.created_at)}</td><td>${renderStatusBadge(reading.air_quality_status)}</td><td>${formatValue(reading.temperature)} °C</td><td>${formatValue(reading.humidity)}%</td><td>${sourceLabel(reading.data_source)}</td></tr>`).join("") : '<tr><td colspan="5">Nenhum alerta registrado no período.</td></tr>';
    // Use the current room limits for its live status; historical alerts retain their original classification.
    updateMetrics({ status: payload.status, latest_reading: payload.latest_reading, recommendations: [payload.stale ? "Leitura desatualizada. Verifique a origem dos dados." : "Limites específicos da sala aplicados ao status atual."] });
  } catch (error) {
    if (version !== detailVersion) return;
    document.getElementById("roomHistoryContext").textContent = `Falha ao consultar o período: ${error.message}`;
    document.getElementById("roomStatistics").innerHTML = '<p class="form-error">Não foi possível carregar as estatísticas.</p>';
    drawHistory("roomTemperatureChart", [], "temperature", "°C", "#0f766e");
    drawHistory("roomHumidityChart", [], "humidity", "%", "#2563eb");
    document.getElementById("roomAlertsTable").innerHTML = '<tr><td colspan="5">Falha ao carregar alertas.</td></tr>';
    document.getElementById("roomSeriesTable").replaceChildren();
  }
}

function drawHistory(id, series, field, unit, color, hoverIndex = null, secondaryField = null) {
  chartStates.set(id, { series, field, unit, color, secondaryField });
  const canvas = document.getElementById(id), context = canvas.getContext("2d");
  const { width, height } = prepareCanvas(canvas, context);
  const output = document.getElementById(`${id}Tooltip`);
  output.textContent = "";
  context.font = "13px sans-serif";
  if (!series.length) {
    context.fillStyle = "#526173";
    context.fillText("Sem histórico no período selecionado.", 14, 36);
    return;
  }
  const padding = { left: 48, right: 20, top: 20, bottom: 36 };
  const plotWidth = Math.max(1, width - padding.left - padding.right), plotHeight = height - padding.top - padding.bottom;
  const values = series.flatMap(point => secondaryField ? [point[field], point[secondaryField]] : [point[field]]);
  const min = secondaryField ? 0 : Math.min(...values) - 1, max = Math.max(...values) + 1;
  const first = new Date(series[0].at).getTime(), last = new Date(series.at(-1).at).getTime();
  const points = series.map((point, index) => ({
    x: padding.left + ((new Date(point.at).getTime() - first) / (last - first || 1)) * plotWidth,
    y: padding.top + plotHeight * (1 - (point[field] - min) / (max - min)),
  }));
  context.strokeStyle = "#dfe6ef";
  context.fillStyle = "#526173";
  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + plotHeight * index / 4;
    context.beginPath(); context.moveTo(padding.left, y); context.lineTo(width - padding.right, y); context.stroke();
    context.fillText(formatValue(max - (max - min) * index / 4), 4, y + 4);
  }
  context.fillText(new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: DASHBOARD_TIME_ZONE }).format(new Date(series[0].at)), padding.left, height - 10);
  if (width > 320) context.fillText(new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: DASHBOARD_TIME_ZONE }).format(new Date(series.at(-1).at)), width - 140, height - 10);
  context.strokeStyle = color; context.lineWidth = 2;
  context.beginPath();
  points.forEach((point, index) => { if (index === 0) context.moveTo(point.x, point.y); else context.lineTo(point.x, point.y); });
  context.stroke();
  if (secondaryField) {
    context.strokeStyle = "#b91c1c";
    context.beginPath();
    series.forEach((point, index) => {
      const y = padding.top + plotHeight * (1 - (point[secondaryField] - min) / (max - min));
      if (index === 0) context.moveTo(points[index].x, y); else context.lineTo(points[index].x, y);
    });
    context.stroke();
  }
  const index = hoverIndex === null ? series.length - 1 : Math.max(0, Math.min(series.length - 1, hoverIndex));
  const point = points[index];
  context.fillStyle = color; context.beginPath(); context.arc(point.x, point.y, 4, 0, Math.PI * 2); context.fill();
  output.textContent = `${formatDate(series[index].at)} · ${secondaryField ? `Alertas: ${series[index][field]} · Críticos: ${series[index][secondaryField]}` : `${formatValue(series[index][field])} ${unit}`} · ${series[index].count} leitura(s)${series[index].room_count ? ` em ${series[index].room_count} sala(s)` : ""}. Use o cursor ou as setas para explorar.`;
  canvas.dataset.index = index;
}

function comparisonBars(items, field, title, unit, color) {
  const values = items.filter(item => item.statistics).map(item => item.statistics[field]);
  const min = Math.min(0, ...values), max = Math.max(1, ...values), range = max - min;
  const zero = -min / range * 100;
  return `<section class="chart-section"><h2>${title}</h2>${items.map(item => {
    if (!item.statistics) return `<div class="compare-row"><span>${escapeHtml(item.room.name)}</span><small>Sem dados no período</small></div>`;
    const value = item.statistics[field], percent = (value - min) / range * 100;
    return `<div class="compare-row"><span>${escapeHtml(item.room.name)}</span><div class="compare-track" aria-hidden="true"><span style="left:${Math.min(zero, percent)}%;width:${Math.max(0.4, Math.abs(percent - zero))}%;background:${color}"></span></div><strong>${formatValue(value)} ${unit}</strong></div>`;
  }).join("")}</section>`;
}

async function refreshComparison() {
  const version = ++comparisonVersion;
  document.getElementById("comparisonContext").textContent = "Carregando comparação…";
  try {
    const payload = await fetchJson(`/api/rooms/comparison?days=${document.getElementById("comparisonPeriod").value}`);
    if (version !== comparisonVersion) return;
    document.getElementById("comparisonContext").textContent = `${formatDate(payload.start)} a ${formatDate(payload.end)}. Todas as salas cadastradas participam; a origem de cada conjunto é indicada na tabela. Dados meteorológicos podem compartilhar a mesma origem e não são medições internas independentes. Contagens refletem ocorrências registradas, não a duração dos alertas.`;
    document.getElementById("comparisonCharts").innerHTML = payload.rooms.length ? comparisonBars(payload.rooms, "temperature_avg", "Temperatura média", "°C", "#0f766e") + comparisonBars(payload.rooms, "humidity_avg", "Umidade média", "%", "#2563eb") : '<p class="empty-state">Cadastre salas para compará-las.</p>';
    document.getElementById("comparisonTable").innerHTML = payload.rooms.length ? payload.rooms.map(item => {
      const stat = item.statistics;
      return `<tr><th scope="row">${escapeHtml(item.room.name)}</th><td>${escapeHtml(sourceDescription(item.sources))}</td><td>${formatValue(stat?.temperature_avg)} °C</td><td>${formatValue(stat?.temperature_min)} °C</td><td>${formatValue(stat?.temperature_max)} °C</td><td>${formatValue(stat?.humidity_avg)}%</td><td>${stat ? integerFormat.format(stat.alerts) : "--"}</td><td>${stat ? integerFormat.format(stat.count) : "--"}</td></tr>`;
    }).join("") : '<tr><td colspan="8">Nenhuma sala cadastrada.</td></tr>';
  } catch (error) {
    if (version !== comparisonVersion) return;
    document.getElementById("comparisonContext").textContent = `Não foi possível comparar os ambientes: ${error.message}`;
    document.getElementById("comparisonCharts").replaceChildren();
    document.getElementById("comparisonTable").innerHTML = '<tr><td colspan="8">Falha ao carregar comparação.</td></tr>';
  }
}

function findRoom(id) { return Array.from(rooms.values()).find(room => room.id === id); }

function openRoomForm(room = null) {
  const form = document.getElementById("roomForm");
  form.reset();
  const fields = { Id: "id", Name: "name", Location: "location", Identifier: "identifier", City: "city", State: "state", InternalLocation: "internal_location", Description: "description", Device: "device_id", Source: "data_source", TempMin: "temperature_min", TempMax: "temperature_max", HumidityMin: "humidity_min", HumidityMax: "humidity_max" };
  Object.entries(fields).forEach(([suffix, field]) => {
    if (room) document.getElementById(`roomForm${suffix}`).value = room[field] ?? "";
  });
  document.getElementById("roomFormId").value = room?.id || "";
  document.getElementById("roomFormDevice").readOnly = false;
  document.getElementById("roomFormApiUrl").value = room?.source_config?.external_api_url || "";
  document.getElementById("roomFormNotes").value = room?.source_config?.notes || "";
  document.getElementById("roomDialogTitle").textContent = room ? `Editar ${room.name}` : "Nova sala";
  document.getElementById("roomFormError").textContent = "";
  document.getElementById("roomDialog").showModal();
  document.getElementById("roomFormName").focus();
}

async function mutateRoom(url, method, payload) {
  const response = await fetch(url, { method, headers: authenticatedHeaders({ "Content-Type": "application/json" }), ...(payload ? { body: JSON.stringify(payload) } : {}) });
  if (response.status === 401) { redirectToLogin(); throw new Error("Sessão expirada"); }
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(Array.isArray(data?.detail) ? data.detail.map(error => error.msg).join("; ") : data?.detail || "Não foi possível salvar a sala");
  return data;
}

async function reloadRoomViews() {
  await loadRooms();
  renderManagement();
  await refreshOverview();
  const viewId = document.querySelector(".view.active").id;
  if (viewId === "comparisonView") await refreshComparison();
  if (viewId === "generalView") { await refreshDashboard(); await refreshRoomDetails(); }
  if (!rooms.size) { clearDetails(); switchView("overviewView"); }
}

document.getElementById("roomForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = document.getElementById("saveRoomButton");
  button.disabled = true;
  document.getElementById("roomFormError").textContent = "";
  const value = suffix => document.getElementById(`roomForm${suffix}`).value.trim();
  const id = value("Id");
  const payload = {
    name: value("Name"), location: value("Location"), description: value("Description"), device_id: value("Device"),
    identifier: value("Identifier"), city: value("City"), state: value("State"), internal_location: value("InternalLocation"),
    data_source: value("Source"), temperature_min: Number(value("TempMin")), temperature_max: Number(value("TempMax")),
    humidity_min: Number(value("HumidityMin")), humidity_max: Number(value("HumidityMax")),
    source_config: { external_api_url: value("ApiUrl") || null, notes: value("Notes") },
  };
  try {
    await mutateRoom(id ? `/api/rooms/${id}` : "/api/rooms", id ? "PUT" : "POST", payload);
    document.getElementById("roomDialog").close();
    notify(id ? "Configurações da sala atualizadas." : "Sala cadastrada. Ela já aparece nos dashboards; aguardando suas primeiras leituras.");
    await reloadRoomViews();
  } catch (error) {
    const dialog = document.getElementById("roomDialog");
    if (dialog.open) document.getElementById("roomFormError").textContent = error.message;
    else notify(`Sala salva, mas houve falha ao atualizar a tela: ${error.message}`, true);
  } finally { button.disabled = false; }
});

document.getElementById("closeRoomDialog").addEventListener("click", () => document.getElementById("roomDialog").close());
document.getElementById("editSelectedRoom").addEventListener("click", () => { if (selectedRoom()) openRoomForm(selectedRoom()); });
document.getElementById("detailPeriod").addEventListener("change", refreshRoomDetails);
document.getElementById("comparisonPeriod").addEventListener("change", refreshComparison);
document.getElementById("overviewRoomFilter").addEventListener("change", refreshOverviewCharts);
document.getElementById("applyOverviewPeriod").addEventListener("click", refreshOverviewCharts);
document.getElementById("overviewPeriod").addEventListener("change", () => {
  const custom = document.getElementById("overviewPeriod").value === "custom";
  document.getElementById("overviewCustomRange").hidden = !custom;
  refreshOverviewCharts();
});

document.addEventListener("click", async event => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.action === "create-room") openRoomForm();
  if (button.dataset.action === "back-overview") switchView("overviewView");
  if (button.dataset.action === "room-alerts") switchView("alertsView");
  if (button.dataset.action === "room-costs") switchView("costsView");
  if (button.dataset.openRoom) {
    const room = findRoom(button.dataset.openRoom);
    if (room) { roomSelect.value = room.device_id; roomSelect.dispatchEvent(new Event("change")); }
  }
  if (button.dataset.editRoom) openRoomForm(findRoom(button.dataset.editRoom));
  if (button.dataset.deleteRoom) {
    const room = findRoom(button.dataset.deleteRoom);
    if (!room || !window.confirm(`Excluir “${room.name}” do monitoramento? O histórico será preservado para auditoria. As outras salas não serão afetadas.`)) return;
    button.disabled = true;
    try {
      await mutateRoom(`/api/rooms/${room.id}?confirm=true`, "DELETE");
      detailVersion += 1; dashboardRequestId += 1;
      notify("Sala excluída do monitoramento. Histórico preservado.");
      await reloadRoomViews();
    } catch (error) { notify(error.message, true); button.disabled = false; }
  }
});

for (const id of ["roomTemperatureChart", "roomHumidityChart", "overviewTemperatureChart", "overviewHumidityChart", "overviewEventsChart"]) {
  const canvas = document.getElementById(id);
  canvas.addEventListener("mousemove", event => {
    const state = chartStates.get(id);
    if (!state?.series.length) return;
    const ratio = Math.max(0, Math.min(1, (event.clientX - canvas.getBoundingClientRect().left - 48) / Math.max(1, canvas.clientWidth - 68)));
    const start = new Date(state.series[0].at).getTime(), end = new Date(state.series.at(-1).at).getTime();
    const target = start + ratio * (end - start);
    let index = 0;
    state.series.forEach((point, candidate) => { if (Math.abs(new Date(point.at).getTime() - target) < Math.abs(new Date(state.series[index].at).getTime() - target)) index = candidate; });
    drawHistory(id, state.series, state.field, state.unit, state.color, index, state.secondaryField);
  });
  canvas.addEventListener("keydown", event => {
    const state = chartStates.get(id);
    if (!state?.series.length || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    drawHistory(id, state.series, state.field, state.unit, state.color, Number(canvas.dataset.index || 0) + (event.key === "ArrowRight" ? 1 : -1), state.secondaryField);
  });
}

function refreshRoomsView(viewId) {
  const room = selectedRoom();
  window.history.replaceState({}, "", viewId === "generalView" && room ? `/rooms/${room.id}` : "/dashboard");
  if (viewId === "overviewView") refreshOverview();
  if (viewId === "roomsView") renderManagement();
  if (viewId === "generalView") refreshRoomDetails();
  if (viewId === "comparisonView") refreshComparison();
  if (viewId === "costsView" && typeof refreshCostsView === "function") refreshCostsView();
}

window.addEventListener("resize", () => {
  chartStates.forEach((state, id) => {
    if (document.getElementById(id).closest(".view").classList.contains("active")) {
      drawHistory(id, state.series, state.field, state.unit, state.color, null, state.secondaryField);
    }
  });
});

async function startRoomDashboards() {
  if (!getAccessToken()) { redirectToLogin(); return; }
  try {
    const defaultPeriod = getDefaultPeriod();
    document.getElementById("overviewStart").value = formatDateTimeLocal(defaultPeriod.start);
    document.getElementById("overviewEnd").value = formatDateTimeLocal(defaultPeriod.end);
    await loadRooms();
    const initialRoom = findRoom(document.body.dataset.initialRoomId);
    if (initialRoom) { roomSelect.value = initialRoom.device_id; syncRoomFilters(); }
    await setDefaultFilters();
    renderManagement();
    if (initialRoom) switchView("generalView");
    else await refreshOverview();
  } catch (error) {
    notify(`Não foi possível carregar as salas: ${error.message}. Recarregue a página para tentar novamente.`, true);
    document.getElementById("roomCards").innerHTML = '<p class="form-error">Falha ao carregar ambientes.</p>';
  }
}

startRoomDashboards();
setInterval(async () => {
  if (document.hidden || document.getElementById("roomDialog").open) return;
  try {
    await loadRooms();
    const viewId = document.querySelector(".view.active").id;
    if (viewId === "generalView") await refreshDashboard();
    refreshRoomsView(viewId);
  } catch (error) { notify(`Falha ao atualizar: ${error.message}`, true); }
}, 15000);
