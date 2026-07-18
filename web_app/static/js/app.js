const runButton = document.getElementById("run-button");
const cancelButton = document.getElementById("cancel-button");
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
const viewerEmpty = document.getElementById("viewer-empty");
const viewerContent = document.getElementById("viewer-content");
const viewerResultSet = document.getElementById("viewer-result-set");
const viewerCount = document.getElementById("viewer-count");
const viewerList = document.getElementById("viewer-list");
const refreshEnvButton = document.getElementById("refresh-env");
const envBadge = document.getElementById("env-badge");

let pollTimer = null;
let activeInputMode = "upload";
let viewerData = null;
let currentOutputDir = null;
let iupacRequestToken = 0;

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
}

function updateLogs(logs) {
  if (!logs || logs.length === 0) {
    logOutput.textContent = "No output yet.";
    return;
  }
  logOutput.textContent = logs.join("\n");
  logOutput.scrollTop = logOutput.scrollHeight;
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
    loadViewerData(data.output_dir);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderViewerCards(resultSet) {
  if (!resultSet) {
    viewerList.innerHTML = "";
    viewerCount.textContent = "";
    return;
  }

  viewerCount.textContent = `${resultSet.metabolite_count} predicted metabolite(s) for ${resultSet.label}`;

  viewerList.innerHTML = resultSet.metabolites
    .map((metabolite) => {
      const imageUrl = metabolite.image_name
        ? `/api/results/image/${encodeURIComponent(resultSet.id)}/${encodeURIComponent(metabolite.image_name)}`
        : "";
      const tools = metabolite.tools.length
        ? metabolite.tools.map((tool) => `<span class="tool-badge">${escapeHtml(tool)}</span>`).join("")
        : '<span class="text-sm text-slate-400">No tool annotation</span>';

      return `
        <article class="viewer-card p-4">
          <div class="grid gap-4 md:grid-cols-[220px_1fr]">
            <div class="viewer-structure">
              ${
                imageUrl
                  ? `<img src="${imageUrl}" alt="Structure for ${escapeHtml(metabolite.figure_id || metabolite.index)}" loading="lazy">`
                  : '<span class="text-sm text-slate-400">No structure image</span>'
              }
            </div>
            <div class="space-y-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <h4 class="text-base font-semibold text-slate-900">${escapeHtml(metabolite.figure_id || `Metabolite ${metabolite.index}`)}</h4>
                <span class="text-sm text-slate-500">#${metabolite.index}</span>
              </div>
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
            </div>
          </div>
        </article>
      `;
    })
    .join("");

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

function showViewerState(hasData) {
  viewerEmpty.classList.toggle("hidden", hasData);
  viewerContent.classList.toggle("hidden", !hasData);
}

async function loadViewerData(outputDir) {
  currentOutputDir = outputDir || currentOutputDir;
  if (!currentOutputDir) {
    showViewerState(false);
    return;
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
    populateViewerSelect(data.result_sets);
    renderViewerCards(data.result_sets[0]);
  } catch (error) {
    showViewerState(false);
    console.error("Failed to load viewer data:", error);
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
  if (!viewerData || !viewerData.result_sets) {
    return;
  }
  const selected = viewerData.result_sets.find((resultSet) => resultSet.id === viewerResultSet.value);
  renderViewerCards(selected);
});

runButton.addEventListener("click", startRun);
cancelButton.addEventListener("click", cancelRun);
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
    if (data.running) {
      pollJobStatus();
    } else if (data.output_dir) {
      loadViewerData(data.output_dir);
    }
  })
  .catch(() => {});
