const BASE = location.pathname.startsWith("/mobile") ? "/mobile" : "";
const token = localStorage.getItem("sales_mobile_token") || "";

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

async function refreshCompanyOptions() {
  state.companies = await api("/api/companies") || [];
  renderActionFilters();
}

function setView(view) {
  state.view = view;
  $("viewDashboard").classList.toggle("hidden", view !== "dashboard");
  $("viewActions").classList.toggle("hidden", view !== "actions");
  $("viewCompanies").classList.toggle("hidden", view !== "companies");
  $("viewCandidates").classList.toggle("hidden", view !== "candidates");
  for (const btn of document.querySelectorAll(".tabs button")) {
    btn.classList.toggle("active", btn.dataset.view === view);
  }
  if (view === "actions") {
    loadActions();
    loadPromises();
  }
  if (view === "companies") loadCompanies();
  if (view === "candidates") loadCandidates();
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
  $("newCompanyBtn").onclick = () => showCompanyForm();
  $("companySearch").oninput = () => {
    clearTimeout(window.__companySearchTimer);
    window.__companySearchTimer = setTimeout(loadCompanies, 250);
  };
  $("companyTypeFilter").onchange = loadCompanies;
  $("companyStageFilter").onchange = loadCompanies;
  $("companyRiskFilter").onchange = loadCompanies;
  $("candidateState").onchange = loadCandidates;
  document.addEventListener("click", async event => {
    const target = event.target;
    if (target.matches("[data-cancel-form]")) target.closest("form").classList.add("hidden");
    const clearSlot = target.dataset.clearSlot;
    if (clearSlot) $(clearSlot).innerHTML = "";
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
    state.companies = await api("/api/companies") || [];
    renderActionFilters();
    renderCompanyFilters();
    bindEvents();
    await loadDashboard();
  } catch (err) {
    $("error").textContent = err.message;
  }
}

load();
