const runButton = document.getElementById("run-button");
const cancelButton = document.getElementById("cancel-button");
const logOutput = document.getElementById("log-output");
const runStatus = document.getElementById("run-status");
const alertBox = document.getElementById("alert-box");
const optionsForm = document.getElementById("options-form");
const inputFile = document.getElementById("input_file");
const resultsEmpty = document.getElementById("results-empty");
const resultsContent = document.getElementById("results-content");
const resultsSummary = document.getElementById("results-summary");
const refreshEnvButton = document.getElementById("refresh-env");
const envBadge = document.getElementById("env-badge");

let pollTimer = null;

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
    } else if (data.output_dir) {
      showAlert("Prediction completed successfully.", "success");
    }
  } catch (error) {
    setRunning(false);
    showAlert(`Failed to fetch job status: ${error.message}`, "error");
  }
}

async function startRun() {
  hideAlert();

  const formData = new FormData(optionsForm);
  if (inputFile.files.length > 0) {
    formData.append("input_file", inputFile.files[0]);
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

runButton.addEventListener("click", startRun);
cancelButton.addEventListener("click", cancelRun);
refreshEnvButton.addEventListener("click", refreshEnvironment);

fetch("/api/job")
  .then((response) => response.json())
  .then((data) => {
    updateLogs(data.logs);
    updateResults(data);
    if (data.running) {
      pollJobStatus();
    }
  })
  .catch(() => {});
