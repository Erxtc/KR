/* Knowledge Router UI.
 *
 * Every relation is a market, so every claim is drawn the same way: a name, a
 * probability, and what it rests on. One snapshot in, one operation out - the
 * server assembles the joins (ui/krstore.py), so this file renders and posts and
 * never decides for itself what a claim inherits.
 */

const S = {
  data: null,
  view: "markets",
  sel: null, // {kind, id}
  filter: "",
  edit: null, // {field:"name"|"definition", kind, id}
  editPrice: null, // {table, id}
  editValue: null, // value row id
};

const VIEWS = ["markets", "objects", "classes", "assumptions", "gaps"];
const VIEW_KIND = { objects: "object", classes: "class", assumptions: "assumption", markets: "market" };

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (p) => (p === null || p === undefined ? "—" : `${Math.round(p * 100)}%`);
const gapWarn = () => S.data?.gap_warn ?? 0.2;

/* ---------- server ---------- */

async function load() {
  const res = await fetch("/api/state");
  if (!res.ok) throw new Error(`state: ${res.status}`);
  S.data = await res.json();
  return S.data;
}

async function mutate(op, body = {}) {
  const res = await fetch("/api/mutate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ op, ...body }),
  });
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || `mutate: ${res.status}`);
  S.data = payload;
  S.edit = null;
  S.editPrice = null;
  S.editValue = null;
  return payload;
}

/* ---------- lookups ---------- */

const pool = (kind) =>
  kind === "class" ? S.data.classes : kind === "object" ? S.data.objects : S.data.assumptions;
const byId = (kind, id) => pool(kind).find((x) => x.id === id);
const classes = () => S.data.classes;
const objects = () => S.data.objects;
const assumptions = () => S.data.assumptions;
const claims = () => S.data.prices || [];

function edgeId(aId, bId) {
  const hit = (S.data.edges || []).find((e) => e.a_id === aId && e.b_id === bId);
  return hit ? hit.id : null;
}

/* ---------- a price, always the same shape ---------- */

function priceControl(table, id, p, opts = {}) {
  if (S.editPrice && S.editPrice.table === table && S.editPrice.id === id) {
    return `<input class="pinput" id="priceInput" data-table="${esc(table)}" data-id="${esc(id)}"
      value="${p === null || p === undefined ? "" : pct(p)}" placeholder="—" spellcheck="false" autocomplete="off" />`;
  }
  const warn = opts.warn ? " warn" : "";
  const unpriced = p === null || p === undefined ? " unpriced" : "";
  const title = opts.title || (p === null ? "unpriced — click to stake an opinion" : "click to change the price");
  return `<button class="price${unpriced}${warn}" data-act="edit-price" data-table="${esc(table)}" data-id="${esc(id)}"
    title="${esc(title)}">${pct(p)}</button>`;
}

function bar(p, warn) {
  if (p === null || p === undefined) return `<div class="bar none"><i style="width:100%"></i></div>`;
  return `<div class="bar${warn ? " warn" : ""}"><i style="width:${Math.round(p * 100)}%"></i></div>`;
}

/* ---------- chrome ---------- */

function renderChrome() {
  const d = S.data;
  const books = claims();
  const priced = books.filter((c) => c.belief !== null);
  $("#nMarkets").textContent = books.length;
  $("#nObjects").textContent = d.counts.objects;
  $("#nClasses").textContent = d.counts.classes;
  $("#nAssumptions").textContent = d.counts.assumptions;
  const warnings = d.issues.filter((i) => i.level === "warn").length;
  $("#nIssues").textContent = d.issues.length;
  $("#nIssues").classList.toggle("warn", warnings > 0);

  for (const tab of document.querySelectorAll(".tab")) {
    tab.setAttribute("aria-selected", String(tab.dataset.view === S.view));
  }

  $("#sideFoot").innerHTML =
    `${books.length} claims · ${priced.length} priced · ${books.length - priced.length} unpriced<br>` +
    `${d.counts.objects} objects · ${d.counts.classes} classes · ${d.counts.assumptions} assumptions<br>` +
    `${d.counts.values} values · ${d.counts.markets} questions<br>` +
    `<span title="${esc(d.db)}">${esc(d.db.split(/[\\/]/).pop())}</span>` +
    (d.backup ? `<br><span title="${esc(d.backup)}">undo: ${esc(d.backup.split(/[\\/]/).pop())}</span>` : "");
}

/* ---------- list ---------- */

function listRows() {
  const q = S.filter.trim().toLowerCase();
  const hit = (t) => !q || String(t || "").toLowerCase().includes(q);

  if (S.view === "gaps") {
    return S.data.issues
      .filter((i) => hit(i.title) || hit(i.detail))
      .map((i) => ({
        id: `${i.level}:${i.title}`,
        kind: i.level === "warn" ? "gap" : "note",
        name: i.title,
        meta: i.detail,
        warn: i.level === "warn",
        ref: i.ref || null,
        price: null,
      }));
  }

  if (S.view === "markets") {
    return claims()
      .filter((c) => hit(c.claim) || hit(c.object) || hit(c.subject))
      .slice()
      .sort((a, b) => (b.belief ?? -1) - (a.belief ?? -1))
      .map((c) => ({
        id: c.id,
        kind: c.kind,
        name: c.claim,
        meta:
          c.belief === null
            ? "unpriced — nobody has staked"
            : c.gap !== null && c.gap !== undefined && c.gap >= gapWarn()
            ? `${pct(c.gap)} above what it rests on`
            : `rests on ${c.weakest ? c.weakest : "itself"}`,
        warn: c.gap !== null && c.gap !== undefined && c.gap >= gapWarn(),
        ref: c.href,
        price: c.belief,
        priceWarn: c.gap !== null && c.gap !== undefined && c.gap >= gapWarn(),
      }));
  }

  if (S.view === "objects") {
    return objects()
      .filter((o) => hit(o.name) || hit(o.definition))
      .map((o) => {
        const worst = o.classes
          .filter((c) => c.belief !== null)
          .sort((a, b) => a.belief - b.belief)[0];
        return {
          id: o.id,
          kind: "object",
          name: o.name,
          meta: o.classes.length ? o.classes.map((c) => c.class_name).join(" · ") : "no class",
          warn: !o.classes.length,
          ref: { kind: "object", id: o.id },
          price: worst ? worst.belief : null,
          priceWarn: o.classes.some((c) => c.gap !== null && c.gap >= gapWarn()),
        };
      });
  }

  if (S.view === "classes") {
    return classes()
      .filter((c) => hit(c.name) || hit(c.definition))
      .map((c) => {
        const bare = !c.assumptions.length && !c.inherited.length;
        const crit = c.criterion.p === null ? (bare ? "no assumptions" : "criterion unpriced") : `criterion ${pct(c.criterion.p)}`;
        return {
          id: c.id,
          kind: "class",
          name: c.name,
          meta: `${crit} · ${c.instances.length} instance${c.instances.length === 1 ? "" : "s"}`,
          warn: bare || c.criterion.p === null,
          ref: { kind: "class", id: c.id },
          price: c.criterion.p,
          priceWarn: bare,
        };
      });
  }

  return assumptions()
    .filter((a) => hit(a.name) || hit(a.definition))
    .map((a) => {
      const worst = a.classes.filter((c) => c.belief !== null).sort((x, y) => x.belief - y.belief)[0];
      return {
        id: a.id,
        kind: "assumption",
        name: a.name,
        meta: a.classes.length
          ? `required by ${a.classes.map((c) => c.name).join(", ")}`
          : "required by nothing",
        warn: !a.classes.length,
        ref: { kind: "assumption", id: a.id },
        price: worst ? worst.belief : null,
        priceWarn: !a.classes.length,
      };
    });
}

function renderList() {
  const rows = listRows();
  $("#listTitle").textContent = S.view === "gaps" ? "what cannot be checked" : S.view;
  $("#listCount").textContent = rows.length;
  const selId = S.sel ? S.sel.id : null;

  $("#list").innerHTML = rows.length
    ? rows
        .map(
          (r) => `<button class="row${r.warn ? " warn" : ""}" role="option" data-act="pick" data-id="${esc(r.id)}"
             data-kind="${esc(r.kind)}" aria-selected="${String(r.id === selId)}" data-ref='${esc(JSON.stringify(r.ref))}'>
            <span class="t">
              <span class="nm">${esc(r.name)}</span>
              ${r.price !== undefined ? `<span class="p${r.price === null ? " unpriced" : ""}${r.priceWarn ? " warn" : ""}">${pct(r.price)}</span>` : ""}
              <span class="kind">${esc(r.kind)}</span>
            </span>
            <span class="m">${esc(r.meta)}</span>
          </button>`
        )
        .join("")
    : `<div class="empty">nothing matches “${esc(S.filter)}”</div>`;
}

/* ---------- navigation ---------- */

function select(kind, id) {
  S.sel = { kind, id };
  S.edit = null;
  S.editPrice = null;
  S.editValue = null;
  S.view = kind === "object" ? "objects" : kind === "class" ? "classes" : "assumptions";
  location.hash = `#/${S.view}/${id}`;
  render();
}

function jump(ref) {
  if (!ref) return toast("this row has nothing to open", true);
  select(ref.kind, ref.id);
}

/* ---------- detail scaffolding ---------- */

function headHTML(kind, item, extra = "") {
  const editing = S.edit && S.edit.field === "name" && S.edit.id === item.id;
  const title = editing
    ? `<input class="nameinput" id="editName" value="${esc(item.name)}" style="font-size:24px;font-weight:600;width:100%;background:var(--bg);border:1px solid var(--line-2);border-radius:8px;padding:6px 9px;outline:none" />`
    : `<h1>${esc(item.name)}</h1>`;
  const actions = editing
    ? `<button class="btn tiny primary" data-act="save-name" data-kind="${kind}" data-id="${item.id}">save</button>
       <button class="btn tiny" data-act="cancel-edit">cancel</button>`
    : `<button class="btn ghost tiny" data-act="edit-name" data-kind="${kind}" data-id="${item.id}" title="rename">rename</button>
       <button class="btn ghost tiny danger" data-act="delete" data-kind="${kind}" data-id="${item.id}" title="delete">delete</button>`;
  return `<div class="crumb">${kind}${extra}</div>
    <div class="head"><div class="grow">${title}</div><div class="head-actions">${actions}</div></div>`;
}

function definitionHTML(kind, item) {
  if (S.edit && S.edit.field === "definition" && S.edit.id === item.id) {
    return `<div class="def-edit">
      <textarea id="editDef" autofocus placeholder="what the name means">${esc(item.definition)}</textarea>
      <div style="display:grid;gap:6px;align-content:start">
        <button class="btn tiny primary" data-act="save-def" data-kind="${kind}" data-id="${item.id}">save</button>
        <button class="btn tiny" data-act="cancel-edit">cancel</button>
      </div>
    </div>`;
  }
  const def = String(item.definition || "").trim();
  return `${
    def
      ? `<div class="definition">${esc(def)}</div>`
      : `<div class="definition missing">no definition yet — a name without a definition cannot be applied the same way twice</div>`
  }
  <div><button class="btn ghost tiny" data-act="edit-def" data-kind="${kind}" data-id="${item.id}">${
    def ? "edit definition" : "add definition"
  }</button></div>`;
}

function warnPills(kind, item) {
  const out = [];
  const def = String(item.definition || "").trim();
  if (kind === "class") {
    if (!def) out.push(`<span class="pill warn">no definition</span>`);
    else if (def.toLowerCase() === item.name.toLowerCase()) out.push(`<span class="pill warn">definition restates the name</span>`);
    if (!item.assumptions.length && !item.inherited.length) out.push(`<span class="pill warn">no assumptions</span>`);
    else if (item.criterion.p === null) out.push(`<span class="pill warn">criterion unpriced</span>`);
    else out.push(`<span class="pill ok">criterion ${pct(item.criterion.p)}</span>`);
  }
  if (kind === "assumption" && !item.classes.length) out.push(`<span class="pill warn">required by nothing</span>`);
  if (kind === "object" && !item.classes.length) out.push(`<span class="pill warn">no class</span>`);
  return out.length ? `<div class="chips" style="margin-top:12px">${out.join("")}</div>` : "";
}

function selectOptions(items, placeholder) {
  return [`<option value="">${esc(placeholder)}</option>`]
    .concat(items.map((i) => `<option value="${esc(i.id)}">${esc(i.name)}</option>`))
    .join("");
}

/* ---------- object ---------- */

function membershipChip(o, c) {
  const warn = c.gap !== null && c.gap >= gapWarn();
  const sub = c.criterion === null
    ? "criterion unpriced"
    : warn
    ? `${pct(c.gap)} above its criterion (${pct(c.criterion)})`
    : `criterion ${pct(c.criterion)} · holds`;
  return `<div class="chip${warn ? " gap-warn" : ""}">
    <span class="topline">
      <button class="nm" data-act="open" data-kind="class" data-id="${esc(c.class_id)}">${esc(c.class_name)}</button>
      ${priceControl("is_", c.id, c.belief)}
      <button class="x" data-act="unlink-edge" data-id="${esc(c.id)}" title="remove">×</button>
    </span>
    ${bar(c.belief, warn)}
    <span class="sub${warn ? " warn" : ""}">${esc(sub)}</span>
  </div>`;
}

function restedChip(a) {
  const chain = (a.chain || []).map((s) => `${s.label} ${pct(s.p)}`).join("  →  ");
  return `<div class="chip">
    <span class="topline">
      <button class="nm" data-act="open" data-kind="assumption" data-id="${esc(a.id)}">${esc(a.name)}</button>
    </span>
    ${bar(a.p, false)}
    <span class="sub" title="${esc(chain)}">supported at ${pct(a.p)} · via ${esc(a.via.join(", "))}</span>
    ${a.weakest ? `<span class="sub">weakest: ${esc(a.weakest)}</span>` : ""}
  </div>`;
}

function valueRow(kind, id, name, v) {
  const isOpen = S.editValue === v.id;
  return `<div class="r">
    <button class="k" data-act="open" data-kind="${kind}" data-id="${esc(id)}">${esc(name)}</button>
    <span class="cell">
      ${
        isOpen
          ? `<input class="vinput" id="valueInput" data-id="${esc(v.id)}" type="number" step="1" value="${esc(v.value)}" />`
          : `<button class="vnum" data-act="edit-value" data-id="${esc(v.id)}" title="click to change the number">${esc(v.value)}</button>`
      }
      ${priceControl("value", v.id, v.belief, { title: "how much the number is believed" })}
    </span>
    <button class="x" data-act="clear-value" data-id="${esc(v.id)}" title="remove">×</button>
  </div>`;
}

function renderObject(o) {
  const valued = new Set(o.values.map((v) => v.class_id));
  const freeClasses = classes().filter((c) => !valued.has(c.id));
  const extra =
    o.all_classes.length > o.classes.length
      ? `<div class="note" style="margin-top:10px">by class, also: ${o.all_classes
          .filter((c) => !o.classes.some((d) => d.class_id === c.id))
          .map((c) => `<b>${esc(c.name)}</b>${c.via && c.via !== c.name ? ` (via ${esc(c.via)})` : ""}`)
          .join(", ")}</div>`
      : "";

  const restsOn = o.assumptions.length
    ? `<div class="chips">${o.assumptions.map(restedChip).join("")}</div>`
    : `<p class="note">Nothing is asserted. ${
        o.classes.length ? "Its classes carry no assumptions, so there is no test." : "It belongs to no class, so there is nothing to test."
      }</p>`;

  return `${headHTML("object", o)}
    ${definitionHTML("object", o)}
    ${warnPills("object", o)}

    <div class="sect">
      <div class="sect-head"><h2>is a</h2><span class="n">${o.classes.length}</span></div>
      ${
        o.classes.length
          ? `<div class="chips">${o.classes.map((c) => membershipChip(o, c)).join("")}</div>`
          : `<p class="note">No class, so no properties. An object without properties has nothing to observe.</p>`
      }
      ${extra}
      <div class="addline">
        <select id="addClassPick">${selectOptions(
          classes().filter((c) => !o.classes.some((d) => d.class_id === c.id)),
          "add a class…"
        )}</select>
        <input class="pricetext" id="addClassPrice" placeholder="price…" spellcheck="false" />
        <button class="btn tiny" data-act="add-class" data-object="${esc(o.id)}">add</button>
        <span class="hint">a class with no price is a claim nobody has staked on</span>
      </div>
    </div>

    <div class="sect">
      <div class="sect-head"><h2>values</h2><span class="n">${o.values.length}</span></div>
      ${
        o.values.length
          ? `<div class="kv">${o.values.map((v) => valueRow("class", v.class_id, v.class_name, v)).join("")}</div>`
          : `<p class="note">No parametric value. A class with a number is a property, so <b>${esc(o.name)}</b> has none yet.</p>`
      }
      <div class="addline">
        <select id="addValueClass">${selectOptions(freeClasses, freeClasses.length ? "which class…" : "every class already has a value")}</select>
        <input id="addValueNum" type="number" step="1" placeholder="number" />
        <input class="pricetext" id="addValuePrice" placeholder="price…" spellcheck="false" />
        <button class="btn tiny" data-act="add-value" data-object="${esc(o.id)}">set</button>
      </div>
    </div>

    <div class="sect">
      <div class="sect-head"><h2>rests on</h2><span class="n">${o.assumptions.length}</span></div>
      ${restsOn}
    </div>`;
}

/* ---------- class ---------- */

function requirementChip(c, a) {
  const def = String(a.definition || "").trim();
  const sub = def && def.toLowerCase() !== a.name.trim().toLowerCase() ? `<span class="sub">${esc(def.slice(0, 70))}</span>` : "";
  return `<div class="chip">
    <span class="topline">
      <button class="nm" data-act="open" data-kind="assumption" data-id="${esc(a.id)}">${esc(a.name)}</button>
      ${priceControl("assumptionmatching", a.matching_id, a.belief, { title: "how true is “being this class requires this”" })}
      <button class="x" data-act="unlink-assumption" data-id="${esc(a.matching_id)}" title="remove">×</button>
    </span>
    ${bar(a.belief, false)}
    ${sub}
  </div>`;
}

function linkChip(kind, item, edgeTable, edgeRow, extraSub) {
  return `<div class="chip">
    <span class="topline">
      <button class="nm" data-act="open" data-kind="${kind}" data-id="${esc(item.id)}">${esc(item.name)}</button>
      ${priceControl("is_", edgeRow, item.belief)}
      <button class="x" data-act="unlink-edge" data-id="${esc(edgeRow)}" title="remove">×</button>
    </span>
    ${bar(item.belief, false)}
    <span class="sub">${esc(extraSub)}</span>
  </div>`;
}

function renderClass(c) {
  const others = classes().filter((x) => x.id !== c.id && !c.superclasses.some((s) => s.id === x.id));
  const freeAssumptions = assumptions().filter((a) => !c.assumptions.some((x) => x.id === a.id));
  const freeObjects = objects().filter((o) => !c.instances.some((x) => x.id === o.id));

  const criterion = c.criterion;
  const critLine =
    criterion.of === 0
      ? `Nothing has to be true for something to be a <b>${esc(c.name)}</b>, so the class cannot be checked.`
      : criterion.p === null
      ? `${criterion.of} requirement${criterion.of === 1 ? "" : "s"}, none of them priced. The class is a definition with no market yet.`
      : `The class applies at <b>${pct(criterion.p)}</b> — its weakest requirement${
          criterion.weakest ? `, “${esc(criterion.weakest)}”` : ""
        }. ${criterion.priced} of ${criterion.of} priced.`;

  const instances = c.instances.length
    ? `<div class="chips">${c.instances
        .map((i) => {
          const warn = i.gap !== null && i.gap >= gapWarn();
          return `<div class="chip${warn ? " gap-warn" : ""}">
            <span class="topline">
              <button class="nm" data-act="open" data-kind="object" data-id="${esc(i.id)}">${esc(i.name)}</button>
              ${priceControl("is_", i.edge_id, i.belief)}
              <button class="x" data-act="unlink-edge" data-id="${esc(i.edge_id)}" title="remove">×</button>
            </span>
            ${bar(i.belief, warn)}
            <span class="sub${warn ? " warn" : ""}">${
              warn ? `${pct(i.gap)} above what the class asks` : i.belief === null ? "unpriced" : "within its criterion"
            }</span>
          </div>`;
        })
        .join("")}</div>`
    : `<p class="note">Nothing is a <b>${esc(c.name)}</b>. The class states a test nobody is filed under.</p>`;

  const relations =
    c.superclasses.length || c.subclasses.length
      ? `<div class="chips">
          ${c.superclasses.map((s) => linkChip("class", s, "is_", s.edge_id, "is a (inherits its assumptions)")).join("")}
          ${c.subclasses
            .map((s) => linkChip("class", s, "is_", s.edge_id, `is a ${c.name}`))
            .join("")}
        </div>`
      : `<p class="note">No sub-classes. A class of a class is how one criterion gets reused.</p>`;

  return `${headHTML("class", c)}
    ${definitionHTML("class", c)}
    ${warnPills("class", c)}

    <div class="sect">
      <div class="sect-head"><h2>criterion</h2><span class="n">${c.assumptions.length}</span><span class="spacer"></span>
        <span class="n">${criterion.p === null ? "unpriced" : `applies at ${pct(criterion.p)}`}</span>
      </div>
      <p class="note">${critLine}</p>
      ${
        c.assumptions.length
          ? `<div class="chips" style="margin-top:10px">${c.assumptions.map((a) => requirementChip(c, a)).join("")}</div>`
          : ""
      }
      ${
        c.inherited.length
          ? `<div class="chips" style="margin-top:10px">${c.inherited
              .map(
                (a) => `<div class="chip"><span class="topline">
                  <button class="nm" data-act="open" data-kind="assumption" data-id="${esc(a.id)}">${esc(a.name)}</button>
                  <span class="price${a.belief === null ? " unpriced" : ""}">${pct(a.belief)}</span>
                </span><span class="sub">inherited from ${esc(a.from)}</span></div>`
              )
              .join("")}</div>`
          : ""
      }
      <div class="addline">
        <select id="addAssumePick">${selectOptions(freeAssumptions, "add an assumption…")}</select>
        <input class="pricetext" id="addAssumePrice" placeholder="price…" spellcheck="false" />
        <button class="btn tiny" data-act="add-assumption" data-class="${esc(c.id)}">add</button>
        <button class="btn ghost tiny" data-act="new-for-class" data-id="${esc(c.id)}">new assumption</button>
      </div>
    </div>

    <div class="sect">
      <div class="sect-head"><h2>instances</h2><span class="n">${c.instances.length}</span></div>
      ${instances}
      <div class="addline">
        <select id="addInstPick">${selectOptions(freeObjects, "file an object under it…")}</select>
        <input class="pricetext" id="addInstPrice" placeholder="price…" spellcheck="false" />
        <button class="btn tiny" data-act="add-instance" data-class="${esc(c.id)}">add</button>
      </div>
    </div>

    <div class="sect">
      <div class="sect-head"><h2>classes of classes</h2><span class="n">${c.superclasses.length + c.subclasses.length}</span></div>
      ${relations}
      <div class="addline">
        <select id="addSuperPick">${selectOptions(others, "make it a sub-class of…")}</select>
        <input class="pricetext" id="addSuperPrice" placeholder="price…" spellcheck="false" />
        <button class="btn tiny" data-act="add-super" data-class="${esc(c.id)}">add</button>
      </div>
    </div>

    <div class="sect">
      <div class="sect-head"><h2>values</h2><span class="n">${c.values.length}</span></div>
      ${
        c.values.length
          ? `<div class="kv">${c.values.map((v) => valueRow("object", v.object_id, v.object_name, v)).join("")}</div>`
          : `<p class="note">No object has a number for this class yet.</p>`
      }
    </div>`;
}

/* ---------- assumption ---------- */

function renderAssumption(a) {
  const holders = a.classes.length
    ? `<div class="chips">${a.classes
        .map(
          (c) => `<div class="chip"><span class="topline">
            <button class="nm" data-act="open" data-kind="class" data-id="${esc(c.id)}">${esc(c.name)}</button>
            ${priceControl("assumptionmatching", c.matching_id, c.belief)}
            <button class="x" data-act="unlink-assumption" data-id="${esc(c.matching_id)}" title="remove">×</button>
          </span>${bar(c.belief, false)}<span class="sub">requires it</span></div>`
        )
        .join("")}</div>`
    : `<p class="note">No class lists it, so no claim rests on it.</p>`;

  const touched = a.objects.length
    ? `<div class="chips">${a.objects
        .map(
          (o) => `<div class="chip plain"><span class="topline">
          <button class="nm" data-act="open" data-kind="object" data-id="${esc(o.id)}">${esc(o.name)}</button>
        </span><span class="sub">via ${esc(o.via.join(", "))}</span></div>`
        )
        .join("")}</div>`
    : `<p class="note">No object inherits it, because nothing is filed under the classes above.</p>`;

  return `${headHTML("assumption", a)}
    ${definitionHTML("assumption", a)}
    ${warnPills("assumption", a)}

    <div class="sect">
      <div class="sect-head"><h2>required by</h2><span class="n">${a.classes.length}</span></div>
      ${holders}
    </div>

    <div class="sect">
      <div class="sect-head"><h2>asserted of</h2><span class="n">${a.objects.length}</span></div>
      ${touched}
    </div>`;
}

/* ---------- the book ---------- */

function renderMarkets() {
  const books = claims();
  const priced = books.filter((c) => c.belief !== null).sort((a, b) => b.belief - a.belief);
  const unpriced = books.filter((c) => c.belief === null);
  const buckets = [0, 0.2, 0.4, 0.6, 0.8, 1.0001];
  const counts = buckets.slice(0, -1).map((low, i) => priced.filter((c) => c.belief >= low && c.belief < buckets[i + 1]).length);
  const gaps = books
    .filter((c) => c.gap !== null && c.gap >= gapWarn())
    .sort((a, b) => b.gap - a.gap);

  const dist = counts
    .map((n, i) => {
      const width = priced.length ? Math.round((n / priced.length) * 100) : 0;
      return `<div class="board"><div class="b" style="cursor:default;grid-template-columns:60px 1fr 40px">
        <span class="num muted">${Math.round(buckets[i] * 100)}–${Math.round(buckets[i + 1] * 100)}%</span>
        <span><span class="bar"><i style="width:${width}%"></i></span></span>
        <span class="num">${n}</span>
      </div></div>`;
    })
    .join("");

  const boardRow = (c) => {
    /* A gap is belief the claim does not pay for, so only a positive one is news:
       a claim below its own criterion is just consistent. */
    const above = c.gap !== null && c.gap !== undefined && c.gap > 0;
    return `<div class="b" data-act="jump" data-ref='${esc(JSON.stringify(c.href))}'>
      <span class="cl">${esc(c.claim)}</span>
      <span class="num${c.belief === null ? " unpriced" : ""}">${pct(c.belief)}</span>
      <span class="num muted">${pct(c.support)}</span>
      <span class="num${above && c.gap >= gapWarn() ? " warn" : " muted"}">${above ? `+${pct(c.gap)}` : "—"}</span>
    </div>`;
  };

  const head = `<div class="h"><span>claim</span><span class="num">price</span><span class="num">rests on</span><span class="num">gap</span></div>`;

  const questions = S.data.markets.length
    ? `<div class="kv">${S.data.markets
        .map(
          (m) => `<div class="r" style="grid-template-columns:minmax(0,1fr) auto auto">
        <span class="k" style="cursor:default">${esc(m.question || "(no question)")}${
            m.binds ? `<span class="sub" style="color:var(--faint)"> · binds ${esc(m.binds)}</span>` : ""
          }</span>
        <span class="cell">${priceControl("market", m.id, m.belief)}</span>
        <button class="x" data-act="delete-market" data-id="${esc(m.id)}" title="remove">×</button>
      </div>`
        )
        .join("")}</div>`
    : `<p class="note">No question markets yet. Everything above is a price on a row; a question market is for a
       claim the tables do not have a column for.</p>`;

  const median = priced.length ? priced[Math.floor(priced.length / 2)].belief : null;

  return `<div class="crumb">markets</div>
    <div class="head"><div class="grow"><h1>The book</h1></div>
      <div class="head-actions">
        <button class="btn tiny" data-act="new" data-kind="market">＋ question</button>
      </div>
    </div>
    <div class="definition">Every relation is a market: <b>${esc("NS is country")}</b> is not a fact but a price, and so is
      <b>${esc("being a scammer requires deliberately deceiving people")}</b>. ${books.length} claims, ${
    priced.length
  } of them traded. A claim cannot be worth more than what it rests on, so the gap column is the belief it does not pay
      for.</div>

    <div class="sect">
      <div class="sect-head"><h2>the board</h2><span class="n">${priced.length} priced</span>
        <span class="spacer"></span><span class="n">median ${pct(median)}</span></div>
      ${
        priced.length
          ? `<div class="board">${head}${priced.slice(0, 40).map(boardRow).join("")}</div>
             ${priced.length > 40 ? `<p class="note">showing the top 40 of ${priced.length}.</p>` : ""}`
          : `<p class="note">Nothing has a price yet. Open an object and give one of its classes a number.</p>`
      }
    </div>

    ${
      gaps.length
        ? `<div class="sect">
        <div class="sect-head"><h2>claiming more than it rests on</h2><span class="n">${gaps.length}</span></div>
        <div class="board">${head}${gaps.slice(0, 12).map(boardRow).join("")}</div>
      </div>`
        : ""
    }

    <div class="sect">
      <div class="sect-head"><h2>distribution</h2><span class="n">${priced.length} priced claims</span></div>
      <div style="display:grid;gap:6px">${dist}</div>
    </div>

    <div class="sect">
      <div class="sect-head"><h2>unpriced</h2><span class="n">${unpriced.length}</span></div>
      ${
        unpriced.length
          ? `<div class="board">${head}${unpriced.slice(0, 20).map(boardRow).join("")}</div>`
          : `<p class="note">Every claim has a price. That is unusual and worth questioning.</p>`
      }
    </div>

    <div class="sect">
      <div class="sect-head"><h2>questions</h2><span class="n">${S.data.markets.length}</span></div>
      ${questions}
      <div class="addline">
        <input id="mktQuestion" placeholder="a question worth pricing…" style="flex:1;min-width:240px" spellcheck="false" />
        <input id="mktBinds" placeholder="binds to… (optional)" spellcheck="false" />
        <input class="pricetext" id="mktPrice" placeholder="price…" spellcheck="false" />
        <button class="btn tiny" data-act="add-market">add</button>
      </div>
    </div>`;
}

/* ---------- gaps ---------- */

function renderGaps() {
  const groups = [
    ["warn", "gaps"],
    ["note", "notes"],
  ];
  const body = groups
    .map(([level, label]) => {
      const items = S.data.issues.filter((i) => i.level === level);
      if (!items.length) return "";
      return `<div class="sect">
        <div class="sect-head"><h2>${label}</h2><span class="n">${items.length}</span></div>
        ${items
          .map(
            (i) => `<div class="issue ${level}" data-act="jump" data-ref='${esc(JSON.stringify(i.ref || null))}'>
            <span class="ttl">${esc(i.title)}</span>
            <span class="det">${esc(i.detail)}</span>
          </div>`
          )
          .join("")}
      </div>`;
    })
    .join("");

  const warn = S.data.issues.filter((i) => i.level === "warn").length;
  return `<div class="crumb">gaps</div>
    <div class="head"><div class="grow"><h1>What cannot be checked yet</h1></div></div>
    <div class="definition">A class is a definition plus the assumptions that must hold, priced by its weakest. Where a
      price is missing, or a claim sits above what it rests on, the belief is not paid for — so those places are
      computed here rather than trusted to be absent.</div>
    ${body || `<div class="empty">nothing to flag</div>`}
    <p class="note" style="margin-top:20px">${warn} gap${warn === 1 ? "" : "s"}, ${S.data.issues.length - warn} note${
      S.data.issues.length - warn === 1 ? "" : "s"
    }.</p>`;
}

/* ---------- render ---------- */

function render() {
  renderChrome();
  renderList();

  let html;
  if (S.view === "markets") {
    html = renderMarkets();
  } else if (S.view === "gaps") {
    html = renderGaps();
  } else if (S.sel) {
    const item = byId(S.sel.kind, S.sel.id);
    if (!item) html = `<div class="empty">that row is gone.</div>`;
    else if (S.sel.kind === "object") html = renderObject(item);
    else if (S.sel.kind === "class") html = renderClass(item);
    else html = renderAssumption(item);
  } else {
    html = emptyView();
  }
  $("#detail").innerHTML = html;

  const nameInput = $("#editName");
  if (nameInput) {
    nameInput.focus();
    nameInput.select();
  }
  const defInput = $("#editDef");
  if (defInput) {
    defInput.focus();
    defInput.setSelectionRange(defInput.value.length, defInput.value.length);
  }
  const priceInput = $("#priceInput");
  if (priceInput) {
    priceInput.focus();
    priceInput.select();
  }
  const valueInput = $("#valueInput");
  if (valueInput) {
    valueInput.focus();
    valueInput.select();
  }
}

function emptyView() {
  const rows = listRows();
  if (rows.length) {
    return `<div class="crumb">${S.view}</div>
      <div class="head"><div class="grow"><h1>${esc(rows[0].name)}</h1></div></div>
      <p class="note">Pick something on the left. <span class="dim">j / k moves, / filters.</span></p>`;
  }
  return `<div class="crumb">${S.view}</div>
    <div class="head"><div class="grow"><h1>Nothing here yet</h1></div></div>
    <p class="note">The database is empty at this view.
      <button class="btn tiny" data-act="new" data-kind="${esc(VIEW_KIND[S.view] || "object")}">create the first one</button>
    </p>`;
}

/* ---------- dialog ---------- */

const DIALOG = {
  object: {
    note: "An object is a thing: NS, Sweden, FC Barcelona. It means what its definition says.",
    name: "name",
    def: "definition",
  },
  class: {
    note: "A class is a property something can have: country, gdp, scammer. Its assumptions are the test, and each is priced.",
    name: "name",
    def: "definition",
  },
  assumption: {
    note: "An assumption is a sentence a class requires: deliberately deceives people.",
    name: "name",
    def: "definition",
  },
  market: {
    note: "A question market: a claim the tables have no column for, priced on its own.",
    name: "question",
    def: "",
  },
};

function openDialog(kind, returnTo = "") {
  const k = DIALOG[kind] ? kind : "object";
  const spec = DIALOG[k];
  $("#newKind").textContent = k;
  $("#newNameLabel").textContent = spec.name;
  $("#newDefLabel").textContent = spec.def || "notes";
  $("#newName").value = "";
  $("#newDef").value = "";
  $("#newBinds").value = "";
  $("#newPrice").value = "";
  $("#newDef").parentElement.hidden = !spec.def;
  $("#newBindsField").hidden = k !== "market";
  // a price belongs to a market, or to the link that "new assumption" will make
  $("#newPrice").parentElement.hidden = !(k === "market" || returnTo);
  $("#newNote").textContent = spec.note;
  $("#newForm").dataset.kind = k;
  $("#newForm").dataset.returnTo = returnTo;
  $("#newDialog").showModal();
  $("#newName").focus();
}

async function createFromDialog() {
  const form = $("#newForm");
  const kind = form.dataset.kind || "object";
  const returnTo = form.dataset.returnTo || "";
  const name = $("#newName").value.trim();
  const definition = $("#newDef").value.trim();
  const price = $("#newPrice").value.trim();
  if (!name) return;
  form.dataset.returnTo = "";

  let payload;
  if (kind === "market") {
    payload = await mutate("market.create", { question: name, binds: $("#newBinds").value.trim(), belief: price });
    $("#newDialog").close();
    toast("question added");
    return render();
  }

  payload = await mutate(`${kind}.create`, { name, definition });
  const made = payload[kind === "class" ? "classes" : kind + "s"].find((x) => x.name.toLowerCase() === name.toLowerCase());

  if (made && kind === "assumption" && returnTo) {
    await mutate("assumption.link", { class_id: returnTo, assumption_id: made.id, belief: price });
    $("#newDialog").close();
    select("class", returnTo);
    toast("assumption created and attached");
    return;
  }
  $("#newDialog").close();
  if (made) select(kind, made.id);
  toast(`${kind} created`);
}

/* ---------- toast ---------- */

function toast(message, bad = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("bad", bad);
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), bad ? 4600 : 1900);
}

/* ---------- actions ---------- */

const actions = {
  pick: (el) => {
    if (S.view === "markets") return jump(el.dataset.ref ? JSON.parse(el.dataset.ref) : null);
    if (S.view === "gaps") return jump(el.dataset.ref ? JSON.parse(el.dataset.ref) : null);
    select(el.dataset.kind, el.dataset.id);
  },
  jump: (el) => jump(el.dataset.ref ? JSON.parse(el.dataset.ref) : null),
  open: (el) => select(el.dataset.kind, el.dataset.id),
  new: (el) => openDialog(el.dataset.kind || VIEW_KIND[S.view]),
  "new-for-class": (el) => openDialog("assumption", el.dataset.id),

  "edit-name": (el) => {
    S.edit = { field: "name", kind: el.dataset.kind, id: el.dataset.id };
    render();
  },
  "save-name": async (el) => {
    const kind = el.dataset.kind;
    const item = byId(kind, el.dataset.id);
    const name = $("#editName").value.trim();
    if (!name) throw new Error("a name is required");
    await mutate(`${kind}.update`, { id: item.id, name, definition: item.definition });
    render();
    toast("renamed");
  },
  "cancel-edit": () => {
    S.edit = null;
    render();
  },
  "edit-def": (el) => {
    S.edit = { field: "definition", kind: el.dataset.kind, id: el.dataset.id };
    render();
  },
  "save-def": async (el) => {
    const kind = el.dataset.kind;
    const item = byId(kind, el.dataset.id);
    await mutate(`${kind}.update`, { id: item.id, name: item.name, definition: $("#editDef").value.trim() });
    render();
    toast("definition saved");
  },
  delete: async (el) => {
    const kind = el.dataset.kind;
    const item = byId(kind, el.dataset.id);
    const warn = kind === "class" ? " (its edges, requirements and values go too)" : "";
    if (!confirm(`delete ${kind} “${item.name}”${warn}?`)) return;
    await mutate(`${kind}.delete`, { id: item.id });
    S.sel = null;
    location.hash = `#/${S.view}`;
    render();
    toast(`${kind} deleted`);
  },

  // prices
  "edit-price": (el) => {
    S.editPrice = { table: el.dataset.table, id: el.dataset.id };
    render();
  },

  // object <-> class
  "add-class": async (el) => {
    const bId = $("#addClassPick").value;
    if (!bId) return toast("pick a class first", true);
    await mutate("is.add", {
      a_id: el.dataset.object,
      a_kind: "object",
      b_id: bId,
      belief: $("#addClassPrice").value.trim(),
    });
    render();
  },
  "unlink-edge": async (el) => {
    await mutate("is.remove", { id: el.dataset.id });
    render();
  },
  "add-instance": async (el) => {
    const aId = $("#addInstPick").value;
    if (!aId) return toast("pick an object first", true);
    await mutate("is.add", { a_id: aId, a_kind: "object", b_id: el.dataset.class, belief: $("#addInstPrice").value.trim() });
    render();
  },
  "add-super": async (el) => {
    const bId = $("#addSuperPick").value;
    if (!bId) return toast("pick a class first", true);
    await mutate("is.add", { a_id: el.dataset.class, a_kind: "class", b_id: bId, belief: $("#addSuperPrice").value.trim() });
    render();
  },

  // classes <-> assumptions
  "add-assumption": async (el) => {
    const aId = $("#addAssumePick").value;
    if (!aId) return toast("pick an assumption first", true);
    await mutate("assumption.link", {
      class_id: el.dataset.class,
      assumption_id: aId,
      belief: $("#addAssumePrice").value.trim(),
    });
    render();
  },
  "unlink-assumption": async (el) => {
    await mutate("assumption.unlink", { id: el.dataset.id });
    render();
  },

  // values
  "add-value": async (el) => {
    const classId = $("#addValueClass").value;
    const raw = $("#addValueNum").value;
    if (!classId) return toast("pick a class first", true);
    if (raw === "") return toast("a number is required", true);
    await mutate("value.set", {
      class_id: classId,
      object_id: el.dataset.object,
      value: Number(raw),
      belief: $("#addValuePrice").value.trim(),
    });
    render();
    toast("value set");
  },
  "edit-value": (el) => {
    S.editValue = el.dataset.id;
    render();
  },
  "clear-value": async (el) => {
    await mutate("value.clear", { id: el.dataset.id });
    render();
  },

  // questions
  "add-market": async () => {
    const question = $("#mktQuestion").value.trim();
    if (!question) return toast("a question is required", true);
    await mutate("market.create", {
      question,
      binds: $("#mktBinds").value.trim(),
      belief: $("#mktPrice").value.trim(),
    });
    render();
    toast("question added");
  },
  "delete-market": async (el) => {
    await mutate("market.delete", { id: el.dataset.id });
    render();
  },
};

function findValue(id) {
  for (const o of objects()) for (const v of o.values) if (v.id === id) return v;
  for (const c of classes()) for (const v of c.values) if (v.id === id) return v;
  return null;
}

async function savePrice(table, id, raw) {
  if (!S.editPrice || S.editPrice.id !== id) return;
  S.editPrice = null;
  await mutate("claim.price", { table, id, belief: raw.trim() });
  render();
}

async function saveValue(id, raw) {
  if (S.editValue !== id) return; // already committed or cancelled
  S.editValue = null;
  const row = findValue(id);
  if (!row) return render();
  if (raw === "") return render();
  const number = Number(raw);
  if (!Number.isFinite(number)) {
    toast("a value is a number", true);
    return render();
  }
  if (Math.trunc(number) === row.value) return render();
  await mutate("value.set", { class_id: row.class_id, object_id: row.object_id, value: Math.trunc(number) });
  render();
}

/* ---------- wiring ---------- */

document.addEventListener("click", async (ev) => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const fn = actions[el.dataset.act];
  if (!fn) return;
  ev.preventDefault();
  try {
    await fn(el);
  } catch (err) {
    toast(String(err.message || err), true);
  }
});

document.addEventListener("click", (ev) => {
  const tab = ev.target.closest(".tab");
  if (!tab) return;
  S.view = tab.dataset.view;
  S.sel = null;
  location.hash = `#/${S.view}`;
  render();
});

$("#newBtn").addEventListener("click", () => openDialog(VIEW_KIND[S.view] || "object"));
$("#newForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  createFromDialog().catch((err) => toast(String(err.message || err), true));
});

$("#q").addEventListener("input", (ev) => {
  S.filter = ev.target.value;
  renderList();
});

/* enter commits, esc cancels, focus loss commits - for both inline editors */
document.addEventListener("keydown", (ev) => {
  const el = document.activeElement;
  if (el?.id === "priceInput") {
    if (ev.key === "Enter") {
      ev.preventDefault();
      savePrice(el.dataset.table, el.dataset.id, el.value).catch((e) => toast(e.message, true));
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      S.editPrice = null;
      render();
    }
    return;
  }
  if (el?.id === "valueInput") {
    if (ev.key === "Enter") {
      ev.preventDefault();
      saveValue(el.dataset.id, el.value).catch((e) => toast(e.message, true));
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      S.editValue = null;
      render();
    }
    return;
  }
  if (el?.id === "editName" && ev.key === "Enter") {
    ev.preventDefault();
    actions["save-name"]({ dataset: { kind: S.edit.kind, id: S.edit.id } }).catch((e) => toast(e.message, true));
    return;
  }
  if (el?.id === "editDef" && ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) {
    ev.preventDefault();
    actions["save-def"]({ dataset: { kind: S.edit.kind, id: S.edit.id } }).catch((e) => toast(e.message, true));
    return;
  }
});

document.addEventListener(
  "focusout",
  (ev) => {
    const el = ev.target;
    if (el?.id === "priceInput") savePrice(el.dataset.table, el.dataset.id, el.value).catch((e) => toast(e.message, true));
    else if (el?.id === "valueInput") saveValue(el.dataset.id, el.value).catch((e) => toast(e.message, true));
  },
  true
);

document.addEventListener("keydown", (ev) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
  if (ev.key === "/" && !typing) {
    ev.preventDefault();
    $("#q").focus();
    return;
  }
  if (ev.key === "Escape") {
    if (typing) document.activeElement.blur();
    if (S.filter) {
      S.filter = "";
      $("#q").value = "";
      renderList();
    }
    if (S.edit) actions["cancel-edit"]();
    return;
  }
  if (typing) return;

  const rows = listRows();
  if (["j", "k", "ArrowDown", "ArrowUp"].includes(ev.key) && rows.length) {
    ev.preventDefault();
    const down = ev.key === "j" || ev.key === "ArrowDown";
    const at = rows.findIndex((r) => S.sel && r.id === S.sel.id);
    const next = at === -1 ? 0 : Math.min(rows.length - 1, Math.max(0, at + (down ? 1 : -1)));
    if (S.view === "markets" || S.view === "gaps") jump(rows[next].ref);
    else select(rows[next].kind, rows[next].id);
  }
});

window.addEventListener("hashchange", () => {
  route();
  render();
});

function route() {
  const bits = location.hash.replace(/^#\/?/, "").split("/");
  if (VIEWS.includes(bits[0])) S.view = bits[0];
  if (bits[1] && S.view !== "markets" && S.view !== "gaps") {
    S.sel = { kind: VIEW_KIND[S.view], id: bits[1] };
  } else {
    S.sel = null;
  }
}

load()
  .then(() => {
    route();
    render();
  })
  .catch((err) => {
    $("#detail").innerHTML = `<div class="empty">cannot read the database<br><span class="dim">${esc(err.message)}</span></div>`;
  });
