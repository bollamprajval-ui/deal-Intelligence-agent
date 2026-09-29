const $app = document.getElementById("app");
let deals = [];
let health = { ollama: false, model: null, detail: "" };
let cache = {};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      detail = await res.text();
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

function parseHash() {
  const raw = (location.hash || "#/").replace(/^#/, "");
  const parts = raw.split("/").filter(Boolean);
  if (!parts.length) return { page: "home" };
  if (parts[0] === "new") return { page: "new" };
  if (parts[0] === "d" && parts[1]) {
    return { page: parts[2] || "ask", id: parts[1] };
  }
  return { page: "home" };
}

function go(hash) {
  location.hash = hash;
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function stageLabel(s) {
  return (s || "").replace(/_/g, " ");
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function loadDeals() {
  deals = await api("/deals");
}

async function loadDoc(id) {
  if (!cache[id]) cache[id] = {};
  const [doc, chat, reasoning, hindsight] = await Promise.all([
    api(`/deals/${id}`),
    api(`/deals/${id}/chat`),
    api(`/deals/${id}/reasoning`),
    api(`/deals/${id}/hindsight`),
  ]);
  cache[id] = { ...cache[id], doc, chat, reasoning, hindsight };
  return cache[id];
}

function pct(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return "";
  return Math.round(n * 100) + "% match";
}

function hindsightCards(items) {
  if (!items || !items.length) {
    return `<p>No closed deals to compare yet. Close a deal with a log and it will show up here.</p>`;
  }
  return items
    .map((m) => {
      const meta = m.metadata || {};
      const why = meta.outcome_reason || m.outcome_reason || "";
      const outcome = meta.outcome || m.outcome || "—";
      return `<div class="hit">
        <strong>${esc(m.name || "Closed deal")}</strong>
        <span class="score">${esc(outcome)}${m.score != null ? " · " + pct(m.score) : ""}</span>
        ${why ? `<p>${esc(why)}</p>` : ""}
      </div>`;
    })
    .join("");
}

function documentHtml(doc, reasoning, compact) {
  const { deal, people, timeline, stages, signals, reviews } = doc;
  const tags = [...new Set((signals || []).map((s) => s.signal_type.replace(/_/g, " ")))];
  const log = compact ? (timeline || []).slice(-5) : timeline || [];
  const notes = compact ? (reviews || []).slice(0, 2) : reviews || [];
  let html = "";
  html += `<div class="${compact ? "rail-block" : "log-item"}"><h3>1 · Snapshot</h3>
    <p><strong>${esc(deal.name)}</strong></p>
    <p>Stage: ${esc(stageLabel(deal.stage))}${deal.budget != null ? " · Budget: " + esc(deal.budget) : ""}</p>
    ${deal.outcome ? `<p>Outcome: ${esc(deal.outcome)}</p>` : "<p>Still open</p>"}
    ${deal.outcome_reason ? `<p>${esc(deal.outcome_reason)}</p>` : ""}
    ${(stages || []).length ? `<p>Path: ${esc(stages.map((s) => stageLabel(s.stage)).join(" → "))}</p>` : ""}
  </div>`;
  html += `<div class="${compact ? "rail-block" : "log-item"}"><h3>2 · People</h3>`;
  if (people && people.length) {
    html += people
      .map((p) => `<p>${esc(p.name)} — ${esc((p.role || "role not set").replace(/_/g, " "))}${p.email ? " · " + esc(p.email) : ""}</p>`)
      .join("");
  } else html += `<p>No one linked yet.</p>`;
  html += `</div>`;
  html += `<div class="${compact ? "rail-block" : "log-item"}"><h3>3 · Signals</h3>`;
  html += tags.length ? `<p>${esc(tags.join(" · "))}</p>` : `<p>None tagged yet.</p>`;
  html += `</div>`;
  html += `<div class="${compact ? "rail-block" : "log-item"}"><h3>4 · Interaction log</h3>`;
  if (!log.length) html += `<p>Nothing logged yet. Use Add update.</p>`;
  else {
    html += log
      .map(
        (row) =>
          `<p><span class="score">${esc(row.tool_source)} · ${esc(when(row.occurred_at))}</span><br>${esc(row.summary)}</p>`
      )
      .join("");
  }
  html += `</div>`;
  html += `<div class="${compact ? "rail-block" : "log-item"}"><h3>5 · Your notes</h3>`;
  if (notes.length) {
    html += notes.map((n) => `<p>${esc(n.note)}</p>`).join("");
  } else html += `<p>No human notes yet.</p>`;
  html += `</div>`;
  if (!compact) {
    html += `<div class="log-item"><h3>6 · AI memory</h3>`;
    if (reasoning && reasoning.length) {
      html += reasoning
        .map((r) => `<p><span class="score">${esc(when(r.created_at))}</span><br>${esc(r.reasoning)}</p>`)
        .join("");
    } else html += `<p>No Ask turns yet.</p>`;
    html += `</div>`;
  }
  return html;
}

function layout(inner, { id, tab, title, pageClass } = {}) {
  const deal = deals.find((d) => d.id === id);
  const healthCls = health.ollama ? "health" : "health off";
  const healthTxt = health.ollama
    ? `Ollama · ${health.model || "local model"}`
    : "Ollama off — start it to get answers";
  const tabs = id
    ? `<nav class="tabs">
        <a href="#/d/${id}/ask" class="${tab === "ask" ? "on" : ""}">Ask</a>
        <a href="#/d/${id}/doc" class="${tab === "doc" ? "on" : ""}">Document</a>
        <a href="#/d/${id}/hindsight" class="${tab === "hindsight" ? "on" : ""}">Hindsight</a>
        <a href="#/d/${id}/add" class="${tab === "add" ? "on" : ""}">Add update</a>
        <a href="#/d/${id}/end" class="${tab === "end" ? "on" : ""}">Close</a>
      </nav>`
    : "";
  const list = deals.length
    ? deals
        .map(
          (d) => `<a href="#/d/${d.id}/ask" class="${d.id === id ? "on" : ""}">
            ${esc(d.name)}
            <small>${esc(stageLabel(d.outcome || d.stage))}</small>
          </a>`
        )
        .join("")
    : `<p class="empty" style="padding:1rem">No deals yet.</p>`;

  $app.innerHTML = `
    <div class="app">
      <aside class="sidebar">
        <div class="brand">
          <h1>Deal AI</h1>
          <p>One AI per deal. It only knows that file.</p>
          <div class="${healthCls}">${esc(healthTxt)}</div>
        </div>
        <div class="side-actions">
          <button class="primary" type="button" id="start-deal" style="width:100%">Start a deal</button>
        </div>
        <nav class="deal-nav">${list}</nav>
      </aside>
      <section class="main">
        <header class="top">
          <div class="top-left">
            <button class="ghost menu-btn" type="button" id="menu-btn">Deals</button>
            <h2>${esc(title || (deal ? deal.name : "Deals"))}</h2>
          </div>
          ${tabs ? `<div class="tabs-wrap">${tabs}</div>` : ""}
        </header>
        <div class="page ${pageClass || ""}">${inner}</div>
      </section>
    </div>`;
  document.getElementById("start-deal").onclick = () => go("/new");
  const menu = document.getElementById("menu-btn");
  if (menu) {
    menu.onclick = () => document.querySelector(".app").classList.toggle("nav-open");
  }
}

function pageHome() {
  layout(
    `<div class="card">
      <h3>How this works</h3>
      <ol class="steps">
        <li><strong>Start a deal</strong> — name it. Budget and a contact are optional.</li>
        <li><strong>Add update</strong> — paste mail or notes. That fills the document.</li>
        <li><strong>Ask</strong> — chat on the left. The document the AI is using is on the right.</li>
        <li><strong>Document</strong> — full track, numbered. <strong>Hindsight</strong> — closed deals this one is compared to.</li>
        <li><strong>Close</strong> — won, lost, or stalled. That file trains the next deal.</li>
      </ol>
      <button class="primary" type="button" id="home-start">Start a deal</button>
    </div>`,
    { title: "Your deals" }
  );
  document.getElementById("home-start").onclick = () => go("/new");
}

function pageNew() {
  layout(
    `<div class="card">
      <h3>A few details</h3>
      <p class="hint">That’s enough to open a file. You can add more later.</p>
      <form id="new-form">
        <div class="field">
          <label>What is this deal?</label>
          <input name="name" required placeholder="Northwind — ERP license" />
        </div>
        <div class="field">
          <label>Budget (optional)</label>
          <input name="budget" type="number" min="0" step="1000" placeholder="Skip if you don’t know" />
        </div>
        <div class="field">
          <label>Main person on their side (optional)</label>
          <input name="person" placeholder="Name" />
        </div>
        <div class="field">
          <label>Their email (optional)</label>
          <input name="email" type="email" placeholder="name@company.com" />
        </div>
        <p class="err" id="new-err" hidden></p>
        <button class="primary" type="submit">Open deal</button>
      </form>
    </div>`,
    { title: "Start a deal" }
  );
  document.getElementById("new-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const err = document.getElementById("new-err");
    err.hidden = true;
    try {
      const budget = f.budget.value ? Number(f.budget.value) : null;
      const created = await api("/deals", {
        method: "POST",
        body: JSON.stringify({ name: f.name.value, budget }),
      });
      if (f.person.value.trim()) {
        await api(`/deals/${created.deal_id}/people`, {
          method: "POST",
          body: JSON.stringify({
            name: f.person.value.trim(),
            email: f.email.value || null,
            role: "decision_maker",
            side: "theirs",
          }),
        });
      }
      await loadDeals();
      go(`/d/${created.deal_id}/ask`);
    } catch (ex) {
      err.hidden = false;
      err.textContent = ex.message;
    }
  };
}

async function pageAsk(id) {
  layout(`<p class="empty">Loading this deal’s AI…</p>`, {
    id,
    tab: "ask",
    title: deals.find((d) => d.id === id)?.name,
  });
  const { chat, doc, hindsight } = await loadDoc(id);
  const msgs = (chat || [])
    .map(
      (m) => `<div class="msg ${m.role === "user" ? "user" : "ai"}">
        <div class="who">${m.role === "user" ? "You" : "Deal AI"}</div>
        <p>${esc(m.content)}</p>
      </div>`
    )
    .join("");
  layout(
    `<div class="ask-split">
      <div class="chat-pane">
        <div class="chat-wrap">
          <div class="messages" id="messages">${
            msgs || `<p class="empty">This AI only sees this deal’s document. Ask, or add an update first.</p>`
          }</div>
          <div class="composer-wrap">
            <form class="composer" id="ask-form">
              <textarea id="ask-input" rows="2" placeholder="Ask about this deal"></textarea>
              <button class="primary" type="submit">Ask</button>
            </form>
            <p class="err" id="ask-err" hidden></p>
          </div>
        </div>
      </div>
      <aside class="context-rail">
        <div class="rail-block">
          <h3>What the AI is reading</h3>
          <p>Answers come from this document, plus hindsight below.</p>
        </div>
        ${documentHtml(doc, [], true)}
        <a class="more-link" href="#/d/${id}/doc">Open full document</a>
        <div class="rail-block" style="margin-top:1.2rem">
          <h3>Hindsight</h3>
          ${hindsightCards(hindsight)}
          <a class="more-link" href="#/d/${id}/hindsight">Hindsight page</a>
        </div>
      </aside>
    </div>`,
    { id, tab: "ask", title: deals.find((d) => d.id === id)?.name, pageClass: "split-page" }
  );
  const box = document.getElementById("messages");
  box.scrollTop = box.scrollHeight;
  document.getElementById("ask-form").onsubmit = async (e) => {
    e.preventDefault();
    const input = document.getElementById("ask-input");
    const err = document.getElementById("ask-err");
    const message = input.value.trim();
    if (!message) return;
    err.hidden = true;
    input.value = "";
    box.insertAdjacentHTML(
      "beforeend",
      `<div class="msg user"><div class="who">You</div><p>${esc(message)}</p></div>
       <div class="msg ai" id="pending"><div class="who">Deal AI</div><p>Thinking…</p></div>`
    );
    box.scrollTop = box.scrollHeight;
    try {
      const { reply } = await api(`/deals/${id}/chat`, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      document.getElementById("pending").querySelector("p").textContent = reply;
      cache[id] = {};
    } catch (ex) {
      document.getElementById("pending")?.remove();
      err.hidden = false;
      err.textContent = ex.message;
    }
    box.scrollTop = box.scrollHeight;
  };
}

async function pageAdd(id) {
  layout(
    `<div class="card">
      <h3>What happened?</h3>
      <p class="hint">Paste a mail, call note, or just type it. It goes on this deal’s log.</p>
      <form id="add-form">
        <div class="field">
          <label>Update</label>
          <textarea name="content" required placeholder="They asked for a revised timeline. Budget is fine."></textarea>
        </div>
        <div class="row">
          <div class="field">
            <label>Kind</label>
            <select name="source">
              <option value="mail">Mail</option>
              <option value="meeting">Meeting</option>
              <option value="voice_note">Call</option>
              <option value="paste">Note</option>
            </select>
          </div>
          <div class="field">
            <label>Stage now</label>
            <select name="stage">
              <option value="">No change</option>
              <option value="contact">Contact</option>
              <option value="discovery">Discovery</option>
              <option value="proposal">Proposal</option>
              <option value="negotiation">Negotiation</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label>Your read (optional)</label>
          <input name="note" placeholder="Champion is real. Legal is the wait." />
        </div>
        <p class="err" id="add-err" hidden></p>
        <button class="primary" type="submit">Save to this deal</button>
      </form>
    </div>`,
    { id, tab: "add", title: deals.find((d) => d.id === id)?.name }
  );
  document.getElementById("add-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const err = document.getElementById("add-err");
    err.hidden = true;
    try {
      await api(`/deals/${id}/inputs`, {
        method: "POST",
        body: JSON.stringify({ content: f.content.value, source: f.source.value }),
      });
      if (f.stage.value) {
        await api(`/deals/${id}/stage`, {
          method: "POST",
          body: JSON.stringify({ stage: f.stage.value }),
        });
      }
      if (f.note.value.trim()) {
        await api(`/deals/${id}/reviews`, {
          method: "POST",
          body: JSON.stringify({ note: f.note.value.trim() }),
        });
      }
      cache[id] = {};
      await loadDeals();
      go(`/d/${id}/doc`);
    } catch (ex) {
      err.hidden = false;
      err.textContent = ex.message;
    }
  };
}

async function pageDoc(id) {
  layout(`<p class="empty">Loading document…</p>`, {
    id,
    tab: "doc",
    title: deals.find((d) => d.id === id)?.name,
  });
  const { doc, reasoning } = await loadDoc(id);
  layout(
    `<div class="doc-page">
      <p class="hint">Six blocks. Same file the AI reads on Ask.</p>
      ${documentHtml(doc, reasoning, false)}
    </div>`,
    { id, tab: "doc", title: doc.deal.name }
  );
}

async function pageHindsight(id) {
  layout(`<p class="empty">Loading hindsight…</p>`, {
    id,
    tab: "hindsight",
    title: deals.find((d) => d.id === id)?.name,
  });
  const [{ hindsight, doc }, library] = await Promise.all([
    loadDoc(id),
    api("/hindsight").catch(() => []),
  ]);
  const libraryCards = (library || []).map((h) => ({
    name: h.name,
    outcome: h.outcome,
    outcome_reason: h.outcome_reason,
    metadata: { outcome: h.outcome, outcome_reason: h.outcome_reason },
  }));
  layout(
    `<div class="card wide">
      <h3>What hindsight is</h3>
      <p class="hint">When you close a deal, the outcome and log are stored. This deal’s AI compares its document to those closed files and uses the closest ones. If nothing is close, it says so instead of inventing a comparison.</p>
      <div class="doc-sec">
        <h3>Closest to ${esc(doc.deal.name)}</h3>
        ${hindsightCards(hindsight)}
      </div>
      <div class="doc-sec">
        <h3>All closed files in the library</h3>
        ${
          libraryCards.length
            ? hindsightCards(libraryCards)
            : `<p>No closed deals yet. Use Close when a deal ends.</p>`
        }
      </div>
    </div>`,
    { id, tab: "hindsight", title: doc.deal.name }
  );
}

async function pageEnd(id) {
  const deal = deals.find((d) => d.id === id);
  const closed = Boolean(deal?.outcome);
  layout(
    `<div class="card">
      <h3>${closed ? "This deal is closed" : "End this deal"}</h3>
      <p class="hint">${
        closed
          ? "It is saved into hindsight for the next deal’s AI."
          : "Won, lost, or stalled — in your words. That becomes training for later deals."
      }</p>
      <form id="end-form">
        <div class="field">
          <label>Outcome</label>
          <select name="outcome" required ${closed ? "disabled" : ""}>
            <option value="won">Won</option>
            <option value="lost">Lost</option>
            <option value="stalled">Stalled</option>
          </select>
        </div>
        <div class="field">
          <label>Why, in your words</label>
          <textarea name="outcome_reason" ${closed ? "disabled" : ""} placeholder="They moved after legal signed off."></textarea>
        </div>
        <p class="err" id="end-err" hidden></p>
        <button class="primary" type="submit" ${closed ? "disabled" : ""}>Save close</button>
      </form>
    </div>`,
    { id, tab: "end", title: deal?.name }
  );
  if (closed) return;
  document.getElementById("end-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const err = document.getElementById("end-err");
    try {
      await api(`/deals/${id}/close`, {
        method: "POST",
        body: JSON.stringify({
          outcome: f.outcome.value,
          outcome_reason: f.outcome_reason.value || null,
        }),
      });
      cache[id] = {};
      await loadDeals();
      go(`/d/${id}/hindsight`);
    } catch (ex) {
      err.hidden = false;
      err.textContent = ex.message;
    }
  };
}

async function route() {
  try {
    health = await api("/health").catch(() => health);
    await loadDeals();
    const r = parseHash();
    if (r.page === "new") return pageNew();
    if (r.id) {
      if (!deals.some((d) => d.id === r.id)) {
        layout(`<p class="empty">That deal was not found.</p>`, { title: "Missing" });
        return;
      }
      if (r.page === "add") return pageAdd(r.id);
      if (r.page === "doc" || r.page === "log" || r.page === "document") return pageDoc(r.id);
      if (r.page === "hindsight") return pageHindsight(r.id);
      if (r.page === "end") return pageEnd(r.id);
      return pageAsk(r.id);
    }
    pageHome();
  } catch (ex) {
    $app.innerHTML = `<div class="page"><p class="err">${esc(ex.message)}</p></div>`;
  }
}

window.addEventListener("hashchange", route);
route();
