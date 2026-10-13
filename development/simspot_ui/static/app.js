"use strict";
// All stored/user text is assigned through textContent/value, never interpreted as HTML.
const $ = (selector, root = document) => root.querySelector(selector);
const content = $("#content");
let selected = null, view = "All contacts", search = "", renderVersion = 0;
const el = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
const append = (parent, ...children) => { parent.append(...children); return parent; };
const button = (label, action, className) => { const node = el("button", label, className); node.type = "button"; node.addEventListener("click", action); return node; };
const link = (label, href) => { const node = el("a", label); node.href = href; return node; };
const fullName = contact => `${contact.first_name} ${contact.last_name}`;
const status = message => { $("#status").textContent = message; };
async function api(path, method = "GET", data) {
  const response = await fetch(path, {method, headers: data ? {"Content-Type": "application/json"} : {}, body: data ? JSON.stringify(data) : undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}
function table(headings, rows) {
  const node = el("table"), head = el("tr"), body = el("tbody");
  for (const heading of headings) head.append(el("th", heading));
  node.append(append(el("thead"), head), body);
  for (const cells of rows) {
    const row = el("tr");
    for (const value of cells) row.append(value instanceof Node ? append(el("td"), value) : el("td", value));
    body.append(row);
  }
  return append(el("div", undefined, "table-wrap"), node);
}
async function showContacts(version) {
  const page = el("section", undefined, "page");
  const refresh = button("Refresh", () => render());
  const create = button("Create Contact", () => { const dialog = $("#create-dialog"); $("form", dialog).reset(); $(".form-error", dialog).textContent = ""; dialog.showModal(); }, "primary");
  page.append(append(el("div", undefined, "page-head"), el("h1", "Contacts"), append(el("div", undefined, "head-actions"), refresh, create)));
  const tabs = el("div", undefined, "tabs");
  for (const name of ["All contacts", "All customers"]) tabs.append(button(name, () => {view = name; render();}, view === name ? "active" : ""));
  const input = el("input"); input.type = "search"; input.placeholder = "Search ( / )"; input.setAttribute("aria-label", "Search ( / )"); input.value = search;
  const toolbar = append(el("div", undefined, "toolbar"), input, button("Clear input", () => { search = ""; input.value = ""; loadRows(); input.focus(); }));
  const results = el("div"); page.append(tabs, toolbar, results); content.replaceChildren(page);
  let searchVersion = 0;
  async function loadRows() {
    const current = ++searchVersion;
    try {
      const records = await api(`/api/contacts?q=${encodeURIComponent(search)}&stage=${view === "All customers" ? "Customer" : ""}`);
      if (current !== searchVersion || version !== renderVersion) return;
      const rows = records.map(c => [link(fullName(c), `#contact/${c.contact_id}`), c.email, c.company_name, el("span", c.lifecycle_stage, "badge"), c.job_title || "--"]);
      results.replaceChildren(table(["Name", "Email", "Company Name", "Lifecycle Stage", "Job Title"], rows), el("div", `${records.length} contacts`, "count"));
      if (!records.length) results.append(el("p", "No contacts match your search.", "empty"));
    } catch (error) { status(error.message); }
  }
  input.addEventListener("input", () => { search = input.value; loadRows(); });
  await loadRows();
}
function openForm(id) {
  const dialog = $(id), form = $("form", dialog);
  form.reset(); $(".form-error", dialog).textContent = "";
  form.dataset.contact = selected.contact_id;
  if (id === "#editor") {
    for (const field of ["first_name", "last_name", "job_title", "email"]) form.elements[field].value = selected[field];
  } else if (id === "#note-dialog") {
    $(".company-label", form).textContent = selected.company_name;
    $(".association", form).hidden = !selected.company_id;
    $("details", form).open = false;
    updateFormAssociations(form);
    $("button[type=submit]", form).disabled = true;
  } else {
    $(".company-label", form).textContent = selected.company_name;
    $(".association", form).hidden = !selected.company_id;
    $("details", form).open = false;
    updateFormAssociations(form);
    const day = new Date(); let remaining = 3;
    while (remaining) { day.setDate(day.getDate() + 1); if (![0,6].includes(day.getDay())) remaining--; }
    form.elements.due_date.value = `${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,"0")}-${String(day.getDate()).padStart(2,"0")}`;
    $("button[type=submit]", form).disabled = true;
  }
  dialog.showModal();
}
async function showContact(id, version) {
  const [contact, activities] = await Promise.all([api(`/api/contacts/${encodeURIComponent(id)}`), api(`/api/contacts/${encodeURIComponent(id)}/activities`)]);
  if (version !== renderVersion) return;
  selected = contact; document.title = `${fullName(contact)} | SimSpot`;
  const layout = el("section", undefined, "detail"), identity = el("aside", undefined, "identity");
  const back = link("‹ Contacts", "#contacts"); back.className = "back";
  identity.append(back, append(el("div", undefined, "edit-line"), el("h1", fullName(contact)), button("Edit", () => openForm("#editor"))));
  identity.append(el("p", contact.job_title || contact.company_name || "New lead", "muted"), el("div", contact.email, "email"));
  const note = button("Note", () => openForm("#note-dialog")); note.setAttribute("aria-label", "Create a note");
  const task = button("Task", () => openForm("#task-dialog")); task.setAttribute("aria-label", "Create a task");
  identity.append(append(el("div", undefined, "quick-actions"), note, task));
  const properties = append(el("section", undefined, "section"), el("h2", "Key information"));
  for (const [name, value] of [["Email", contact.email], ["Company Name", contact.company_name || "--"], ["Job Title", contact.job_title || "--"], ["Record ID", contact.contact_id]]) properties.append(append(el("div", undefined, "property"), el("label", name), el("span", value)));
  const stage = el("select"); stage.setAttribute("aria-label", "Lifecycle Stage");
  for (const name of ["Lead", "Opportunity", "Customer"]) { const option = el("option", name); option.value = name; stage.append(option); }
  stage.value = contact.lifecycle_stage;
  stage.addEventListener("change", async () => { stage.disabled = true; try { await api(`/api/contacts/${contact.contact_id}`, "PATCH", {lifecycle_stage: stage.value}); status("Lifecycle Stage saved."); await render(); } catch (error) { status(error.message); stage.value = contact.lifecycle_stage; stage.disabled = false; } });
  properties.append(append(el("div", undefined, "property"), el("label", "Lifecycle Stage"), stage)); identity.append(properties);
  const center = el("section", undefined, "center"), tabs = el("div", undefined, "tabs"), feed = el("div");
  const showFeed = mode => {
    feed.replaceChildren();
    tabs.querySelectorAll("button").forEach(b => b.classList.toggle("active", b.textContent === mode));
    if (mode === "Catch-up") feed.append(append(el("article", undefined, "card"), el("h2", "Contact insights"), el("p", activities.length ? `${activities.length} saved activities for this contact.` : "No recent activities or communications are recorded. Add activities or associations to see an updated summary.")));
    feed.append(el("h2", mode === "Activities" ? "Activities" : "Recent interactions"));
    if (!activities.length) feed.append(el("div", "No activity on this record.", "card empty"));
    for (const item of activities) {
      const card = el("article", undefined, "card activity");
      const heading = item.kind === "note" ? "Note" : item.kind === "message" ? "Customer message" : item.title;
      const timestamp = item.kind === "message" ? item.received_at : item.created_at;
      card.append(el("h3", heading), el("small", new Date(timestamp).toLocaleString()));
      if (item.kind === "task") card.append(el("p", `${item.task_type} · ${item.status} · ${item.priority} priority`), el("p", `Activity date: ${item.due_date} ${item.due_time} · ${item.assigned_to}`));
      const associated = item.company_id ? `2 records: ${fullName(contact)} and ${contact.company_name}` : `1 record: ${fullName(contact)}`;
      card.append(el("p", item.body), el("small", `Associated with ${associated}`)); feed.append(card);
    }
  };
  for (const name of ["Catch-up", "Activities"]) tabs.append(button(name, () => showFeed(name)));
  center.append(tabs, feed); showFeed("Activities");
  const associations = el("aside", undefined, "associations");
  const companyCard = append(el("div", undefined, "card"), el("h2", `Companies (${contact.company_id ? 1 : 0})`));
  if (contact.company_id) companyCard.append(link(contact.company_name, "#companies"), el("p", "Primary", "badge"));
  else companyCard.append(el("p", "No company associated.", "muted"));
  associations.append(companyCard, append(el("div", undefined, "card"), el("h2", "Deals (0)"), el("p", "Track the revenue opportunities associated with this record.", "muted")));
  layout.append(identity, center, associations); content.replaceChildren(layout);
}
async function render() {
  const version = ++renderVersion, route = location.hash.slice(1) || "contacts";
  document.title = "Contacts | SimSpot";
  document.querySelectorAll(".sidebar a").forEach(a => { if (route.startsWith(a.hash.slice(1)) || (route.startsWith("contact/") && a.hash === "#contacts")) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  try {
    if (route.startsWith("contact/")) return await showContact(route.slice(8), version);
    selected = null;
    if (route === "home") {
      content.replaceChildren(append(el("section", undefined, "home"), el("h1", "Start growing your pipeline, Demo"), el("p", "Explore six fictional contacts, record discovery notes, and organize follow-up tasks."), link("Open contacts", "#contacts")));
    } else if (route === "companies") {
      const companies = await api("/api/companies"); if (version !== renderVersion) return;
      content.replaceChildren(append(el("section", undefined, "page"), el("h1", "Companies"), el("p", "Five intended fictional associations. These are local fixture data."), table(["Company Name", "Record ID"], companies.map(c => [c.name, c.company_id]))));
    } else if (route === "deals") {
      content.replaceChildren(append(el("section", undefined, "page"), el("h1", "Deals"), el("p", "Sales Pipeline"), el("div", "No deals. Deal creation is outside this experimental contact workflow.", "card empty")));
    } else await showContacts(version);
  } catch (error) { status(error.message); content.replaceChildren(el("p", "Could not load this view. Return to Contacts and try again.", "page")); }
}
document.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", () => b.closest("dialog").close()));
function updateFormAssociations(form) {
  const includeCompany = Boolean(selected.company_id && form.elements.include_company.checked);
  const forRecord = $(".for-record", form);
  if (forRecord) forRecord.textContent = `For ${fullName(selected)}${includeCompany ? ` and ${selected.company_name}` : ""}`;
  $("summary", form).textContent = `Associated with ${includeCompany ? "2 records" : "1 record"}`;
}
$("#create-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget, submit = $("button[type=submit]", form);
  if (!form.checkValidity()) return;
  submit.disabled = true;
  try {
    const created = await api("/api/contacts", "POST", Object.fromEntries(new FormData(form)));
    form.closest("dialog").close(); status("Contact created."); location.hash = `contact/${created.contact_id}`;
  } catch (error) { $(".form-error", form).textContent = error.message; }
  finally { submit.disabled = false; }
});
for (const id of ["#note-form", "#task-form"]) {
  const form = $(id);
  form.elements.include_company.addEventListener("change", () => updateFormAssociations(form));
}
for (const [id, suffix, method] of [["#identity-form", "", "PATCH"], ["#note-form", "/notes", "POST"], ["#task-form", "/tasks", "POST"]]) {
  const form = $(id), submit = $("button[type=submit]", form);
  form.addEventListener("input", () => { submit.disabled = !form.checkValidity() || (id === "#note-form" && !form.elements.body.value.trim()) || (id === "#task-form" && !form.elements.title.value.trim()); });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (submit.disabled) return; submit.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(form));
      if (id !== "#identity-form") payload.include_company = form.elements.include_company.checked;
      await api(`/api/contacts/${encodeURIComponent(form.dataset.contact)}${suffix}`, method, payload);
      form.closest("dialog").close(); status(suffix === "/notes" ? "Note created and saved." : suffix === "/tasks" ? "Task created and saved." : "Contact saved."); await render();
    } catch (error) { $(".form-error", form).textContent = error.message; }
    finally { submit.disabled = false; }
  });
}
$("#global-search").addEventListener("keydown", event => { if (event.key === "Enter") { search = event.target.value; view = "All contacts"; if (location.hash === "#contacts") render(); else location.hash = "contacts"; } });
window.addEventListener("hashchange", render);
render();
