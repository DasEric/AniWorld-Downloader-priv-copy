/* Auto-Sync page: explicit tracked-series list, status and last report. */

(function () {
  const el = (id) => document.getElementById(id);
  const syncNowBtn = el("syncNowBtn");
  const seriesBody = el("seriesBody");

  const IDLE_POLL = 30000;
  const RUNNING_POLL = 3000;
  const SITE_LABELS = { aniworld: "AniWorld", sto: "SerienStream" };
  let timer = null;

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
    let statusData;
    try {
      statusData = await apiFetch("/api/autosync/status");
    } catch (_error) {
      schedule(false);
      return;
    }

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

  Promise.all([loadStatus(), loadSeries()]);
})();
