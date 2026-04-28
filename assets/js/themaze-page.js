(() => {
  const meta = document.getElementById("meta");
  const tableBody = document.querySelector("#table tbody");
  const alertSlot = document.getElementById("alert-slot");
  const refreshBtn = document.getElementById("btn-refresh");
  const sourceBtn = document.getElementById("btn-source");

  const SOURCE_URL = "http://themazenw.co.kr/adm/";
  const REFRESH_MS = 15000;
  let timer = null;
  let lastLoadedAt = null;

  function setMeta(text) {
    meta.textContent = text;
  }

  function setAlert(text) {
    alertSlot.innerHTML = text ? `<div class="alert">${text}</div>` : "";
  }

  function renderRows(rows) {
    if (!Array.isArray(rows) || !rows.length) {
      tableBody.innerHTML = `<tr><td class="empty">No data</td></tr>`;
      return;
    }
    tableBody.innerHTML = rows
      .map((row) => {
        const cells = (Array.isArray(row) ? row : []).map((cell) => {
          const value = String(cell || "").trim();
          return `<td class="${value ? "" : "empty"}">${value || ""}</td>`;
        });
        return `<tr>${cells.join("")}</tr>`;
      })
      .join("");
  }

  async function load() {
    refreshBtn.disabled = true;
    setAlert("");
    setMeta("Loading timetable...");
    try {
      const res = await fetch("/api/themaze/timetable", { credentials: "same-origin", cache: "no-store" });
      const data = await res.json();
      if (!res.ok) {
        renderRows([]);
        setMeta(data?.title ? `Source: ${data.title}` : "Failed to load source.");
        if (data?.authRequired) {
          setAlert("Source site requires admin login session. Configure THEMAZE_SOURCE_COOKIE on server to enable crawling.");
        } else {
          setAlert(data?.message || "Failed to load timetable.");
        }
        return;
      }
      renderRows(data.rows);
      lastLoadedAt = Date.now();
      setMeta(`Rows: ${data.rowCount} · Cols: ${data.colCount} · Updated: ${new Date(data.fetchedAt).toLocaleString()} · Auto refresh ${Math.floor(REFRESH_MS / 1000)}s`);
    } catch (_err) {
      renderRows([]);
      setMeta("Network error while loading timetable.");
      setAlert("Could not fetch timetable data from server.");
    } finally {
      refreshBtn.disabled = false;
    }
  }

  refreshBtn.addEventListener("click", load);
  sourceBtn.addEventListener("click", () => {
    window.open(SOURCE_URL, "_blank", "noopener,noreferrer");
  });

  load();
  timer = setInterval(() => {
    load();
  }, REFRESH_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") return;
    if (!lastLoadedAt || Date.now() - lastLoadedAt > REFRESH_MS) {
      load();
    }
  });
})();
