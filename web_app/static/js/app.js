const runButton = document.getElementById("run-button");
const cancelButton = document.getElementById("cancel-button");
const clearSessionButton = document.getElementById("clear-session-button");
const clearSessionResultsButton = document.getElementById("clear-session-results-button");
const logOutput = document.getElementById("log-output");
const runStatus = document.getElementById("run-status");
const alertBox = document.getElementById("alert-box");
const optionsForm = document.getElementById("options-form");
const inputFile = document.getElementById("input_file");
const inputText = document.getElementById("input_text");
const inputUploadPanel = document.getElementById("input-upload-panel");
const inputPastePanel = document.getElementById("input-paste-panel");
const inputModeTabs = document.querySelectorAll(".input-mode-tab");
const resultsEmpty = document.getElementById("results-empty");
const resultsContent = document.getElementById("results-content");
const resultsSummary = document.getElementById("results-summary");
const downloadLink = document.getElementById("download-link");
const elmavenDownloadLink = document.getElementById("elmaven-download-link");
const viewerEmpty = document.getElementById("viewer-empty");
const viewerContent = document.getElementById("viewer-content");
const viewerResultSet = document.getElementById("viewer-result-set");
const viewerCount = document.getElementById("viewer-count");
const viewerList = document.getElementById("viewer-list");
const viewerSort = document.getElementById("viewer-sort");
const viewerSource = document.getElementById("viewer-source");
const viewerZipInput = document.getElementById("viewer-zip-input");
const viewerZipUpload = document.getElementById("viewer-zip-upload");
const viewerZipStatus = document.getElementById("viewer-zip-status");
const viewerZipInputActive = document.getElementById("viewer-zip-input-active");
const viewerZipUploadActive = document.getElementById("viewer-zip-upload-active");
const refreshEnvButton = document.getElementById("refresh-env");
const envBadge = document.getElementById("env-badge");

let pollTimer = null;
let activeInputMode = "upload";
let viewerData = null;
let currentOutputDir = null;
let viewerSourceLabel = "";
let iupacRequestToken = 0;
let variantSelections = {};

function isMissingIupac(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  return !normalized || normalized === "na" || normalized === "n/a" || normalized === "name unavailable";
}

function setInputMode(mode) {
  activeInputMode = mode;
  inputUploadPanel.classList.toggle("hidden", mode !== "upload");
  inputPastePanel.classList.toggle("hidden", mode !== "paste");

  inputModeTabs.forEach((tab) => {
    const selected = tab.dataset.inputMode === mode;
    tab.classList.toggle("border-brand-600", selected);
    tab.classList.toggle("text-brand-600", selected);
    tab.classList.toggle("border-transparent", !selected);
    tab.classList.toggle("text-slate-500", !selected);
  });
}

function showAlert(message, type = "error") {
  alertBox.textContent = message;
  alertBox.className = `mb-4 rounded-lg p-4 text-sm ${type}`;
  alertBox.classList.remove("hidden");
}

function hideAlert() {
  alertBox.classList.add("hidden");
}

function setRunning(running) {
  runButton.disabled = running;
  cancelButton.disabled = !running;
  runStatus.textContent = running ? "Running..." : "Idle";
  if (running) {
    [clearSessionButton, clearSessionResultsButton].forEach((button) => {
      if (button) {
        button.classList.add("hidden");
      }
    });
  }
}

function updateLogs(logs) {
  if (!logs || logs.length === 0) {
    logOutput.textContent = "No output yet.";
    return;
  }
  logOutput.textContent = logs.join("\n");
  logOutput.scrollTop = logOutput.scrollHeight;
}

function updateSessionActions(data) {
  const canClear =
    !data.running &&
    (Boolean(data.output_dir) || Boolean(data.error) || Boolean(data.logs && data.logs.length > 0));

  [clearSessionButton, clearSessionResultsButton].forEach((button) => {
    if (!button) {
      return;
    }
    button.classList.toggle("hidden", !canClear);
  });
}

function resetUiForNewQuery() {
  hideAlert();
  updateLogs([]);
  setRunning(false);

  resultsEmpty.classList.remove("hidden");
  resultsContent.classList.add("hidden");
  resultsSummary.textContent = "";
  downloadLink.classList.add("hidden");
  elmavenDownloadLink.classList.add("hidden");

  viewerData = null;
  currentOutputDir = null;
  viewerSourceLabel = "";
  variantSelections = {};
  showViewerState(false);
  viewerList.innerHTML = "";
  viewerCount.textContent = "";
  if (viewerResultSet) {
    viewerResultSet.innerHTML = "";
  }
  if (viewerZipStatus) {
    viewerZipStatus.textContent = "";
  }

  inputFile.value = "";
  inputText.value = "";
  updateSessionActions({ running: false, logs: [] });
}

function updateResults(data) {
  if (data.output_dir && data.summary) {
    resultsEmpty.classList.add("hidden");
    resultsContent.classList.remove("hidden");
    resultsSummary.textContent = data.summary;
    if (data.zip_ready) {
      downloadLink.classList.remove("hidden", "pointer-events-none", "opacity-50");
      downloadLink.setAttribute("aria-disabled", "false");
    } else {
      downloadLink.classList.add("hidden");
    }
    if (data.summary.includes("El-MAVEN knowns list:")) {
      const elmavenUrl = `/api/results/elmaven?output_dir=${encodeURIComponent(data.output_dir)}`;
      elmavenDownloadLink.href = elmavenUrl;
      elmavenDownloadLink.classList.remove("hidden");
    } else {
      elmavenDownloadLink.classList.add("hidden");
    }
    viewerSourceLabel = "";
    loadViewerData(data.output_dir);
  }
  updateSessionActions(data);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function parseMassValue(mass) {
  const value = Number.parseFloat(String(mass || "").trim());
  return Number.isFinite(value) ? value : null;
}

function massGroupKey(mass) {
  const value = parseMassValue(mass);
  return value === null ? "na" : value.toFixed(5);
}

function buildDisplayGroups(metabolites, sortOrder) {
  const grouped = new Map();
  metabolites.forEach((metabolite) => {
    const key = metabolite.mass_group || massGroupKey(metabolite.mass);
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key).push(metabolite);
  });

  const groups = [...grouped.entries()].map(([key, variants]) => {
    const sortedVariants = [...variants].sort((left, right) => left.index - right.index);
    return {
      key,
      mass: sortedVariants[0].mass,
      massValue: parseMassValue(sortedVariants[0].mass),
      variants: sortedVariants,
    };
  });

  const compareByIndex = (left, right) => left.variants[0].index - right.variants[0].index;
  const compareByMass = (left, right, direction) => {
    if (left.massValue === null && right.massValue === null) {
      return compareByIndex(left, right);
    }
    if (left.massValue === null) {
      return 1;
    }
    if (right.massValue === null) {
      return -1;
    }
    return direction * (left.massValue - right.massValue) || compareByIndex(left, right);
  };

  if (sortOrder === "mz-desc") {
    groups.sort((left, right) => compareByMass(left, right, -1));
  } else if (sortOrder === "index") {
    groups.sort(compareByIndex);
  } else {
    groups.sort((left, right) => compareByMass(left, right, 1));
  }

  return groups;
}

function variantLabel(metabolite) {
  const tools = metabolite.tools.length ? metabolite.tools.join(", ") : "No tool";
  const title = metabolite.figure_id || `Metabolite ${metabolite.index}`;
  return `#${metabolite.index} · ${title} · ${tools}`;
}

function parsePathwayEntries(value) {
  return String(value || "")
    .split(";")
    .map((entry) => entry.trim().replace(/[;,]+$/, "").trim())
    .filter((entry) => entry && entry.toUpperCase() !== "NA");
}

function formatPathwayEntry(value) {
  const cleaned = String(value || "").trim();
  if (!cleaned) {
    return "";
  }
  if (/[A-Z]/.test(cleaned) && cleaned.includes(" ")) {
    return cleaned;
  }
  return cleaned.replaceAll("_", " ");
}

function renderPathwaySection(metabolite) {
  const sources = [
    { label: "SygMa", value: metabolite.sygma_pathway },
    { label: "BioTransformer", value: metabolite.biotrans_pathway },
    { label: "GLORYx", value: metabolite.gloryx_pathway },
  ]
    .map((source) => ({
      ...source,
      entries: parsePathwayEntries(source.value).map(formatPathwayEntry),
    }))
    .filter((source) => source.entries.length > 0);

  if (!sources.length) {
    return "";
  }

  const items = sources
    .map(
      (source) => `
        <div class="pathway-item">
          <p class="pathway-source">${escapeHtml(source.label)}</p>
          <p class="pathway-value">${source.entries.map((entry) => escapeHtml(entry)).join("<br>")}</p>
        </div>
      `
    )
    .join("");

  return `
    <div>
      <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Predicted transformations</p>
      <div class="pathway-list mt-2">${items}</div>
    </div>
  `;
}

function bindVariantSelect(resultSet, group) {
  const select = viewerList.querySelector(`.variant-select[data-group-key="${group.key}"]`);
  if (!select) {
    return;
  }

  select.addEventListener("change", () => {
    const selectionKey = `${resultSet.id}:${group.key}`;
    variantSelections[selectionKey] = Number.parseInt(select.value, 10) || 0;
    const card = viewerList.querySelector(`[data-group-key="${group.key}"]`);
    if (!card) {
      return;
    }
    card.outerHTML = renderMetaboliteCard(resultSet, group, variantSelections[selectionKey]);
    bindVariantSelect(resultSet, group);
    hydrateIupacNames(resultSet);
  });
}

function structureImageUrl(resultSetId, imageName) {
  if (!imageName || !currentOutputDir) {
    return "";
  }
  return `/api/results/image/${encodeURIComponent(resultSetId)}/${encodeURIComponent(imageName)}?output_dir=${encodeURIComponent(currentOutputDir)}`;
}

function renderStructurePanel(kind, label, imageUrl, caption, metaLines = []) {
  const metaHtml = metaLines
    .filter((line) => line.value)
    .map(
      (line) =>
        `<p class="structure-meta"><span class="structure-meta-label">${escapeHtml(line.label)}:</span> ${escapeHtml(line.value)}</p>`
    )
    .join("");

  return `
    <div class="viewer-structure-panel ${kind}">
      <p class="structure-label">${escapeHtml(label)}</p>
      <div class="viewer-structure">
        ${
          imageUrl
            ? `<img src="${imageUrl}" alt="${escapeHtml(label)}" loading="lazy">`
            : '<span class="text-sm text-slate-400">No structure image</span>'
        }
      </div>
      ${caption ? `<p class="structure-caption">${escapeHtml(caption)}</p>` : ""}
      ${metaHtml ? `<div class="structure-meta-list">${metaHtml}</div>` : ""}
    </div>
  `;
}

function renderStructureComparison(resultSet, metabolite, productImageUrl) {
  const parent = resultSet.parent;
  const parentImageUrl = parent?.image_name ? structureImageUrl(resultSet.id, parent.image_name) : "";
  const parentMeta = parent
    ? [
        { label: "Formula", value: parent.formula },
        { label: "Mass (+H)", value: parent.mass },
      ]
    : [];
  const productMeta = [
    { label: "Formula", value: metabolite.formula },
    { label: "Mass (+H)", value: metabolite.mass },
  ];

  return `
    <div class="structure-compare">
      ${renderStructurePanel(
        "parent",
        "Original molecule",
        parentImageUrl,
        parent?.name || resultSet.label,
        parentMeta
      )}
      <div class="structure-compare-divider" aria-hidden="true">→</div>
      ${renderStructurePanel(
        "product",
        "Predicted product",
        productImageUrl,
        metabolite.figure_id || `Metabolite ${metabolite.index}`,
        productMeta
      )}
    </div>
  `;
}

function renderMetaboliteCard(resultSet, group, activeVariantIndex) {
  const metabolite = group.variants[activeVariantIndex] || group.variants[0];
  const imageUrl = structureImageUrl(resultSet.id, metabolite.image_name);
  const tools = metabolite.tools.length
    ? metabolite.tools.map((tool) => `<span class="tool-badge">${escapeHtml(tool)}</span>`).join("")
    : '<span class="text-sm text-slate-400">No tool annotation</span>';
  const variantSelect =
    group.variants.length > 1
      ? `
        <div class="variant-picker">
          <label class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500" for="variant-${group.key}">
            ${group.variants.length} renditions at m/z ${escapeHtml(group.mass || "NA")}
          </label>
          <select id="variant-${group.key}" class="variant-select block w-full rounded-lg border border-slate-300 bg-slate-50 p-2 text-sm focus:border-brand-500 focus:ring-brand-500" data-group-key="${group.key}">
            ${group.variants
              .map(
                (variant, variantIndex) =>
                  `<option value="${variantIndex}" ${variantIndex === activeVariantIndex ? "selected" : ""}>${escapeHtml(variantLabel(variant))}</option>`
              )
              .join("")}
          </select>
        </div>
      `
      : "";

  return `
    <article class="viewer-card p-4" data-group-key="${group.key}">
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        ${renderStructureComparison(resultSet, metabolite, imageUrl)}
        <div class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h4 class="text-base font-semibold text-slate-900">${escapeHtml(metabolite.figure_id || `Metabolite ${metabolite.index}`)}</h4>
            <span class="text-sm text-slate-500">#${metabolite.index}</span>
          </div>
          ${variantSelect}
          <div>
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">IUPAC name</p>
            <p class="mt-1 text-sm leading-relaxed text-slate-800 iupac-name" data-index="${metabolite.index}">
              ${escapeHtml(isMissingIupac(metabolite.iupac) ? "Resolving name..." : metabolite.iupac)}
            </p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Formula</p>
              <p class="mt-1 text-sm text-slate-800">${escapeHtml(metabolite.formula || "NA")}</p>
            </div>
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Mass (+H)</p>
              <p class="mt-1 text-sm text-slate-800">${escapeHtml(metabolite.mass || "NA")}</p>
            </div>
          </div>
          <div>
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">SMILES</p>
            <p class="mt-1 break-all font-mono text-xs text-slate-700">${escapeHtml(metabolite.smiles || "")}</p>
          </div>
          <div class="flex flex-wrap gap-2">${tools}</div>
          ${renderPathwaySection(metabolite)}
        </div>
      </div>
    </article>
  `;
}

function renderViewerCards(resultSet) {
  if (!resultSet) {
    viewerList.innerHTML = "";
    viewerCount.textContent = "";
    return;
  }

  const sortOrder = viewerSort ? viewerSort.value : "mz-asc";
  const groups = buildDisplayGroups(resultSet.metabolites, sortOrder);
  const uniqueMasses = groups.length;
  const totalHits = resultSet.metabolite_count;
  const duplicateHits = totalHits - uniqueMasses;

  viewerCount.textContent =
    duplicateHits > 0
      ? `${uniqueMasses} unique m/z value(s), ${totalHits} total hit(s) for ${resultSet.label}`
      : `${totalHits} predicted metabolite(s) for ${resultSet.label}`;

  viewerList.innerHTML = groups
    .map((group) => {
      const selectionKey = `${resultSet.id}:${group.key}`;
      const activeVariantIndex = variantSelections[selectionKey] || 0;
      return renderMetaboliteCard(resultSet, group, activeVariantIndex);
    })
    .join("");

  groups.forEach((group) => bindVariantSelect(resultSet, group));
  hydrateIupacNames(resultSet);
}

async function hydrateIupacNames(resultSet) {
  if (!currentOutputDir || !resultSet) {
    return;
  }

  const requestToken = ++iupacRequestToken;
  const smilesToResolve = [
    ...new Set(
      resultSet.metabolites
        .filter((metabolite) => isMissingIupac(metabolite.iupac) && metabolite.smiles)
        .map((metabolite) => metabolite.smiles)
    ),
  ];

  if (!smilesToResolve.length) {
    return;
  }

  const batchSize = 25;
  for (let offset = 0; offset < smilesToResolve.length; offset += batchSize) {
    if (requestToken !== iupacRequestToken) {
      return;
    }

    const batch = smilesToResolve.slice(offset, offset + batchSize);
    try {
      const response = await fetch(
        `/api/results/iupac?output_dir=${encodeURIComponent(currentOutputDir)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ smiles: batch }),
        }
      );
      const data = await response.json();
      if (!response.ok || requestToken !== iupacRequestToken) {
        continue;
      }

      const names = data.names || {};
      batch.forEach((smiles) => {
        const iupac = names[smiles];
        resultSet.metabolites
          .filter((metabolite) => metabolite.smiles === smiles)
          .forEach((metabolite) => {
            if (!isMissingIupac(iupac)) {
              metabolite.iupac = iupac;
            }
            const node = viewerList.querySelector(`.iupac-name[data-index="${metabolite.index}"]`);
            if (node) {
              node.textContent = isMissingIupac(iupac) ? "Name unavailable" : iupac;
            }
          });
      });
    } catch (error) {
      console.error("Failed to resolve IUPAC names:", error);
    }
  }
}

function populateViewerSelect(resultSets) {
  viewerResultSet.innerHTML = resultSets
    .map(
      (resultSet) =>
        `<option value="${escapeHtml(resultSet.id)}">${escapeHtml(resultSet.label)} (${resultSet.metabolite_count})</option>`
    )
    .join("");
}

function updateViewerSourceLabel() {
  if (!viewerSource) {
    return;
  }
  if (viewerSourceLabel) {
    viewerSource.textContent = `Viewing uploaded archive: ${viewerSourceLabel}`;
    viewerSource.classList.remove("hidden");
  } else {
    viewerSource.textContent = "";
    viewerSource.classList.add("hidden");
  }
}

function showViewerState(hasData) {
  viewerEmpty.classList.toggle("hidden", hasData);
  viewerContent.classList.toggle("hidden", !hasData);
}

function getSelectedResultSet() {
  if (!viewerData || !viewerData.result_sets) {
    return null;
  }
  return viewerData.result_sets.find((resultSet) => resultSet.id === viewerResultSet.value) || viewerData.result_sets[0];
}

async function loadViewerData(outputDir, options = {}) {
  currentOutputDir = outputDir || currentOutputDir;
  if (!currentOutputDir) {
    showViewerState(false);
    return;
  }

  if (options.sourceLabel !== undefined) {
    viewerSourceLabel = options.sourceLabel;
  }

  try {
    const response = await fetch(`/api/results/viewer?output_dir=${encodeURIComponent(currentOutputDir)}`);
    const data = await response.json();
    viewerData = data;
    if (!data.available || !data.result_sets.length) {
      showViewerState(false);
      return;
    }

    showViewerState(true);
    updateViewerSourceLabel();
    populateViewerSelect(data.result_sets);
    renderViewerCards(data.result_sets[0]);
  } catch (error) {
    showViewerState(false);
    console.error("Failed to load viewer data:", error);
  }
}

async function uploadViewerZip(fileInput, statusNode) {
  const file = fileInput?.files?.[0];
  if (!file) {
    if (statusNode) {
      statusNode.textContent = "Choose a MetaTox results .zip file first.";
    }
    return;
  }

  if (statusNode) {
    statusNode.textContent = "Uploading and extracting results...";
  }

  const formData = new FormData();
  formData.append("results_zip", file);

  try {
    const response = await fetch("/api/results/upload-zip", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to load results zip.");
    }

    variantSelections = {};
    await loadViewerData(data.output_dir, { sourceLabel: data.label || file.name });
    if (statusNode) {
      statusNode.textContent = `Loaded ${file.name}.`;
    }
    showAlert("Results archive loaded into the viewer.", "success");
  } catch (error) {
    if (statusNode) {
      statusNode.textContent = error.message;
    }
    showAlert(error.message, "error");
  } finally {
    fileInput.value = "";
  }
}

async function pollJobStatus() {
  try {
    const response = await fetch("/api/job");
    const data = await response.json();
    updateLogs(data.logs);
    updateResults(data);

    if (data.running) {
      setRunning(true);
      pollTimer = window.setTimeout(pollJobStatus, 1000);
      return;
    }

    setRunning(false);
    pollTimer = null;

    if (data.error) {
      showAlert(data.error, "error");
    } else if (data.output_dir && data.zip_ready) {
      showAlert("Prediction completed successfully. Browse results in the Viewer tab or download the zip.", "success");
      await loadViewerData(data.output_dir);
    } else if (data.output_dir) {
      showAlert("Prediction finished but the results archive is not ready. Check the logs.", "error");
    }
  } catch (error) {
    setRunning(false);
    showAlert(`Failed to fetch job status: ${error.message}`, "error");
  }
}

async function startRun() {
  hideAlert();
  viewerData = null;
  viewerSourceLabel = "";
  variantSelections = {};
  showViewerState(false);

  const formData = new FormData(optionsForm);
  if (activeInputMode === "upload" && inputFile.files.length > 0) {
    formData.append("input_file", inputFile.files[0]);
  } else if (activeInputMode === "paste") {
    formData.set("input_text", inputText.value.trim());
  }

  const useExample = document.getElementById("use_example");
  if (useExample) {
    formData.set("use_example", useExample.checked ? "true" : "false");
  } else {
    formData.set("use_example", "false");
  }

  formData.set("predictor_activate", document.getElementById("predictor_activate").checked ? "true" : "false");
  formData.set("keep_tmp", document.getElementById("keep_tmp").checked ? "true" : "false");
  formData.set("export_elmaven", document.getElementById("export_elmaven").checked ? "true" : "false");

  setRunning(true);
  logOutput.textContent = "Starting prediction...";

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to start prediction.");
    }
    showAlert("Prediction started.", "success");
    pollJobStatus();
  } catch (error) {
    setRunning(false);
    showAlert(error.message, "error");
  }
}

async function clearSession() {
  if (
    !window.confirm(
      "Clear the current logs and saved results? Download anything you need first, then you can start a new query."
    )
  ) {
    return;
  }

  try {
    const response = await fetch("/api/clear", { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to clear the current session.");
    }
    resetUiForNewQuery();
    showAlert("Session cleared. You can start a new query.", "success");
  } catch (error) {
    showAlert(error.message, "error");
  }
}

async function cancelRun() {
  try {
    await fetch("/api/cancel", { method: "POST" });
    showAlert("Cancellation requested. Waiting for the current step to stop...", "warning");
  } catch (error) {
    showAlert(`Failed to cancel: ${error.message}`, "error");
  }
}

async function refreshEnvironment() {
  try {
    const response = await fetch("/api/environment");
    const data = await response.json();
    envBadge.textContent = data.ready ? "Environment ready" : "Setup required";
    envBadge.className = `inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${
      data.ready ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"
    }`;
    window.location.reload();
  } catch (error) {
    showAlert(`Failed to refresh environment: ${error.message}`, "error");
  }
}

viewerResultSet.addEventListener("change", () => {
  renderViewerCards(getSelectedResultSet());
});

if (viewerSort) {
  viewerSort.addEventListener("change", () => {
    renderViewerCards(getSelectedResultSet());
  });
}

if (viewerZipUpload && viewerZipInput) {
  viewerZipUpload.addEventListener("click", () => uploadViewerZip(viewerZipInput, viewerZipStatus));
}

if (viewerZipUploadActive && viewerZipInputActive) {
  viewerZipUploadActive.addEventListener("click", () => uploadViewerZip(viewerZipInputActive, null));
}

runButton.addEventListener("click", startRun);
cancelButton.addEventListener("click", cancelRun);
if (clearSessionButton) {
  clearSessionButton.addEventListener("click", clearSession);
}
if (clearSessionResultsButton) {
  clearSessionResultsButton.addEventListener("click", clearSession);
}
refreshEnvButton.addEventListener("click", refreshEnvironment);
inputModeTabs.forEach((tab) => {
  tab.addEventListener("click", () => setInputMode(tab.dataset.inputMode));
});
setInputMode("upload");

fetch("/api/job")
  .then((response) => response.json())
  .then((data) => {
    updateLogs(data.logs);
    updateResults(data);
    updateSessionActions(data);
    if (data.running) {
      pollJobStatus();
    } else if (data.output_dir) {
      loadViewerData(data.output_dir);
    }
  })
  .catch(() => {});
