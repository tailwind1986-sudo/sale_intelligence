const state = {
  token: localStorage.getItem("sales_mobile_token") || "",
  today: new Date(),
  year: new Date().getFullYear(),
  month: new Date().getMonth() + 1,
  selectedDate: isoDate(new Date()),
  companies: [],
  companyId: "",
  schedules: [],
  meetings: [],
  editing: null,
};
const BASE = location.pathname.startsWith("/mobile") ? "/mobile" : "";

const $ = id => document.getElementById(id);

function isoDate(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDate(value) {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function show(screenId) {
  for (const node of document.querySelectorAll(".screen")) node.classList.add("hidden");
  $(screenId).classList.remove("hidden");
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("sales_mobile_token");
    state.token = "";
    show("login");
    throw new Error("로그인이 필요합니다.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "요청 실패");
  }
  return res.json();
}

async function login() {
  $("loginError").textContent = "";
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username: $("username").value, password: $("password").value }),
    });
    state.token = data.token || "";
    localStorage.setItem("sales_mobile_token", state.token);
    await bootstrap();
  } catch (err) {
    $("loginError").textContent = err.message;
  }
}

async function bootstrap() {
  state.companies = await api("/api/companies");
  renderCompanyFilters();
  await loadMonth();
  show("calendar");
}

function renderCompanyFilters() {
  const filters = [$("companyFilter"), $("scheduleCompany")];
  for (const select of filters) {
    select.innerHTML = `<option value="">전체/없음</option>` + state.companies.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("");
  }
}

async function loadMonth() {
  const params = new URLSearchParams({ year: state.year, month: state.month });
  if (state.companyId) params.set("company_id", state.companyId);
  const data = await api(`/api/calendar/month?${params}`);
  state.schedules = data.schedules;
  state.meetings = data.meetings;
  renderMonth();
  renderDay();
}

function renderMonth() {
  $("monthTitle").textContent = `${state.year}년 ${state.month}월`;
  $("monthSummary").textContent = `일정 ${state.schedules.length}건 · 미팅기록 ${state.meetings.length}건`;
  const grid = $("monthGrid");
  grid.innerHTML = "";
  const first = new Date(state.year, state.month - 1, 1);
  const lastDay = new Date(state.year, state.month, 0).getDate();
  const offset = (first.getDay() + 6) % 7;
  for (let i = 0; i < offset; i++) grid.appendChild(emptyCell());
  for (let day = 1; day <= lastDay; day++) {
    const d = new Date(state.year, state.month - 1, day);
    const iso = isoDate(d);
    const schedules = state.schedules.filter(s => s.start_date <= iso && s.end_date >= iso);
    const meetings = state.meetings.filter(m => m.meeting_date === iso);
    const cell = document.createElement("button");
    cell.className = "day-cell";
    if (iso === state.selectedDate) cell.classList.add("selected");
    if (iso === isoDate(new Date())) cell.classList.add("today");
    cell.innerHTML = `<div class="day-num">${day}</div><div class="badges">${schedules.length ? `<span class="badge schedule">${schedules.length}</span>` : ""}${meetings.length ? `<span class="badge meeting">${meetings.length}</span>` : ""}</div>`;
    cell.onclick = () => {
      state.selectedDate = iso;
      renderMonth();
      renderDay();
    };
    grid.appendChild(cell);
  }
}

function emptyCell() {
  const cell = document.createElement("div");
  cell.className = "day-cell empty";
  return cell;
}

function renderDay() {
  const d = parseLocalDate(state.selectedDate);
  $("dayTitle").textContent = `${d.getMonth() + 1}월 ${d.getDate()}일`;
  const schedules = state.schedules.filter(s => s.start_date <= state.selectedDate && s.end_date >= state.selectedDate);
  const meetings = state.meetings.filter(m => m.meeting_date === state.selectedDate);
  const wrap = $("dayItems");
  wrap.innerHTML = "";
  if (!schedules.length && !meetings.length) {
    wrap.innerHTML = `<p class="summary">등록된 일정이나 미팅 기록이 없습니다.</p>`;
    return;
  }
  for (const s of schedules) wrap.appendChild(scheduleButton(s));
  for (const m of meetings) wrap.appendChild(meetingButton(m));
}

function scheduleButton(s) {
  const btn = document.createElement("button");
  btn.className = "item";
  btn.style.borderLeftColor = s.color || "#2563eb";
  const time = s.all_day ? "종일" : `${s.start_time || ""} → ${s.end_time || ""}`;
  btn.innerHTML = `<div class="item-title">${escapeHtml(s.title)}</div><div class="item-meta">${time}${s.company_name ? " · " + escapeHtml(s.company_name) : ""}</div>`;
  btn.onclick = () => openScheduleDetail(s);
  return btn;
}

function meetingButton(m) {
  const btn = document.createElement("button");
  btn.className = "item meeting";
  btn.innerHTML = `<div class="item-title">미팅 · ${escapeHtml(m.company_name || "-")}</div><div class="item-meta">${escapeHtml(m.summary || m.meeting_type || "")}</div>`;
  btn.onclick = () => {
    $("detailContent").innerHTML = `<h2>미팅: ${escapeHtml(m.company_name || "-")}</h2><p class="summary">${m.meeting_date}</p><p>${escapeHtml(m.attendees || "")}</p><p>${escapeHtml(m.summary || "")}</p>`;
    show("detail");
  };
  return btn;
}

function openScheduleDetail(s) {
  $("detailContent").innerHTML = `
    <h2>${escapeHtml(s.title)}</h2>
    <p class="summary">${s.start_date}${s.end_date !== s.start_date ? " ~ " + s.end_date : ""}</p>
    <p>${s.all_day ? "종일" : `${s.start_time || ""} → ${s.end_time || ""}`}</p>
    <p>${escapeHtml(s.company_name || "")}</p>
    <p>${escapeHtml(s.description || "")}</p>
    <button class="primary" id="editFromDetail">수정</button>
  `;
  $("editFromDetail").onclick = () => openEditor(s);
  show("detail");
}

function openEditor(schedule = null) {
  state.editing = schedule;
  $("editorTitle").textContent = schedule ? "일정 수정" : "일정 추가";
  $("scheduleTitle").value = schedule?.title || "";
  $("scheduleDescription").value = schedule?.description || "";
  $("allDay").checked = schedule ? schedule.all_day : true;
  $("startDate").value = schedule?.start_date || state.selectedDate;
  $("endDate").value = schedule?.end_date || state.selectedDate;
  $("startTime").value = schedule?.start_time || "09:00";
  $("endTime").value = schedule?.end_time || "10:00";
  $("scheduleCompany").value = schedule?.company_id || "";
  $("scheduleColor").value = schedule?.color || "#2563EB";
  $("deleteSchedule").classList.toggle("hidden", !schedule);
  toggleTimeFields();
  show("editor");
}

function toggleTimeFields() {
  $("timeFields").classList.toggle("hidden", $("allDay").checked);
}

async function saveSchedule() {
  $("editorError").textContent = "";
  const payload = {
    title: $("scheduleTitle").value.trim(),
    description: $("scheduleDescription").value.trim() || null,
    start_date: $("startDate").value,
    end_date: $("endDate").value,
    start_time: $("allDay").checked ? null : $("startTime").value,
    end_time: $("allDay").checked ? null : $("endTime").value,
    all_day: $("allDay").checked,
    color: $("scheduleColor").value,
    company_id: $("scheduleCompany").value ? Number($("scheduleCompany").value) : null,
    remind_enabled: true,
    remind_minutes: 1440,
  };
  if (!payload.title) {
    $("editorError").textContent = "제목을 입력해주세요.";
    return;
  }
  try {
    if (state.editing) {
      await api(`/api/schedules/${state.editing.id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/schedules", { method: "POST", body: JSON.stringify(payload) });
    }
    state.selectedDate = payload.start_date;
    await loadMonth();
    show("calendar");
  } catch (err) {
    $("editorError").textContent = err.message;
  }
}

async function deleteSchedule() {
  if (!state.editing || !confirm("삭제할까요?")) return;
  await api(`/api/schedules/${state.editing.id}`, { method: "DELETE" });
  await loadMonth();
  show("calendar");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}

$("loginBtn").onclick = login;
$("prevMonth").onclick = async () => {
  if (state.month === 1) { state.year--; state.month = 12; } else state.month--;
  state.selectedDate = `${state.year}-${String(state.month).padStart(2, "0")}-01`;
  await loadMonth();
};
$("nextMonth").onclick = async () => {
  if (state.month === 12) { state.year++; state.month = 1; } else state.month++;
  state.selectedDate = `${state.year}-${String(state.month).padStart(2, "0")}-01`;
  await loadMonth();
};
$("companyFilter").onchange = async e => { state.companyId = e.target.value; await loadMonth(); };
$("addBtn").onclick = () => openEditor();
$("allDay").onchange = toggleTimeFields;
$("startDate").onchange = () => {
  if (!$("endDate").value || $("endDate").value < $("startDate").value) $("endDate").value = $("startDate").value;
};
$("saveSchedule").onclick = saveSchedule;
$("deleteSchedule").onclick = deleteSchedule;
for (const btn of document.querySelectorAll(".back")) btn.onclick = () => show(btn.dataset.target);

if ("serviceWorker" in navigator) navigator.serviceWorker.register(`${BASE}/static/sw.js`).catch(() => {});

if (state.token) bootstrap().catch(() => show("login"));
else show("login");
