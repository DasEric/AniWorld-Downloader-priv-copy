(function () {
  const el = (id) => document.getElementById(id);
  const poster = (path) =>
    typeof path === "string" && /^\/[A-Za-z0-9._/-]+$/.test(path)
      ? `https://image.tmdb.org/t/p/w342${path}`
      : "";

  function movieCard(movie) {
    const posterUrl = poster(movie.poster_path);
    return `<article class="upcoming-card">${posterUrl ? `<img src="${posterUrl}" alt="" loading="lazy">` : ""}<div><h3>${esc(movie.title)}</h3><p class="hint">${esc(movie.release_date || "")}</p><p>${esc((movie.overview || "").slice(0, 220))}</p><button class="btn btn-primary" data-add="${movie.tmdb_id}">${t("common.add", "Add")}</button></div></article>`;
  }

  async function load() {
    const data = await apiFetch("/api/upcoming");
    el("tmdbMissing").hidden = data.configured;
    el("upcomingSchedule").textContent = data.next_run ? `${t("upcoming.next", "Next check")}: ${new Date(data.next_run).toLocaleString()}` : "";
    el("upcomingList").innerHTML = data.items.length ? data.items.map((movie) => {
      const canToggle = ["waiting", "error", "paused"].includes(movie.status);
      const toggle = canToggle ? `<button class="btn btn-ghost" data-toggle="${movie.id}" data-status="${movie.status === "paused" ? "waiting" : "paused"}">${movie.status === "paused" ? "Resume" : "Pause"}</button>` : "";
      return `<div class="upcoming-row"><div><strong>${esc(movie.title)}</strong><div class="hint">${esc(movie.release_date)} · ${esc(movie.status)}${movie.last_message ? ` · ${esc(movie.last_message)}` : ""}</div></div><div class="action-row">${toggle}<button class="icon-btn" data-delete="${movie.id}" aria-label="Remove">×</button></div></div>`;
    }).join("") : `<div class="empty-state">${t("upcoming.empty", "No movies are being watched.")}</div>`;
  }

  async function results(url) {
    try { const data = await apiFetch(url); el("upcomingResults").innerHTML = (data.items || []).map(movieCard).join(""); }
    catch (error) { showToast(error.message); }
  }
  el("searchUpcomingBtn").addEventListener("click", () => results(`/api/upcoming/tmdb/search?q=${encodeURIComponent(el("upcomingSearch").value.trim())}`));
  el("browseUpcomingBtn").addEventListener("click", () => results("/api/upcoming/tmdb/movies"));
  el("upcomingResults").addEventListener("click", async (event) => { const button = event.target.closest("[data-add]"); if (!button) return; try { await apiSend("/api/upcoming", "POST", {tmdb_id: Number(button.dataset.add)}); showToast(t("upcoming.added", "Added")); load(); } catch (error) { showToast(error.message); } });
  el("upcomingList").addEventListener("click", async (event) => { const toggle = event.target.closest("[data-toggle]"); const remove = event.target.closest("[data-delete]"); try { if (toggle) await apiSend(`/api/upcoming/${toggle.dataset.toggle}`, "PATCH", {status: toggle.dataset.status}); if (remove) await apiSend(`/api/upcoming/${remove.dataset.delete}`, "DELETE"); if (toggle || remove) load(); } catch (error) { showToast(error.message); } });
  el("checkUpcomingBtn").addEventListener("click", async () => { try { await apiSend("/api/upcoming/run", "POST"); showToast(t("upcoming.started", "Check started")); setTimeout(load, 1200); } catch (error) { showToast(error.message); } });
  load().catch((error) => showToast(error.message));
})();
