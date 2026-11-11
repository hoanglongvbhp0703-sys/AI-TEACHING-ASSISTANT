"use strict";
const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const key = (value) => encodeURIComponent(value);
const roles = {
  student: "Học viên",
  teacher: "Giảng viên",
  admin: "Quản trị viên",
};
const pages = {
  overview: ["Tổng quan", "◫"],
  classes: ["Lớp học", "▦"],
  requests: ["Yêu cầu của tôi", "↗"],
  documents: ["Học liệu", "▤"],
  tickets: ["Yêu cầu hỗ trợ", "☷"],
  users: ["Tài khoản", "♙"],
  courses: ["Khóa học", "▥"],
  reports: ["Báo cáo", "▥"],
};
const state = {
  me: null,
  classes: [],
  courses: [],
  page: "overview",
  offsets: {},
  docQuery: "",
  docClass: "",
  userQuery: "",
  userRole: "",
  ticketStatus: "",
  ticketClass: "",
  range: {},
  sequence: 0,
  modalSubmit: null,
};
function usersPath() {
  const params = new URLSearchParams({limit: "21", offset: String(state.offsets.users || 0), query: state.userQuery});
  if (state.userRole) params.set("role", state.userRole);
  return "/users?" + params;
}
const allowed = (role) =>
  role === "student"
    ? ["overview", "classes", "requests"]
    : role === "teacher"
      ? ["overview", "classes", "documents", "tickets", "reports"]
      : [
          "overview",
          "courses",
          "classes",
          "users",
          "documents",
          "tickets",
          "reports",
        ];
const date = (value) =>
  value
    ? new Date(value).toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        dateStyle: "short",
        timeStyle: "short",
      })
    : "—";
const status = (value) => {
  const names = {
    open: ["Mới gửi", "amber"],
    assigned: ["Đang xử lý", "blue"],
    answered: ["Đã phản hồi", "green"],
    closed: ["Đã đóng", "gray"],
    active: ["Đang hoạt động", "green"],
    suspended: ["Tạm dừng", "amber"],
    left: ["Đã rời lớp", "gray"],
    draft: ["Đã lưu", "blue"],
    approved: ["Đã duyệt", "green"],
    revoked: ["Đã thu hồi", "gray"],
    queued: ["Đã lưu · chờ lập chỉ mục", "blue"],
    failed: ["Chưa xử lý được", "red"],
    cancelled: ["Chưa lập chỉ mục", "gray"],
  };
  const [name, color] = names[value] || [value, "gray"];
  return `<span class="status ${color}">${esc(name)}</span>`;
};
const button = (label, action, id = "", kind = "secondary small") =>
  `<button type="button" class="${kind}" data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`;
const options = (items, selected = "") =>
  items
    .map(
      ([id, name]) =>
        `<option value="${esc(id)}" ${String(id) === String(selected) ? "selected" : ""}>${esc(name)}</option>`,
    )
    .join("");
const classOptions = () => state.classes.map((c) => [c.id, c.name]);
const scopeOptions = () => [
  ...state.classes.map((c) => ["class:" + c.id, "Lớp: " + c.name]),
  ...state.courses.map((c) => ["course:" + c.id, "Toàn khóa: " + c.name]),
];
const metric = (label, value, note = "") =>
  `<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(value)}</div><div class="metric-note">${esc(note)}</div></div>`;
const empty = (title, note = "") =>
  `<div class="empty"><strong>${esc(title)}</strong>${esc(note)}</div>`;
const lead = (title, description, action = "") =>
  `<div class="page-lead"><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div>${action}</div>`;
const card = (title, body, action = "") =>
  `<section class="card"><div class="card-head"><h3>${esc(title)}</h3>${action}</div>${body}</section>`;
const table = (headers, rows) =>
  rows.length
    ? `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    : empty(
        "Chưa có dữ liệu",
        "Các thay đổi sẽ xuất hiện tại đây sau khi được lưu.",
      );
function pager(page, total, more) {
  const offset = state.offsets[page] || 0;
  return `<div class="pager"><span>${total !== undefined ? `${total} mục` : `Từ mục ${offset + 1}`}</span><div><button class="secondary small" data-action="previous" data-id="${page}" ${offset === 0 ? "disabled" : ""}>Trước</button><button class="secondary small" data-action="next" data-id="${page}" ${(total !== undefined ? offset + 20 >= total : !more) ? "disabled" : ""}>Tiếp</button></div></div>`;
}
function notify(message, error = false) {
  $("toast").textContent = message;
  $("toast").className = "toast" + (error ? " error" : "");
  $("toast").hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => ($("toast").hidden = true), 4500);
}
async function api(path, { method = "GET", body, form } = {}) {
  const config = { method, credentials: "same-origin", headers: {} };
  if (form) config.body = form;
  else if (body !== undefined) {
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(body);
  }
  const response = await fetch("/api/v1" + path, config);
  let result;
  try {
    result = await response.json();
  } catch {
    throw Error("Không đọc được phản hồi từ hệ thống.");
  }
  if (!response.ok) {
    const e = Error(result.error?.message || "Không thực hiện được thao tác.");
    e.status = response.status;
    throw e;
  }
  return result.data;
}
let uploadProgressSequence = 0;
function showUploadProgress(title) {
  const sequence = ++uploadProgressSequence;
  $("upload-progress-panel").hidden = false;
  $("upload-progress-panel").classList.remove("failed");
  $("upload-progress-title").textContent = title;
  $("upload-transfer-bar").value = 0;
  $("upload-index-bar").value = 0;
  $("upload-transfer-label").textContent = "Đang truyền file…";
  $("upload-index-label").textContent = "Chờ backend xác thực file";
  $("upload-progress-detail").textContent =
    "Phần trăm index theo công đoạn, không phải thời gian còn lại.";
  return sequence;
}
function progressFailure(message) {
  $("upload-progress-panel").classList.add("failed");
  $("upload-index-label").textContent = message;
  $("upload-progress-detail").textContent =
    "File chỉ được dùng cho RAG sau khi index thành công. Có thể mở Chi tiết để thử lại.";
}
function uploadDocument(path, body) {
  const file = body.get("file");
  const sequence = showUploadProgress(file?.name || "Tải tài liệu");
  const limit = state.health?.max_upload_bytes || 10485760;
  if (file && file.size > limit) {
    const error = Error(
      "File vượt giới hạn " + Math.round(limit / 1048576) + " MB.",
    );
    progressFailure(error.message);
    return Promise.reject(error);
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1" + path);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (sequence !== uploadProgressSequence) return;
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        $("upload-transfer-bar").value = percent;
        $("upload-transfer-label").textContent =
          "Đã truyền " + percent + "% file";
      } else $("upload-transfer-bar").removeAttribute("value");
    };
    xhr.upload.onload = () => {
      if (sequence === uploadProgressSequence) {
        $("upload-transfer-bar").value = 100;
        $("upload-transfer-label").textContent =
          "Đã truyền 100% — backend đang kiểm tra file";
      }
    };
    xhr.onerror = () => {
      const error = Error(
        "Mất kết nối khi upload. Kiểm tra backend và thử lại.",
      );
      if (sequence === uploadProgressSequence) progressFailure(error.message);
      reject(error);
    };
    xhr.onload = () => {
      let result;
      try {
        result = JSON.parse(xhr.responseText);
      } catch {
        result = {};
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const error = Error(
          (result.error?.message || "Upload không thành công") +
            (result.error?.code ? " [" + result.error.code + "]" : "") +
            (result.request_id ? " · request_id=" + result.request_id : ""),
        );
        if (sequence === uploadProgressSequence) progressFailure(error.message);
        reject(error);
        return;
      }
      if (sequence === uploadProgressSequence) {
        $("upload-transfer-bar").value = 100;
        $("upload-transfer-label").textContent = "Backend đã nhận và lưu file";
        if (result.data?.job_id)
          trackIngestion(result.data.job_id).catch((e) =>
            progressFailure(e.message),
          );
        else {
          $("upload-index-label").textContent =
            result.data?.status === "unchanged"
              ? "File và cấu hình không đổi; dùng phiên bản hiện có."
              : "File đã được lưu.";
        }
      }
      resolve(result.data);
    };
    xhr.send(body);
  });
}
async function trackIngestion(jobId) {
  const sequence = ++uploadProgressSequence;
  sessionStorage.setItem("gos_ingestion_job", jobId);
  $("upload-progress-panel").hidden = false;
  $("upload-progress-panel").classList.remove("failed");
  $("upload-progress-title").textContent = "Lập chỉ mục tài liệu";
  $("upload-transfer-bar").value = 100;
  $("upload-transfer-label").textContent = "File đã lưu trên hệ thống";
  while (sequence === uploadProgressSequence && state.me) {
    let job;
    try {
      job = await api("/ingestion-jobs/" + key(jobId));
    } catch (e) {
      sessionStorage.removeItem("gos_ingestion_job");
      throw e;
    }
    if (sequence !== uploadProgressSequence) return;
    const p = job.progress || {
      percent: job.status === "succeeded" ? 100 : 0,
      label: "Backend cần khởi động lại để xem tiến trình chi tiết.",
      chunks_done: 0,
      chunks_total: 0,
      points_done: 0,
      points_total: 0,
    };
    $("upload-progress-title").textContent = "Lập chỉ mục tài liệu";
    $("upload-index-bar").value = p.percent;
    $("upload-index-label").textContent = p.label + " · " + p.percent + "%";
    $("upload-progress-detail").textContent =
      (p.chunks_total
        ? "Embedding: " + p.chunks_done + "/" + p.chunks_total + " đoạn. "
        : "") +
      (p.points_total
        ? "Vector đã lưu: " + p.points_done + "/" + p.points_total + ". "
        : "") +
      "Theo công đoạn · job_id=" +
      jobId +
      (p.error_code ? " · " + p.error_code : "");
    if (["succeeded", "failed", "cancelled"].includes(job.status)) {
      sessionStorage.removeItem("gos_ingestion_job");
      if (job.status !== "succeeded")
        $("upload-progress-panel").classList.add("failed");
      if (job.status === "succeeded")
        notify("Index thành công. Phiên bản mới đã sẵn sàng cho RAG.");
      if (state.page === "documents") await navigate("documents");
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
async function basis() {
  state.health = await api("/health");
  $("rag-sidebar-status").textContent =
    state.health.rag === "ready" && state.health.rag_jobs_enabled
      ? "RAG đang bật"
      : "RAG chưa sẵn sàng hoặc đang tắt";
  state.classes = await api("/classes");
  state.courses = state.me.role === "student" ? [] : await api("/courses");
}
let loginOptionsSequence = 0;
async function syncLoginProfile() {
  const sequence = ++loginOptionsSequence;
  const role = state.setupRequired ? "admin" : $("login-role").value;
  $("login-role-field").hidden = state.setupRequired;
  $("username-field").hidden = role !== "admin";
  $("username").required = role === "admin";
  $("login-profile-field").hidden = role === "admin";
  $("login-profile").required = role !== "admin";
  $("login-class-field").hidden = role !== "student";
  $("login-class").required = role === "student";
  $("login-profile").replaceChildren(new Option("Đang đọc hồ sơ…", ""));
  if (role === "admin") return;
  const info = await api(
    "/auth/options?role=" +
      role +
      (role === "student" ? "&class_id=" + key($("login-class").value) : ""),
  );
  if (sequence !== loginOptionsSequence) return;
  let profiles = info.profiles;
  if (role === "student") {
    const chosen = $("login-class").value;
    $("login-class").replaceChildren(
      ...info.classes.map((c) => new Option(c.name, c.id)),
    );
    if (info.classes.some((c) => c.id === chosen))
      $("login-class").value = chosen;
    if ($("login-class").value !== chosen) {
      const selected = await api(
        "/auth/options?role=student&class_id=" + key($("login-class").value),
      );
      if (sequence !== loginOptionsSequence) return;
      profiles = selected.profiles;
    }
  }
  $("login-profile").replaceChildren(
    new Option("Chọn hồ sơ đã được cấp", ""),
    ...profiles.map((p) => {
      const option = new Option(
        p.display_name + (p.username ? "" : " · chưa cấp đăng nhập"),
        p.username || "",
      );
      option.disabled = !p.username;
      return option;
    }),
  );
  $("login-description").textContent =
    role === "teacher"
      ? "Chọn hồ sơ giảng viên do admin cấp và nhập mật khẩu."
      : "Chọn lớp, số thứ tự học viên và nhập mật khẩu được cấp.";
}
$("login-role").onchange = () => {
  $("password").value = "";
  $("login-error").textContent = "";
  syncLoginProfile().catch((e) => ($("login-error").textContent = e.message));
};
$("login-class").onchange = () => {
  $("password").value = "";
  syncLoginProfile().catch((e) => ($("login-error").textContent = e.message));
};
async function showLogin() {
  state.sequence++;
  state.me = null;
  state.offsets = {};
  state.docQuery = "";
  state.docClass = "";
  state.ticketStatus = "";
  state.ticketClass = "";
  state.range = {};
  $("toast").hidden = true;
  clearTimeout(notify.timer);
  uploadProgressSequence++;
  $("upload-progress-title").textContent = "Tiến trình tài liệu";
  $("upload-progress-panel").hidden = true;
  $("workspace").hidden = true;
  $("login").hidden = false;
  $("login-error").textContent = "";
  try {
    const info = await api("/auth/status");
    state.setupRequired = info.setup_required;
    $("setup-name-field").hidden = !state.setupRequired;
    $("confirm-password-field").hidden = !state.setupRequired;
    $("setup-name").required = state.setupRequired;
    $("password-confirm").required = state.setupRequired;
    $("password").minLength = state.setupRequired ? 15 : 1;
    $("password").maxLength = state.setupRequired ? 128 : 1024;
    $("password").autocomplete = state.setupRequired
      ? "new-password"
      : "current-password";
    $("login-title").textContent = state.setupRequired
      ? "Khởi tạo quản trị viên"
      : "Chào mừng trở lại";
    $("login-description").textContent = state.setupRequired
      ? "Tạo tài khoản admin đầu tiên. Chỉ thực hiện một lần."
      : "Đăng nhập bằng tài khoản và mật khẩu của bạn.";
    $("login-button").textContent = state.setupRequired
      ? "Tạo tài khoản admin"
      : "Đăng nhập";
    await syncLoginProfile();
  } catch (e) {
    $("login-error").textContent = e.message;
  }
}
async function enter() {
  state.me = await api("/auth/me");
  await basis();
  $("login").hidden = true;
  $("workspace").hidden = false;
  $("user-name").textContent = state.me.display_name;
  $("user-role").textContent = roles[state.me.role] || state.me.role;
  $("navigation").innerHTML = allowed(state.me.role)
    .map(
      (p) =>
        `<a class="nav-button" href="#${p}" data-page="${p}"><span class="nav-icon">${pages[p][1]}</span>${pages[p][0]}</a>`,
    )
    .join("");
  const desired = location.hash.slice(1);
  await navigate(
    allowed(state.me.role).includes(desired) ? desired : "overview",
  );
  const pending = sessionStorage.getItem("gos_ingestion_job");
  if (pending && state.me.role !== "student")
    trackIngestion(pending).catch((e) => progressFailure(e.message));
}
async function navigate(page) {
  if (!state.me) return;
  if (!allowed(state.me.role).includes(page)) page = "overview";
  state.page = page;
  history.replaceState(null, "", "#" + page);
  const sequence = ++state.sequence;
  $("page-title").textContent = pages[page][0];
  document
    .querySelectorAll("[data-page]")
    .forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  $("content").innerHTML = '<div class="loading">Đang tải dữ liệu…</div>';
  try {
    const html = await renderers[page]();
    if (sequence === state.sequence) $("content").innerHTML = html;
  } catch (e) {
    if (sequence !== state.sequence) return;
    if (e.status === 401) return showLogin();
    $("content").innerHTML = empty("Không tải được dữ liệu", e.message);
  }
}
function fields(definitions) {
  return definitions
    .map((f) => {
      if (f.type === "hidden")
        return `<input type="hidden" name="${f.name}" value="${esc(f.value)}">`;
      const attrs = `name="${f.name}" id="field-${f.name}" ${f.required === false ? "" : "required"} ${f.max ? `maxlength="${f.max}"` : ""} ${f.min ? `minlength="${f.min}"` : ""} ${f.pattern ? `pattern="${f.pattern}"` : ""}`;
      let input =
        f.type === "select"
          ? `<select ${attrs}>${options(f.options, f.value)}</select>`
          : f.type === "textarea"
            ? `<textarea ${attrs}>${esc(f.value)}</textarea>`
            : `<input type="${f.type || "text"}" ${attrs} value="${f.type === "file" ? "" : esc(f.value)}" ${f.accept ? `accept="${f.accept}"` : ""}>`;
      return `<div class="field"><label for="field-${f.name}">${esc(f.label)}</label>${input}${f.hint ? `<small>${esc(f.hint)}</small>` : ""}</div>`;
    })
    .join("");
}
function modal(title, body, onSubmit = null, saveLabel = "Lưu") {
  if ($("dialog").open) $("dialog").close();
  state.modalSubmit = onSubmit;
  $("dialog-title").textContent = title;
  $("dialog-body").innerHTML = body;
  $("dialog-error").textContent = "";
  $("dialog-submit").textContent = saveLabel;
  $("dialog-submit").hidden = !onSubmit;
  $("dialog-submit").disabled = false;
  $("dialog").showModal();
}
function form(title, definitions, onSubmit, label = "Lưu") {
  modal(title, fields(definitions), onSubmit, label);
}
const idField = {
  name: "id",
  label: "Mã định danh",
  max: 100,
  pattern: "[A-Za-z0-9_-]+",
  hint: "Dùng chữ không dấu, số, dấu gạch ngang hoặc gạch dưới.",
};
function ticketRows(items, own = false) {
  return items.map((t) => [
    `<strong>${esc(t.question_redacted.slice(0, 85))}${t.question_redacted.length > 85 ? "…" : ""}</strong><span class="subline">#${esc(t.id.slice(0, 8))} · ${date(t.created_at)}</span>`,
    esc(
      t.class_name ||
        state.classes.find((c) => c.id === t.class_id)?.name ||
        t.class_id,
    ),
    status(t.status),
    button("Chi tiết", own ? "requestDetail" : "ticketDetail", t.id),
  ]);
}

const renderers = {
  async overview() {
    const me = state.me;
    if (me.role === "student") {
      const [quota, requests] = await Promise.all([
        api("/students/" + key(me.id) + "/quota"),
        api("/support-requests?limit=5"),
      ]);
      return (
        lead(
          "Chào " + me.display_name + ",",
          "Theo dõi lớp học và nhận hỗ trợ từ giảng viên.",
          button("Gửi yêu cầu hỗ trợ", "newRequest", "", "primary"),
        ) +
        `<div class="metrics">${metric("Lớp đang tham gia", state.classes.length, "Các lớp bạn có quyền truy cập")}${metric("Lượt hỏi còn lại", quota.remaining, `Hạn mức ${quota.limit} lượt/ngày · làm mới theo giờ Việt Nam`)}${metric("Yêu cầu đã gửi", requests.total, "Yêu cầu trực tiếp không dùng lượt hỏi AI")}</div>` +
        card(
          "Yêu cầu gần đây",
          table(
            ["Nội dung", "Lớp", "Trạng thái", ""],
            ticketRows(requests.items, true),
          ),
          `<a class="help-link" href="#requests">Xem tất cả →</a>`,
        ) +
        card(
          "Lớp của bạn",
          table(
            ["Tên lớp", "Mã lớp", ""],
            state.classes.map((c) => [
              `<strong>${esc(c.name)}</strong>`,
              esc(c.id),
              button("Xem lớp", "classDetail", c.id),
            ]),
          ),
        )
      );
    }
    const [open, assigned, recent, docs] = await Promise.all([
      api("/tickets?status=open&limit=1"),
      api("/tickets?status=assigned&limit=1"),
      api("/tickets?limit=5"),
      api("/documents?limit=1"),
    ]);
    return (
      lead(
        "Chào " + me.display_name + ",",
        "Quản lý lớp học, học liệu và những yêu cầu cần phản hồi.",
        button("Xem yêu cầu", "goTickets", "", "primary"),
      ) +
      `<div class="metrics">${metric("Lớp phụ trách", state.classes.length, "Theo phân quyền hiện tại")}${metric("Yêu cầu chờ xử lý", open.total + assigned.total, "Bao gồm yêu cầu mới và đang xử lý")}${metric("Học liệu đã lưu", docs.total, "File được lưu, chưa bật lập chỉ mục")}</div>` +
      card(
        "Yêu cầu mới nhất",
        table(["Nội dung", "Lớp", "Trạng thái", ""], ticketRows(recent.items)),
        `<a class="help-link" href="#tickets">Xem tất cả →</a>`,
      ) +
      card(
        "Lớp học",
        table(
          ["Tên lớp", "Khóa học", "Bot", ""],
          state.classes
            .slice(0, 5)
            .map((c) => [
              `<strong>${esc(c.name)}</strong>`,
              esc(c.course_id),
              status(c.bot_enabled ? "active" : "suspended"),
              button("Xem lớp", "classDetail", c.id),
            ]),
        ),
      )
    );
  },
  async classes() {
    await basis();
    return (
      lead(
        "Lớp học",
        state.me.role === "student"
          ? "Các lớp bạn đang tham gia."
          : "Quản lý thông tin và người tham gia từng lớp.",
        state.me.role === "admin"
          ? button("Tạo lớp", "newClass", "", "primary")
          : "",
      ) +
      card(
        "Danh sách lớp",
        table(
          ["Lớp", "Khóa học", "Trạng thái", "Bot", ""],
          state.classes.map((c) => [
            `<strong>${esc(c.name)}</strong><span class="subline">${esc(c.id)}</span>`,
            esc(
              state.courses.find((x) => x.id === c.course_id)?.name ||
                c.course_id,
            ),
            status(c.status),
            status(c.bot_enabled ? "active" : "suspended"),
            `<div class="table-actions">${button("Chi tiết", "classDetail", c.id)}${state.me.role === "admin" ? button(c.bot_enabled ? "Tắt bot" : "Bật bot", "toggleBot", c.id) : ""}</div>`,
          ]),
        ),
      )
    );
  },
  async courses() {
    state.courses = await api("/courses");
    return (
      lead(
        "Khóa học",
        "Tổ chức các lớp theo từng chương trình đào tạo.",
        button("Tạo khóa học", "newCourse", "", "primary"),
      ) +
      card(
        "Danh sách khóa học",
        table(
          ["Tên khóa học", "Mã", "Trạng thái"],
          state.courses.map((c) => [
            `<strong>${esc(c.name)}</strong>`,
            esc(c.id),
            status(c.status),
          ]),
        ),
      )
    );
  },
  async users() {
    const rows = await api(usersPath());
    const search = `<form class="toolbar" id="user-search"><input name="query" aria-label="Tìm tài khoản" placeholder="Tìm tên, mã tài khoản hoặc tên đăng nhập…" value="${esc(state.userQuery)}"><select name="role" aria-label="Lọc vai trò">${options([["", "Tất cả vai trò"], ["teacher", "Giảng viên"], ["student", "Học viên"], ["admin", "Quản trị viên"]], state.userRole)}</select><button class="secondary">Tìm kiếm</button>${button("Xóa bộ lọc", "clearUserSearch")}</form>`;
    return (
      lead(
        "Tài khoản",
        "Tạo người dùng và quản lý trạng thái truy cập.",
        button("Tạo tài khoản", "newUser", "", "primary"),
      ) +
      card(
        "Người dùng hệ thống",
        search + table(
          ["Người dùng", "Vai trò", "Trạng thái", ""],
          rows
            .slice(0, 20)
            .map((u) => [
              `<strong>${esc(u.display_name)}</strong><span class="subline">${esc(u.id)}</span>`,
              `${esc(roles[u.role] || u.role)}<span class="subline">${u.username ? esc(u.username) : "Chưa có tên đăng nhập"}</span>`,
              status(u.is_active ? "active" : "suspended"),
              u.id === state.me.id
                ? '<span class="muted">Tài khoản hiện tại</span>'
                : (u.role !== "service"
                    ? button(
                        u.username ? "Đặt lại đăng nhập" : "Cấp đăng nhập",
                        "resetCredentials",
                        u.id,
                      )
                    : "") +
                  button(
                    u.is_active ? "Khóa tài khoản" : "Mở tài khoản",
                    "toggleUser",
                    u.id,
                  ),
            ]),
        ) + pager("users", undefined, rows.length > 20),
      )
    );
  },
  async requests() {
    const data = await api(
      `/support-requests?limit=20&offset=${state.offsets.requests || 0}`,
    );
    return (
      lead(
        "Yêu cầu hỗ trợ",
        "Gửi câu hỏi trực tiếp và theo dõi phản hồi từ giảng viên.",
        button("Gửi yêu cầu", "newRequest", "", "primary"),
      ) +
      `<div class="notice">Giảng viên sẽ phản hồi trực tiếp. Yêu cầu tại đây không gọi AI và không trừ lượt hỏi.</div>` +
      card(
        "Yêu cầu của bạn",
        table(
          ["Nội dung", "Lớp", "Trạng thái", ""],
          ticketRows(data.items, true),
        ) + pager("requests", data.total),
      )
    );
  },
  async documents() {
    const p = new URLSearchParams({
      query: state.docQuery,
      limit: 20,
      offset: state.offsets.documents || 0,
    });
    if (state.docClass) p.set("class_id", state.docClass);
    const data = await api("/documents?" + p);
    const search = `<form class="toolbar" id="document-search"><input name="query" aria-label="Tên tài liệu hoặc chủ đề" placeholder="Tìm tên tài liệu hoặc chủ đề…" value="${esc(state.docQuery)}"><select name="class_id" aria-label="Lọc theo lớp">${options([["", "Tất cả lớp"], ...classOptions()], state.docClass)}</select><button class="secondary">Tìm kiếm</button></form>`;
    return (
      lead(
        "Học liệu",
        "Lưu trữ và quản lý các phiên bản tài liệu của lớp.",
        button("Thêm tài liệu", "newDocument", "", "primary"),
      ) +
      `<div class="notice">${state.health?.rag_jobs_enabled ? "RAG đang bật. Phiên bản mới chỉ được sử dụng sau khi index thành công; quyền áp dụng cho toàn tài liệu." : "Giai đoạn này chỉ lưu file và quản lý phiên bản. Tài liệu chưa được lập chỉ mục hoặc đưa vào RAG."}</div>` +
      card(
        "Thư viện tài liệu",
        search +
          table(
            ["Tài liệu", "Phạm vi", "Phiên bản", "Trạng thái", ""],
            data.items.map((d) => [
              `<strong>${esc(d.title)}</strong><span class="subline">${esc(d.topic)}</span>`,
              d.scope_ids
                .map((s) =>
                  esc(s.replace("class:", "Lớp ").replace("course:", "Khóa ")),
                )
                .join("<br>"),
              d.latest_version
                ? "V" + d.latest_version
                : d.active_version
                  ? "V" + d.active_version
                  : "—",
              status(d.status),
              `<div class="table-actions">${button("Chi tiết", "documentDetail", d.id)}${d.status !== "revoked" ? button("Thay file", "newVersion", d.id) : ""}</div>`,
            ]),
          ) +
          pager("documents", data.total),
      )
    );
  },
  async tickets() {
    const p = new URLSearchParams({
      limit: 20,
      offset: state.offsets.tickets || 0,
    });
    if (state.ticketStatus) p.set("status", state.ticketStatus);
    if (state.ticketClass) p.set("class_id", state.ticketClass);
    const data = await api("/tickets?" + p);
    const toolbar = `<form class="toolbar" id="ticket-search"><select name="status" aria-label="Lọc trạng thái">${options(
      [
        ["", "Mọi trạng thái"],
        ["open", "Mới gửi"],
        ["assigned", "Đang xử lý"],
        ["answered", "Đã phản hồi"],
        ["closed", "Đã đóng"],
      ],
      state.ticketStatus,
    )}</select><select name="class_id" aria-label="Lọc lớp">${options([["", "Tất cả lớp"], ...classOptions()], state.ticketClass)}</select><button class="secondary">Lọc yêu cầu</button></form>`;
    return (
      lead(
        "Yêu cầu hỗ trợ",
        "Phân công, phản hồi và ghi nhận nội dung đã được xác nhận.",
      ) +
      card(
        "Danh sách yêu cầu",
        toolbar +
          table(["Câu hỏi", "Lớp", "Trạng thái", ""], ticketRows(data.items)) +
          pager("tickets", data.total),
      )
    );
  },
  async reports() {
    const p = new URLSearchParams(state.range);
    const data = await api("/reports/summary?" + p);
    const labels = {
      manual_support: "Hỗ trợ trực tiếp",
      answered: "Đã trả lời",
      insufficient_evidence: "Chuyển giảng viên",
      blocked: "Từ chối an toàn",
      error: "Lỗi xử lý",
      quota_exceeded: "Hết lượt hỏi",
      not_a_question: "Tin thông thường",
      access_denied: "Không đủ quyền",
    };
    return (
      lead(
        "Báo cáo hoạt động",
        "Dữ liệu được tổng hợp theo phạm vi lớp bạn được phân quyền.",
      ) +
      `<div class="metrics">${metric("Yêu cầu hỗ trợ", data.tickets, "Trong khoảng thời gian được chọn")}${metric("Sự kiện được ghi nhận", data.unique_events, `${date(data.from)} → ${date(data.to)}`)}${metric("Câu hỏi dùng quota", data.accepted_questions, "Yêu cầu hỗ trợ trực tiếp không tính vào đây")}</div>` +
      card(
        "Chọn khoảng thời gian",
        `<form class="toolbar" id="report-range"><div><label>Từ ngày</label><input type="date" name="from" required></div><div><label>Đến hết ngày</label><input type="date" name="to" required></div><button class="secondary">Xem báo cáo</button></form>`,
      ) +
      card(
        "Kết quả tiếp nhận",
        table(
          ["Loại kết quả", "Số lượng"],
          Object.entries(data.event_outcomes).map(([k, v]) => [
            esc(labels[k] || k),
            esc(v),
          ]),
        ),
      ) +
      `<p class="inline-note">${state.health?.rag_jobs_enabled ? "RAG đang bật. Token được ghi từ phản hồi provider; chi phí chưa có đơn giá được để trống." : "RAG chưa bật. Báo cáo không tự tạo số token hoặc chi phí model."}</p>`
    );
  },
};

async function newRequest(classId = "") {
  if (!state.classes.length) return notify("Bạn chưa tham gia lớp nào.", true);
  let requestId = crypto.randomUUID();
  form(
    "Gửi yêu cầu hỗ trợ",
    [
      {
        name: "class_id",
        label: "Lớp học",
        type: "select",
        options: classOptions(),
        value: classId,
      },
      {
        name: "question",
        label: "Nội dung cần giảng viên hỗ trợ",
        type: "textarea",
        max: 8000,
        hint: "Mô tả câu hỏi hoặc lỗi đang gặp. Không gửi mật khẩu hoặc khóa truy cập.",
      },
    ],
    async (data) => {
      await api("/support-requests", {
        method: "POST",
        body: {
          class_id: data.get("class_id"),
          question: data.get("question"),
          client_request_id: requestId,
        },
      });
      notify("Đã gửi yêu cầu cho giảng viên.");
      state.offsets.requests = 0;
      await navigate("requests");
    },
    "Gửi yêu cầu",
  );
}
async function requestDetail(id) {
  const t = await api("/support-requests/" + key(id));
  modal(
    "Yêu cầu #" + t.id.slice(0, 8),
    `<div class="detail-meta">${status(t.status)}<span class="muted">${esc(t.class_name)} · ${date(t.created_at)}</span></div><div class="section-label">Nội dung của bạn</div><div class="message-box">${esc(t.question_redacted)}</div><div class="section-label">Phản hồi của giảng viên</div>${t.answer_redacted ? `<div class="message-box answer">${esc(t.answer_redacted)}</div>` : '<p class="muted">Yêu cầu đang chờ giảng viên phản hồi.</p>'}`,
  );
}
async function classDetail(id) {
  const c = state.classes.find((x) => x.id === id);
  const teachers = await api("/classes/" + key(id) + "/teachers");
  const staff = state.me.role !== "student";
  const members = staff
    ? await api("/classes/" + key(id) + "/members?limit=100")
    : [];
  modal(
    c?.name || id,
    `<div class="detail-meta">${status(c?.status || "active")}<span class="muted">${esc(id)}</span></div><div class="section-label">Giảng viên</div>${teachers.length ? teachers.map((t) => `<p>${esc(t.display_name)} ${status(t.assignment_active ? "active" : "suspended")}</p>`).join("") : '<p class="muted">Chưa có giảng viên được phân công.</p>'}${
      staff
        ? `<div class="section-label">Học viên · ${members.length}</div>${table(
            ["STT", "Học viên", "Trạng thái", ""],
            members.map((m) => [
              esc(m.student_number),
              `<strong>${esc(m.display_name)}</strong><span class="subline">${esc(m.id)}</span>`,
              status(m.status),
              state.me.role === "admin"
                ? button(
                    m.status === "active" ? "Tạm dừng" : "Cho tham gia",
                    "toggleEnrollment",
                    id + "|" + m.id,
                  )
                : "",
            ]),
          )}`
        : ""
    }<div class="dialog-toolbar">${state.me.role === "admin" ? button("Sĩ số từ metadata", "classRoster", id) + button("Thêm học viên", "addEnrollment", id) + button("Phân công giảng viên", "assignTeacher", id) + button("Liên kết nhóm", "bindGroup", id) : state.me.role === "student" ? button("Gửi yêu cầu hỗ trợ", "newRequest", id, "primary") : ""}</div>`,
  );
}
async function documentDetail(id) {
  const d = await api("/documents/" + key(id));
  const health = await api("/health");
  modal(
    d.title,
    `<div class="detail-meta">${status(d.status)}<span class="muted">${esc(d.topic)}</span></div><p class="inline-note">${d.scope_ids.map((s) => esc(s)).join(" · ")}</p>${table(
      ["Phiên bản", "File nguồn", "Thời gian", "Lập chỉ mục"],
      d.versions.map((v) => [
        "V" +
          v.version +
          (v.id === d.active_version_id ? " · Đang sử dụng" : "") +
          `<span class="subline">${status(v.status)}</span>`,
        `<strong>${esc(v.original_filename)}</strong><span class="subline">${Math.ceil(v.file_size_bytes / 1024)} KB</span>`,
        date(v.uploaded_at),
        `<span class="subline">${v.error_code ? esc(v.error_code) : ""}</span>${v.job_id ? button("Xem tiến trình", "showIndexProgress", v.job_id) : ""}${v.status === "failed" && v.job_id ? button("Thử index lại", "retryIndex", v.job_id) : ""}`,
      ]),
    )}<p class="inline-note">${health.rag_jobs_enabled ? "Phiên bản hiện hành chỉ đổi khi bản mới index thành công." : "File được lưu trong hệ thống. Lập chỉ mục chưa bật trong giai đoạn này."}</p>${d.status !== "revoked" ? `<div class="dialog-toolbar">${button("Upload phiên bản mới", "newVersion", id, "primary")}${health.rag_jobs_enabled ? button("Lập chỉ mục lại", "reindexDocument", id) : ""}${button("Thu hồi tài liệu", "revokeDocument", id, "danger")}</div>` : ""}`,
  );
}
async function ticketDetail(id) {
  const t = await api("/tickets/" + key(id));
  const teachers = await api("/classes/" + key(t.class_id) + "/teachers");
  const owner = teachers.find((u) => u.id === t.assignee_id);
  modal(
    "Yêu cầu #" + t.id.slice(0, 8),
    `<div class="detail-meta">${status(t.status)}<span class="muted">${esc(t.class_id)} · ${date(t.created_at)}</span></div><div class="section-label">Câu hỏi từ học viên ${esc(t.student_id)}</div><div class="message-box">${esc(t.question_redacted)}</div><p class="inline-note">Phụ trách: ${esc(owner?.display_name || t.assignee_id || "Chưa phân công")}</p>${t.reply ? `<div class="section-label">Câu trả lời chính thức</div><div class="message-box answer">${esc(t.reply.answer_redacted)}</div>${t.status === "assigned" ? '<p class="inline-note">Đã lưu câu trả lời, đang chờ hệ thống ghi nhận gửi thành công.</p>' : ""}` : ""}<div class="dialog-toolbar">${["open", "assigned"].includes(t.status) && !t.reply ? button("Phân công", "assignTicket", id) + button("Trả lời", "answerTicket", id, "primary") : ""}${t.status === "answered" ? button("Đóng yêu cầu", "closeTicket", id) : ""}${["answered", "closed"].includes(t.status) ? button(t.faq ? "Xem FAQ" : "Tạo FAQ", "ticketFaq", id) : ""}</div>`,
  );
}

const actions = {
  clearUserSearch: async () => {
    state.userQuery = "";
    state.userRole = "";
    state.offsets.users = 0;
    await navigate("users");
  },
  goTickets: () => navigate("tickets"),
  previous: (id) => {
    state.offsets[id] = Math.max(0, (state.offsets[id] || 0) - 20);
    return navigate(id);
  },
  next: (id) => {
    state.offsets[id] = (state.offsets[id] || 0) + 20;
    return navigate(id);
  },
  newRequest,
  requestDetail,
  classDetail,
  documentDetail,
  ticketDetail,
  newUser: () =>
    form(
      "Tạo tài khoản",
      [
        idField,
        { name: "display_name", label: "Tên hiển thị", max: 200 },
        {
          name: "username",
          label: "Tên đăng nhập",
          min: 3,
          max: 64,
          pattern: "[A-Za-z0-9][A-Za-z0-9._-]{2,63}",
        },
        {
          name: "password",
          label: "Mật khẩu",
          type: "password",
          min: 15,
          max: 128,
          hint: "Tối thiểu 15 ký tự.",
        },
        {
          name: "confirm_password",
          label: "Nhập lại mật khẩu",
          type: "password",
          min: 15,
          max: 128,
        },
        {
          name: "role",
          label: "Vai trò",
          type: "select",
          value: "teacher",
          options: [
            ["student", "Học viên"],
            ["teacher", "Giảng viên"],
            ["admin", "Quản trị viên"],
          ],
        },
      ],
      async (data) => {
        if (data.get("password") !== data.get("confirm_password"))
          throw Error("Hai mật khẩu không khớp.");
        const body = Object.fromEntries(data);
        delete body.confirm_password;
        await api("/users", { method: "POST", body });
        notify("Đã tạo tài khoản và thông tin đăng nhập.");
        await navigate("users");
      },
      "Tạo tài khoản",
    ),
  changePassword: () =>
    form(
      "Đổi mật khẩu",
      [
        {
          name: "current_password",
          label: "Mật khẩu hiện tại",
          type: "password",
          max: 1024,
        },
        {
          name: "new_password",
          label: "Mật khẩu mới",
          type: "password",
          min: 15,
          max: 128,
          hint: "Tối thiểu 15 ký tự. Các phiên đăng nhập khác sẽ hết hiệu lực.",
        },
        {
          name: "confirm_password",
          label: "Nhập lại mật khẩu mới",
          type: "password",
          min: 15,
          max: 128,
        },
      ],
      async (data) => {
        if (data.get("new_password") !== data.get("confirm_password"))
          throw Error("Hai mật khẩu không khớp.");
        await api("/auth/password", {
          method: "POST",
          body: {
            current_password: data.get("current_password"),
            new_password: data.get("new_password"),
          },
        });
        notify("Đã đổi mật khẩu và thu hồi các phiên đăng nhập khác.");
      },
      "Đổi mật khẩu",
    ),
  resetCredentials: async (id) => {
    const rows = await api(usersPath());
    const user = rows.find((u) => u.id === id);
    if (!user) throw Error("Hãy tải lại danh sách tài khoản.");
    form(
      "Thiết lập đăng nhập · " + user.display_name,
      [
        {
          name: "username",
          label: "Tên đăng nhập",
          value: user.username || "",
          min: 3,
          max: 64,
          pattern: "[A-Za-z0-9][A-Za-z0-9._-]{2,63}",
        },
        {
          name: "password",
          label: "Mật khẩu mới",
          type: "password",
          min: 15,
          max: 128,
          hint: "Tối thiểu 15 ký tự. Các phiên cũ của tài khoản sẽ bị thu hồi.",
        },
        {
          name: "confirm_password",
          label: "Nhập lại mật khẩu",
          type: "password",
          min: 15,
          max: 128,
        },
      ],
      async (data) => {
        if (data.get("password") !== data.get("confirm_password"))
          throw Error("Hai mật khẩu không khớp.");
        await api("/users/" + key(id) + "/credentials", {
          method: "PUT",
          body: {
            username: data.get("username"),
            password: data.get("password"),
          },
        });
        notify(
          "Đã lưu thông tin đăng nhập. Hãy cấp mật khẩu cho đúng người dùng.",
        );
        await navigate("users");
      },
      "Lưu thông tin đăng nhập",
    );
  },
  toggleUser: async (id) => {
    const users = await api(usersPath());
    const u = users.find((x) => x.id === id);
    if (!u) throw Error("Hãy tải lại danh sách tài khoản.");
    form(
      u.is_active ? "Khóa tài khoản" : "Mở tài khoản",
      [],
      async () => {
        await api("/users/" + key(id), {
          method: "PATCH",
          body: { is_active: !u.is_active },
        });
        notify("Đã cập nhật trạng thái tài khoản.");
        await navigate("users");
      },
      "Xác nhận",
    );
    $("dialog-body").innerHTML =
      `<p>${u.is_active ? "Khóa" : "Mở lại"} quyền truy cập của <strong>${esc(u.display_name)}</strong>?</p>`;
  },
  newCourse: () =>
    form(
      "Tạo khóa học",
      [idField, { name: "name", label: "Tên khóa học", max: 200 }],
      async (data) => {
        await api("/courses", {
          method: "POST",
          body: Object.fromEntries(data),
        });
        notify("Đã tạo khóa học.");
        await basis();
        await navigate("courses");
      },
      "Tạo khóa học",
    ),
  newClass: () => {
    if (!state.courses.length) return notify("Hãy tạo khóa học trước.", true);
    form(
      "Tạo lớp",
      [
        idField,
        { name: "name", label: "Tên lớp", max: 200 },
        {
          name: "course_id",
          label: "Thuộc khóa học",
          type: "select",
          options: state.courses.map((c) => [c.id, c.name]),
        },
        {
          name: "student_count",
          label: "Sĩ số theo metadata",
          type: "number",
          required: false,
          hint: "Để trống nếu chưa có danh sách; nhập 49 để tạo STT 1–49.",
        },
      ],
      async (data) => {
        const body = Object.fromEntries(data);
        body.student_count = Number(body.student_count || 0);
        await api("/classes", {
          method: "POST",
          body,
        });
        notify("Đã tạo lớp. Mở chi tiết để thêm học viên và liên kết nhóm.");
        await navigate("classes");
      },
      "Tạo lớp",
    );
  },
  toggleBot: async (id) => {
    const c = state.classes.find((x) => x.id === id);
    await api("/classes/" + key(id) + "/bot", {
      method: "PATCH",
      body: { bot_enabled: !c.bot_enabled },
    });
    notify("Đã cập nhật cấu hình bot của lớp.");
    await navigate("classes");
  },
  classRoster: (id) =>
    form(
      "Danh sách học viên từ metadata lớp",
      [
        {
          name: "student_count",
          label: "Sĩ số lớp",
          type: "number",
          hint: "Ví dụ 49: tạo đủ danh sách STT 1–49. Không xóa học viên hoặc đặt lại STT đã có.",
        },
      ],
      async (data) => {
        await api("/classes/" + key(id) + "/roster", {
          method: "PUT",
          body: { student_count: Number(data.get("student_count")) },
        });
        notify(
          "Đã cập nhật danh sách theo metadata lớp. Tài khoản đăng nhập được cấp riêng.",
        );
        await classDetail(id);
      },
      "Cập nhật danh sách",
    ),
  addEnrollment: async (id) => {
    const users = (await api("/users?limit=100")).filter(
      (u) => u.role === "student" && u.is_active,
    );
    if (!users.length)
      return notify("Chưa có tài khoản học viên khả dụng.", true);
    form(
      "Thêm học viên vào lớp",
      [
        {
          name: "student_id",
          label: "Học viên",
          type: "select",
          options: users.map((u) => [u.id, u.display_name + " · " + u.id]),
        },
      ],
      async (data) => {
        await api(
          "/classes/" + key(id) + "/members/" + key(data.get("student_id")),
          { method: "PUT", body: { status: "active" } },
        );
        notify("Đã thêm học viên vào lớp.");
        await classDetail(id);
      },
      "Thêm học viên",
    );
  },
  toggleEnrollment: async (value) => {
    const [cid, student] = value.split("|");
    const rows = await api("/classes/" + key(cid) + "/members?limit=100");
    const member = rows.find((r) => r.id === student);
    await api("/classes/" + key(cid) + "/members/" + key(student), {
      method: "PUT",
      body: { status: member.status === "active" ? "suspended" : "active" },
    });
    notify("Đã cập nhật quyền tham gia lớp.");
    await classDetail(cid);
  },
  assignTeacher: async (id) => {
    const users = (await api("/users?limit=100")).filter(
      (u) => u.role === "teacher" && u.is_active,
    );
    if (!users.length)
      return notify("Chưa có tài khoản giảng viên khả dụng.", true);
    form(
      "Phân công giảng viên",
      [
        {
          name: "teacher_id",
          label: "Giảng viên",
          type: "select",
          options: users.map((u) => [u.id, u.display_name]),
        },
        {
          name: "is_active",
          label: "Trạng thái phân công",
          type: "select",
          options: [
            ["true", "Đang phụ trách"],
            ["false", "Ngừng phụ trách"],
          ],
        },
      ],
      async (data) => {
        await api(
          "/classes/" + key(id) + "/teachers/" + key(data.get("teacher_id")),
          {
            method: "PUT",
            body: { is_active: data.get("is_active") === "true" },
          },
        );
        notify("Đã cập nhật phân công giảng viên.");
        await classDetail(id);
      },
      "Lưu phân công",
    );
  },
  bindGroup: (id) =>
    form(
      "Liên kết nhóm nhận phản hồi",
      [
        { name: "external_group_id", label: "Mã nhóm giả lập", max: 200 },
        { name: "display_name", label: "Tên nhóm", max: 200 },
      ],
      async (data) => {
        await api("/group-bindings", {
          method: "POST",
          body: { ...Object.fromEntries(data), class_id: id },
        });
        notify("Đã liên kết nhóm với lớp.");
      },
      "Liên kết",
    ),
  newDocument: () => {
    const choices = scopeOptions();
    if (!choices.length)
      return notify("Bạn chưa có lớp hoặc khóa học để quản lý học liệu.", true);
    form(
      "Thêm tài liệu",
      [
        { name: "title", label: "Tên tài liệu", max: 300 },
        { name: "topic", label: "Chủ đề", max: 200 },
        {
          name: "scope",
          label: "Phạm vi áp dụng",
          type: "select",
          options: choices,
          hint: "Tài liệu của khóa học ảnh hưởng mọi lớp trong khóa; Backend sẽ kiểm tra quyền.",
        },
        {
          name: "file",
          label: "File nguồn",
          type: "file",
          accept: ".pdf,.docx,.xlsx,.json",
          hint: state.health?.rag_jobs_enabled
            ? "PDF, DOCX, XLSX hoặc FAQ JSON. Tối đa 10 MB; phiên bản mới sẽ được lập chỉ mục."
            : "PDF, DOCX, XLSX hoặc FAQ JSON. Tối đa 10 MB; chỉ lưu file, chưa lập chỉ mục.",
        },
      ],
      async (data) => {
        const file = data.get("file");

        const body = new FormData();
        body.set("title", data.get("title"));
        body.set("topic", data.get("topic"));
        body.set("scope_ids", JSON.stringify([data.get("scope")]));
        body.set("file", file);
        const result = await uploadDocument("/documents", body);
        notify(
          result.status === "queued"
            ? "Đã nhận tài liệu và xếp hàng lập chỉ mục."
            : "Đã lưu tài liệu. Chưa chạy lập chỉ mục.",
        );
        state.offsets.documents = 0;
        await navigate("documents");
      },
      "Lưu tài liệu",
    );
  },
  reindexDocument: (id) =>
    form(
      "Lập chỉ mục lại",
      [],
      async () => {
        const result = await api("/documents/" + key(id) + "/reindex", {
          method: "POST",
          body: {},
        });
        notify(
          "Đã tạo V" +
            result.version +
            " để lập chỉ mục lại. Phiên bản hiện hành vẫn được sử dụng đến khi hoàn tất.",
        );
        trackIngestion(result.job_id).catch((e) => progressFailure(e.message));
        await navigate("documents");
      },
      "Tạo phiên bản và lập chỉ mục lại",
    ),
  showIndexProgress: async (jobId) => {
    $("dialog").close();
    await trackIngestion(jobId);
  },
  retryIndex: async (jobId) => {
    const result = await api("/ingestion-jobs/" + key(jobId) + "/retry", {
      method: "POST",
    });
    $("dialog").close();
    trackIngestion(result.job_id).catch((e) => progressFailure(e.message));
    notify("Đã xếp hàng thử index lại file đã lưu.");
  },
  newVersion: (id) =>
    form(
      "Thay file tài liệu đã chọn",
      [
        {
          name: "file",
          label: "File thay thế",
          type: "file",
          accept: ".pdf,.docx,.xlsx,.json",
        },
        {
          name: "change_note",
          label: "Ghi chú thay đổi",
          type: "textarea",
          required: false,
          max: 2000,
        },
      ],
      async (data) => {
        const result = await uploadDocument(
          "/documents/" + key(id) + "/versions",
          data,
        );
        notify(
          result.status === "unchanged"
            ? "File không thay đổi so với phiên bản gần nhất."
            : result.status === "queued"
              ? "Đã nhận phiên bản mới, đang chờ lập chỉ mục. Bản hiện hành tiếp tục được sử dụng."
              : "Đã lưu phiên bản mới. Chưa chạy lập chỉ mục.",
        );
        await navigate("documents");
      },
      "Lưu phiên bản",
    ),
  revokeDocument: async (id) => {
    const d = await api("/documents/" + key(id));
    modal(
      "Thu hồi tài liệu",
      `<p>Thu hồi <strong>${esc(d.title)}</strong> khỏi các lớp áp dụng?</p><p class="muted">Lịch sử phiên bản vẫn được giữ trong hệ thống.</p>`,
      async () => {
        await api("/documents/" + key(id), { method: "DELETE" });
        notify("Đã thu hồi tài liệu.");
        await navigate("documents");
      },
      "Thu hồi",
    );
  },
  assignTicket: async (id) => {
    const t = await api("/tickets/" + key(id));
    const teachers = (
      await api("/classes/" + key(t.class_id) + "/teachers")
    ).filter((u) => u.user_active && u.assignment_active);
    if (!teachers.length)
      return notify("Lớp chưa có giảng viên đang phụ trách.", true);
    form(
      "Phân công xử lý",
      [
        {
          name: "teacher_id",
          label: "Giảng viên phụ trách",
          type: "select",
          options: teachers.map((u) => [u.id, u.display_name]),
          value: t.assignee_id,
        },
      ],
      async (data) => {
        await api("/tickets/" + key(id) + "/assign", {
          method: "POST",
          body: { teacher_id: data.get("teacher_id"), revision: t.revision },
        });
        notify("Đã phân công xử lý.");
        await ticketDetail(id);
      },
      "Phân công",
    );
  },
  answerTicket: async (id) => {
    const t = await api("/tickets/" + key(id));
    form(
      "Trả lời yêu cầu",
      [
        {
          name: "answer",
          label: "Câu trả lời chính thức",
          type: "textarea",
          max: 12000,
          hint: "Câu trả lời sẽ được lưu và hiển thị cho học viên sau khi gửi thành công.",
        },
      ],
      async (data) => {
        await api("/tickets/" + key(id) + "/answer", {
          method: "POST",
          body: { answer: data.get("answer"), revision: t.revision },
        });
        notify("Đã lưu câu trả lời và đưa vào hàng đợi gửi.");
        await navigate("tickets");
      },
      "Gửi phản hồi",
    );
  },
  closeTicket: async (id) => {
    const t = await api("/tickets/" + key(id));
    await api("/tickets/" + key(id) + "/close", {
      method: "POST",
      body: { revision: t.revision },
    });
    notify("Đã đóng yêu cầu.");
    await ticketDetail(id);
  },
  ticketFaq: async (id) => {
    const t = await api("/tickets/" + key(id));
    if (t.faq) return showFaq(t.faq.id);
    form(
      "Tạo FAQ từ câu trả lời",
      [
        { name: "topic", label: "Chủ đề", max: 200 },
        {
          name: "scope_id",
          label: "Phạm vi áp dụng",
          type: "select",
          options: scopeOptions(),
          value: "class:" + t.class_id,
        },
      ],
      async (data) => {
        const faq = await api("/tickets/" + key(id) + "/faq-draft", {
          method: "POST",
          body: Object.fromEntries(data),
        });
        notify("Đã tạo FAQ nháp.");
        await showFaq(faq.id);
      },
      "Tạo bản nháp",
    );
  },
  approveFaq: async (id) => {
    await api("/faqs/" + key(id) + "/approve", { method: "POST" });
    notify("Đã duyệt và lưu FAQ. Chưa lập chỉ mục.");
    await showFaq(id);
  },
};
async function showFaq(id) {
  const f = await api("/faqs/" + key(id));
  modal(
    "Nội dung FAQ",
    `<div class="detail-meta">${status(f.status)}<span class="muted">${esc(f.topic)}</span></div><div class="section-label">Câu hỏi</div><div class="message-box">${esc(f.question_redacted)}</div><div class="section-label">Câu trả lời đã xác nhận</div><div class="message-box answer">${esc(f.approved_answer_redacted)}</div><p class="inline-note">Phạm vi: ${esc(f.scope_id)}. Duyệt FAQ chỉ lưu nguồn chính thức; chưa chạy RAG.</p>${f.status === "draft" ? `<div class="dialog-toolbar">${button("Duyệt FAQ", "approveFaq", id, "primary")}</div>` : ""}`,
  );
}

$("login-form").onsubmit = async (e) => {
  e.preventDefault();
  $("login-button").disabled = true;
  $("login-error").textContent = "";
  try {
    if (
      state.setupRequired &&
      $("password").value !== $("password-confirm").value
    )
      throw Error("Hai mật khẩu không khớp.");
    const body = {
      username:
        state.setupRequired || $("login-role").value === "admin"
          ? $("username").value
          : $("login-profile").value,
      password: $("password").value,
    };
    if (state.setupRequired) body.display_name = $("setup-name").value;
    else {
      body.role = $("login-role").value;
      if (body.role === "student") body.class_id = $("login-class").value;
    }
    await api(state.setupRequired ? "/auth/setup" : "/auth/login", {
      method: "POST",
      body,
    });
    await enter();
  } catch (error) {
    $("login-error").textContent = error.message;
  } finally {
    $("password").value = "";
    $("password-confirm").value = "";
    $("login-button").disabled = false;
  }
};
$("logout-button").onclick = async () => {
  try {
    await api("/auth/logout", { method: "POST" });
    sessionStorage.removeItem("gos_ingestion_job");
    $("dialog").close();
    state.offsets = {};
    await showLogin();
  } catch (e) {
    notify(e.message, true);
  }
};
$("refresh-button").onclick = async () => {
  try {
    await basis();
    await navigate(state.page);
  } catch (e) {
    notify(e.message, true);
  }
};
$("dialog-close").onclick = $("dialog-cancel").onclick = () =>
  $("dialog").close();
$("dialog-form").onsubmit = async (e) => {
  e.preventDefault();
  const callback = state.modalSubmit;
  if (!callback) return;
  $("dialog-submit").disabled = true;
  $("dialog-error").textContent = "";
  try {
    await callback(new FormData(e.target));
    if (state.modalSubmit === callback) $("dialog").close();
  } catch (error) {
    $("dialog-error").textContent = error.message;
  } finally {
    $("dialog-submit").disabled = false;
  }
};
document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-page]");
  if (nav) {
    event.preventDefault();
    await navigate(nav.dataset.page);
    return;
  }
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  const action = actions[target.dataset.action];
  if (!action) return;
  target.disabled = true;
  try {
    await action(target.dataset.id);
  } catch (e) {
    notify(e.message, true);
  } finally {
    target.disabled = false;
  }
});
document.addEventListener("submit", async (event) => {
  const f = event.target;
  if (!["user-search", "document-search", "ticket-search", "report-range"].includes(f.id))
    return;
  event.preventDefault();
  const data = new FormData(f);
  if (f.id === "user-search") {
    state.userQuery = String(data.get("query") || "").trim();
    state.userRole = data.get("role");
    state.offsets.users = 0;
    await navigate("users");
  } else if (f.id === "document-search") {
    state.docQuery = data.get("query");
    state.docClass = data.get("class_id");
    state.offsets.documents = 0;
    await navigate("documents");
  } else if (f.id === "ticket-search") {
    state.ticketStatus = data.get("status");
    state.ticketClass = data.get("class_id");
    state.offsets.tickets = 0;
    await navigate("tickets");
  } else {
    const start = new Date(data.get("from") + "T00:00:00+07:00");
    const end = new Date(data.get("to") + "T00:00:00+07:00");
    end.setTime(end.getTime() + 86400000);
    if (start >= end) return notify("Khoảng ngày không hợp lệ.", true);
    state.range = { from: start.toISOString(), to: end.toISOString() };
    await navigate("reports");
  }
});
window.addEventListener("hashchange", () => {
  if (state.me) navigate(location.hash.slice(1));
});
setInterval(() => {
  if (
    state.me &&
    ["requests", "tickets"].includes(state.page) &&
    !$("dialog").open &&
    document.visibilityState === "visible"
  )
    navigate(state.page);
}, 5000);
(async () => {
  try {
    await enter();
  } catch {
    await showLogin();
  }
})();

$("dialog").addEventListener("close", () => {
  $("dialog")
    .querySelectorAll("input[type=password]")
    .forEach((input) => (input.value = ""));
});
