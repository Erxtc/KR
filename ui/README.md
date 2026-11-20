# kr ui

A browser view of `kr.sqlite` — the objects, the classes that give them
properties, the assumptions each class requires, and the price of every one of
those claims.

    python ui/serve.py                       # http://127.0.0.1:8788
    python ui/serve.py --port 9000 --db other.sqlite

Standard library only. It reads the same tables as `db/schema.py` but with plain
`sqlite3`, so it runs against a copy of the database with nothing installed — no
sqlmodel, no `.env`, no build step. `ui/` is served as three static files plus one
JSON endpoint; every change is one operation posted back, and the response is the
new snapshot.

## The idea it is shaped around

**Every relation is a market.** `NS is country` is not a fact in this database,
it is a claim with a price — so is `being a scammer requires deliberately
deceiving people`, and so is `NS.gdp = 1200000000`. Each of those rows carries a
probability in `[0, 1]`, shown as 0–100%.

That is why the schema grew a `belief` column on `is_`,
`assumptionmatching` and `value`, and why `market` now has a question, a binding
and a price. `NULL` means *nobody has traded this yet*, which is deliberately
different from 0.5 and is drawn differently — a dashed pill instead of a solid
one.

### The one derived number

A class applies as strongly as its weakest requirement, so:

    criterion(class) = min(price of the assumptions it requires)
    support(claim)   = min(price of the claim, criterion(class) it points at)
    gap              = price of the claim − criterion

`NS is a scammer` at 99% resting on a class whose criterion is 40% has a gap of
+59%: belief the claim does not pay for. That gap is the fragility number — where
an assumption is most likely to break next — and it is surfaced per claim, on the
board, and as a warning in **gaps**.

## What is on screen

| view | what it answers |
| --- | --- |
| **markets** | every claim in the database with its price, what it rests on, and its gap. The book. |
| **objects** | what a thing is: its classes, its values, and the assumptions it inherits |
| **classes** | the membership test: definition, required assumptions (priced), instances, sub-classes |
| **assumptions** | which classes require it and which objects therefore rest on it |
| **gaps** | what cannot be checked yet: unpriced criteria, claims above their criterion, self-defining classes, orphans |

Every price is the same control in the same place: click it, type `62%` or `0.62`
or `62`, enter. Values are numbers with a price attached. Prices live in the
database, not in the tab, so two tabs see one book.

## Files

    ui/krstore.py   the seven tables read and written in plain SQL, plus the joins
    ui/serve.py     the HTTP server: static files, /api/state, /api/mutate
    ui/index.html   the shell
    ui/app.js       render + post; it never decides what a claim inherits
    ui/app.css      one dark panel, one type scale

`ui/krstore.py` also computes the derived numbers and the gap list, so the
browser is a renderer rather than a second, subtly different model of the same
data.

## Writing

Writes go straight to `kr.sqlite`. The first change in a session copies the file
into `ui/backups/` (last ten kept) and the copy is shown in the footer as the
undo. Nothing else versions the data: the schema has no history table.

Two rules the schema does not enforce, enforced in `krstore.py` instead:

* one value per (class, object) — two numbers for one slot would mean nothing;
* deletes take their edges with them (`PRAGMA foreign_keys` is on, so children go
  first).

## Migration

New databases get the price columns from `create_all`. An existing one does not,
so:

    python db/migrate_market.py

Idempotent, prints what it added, and leaves a `kr.bak-<timestamp>.sqlite` copy
next to the file before it touches anything.
