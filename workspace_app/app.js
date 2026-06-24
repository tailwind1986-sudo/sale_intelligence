const BASE = location.pathname.startsWith("/mobile") ? "/mobile" : "";
const token = localStorage.getItem("sales_mobile_token") || "";

const $ = id => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

async function api(path) {
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) {
    location.href = `${BASE}/`;
    return null;
  }
  if (!res.ok) throw new Error("데이터를 불러오지 못했습니다.");
  return res.json();
}

function renderMetrics(metrics) {
  const items = [
    ["오늘 일정", metrics.today_schedules],
    ["7일 내 일정", metrics.week_schedules],
    ["마감 액션", metrics.due_actions],
    ["확인 약속", metrics.open_promises],
  ];
  $("metrics").innerHTML = items.map(([label, value]) => `
    <div class="metric"><strong>${value}</strong><span>${label}</span></div>
  `).join("");
}

function renderList(id, rows, type) {
  if (!rows.length) {
    $(id).innerHTML = `<p class="empty">표시할 항목이 없습니다.</p>`;
    return;
  }
  $(id).innerHTML = rows.map(row => {
    const date = row.date || row.due_date || "";
    const title = row.title || row.content || row.summary || "-";
    const metaParts = [row.company, row.time, row.assignee, row.promised_by, row.status].filter(Boolean);
    return `
      <div class="item ${type}">
        <div class="date">${escapeHtml(date)}</div>
        <div>
          <div class="title">${escapeHtml(title)}</div>
          <div class="meta">${escapeHtml(metaParts.join(" · "))}</div>
        </div>
      </div>
    `;
  }).join("");
}

async function load() {
  try {
    const data = await api("/api/dashboard");
    if (!data) return;
    renderMetrics(data.metrics || {});
    renderList("todaySchedules", data.today_schedules || [], "schedule");
    renderList("weekSchedules", data.week_schedules || [], "schedule");
    renderList("actions", data.actions || [], "action");
    renderList("promises", data.promises || [], "promise");
    renderList("meetings", data.recent_meetings || [], "meeting");
  } catch (err) {
    $("error").textContent = err.message;
  }
}

load();
