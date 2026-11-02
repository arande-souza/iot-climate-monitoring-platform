const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const energyFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });
const costState = { roomId: null, version: 0, compareVersion: 0, scenarios: [], selected: new Set(), current: null, charts: [], busy: false };
Object.assign(costState, { climate: null, climateVersion: 0, previewVersion: 0, previewTimer: null, portfolio: [], portfolioSelection: new Map(), autoSummary: false });
const costFields = { name: "costName", equipment_model: "costModel", cooling_capacity_btu_h: "costCapacity",
  method: "costMethod", average_power_kw: "costPower", equipment_price: "costPrice", installation_cost: "costInstallation",
  maintenance_cost: "costMaintenance", maintenance_interval_months: "costMaintenanceInterval",
  hours_per_day: "costHours", days_per_month: "costDays", tariff_per_kwh: "costTariff", label_energy_kwh: "costLabelEnergy",
  label_reference_hours: "costLabelHours", label_period: "costLabelPeriod", parameter_source: "costSource", notes: "costNotes" };
const money = value => moneyFormat.format(Number(value));

function costMessage(message, error = false) {
  const node = document.getElementById("costNotice");
  node.textContent = message;
  node.classList.toggle("form-error", error);
}

function syncCostMethod() {
  const label = document.getElementById("costMethod").value === "label";
  const fields = document.getElementById("costLabelFields");
  fields.hidden = !label; fields.disabled = !label;
  document.getElementById("costPower").required = !label;
  document.getElementById("costPowerLabel").textContent = label ? "Potência média em kW (opcional neste método)" : "Potência elétrica média estimada (kW)";
  document.getElementById("costPowerHelp").textContent = label ? "Apenas para registro. O cálculo usa o consumo e as horas de referência da etiqueta." : "Informe uma potência média, não a capacidade em BTU/h. 1 kW = 1.000 W.";
  document.getElementById("costSource").required = label;
}

function resetCostForm() {
  costState.autoSummary = false;
  clearTimeout(costState.previewTimer); costState.previewVersion++; costState.compareVersion++;
  document.getElementById("costForm").reset();
  document.getElementById("costScenarioId").value = "";
  document.getElementById("costFormTitle").textContent = "Novo cenário";
  document.getElementById("costFormError").textContent = "";
  document.getElementById("costResults").hidden = false;
  document.getElementById("costResultMetrics").innerHTML = ["Investimento inicial", "Custo mensal de energia", "Custo anual de energia", "Total em 36 meses"].map(label => metric(label, "—", "", "Preencha os parâmetros para calcular", "wallet")).join("");
  document.getElementById("costProjectionTable").innerHTML = '<tr><td colspan="4">Nenhuma estimativa calculada. Informe os parâmetros acima ou edite um cenário salvo.</td></tr>';
  document.getElementById("costCalculationMethod").textContent = "";
  document.getElementById("costChartsPanel").hidden = true;
  document.getElementById("exportCurrentCost").disabled = true;
  costState.current = null; costState.charts = [];
  renderCostSummaryOptions();
  clearCostComparison(); renderCostAnalysis(); renderCostComposition(); updateCostExport();
  syncCostMethod();
}

function costPayload() {
  const payload = { room_id: selectedRoom().id };
  Object.entries(costFields).forEach(([field, id]) => {
    const value = document.getElementById(id).value.trim();
    payload[field] = ["cooling_capacity_btu_h", "days_per_month", "maintenance_interval_months"].includes(field) ? (value === "" ? null : Number(value)) : value;
  });
  ["average_power_kw", "label_energy_kwh", "label_reference_hours", "label_period", "maintenance_cost"].forEach(field => { if (payload[field] === "") payload[field] = null; });
  if (payload.method === "power") { payload.label_energy_kwh = null; payload.label_reference_hours = null; payload.label_period = null; }
  return payload;
}

function renderCostList() {
  document.getElementById("costScenarioTable").innerHTML = costState.scenarios.length ? costState.scenarios.map(item => `
    <tr><td><input type="checkbox" data-cost-select="${item.id}" aria-label="Selecionar ${escapeHtml(item.parameters.name)}" ${costState.selected.has(item.id) ? "checked" : ""} /></td>
    <td>${escapeHtml(item.parameters.name)}<small>${escapeHtml(item.parameters.equipment_model)} · ${integerFormat.format(item.parameters.cooling_capacity_btu_h)} BTU/h</small></td>
    <td>${energyFormat.format(Number(item.results.monthly_energy_kwh))} kWh</td><td>${money(item.results.monthly_cost)}</td><td>${money(item.results.initial_investment)}</td>
    <td><div class="room-actions"><button type="button" class="secondary-action" data-cost-edit="${item.id}">Editar</button><button type="button" class="danger-action" data-cost-delete="${item.id}">Excluir</button></div></td></tr>`).join("")
    : '<tr><td colspan="6">Nenhum cenário salvo nesta sala. Informe seus parâmetros para começar.</td></tr>';
  document.getElementById("compareCosts").disabled = costState.selected.size !== 2 || costState.busy;
  document.getElementById("exportCostSelection").disabled = !costState.selected.size || costState.busy;
  updateCostExport();
}

async function loadCostScenarios() {
  const roomId = costState.roomId, version = costState.version;
  const rows = await fetchJson(`/api/costs/scenarios?room_id=${encodeURIComponent(roomId)}`);
  if (roomId !== costState.roomId || version !== costState.version) return;
  costState.scenarios = rows;
  costState.selected = new Set([...costState.selected].filter(id => rows.some(row => row.id === id)));
  renderCostSummaryOptions();
  if (costState.autoSummary && rows.length && !costState.busy) {
    const rank = scenario => {
      const reference = scenario.parameters.name.match(/\b(\d{2})\/(\d{4})\b/);
      return reference ? `${reference[2]}-${reference[1]}` : (scenario.updated_at || scenario.created_at || "");
    };
    const latest = [...rows].sort((a, b) => rank(b).localeCompare(rank(a)) || b.id.localeCompare(a.id))[0];
    showCostResults(latest);
    costState.autoSummary = false;
  }
  renderCostList();
}

async function refreshCostsView() {
  const room = selectedRoom();
  const roomId = room?.id || null;
  if (costState.roomId !== roomId) {
    costState.version += 1; costState.roomId = roomId;
    costState.scenarios = []; costState.selected.clear(); resetCostForm(); renderCostList();
    costState.autoSummary = true;
    costState.climate = null;
  }
  document.getElementById("costSelectedRoom").textContent = room ? `${room.name} · ${locationDescription(room)}` : "Nenhuma sala cadastrada";
  document.getElementById("newCostScenario").disabled = !room;
  document.getElementById("calculateCost").disabled = !room || costState.busy;
  document.getElementById("saveCostScenario").disabled = !room || costState.busy;
  if (!room) {
    document.getElementById("costClimateContext").textContent = "Nenhuma sala cadastrada. Cadastre um ambiente antes de criar cenários.";
    document.getElementById("costClimateMetrics").innerHTML = "";
    document.getElementById("costClimateCoverage").textContent = "";
    document.getElementById("costClimateMethod").textContent = "";
    costState.climate = null; renderCostAnalysis();
    return;
  }
  const version = costState.version;
  try {
    await Promise.all([loadCostClimate(), loadCostScenarios(), loadCostPortfolio()]);
    if (room.id !== costState.roomId || version !== costState.version) return;
  } catch (error) { if (version === costState.version) costMessage(`Não foi possível carregar os dados desta sala: ${error.message}`, true); }
}

function showCostResults(scenario) {
  costState.current = scenario;
  document.getElementById("costResults").hidden = false;
  const result = scenario.results;
  document.getElementById("costResultMetrics").innerHTML = [
    metric("Investimento inicial", money(result.initial_investment), "", "Equipamento + instalação", "calculator"),
    metric("Custo mensal de energia", money(result.monthly_cost), "", "Estimativa de energia no mês", "energy"),
    metric("Custo anual de energia", money(result.annual_cost), "", "Estimativa de 12 meses de energia", "chart"),
    metric("Total em 36 meses", money(result.projections[2].total_cost), "", result.maintenance_informed ? "Investimento + energia + manutenção" : "Manutenção não informada", "chart"),
    metric("Consumo mensal estimado", energyFormat.format(Number(result.monthly_energy_kwh)), " kWh", "Não é medição elétrica", "energy"),
    metric("Aquisição", money(result.equipment_cost), "", "Preço informado", "wallet"),
    metric("Instalação", money(result.installation_cost), "", "Custo informado", "chip"),
    metric("Manutenção anual prevista", result.maintenance_informed ? money(result.annual_maintenance_cost) : "Não informada", "", "Cronograma informado, sem rateio", "calculator"),
  ].join("");
  renderCostSummaryOptions();
  document.getElementById("costProjectionTable").innerHTML = result.projections.map(row => `<tr><th scope="row">${row.months} meses</th><td>${money(row.energy_cost)}</td><td>${row.maintenance_cost === null ? "Não informada" : money(row.maintenance_cost)}</td><td>${money(row.total_cost)}</td></tr>`).join("");
  document.getElementById("costCalculationMethod").textContent = `${result.formulas[0]}. Uso mensal informado: ${energyFormat.format(Number(result.monthly_hours))} horas. Valores arredondados somente na apresentação.`;
  document.getElementById("costMethodology").innerHTML = `<h3>Fórmulas aplicadas</h3><ul>${result.formulas.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul><h3>Limitações</h3><ul>${result.limitations.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul><p>Metodologia ${escapeHtml(result.methodology_version)} · <a href="${result.reference_url}" target="_blank" rel="noopener noreferrer">Etiqueta de eficiência — Inmetro</a></p>`;
  document.getElementById("exportCurrentCost").disabled = !scenario.id;
  costState.charts = [scenario];
  clearCostComparison();
  document.getElementById("costComparisonContext").textContent = `Cenário: ${scenario.parameters.name}. Uso e tarifa constantes. O custo acumulado inclui o investimento desde o mês zero.`;
  drawCostProjections();
  renderCostAnalysis(); updateCostExport();
}

async function calculateOrSaveCost(save) {
  const form = document.getElementById("costForm");
  if (!selectedRoom() || costState.busy || !form.reportValidity()) return;
  clearTimeout(costState.previewTimer); costState.previewVersion++;
  const roomId = selectedRoom().id, version = costState.version;
  const id = document.getElementById("costScenarioId").value;
  costState.busy = true;
  form.querySelectorAll("input, select, textarea, button").forEach(node => { node.disabled = true; });
  document.getElementById("newCostScenario").disabled = true;
  document.getElementById("calculateCost").disabled = true;
  document.getElementById("saveCostScenario").disabled = true;
  document.getElementById("costFormError").textContent = "";
  costMessage(save ? "Salvando cenário…" : "Calculando estimativa…");
  try {
    const url = save ? `/api/costs/scenarios${id ? `/${id}` : ""}` : "/api/costs/estimate";
    const result = await mutateRoom(url, save && id ? "PUT" : "POST", costPayload());
    if (roomId !== costState.roomId || version !== costState.version) return;
    if (save) {
      document.getElementById("costScenarioId").value = result.id;
      document.getElementById("costFormTitle").textContent = `Editar cenário: ${result.parameters.name}`;
      if (costState.selected.size < 2) costState.selected.add(result.id);
      await loadCostScenarios();
      await loadCostPortfolio();
    }
    showCostResults(result);
    costMessage(save ? "Cenário salvo. Selecione dois cenários na tabela para comparar." : "Estimativa calculada. Salve o cenário para poder exportá-lo e compará-lo.");
  } catch (error) { if (roomId === costState.roomId) document.getElementById("costFormError").textContent = error.message; }
  finally {
    costState.busy = false;
    form.querySelectorAll("input, select, textarea, button").forEach(node => { node.disabled = false; });
    syncCostMethod();
    document.getElementById("newCostScenario").disabled = !selectedRoom();
    document.getElementById("calculateCost").disabled = !selectedRoom();
    document.getElementById("saveCostScenario").disabled = !selectedRoom();
    renderCostList();
  }
}

function exportCostReport(ids) {
  if (!ids.length) return;
  try { startBrowserDownload(`/api/costs/report?${costReportParams(ids)}`); }
  catch (error) { costMessage(error.message, true); }
}

function drawCostProjections(hoverMonth = null) {
  if (!costState.charts.length) return;
  const months = Number(document.getElementById("costHorizon").value);
  document.getElementById("costChartsPanel").hidden = false;
  document.getElementById("costChartTitle").textContent = `Projeções estimadas em ${months} meses`;
  const colors = ["#0f766e", "#2563eb"];
  document.getElementById("costChartLegend").innerHTML = costState.charts.map((item, index) => `<span style="--series-color:${colors[index]}">${escapeHtml(item.parameters.name)}</span>`).join("");
  for (const [id, field] of [["costMonthlyChart", "energy_cost"], ["costCumulativeChart", "total_cost"]]) {
    const canvas = document.getElementById(id), context = canvas.getContext("2d");
    const { width, height } = prepareCanvas(canvas, context);
    const start = field === "energy_cost" ? 1 : 0;
    const maximum = Math.max(1, ...costState.charts.flatMap(item => item.results.series.slice(start, months + 1).map(point => Number(point[field])))) * 1.1;
    const left = 72, right = 16, top = 18, bottom = 32;
    const plotWidth = Math.max(1, width - left - right), plotHeight = height - top - bottom;
    context.font = "11px sans-serif"; context.fillStyle = "#526173"; context.setLineDash([]);
    const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
    for (let index = 0; index <= 4; index += 1) {
      const y = top + plotHeight * index / 4;
      context.strokeStyle = "#dfe6ef"; context.lineWidth = 1; context.beginPath(); context.moveTo(left, y); context.lineTo(width - right, y); context.stroke();
      context.fillText(`R$ ${compact.format(maximum * (1 - index / 4))}`, 3, y + 4);
    }
    const month = hoverMonth === null ? months : Math.max(start, Math.min(months, hoverMonth));
    costState.charts.forEach((scenario, index) => {
      context.strokeStyle = colors[index]; context.lineWidth = 2.5; context.setLineDash(index ? [6, 4] : []); context.beginPath();
      for (let current = start; current <= months; current += 1) {
        const x = left + plotWidth * (current - start) / (months - start);
        const y = top + plotHeight * (1 - Number(scenario.results.series[current][field]) / maximum);
        if (current === start) context.moveTo(x, y); else context.lineTo(x, y);
      }
      context.stroke(); context.fillStyle = colors[index]; context.beginPath();
      context.arc(left + plotWidth * (month - start) / (months - start), top + plotHeight * (1 - Number(scenario.results.series[month][field]) / maximum), 4, 0, Math.PI * 2); context.fill();
    });
    context.setLineDash([]);
    context.fillStyle = "#526173"; context.fillText(`Mês ${start}`, left, height - 8); context.fillText(`Mês ${months}`, width - 64, height - 8);
    document.getElementById(`${id}Tooltip`).textContent = `Mês ${month}: ${costState.charts.map(item => `${item.parameters.name}: ${money(item.results.series[month][field])}`).join(" · ")}. Estimativas; explore com o cursor ou as setas.`;
    canvas.dataset.month = month;
  }
  document.getElementById("costTimelineHeader").innerHTML = `<tr><th>Mês</th>${costState.charts.map(item => `<th>${escapeHtml(item.parameters.name)} · energia mensal</th><th>${escapeHtml(item.parameters.name)} · total acumulado</th>`).join("")}</tr>`;
  document.getElementById("costTimelineTable").innerHTML = Array.from({ length: months + 1 }, (_, month) => `<tr><th scope="row">${month}</th>${costState.charts.map(item => `<td>${money(item.results.series[month].energy_cost)}</td><td>${money(item.results.series[month].total_cost)}</td>`).join("")}</tr>`).join("");
  renderCostComposition(); renderCostPortfolio(); renderCostAnalysis();
}

document.getElementById("costForm").addEventListener("submit", event => { event.preventDefault(); calculateOrSaveCost(false); });
document.getElementById("saveCostScenario").addEventListener("click", () => calculateOrSaveCost(true));
document.getElementById("costForm").addEventListener("input", () => {
  costState.autoSummary = false;
  costState.previewVersion++; costState.compareVersion++;
  document.getElementById("costResults").hidden = false; document.getElementById("costChartsPanel").hidden = true;
  document.getElementById("costResultMetrics").innerHTML = ["Investimento inicial", "Custo mensal de energia", "Custo anual de energia", "Total em 36 meses"].map(label => metric(label, "—", "", "Aguardando parâmetros válidos para calcular", "wallet")).join("");
  document.getElementById("costProjectionTable").innerHTML = '<tr><td colspan="4">Complete os parâmetros para atualizar a estimativa.</td></tr>';
  document.getElementById("costCalculationMethod").textContent = "";
  costState.current = null; costState.charts = [];
  renderCostSummaryOptions();
  clearCostComparison(); renderCostAnalysis(); renderCostComposition(); updateCostExport();
  costMessage("Atualização automática: complete os campos obrigatórios para visualizar a estimativa.");
  clearTimeout(costState.previewTimer);
  costState.previewTimer = setTimeout(previewCostAutomatically, 450);
});
document.getElementById("costMethod").addEventListener("change", syncCostMethod);
document.getElementById("newCostScenario").addEventListener("click", () => { resetCostForm(); document.getElementById("costName").focus(); });
document.getElementById("cancelCostEdit").addEventListener("click", resetCostForm);
document.getElementById("costHorizon").addEventListener("change", () => {
  if (costState.charts.length === 2) compareCostSelection(); else drawCostProjections();
  renderCostPortfolio();
});
document.getElementById("exportCurrentCost").addEventListener("click", () => { if (costState.current?.id) exportCostReport([costState.current.id]); });
document.getElementById("exportCostSelection").addEventListener("click", () => exportCostReport([...costState.selected]));

async function compareCostSelection() {
  if (costState.selected.size !== 2 || costState.busy) return;
  clearTimeout(costState.previewTimer); costState.previewVersion++;
  const version = costState.version;
  const requestVersion = ++costState.compareVersion;
  const selectionKey = [...costState.selected].join(",");
  try {
    const result = await mutateRoom("/api/costs/compare", "POST", { scenario_ids: [...costState.selected], months: Number(document.getElementById("costHorizon").value), ...costComparisonBasis() });
    if (version !== costState.version || requestVersion !== costState.compareVersion
        || selectionKey !== [...costState.selected].join(",")
        || result.months !== Number(document.getElementById("costHorizon").value)) return;
    showCostResults(result.scenarios[0]);
    costState.charts = result.scenarios;
    document.getElementById("costCalculationMethod").textContent = `Resumo financeiro do cenário A: ${result.scenarios[0].parameters.name}, com as premissas desta comparação. ${result.comparison_basis.note}`;
    document.getElementById("costComparisonContext").textContent = `A: ${result.scenarios[0].parameters.name}. B: ${result.scenarios[1].parameters.name}. Diferença B − A em ${result.months} meses: ${money(result.difference_b_minus_a.total_cost)}. ${result.comparison_basis.note}`;
    const winner = result.scenarios.find(s => s.id === result.lowest_total_cost_scenario_id);
    document.getElementById("costWinner").textContent = `${winner ? `${winner.parameters.name}: menor custo total projetado.` : "Empate nos custos totais projetados."} ${result.interpretation}`;
    renderCostComparisonTable(result.scenarios); updateCostExport();
    drawCostProjections();
  } catch (error) { costMessage(error.message, true); }
}
document.getElementById("compareCosts").addEventListener("click", compareCostSelection);
document.addEventListener("change", event => {
  const id = event.target.dataset.costSelect;
  if (!id) return;
  if (event.target.checked && costState.selected.size >= 2) { event.target.checked = false; costMessage("Selecione no máximo dois cenários para comparação.", true); return; }
  if (event.target.checked) costState.selected.add(id); else costState.selected.delete(id);
  costState.compareVersion++;
  if (costState.charts.length === 2) { costState.charts = []; document.getElementById("costChartsPanel").hidden = true; clearCostComparison(); renderCostAnalysis(); renderCostComposition(); }
  renderCostList();
});
document.addEventListener("click", async event => {
  const button = event.target.closest("button"); if (!button) return;
  if (button.dataset.action === "cost-room-details") switchView("generalView");
  const editId = button.dataset.costEdit, deleteId = button.dataset.costDelete;
  if ((editId || deleteId) && costState.busy) return;
  if (editId) {
    const scenario = costState.scenarios.find(item => item.id === editId); if (!scenario) return;
    resetCostForm();
    Object.entries(costFields).forEach(([field, id]) => { document.getElementById(id).value = scenario.parameters[field] ?? ""; });
    document.getElementById("costScenarioId").value = scenario.id;
    document.getElementById("costFormTitle").textContent = `Editar cenário: ${scenario.parameters.name}`;
    syncCostMethod(); showCostResults(scenario); document.getElementById("costFormTitle").scrollIntoView({ block: "start" });
  }
  if (deleteId) {
    const scenario = costState.scenarios.find(item => item.id === deleteId);
    if (!scenario || !window.confirm(`Excluir o cenário “${scenario.parameters.name}”? A sala e suas leituras serão preservadas.`)) return;
    button.disabled = true;
    try {
      await mutateRoom(`/api/costs/scenarios/${deleteId}?confirm=true`, "DELETE");
      costState.selected.delete(deleteId);
      if (costState.current?.id === deleteId || document.getElementById("costScenarioId").value === deleteId) resetCostForm();
      else { costState.charts = []; document.getElementById("costChartsPanel").hidden = true; }
      clearCostComparison(); renderCostAnalysis(); renderCostComposition();
      await loadCostScenarios(); await loadCostPortfolio(); costMessage("Cenário excluído.");
    } catch (error) { costMessage(error.message, true); button.disabled = false; }
  }
});
for (const id of ["costMonthlyChart", "costCumulativeChart"]) {
  const canvas = document.getElementById(id);
  canvas.addEventListener("mousemove", event => {
    const months = Number(document.getElementById("costHorizon").value);
    const ratio = Math.max(0, Math.min(1, (event.clientX - canvas.getBoundingClientRect().left - 72) / Math.max(1, canvas.clientWidth - 88)));
    drawCostProjections(Math.round(ratio * months));
  });
  canvas.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault(); drawCostProjections(Number(canvas.dataset.month || 0) + (event.key === "ArrowRight" ? 1 : -1));
  });
}
window.addEventListener("resize", () => { if (document.getElementById("costsView").classList.contains("active")) drawCostProjections(); });
roomSelect.addEventListener("change", () => {
  if (document.getElementById("costsView").classList.contains("active")) refreshCostsView();
});
syncCostMethod();

function renderCostSummaryOptions() {
  const select = document.getElementById("costSummaryScenario");
  select.innerHTML = '<option value="">Prévia do formulário / selecione um cenário salvo</option>' + costState.scenarios.map(s => `<option value="${s.id}">${escapeHtml(s.parameters.name)}</option>`).join("");
  select.value = costState.current?.id || "";
  document.getElementById("costSummaryContext").textContent = costState.current
    ? `${costState.current.id ? "Cenário salvo" : "Prévia sem salvar"}: ${costState.current.parameters.name}. Valores estimados para esta alternativa.`
    : "Selecione um cenário salvo ou preencha os parâmetros do formulário para calcular.";
}

document.getElementById("costSummaryScenario").addEventListener("change", event => {
  const scenario = costState.scenarios.find(s => s.id === event.target.value);
  if (!scenario) return;
  clearTimeout(costState.previewTimer); costState.previewVersion++; costState.compareVersion++;
  costState.autoSummary = false;
  showCostResults(scenario);
});

function clearCostComparison() {
  document.getElementById("costWinner").textContent = "Selecione dois cenários para identificar o menor custo projetado.";
  document.getElementById("costCompareHeader").innerHTML = "";
  document.getElementById("costCompareTable").innerHTML = "";
}

async function previewCostAutomatically() {
  const form = document.getElementById("costForm"), room = selectedRoom();
  if (!room || costState.busy || !form.checkValidity()) return;
  const revision = ++costState.previewVersion, roomId = room.id;
  costMessage("Calculando estimativa…");
  try {
    const result = await mutateRoom("/api/costs/estimate", "POST", costPayload());
    if (revision !== costState.previewVersion || roomId !== costState.roomId) return;
    document.getElementById("costFormError").textContent = "";
    showCostResults(result);
    costMessage("Estimativa atualizada automaticamente. Use Salvar cenário para gravar os parâmetros.");
  } catch (error) {
    if (revision === costState.previewVersion && roomId === costState.roomId) document.getElementById("costFormError").textContent = error.message;
  }
}

function costComparisonBasis() {
  const tariff_mode = document.getElementById("costTariffMode").value;
  const input = document.getElementById("costCommonTariff");
  if (tariff_mode === "shared" && !input.checkValidity()) throw new Error("Informe uma tarifa comum válida.");
  return { tariff_mode, common_tariff_per_kwh: tariff_mode === "shared" && input.value !== "" ? input.value : null };
}

function costReportParams(ids) {
  const params = new URLSearchParams({ months: document.getElementById("costHorizon").value, days: document.getElementById("costClimateDays").value });
  ids.forEach(id => params.append("scenario_id", id));
  if (ids.length === 2) Object.entries(costComparisonBasis()).forEach(([key, value]) => { if (value !== null) params.set(key, value); });
  return params;
}

function costReportIds() {
  if (costState.charts.length === 2) return costState.charts.map(s => s.id);
  if (costState.current?.id) return [costState.current.id];
  return [...costState.selected];
}

function updateCostExport() {
  document.getElementById("exportCurrentCost").disabled = !costState.current?.id || costState.charts.length === 2;
  document.getElementById("printCostReport").disabled = !costReportIds().length;
  document.getElementById("printCostReport").textContent = costState.charts.length === 2 || !costState.current?.id ? "Relatório dos selecionados / PDF" : "Relatório do cenário atual / PDF";
}

document.getElementById("printCostReport").addEventListener("click", () => {
  try {
    const ids = costReportIds();
    if (ids.length) window.open(`/api/costs/report/print?${costReportParams(ids)}`, "_blank", "noopener");
  } catch (error) { costMessage(error.message, true); }
});

for (const id of ["costTariffMode", "costCommonTariff"]) {
  document.getElementById(id).addEventListener("change", () => {
    document.getElementById("costCommonTariff").disabled = document.getElementById("costTariffMode").value === "scenario";
    costState.compareVersion++;
    if (costState.selected.size === 2) compareCostSelection();
  });
}

function renderCostComparisonTable(scenarios) {
  const months = Number(document.getElementById("costHorizon").value);
  document.getElementById("costCompareHeader").innerHTML = `<tr><th>Indicador</th>${scenarios.map(s => `<th>${escapeHtml(s.parameters.name)}</th>`).join("")}</tr>`;
  const rows = [
    ["Equipamento", s => escapeHtml(s.parameters.equipment_model)],
    ["Capacidade de refrigeração", s => `${s.parameters.cooling_capacity_btu_h} BTU/h`],
    ["Potência média informada", s => s.parameters.average_power_kw === null ? "Não informada (método por etiqueta)" : `${energyFormat.format(Number(s.parameters.average_power_kw))} kW`],
    ["Método de consumo", s => s.parameters.method === "label" ? `Etiqueta: ${energyFormat.format(Number(s.parameters.label_energy_kwh))} kWh / ${s.parameters.label_reference_hours} horas de referência` : "Potência elétrica média estimada"],
    ["Aquisição", s => money(s.parameters.equipment_price)], ["Instalação", s => money(s.parameters.installation_cost)],
    ["Investimento inicial", s => money(s.results.initial_investment)],
    ["Uso", s => `${s.parameters.hours_per_day} h/dia · ${s.parameters.days_per_month} dias/mês`],
    ["Tarifa aplicada", s => `${energyFormat.format(Number(s.parameters.tariff_per_kwh))} R$/kWh`],
    ["Consumo mensal estimado", s => `${energyFormat.format(Number(s.results.monthly_energy_kwh))} kWh`],
    ["Energia mensal", s => money(s.results.monthly_cost)],
    ["Manutenção", s => s.results.maintenance_informed ? `${money(s.parameters.maintenance_cost)} a cada ${s.parameters.maintenance_interval_months} meses` : "Não informada"],
    [`Total em ${months} meses`, s => `<strong>${money(s.results.series[months].total_cost)}</strong>`],
  ];
  document.getElementById("costCompareTable").innerHTML = rows.map(([label, value]) => `<tr><th scope="row">${label}</th>${scenarios.map(s => `<td>${value(s)}</td>`).join("")}</tr>`).join("");
}

function renderCostComposition() {
  const panel = document.getElementById("costComposition"), months = Number(document.getElementById("costHorizon").value);
  panel.innerHTML = '<h2>Investimento e custos operacionais</h2>';
  if (!costState.charts.length) { panel.innerHTML += '<p class="muted">Calcule um cenário para visualizar a composição dos custos.</p>'; return; }
  panel.innerHTML += '<p class="muted">Aquisição e instalação no mês zero; energia e manutenção ao longo do horizonte selecionado.</p>';
  panel.innerHTML += costState.charts.map(s => {
    const r = s.results, row = r.series[months], total = Number(row.total_cost);
    const values = [r.equipment_cost, r.installation_cost, row.cumulative_energy_cost, row.cumulative_maintenance_cost];
    const labels = ["Aquisição", "Instalação", "Energia", "Manutenção"], colors = ["#12344d", "#2563eb", "#0f766e", "#a16207"];
    return `<article class="cost-breakdown"><h3>${escapeHtml(s.parameters.name)} · ${months} meses · ${money(total)}</h3><div class="cost-stacked-bar" role="img" aria-label="Composição do custo, valores discriminados abaixo">${values.map((v, i) => `<span style="width:${total ? Number(v || 0) / total * 100 : 0}%;background:${colors[i]}"></span>`).join("")}</div><dl class="cost-breakdown-values">${values.map((v, i) => `<div><dt>${labels[i]}</dt><dd>${v === null ? "Não informada" : money(v)}</dd></div>`).join("")}</dl></article>`;
  }).join("");
}

async function loadCostPortfolio() {
  const version = costState.version;
  const data = await fetchJson("/api/costs/portfolio");
  if (version !== costState.version) return;
  costState.portfolio = data;
  const options = document.getElementById("costPortfolioOptions");
  options.innerHTML = data.map(room => {
    const selected = costState.portfolioSelection.get(room.room_id);
    if (selected && !room.scenarios.some(s => s.id === selected)) costState.portfolioSelection.delete(room.room_id);
    return `<label>${escapeHtml(room.room_name)}<select data-cost-portfolio="${room.room_id}"><option value="">${room.scenarios.length ? "Não incluir / selecione um cenário" : "Sem cenários cadastrados"}</option>${room.scenarios.map(s => `<option value="${s.id}" ${costState.portfolioSelection.get(room.room_id) === s.id ? "selected" : ""}>${escapeHtml(s.parameters.name)}</option>`).join("")}</select></label>`;
  }).join("");
  renderCostPortfolio();
}

document.getElementById("costPortfolioOptions").addEventListener("change", event => {
  if (!event.target.dataset.costPortfolio) return;
  costState.portfolioSelection.set(event.target.dataset.costPortfolio, event.target.value); renderCostPortfolio();
});

function renderCostPortfolio() {
  const months = Number(document.getElementById("costHorizon").value);
  const rows = costState.portfolio.flatMap(room => {
    const scenario = room.scenarios.find(s => s.id === costState.portfolioSelection.get(room.room_id));
    return scenario ? [{ room, scenario, total: Number(scenario.results.series[months].total_cost) }] : [];
  });
  const maximum = Math.max(1, ...rows.map(r => r.total));
  document.getElementById("costPortfolioChart").innerHTML = rows.length ? `<p class="muted">Totais em ${months} meses, usando os parâmetros salvos de cada cenário, inclusive suas tarifas.</p>${rows.map(r => `<div class="cost-room-bar"><span>${escapeHtml(r.room.room_name)} · ${escapeHtml(r.scenario.parameters.name)}</span><strong>${money(r.total)}</strong><div><span style="width:${r.total / maximum * 100}%"></span></div></div>`).join("")}` : '<p class="muted">Selecione pelo menos um cenário acima para visualizar a distribuição. Nenhum custo é presumido para salas sem seleção.</p>';
}

async function loadCostClimate() {
  const room = selectedRoom(); if (!room) return;
  const revision = ++costState.climateVersion, days = document.getElementById("costClimateDays").value;
  costState.climate = null; renderCostAnalysis();
  document.getElementById("costClimateContext").textContent = `Carregando indicadores de ${room.name}…`;
  document.getElementById("costClimateMetrics").innerHTML = "";
  document.getElementById("costClimateCoverage").textContent = "";
  try {
    const c = await fetchJson(`/api/costs/context?room_id=${encodeURIComponent(room.id)}&days=${days}`);
    if (revision !== costState.climateVersion || room.id !== costState.roomId) return;
    costState.climate = c;
    const latest = c.latest_reading;
    document.getElementById("costClimateContext").textContent = `${room.name} · ${locationDescription(room)}. ${latest ? `Última leitura: ${formatValue(latest.temperature)} °C e ${formatValue(latest.humidity)}%, em ${formatDate(latest.created_at)}${c.stale ? " (desatualizada)" : ""}.` : "Nenhuma leitura disponível."} Período: ${formatDate(c.start)} a ${formatDate(c.end)}.`;
    document.getElementById("costClimateMetrics").innerHTML = [
      metric("Temperatura média", c.count ? formatValue(c.temperature_avg) : "—", " °C", `${c.count} leituras válidas`, "temperature"),
      metric("Umidade média", c.count ? formatValue(c.humidity_avg) : "—", "%", "Média no período selecionado", "droplet"),
      metric("Leituras em alerta", c.count ? integerFormat.format(c.alerts) : "—", "", "Classificação histórica", "alert"),
      metric("Leituras críticas", c.count ? integerFormat.format(c.critical) : "—", "", "Classificação histórica", "bell"),
      metric("Tempo fora dos limites", c.outside_seconds === null ? "Não calculável" : `${formatValue(c.outside_seconds / 3600)} h`, "", "Estimativa nos intervalos cobertos", "chart"),
    ].join("");
    document.getElementById("costClimateCoverage").textContent = `Cobertura temporal: ${formatValue(c.coverage_percent)}%. Sem cobertura: ${formatValue(c.unknown_seconds / 3600)} h. ${c.excluded_count} leituras inválidas ou referências externas excluídas. ${c.count ? "" : "Sem dados válidos no período."}`;
    document.getElementById("costClimateMethod").textContent = c.methodology;
    renderCostAnalysis();
  } catch (error) {
    if (revision === costState.climateVersion) {
      document.getElementById("costClimateContext").textContent = `Não foi possível carregar os indicadores: ${error.message}`;
      document.getElementById("costClimateMethod").textContent = ""; renderCostAnalysis();
    }
  }
}

document.getElementById("costClimateDays").addEventListener("change", loadCostClimate);

function renderCostAnalysis() {
  const node = document.getElementById("costAnalysis"), c = costState.climate;
  const scenarios = costState.charts, months = Number(document.getElementById("costHorizon").value);
  const parts = [];
  if (c) parts.push(c.count ? `${c.room.name}: ${c.alerts} leituras em alerta e ${c.critical} críticas entre ${c.count} leituras válidas no período selecionado.` : `${c.room.name}: sem leituras ambientais válidas no período selecionado.`);
  else parts.push("Indicadores ambientais indisponíveis ou em carregamento.");
  if (!scenarios.length) parts.push("Preencha os parâmetros ou abra um cenário salvo para analisar o investimento.");
  scenarios.forEach(s => {
    const r = s.results;
    parts.push(`${s.parameters.name}: investimento inicial estimado de ${money(r.initial_investment)}, energia mensal de ${money(r.monthly_cost)} e total projetado de ${money(r.series[months].total_cost)} em ${months} meses.${r.maintenance_informed ? " Manutenção prevista incluída." : " Manutenção não informada e não incluída no total."}`);
  });
  if (scenarios.length === 2) {
    const totals = scenarios.map(s => Number(s.results.series[months].total_cost));
    parts.push(totals[0] === totals[1] ? "Os cenários têm o mesmo total projetado." : `${scenarios[totals[0] < totals[1] ? 0 : 1].parameters.name} tem menor custo projetado, com diferença de ${money(Math.abs(totals[1] - totals[0]))}.`);
  }
  parts.push("Estimativas não são medições elétricas. Menor custo não comprova melhor climatização, economia real ou retorno do investimento. Os dados ambientais não determinam o consumo do equipamento.");
  node.textContent = parts.join(" ");
}
