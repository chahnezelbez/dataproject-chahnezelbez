"use strict";
// CONTEXTE ÉTUDIANT : S2, script chargé par index.html dans le navigateur.
// CONTRÔLE : textContent partout, chemins /api relatifs, boutons désactivés pendant les mutations.

let currentDataset = null;

function element(id) {
  return document.getElementById(id);
}

function cell(value) {
  const td = document.createElement("td");
  td.textContent = value === null || value === undefined ? "-" : String(value);
  return td;
}

function button(label, onClick) {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = label;
  node.addEventListener("click", onClick);
  return node;
}

function showState(node, text, isError = false) {
  node.hidden = false;
  node.textContent = text;
  node.setAttribute("role", isError ? "alert" : "status");
}

function hideState(node) {
  node.hidden = true;
  node.textContent = "";
}

function setMessage(text, isError = false) {
  const node = element("message");
  node.textContent = text;
  node.setAttribute("role", isError ? "alert" : "status");
}

function formatDetail(payload) {
  if (payload && typeof payload === "object") {
    const detail = payload.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (item && item.msg ? item.msg : JSON.stringify(item)))
        .join(" ; ");
    }
    return JSON.stringify(payload);
  }
  if (typeof payload === "string" && payload.trim()) {
    return payload.replace(/\s+/g, " ").trim().slice(0, 200);
  }
  return "réponse inexploitable";
}

async function request(path, options = {}) {
  const init = { ...options };
  const isJsonBody =
    init.body !== undefined &&
    init.body !== null &&
    typeof init.body === "object" &&
    !(init.body instanceof Blob) &&
    !(init.body instanceof FormData) &&
    !(init.body instanceof ArrayBuffer);

  if (isJsonBody) {
    init.body = JSON.stringify(init.body);
    init.headers = { ...(init.headers || {}), "Content-Type": "application/json" };
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error("Erreur réseau : serveur injoignable");
  }

  if (response.status === 204) {
    return null;
  }

  const text = await response.text();
  let payload = text;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    throw new Error(`Erreur ${response.status} : ${formatDetail(payload)}`);
  }
  return payload;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function formatDecimal(value) {
  return Number(value).toFixed(1);
}

function formatCounter(value) {
  return value === null || value === undefined ? "-" : String(value);
}

function describeIngestion(ingestion) {
  const prefix = `${ingestion.filename} : ${ingestion.status}`;
  if (ingestion.status === "succeeded") {
    return `${prefix} - ${formatCounter(ingestion.rows_accepted)} acceptées, ${formatCounter(ingestion.rows_rejected)} rejetées, ${formatCounter(ingestion.rows_duplicate)} doublons`;
  }
  if (ingestion.status === "failed") {
    return `${prefix} - ${ingestion.error_message || "traitement refusé"}`;
  }
  return prefix;
}

function readableStatsError(error) {
  if (error.message.includes("Invalid period")) {
    return "Erreur 422 : from must be before to";
  }
  return error.message;
}

async function loadDatasets() {
  const state = element("datasets-state");
  const body = element("datasets");
  body.replaceChildren();
  showState(state, "Chargement des jeux de données…");

  try {
    const datasets = await request("/api/datasets");
    if (datasets.length === 0) {
      showState(state, "Aucun jeu de données.");
      return;
    }
    hideState(state);
    renderDatasets(datasets);
  } catch (error) {
    showState(state, error.message, true);
  }
}

function renderDatasets(datasets) {
  const body = element("datasets");
  body.replaceChildren();

  for (const dataset of datasets) {
    const row = document.createElement("tr");
    row.append(
      cell(dataset.name),
      cell(dataset.owner),
      cell(dataset.measurement_count),
      cell(formatDate(dataset.created_at))
    );

    const actions = cell("");
    actions.append(
      button("Ouvrir", () => openDataset(dataset)),
      button("Supprimer", (event) => deleteDataset(dataset, event.currentTarget))
    );
    row.append(actions);
    body.append(row);
  }
}

async function createDataset(event) {
  event.preventDefault();
  const submitButton = element("create-button");
  submitButton.disabled = true;

  const name = element("dataset-name").value.trim();
  const owner = element("dataset-owner").value.trim();
  const description = element("dataset-description").value;
  const payload = { name, owner, description: description === "" ? null : description };

  try {
    const dataset = await request("/api/datasets", { method: "POST", body: payload });
    setMessage(`Jeu « ${dataset.name} » créé.`);
    element("dataset-form").reset();
    element("dataset-owner").value = "Équipe";
    await loadDatasets();
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    submitButton.disabled = false;
  }
}

async function deleteDataset(dataset, deleteButton) {
  const question = `Supprimer le jeu « ${dataset.name} » et ses ${dataset.measurement_count} mesures ?`;
  if (!confirm(question)) {
    setMessage("Suppression annulée.");
    return;
  }

  deleteButton.disabled = true;
  try {
    await request(`/api/datasets/${encodeURIComponent(dataset.id)}`, { method: "DELETE" });
    setMessage(`Jeu « ${dataset.name} » supprimé.`);

    if (currentDataset && currentDataset.id === dataset.id) {
      currentDataset = null;
      element("dataset-detail").hidden = true;
      element("ingestion-status").textContent = "Aucun dépôt en cours.";
      element("ingestions").replaceChildren();
      element("stats").replaceChildren();
      element("report").replaceChildren();
      showState(element("report-state"), "Sélectionnez un dépôt.");
    }
    await loadDatasets();
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    deleteButton.disabled = false;
  }
}

async function openDataset(dataset) {
  currentDataset = dataset;
  element("dataset-detail").hidden = false;
  element("detail-title").textContent = dataset.name;
  element("detail-count").textContent = `${dataset.measurement_count} mesures`;
  element("ingestion-status").textContent = "Aucun dépôt en cours.";
  element("ingestion-filter").value = "";
  element("report").replaceChildren();
  showState(element("report-state"), "Sélectionnez un dépôt.");
  setMessage(`Jeu « ${dataset.name} » ouvert.`);
  await Promise.all([loadIngestions(), loadStats()]);
}

async function uploadFile(event) {
  event.preventDefault();
  if (!currentDataset) {
    setMessage("Ouvrez d'abord un jeu de données.", true);
    return;
  }

  const file = element("csv-file").files[0];
  if (!file) {
    setMessage("Choisissez un fichier CSV.", true);
    return;
  }

  const submitButton = element("upload-button");
  const status = element("ingestion-status");
  submitButton.disabled = true;
  status.textContent = `Dépôt de « ${file.name} » en cours…`;

  try {
    const query = new URLSearchParams({ filename: file.name });
    const ingestion = await request(
      `/api/datasets/${currentDataset.id}/ingestions?${query.toString()}`,
      { method: "POST", body: file, headers: { "Content-Type": "text/csv" } }
    );
    setMessage(`Fichier « ${file.name} » reçu, statut pending.`);
    status.textContent = describeIngestion(ingestion);
    element("csv-file").value = "";
    await loadIngestions();
    await followIngestion(ingestion.id, status);
  } catch (error) {
    status.textContent = error.message;
    setMessage(error.message, true);
  } finally {
    submitButton.disabled = false;
  }
}

async function loadIngestions() {
  if (!currentDataset) {
    return;
  }

  const refreshButton = element("refresh-ingestions");
  const state = element("ingestions-state");
  const table = element("ingestions-table");
  const body = element("ingestions");
  refreshButton.disabled = true;
  table.hidden = true;
  body.replaceChildren();
  showState(state, "Chargement des dépôts…");

  try {
    const status = element("ingestion-filter").value;
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    const ingestions = await request(
      `/api/datasets/${currentDataset.id}/ingestions${query}`
    );

    if (ingestions.length === 0) {
      showState(state, "Aucun dépôt pour ce jeu.");
      return;
    }

    hideState(state);
    table.hidden = false;

    for (const ingestion of ingestions) {
      const row = document.createElement("tr");
      row.append(
        cell(ingestion.filename),
        cell(ingestion.status),
        cell(ingestion.rows_accepted),
        cell(ingestion.rows_rejected),
        cell(ingestion.rows_duplicate),
        cell(formatDate(ingestion.created_at))
      );

      const actions = cell("");
      actions.append(button("Rapport", () => showReport(ingestion)));
      if (ingestion.status === "failed") {
        actions.append(
          button("Relancer", (event) => retryIngestion(ingestion, event.currentTarget))
        );
      }
      row.append(actions);
      body.append(row);
    }
  } catch (error) {
    showState(state, error.message, true);
  } finally {
    refreshButton.disabled = false;
  }
}

function showReport(ingestion) {
  const state = element("report-state");
  const report = element("report");
  state.hidden = true;
  report.replaceChildren();

  for (const text of [
    `Fichier : ${ingestion.filename}`,
    `Statut : ${ingestion.status}`,
  ]) {
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    report.append(paragraph);
  }

  if (ingestion.status === "failed" && ingestion.error_message) {
    const paragraph = document.createElement("p");
    paragraph.textContent = `Message : ${ingestion.error_message}`;
    report.append(paragraph);
  }

  const errors = Array.isArray(ingestion.errors) ? ingestion.errors : [];
  if (errors.length === 0) {
    const paragraph = document.createElement("p");
    paragraph.textContent = "Aucune erreur détaillée.";
    report.append(paragraph);
  } else {
    const list = document.createElement("ul");
    for (const error of errors) {
      const item = document.createElement("li");
      item.textContent = `Ligne ${error.line} : ${error.reason}`;
      list.append(item);
    }
    report.append(list);
  }

  const remaining = (ingestion.rows_rejected ?? 0) - errors.length;
  if (remaining > 0) {
    const paragraph = document.createElement("p");
    paragraph.textContent = `${remaining} ligne(s) rejetée(s) supplémentaire(s) non détaillée(s).`;
    report.append(paragraph);
  }
}

async function retryIngestion(ingestion, retryButton) {
  retryButton.disabled = true;
  const status = element("ingestion-status");

  try {
    const retried = await request(
      `/api/ingestions/${encodeURIComponent(ingestion.id)}/retry`,
      { method: "POST" }
    );
    setMessage(`Dépôt « ${retried.filename} » relancé, statut pending.`);
    status.textContent = describeIngestion(retried);
    await loadIngestions();
    await followIngestion(retried.id, status);
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    retryButton.disabled = false;
  }
}

async function loadStats() {
  if (!currentDataset) {
    return;
  }

  const filterButton = element("stats-button");
  const state = element("stats-state");
  const table = element("stats-table");
  const body = element("stats");
  filterButton.disabled = true;
  table.hidden = true;
  body.replaceChildren();
  showState(state, "Chargement des indicateurs…");

  const params = new URLSearchParams();
  const room = element("stats-room").value.trim();
  if (room) {
    params.set("room", room);
  }
  const from = element("stats-from").value;
  if (from) {
    params.set("from", new Date(from).toISOString());
  }
  const to = element("stats-to").value;
  if (to) {
    params.set("to", new Date(to).toISOString());
  }
  const query = params.toString();

  try {
    const result = await request(
      `/api/datasets/${currentDataset.id}/stats${query ? `?${query}` : ""}`
    );
    const rooms = Array.isArray(result.rooms) ? result.rooms : [];
    if (rooms.length === 0) {
      showState(state, "Aucune mesure ne correspond à ce filtre.");
      return;
    }

    hideState(state);
    table.hidden = false;

    for (const row of rooms) {
      const tr = document.createElement("tr");
      tr.append(
        cell(row.room),
        cell(row.measurements),
        cell(formatDecimal(row.co2_avg)),
        cell(row.co2_min),
        cell(row.co2_max),
        cell(formatDecimal(row.temperature_avg)),
        cell(formatDecimal(row.humidity_avg)),
        cell(formatDate(row.last_measured_at))
      );
      body.append(tr);
    }
  } catch (error) {
    const message = readableStatsError(error);
    showState(state, message, true);
    setMessage(message, true);
  } finally {
    filterButton.disabled = false;
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function followIngestion(ingestionId, statusNode) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await delay(2000);
    try {
      const ingestion = await request(
        `/api/ingestions/${encodeURIComponent(ingestionId)}`
      );
      statusNode.textContent = describeIngestion(ingestion);
      if (ingestion.status === "succeeded" || ingestion.status === "failed") {
        await Promise.all([loadIngestions(), loadDatasets()]);
        return ingestion;
      }
    } catch (error) {
      statusNode.textContent = error.message;
      return null;
    }
  }

  statusNode.textContent = "Suivi arrêté après 60 essais ; actualisez la liste.";
  await loadIngestions();
  return null;
}

async function loadVersion() {
  try {
    const response = await request("/api/version");
    element("version").textContent = `Version : ${response.version}`;
  } catch {
    element("version").textContent = "Version : indisponible";
  }
}

function init() {
  element("dataset-form").addEventListener("submit", createDataset);
  element("upload-form").addEventListener("submit", uploadFile);
  element("refresh-ingestions").addEventListener("click", loadIngestions);
  element("ingestion-filter").addEventListener("change", loadIngestions);
  element("stats-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadStats();
  });
  loadDatasets();
  loadVersion();
}

document.addEventListener("DOMContentLoaded", init);
