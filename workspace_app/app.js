const BASE = location.pathname.startsWith("/mobile") ? "/mobile" : "";
const token = localStorage.getItem("sales_mobile_token") || "";

const ACTION_STATUSES = ["전체", "예정", "진행중", "완료", "지연"];
const PROMISE_STATUSES = ["전체", "미확인", "진행중", "완료", "지연", "불이행"];

const state = {
  companies: [],
  actions: [],
  promises: [],
  view: "dashboard",
};

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

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    location.href = `${BASE}/`;
    return null;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "데이터를 불러오지 못했습니다.");
  }
  return res.json();
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
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
    const metaParts = [row.company, row.company_name, row.time, row.assignee, row.promised_by, row.status].filter(Boolean);
    return `
      <div class="item ${type} ${row.is_overdue ? "overdue" : ""}">
        <div class="date">${escapeHtml(date)}</div>
        <div>
          <div class="title">${escapeHtml(title)}</div>
          <div class="meta">${escapeHtml(metaParts.join(" · "))}</div>
        </div>
      </div>
    `;
  }).join("");
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  if (!data) return;
  renderMetrics(data.metrics || {});
  renderList("todaySchedules", data.today_schedules || [], "schedule");
  renderList("weekSchedules", data.week_schedules || [], "schedule");
  renderList("dashboardActions", data.actions || [], "action");
  renderList("dashboardPromises", data.promises || [], "promise");
  renderList("meetings", data.recent_meetings || [], "meeting");
}

function companyOptions(selected = "") {
  return [`<option value="">전체 고객사</option>`]
    .concat(state.companies.map(c => `<option value="${c.id}" ${String(selected) === String(c.id) ? "selected" : ""}>${escapeHtml(c.name)}</option>`))
    .join("");
}

function statusOptions(statuses, selected = "전체") {
  return statuses.map(s => `<option value="${s}" ${s === selected ? "selected" : ""}>${s}</option>`).join("");
}

function renderActionFilters() {
  $("actionStatus").innerHTML = statusOptions(ACTION_STATUSES, $("actionStatus").value || "전체");
  $("promiseStatus").innerHTML = statusOptions(PROMISE_STATUSES, $("promiseStatus").value || "전체");
  $("actionCompany").innerHTML = companyOptions($("actionCompany").value);
  $("promiseCompany").innerHTML = companyOptions($("promiseCompany").value);
}

async function loadActions() {
  const params = new URLSearchParams();
  params.set("status", $("actionStatus").value || "전체");
  if ($("actionCompany").value) params.set("company_id", $("actionCompany").value);
  if ($("actionAssignee").value.trim()) params.set("assignee", $("actionAssignee").value.trim());
  state.actions = await api(`/api/actions?${params}`) || [];
  renderActions();
}

async function loadPromises() {
  const params = new URLSearchParams();
  params.set("status", $("promiseStatus").value || "전체");
  if ($("promiseCompany").value) params.set("company_id", $("promiseCompany").value);
  state.promises = await api(`/api/promises?${params}`) || [];
  renderPromises();
}

function renderActions() {
  if (!state.actions.length) {
    $("actionList").innerHTML = `<p class="empty">액션아이템이 없습니다.</p>`;
    return;
  }
  $("actionList").innerHTML = state.actions.map(row => `
    <div class="manage-row ${row.is_overdue ? "overdue" : ""}">
      <div>
        <div class="title">${escapeHtml(row.content)}</div>
        <div class="meta">${escapeHtml([row.company_name, row.assignee || "담당자 없음", row.due_date || "기한 없음"].join(" · "))}</div>
      </div>
      <select data-action-status="${row.id}">${statusOptions(ACTION_STATUSES.filter(s => s !== "전체"), row.status || "예정")}</select>
      <button data-action-edit="${row.id}">수정</button>
      <button class="danger-btn" data-action-delete="${row.id}">삭제</button>
    </div>
  `).join("");
}

function renderPromises() {
  if (!state.promises.length) {
    $("promiseList").innerHTML = `<p class="empty">약속사항이 없습니다.</p>`;
    return;
  }
  $("promiseList").innerHTML = state.promises.map(row => `
    <div class="manage-row ${row.is_overdue ? "overdue" : ""}">
      <div>
        <div class="title">${escapeHtml(row.content)}</div>
        <div class="meta">${escapeHtml([row.company_name, row.promised_by || "약속자 없음", row.due_date || "기한 없음"].join(" · "))}</div>
      </div>
      <select data-promise-status="${row.id}">${statusOptions(PROMISE_STATUSES.filter(s => s !== "전체"), row.status || "미확인")}</select>
      <button data-promise-edit="${row.id}">수정</button>
      <button class="danger-btn" data-promise-delete="${row.id}">삭제</button>
    </div>
  `).join("");
}

function actionPayloadFromForm(form) {
  return {
    company_id: Number(form.company_id.value),
    content: form.content.value.trim(),
    assignee: form.assignee.value.trim() || null,
    due_date: form.due_date.value || null,
    status: form.status.value || "예정",
    notes: form.notes.value.trim() || null,
  };
}

function promisePayloadFromForm(form) {
  return {
    company_id: Number(form.company_id.value),
    content: form.content.value.trim(),
    promised_by: form.promised_by.value.trim() || null,
    promised_date: form.promised_date.value || null,
    due_date: form.due_date.value || null,
    status: form.status.value || "미확인",
    notes: form.notes.value.trim() || null,
  };
}

function showActionForm(row = null) {
  const form = $("actionForm");
  form.classList.remove("hidden");
  form.innerHTML = `
    <select name="company_id" required>${companyOptions(row?.company_id || "")}</select>
    <textarea name="content" placeholder="내용" required>${escapeHtml(row?.content || "")}</textarea>
    <input name="assignee" placeholder="담당자" value="${escapeHtml(row?.assignee || "")}" />
    <input name="due_date" type="date" value="${escapeHtml(row?.due_date || todayIso())}" />
    <select name="status">${statusOptions(ACTION_STATUSES.filter(s => s !== "전체"), row?.status || "예정")}</select>
    <input name="notes" placeholder="메모" value="${escapeHtml(row?.notes || "")}" />
    <div class="form-actions">
      <button type="submit" class="small-primary">저장</button>
      <button type="button" data-cancel-form>취소</button>
    </div>
  `;
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = actionPayloadFromForm(form);
    if (!payload.company_id || !payload.content) return;
    await api(row ? `/api/actions/${row.id}` : "/api/actions", {
      method: row ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    form.classList.add("hidden");
    await loadActions();
    await loadDashboard();
  };
}

function showPromiseForm(row = null) {
  const form = $("promiseForm");
  form.classList.remove("hidden");
  form.innerHTML = `
    <select name="company_id" required>${companyOptions(row?.company_id || "")}</select>
    <textarea name="content" placeholder="약속 내용" required>${escapeHtml(row?.content || "")}</textarea>
    <input name="promised_by" placeholder="약속한 사람" value="${escapeHtml(row?.promised_by || "")}" />
    <input name="promised_date" type="date" value="${escapeHtml(row?.promised_date || todayIso())}" />
    <input name="due_date" type="date" value="${escapeHtml(row?.due_date || todayIso())}" />
    <select name="status">${statusOptions(PROMISE_STATUSES.filter(s => s !== "전체"), row?.status || "미확인")}</select>
    <input name="notes" placeholder="메모" value="${escapeHtml(row?.notes || "")}" />
    <div class="form-actions">
      <button type="submit" class="small-primary">저장</button>
      <button type="button" data-cancel-form>취소</button>
    </div>
  `;
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = promisePayloadFromForm(form);
    if (!payload.company_id || !payload.content) return;
    await api(row ? `/api/promises/${row.id}` : "/api/promises", {
      method: row ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    form.classList.add("hidden");
    await loadPromises();
    await loadDashboard();
  };
}

function setView(view) {
  state.view = view;
  $("viewDashboard").classList.toggle("hidden", view !== "dashboard");
  $("viewActions").classList.toggle("hidden", view !== "actions");
  for (const btn of document.querySelectorAll(".tabs button")) {
    btn.classList.toggle("active", btn.dataset.view === view);
  }
  if (view === "actions") {
    loadActions();
    loadPromises();
  }
}

function bindEvents() {
  for (const btn of document.querySelectorAll(".tabs button")) {
    btn.onclick = () => setView(btn.dataset.view);
  }
  $("newActionBtn").onclick = () => showActionForm();
  $("newPromiseBtn").onclick = () => showPromiseForm();
  $("actionStatus").onchange = loadActions;
  $("actionCompany").onchange = loadActions;
  $("actionAssignee").oninput = () => {
    clearTimeout(window.__actionSearchTimer);
    window.__actionSearchTimer = setTimeout(loadActions, 250);
  };
  $("promiseStatus").onchange = loadPromises;
  $("promiseCompany").onchange = loadPromises;
  document.addEventListener("click", async event => {
    const target = event.target;
    if (target.matches("[data-cancel-form]")) target.closest("form").classList.add("hidden");
    const actionEdit = target.dataset.actionEdit;
    if (actionEdit) showActionForm(state.actions.find(row => String(row.id) === actionEdit));
    const promiseEdit = target.dataset.promiseEdit;
    if (promiseEdit) showPromiseForm(state.promises.find(row => String(row.id) === promiseEdit));
    const actionDelete = target.dataset.actionDelete;
    if (actionDelete && confirm("이 액션아이템을 삭제할까요?")) {
      await api(`/api/actions/${actionDelete}`, { method: "DELETE" });
      await loadActions();
      await loadDashboard();
    }
    const promiseDelete = target.dataset.promiseDelete;
    if (promiseDelete && confirm("이 약속사항을 삭제할까요?")) {
      await api(`/api/promises/${promiseDelete}`, { method: "DELETE" });
      await loadPromises();
      await loadDashboard();
    }
  });
  document.addEventListener("change", async event => {
    const actionId = event.target.dataset.actionStatus;
    if (actionId) {
      const row = state.actions.find(item => String(item.id) === actionId);
      await api(`/api/actions/${actionId}`, {
        method: "PUT",
        body: JSON.stringify({ ...row, company_id: row.company_id, status: event.target.value }),
      });
      await loadActions();
      await loadDashboard();
    }
    const promiseId = event.target.dataset.promiseStatus;
    if (promiseId) {
      const row = state.promises.find(item => String(item.id) === promiseId);
      await api(`/api/promises/${promiseId}`, {
        method: "PUT",
        body: JSON.stringify({ ...row, company_id: row.company_id, status: event.target.value }),
      });
      await loadPromises();
      await loadDashboard();
    }
  });
}

async function load() {
  try {
    state.companies = await api("/api/companies") || [];
    renderActionFilters();
    bindEvents();
    await loadDashboard();
  } catch (err) {
    $("error").textContent = err.message;
  }
}

load();
