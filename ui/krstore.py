"""The ``kr.sqlite`` schema, read and written with the standard library.

The project's models live in ``db/schema.py`` (sqlmodel). This module speaks the
same tables in plain SQL, on purpose: the UI can be pointed at a copy of the
database with nothing installed - no sqlmodel, no dotenv, no ``.env``.

The idea the shape comes from: **every relation is a market**. ``NS is country``
is not a fact, it is a claim with a price, and so is ``being a scammer requires
deliberately deceiving people`` and so is ``NS.gdp = 1234``. Every row that can be
believed therefore carries ``belief`` - a probability in [0, 1], or NULL when
nobody has traded it yet. NULL is not 0.5: unpriced and half-believed are
different states and the UI shows them differently.

From those prices one number is derived, per claim:

    support = min(price of the claim, price of everything it rests on)

``NS is a scammer`` at 0.9 rests on ``being a scammer requires deliberately
deceiving people`` at 0.2, so it is supported at 0.2 and the gap (0.7) is the
amount of belief the claim does not pay for. That gap is what makes the next
failure findable instead of surprising.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "kr.sqlite"

TABLES = ("object", "class", "assumption", "is_", "assumptionmatching", "value", "market")

#: how much belief a claim may have above what it rests on before it is a gap
GAP_WARN = 0.20


class StoreError(Exception):
    """A mutation the database would accept but that would mean nothing."""


def new_id() -> str:
    """The same 32-hex uuid7 the models hand out, so ids stay one shape."""
    return uuid.uuid7().hex


def connect(path: Path | str = SCHEMA) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean(text: str | None) -> str:
    return (text or "").strip()


def price_of(value) -> float | None:
    """A stored belief as a probability, or None when the row has no price."""
    if value is None:
        return None
    try:
        p = float(value)
    except (TypeError, ValueError):
        return None
    if p < 0.0 or p > 1.0:
        return None
    return p


def _lowest(pairs: list[tuple[str, float]]) -> tuple[float, str] | None:
    priced = [(label, p) for label, p in pairs if p is not None]
    if not priced:
        return None
    label, p = min(priced, key=lambda pair: pair[1])
    return p, label


# -- reading ---------------------------------------------------------------
def _closure(edges: dict[str, set[str]], roots: list[str]) -> tuple[dict[str, str], set[str]]:
    """Everything reachable from ``roots`` and, for each hit, the root it came by."""
    came_by: dict[str, str] = {}
    seen: set[str] = set()
    queue = [(root, root) for root in roots]
    for node, root in queue:
        if node in seen:
            continue
        seen.add(node)
        came_by[node] = root
        for nxt in sorted(edges.get(node, ())):
            if nxt not in seen:
                queue.append((nxt, root))
    return came_by, seen


def state(path: Path | str = SCHEMA) -> dict:
    """Everything in the database, priced and joined the way the pages need it."""
    path = Path(path)
    con = connect(path)
    try:
        objects = [dict(r) for r in con.execute('select * from "object"')]
        classes = [dict(r) for r in con.execute('select * from "class"')]
        assumptions = [dict(r) for r in con.execute('select * from "assumption"')]
        is_ = [dict(r) for r in con.execute('select * from "is_"')]
        matching = [dict(r) for r in con.execute('select * from "assumptionmatching"')]
        values = [dict(r) for r in con.execute('select * from "value"')]
        markets = [dict(r) for r in con.execute('select * from "market"')]
    finally:
        con.close()

    obj_by = {o["id"]: o for o in objects}
    cls_by = {c["id"]: c for c in classes}
    asm_by = {a["id"]: a for a in assumptions}

    # object -> [(class, edge)]
    obj_classes: dict[str, list[dict]] = {}
    class_edges: dict[str, set[str]] = {}
    class_edge_rows: dict[tuple[str, str], dict] = {}
    for edge in is_:
        a, b = edge["a_id"], edge["b_id"]
        if edge["a_kind"] == "object":
            obj_classes.setdefault(a, []).append(edge)
        else:
            class_edges.setdefault(a, set()).add(b)
            class_edge_rows[(a, b)] = edge

    # class -> [(assumption, matching)]
    class_assumptions: dict[str, list[dict]] = {}
    for m in matching:
        class_assumptions.setdefault(m["class_id"], []).append(m)

    value_at: dict[tuple[str, str], dict] = {}
    for v in values:
        value_at[(v["class_id"], v["object_id"])] = v

    def assumption_brief(aid: str) -> dict:
        a = asm_by.get(aid, {"id": aid, "name": "(missing assumption)", "definition": ""})
        return {"id": aid, "name": a["name"], "definition": a["definition"]}

    def criterion(cid: str) -> dict:
        """How strongly the class applies: its own weakest requirement."""
        rows = [
            (assumption_brief(m["assumption_id"])["name"], price_of(m["belief"]))
            for m in class_assumptions.get(cid, [])
        ]
        low = _lowest(rows)
        total = len(rows)
        priced = sum(1 for _, p in rows if p is not None)
        return {
            "p": low[0] if low else None,
            "weakest": low[1] if low else None,
            "priced": priced,
            "of": total,
        }

    def support(*parts: float | None) -> float | None:
        known = [p for p in parts if p is not None]
        return min(known) if known else None

    # -- objects
    out_objects = []
    for o in objects:
        direct = [e for e in obj_classes.get(o["id"], []) if e["b_id"] in cls_by]
        direct_ids = [e["b_id"] for e in direct]
        came_by, reachable = _closure(class_edges, direct_ids)

        inherited: dict[str, dict] = {}
        for cid in reachable:
            for m in class_assumptions.get(cid, []):
                aid = m["assumption_id"]
                entry = inherited.setdefault(aid, {**assumption_brief(aid), "classes": [], "via": [], "chain": []})
                cname = cls_by[cid]["name"]
                if cname not in entry["classes"]:
                    entry["classes"].append(cname)
                root = came_by.get(cid, cid)
                via = cls_by.get(root, {}).get("name")
                if via and via not in entry["via"]:
                    entry["via"].append(via)
                edge = next((e for e in direct if e["b_id"] == root), None)
                # the steps the claim rests on, weakest first is computed below
                steps = [
                    {"label": f"{o['name']} is {cls_by[root]['name']}", "p": price_of(edge["belief"]) if edge else None,
                     "table": "is_", "id": edge["id"] if edge else None},
                    {"label": f"{cname} requires {assumption_brief(aid)['name']}", "p": price_of(m["belief"]),
                     "table": "assumptionmatching", "id": m["id"]},
                ]
                if cname != cls_by.get(root, {}).get("name"):
                    steps.insert(1, {
                        "label": f"{cls_by.get(root, {}).get('name')} is {cname}",
                        "p": price_of(class_edge_rows.get((root, cid), {}).get("belief")),
                        "table": "is_",
                        "id": class_edge_rows.get((root, cid), {}).get("id"),
                    })
                entry["chain"] = steps
                entry["p"] = support(*[step["p"] for step in steps])
                lowest = _lowest([(step["label"], step["p"]) for step in steps])
                entry["weakest"] = lowest[1] if lowest else None

        edges = []
        for e in direct:
            cid = e["b_id"]
            crit = criterion(cid)
            p = price_of(e["belief"])
            edges.append(
                {
                    "id": e["id"],
                    "class_id": cid,
                    "class_name": cls_by[cid]["name"],
                    "belief": p,
                    "criterion": crit["p"],
                    "weakest": crit["weakest"],
                    "support": support(p, crit["p"]),
                    "gap": (p - crit["p"]) if (p is not None and crit["p"] is not None) else None,
                }
            )

        out_objects.append(
            {
                **{k: o[k] for k in ("id", "name", "definition")},
                "classes": edges,
                "all_classes": [
                    {
                        "id": cid,
                        "name": cls_by[cid]["name"],
                        "via": cls_by.get(came_by.get(cid, cid), {}).get("name"),
                        "criterion": criterion(cid)["p"],
                    }
                    for cid in sorted(reachable, key=lambda c: cls_by[c]["name"].lower())
                ],
                "values": [
                    {
                        "id": v["id"],
                        "class_id": v["class_id"],
                        "class_name": cls_by.get(v["class_id"], {}).get("name", "(missing class)"),
                        "value": v["value"],
                        "belief": price_of(v["belief"]),
                    }
                    for (cid, oid), v in value_at.items()
                    if oid == o["id"]
                ],
                "assumptions": sorted(inherited.values(), key=lambda a: a["name"].lower()),
            }
        )

    # -- classes
    out_classes = []
    for c in classes:
        came_by, reachable = _closure(class_edges, [c["id"]])
        reachable.discard(c["id"])
        inherited: dict[str, dict] = {}
        for cid in reachable:
            for m in class_assumptions.get(cid, []):
                inherited.setdefault(
                    m["assumption_id"],
                    {
                        **assumption_brief(m["assumption_id"]),
                        "from": cls_by[cid]["name"],
                        "belief": price_of(m["belief"]),
                        "id": m["id"],
                    },
                )
        crit = criterion(c["id"])
        instances = []
        for o in objects:
            edge = next((e for e in obj_classes.get(o["id"], []) if e["b_id"] == c["id"]), None)
            if edge is None:
                continue
            p = price_of(edge["belief"])
            instances.append(
                {
                    "id": o["id"],
                    "name": o["name"],
                    "belief": p,
                    "edge_id": edge["id"],
                    "gap": (p - crit["p"]) if (p is not None and crit["p"] is not None) else None,
                }
            )
        out_classes.append(
            {
                **{k: c[k] for k in ("id", "name", "definition")},
                "assumptions": [
                    {**assumption_brief(m["assumption_id"]), "belief": price_of(m["belief"]), "matching_id": m["id"]}
                    for m in class_assumptions.get(c["id"], [])
                ],
                "inherited": sorted(inherited.values(), key=lambda a: a["name"].lower()),
                "criterion": crit,
                "instances": sorted(instances, key=lambda x: x["name"].lower()),
                "subclasses": [
                    {
                        "id": x["id"],
                        "name": x["name"],
                        "belief": price_of(class_edge_rows.get((x["id"], c["id"]), {}).get("belief")),
                        "edge_id": class_edge_rows.get((x["id"], c["id"]), {}).get("id"),
                    }
                    for x in classes
                    if c["id"] in class_edges.get(x["id"], set())
                ],
                "superclasses": sorted(
                    [
                        {
                            "id": cid,
                            "name": cls_by[cid]["name"],
                            "belief": price_of(class_edge_rows.get((c["id"], cid), {}).get("belief")),
                            "edge_id": class_edge_rows.get((c["id"], cid), {}).get("id"),
                            "criterion": criterion(cid)["p"],
                        }
                        for cid in reachable
                    ],
                    key=lambda x: x["name"].lower(),
                ),
                "values": [
                    {
                        "id": v["id"],
                        "object_id": v["object_id"],
                        "object_name": obj_by.get(v["object_id"], {}).get("name", "(missing object)"),
                        "value": v["value"],
                        "belief": price_of(v["belief"]),
                    }
                    for (cid, _oid), v in value_at.items()
                    if cid == c["id"]
                ],
            }
        )

    # -- assumptions
    out_assumptions = []
    for a in assumptions:
        holders = [c for c in classes if any(m["assumption_id"] == a["id"] for m in class_assumptions.get(c["id"], []))]
        touched: dict[str, dict] = {}
        for c in holders:
            for other in classes:
                carrier = other
                if other["id"] != c["id"]:
                    _, reach = _closure(class_edges, [other["id"]])
                    if c["id"] not in reach:
                        continue
                for o in objects:
                    if carrier["id"] not in [e["b_id"] for e in obj_classes.get(o["id"], [])]:
                        continue
                    entry = touched.setdefault(o["id"], {"id": o["id"], "name": o["name"], "via": []})
                    name = c["name"] if carrier["id"] == c["id"] else f"{carrier['name']} → {c['name']}"
                    if name not in entry["via"]:
                        entry["via"].append(name)
        out_assumptions.append(
            {
                **{k: a[k] for k in ("id", "name", "definition")},
                "classes": [
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "belief": price_of(next(m for m in class_assumptions[c["id"]] if m["assumption_id"] == a["id"])["belief"]),
                        "matching_id": next(m for m in class_assumptions[c["id"]] if m["assumption_id"] == a["id"])["id"],
                    }
                    for c in holders
                ],
                "objects": sorted(touched.values(), key=lambda x: x["name"].lower()),
            }
        )

    prices = claim_list(out_objects, out_classes, out_assumptions, markets)

    payload = {
        "db": str(path),
        "loaded": _now(),
        "gap_warn": GAP_WARN,
        "counts": {
            "objects": len(objects),
            "classes": len(classes),
            "assumptions": len(assumptions),
            "is": len(is_),
            "matchings": len(matching),
            "values": len(values),
            "markets": len(markets),
            "claims": len(prices),
            "priced": sum(1 for c in prices if c["belief"] is not None),
        },
        "objects": sorted(out_objects, key=lambda o: o["name"].lower()),
        "classes": sorted(out_classes, key=lambda c: c["name"].lower()),
        "assumptions": sorted(out_assumptions, key=lambda a: a["name"].lower()),
        "markets": sorted(
            [
                {
                    **{k: m[k] for k in ("id", "question", "binds")},
                    "belief": price_of(m["price"]),
                }
                for m in markets
            ],
            key=lambda m: (m["question"] or "").lower(),
        ),
        "prices": prices,
        "edges": is_,
        "matchings": matching,
    }
    payload["issues"] = issues(payload)
    return payload


def claim_list(objects: list[dict], classes: list[dict], assumptions: list[dict], markets: list[dict]) -> list[dict]:
    """Every row that can be staked on, flattened: this is the market list."""
    out: list[dict] = []
    obj_name = {o["id"]: o["name"] for o in objects}
    for o in objects:
        for e in o["classes"]:
            out.append(
                {
                    "table": "is_",
                    "id": e["id"],
                    "kind": "is",
                    "claim": f'{o["name"]} is {e["class_name"]}',
                    "subject": o["name"],
                    "object": e["class_name"],
                    "href": {"kind": "object", "id": o["id"]},
                    "belief": e["belief"],
                    "support": e["support"],
                    "gap": e["gap"],
                    "weakest": e["weakest"],
                }
            )
        for v in o["values"]:
            out.append(
                {
                    "table": "value",
                    "id": v["id"],
                    "kind": "value",
                    "claim": f'{o["name"]}.{v["class_name"]} = {v["value"]}',
                    "subject": o["name"],
                    "object": v["class_name"],
                    "href": {"kind": "object", "id": o["id"]},
                    "belief": v["belief"],
                    "support": v["belief"],
                    "gap": None,
                    "weakest": None,
                }
            )
    for c in classes:
        for a in c["assumptions"]:
            out.append(
                {
                    "table": "assumptionmatching",
                    "id": a["matching_id"],
                    "kind": "requirement",
                    "claim": f'{c["name"]} requires {a["name"]}',
                    "subject": c["name"],
                    "object": a["name"],
                    "href": {"kind": "class", "id": c["id"]},
                    "belief": a["belief"],
                    "support": a["belief"],
                    "gap": None,
                    "weakest": None,
                }
            )
        for s in c["superclasses"]:
            out.append(
                {
                    "table": "is_",
                    "id": s["edge_id"],
                    "kind": "is",
                    "claim": f'{c["name"]} is {s["name"]}',
                    "subject": c["name"],
                    "object": s["name"],
                    "href": {"kind": "class", "id": c["id"]},
                    "belief": s["belief"],
                    "support": s["belief"],
                    "gap": None,
                    "weakest": None,
                }
            )
    for m in markets:
        p = price_of(m.get("price"))
        out.append(
            {
                "table": "market",
                "id": m["id"],
                "kind": "market",
                "claim": m.get("question") or "(no question)",
                "subject": "",
                "object": m.get("binds") or "",
                "href": None,
                "belief": p,
                "support": p,
                "gap": None,
                "weakest": None,
            }
        )
    return out


def issues(payload: dict) -> list[dict]:
    """What the prices cannot support yet.

    A class is a definition plus the assumptions that must hold - that is its
    membership criterion, and its price is the weakest of them. So the failures
    worth surfacing are the priced ones: a claim above what it rests on, and a
    claim that rests on nothing priced at all.
    """
    out: list[dict] = []

    def add(level: str, title: str, detail: str, ref: dict | None = None) -> None:
        out.append({"level": level, "title": title, "detail": detail, "ref": ref})

    warn_gap = payload.get("gap_warn", GAP_WARN)

    for c in payload["classes"]:
        name, definition = c["name"].strip(), _clean(c["definition"])
        crit = c["criterion"]
        if not definition:
            add("warn", f"{name} has no definition", "A class with no definition cannot be applied consistently.", {"kind": "class", "id": c["id"]})
        elif definition.lower() == name.lower():
            add("warn", f"{name} defines itself", f'The definition is "{definition}", which restates the name.', {"kind": "class", "id": c["id"]})
        if not c["assumptions"] and not c["inherited"]:
            add("warn", f"{name} has no assumptions", "Nothing has to be true for something to be this class, so nothing can be checked.", {"kind": "class", "id": c["id"]})
        elif crit["p"] is None:
            add("warn", f"{name} has no priced assumption", f'{crit["of"]} requirement(s), none of them traded. The price of being a {name} is unknown.', {"kind": "class", "id": c["id"]})
        if not c["instances"] and not c["subclasses"]:
            add("note", f"nothing is {name}", "The class exists but nothing is filed under it.", {"kind": "class", "id": c["id"]})

        for i in c["instances"]:
            if i["gap"] is not None and i["gap"] >= warn_gap:
                add(
                    "warn",
                    f"{i['name']} is {name} at {pct(i['belief'])}, but {name} only asks for {pct(crit['p'])}",
                    f"the claim is {pct(i['gap'])} above its own criterion"
                    + (f", whose weakest link is “{crit['weakest']}”" if crit["weakest"] else ""),
                    {"kind": "object", "id": i["id"]},
                )
            elif i["belief"] is None:
                add("note", f"{i['name']} is {name} is unpriced", "Nobody has staked on it, so it is neither true nor false yet.", {"kind": "object", "id": i["id"]})

    for o in payload["objects"]:
        if not o["classes"]:
            add("warn", f"{o['name']} belongs to no class", "It has no properties, so there is nothing to observe about it.", {"kind": "object", "id": o["id"]})
        if not _clean(o["definition"]):
            add("note", f"{o['name']} has no definition", "What the name means is not written down.", {"kind": "object", "id": o["id"]})

    for a in payload["assumptions"]:
        if not a["classes"]:
            add("warn", f"{a['name']} is required by nothing", "No class lists it, so no claim rests on it.", {"kind": "assumption", "id": a["id"]})
        if _clean(a["definition"]).lower() == a["name"].lower():
            add("note", f"{a['name']} defines itself", "The definition restates the name.", {"kind": "assumption", "id": a["id"]})

    known = {o["id"] for o in payload["objects"]} | {c["id"] for c in payload["classes"]}
    class_ids = {c["id"] for c in payload["classes"]}
    for edge in payload["edges"]:
        if edge["a_id"] not in known:
            add("warn", "dangling is_ edge", f'{edge["id"]} points at a row that is gone.', None)
        if edge["b_id"] not in class_ids:
            add("warn", "is_ points at no class", f'{edge["id"]} names a class that is not in the table.', None)

    for m in payload["markets"]:
        if m["belief"] is None:
            add("note", f"market “{m['question'] or m['id']}” is unpriced", "A market with no price is a question nobody has answered with money.", None)

    return out


def pct(p: float | None) -> str:
    return "—" if p is None else f"{round(p * 100)}%"


# -- writing ---------------------------------------------------------------
def _find(con: sqlite3.Connection, table: str, row_id: str) -> sqlite3.Row:
    row = con.execute(f'select * from "{table}" where id = ?', (row_id,)).fetchone()
    if row is None:
        raise StoreError(f"no {table} with id {row_id}")
    return row


def _unique_name(con: sqlite3.Connection, table: str, name: str, row_id: str | None = None) -> None:
    clash = con.execute(f'select id from "{table}" where lower(name) = lower(?)', (name,)).fetchone()
    if clash is not None and clash["id"] != row_id:
        raise StoreError(f"{name} already exists")


def _require(payload: dict, *keys: str) -> None:
    for key in keys:
        if payload.get(key) in (None, ""):
            raise StoreError(f"{key} is required")


def belief_arg(raw) -> float | None:
    """Accept ``0.62``, ``62`` or ``"62%"``; empty means unpriced."""
    if raw is None or raw == "":
        return None
    text = str(raw).strip().rstrip("%").strip()
    try:
        number = float(text)
    except ValueError:
        raise StoreError(f"not a probability: {raw!r}") from None
    if number > 1.0:
        number = number / 100.0
    if number < 0.0 or number > 1.0:
        raise StoreError("a probability is between 0 and 1 (or 0 and 100%)")
    return number


CLAIM_TABLES = {"is_", "assumptionmatching", "value", "market"}


def mutate(op: str, payload: dict, path: Path | str = SCHEMA) -> dict:
    """Apply one change and return the new state."""
    con = connect(path)
    try:
        with con:  # one transaction: either the change happens or it does not
            _apply(con, op, payload)
    finally:
        con.close()
    return state(path)


def _apply(con: sqlite3.Connection, op: str, p: dict) -> None:
    if op == "claim.price":
        table = p.get("table")
        if table not in CLAIM_TABLES:
            raise StoreError(f"cannot price a {table!r}")
        _require(p, "id")
        _find(con, table, p["id"])
        column = "price" if table == "market" else "belief"
        con.execute(f'update "{table}" set {column} = ? where id = ?', (belief_arg(p.get("belief")), p["id"]))

    elif op == "object.create":
        _require(p, "name")
        name = _clean(p["name"])
        _unique_name(con, "object", name)
        con.execute(
            'insert into "object" (id, name, definition) values (?, ?, ?)',
            (new_id(), name, _clean(p.get("definition"))),
        )
    elif op == "object.update":
        _require(p, "id", "name")
        _find(con, "object", p["id"])
        name = _clean(p["name"])
        _unique_name(con, "object", name, p["id"])
        con.execute(
            'update "object" set name = ?, definition = ? where id = ?',
            (name, _clean(p.get("definition")), p["id"]),
        )
    elif op == "object.delete":
        _require(p, "id")
        _find(con, "object", p["id"])
        con.execute('delete from "value" where object_id = ?', (p["id"],))
        con.execute('delete from "is_" where a_id = ? and a_kind = ?', (p["id"], "object"))
        con.execute('delete from "object" where id = ?', (p["id"],))

    elif op == "class.create":
        _require(p, "name")
        name = _clean(p["name"])
        _unique_name(con, "class", name)
        con.execute(
            'insert into "class" (id, name, definition) values (?, ?, ?)',
            (new_id(), name, _clean(p.get("definition"))),
        )
    elif op == "class.update":
        _require(p, "id", "name")
        _find(con, "class", p["id"])
        name = _clean(p["name"])
        _unique_name(con, "class", name, p["id"])
        con.execute(
            'update "class" set name = ?, definition = ? where id = ?',
            (name, _clean(p.get("definition")), p["id"]),
        )
    elif op == "class.delete":
        _require(p, "id")
        _find(con, "class", p["id"])
        con.execute('delete from "value" where class_id = ?', (p["id"],))
        con.execute('delete from "assumptionmatching" where class_id = ?', (p["id"],))
        con.execute('delete from "is_" where b_id = ?', (p["id"],))
        con.execute('delete from "is_" where a_id = ? and a_kind = ?', (p["id"], "class"))
        con.execute('delete from "class" where id = ?', (p["id"],))

    elif op == "assumption.create":
        _require(p, "name")
        name = _clean(p["name"])
        _unique_name(con, "assumption", name)
        con.execute(
            'insert into "assumption" (id, name, definition) values (?, ?, ?)',
            (new_id(), name, _clean(p.get("definition"))),
        )
    elif op == "assumption.update":
        _require(p, "id", "name")
        _find(con, "assumption", p["id"])
        name = _clean(p["name"])
        _unique_name(con, "assumption", name, p["id"])
        con.execute(
            'update "assumption" set name = ?, definition = ? where id = ?',
            (name, _clean(p.get("definition")), p["id"]),
        )
    elif op == "assumption.delete":
        _require(p, "id")
        _find(con, "assumption", p["id"])
        con.execute('delete from "assumptionmatching" where assumption_id = ?', (p["id"],))
        con.execute('delete from "assumption" where id = ?', (p["id"],))

    elif op == "is.add":
        _require(p, "a_id", "b_id")
        a_kind = p.get("a_kind") or "object"
        if a_kind not in ("object", "class"):
            raise StoreError(f"a_kind must be object or class, not {a_kind!r}")
        _find(con, a_kind, p["a_id"])
        _find(con, "class", p["b_id"])
        if p["a_id"] == p["b_id"]:
            raise StoreError("a class cannot be a class of itself")
        exists = con.execute('select id from "is_" where a_id = ? and b_id = ?', (p["a_id"], p["b_id"])).fetchone()
        if exists is not None:
            # The pair is already stated, so saying it twice adds nothing - but a
            # price on it is a new opinion, so that part is kept.
            belief = belief_arg(p.get("belief"))
            if belief is not None:
                con.execute('update "is_" set belief = ? where id = ?', (belief, exists["id"]))
            return
        con.execute(
            'insert into "is_" (id, a_id, a_kind, b_id, belief) values (?, ?, ?, ?, ?)',
            (new_id(), p["a_id"], a_kind, p["b_id"], belief_arg(p.get("belief"))),
        )
    elif op == "is.remove":
        _require(p, "id")
        _find(con, "is_", p["id"])
        con.execute('delete from "is_" where id = ?', (p["id"],))

    elif op == "assumption.link":
        _require(p, "class_id", "assumption_id")
        _find(con, "class", p["class_id"])
        _find(con, "assumption", p["assumption_id"])
        exists = con.execute(
            'select id from "assumptionmatching" where class_id = ? and assumption_id = ?',
            (p["class_id"], p["assumption_id"]),
        ).fetchone()
        if exists is not None:
            belief = belief_arg(p.get("belief"))
            if belief is not None:
                con.execute('update "assumptionmatching" set belief = ? where id = ?', (belief, exists["id"]))
            return
        con.execute(
            'insert into "assumptionmatching" (id, class_id, assumption_id, belief) values (?, ?, ?, ?)',
            (new_id(), p["class_id"], p["assumption_id"], belief_arg(p.get("belief"))),
        )
    elif op == "assumption.unlink":
        _require(p, "id")
        _find(con, "assumptionmatching", p["id"])
        con.execute('delete from "assumptionmatching" where id = ?', (p["id"],))

    elif op == "value.set":
        _require(p, "class_id", "object_id", "value")
        _find(con, "class", p["class_id"])
        _find(con, "object", p["object_id"])
        try:
            number = int(p["value"])
        except (TypeError, ValueError):
            raise StoreError(f"value must be a whole number, not {p['value']!r}") from None
        found = con.execute(
            'select id from "value" where class_id = ? and object_id = ?', (p["class_id"], p["object_id"])
        ).fetchone()
        if found is None:
            con.execute(
                'insert into "value" (id, class_id, object_id, value, belief) values (?, ?, ?, ?, ?)',
                (new_id(), p["class_id"], p["object_id"], number, belief_arg(p.get("belief"))),
            )
        else:
            con.execute('update "value" set value = ? where id = ?', (number, found["id"]))
    elif op == "value.clear":
        _require(p, "id")
        _find(con, "value", p["id"])
        con.execute('delete from "value" where id = ?', (p["id"],))

    elif op == "market.create":
        _require(p, "question")
        con.execute(
            'insert into "market" (id, question, binds, price) values (?, ?, ?, ?)',
            (new_id(), _clean(p["question"]), _clean(p.get("binds")), belief_arg(p.get("belief"))),
        )
    elif op == "market.update":
        _require(p, "id", "question")
        _find(con, "market", p["id"])
        con.execute(
            'update "market" set question = ?, binds = ?, price = ? where id = ?',
            (_clean(p["question"]), _clean(p.get("binds")), belief_arg(p.get("belief")), p["id"]),
        )
    elif op == "market.delete":
        _require(p, "id")
        _find(con, "market", p["id"])
        con.execute('delete from "market" where id = ?', (p["id"],))

    else:
        raise StoreError(f"unknown operation {op!r}")
