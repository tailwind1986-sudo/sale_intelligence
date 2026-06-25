const NAV_BASE = location.pathname.startsWith("/mobile") ? "/mobile" : "";
let token = localStorage.getItem("sales_mobile_token") || "";
let eventsBound = false;

const ACTION_STATUSES = ["전체", "예정", "진행중", "완료", "지연"];
const PROMISE_STATUSES = ["전체", "미확인", "진행중", "완료", "지연", "불이행"];
const BUSINESS_TYPES = ["전체", "CSO", "TLD", "기타"];
const SALES_STAGES = ["전체", "잠재", "접촉", "제안", "협상", "계약", "완료", "보류"];
const IMPORTANCE = ["전체", "높음", "보통", "낮음"];
const INFO_CATEGORIES = ["생일", "취향", "가족사항", "주요이슈", "알레르기/금기", "선물내역", "기타"];

const state = {
  companies: [],
  companyRows: [],
  selectedCompany: null,
  actions: [],
  promises: [],
  candidates: [],
  meetings: [],
  selectedMeeting: null,
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
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("sales_mobile_token");
    token = "";
    showWorkspaceLogin("로그인이 필요합니다.");
    throw new Error("로그인이 필요합니다.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "데이터를 불러오지 못했습니다.");
  }
  return res.json();
}

async function apiForm(path, formData) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { method: "POST", headers, body: formData });
  if (res.status === 401) {
    localStorage.removeItem("sales_mobile_token");
    token = "";
    showWorkspaceLogin("로그인이 필요합니다.");
    throw new Error("로그인이 필요합니다.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "요청 처리에 실패했습니다.");
  }
  return res.json();
}

function showWorkspaceLogin(message = "") {
  $("workspaceLogin").classList.remove("hidden");
  document.querySelector(".app-layout").classList.add("hidden");
  $("workspaceLoginError").textContent = message;
  setTimeout(() => $("workspacePassword")?.focus(), 0);
}

function hideWorkspaceLogin() {
  $("workspaceLogin").classList.add("hidden");
  document.querySelector(".app-layout").classList.remove("hidden");
  $("workspaceLoginError").textContent = "";
}

async function loginWorkspace(event) {
  event.preventDefault();
  $("workspaceLoginError").textContent = "";
  const form = event.currentTarget;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: form.username.value.trim(),
        password: form.password.value,
      }),
    });
    if (!res.ok) throw new Error("아이디 또는 비밀번호가 올바르지 않습니다.");
    const data = await res.json();
    token = data.token || "";
    localStorage.setItem("sales_mobile_token", token);
    hideWorkspaceLogin();
    await load();
  } catch (err) {
    $("workspaceLoginError").textContent = err.message;
  }
}

function bindWorkspaceLogin() {
  $("workspaceLoginForm").onsubmit = loginWorkspace;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function renderMetrics(metrics) {
  const items = [
    ["오늘", "일정", metrics.today_schedules],
    ["7일", "예정", metrics.week_schedules],
    ["마감", "액션", metrics.due_actions],
    ["확인", "약속", metrics.open_promises],
  ];
  $("metrics").innerHTML = items.map(([kicker, label, value]) => `
    <div class="metric">
      <span>${kicker}</span>
      <strong>${value ?? 0}</strong>
      <em>${label}</em>
    </div>
  `).join("");
}

function emptyState(title, action = "") {
  return `
    <div class="empty-state">
      <strong>${escapeHtml(title)}</strong>
      ${action ? `<span>${escapeHtml(action)}</span>` : ""}
    </div>
  `;
}

function badge(text, tone = "neutral") {
  return `<span class="badge ${tone}">${escapeHtml(text || "-")}</span>`;
}

function statusTone(status = "") {
  if (status.includes("지연") || status.includes("불이행")) return "danger";
  if (status.includes("완료")) return "done";
  if (status.includes("진행")) return "active";
  return "neutral";
}

function dashboardCard(row, type) {
  const date = row.date || row.due_date || "";
  const title = row.title || row.content || row.summary || "-";
  const company = row.company || row.company_name || "";
  const timeText = row.time || "";
  const people = row.assignee || row.promised_by || "";
  const status = row.status || "";
  const meta = [company, timeText, people].filter(Boolean).join(" · ");
  const tone = row.is_overdue ? "danger" : statusTone(status);
  return `
    <div class="dash-item ${type} ${row.is_overdue ? "overdue" : ""}">
      <div class="dash-main">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(meta || date || "세부 정보 없음")}</span>
      </div>
      <div class="dash-side">
        ${date ? `<time>${escapeHtml(date)}</time>` : ""}
        ${status ? badge(status, tone) : ""}
      </div>
    </div>
  `;
}

function renderList(id, rows, type) {
  if (!rows.length) {
    const emptyMessages = {
      schedule: ["예정된 일정이 없습니다", "새 일정이 생기면 여기에 표시됩니다."],
      action: ["마감 액션이 없습니다", "급한 후속 조치가 없어요."],
      promise: ["확인할 약속이 없습니다", "미확인 약속이 생기면 알려드립니다."],
      meeting: ["최근 미팅이 없습니다", "회의록을 업로드하면 요약이 쌓입니다."],
    };
    const [title, action] = emptyMessages[type] || ["표시할 항목이 없습니다", ""];
    $(id).innerHTML = emptyState(title, action);
    return;
  }
  $(id).innerHTML = rows.map(row => dashboardCard(row, type)).join("");
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

function plainOptions(values, selected = "") {
  return values.map(value => `<option value="${value}" ${String(value) === String(selected) ? "selected" : ""}>${escapeHtml(value)}</option>`).join("");
}

function renderActionFilters() {
  $("actionStatus").innerHTML = statusOptions(ACTION_STATUSES, $("actionStatus").value || "전체");
  $("promiseStatus").innerHTML = statusOptions(PROMISE_STATUSES, $("promiseStatus").value || "전체");
  $("actionCompany").innerHTML = companyOptions($("actionCompany").value);
  $("promiseCompany").innerHTML = companyOptions($("promiseCompany").value);
}

function renderCompanyFilters() {
  $("companyTypeFilter").innerHTML = plainOptions(BUSINESS_TYPES, $("companyTypeFilter").value || "전체");
  $("companyStageFilter").innerHTML = plainOptions(SALES_STAGES, $("companyStageFilter").value || "전체");
  $("companyRiskFilter").innerHTML = plainOptions(IMPORTANCE, $("companyRiskFilter").value || "전체");
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
    $("actionList").innerHTML = emptyState("액션아이템이 없습니다", "새 액션을 추가하거나 미팅을 분석하면 자동으로 표시됩니다.");
    return;
  }
  $("actionList").innerHTML = state.actions.map(row => `
    <div class="task-card ${row.is_overdue ? "overdue" : ""}">
      <div class="task-body">
        <div class="task-topline">
          ${badge(row.status || "예정", statusTone(row.status))}
          ${row.is_overdue ? badge("기한 초과", "danger") : ""}
          ${row.due_date ? `<time>${escapeHtml(row.due_date)}</time>` : `<time>기한 없음</time>`}
        </div>
        <strong>${escapeHtml(row.content)}</strong>
        <span>${escapeHtml([row.company_name, row.assignee || "담당자 미정"].filter(Boolean).join(" · "))}</span>
        ${row.notes ? `<p>${escapeHtml(row.notes)}</p>` : ""}
      </div>
      <div class="task-actions">
        <select data-action-status="${row.id}">${statusOptions(ACTION_STATUSES.filter(s => s !== "전체"), row.status || "예정")}</select>
        <button data-action-calendar="${row.id}" class="accept-btn">수락</button>
        <button data-action-edit="${row.id}">수정</button>
        <button class="danger-btn" data-action-delete="${row.id}">삭제</button>
      </div>
    </div>
  `).join("");
}

function actionScheduleDraft(row) {
  const scheduleDate = row.due_date || todayIso();
  const description = [
    row.company_name ? `고객사: ${row.company_name}` : "",
    row.assignee ? `담당자: ${row.assignee}` : "",
    row.status ? `액션 상태: ${row.status}` : "",
    row.notes ? `메모: ${row.notes}` : "",
  ].filter(Boolean).join("\n");
  return {
    source: "action_item",
    source_id: row.id,
    title: row.content || "액션아이템",
    description,
    start_date: scheduleDate,
    end_date: scheduleDate,
    start_time: "09:00",
    end_time: "10:00",
    all_day: true,
    color: "#2563EB",
    company_id: row.company_id || null,
    remind_enabled: true,
    remind_minutes: 1440,
  };
}

function openCalendarDraft(draft) {
  localStorage.setItem("sales_schedule_draft", JSON.stringify(draft));
  setView("calendar");
  const frame = document.getElementById("calendarFrame");
  if (frame) {
    frame.dataset.loaded = "1";
    const auth = token ? `auth=${encodeURIComponent(token)}&` : "";
    frame.src = `/mobile/?${auth}draft=${Date.now()}`;
  }
}

function renderPromises() {
  if (!state.promises.length) {
    $("promiseList").innerHTML = emptyState("약속사항이 없습니다", "고객에게 받은 약속이나 확인 필요 항목이 표시됩니다.");
    return;
  }
  $("promiseList").innerHTML = state.promises.map(row => `
    <div class="task-card promise ${row.is_overdue ? "overdue" : ""}">
      <div class="task-body">
        <div class="task-topline">
          ${badge(row.status || "미확인", statusTone(row.status))}
          ${row.is_overdue ? badge("확인 지연", "danger") : ""}
          ${row.due_date ? `<time>${escapeHtml(row.due_date)}</time>` : `<time>기한 없음</time>`}
        </div>
        <strong>${escapeHtml(row.content)}</strong>
        <span>${escapeHtml([row.company_name, row.promised_by || "약속자 미정"].filter(Boolean).join(" · "))}</span>
        ${row.notes ? `<p>${escapeHtml(row.notes)}</p>` : ""}
      </div>
      <div class="task-actions">
        <select data-promise-status="${row.id}">${statusOptions(PROMISE_STATUSES.filter(s => s !== "전체"), row.status || "미확인")}</select>
        <button data-promise-edit="${row.id}">수정</button>
        <button class="danger-btn" data-promise-delete="${row.id}">삭제</button>
      </div>
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

async function loadCompanies() {
  const params = new URLSearchParams();
  if ($("companySearch").value.trim()) params.set("q", $("companySearch").value.trim());
  params.set("business_type", $("companyTypeFilter").value || "전체");
  params.set("sales_stage", $("companyStageFilter").value || "전체");
  params.set("risk_level", $("companyRiskFilter").value || "전체");
  state.companyRows = await api(`/api/workspace/companies?${params}`) || [];
  renderCompanies();
}

function renderCompanies() {
  if (!state.companyRows.length) {
    $("companyList").innerHTML = `<p class="empty">고객사가 없습니다.</p>`;
    $("companyDetail").innerHTML = "";
    return;
  }
  $("companyList").innerHTML = state.companyRows.map(row => `
    <button class="company-card" data-company-open="${row.id}">
      <strong>${escapeHtml(row.name)}</strong>
      <span>${escapeHtml([row.business_type || "-", row.sales_stage || "-", row.risk_level || "-"].join(" · "))}</span>
      <small>미팅 ${row.meeting_count} · 액션 ${row.action_count} · 약속 ${row.promise_count}</small>
    </button>
  `).join("");
}

function companyPayloadFromForm(form) {
  return {
    name: form.name.value.trim(),
    business_type: form.business_type.value || null,
    industry: form.industry.value.trim() || null,
    address: form.address.value.trim() || null,
    website: form.website.value.trim() || null,
    sales_stage: form.sales_stage.value || null,
    expected_revenue: form.expected_revenue.value ? Number(form.expected_revenue.value) : null,
    importance: form.importance.value || null,
    risk_level: form.risk_level.value || null,
    memo: form.memo.value.trim() || null,
  };
}

function showCompanyForm(row = null) {
  const form = $("companyForm");
  form.classList.remove("hidden");
  form.innerHTML = `
    <input name="name" placeholder="고객사명" required value="${escapeHtml(row?.name || "")}" />
    <select name="business_type">${plainOptions(["", "CSO", "TLD", "기타"], row?.business_type || "")}</select>
    <input name="industry" placeholder="산업/업종" value="${escapeHtml(row?.industry || "")}" />
    <input name="address" placeholder="주소" value="${escapeHtml(row?.address || "")}" />
    <input name="website" placeholder="웹사이트" value="${escapeHtml(row?.website || "")}" />
    <select name="sales_stage">${plainOptions(["", "잠재", "접촉", "제안", "협상", "계약", "완료", "보류"], row?.sales_stage || "")}</select>
    <input name="expected_revenue" type="number" min="0" placeholder="예상매출" value="${escapeHtml(row?.expected_revenue || "")}" />
    <select name="importance">${plainOptions(["", "높음", "보통", "낮음"], row?.importance || "")}</select>
    <select name="risk_level">${plainOptions(["", "높음", "보통", "낮음"], row?.risk_level || "")}</select>
    <textarea name="memo" placeholder="메모">${escapeHtml(row?.memo || "")}</textarea>
    <div class="form-actions">
      <button type="submit" class="small-primary">저장</button>
      <button type="button" data-cancel-form>취소</button>
    </div>
  `;
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = companyPayloadFromForm(form);
    if (!payload.name) return;
    const saved = await api(row ? `/api/workspace/companies/${row.id}` : "/api/workspace/companies", {
      method: row ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    form.classList.add("hidden");
    await refreshCompanyOptions();
    await loadCompanies();
    if (saved?.id) await openCompany(saved.id);
  };
}

function contactPayloadFromForm(form, companyId) {
  return {
    company_id: companyId,
    name: form.name.value.trim(),
    position: form.position.value.trim() || null,
    phone: form.phone.value.trim() || null,
    email: form.email.value.trim() || null,
    birthday: form.birthday.value.trim() || null,
    is_primary: form.is_primary.checked,
    notes: form.notes.value.trim() || null,
  };
}

function infoPayloadFromForm(form, companyId) {
  return {
    company_id: companyId,
    contact_id: form.contact_id.value ? Number(form.contact_id.value) : null,
    category: form.category.value || null,
    key: form.key.value.trim(),
    value: form.value.value.trim(),
    importance: form.importance.value || "보통",
    notes: form.notes.value.trim() || null,
  };
}

async function openCompany(companyId) {
  const detail = await api(`/api/workspace/companies/${companyId}`);
  if (!detail) return;
  state.selectedCompany = detail;
  $("companyDetail").innerHTML = renderCompanyDetail(detail);
}

function renderCompanyDetail(c) {
  return `
    <div class="detail-head">
      <div>
        <h3>${escapeHtml(c.name)}</h3>
        <p>${escapeHtml([c.business_type || "-", c.sales_stage || "-", c.risk_level || "-"].join(" · "))}</p>
      </div>
      <div class="row-actions">
        <button data-company-edit="${c.id}">수정</button>
        <button class="danger-btn" data-company-delete="${c.id}">삭제</button>
      </div>
    </div>
    <p class="meta">${escapeHtml(c.memo || "메모 없음")}</p>
    <div class="detail-section">
      <div class="panel-head"><h3>담당자</h3><button data-contact-new="${c.id}" class="small-primary">추가</button></div>
      <div id="contactFormSlot"></div>
      ${(c.contacts || []).map(row => `
        <div class="mini-row">
          <div><strong>${row.is_primary ? "★ " : ""}${escapeHtml(row.name)}</strong><span>${escapeHtml([row.position, row.phone, row.email].filter(Boolean).join(" · "))}</span></div>
          <div class="row-actions"><button data-contact-edit="${row.id}">수정</button><button class="danger-btn" data-contact-delete="${row.id}">삭제</button></div>
        </div>
      `).join("") || `<p class="empty">담당자가 없습니다.</p>`}
    </div>
    <div class="detail-section">
      <div class="panel-head"><h3>고객 정보</h3><button data-info-new="${c.id}" class="small-primary">추가</button></div>
      <div id="infoFormSlot"></div>
      ${(c.customer_infos || []).map(row => `
        <div class="mini-row">
          <div><strong>[${escapeHtml(row.category || "기타")}] ${escapeHtml(row.key)}</strong><span>${escapeHtml(row.value)} ${row.contact_name ? " · " + escapeHtml(row.contact_name) : ""}</span></div>
          <div class="row-actions"><button data-info-edit="${row.id}">수정</button><button class="danger-btn" data-info-delete="${row.id}">삭제</button></div>
        </div>
      `).join("") || `<p class="empty">고객 정보가 없습니다.</p>`}
    </div>
    <div class="detail-section">
      <h3>최근 미팅</h3>
      ${(c.recent_meetings || []).map(row => `<div class="mini-row"><div><strong>${escapeHtml(row.date)}</strong><span>${escapeHtml(row.summary || "-")}</span></div></div>`).join("") || `<p class="empty">최근 미팅이 없습니다.</p>`}
    </div>
  `;
}

function showContactForm(row = null) {
  const c = state.selectedCompany;
  const slot = $("contactFormSlot");
  slot.innerHTML = `
    <form class="inline-form" id="contactInlineForm">
      <input name="name" placeholder="이름" required value="${escapeHtml(row?.name || "")}" />
      <input name="position" placeholder="직책" value="${escapeHtml(row?.position || "")}" />
      <input name="phone" placeholder="연락처" value="${escapeHtml(row?.phone || "")}" />
      <input name="email" placeholder="이메일" value="${escapeHtml(row?.email || "")}" />
      <input name="birthday" placeholder="생일" value="${escapeHtml(row?.birthday || "")}" />
      <label class="check"><input name="is_primary" type="checkbox" ${row?.is_primary ? "checked" : ""} /> 주담당자</label>
      <input name="notes" placeholder="메모" value="${escapeHtml(row?.notes || "")}" />
      <div class="form-actions"><button class="small-primary" type="submit">저장</button><button type="button" data-clear-slot="contactFormSlot">취소</button></div>
    </form>
  `;
  $("contactInlineForm").onsubmit = async event => {
    event.preventDefault();
    const payload = contactPayloadFromForm(event.target, c.id);
    if (!payload.name) return;
    await api(row ? `/api/workspace/contacts/${row.id}` : "/api/workspace/contacts", {
      method: row ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    await openCompany(c.id);
  };
}

function showInfoForm(row = null) {
  const c = state.selectedCompany;
  const slot = $("infoFormSlot");
  const contactOptions = [`<option value="">고객사 전체</option>`]
    .concat((c.contacts || []).map(contact => `<option value="${contact.id}" ${String(row?.contact_id || "") === String(contact.id) ? "selected" : ""}>${escapeHtml(contact.name)}</option>`))
    .join("");
  slot.innerHTML = `
    <form class="inline-form" id="infoInlineForm">
      <select name="category">${plainOptions(INFO_CATEGORIES, row?.category || "기타")}</select>
      <input name="key" placeholder="항목명" required value="${escapeHtml(row?.key || "")}" />
      <textarea name="value" placeholder="내용" required>${escapeHtml(row?.value || "")}</textarea>
      <select name="contact_id">${contactOptions}</select>
      <select name="importance">${plainOptions(["높음", "보통", "낮음"], row?.importance || "보통")}</select>
      <input name="notes" placeholder="메모" value="${escapeHtml(row?.notes || "")}" />
      <div class="form-actions"><button class="small-primary" type="submit">저장</button><button type="button" data-clear-slot="infoFormSlot">취소</button></div>
    </form>
  `;
  $("infoInlineForm").onsubmit = async event => {
    event.preventDefault();
    const payload = infoPayloadFromForm(event.target, c.id);
    if (!payload.key || !payload.value) return;
    await api(row ? `/api/workspace/customer-infos/${row.id}` : "/api/workspace/customer-infos", {
      method: row ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    await openCompany(c.id);
  };
}

async function loadCandidates() {
  const stateFilter = $("candidateState").value || "pending";
  state.candidates = await api(`/api/schedule-candidates?state=${encodeURIComponent(stateFilter)}`) || [];
  renderCandidates();
}

function renderCandidates() {
  if (!state.candidates.length) {
    $("candidateList").innerHTML = `<p class="empty">검토할 일정 후보가 없습니다.</p>`;
    return;
  }
  $("candidateList").innerHTML = state.candidates.map((row, idx) => {
    const c = row.candidate || {};
    return `
      <form class="candidate-card" data-candidate-form="${idx}">
        <div class="candidate-head">
          <div>
            <strong>${escapeHtml(c.title || "일정 후보")}</strong>
            <span>${escapeHtml([row.company, row.meeting_date, row.state].filter(Boolean).join(" · "))}</span>
          </div>
        </div>
        <input name="title" placeholder="일정 제목" value="${escapeHtml(c.title || "")}" />
        <div class="two-cols">
          <input name="date" type="date" value="${escapeHtml(c.date || "")}" />
          <input name="end_date" type="date" value="${escapeHtml(c.end_date || c.date || "")}" />
        </div>
        <input name="project" placeholder="관련 프로젝트" value="${escapeHtml(c.project || "")}" />
        <input name="assignee" placeholder="담당자" value="${escapeHtml(c.assignee || "")}" />
        <input name="location" placeholder="장소" value="${escapeHtml(c.location || "")}" />
        <textarea name="note" placeholder="비고/근거">${escapeHtml(c.note || "")}</textarea>
        <div class="form-actions">
          <button class="small-primary" type="submit">일정표에 저장</button>
          <button type="button" data-candidate-ignore="${idx}">무시</button>
        </div>
      </form>
    `;
  }).join("");
}

function candidatePayloadFromForm(form) {
  return {
    title: form.title.value.trim(),
    date: form.date.value || null,
    end_date: form.end_date.value || form.date.value || null,
    project: form.project.value.trim() || null,
    assignee: form.assignee.value.trim() || null,
    location: form.location.value.trim() || null,
    note: form.note.value.trim() || null,
  };
}

async function loadMeetings() {
  const params = new URLSearchParams();
  if ($("meetingSearch").value.trim()) params.set("q", $("meetingSearch").value.trim());
  if ($("meetingCompany").value) params.set("company_id", $("meetingCompany").value);
  state.meetings = await api(`/api/meetings?${params}`) || [];
  renderMeetings();
}

function renderMeetings() {
  if (!state.meetings.length) {
    $("meetingList").innerHTML = `<p class="empty">미팅 기록이 없습니다.</p>`;
    $("meetingDetail").innerHTML = "";
    return;
  }
  $("meetingList").innerHTML = state.meetings.map(row => `
    <button class="company-card" data-meeting-open="${row.id}">
      <strong>${escapeHtml(row.company)}</strong>
      <span>${escapeHtml([row.meeting_date, row.meeting_type, row.has_analysis ? "분석완료" : "미분석"].filter(Boolean).join(" · "))}</span>
      <small>${escapeHtml(row.summary || "요약 없음")}</small>
    </button>
  `).join("");
}

async function openMeeting(meetingId) {
  const detail = await api(`/api/meetings/${meetingId}`);
  if (!detail) return;
  state.selectedMeeting = detail;
  $("meetingDetail").innerHTML = renderMeetingDetail(detail);
}

function listBlock(title, rows, formatter = item => String(item)) {
  const body = rows && rows.length
    ? rows.map(item => `<li>${escapeHtml(formatter(item))}</li>`).join("")
    : `<li class="empty">없음</li>`;
  return `<div class="detail-section"><h3>${title}</h3><ul>${body}</ul></div>`;
}

function renderTopic(item) {
  if (typeof item === "object") {
    return `${item.topic || "주제"}: ${item.discussion || item.current_status || item.needs_review || "-"}`;
  }
  return String(item);
}

function renderMeetingDetail(m) {
  const a = m.analysis;
  if (!a) {
    return `
      <div class="detail-head">
        <div><h3>${escapeHtml(m.company)}</h3><p>${escapeHtml(m.meeting_date || "-")}</p></div>
        <div class="row-actions">
          <button data-meeting-analyze="${m.id}">AI 분석</button>
          <button class="danger-btn" data-meeting-delete="${m.id}">삭제</button>
        </div>
      </div>
      <p class="empty">아직 AI 분석 결과가 없습니다. 업로드/AI 분석 단계에서 분석을 실행하세요.</p>
      <div class="detail-section"><h3>원문</h3><p class="meta">${escapeHtml((m.raw_text || "").slice(0, 600))}</p></div>
    `;
  }
  return `
    <div class="detail-head">
      <div>
        <h3>${escapeHtml(m.company)}</h3>
        <p>${escapeHtml([m.meeting_date, m.meeting_type, `신뢰 ${a.trust_score}`, `위험 ${a.risk_score}`].filter(Boolean).join(" · "))}</p>
      </div>
      <div class="row-actions">
        <button data-meeting-analyze="${m.id}">전체 재분석</button>
        <button data-meeting-schedule-analyze="${m.id}">일정 재추출</button>
        <button class="danger-btn" data-meeting-delete="${m.id}">삭제</button>
      </div>
    </div>
    <p class="title">${escapeHtml(a.one_line_summary || "한 줄 결론 없음")}</p>
    <div class="detail-section"><h3>전체 요약</h3><p>${escapeHtml(a.detailed_summary || "-")}</p></div>
    ${listBlock("핵심 논의", a.topic_discussions || [], renderTopic)}
    ${listBlock("결정사항", a.decisions || [])}
    ${listBlock("후속조치", a.action_items_structured || [], item => typeof item === "object" ? `${item.task || item.content || "-"} / ${item.assignee || "담당자 확인"} / ${item.due_date || "기한 확인"}` : String(item))}
    ${listBlock("리스크/확인", a.risks_and_checks || [])}
    <div class="detail-section">
      <h3>카톡/문자 보고</h3>
      <textarea readonly>${escapeHtml(m.compact_report || "")}</textarea>
    </div>
    <div class="detail-section">
      <h3>고객 관계 정보</h3>
      ${(a.relationship_notes || []).map((row, idx) => `
        <div class="mini-row">
          <div><strong>${escapeHtml(row.person_or_company || "-")}</strong><span>${escapeHtml([row.category, row.content, row.use_point].filter(Boolean).join(" · "))}</span></div>
          <button data-relation-save="${idx}" class="small-primary">고객정보 저장</button>
        </div>
      `).join("") || `<p class="empty">추출된 고객 관계 정보가 없습니다.</p>`}
    </div>
    <div class="detail-section"><h3>원문</h3><p class="meta">${escapeHtml((m.raw_text || "").slice(0, 1000))}</p></div>
  `;
}

function resetUploadForm() {
  const form = $("uploadForm");
  form.reset();
  form.meeting_date.value = todayIso();
  form.run_ai.checked = true;
  $("uploadResult").innerHTML = "";
}

async function submitUpload(event) {
  event.preventDefault();
  const form = $("uploadForm");
  const formData = new FormData(form);
  formData.set("run_ai", form.run_ai.checked ? "true" : "false");
  $("uploadResult").innerHTML = `<p class="empty">저장 중입니다. AI 분석을 실행하면 30초 이상 걸릴 수 있습니다.</p>`;
  const result = await apiForm("/api/meetings/upload", formData);
  if (!result) return;
  if (result.ai_error) {
    $("uploadResult").innerHTML = `<p class="error">회의록은 저장됐지만 AI 분석은 실패했습니다: ${escapeHtml(result.ai_error)}</p>`;
  } else {
    $("uploadResult").innerHTML = `<p class="notice">미팅 기록이 저장되었습니다.</p>`;
  }
  await loadMeetings();
  setView("meetings");
  if (result.id) await openMeeting(result.id);
  resetUploadForm();
  await loadDashboard();
}

async function runSearch(event) {
  if (event) event.preventDefault();
  const query = $("searchInput").value.trim();
  if (query.length < 2) {
    $("searchResults").innerHTML = `<p class="empty">두 글자 이상 입력하세요.</p>`;
    return;
  }
  $("searchResults").innerHTML = `<p class="empty">검색 중입니다.</p>`;
  const result = await api(`/api/search?q=${encodeURIComponent(query)}`);
  renderSearchResults(result || { groups: [], total: 0 });
}

function renderSearchResults(result) {
  if (!result.total) {
    $("searchResults").innerHTML = `<p class="empty">검색 결과가 없습니다.</p>`;
    return;
  }
  $("searchResults").innerHTML = `
    <p class="meta">총 ${result.total}건</p>
    ${(result.groups || []).map(group => `
      <section class="result-group">
        <h3>${escapeHtml(group.label)} (${group.items.length})</h3>
        ${group.items.map(item => {
          const openAttr = group.type === "meetings"
            ? `data-search-meeting="${item.id}"`
            : (group.type === "companies" || group.type === "contacts")
              ? `data-search-company="${item.company_id || item.id}"`
              : "";
          return `
            <button class="search-row" ${openAttr}>
              <strong>${escapeHtml(item.title || "-")}</strong>
              <span>${escapeHtml(item.meta || "")}</span>
              <small>${escapeHtml(item.snippet || "")}</small>
            </button>
          `;
        }).join("")}
      </section>
    `).join("")}
  `;
}

async function loadRisk() {
  const params = new URLSearchParams();
  if ($("riskCompany").value) params.set("company_id", $("riskCompany").value);
  const data = await api(`/api/risk?${params}`) || { rows: [], selected: null };
  renderRisk(data);
  await loadTelegramStatus();
}

function riskClass(score) {
  if (score >= 70) return "high";
  if (score >= 40) return "mid";
  return "low";
}

function renderRisk(data) {
  $("riskCompany").innerHTML = companyOptions($("riskCompany").value || data.selected?.id || "");
  if (!data.rows.length) {
    $("riskScoreboard").innerHTML = `<p class="empty">고객사를 먼저 등록하세요.</p>`;
    $("riskDetail").innerHTML = "";
    return;
  }
  $("riskScoreboard").innerHTML = data.rows.map(row => `
    <button class="risk-card ${riskClass(row.composite)}" data-risk-company="${row.id}">
      <strong>${escapeHtml(row.composite)}</strong>
      <span>${escapeHtml(row.company)}</span>
      <small>AI위험 ${row.avg_risk} · 신뢰 ${row.avg_trust} · 지연액션 ${row.overdue_actions}</small>
    </button>
  `).join("");
  const selected = data.selected;
  if (!selected) return;
  $("riskCompany").value = selected.id;
  $("riskDetail").innerHTML = `
    <div class="detail-head">
      <div>
        <h3>${escapeHtml(selected.company)}</h3>
        <p>현재 리스크 등급</p>
      </div>
      <div class="row-actions">
        <select id="riskLevelSelect">
          ${["높음", "보통", "낮음"].map(level => `<option value="${level}" ${selected.risk_level === level ? "selected" : ""}>${level}</option>`).join("")}
        </select>
        <button class="small-primary" data-risk-save="${selected.id}">저장</button>
      </div>
    </div>
    ${listBlock("누적 리스크 요인", selected.risk_factors || [])}
    ${listBlock("불만/우려사항", selected.complaints || [])}
    ${listBlock("경쟁사 언급", selected.competitors || [])}
    ${listBlock("불이행 약속", selected.breaches || [], item => typeof item === "object" ? `${item.content} / ${item.due_date || "기한 없음"}` : String(item))}
    ${listBlock("위험/신뢰 추이", selected.trend || [], item => `${item.date}: 위험 ${item.risk} / 신뢰 ${item.trust}`)}
  `;
}

async function loadTelegramStatus() {
  const status = await api("/api/telegram/status");
  if (!status) return;
  if (status.configured) {
    $("telegramStatus").textContent = `텔레그램 연동 완료 (Chat ID: ${status.chat_id})`;
  } else {
    $("telegramStatus").textContent = `텔레그램 미설정: Token ${status.has_token ? "OK" : "없음"} / Chat ID ${status.has_chat_id ? "OK" : "없음"}`;
  }
}

async function runTelegramAction(action) {
  $("telegramResult").textContent = "요청 처리 중입니다.";
  const result = await api(`/api/telegram/${action}`, { method: "POST" });
  if (!result) return;
  if (action === "check-reminders") {
    $("telegramResult").textContent = `알림 체크 완료: ${result.sent || 0}건 전송`;
  } else {
    $("telegramResult").textContent = result.ok ? "전송 완료" : "전송할 내용이 없거나 설정이 부족합니다.";
  }
}

async function refreshCompanyOptions() {
  state.companies = await api("/api/companies") || [];
  renderActionFilters();
  $("meetingCompany").innerHTML = companyOptions($("meetingCompany").value);
  $("uploadCompany").innerHTML = companyOptions($("uploadCompany").value);
  $("riskCompany").innerHTML = companyOptions($("riskCompany").value);
}

function setView(view) {
  state.view = view;
  $("viewDashboard").classList.toggle("hidden", view !== "dashboard");
  $("viewActions").classList.toggle("hidden", view !== "actions");
  $("viewCompanies").classList.toggle("hidden", view !== "companies");
  $("viewCandidates").classList.toggle("hidden", view !== "candidates");
  $("viewMeetings").classList.toggle("hidden", view !== "meetings");
  $("viewUpload").classList.toggle("hidden", view !== "upload");
  $("viewSearch").classList.toggle("hidden", view !== "search");
  $("viewRisk").classList.toggle("hidden", view !== "risk");
  $("viewCalendar").classList.toggle("hidden", view !== "calendar");
  if (view === "calendar") {
    const frame = document.getElementById("calendarFrame");
    if (!frame.dataset.loaded) {
      frame.dataset.loaded = "1";
      frame.src = token ? `/mobile/?auth=${encodeURIComponent(token)}` : "/mobile/";
    }
  }
  const titles = {
    dashboard: "대시보드", actions: "액션 / 약속", companies: "고객사",
    candidates: "일정 후보", meetings: "미팅 요약", upload: "미팅 업로드",
    search: "통합 검색", risk: "리스크 / 설정", calendar: "캘린더",
  };
  const titleEl = $("pageTitle");
  if (titleEl) titleEl.textContent = titles[view] || view;
  for (const btn of document.querySelectorAll(".nav-item[data-view]")) {
    btn.classList.toggle("active", btn.dataset.view === view);
  }
  if (view === "actions") {
    loadActions();
    loadPromises();
  }
  if (view === "companies") loadCompanies();
  if (view === "candidates") loadCandidates();
  if (view === "upload") resetUploadForm();
  if (view === "meetings") loadMeetings();
  if (view === "risk") loadRisk();
}

function bindSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const hamburger = document.getElementById("hamburger");
  const closeBtn = document.getElementById("sidebarClose");

  function openSidebar() {
    sidebar.classList.add("open");
    overlay.classList.add("open");
  }
  function closeSidebar() {
    sidebar.classList.remove("open");
    overlay.classList.remove("open");
  }

  hamburger?.addEventListener("click", openSidebar);
  closeBtn?.addEventListener("click", closeSidebar);
  overlay?.addEventListener("click", closeSidebar);
}

function bindEvents() {
  for (const btn of document.querySelectorAll(".nav-item[data-view]")) {
    btn.onclick = () => {
      setView(btn.dataset.view);
      // 모바일에서 메뉴 선택 시 사이드바 닫기
      if (window.innerWidth <= 768) {
        document.getElementById("sidebar")?.classList.remove("open");
        document.getElementById("sidebarOverlay")?.classList.remove("open");
      }
    };
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
  $("newCompanyBtn").onclick = () => showCompanyForm();
  $("companySearch").oninput = () => {
    clearTimeout(window.__companySearchTimer);
    window.__companySearchTimer = setTimeout(loadCompanies, 250);
  };
  $("companyTypeFilter").onchange = loadCompanies;
  $("companyStageFilter").onchange = loadCompanies;
  $("companyRiskFilter").onchange = loadCompanies;
  $("candidateState").onchange = loadCandidates;
  $("meetingCompany").onchange = loadMeetings;
  $("meetingSearch").oninput = () => {
    clearTimeout(window.__meetingSearchTimer);
    window.__meetingSearchTimer = setTimeout(loadMeetings, 250);
  };
  $("uploadForm").onsubmit = submitUpload;
  $("clearUploadBtn").onclick = resetUploadForm;
  $("searchForm").onsubmit = runSearch;
  $("searchInput").oninput = () => {
    clearTimeout(window.__searchTimer);
    window.__searchTimer = setTimeout(runSearch, 350);
  };
  $("riskCompany").onchange = loadRisk;
  document.addEventListener("click", async event => {
    const target = event.target;
    if (target.matches("[data-cancel-form]")) target.closest("form").classList.add("hidden");
    const clearSlot = target.dataset.clearSlot;
    if (clearSlot) $(clearSlot).innerHTML = "";
    const actionEdit = target.dataset.actionEdit;
    if (actionEdit) showActionForm(state.actions.find(row => String(row.id) === actionEdit));
    const actionCalendar = target.dataset.actionCalendar;
    if (actionCalendar) {
      const row = state.actions.find(item => String(item.id) === actionCalendar);
      if (row) openCalendarDraft(actionScheduleDraft(row));
    }
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
    const companyOpen = target.closest("[data-company-open]")?.dataset.companyOpen;
    if (companyOpen) await openCompany(companyOpen);
    const companyEdit = target.dataset.companyEdit;
    if (companyEdit) showCompanyForm(state.selectedCompany);
    const companyDelete = target.dataset.companyDelete;
    if (companyDelete && confirm("이 고객사를 삭제할까요? 관련 미팅/약속/액션도 함께 삭제됩니다.")) {
      await api(`/api/workspace/companies/${companyDelete}`, { method: "DELETE" });
      $("companyDetail").innerHTML = "";
      await refreshCompanyOptions();
      await loadCompanies();
    }
    const contactNew = target.dataset.contactNew;
    if (contactNew) showContactForm();
    const contactEdit = target.dataset.contactEdit;
    if (contactEdit) showContactForm(state.selectedCompany.contacts.find(row => String(row.id) === contactEdit));
    const contactDelete = target.dataset.contactDelete;
    if (contactDelete && confirm("이 담당자를 삭제할까요?")) {
      await api(`/api/workspace/contacts/${contactDelete}`, { method: "DELETE" });
      await openCompany(state.selectedCompany.id);
    }
    const infoNew = target.dataset.infoNew;
    if (infoNew) showInfoForm();
    const infoEdit = target.dataset.infoEdit;
    if (infoEdit) showInfoForm(state.selectedCompany.customer_infos.find(row => String(row.id) === infoEdit));
    const infoDelete = target.dataset.infoDelete;
    if (infoDelete && confirm("이 고객 정보를 삭제할까요?")) {
      await api(`/api/workspace/customer-infos/${infoDelete}`, { method: "DELETE" });
      await openCompany(state.selectedCompany.id);
    }
    const candidateIgnore = target.dataset.candidateIgnore;
    if (candidateIgnore) {
      const row = state.candidates[Number(candidateIgnore)];
      await api(`/api/schedule-candidates/${row.meeting_id}/${row.index}/ignore`, { method: "POST" });
      await loadCandidates();
    }
    const meetingOpen = target.closest("[data-meeting-open]")?.dataset.meetingOpen;
    if (meetingOpen) await openMeeting(meetingOpen);
    const relationSave = target.dataset.relationSave;
    if (relationSave && state.selectedMeeting) {
      await api(`/api/meetings/${state.selectedMeeting.id}/relationship-notes/${relationSave}/save`, { method: "POST" });
      alert("고객 정보로 저장했습니다.");
    }
    const meetingAnalyze = target.dataset.meetingAnalyze;
    if (meetingAnalyze && confirm("이 미팅 기록을 전체 재분석할까요? 기존에 직접 수정한 액션/약속은 유지됩니다.")) {
      await api(`/api/meetings/${meetingAnalyze}/analyze`, { method: "POST" });
      await openMeeting(meetingAnalyze);
      await loadMeetings();
      await loadCandidates();
    }
    const meetingScheduleAnalyze = target.dataset.meetingScheduleAnalyze;
    if (meetingScheduleAnalyze && confirm("이 미팅 기록에서 일정 후보만 다시 추출할까요?")) {
      await api(`/api/meetings/${meetingScheduleAnalyze}/analyze?schedule_only=true`, { method: "POST" });
      await openMeeting(meetingScheduleAnalyze);
      await loadCandidates();
    }
    const meetingDelete = target.dataset.meetingDelete;
    if (meetingDelete && confirm("이 미팅 기록을 삭제할까요? 분석/약속/액션도 함께 삭제됩니다.")) {
      await api(`/api/meetings/${meetingDelete}`, { method: "DELETE" });
      $("meetingDetail").innerHTML = "";
      await loadMeetings();
      await loadDashboard();
    }
    const searchMeeting = target.closest("[data-search-meeting]")?.dataset.searchMeeting;
    if (searchMeeting) {
      setView("meetings");
      await openMeeting(searchMeeting);
    }
    const searchCompany = target.closest("[data-search-company]")?.dataset.searchCompany;
    if (searchCompany) {
      setView("companies");
      await openCompany(searchCompany);
    }
    const riskCompany = target.closest("[data-risk-company]")?.dataset.riskCompany;
    if (riskCompany) {
      $("riskCompany").value = riskCompany;
      await loadRisk();
    }
    const riskSave = target.dataset.riskSave;
    if (riskSave) {
      await api(`/api/risk/${riskSave}`, {
        method: "POST",
        body: JSON.stringify({ risk_level: $("riskLevelSelect").value }),
      });
      await loadRisk();
      await loadCompanies();
    }
    const telegramAction = target.dataset.telegramAction;
    if (telegramAction) await runTelegramAction(telegramAction);
  });
  document.addEventListener("submit", async event => {
    const formIndex = event.target.dataset.candidateForm;
    if (formIndex === undefined) return;
    event.preventDefault();
    const row = state.candidates[Number(formIndex)];
    const payload = candidatePayloadFromForm(event.target);
    if (!payload.title || !payload.date) return;
    await api(`/api/schedule-candidates/${row.meeting_id}/${row.index}/save`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadCandidates();
    await loadDashboard();
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
    hideWorkspaceLogin();
    state.companies = await api("/api/companies") || [];
    renderActionFilters();
    renderCompanyFilters();
    $("meetingCompany").innerHTML = companyOptions("");
    $("uploadCompany").innerHTML = companyOptions("");
    $("riskCompany").innerHTML = companyOptions("");
    $("uploadForm").meeting_date.value = todayIso();
    if (!eventsBound) {
      bindSidebar();
      bindEvents();
      eventsBound = true;
    }
    await loadDashboard();
  } catch (err) {
    if (err.message !== "로그인이 필요합니다.") {
      $("error").textContent = err.message;
    }
  }
}

bindWorkspaceLogin();
load();
