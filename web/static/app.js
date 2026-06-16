/* ShopSafe live pipeline theater — consumes /api/stream SSE events. */

"use strict";

const $ = (sel, root = document) => root.querySelector(sel);

const el = (tag, cls, html) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html !== undefined) node.innerHTML = html;
  return node;
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

const STAGE_META = {
  planning:    { index: "01", name: "Planner",   running: "decomposing query" },
  researching: { index: "02", name: "Researcher", running: "searching the live web" },
  writing:     { index: "03", name: "Verdict writer", running: "drafting sourced verdict" },
  auditing:    { index: "04", name: "Auditor",   running: "scoring groundedness" },
};

// ── Page chrome ──────────────────────────────────────────────

$("#case-no").textContent =
  "CASE Nº " + Math.random().toString(16).slice(2, 8).toUpperCase();
$("#case-date").textContent = new Date()
  .toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
  .toUpperCase();

// ── Run state ────────────────────────────────────────────────

let source = null;

function startRun(query) {
  if (source) source.close();

  $("#pipeline").hidden = false;
  $("#report").hidden = true;
  $("#report").innerHTML = "";
  $("#passes").innerHTML = "";
  $("#live-dot").classList.remove("idle");
  $("#run-btn").disabled = true;
  $("#pipeline").scrollIntoView({ behavior: "smooth", block: "start" });

  const passes = {}; // pass number → { section, stages: {stageKey: node} }

  function getPass(n, critique) {
    if (passes[n]) return passes[n];
    const section = el("div", "pass");
    const head = el("div", "pass-head");
    head.appendChild(
      el("span", "pass-num", n === 1 ? "Pass 01 — initial verification" : `Pass 0${n} — refinement`)
    );
    section.appendChild(head);
    if (n > 1 && critique) {
      section.appendChild(
        el("div", "refine-note", `Auditor rejected the previous draft — re-planning with new queries`)
      );
    }
    $("#passes").appendChild(section);
    passes[n] = { section, stages: {} };
    return passes[n];
  }

  function getStage(passNum, key, critique) {
    const pass = getPass(passNum, critique);
    if (pass.stages[key]) return pass.stages[key];
    const meta = STAGE_META[key];
    // previous stage in this pass is done now
    Object.values(pass.stages).forEach((s) => {
      s.classList.remove("running");
      s.classList.add("done");
      $(".stage-status", s).textContent = "complete";
    });
    const stage = el("div", "stage running");
    stage.appendChild(
      el(
        "div",
        "stage-title",
        `<span class="stage-index">${meta.index}</span> ${meta.name}` +
          `<span class="stage-status">${meta.running}</span>`
      )
    );
    stage.appendChild(el("div", "stage-body"));
    pass.section.appendChild(stage);
    pass.stages[key] = stage;
    stage.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return stage;
  }

  source = new EventSource(`/api/stream?q=${encodeURIComponent(query)}`);

  source.addEventListener("config", (e) => {
    const d = JSON.parse(e.data);
    $("#config-line").textContent = `engine online · ${d.describe}`;
  });

  source.addEventListener("stage", (e) => {
    const d = JSON.parse(e.data);
    getStage(d.pass, d.stage, d.critique);
  });

  source.addEventListener("plan", (e) => {
    const d = JSON.parse(e.data);
    const stage = getStage(d.pass, "planning");
    const body = $(".stage-body", stage);
    const ingredients = (d.ingredients_to_check || [])
      .map((i) => `<span class="tag">${esc(i)}</span>`)
      .join("");
    body.innerHTML = `
      <div class="plan-grid">
        <div class="plan-key">Product</div>
        <div class="plan-val"><strong>${esc(d.product_name)}</strong></div>
        ${
          d.user_context
            ? `<div class="plan-key">User context</div>
               <div class="plan-val"><span class="context-flag">⚑ ${esc(d.user_context)}</span></div>`
            : ""
        }
        <div class="plan-key">Ingredients</div>
        <div class="plan-val">${ingredients || "—"}</div>
      </div>
      <div class="query-list"></div>`;
    const list = $(".query-list", body);
    (d.queries || []).forEach((q, i) => {
      const row = el("div", "query-row");
      row.dataset.query = q.query;
      const domains = q.include_domains?.length
        ? `<span class="domains">⌂ ${esc(q.include_domains.join(", "))}</span>`
        : "";
      row.innerHTML = `
        <span class="query-idx">${String(i + 1).padStart(2, "0")}</span>
        <span class="query-text">${esc(q.query)}${domains}</span>
        <span class="query-state searching">queued</span>
        <span class="query-purpose">${esc(q.purpose)}</span>`;
      list.appendChild(row);
    });
  });

  source.addEventListener("search_done", (e) => {
    const d = JSON.parse(e.data);
    const pass = passes[d.pass];
    if (!pass) return;
    const rows = pass.section.querySelectorAll(".query-row");
    for (const row of rows) {
      if (row.dataset.query === d.query) {
        const state = $(".query-state", row);
        state.textContent = `${d.sources} source${d.sources === 1 ? "" : "s"} ✓`;
        state.className = "query-state found";
        break;
      }
    }
  });

  source.addEventListener("verdict", (e) => {
    const d = JSON.parse(e.data);
    const stage = getStage(d.pass, "writing");
    const body = $(".stage-body", stage);
    const minis = (d.ingredients || [])
      .map(
        (ing) =>
          `<span><span class="pill ${esc(ing.verdict)}">${esc(ing.verdict)}</span>${esc(ing.name)}</span>`
      )
      .join(" &nbsp; ");
    const citations = (d.ingredients || []).reduce((n, i) => n + (i.claims?.length || 0), 0);
    body.innerHTML = `
      <div class="verdict-mini">
        <span class="pill ${esc(d.overall_verdict)}">${esc(d.overall_verdict)}</span>
        <strong>${esc(d.product_name)}</strong>
        <span>· ${citations} cited claim${citations === 1 ? "" : "s"}</span>
      </div>
      <div class="mini-ingredients">${minis}</div>`;
  });

  source.addEventListener("audit", (e) => {
    const d = JSON.parse(e.data);
    const stage = getStage(d.pass, "auditing");
    const body = $(".stage-body", stage);
    const threshold = d.threshold ?? 0.85;
    const gauge = (name, score) => {
      const fail = score < threshold;
      return `
        <div class="gauge">
          <span class="gauge-name">${name}</span>
          <div class="gauge-track">
            <div class="gauge-fill ${fail ? "fail" : ""}" data-w="${(score * 100).toFixed(1)}"></div>
            <div class="gauge-tick" style="left:${threshold * 100}%"></div>
          </div>
          <span class="gauge-val">${score.toFixed(2)}</span>
        </div>`;
    };
    body.innerHTML = `
      <div class="gauges">
        ${gauge("Groundedness", d.groundedness_score)}
        ${gauge("Authority", d.authority_score)}
        ${gauge("Tone safety", d.tone_safety_score)}
      </div>
      <div class="audit-result">
        <span class="audit-stamp ${d.passed ? "pass" : "fail"}">
          ${d.passed ? "AUDIT PASSED" : "REJECTED"}
        </span>
        <span>mean ${d.mean.toFixed(2)} · gate: all dimensions ≥ ${threshold}</span>
      </div>
      ${
        d.critique && !d.passed
          ? `<div class="critique"><span class="critique-label">Auditor critique → fed back to planner</span>${esc(d.critique)}</div>`
          : ""
      }`;
    // animate gauge fills on next frame
    requestAnimationFrame(() =>
      requestAnimationFrame(() =>
        body.querySelectorAll(".gauge-fill").forEach((f) => (f.style.width = f.dataset.w + "%"))
      )
    );
    // auditing is the last stage of a pass
    stage.classList.remove("running");
    stage.classList.add("done");
    $(".stage-status", stage).textContent = "complete";
  });

  source.addEventListener("final", (e) => {
    const d = JSON.parse(e.data);
    renderReport(d);
  });

  source.addEventListener("error", (e) => {
    // server-sent error event has data; transport errors do not
    if (e.data) {
      const d = JSON.parse(e.data);
      $("#report").hidden = false;
      $("#report").appendChild(
        el("div", "error-card", `<strong>Run failed.</strong> ${esc(d.message)}`)
      );
    }
    finish();
  });

  source.addEventListener("done", finish);

  function finish() {
    if (source) {
      source.close();
      source = null;
    }
    $("#live-dot").classList.add("idle");
    $("#run-btn").disabled = false;
    document.querySelectorAll(".stage.running").forEach((s) => {
      s.classList.remove("running");
      s.classList.add("done");
      $(".stage-status", s).textContent = "complete";
    });
  }
}

// ── Final report card ────────────────────────────────────────

function renderReport(result) {
  const v = result.final_verdict;
  const a = result.final_audit;
  const citations = (v.ingredients || []).reduce((n, i) => n + (i.claims?.length || 0), 0);

  const ingredients = (v.ingredients || [])
    .map(
      (ing) => `
      <div class="ingredient">
        <div class="ingredient-head">
          <span class="ingredient-name">${esc(ing.name)}</span>
          <span class="pill ${esc(ing.verdict)}">${esc(ing.verdict)}</span>
        </div>
        <div class="ingredient-reason">${esc(ing.reason)}</div>
        ${(ing.claims || [])
          .map(
            (c) => `
          <div class="claim">${esc(c.text)}
            <a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.url)}</a>
          </div>`
          )
          .join("")}
      </div>`
    )
    .join("");

  const report = $("#report");
  report.innerHTML = `
    <div class="report-card">
      <div class="report-rule">
        <span>Final safety report</span>
        <span class="report-rule-right">
          ${result.passes_used} pass${result.passes_used === 1 ? "" : "es"} · ${citations} citation${citations === 1 ? "" : "s"}
          <button type="button" id="export-pdf" class="no-print">Export PDF ↧</button>
        </span>
      </div>
      <div class="stamp ${esc(v.overall_verdict)}">${esc(v.overall_verdict)}</div>
      <h3 class="report-product">${esc(v.product_name)}</h3>
      <p class="report-reason">${esc(v.overall_reason)}</p>
      ${
        v.user_context_notes
          ? `<div class="context-note"><span class="label">User context considered</span>${esc(v.user_context_notes)}</div>`
          : ""
      }
      <div class="ingredients-title">Per-ingredient findings</div>
      ${ingredients}
      <div class="report-meta">
        <span>Audit: <b>${result.approved ? "PASSED" : "NOT PASSED — treat with extra caution"}</b></span>
        ${a ? `<span>Groundedness <b>${a.groundedness_score.toFixed(2)}</b></span>
               <span>Authority <b>${a.authority_score.toFixed(2)}</b></span>
               <span>Tone <b>${a.tone_safety_score.toFixed(2)}</b></span>` : ""}
        <span>Engine: planner → parallel research → verdict → audit</span>
      </div>
    </div>`;
  report.hidden = false;
  $("#export-pdf").addEventListener("click", () => window.print());
  report.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Wiring ───────────────────────────────────────────────────

$("#intake-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#query").value.trim();
  if (q) startRun(q);
});

$("#samples").addEventListener("click", (e) => {
  const btn = e.target.closest(".sample");
  if (!btn) return;
  $("#query").value = btn.dataset.q;
  startRun(btn.dataset.q);
});
