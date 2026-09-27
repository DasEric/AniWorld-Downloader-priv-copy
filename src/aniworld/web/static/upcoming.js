/* Upcoming page: TMDB search, explicit watchlist and daily-check status. */

(function () {
  const el = (id) => document.getElementById(id);
  const checkBtn = el("checkUpcomingBtn");
  const searchBtn = el("searchUpcomingBtn");
  const browseBtn = el("browseUpcomingBtn");
  const searchInput = el("upcomingSearch");
  const resultsBox = el("upcomingResults");
  const listBody = el("upcomingList");

  const STATUS_CLASS = {
    waiting: "status-queued",
    checking: "status-queued",
    queued: "status-completed",
    downloaded: "status-completed",
    paused: "status-cancelled",
    error: "status-failed"
  };

  const STATUS_LABELS = {
    waiting: "Waiting",
    checking: "Checking",
    queued: "Queued",
    downloaded: "Downloaded",
    paused: "Paused",
    error: "Error"
  };

  function statusLabel(status) {
    return t(`upcoming.state.${status}`, STATUS_LABELS[status] || status);
  }

  function formatTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
  }

  function poster(path) {
    return typeof path === "string" && /^\/[A-Za-z0-9._/-]+$/.test(path)
      ? `https://image.tmdb.org/t/p/w342${path}`
      : "";
  }

  function movieCard(movie) {
    const posterUrl = poster(movie.poster_path);
    return `<article class="poster-card upcoming-result-card">
      ${posterUrl ? `<img src="${posterUrl}" alt="" loading="lazy">` : `<div class="upcoming-poster-placeholder" aria-hidden="true">&#127916;</div>`}
      <div class="info">
        <div class="title" title="${esc(movie.title)}">${esc(movie.title)}</div>
        <div class="subtitle">${esc(movie.release_date || t("upcoming.release_unknown", "Release unknown"))}</div>
        <button class="btn btn-primary upcoming-add-btn" data-add="${Number(movie.tmdb_id)}">${t("common.add", "Add")}</button>
      </div>
    </article>`;
  }

  function renderResults(items) {
    resultsBox.hidden = false;
    resultsBox.innerHTML = items.length
      ? items.map(movieCard).join("")
      : `<div class="empty-state">${t("upcoming.no_results", "No upcoming movies found.")}</div>`;
  }

  function renderWatchlist(items) {
    if (!items.length) {
      listBody.innerHTML = `<tr class="empty-row"><td colspan="4">${t("upcoming.empty", "No movies are being watched.")}</td></tr>`;
      return;
    }

    listBody.innerHTML = items.map((movie) => {
      const canToggle = ["waiting", "error", "paused"].includes(movie.status);
      const toggle = canToggle
        ? `<button class="btn btn-ghost" data-toggle="${movie.id}" data-status="${movie.status === "paused" ? "waiting" : "paused"}">${movie.status === "paused" ? t("upcoming.resume", "Resume") : t("upcoming.pause", "Pause")}</button>`
        : "";
      const message = movie.last_message
        ? `<div class="hint upcoming-row-message" title="${esc(movie.last_message)}">${esc(movie.last_message)}</div>`
        : "";
      return `<tr>
        <td><strong>${esc(movie.title)}</strong>${message}</td>
        <td>${esc(movie.release_date || "-")}</td>
        <td><span class="status-pill ${STATUS_CLASS[movie.status] || "status-queued"}">${esc(statusLabel(movie.status))}</span></td>
        <td class="upcoming-actions">${toggle}<button class="btn btn-danger" data-delete="${movie.id}">${t("common.remove", "Remove")}</button></td>
      </tr>`;
    }).join("");
  }

  async function load() {
    const data = await apiFetch("/api/upcoming");
    const configured = Boolean(data.configured);
    el("tmdbMissing").hidden = configured;
    el("upcomingTmdbState").textContent = configured
      ? t("upcoming.configured", "Configured")
      : t("upcoming.not_configured", "Not configured");
    el("upcomingCount").textContent = String((data.items || []).length);
    el("upcomingLastRun").textContent = formatTime(data.last_run);
    el("upcomingNextRun").textContent = formatTime(data.next_run);
    [checkBtn, searchBtn, browseBtn, searchInput].forEach((node) => {
      node.disabled = !configured;
    });
    renderWatchlist(data.items || []);
  }

  async function loadResults(url, button) {
    button.disabled = true;
    resultsBox.hidden = false;
    resultsBox.innerHTML = `<div class="empty-state">${t("common.loading", "Loading...")}</div>`;
    try {
      const data = await apiFetch(url);
      renderResults(data.items || []);
    } catch (error) {
      resultsBox.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
      showToast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  function search() {
    const query = searchInput.value.trim();
    if (query.length < 2) {
      showToast(t("upcoming.search_short", "Enter at least two characters."));
      searchInput.focus();
      return;
    }
    loadResults(`/api/upcoming/tmdb/search?q=${encodeURIComponent(query)}`, searchBtn);
  }

  searchBtn.addEventListener("click", search);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") search();
  });
  browseBtn.addEventListener("click", () => loadResults("/api/upcoming/tmdb/movies", browseBtn));

  resultsBox.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-add]");
    if (!button) return;
    button.disabled = true;
    try {
      await apiSend("/api/upcoming", "POST", { tmdb_id: Number(button.dataset.add) });
      showToast(t("upcoming.added", "Added"));
      await load();
      button.textContent = t("upcoming.added", "Added");
    } catch (error) {
      showToast(error.message);
      button.disabled = false;
    }
  });

  listBody.addEventListener("click", async (event) => {
    const toggle = event.target.closest("[data-toggle]");
    const remove = event.target.closest("[data-delete]");
    try {
      if (toggle) {
        await apiSend(`/api/upcoming/${toggle.dataset.toggle}`, "PATCH", { status: toggle.dataset.status });
      } else if (remove) {
        await apiSend(`/api/upcoming/${remove.dataset.delete}`, "DELETE");
      } else {
        return;
      }
      await load();
    } catch (error) {
      showToast(error.message);
    }
  });

  checkBtn.addEventListener("click", async () => {
    checkBtn.disabled = true;
    try {
      await apiSend("/api/upcoming/run", "POST");
      showToast(t("upcoming.started", "Check started"));
      setTimeout(() => load().catch(() => {}), 1200);
    } catch (error) {
      showToast(error.message);
    } finally {
      checkBtn.disabled = false;
    }
  });

  load().catch((error) => showToast(error.message));
})();
