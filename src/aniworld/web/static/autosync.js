/* Auto-Sync page: explicit tracked-series list, status and last report. */

(function () {
  const el = (id) => document.getElementById(id);
  const syncNowBtn = el("syncNowBtn");
  const seriesBody = el("seriesBody");
  const siteSelect = el("seriesSite");
  const languageSelect = el("seriesLanguage");
  const providerSelect = el("seriesProvider");
  const pathSelect = el("seriesPath");
  const searchInput = el("seriesSearch");
  const searchBtn = el("seriesSearchBtn");
  const searchResults = el("seriesResults");

  const IDLE_POLL = 30000;
  const RUNNING_POLL = 3000;
  const SITE_LABELS = { aniworld: "AniWorld", sto: "SerienStream" };
  let timer = null;
  let statusData = null;

  const STATUS_CLASS = {
    queued: "status-completed",
    "up-to-date": "status-queued",
    skipped: "status-cancelled",
    error: "status-failed"
  };
  const STATUS_LABELS = {
    queued: "Queued",
    "up-to-date": "Up to date",
    skipped: "Skipped",
    error: "Error"
  };

  function statusLabel(status) {
    const key = String(status).replace(/-/g, "_");
    return t(`autosync.status.${key}`, STATUS_LABELS[status] || status);
  }

  function formatTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
  }

  function schedule(running) {
    clearTimeout(timer);
    timer = setTimeout(loadStatus, running ? RUNNING_POLL : IDLE_POLL);
  }

  function setOptions(select, values, selected) {
    select.innerHTML = values.map((value) =>
      `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(value)}</option>`
    ).join("");
  }

  function updateLanguages() {
    const values = statusData?.languages?.[siteSelect.value] || [];
    setOptions(languageSelect, values, languageSelect.value || values[0]);
  }

  function renderReport(report) {
    const container = el("syncReport");
    if (!report) {
      container.innerHTML = `<div class="empty-state">${t("autosync.never_ran", "Auto-Sync has not run yet.")}</div>`;
      return;
    }
    if (report.error) {
      container.innerHTML = `<div class="empty-state">${esc(report.error)}</div>`;
      return;
    }
    const rows = report.results || [];
    if (!rows.length) {
      container.innerHTML = `<div class="empty-state">${t("autosync.no_tracked", "No active series to check.")}</div>`;
      return;
    }
    container.innerHTML = rows.map((row) => {
      const detail = row.reason
        ? esc(row.reason)
        : row.episodes
          ? t("autosync.queued_episodes", "{count} episodes queued in {language}", { count: row.episodes, language: row.language || "" })
          : esc(row.language || "");
      return `<div class="sync-row">
        <div class="sync-row-main">
          <span class="sync-row-title">${esc(row.title)}<span class="sync-row-where">${esc(row.where || "")}</span></span>
          <span class="sync-row-detail">${detail}</span>
        </div>
        <span class="status-pill ${STATUS_CLASS[row.status] || "status-queued"}">${esc(statusLabel(row.status))}</span>
      </div>`;
    }).join("");
  }

  async function loadStatus() {
    try {
      statusData = await apiFetch("/api/autosync/status");
    } catch (_error) {
      schedule(false);
      return;
    }

    if (!providerSelect.options.length) {
      setOptions(providerSelect, statusData.providers || [], (statusData.providers || [])[0]);
    }
    updateLanguages();
    el("syncModeNotice").textContent = statusData.new_only
      ? t("autosync.mode_new", "Mode: only episodes or language releases first seen after this series was added. Earlier gaps stay untouched.")
      : t("autosync.mode_fill", "Mode: fill gaps. Every run queues all available missing episodes in the selected language.");
    el("scheduleValue").textContent = statusData.schedule || "-";
    el("lastRun").textContent = formatTime(statusData.last_run);
    el("nextRun").textContent = statusData.running ? t("autosync.running", "Running...") : formatTime(statusData.next_run);
    const report = statusData.last_report;
    el("lastResult").textContent = report
      ? t("autosync.result", "{queued} of {checked} queued", { queued: report.queued || 0, checked: report.checked || 0 })
      : "-";
    renderReport(report);
    syncNowBtn.disabled = Boolean(statusData.running);
    syncNowBtn.textContent = statusData.running
      ? t("autosync.running", "Running...")
      : t("autosync.sync_now", "Sync now");
    schedule(statusData.running);
  }

  async function loadPaths() {
    try {
      const data = await apiFetch("/api/custom-paths");
      pathSelect.innerHTML = `<option value="">${t("index.default", "Default")}</option>` + (data.paths || []).map((path) =>
        `<option value="${path.id}">${esc(path.name)}</option>`
      ).join("");
    } catch (error) {
      showToast(error.message);
    }
  }

  async function loadSeries() {
    try {
      const data = await apiFetch("/api/autosync/series");
      const rows = data.series || [];
      if (!rows.length) {
        seriesBody.innerHTML = `<tr class="empty-row"><td colspan="5">${t("autosync.no_series", "No series added yet.")}</td></tr>`;
        return;
      }
      seriesBody.innerHTML = rows.map((row) => {
        const state = row.last_error
          ? `<span class="status-pill status-failed" title="${esc(row.last_error)}">${t("autosync.status.error", "Error")}</span>`
          : row.enabled
            ? `<span class="status-pill status-queued">${t("autosync.active", "Active")}</span>`
            : `<span class="status-pill status-cancelled">${t("autosync.paused", "Paused")}</span>`;
        const target = row.custom_path_name || t("index.default", "Default");
        return `<tr>
          <td><a href="${esc(row.series_url)}" target="_blank" rel="noopener noreferrer">${esc(row.title)}</a></td>
          <td>${esc(SITE_LABELS[row.site] || row.site)}</td>
          <td>${esc(row.language)}<br><span class="hint">${esc(target)} · ${esc(row.provider)}</span></td>
          <td>${state}<br><span class="hint">${esc(formatTime(row.last_checked_at))}</span></td>
          <td>
            <button class="btn btn-ghost" data-toggle="${row.id}" data-enabled="${row.enabled ? "1" : "0"}">${row.enabled ? t("autosync.pause", "Pause") : t("autosync.resume", "Resume")}</button>
            <button class="btn btn-danger" data-remove="${row.id}">${t("autosync.remove", "Remove")}</button>
          </td>
        </tr>`;
      }).join("");
    } catch (error) {
      showToast(error.message);
    }
  }

  async function searchTitles() {
    const keyword = searchInput.value.trim();
    if (!keyword) return;
    searchBtn.disabled = true;
    searchResults.innerHTML = `<div class="empty-state">${t("common.loading", "Loading...")}</div>`;
    try {
      const data = await apiSend("/api/search", "POST", { keyword, site: siteSelect.value });
      const results = data.results || [];
      if (!results.length) {
        searchResults.innerHTML = `<div class="empty-state">${t("autosync.no_matches", "No results found.")}</div>`;
      } else {
        searchResults.innerHTML = results.slice(0, 12).map((item) => {
          const title = decodeEntities(item.title);
          return `<div class="exclude-result">
            <span class="exclude-result-title" title="${esc(title)}">${esc(title)}</span>
            <button class="btn btn-ghost" data-add-url="${esc(item.url)}">${t("autosync.add", "Add")}</button>
          </div>`;
        }).join("");
      }
    } catch (error) {
      searchResults.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
    } finally {
      searchBtn.disabled = false;
    }
  }

  syncNowBtn.addEventListener("click", async () => {
    syncNowBtn.disabled = true;
    try {
      await apiSend("/api/autosync/run", "POST");
      showToast(t("autosync.started", "Auto-Sync started"));
      await loadStatus();
    } catch (error) {
      showToast(error.message);
      syncNowBtn.disabled = false;
    }
  });

  siteSelect.addEventListener("change", () => {
    updateLanguages();
    searchResults.innerHTML = "";
  });
  searchBtn.addEventListener("click", searchTitles);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchTitles();
  });

  searchResults.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-add-url]");
    if (!button) return;
    button.disabled = true;
    button.textContent = t("autosync.adding", "Checking ...");
    try {
      await apiSend("/api/autosync/series", "POST", {
        series_url: button.dataset.addUrl,
        language: languageSelect.value,
        provider: providerSelect.value,
        custom_path_id: pathSelect.value ? Number(pathSelect.value) : null
      });
      showToast(t("autosync.added_series", "Series added to Auto-Sync"));
      button.textContent = t("autosync.added_button", "Added");
      await loadSeries();
      await loadStatus();
    } catch (error) {
      showToast(error.message);
      button.disabled = false;
      button.textContent = t("autosync.add", "Add");
    }
  });

  seriesBody.addEventListener("click", async (event) => {
    const toggle = event.target.closest("[data-toggle]");
    const remove = event.target.closest("[data-remove]");
    try {
      if (toggle) {
        await apiSend(`/api/autosync/series/${toggle.dataset.toggle}`, "PATCH", {
          enabled: toggle.dataset.enabled !== "1"
        });
      } else if (remove) {
        await apiSend(`/api/autosync/series/${remove.dataset.remove}`, "DELETE");
      } else {
        return;
      }
      await loadSeries();
      await loadStatus();
    } catch (error) {
      showToast(error.message);
    }
  });

  Promise.all([loadStatus(), loadPaths(), loadSeries()]);
})();
