const REMIND_OPTIONS = [
  ["0", "시작 시간"],
  ["10", "10분 전"],
  ["30", "30분 전"],
  ["60", "1시간 전"],
  ["180", "3시간 전"],
  ["1440", "하루 전"],
  ["10080", "일주일 전"],
];

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
  endDateTouched: false,
  endTimeTouched: false,
};

const BASE = location.pathname.startsWith("/mobile") ? "/mobile" : "";
const $ = id => document.getElementById(id);

function consumeUrlAuth() {
  const url = new URL(location.href);
  const token = url.searchParams.get("auth");
  if (!token) return false;
  state.token = token;
  localStorage.setItem("sales_mobile_token", token);
  url.searchParams.delete("auth");
  history.replaceState({}, "", url.pathname + url.search + url.hash);
  return true;
}

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function parseLocalDate(value) {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function addDays(value, days) {
  const d = parseLocalDate(value);
  d.setDate(d.getDate() + days);
  return isoDate(d);
}

function formatKoreanDate(value, withWeekday = false) {
  const d = parseLocalDate(value);
  const weekday = "일월화수목금토"[d.getDay()];
  return withWeekday ? `${d.getMonth() + 1}월 ${d.getDate()}일 ${weekday}요일` : `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

function toAmpm(value) {
  if (!value) return "";
  const [h, m] = value.split(":").map(Number);
  const part = h < 12 ? "오전" : "오후";
  const hour = h % 12 || 12;
  return `${part} ${hour}:${String(m).padStart(2, "0")}`;
}

function addOneHour(timeValue) {
  const [h, m] = String(timeValue || "09:00").split(":").map(Number);
  const total = h * 60 + m + 60;
  const nextDay = total >= 24 * 60;
  const minutes = total % (24 * 60);
  return {
    time: `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`,
    nextDay,
  };
}

function timeLabel(item) {
  if (item.kind === "meeting") return "미팅\n기록";
  if (item.all_day) return "종일";
  return `${toAmpm(item.start_time)}\n${toAmpm(item.end_time)}`;
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
    throw new Error(body.detail || "요청에 실패했습니다.");
  }
  return res.json();
}

async function login(event) {
  if (event) event.preventDefault();
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
  renderReminderOptions();
  await loadMonth();
  show("calendar");
}

function renderCompanyFilters() {
  const companyOptions = state.companies.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("");
  $("companyFilter").innerHTML = `<option value="">전체 고객사</option>${companyOptions}`;
  $("scheduleCompany").innerHTML = `<option value="">캘린더/고객사 없음</option>${companyOptions}`;
}

function renderReminderOptions() {
  $("remindMinutes").innerHTML = REMIND_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
}

async function loadMonth() {
  const params = new URLSearchParams({ year: state.year, month: state.month });
  if (state.companyId) params.set("company_id", state.companyId);
  const data = await api(`/api/calendar/month?${params}`);
  state.schedules = data.schedules || [];
  state.meetings = data.meetings || [];
  renderMonth();
  renderDay();
}

function renderMonth() {
  $("monthJump").textContent = `${state.year}년 ${state.month}월`;
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
    const items = itemsForDay(iso);
    const cell = document.createElement("button");
    cell.className = "day-cell";
    if (iso === state.selectedDate) cell.classList.add("selected");
    if (iso === isoDate(new Date())) cell.classList.add("today");
    cell.innerHTML = `<div class="day-num">${day}</div>${renderMonthChips(items, iso)}`;
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

function renderMonthChips(items, iso) {
  const visible = items.slice(0, 3).map(item => {
    const color = item.kind === "meeting" ? "#14B8A6" : item.color || "#3B82F6";
    const segment = chipSegment(item, iso);
    const text = segment.showTitle ? escapeHtml(item.title) : "&nbsp;";
    const cls = ["event-chip", item.kind === "meeting" ? "meeting-chip" : "", segment.className].filter(Boolean).join(" ");
    return `<span class="${cls}" style="background:${escapeAttr(color)}">${text}</span>`;
  }).join("");
  const more = items.length > 3 ? `<span class="more-chip">+${items.length - 3}</span>` : "";
  return visible + more;
}

function chipSegment(item, iso) {
  if (item.kind !== "schedule" || item.start_date === item.end_date) {
    return { className: "single", showTitle: true };
  }
  const day = parseLocalDate(iso).getDay();
  const weekStart = day === 1;
  const weekEnd = day === 0;
  const isStart = iso === item.start_date || weekStart;
  const isEnd = iso === item.end_date || weekEnd;
  let className = "mid";
  if (isStart && isEnd) className = "single";
  else if (isStart) className = "start";
  else if (isEnd) className = "end";
  return { className, showTitle: isStart };
}

function itemsForDay(iso) {
  const schedules = state.schedules
    .filter(s => s.start_date <= iso && s.end_date >= iso)
    .map(s => ({ ...s, kind: "schedule" }));
  const meetings = state.meetings
    .filter(m => m.meeting_date === iso)
    .map(m => ({
      ...m,
      kind: "meeting",
      title: `미팅 · ${m.company_name || "-"}`,
      description: m.summary || m.meeting_type || "",
      all_day: true,
      color: "#14B8A6",
    }));
  return [...schedules, ...meetings].sort(compareItems);
}

function compareItems(a, b) {
  if (a.kind !== b.kind && a.kind === "meeting") return 1;
  if (a.kind !== b.kind && b.kind === "meeting") return -1;
  if (a.all_day !== b.all_day) return a.all_day ? -1 : 1;
  return String(a.start_time || "00:00").localeCompare(String(b.start_time || "00:00"));
}

function renderDay() {
  const items = itemsForDay(state.selectedDate);
  $("dayTitle").textContent = formatKoreanDate(state.selectedDate, true);
  $("daySubtitle").textContent = `일정 ${items.filter(i => i.kind === "schedule").length}건 · 미팅 ${items.filter(i => i.kind === "meeting").length}건`;
  const wrap = $("dayItems");
  wrap.innerHTML = "";
  if (!items.length) {
    wrap.innerHTML = `<p class="summary">선택한 날짜의 일정이나 미팅 기록이 없습니다.</p>`;
    return;
  }
  for (const item of items) wrap.appendChild(itemButton(item));
}

function itemButton(item) {
  const btn = document.createElement("button");
  btn.className = "item";
  const color = item.kind === "meeting" ? "#14B8A6" : item.color || "#3B82F6";
  btn.innerHTML = `
    <div class="item-time">${escapeHtml(timeLabel(item)).replace(/\n/g, "<br>")}</div>
    <div class="item-line" style="background:${escapeAttr(color)}"></div>
    <div>
      <div class="item-title">${escapeHtml(item.title)}</div>
      <div class="item-meta">${escapeHtml(item.description || item.company_name || "")}</div>
    </div>
    ${avatarGroup(item.company_name || item.attendees || item.title)}
  `;
  btn.onclick = () => item.kind === "meeting" ? openMeetingDetail(item) : openScheduleDetail(item);
  return btn;
}

function avatarGroup(seed) {
  const names = String(seed || "-").split(/[,\s/]+/).filter(Boolean).slice(0, 3);
  const colors = ["#F59E0B", "#EF4444", "#A855F7", "#14B8A6"];
  return `<div class="avatars">${names.map((name, idx) => `<span class="avatar" style="background:${colors[idx % colors.length]}">${escapeHtml(name.slice(0, 1))}</span>`).join("")}</div>`;
}

function openMeetingDetail(m) {
  $("editFromDetail").classList.add("hidden");
  $("detailContent").innerHTML = `
    ${avatarGroup(m.company_name || m.attendees)}
    <h1 class="detail-title">미팅기록 · ${escapeHtml(m.company_name || "-")}</h1>
    <div class="detail-row"><span>날짜</span><strong>${escapeHtml(formatKoreanDate(m.meeting_date, true))}</strong></div>
    <div class="detail-row"><span>유형</span><strong>${escapeHtml(m.meeting_type || "-")}</strong></div>
    <div class="detail-row"><span>참석자</span><strong>${escapeHtml(m.attendees || "-")}</strong></div>
    <p class="detail-muted">${escapeHtml(m.summary || "요약 정보가 없습니다.")}</p>
  `;
  show("detail");
}

function openScheduleDetail(s) {
  state.editing = s;
  $("editFromDetail").classList.remove("hidden");
  $("editFromDetail").onclick = () => openEditor(s);
  const startText = s.all_day ? "종일" : toAmpm(s.start_time);
  const endText = s.all_day ? "종일" : toAmpm(s.end_time);
  const remindText = s.remind_enabled ? (REMIND_OPTIONS.find(([v]) => Number(v) === Number(s.remind_minutes))?.[1] || `${s.remind_minutes}분 전`) : "알림 없음";
  $("detailContent").innerHTML = `
    ${avatarGroup(s.company_name || s.title)}
    <h1 class="detail-title">${escapeHtml(s.title)}</h1>
    <div class="detail-time">
      <div><span>${escapeHtml(formatKoreanDate(s.start_date, true))}</span><strong>${escapeHtml(startText)}</strong></div>
      <div style="color:var(--accent);font-size:2rem;">›</div>
      <div><span>${escapeHtml(formatKoreanDate(s.end_date, true))}</span><strong>${escapeHtml(endText)}</strong></div>
    </div>
    <div class="detail-row"><span>알림</span><strong>${escapeHtml(remindText)}</strong></div>
    <div class="detail-row"><span>고객사</span><strong>${escapeHtml(s.company_name || "없음")}</strong></div>
    <div class="detail-row"><span>분류</span><strong>출장/외근/미팅</strong></div>
    <p class="detail-muted">${escapeHtml(s.description || "")}</p>
  `;
  show("detail");
}

function openEditor(schedule = null) {
  state.editing = schedule;
  state.endDateTouched = Boolean(schedule);
  state.endTimeTouched = Boolean(schedule);
  $("scheduleTitle").value = schedule?.title || "";
  $("scheduleDescription").value = schedule?.description || "";
  $("allDay").checked = schedule ? schedule.all_day : false;
  $("startDate").value = schedule?.start_date || state.selectedDate;
  $("endDate").value = schedule?.end_date || state.selectedDate;
  $("startTime").value = schedule?.start_time || "09:00";
  $("endTime").value = schedule?.end_time || "10:00";
  $("scheduleCompany").value = schedule?.company_id || "";
  $("scheduleColor").value = schedule?.color || "#3B82F6";
  $("remindEnabled").checked = schedule ? Boolean(schedule.remind_enabled) : true;
  $("remindMinutes").value = String(schedule?.remind_minutes || 1440);
  $("deleteSchedule").classList.toggle("hidden", !schedule);
  if (!schedule) {
    syncEndDateToStart(true);
    syncEndTimeToStart(true);
  }
  toggleTimeFields();
  show("editor");
}

function toggleTimeFields() {
  const allDay = $("allDay").checked;
  $("startTime").classList.toggle("hidden", allDay);
  $("endTime").classList.toggle("hidden", allDay);
}

function syncEndDateToStart(force = false) {
  const start = $("startDate").value;
  if (force || !state.endDateTouched || !$("endDate").value || $("endDate").value < start) {
    $("endDate").value = start;
  }
}

function syncEndTimeToStart(force = false) {
  if ($("allDay").checked) return;
  if (!force && state.endTimeTouched) return;
  const next = addOneHour($("startTime").value);
  $("endTime").value = next.time;
  if (next.nextDay && !state.endDateTouched) $("endDate").value = addDays($("startDate").value, 1);
  if (!next.nextDay && !state.endDateTouched) $("endDate").value = $("startDate").value;
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
    remind_enabled: $("remindEnabled").checked,
    remind_minutes: Number($("remindMinutes").value || 1440),
  };
  if (!payload.title) {
    $("editorError").textContent = "제목을 입력해주세요.";
    return;
  }
  if (payload.end_date < payload.start_date) {
    $("editorError").textContent = "종료일은 시작일보다 빠를 수 없습니다.";
    return;
  }
  try {
    if (state.editing) {
      await api(`/api/schedules/${state.editing.id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/schedules", { method: "POST", body: JSON.stringify(payload) });
    }
    state.selectedDate = payload.start_date;
    state.year = parseLocalDate(payload.start_date).getFullYear();
    state.month = parseLocalDate(payload.start_date).getMonth() + 1;
    await loadMonth();
    show("calendar");
  } catch (err) {
    $("editorError").textContent = err.message;
  }
}

async function deleteSchedule() {
  if (!state.editing || !confirm("이 일정을 삭제할까요?")) return;
  await api(`/api/schedules/${state.editing.id}`, { method: "DELETE" });
  await loadMonth();
  show("calendar");
}

function goToday() {
  const today = new Date();
  state.year = today.getFullYear();
  state.month = today.getMonth() + 1;
  state.selectedDate = isoDate(today);
  loadMonth();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}

function escapeAttr(value) {
  return String(value ?? "").replace(/["'<>]/g, "");
}

$("loginForm").addEventListener("submit", login);
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
$("monthJump").onclick = goToday;
$("todayBtn").onclick = goToday;
$("companyFilter").onchange = async e => { state.companyId = e.target.value; await loadMonth(); };
$("addBtn").onclick = () => openEditor();
$("allDay").onchange = () => { toggleTimeFields(); syncEndTimeToStart(true); };
$("startDate").onchange = () => { syncEndDateToStart(true); syncEndTimeToStart(true); };
$("endDate").onchange = () => { state.endDateTouched = true; };
$("startTime").onchange = () => syncEndTimeToStart(true);
$("endTime").onchange = () => { state.endTimeTouched = true; };
$("saveSchedule").onclick = saveSchedule;
$("deleteSchedule").onclick = deleteSchedule;
for (const btn of document.querySelectorAll(".back")) btn.onclick = () => show(btn.dataset.target);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register(`${BASE}/static/sw.js?v=20260624-tt2`).then(reg => reg.update()).catch(() => {});
}

consumeUrlAuth();
if (state.token) bootstrap().catch(() => show("login"));
else show("login");
