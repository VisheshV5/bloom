"""Generate tasks/benchmark.jsonl. Every answer is computed by code, never hand-typed.

Tasks come from parameterized templates (seeded), 20 per category, split per category:
  dev  (first 8): used by gap detection, the Forge, and the Reviewer's test tasks
  test (last 12): held out; used ONLY by `python -m forge eval`
Templates cycle, so both splits cover every template.

Run: uv run python -m tasks.build_benchmark
"""

from __future__ import annotations

import calendar
import json
import random
from pathlib import Path

from bloom.tools.sql import SCHEMA_DESCRIPTION
from bloom.tools import dates, stats, units
from tasks import local_db as sql

OUT = Path(__file__).with_name("benchmark.jsonl")
SEED = 7
PER_CATEGORY = 20
DEV_PER_CATEGORY = 8
FINAL_HINT = " End your reply with a line `FINAL: <answer>`."
CATEGORIES = ["sql", "stats", "dates", "units", "extraction"]

MONTHS = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June"}
BD = "Business days are Monday to Friday; there are no holidays."


_LAST_SQL: list[str] = [""]


def _one(query: str):
    _LAST_SQL[0] = query
    _, rows = sql.query(query)
    return rows[0][0]


def _mk(category, prompt, answer, check, tolerance=None, how: str = "") -> dict:
    """`how` is a worked solution (tool calls + result) used as a few-shot example by the Forge."""
    if category == "sql" and not how:
        how = f'run_sql(query="{_LAST_SQL[0]}") -> {answer}'
    t = {"category": category, "prompt": prompt + FINAL_HINT, "answer": answer, "check": check}
    if tolerance is not None:
        t["tolerance"] = tolerance
    t["how"] = how
    return t


def _month(rng) -> tuple[int, str, str]:
    m = rng.randint(1, 6)
    return m, MONTHS[m], f"2026-{m:02d}"


def _rand_date(rng, start="2026-01-01", span=700) -> str:
    return dates.add_days(start, rng.randint(0, span))


# ── SQL (Hospital A's records) ────────────────────────────────────────────────
WARDS = ["cardiology", "respiratory", "general medicine", "orthopedics"]
DIAGNOSES = ["heart failure", "pneumonia", "COPD", "diabetes", "hip replacement", "sepsis"]


def _sql_templates():
    p = f"You have access to Hospital A's patient records. {SCHEMA_DESCRIPTION} "

    def busiest_ward(rng):
        _, name, ym = _month(rng)
        return _mk("sql", p + f"Which ward had the most admissions in {name} 2026? Answer with the ward name.",
                   _one(f"SELECT ward FROM admissions WHERE admit_date LIKE '{ym}%' GROUP BY ward ORDER BY COUNT(*) DESC LIMIT 1"),
                   "exact")

    def total_adm(rng):
        _, name, ym = _month(rng)
        return _mk("sql", p + f"How many admissions were there in {name} 2026?",
                   _one(f"SELECT COUNT(*) FROM admissions WHERE admit_date LIKE '{ym}%'"), "number", {"abs": 0})

    def top_diag(rng):
        _, name, ym = _month(rng)
        ward = rng.choice(WARDS[:3])
        return _mk("sql", p + f"Which diagnosis had the most admissions to the {ward} ward in {name} 2026? Answer with the diagnosis.",
                   _one(f"SELECT diagnosis FROM admissions WHERE admit_date LIKE '{ym}%' AND ward='{ward}' "
                        "GROUP BY diagnosis ORDER BY COUNT(*) DESC LIMIT 1"), "exact")

    def readmits(rng):
        _, name, ym = _month(rng)
        diag = rng.choice(DIAGNOSES)
        return _mk("sql", p + f"How many {diag} admissions in {name} 2026 were readmitted within 30 days?",
                   _one(f"SELECT SUM(readmitted_30d) FROM admissions WHERE admit_date LIKE '{ym}%' AND diagnosis='{diag}'"),
                   "number", {"abs": 0})

    def avg_los(rng):
        _, name, ym = _month(rng)
        ward = rng.choice(WARDS)
        return _mk("sql", p + f"What was the average length of stay (days) in the {ward} ward for admissions in {name} 2026? Round to 2 decimals.",
                   round(_one(f"SELECT AVG(length_of_stay) FROM admissions WHERE admit_date LIKE '{ym}%' AND ward='{ward}'"), 2),
                   "number", {"abs": 0.01})

    def rate_by_protocol(rng):
        diag, proto = rng.choice(DIAGNOSES), rng.choice(["old", "new"])
        return _mk("sql", p + f"What was the 30-day readmission rate (percent) for {diag} admissions under the {proto} discharge protocol? Round to 1 decimal.",
                   round(100 * _one(f"SELECT AVG(readmitted_30d) FROM admissions WHERE diagnosis='{diag}' AND protocol='{proto}'"), 1),
                   "number", {"abs": 0.1})

    def older_patients(rng):
        _, name, ym = _month(rng)
        age = rng.choice([60, 65, 70, 75])
        return _mk("sql", p + f"How many admissions in {name} 2026 were for patients aged {age} or older?",
                   _one(f"SELECT COUNT(*) FROM admissions a JOIN patients pt ON pt.patient_id = a.patient_id "
                        f"WHERE a.admit_date LIKE '{ym}%' AND pt.age >= {age}"), "number", {"abs": 0})

    def female_share(rng):
        ward = rng.choice(WARDS)
        return _mk("sql", p + f"What percentage of admissions to the {ward} ward were female patients? Round to 1 decimal.",
                   round(100 * _one(f"SELECT AVG(CASE WHEN pt.sex='F' THEN 1.0 ELSE 0 END) FROM admissions a "
                                    f"JOIN patients pt ON pt.patient_id = a.patient_id WHERE a.ward='{ward}'"), 1),
                   "number", {"abs": 0.1})

    return [busiest_ward, total_adm, top_diag, readmits, avg_los, rate_by_protocol, older_patients, female_share]


# ── stats ──────────────────────────────────────────────────────────────────
def _nums(rng, n, mu, sd) -> list[float]:
    return [round(rng.gauss(mu, sd), 1) for _ in range(n)]


def _stats_templates():
    def stdev(rng):
        a = _nums(rng, rng.randint(18, 30), rng.uniform(20, 80), rng.uniform(4, 12))
        return _mk("stats", f"Compute the sample standard deviation of: {a}. Round to 3 decimals.",
                   round(stats.describe(a)["stdev"], 3), "number", {"abs": 0.002},
                   how=f'describe(values=<the {len(a)} numbers>) -> stdev={stats.describe(a)["stdev"]:.6f}; round to 3 decimals')

    def median(rng):
        b = _nums(rng, rng.choice([25, 27, 29, 31]), rng.uniform(80, 150), 25)
        return _mk("stats", f"What is the median of: {b}?", stats.describe(b)["median"], "number", {"abs": 0.001},
                   how=f'describe(values=<the {len(b)} numbers>) -> median={stats.describe(b)["median"]}')

    def welch_p(rng):
        mu = rng.uniform(8, 12)
        x1, x2 = _nums(rng, rng.randint(15, 22), mu, 2.0), _nums(rng, rng.randint(15, 22), mu + rng.uniform(0.3, 2.0), 2.4)
        return _mk("stats", f"Run a two-sided Welch t-test comparing A={x1} and B={x2}. What is the p-value? Round to 3 decimals.",
                   round(stats.ttest_welch(x1, x2)["p_value"], 3), "number", {"abs": 0.002},
                   how=f'ttest_welch(a=<A>, b=<B>) -> p_value={stats.ttest_welch(x1, x2)["p_value"]:.6f}; round to 3 decimals')

    def slope(rng):
        xs = list(range(1, rng.randint(14, 20)))
        k = rng.uniform(1.5, 4.5)
        ys = [round(k * x + 7 + rng.gauss(0, 4), 1) for x in xs]
        return _mk("stats", f"Fit a least-squares line y = a*x + b to x={xs}, y={ys}. What is the slope a? Round to 3 decimals.",
                   round(stats.linregress(xs, ys)["slope"], 3), "number", {"abs": 0.002},
                   how=f'linregress(x=<x>, y=<y>) -> slope={stats.linregress(xs, ys)["slope"]:.6f}; round to 3 decimals')

    def pearson(rng):
        u = _nums(rng, rng.randint(16, 24), 5, 2)
        v = [round(rng.uniform(0.3, 0.9) * ui + rng.gauss(0, 1.5), 1) for ui in u]
        return _mk("stats", f"What is the Pearson correlation between x={u} and y={v}? Round to 3 decimals.",
                   round(stats.correlation(u, v), 3), "number", {"abs": 0.002},
                   how=f'correlation(x=<x>, y=<y>) -> {stats.correlation(u, v):.6f}; round to 3 decimals')

    def pct(rng):
        w = _nums(rng, rng.randint(30, 45), 200, 40)
        q = rng.choice([75, 90, 95])
        return _mk("stats", f"Compute the {q}th percentile (linear interpolation, like numpy's default) of: {w}. Round to 2 decimals.",
                   round(stats.percentile(w, q), 2), "number", {"abs": 0.01},
                   how=f'percentile(values=<the numbers>, q={q}) -> {stats.percentile(w, q):.4f}; round to 2 decimals')

    def welch_t(rng):
        y1, y2 = _nums(rng, rng.randint(12, 18), 72, 6), _nums(rng, rng.randint(12, 20), rng.uniform(64, 72), 9)
        return _mk("stats", f"Welch's t statistic for A={y1} vs B={y2} (A minus B)? Round to 3 decimals.",
                   round(stats.ttest_welch(y1, y2)["t"], 3), "number", {"abs": 0.002},
                   how=f'ttest_welch(a=<A>, b=<B>) -> t={stats.ttest_welch(y1, y2)["t"]:.6f} (A minus B); round to 3 decimals')

    def mean(rng):
        z = _nums(rng, rng.randint(22, 32), rng.uniform(2, 6), 1.1)
        return _mk("stats", f"What is the arithmetic mean of: {z}? Round to 4 decimals.",
                   round(stats.describe(z)["mean"], 4), "number", {"abs": 0.0001},
                   how=f'describe(values=<the numbers>) -> mean={stats.describe(z)["mean"]:.6f}; round to 4 decimals')

    return [stdev, median, welch_p, slope, pearson, pct, welch_t, mean]


# ── dates ──────────────────────────────────────────────────────────────────
def _dates_templates():
    def add_bd(rng):
        start, n = _rand_date(rng), rng.randint(20, 120)
        return _mk("dates", f"What date is {n} business days after {start}? {BD} The start date is not counted. Answer as YYYY-MM-DD.",
                   dates.add_business_days(start, n), "date",
                   how=f'add_business_days(start="{start}", days={n}) -> {dates.add_business_days(start, n)}')

    def between_bd(rng):
        a = _rand_date(rng, span=400)
        b = dates.add_days(a, rng.randint(40, 200))
        return _mk("dates", f"How many business days are there after {a} up to and including {b}? {BD}",
                   dates.business_days_between(a, b), "number", {"abs": 0},
                   how=f'business_days_between(start="{a}", end="{b}") -> {dates.business_days_between(a, b)}')

    def weekday(rng):
        d = _rand_date(rng, "2025-01-01", 1500)
        return _mk("dates", f"What day of the week is {d}?", dates.weekday(d), "exact",
                   how=f'weekday(date="{d}") -> {dates.weekday(d)}')

    def cal_days(rng):
        a = _rand_date(rng, "2024-01-01", 700)
        b = dates.add_days(a, rng.randint(200, 900))
        return _mk("dates", f"How many calendar days are there from {a} to {b}?", dates.days_between(a, b), "number", {"abs": 0},
                   how=f'days_between(start="{a}", end="{b}") -> {dates.days_between(a, b)}')

    def bd_before(rng):
        d, n = _rand_date(rng), rng.randint(40, 150)
        return _mk("dates", f"What date is {n} business days before {d}? {BD} Answer as YYYY-MM-DD.",
                   dates.add_business_days(d, -n), "date",
                   how=f'add_business_days(start="{d}", days=-{n}) -> {dates.add_business_days(d, -n)}')

    def add_cal(rng):
        d, n = _rand_date(rng), rng.randint(100, 400)
        return _mk("dates", f"What date is {n} calendar days after {d}? Answer as YYYY-MM-DD.", dates.add_days(d, n), "date",
                   how=f'add_days(start="{d}", days={n}) -> {dates.add_days(d, n)}')

    def count_weekday(rng):
        a = _rand_date(rng, span=300)
        b = dates.add_days(a, rng.randint(120, 365))
        day = rng.choice(["Monday", "Wednesday", "Friday"])
        count = sum(1 for d in dates.business_days_in_range(a, b) if dates.weekday(d) == day)
        return _mk("dates", f"How many {day}s are there from {a} to {b} inclusive?", count, "number", {"abs": 0},
                   how=f'business_days_in_range(start="{a}", end="{b}") -> count the dates whose weekday(...) is {day} -> {count}')

    def project(rng):
        start = rng.choice(dates.business_days_in_range("2026-09-01", "2027-03-31"))
        n = rng.randint(30, 90)
        return _mk("dates", f"A project starts on {start} and needs {n} business days of work, finishing at the end of the {n}th business day (the start day counts as day 1). {BD} On what date does it finish? Answer as YYYY-MM-DD.",
                   dates.add_business_days(start, n - 1), "date",
                   how=f'the start day is day 1, so add_business_days(start="{start}", days={n - 1}) -> {dates.add_business_days(start, n - 1)}')

    return [add_bd, between_bd, weekday, cal_days, bd_before, add_cal, count_weekday, project]


# ── units ──────────────────────────────────────────────────────────────────
def _units_templates():
    def price_kg(rng):
        lb, price = rng.choice([1.5, 2, 2.5, 3, 5]), round(rng.uniform(12, 40), 2)
        return _mk("units", f"A {lb} lb bag of coffee beans costs ${price:.2f}. What is the price per kilogram in USD? Round to 2 decimals.",
                   round(price / units.convert(lb, "lb", "kg"), 2), "number", {"abs": 0.01},
                   how=f'convert_units(value={lb}, from_unit="lb", to_unit="kg") -> {units.convert(lb, "lb", "kg"):.6f}; calculate("{price} / {units.convert(lb, "lb", "kg"):.6f}") -> {price / units.convert(lb, "lb", "kg"):.4f}; round to 2 decimals')

    def temp(rng):
        if rng.random() < 0.5:
            f = round(rng.uniform(-10, 110), 1)
            return _mk("units", f"Convert {f} degrees Fahrenheit to Celsius. Round to 2 decimals.",
                       round(units.convert(f, "f", "c"), 2), "number", {"abs": 0.01},
                       how=f'convert_units(value={f}, from_unit="f", to_unit="c") -> {units.convert(f, "f", "c"):.4f}; round to 2 decimals')
        c = round(rng.uniform(-20, 45), 1)
        return _mk("units", f"Convert {c} degrees Celsius to Fahrenheit. Round to 2 decimals.",
                   round(units.convert(c, "c", "f"), 2), "number", {"abs": 0.01},
                   how=f'convert_units(value={c}, from_unit="c", to_unit="f") -> {units.convert(c, "c", "f"):.4f}; round to 2 decimals')

    def speed(rng):
        mi, mins = round(rng.uniform(10, 60), 1), rng.randint(20, 90)
        return _mk("units", f"A delivery van drives {mi} miles in {mins} minutes. What is its average speed in km/h? Round to 2 decimals.",
                   round(units.convert(mi, "mi", "km") / (mins / 60), 2), "number", {"abs": 0.01},
                   how=f'convert_units(value={mi}, from_unit="mi", to_unit="km") -> {units.convert(mi, "mi", "km"):.4f}; calculate("{units.convert(mi, "mi", "km"):.4f} / ({mins} / 60)") -> {units.convert(mi, "mi", "km") / (mins / 60):.4f}; round to 2 decimals')

    def cups(rng):
        c, batches = rng.choice([1.25, 1.5, 2.25, 2.75, 3.5]), rng.randint(3, 12)
        return _mk("units", f"A recipe needs {c} US cups of milk per batch. How many millilitres are needed for {batches} batches? Round to 1 decimal.",
                   round(units.convert(c * batches, "cup", "ml"), 1), "number", {"abs": 0.1},
                   how=f'calculate("{c} * {batches}") -> {c * batches}; convert_units(value={c * batches}, from_unit="cup", to_unit="ml") -> {units.convert(c * batches, "cup", "ml"):.3f}; round to 1 decimal')

    def per_litre(rng):
        price = round(rng.uniform(20, 60), 2)
        return _mk("units", f"Cold brew concentrate costs ${price:.2f} per US gallon. What is the cost per litre in USD? Round to 3 decimals.",
                   round(price / units.convert(1, "gal", "l"), 3), "number", {"abs": 0.001},
                   how=f'convert_units(value=1, from_unit="gal", to_unit="l") -> {units.convert(1, "gal", "l"):.6f}; calculate("{price} / {units.convert(1, "gal", "l"):.6f}") -> {price / units.convert(1, "gal", "l"):.5f}; round to 3 decimals')

    def area(rng):
        ft, inch, depth = rng.randint(4, 9), rng.randint(1, 11), rng.randint(18, 30)
        return _mk("units", f"A counter is {ft} ft {inch} in long and {depth} in deep. What is its area in square centimetres? Round to the nearest whole number.",
                   round(units.convert(ft * 12 + inch, "in", "cm") * units.convert(depth, "in", "cm")), "number", {"abs": 1},
                   how=f'length = {ft}*12+{inch} = {ft * 12 + inch} in -> convert_units(..., "in", "cm") = {units.convert(ft * 12 + inch, "in", "cm"):.3f} cm; depth convert_units({depth}, "in", "cm") = {units.convert(depth, "in", "cm"):.3f} cm; multiply -> {units.convert(ft * 12 + inch, "in", "cm") * units.convert(depth, "in", "cm"):.2f}; round')

    def doses(rng):
        oz, g = rng.choice([8, 10, 12, 16, 32]), rng.choice([14, 16, 18, 20, 21])
        return _mk("units", f"A {oz} oz bag of coffee: how many whole {g} g espresso doses does it make (convert ounces to grams first)? Answer with the number of doses.",
                   int(units.convert(oz, "oz", "g") // g), "number", {"abs": 0},
                   how=f'convert_units(value={oz}, from_unit="oz", to_unit="g") -> {units.convert(oz, "oz", "g"):.3f}; calculate("{units.convert(oz, "oz", "g"):.3f} // {g}") -> {int(units.convert(oz, "oz", "g") // g)} whole doses')

    def pace(rng):
        km, mins = rng.choice([5, 8, 10, 21.1]), rng.randint(25, 130)
        return _mk("units", f"A barista runs {km} km in {mins} minutes. What is the pace in minutes per mile? Round to 2 decimals.",
                   round(mins / units.convert(km, "km", "mi"), 2), "number", {"abs": 0.01},
                   how=f'convert_units(value={km}, from_unit="km", to_unit="mi") -> {units.convert(km, "km", "mi"):.5f}; calculate("{mins} / {units.convert(km, "km", "mi"):.5f}") -> {mins / units.convert(km, "km", "mi"):.4f}; round to 2 decimals')

    return [price_kg, temp, speed, cups, per_litre, area, doses, pace]


# ── extraction ─────────────────────────────────────────────────────────────
_NAMES = ["ana", "ben", "chen", "dana", "eli", "fatima", "gus", "hana", "ivan", "jo"]
_DOMAINS = ["bloom.coffee", "example.org", "beans.io", "mail.test"]


def _extraction_templates():
    def order_ids(rng):
        ids = [f"ORD-{rng.randint(10000, 99999)}" for _ in range(rng.randint(3, 6))]
        text = (f"Customer called about {ids[0]} and {ids[1]}. ORD-12 is not valid. "
                + " ".join(f"Also check {i}." for i in ids[2:]) + f" {ids[0]} was mentioned twice.")
        return _mk("extraction", f"List every distinct order ID of the form ORD-##### (exactly five digits) in this text, comma separated: \"{text}\"",
                   ", ".join(dict.fromkeys(ids)), "set",
                   how='regex_findall(pattern="ORD-\\d{5}\\b", text=<the text>) -> unique matches in order; ORD-12 does not match')

    def emails(rng):
        es = list(dict.fromkeys(f"{rng.choice(_NAMES)}{rng.choice(['', '.ops', '-team'])}@{rng.choice(_DOMAINS)}" for _ in range(3)))
        text = f"Contacts: {es[0]} (manager); " + ", ".join(es[1:]) + ". Not emails: team@ and @bloom."
        return _mk("extraction", f"Extract all email addresses from: \"{text}\" Comma separated.", ", ".join(es), "set",
                   how='regex_findall(pattern="[\\w.+-]+@[\\w-]+(?:\\.[\\w-]+)+", text=<the text>) -> the full addresses; "team@" and "@bloom" are not emails')

    def iso_dates(rng):
        ds = sorted({_rand_date(rng, span=360) for _ in range(rng.randint(3, 5))})
        text = "Invoices dated " + ", ".join(ds[:-1]) + f" were paid; 2026-13-0{rng.randint(1, 9)} is a typo. Next due {ds[-1]}."
        return _mk("extraction", f"List all valid ISO dates (YYYY-MM-DD) in: \"{text}\" Comma separated.", ", ".join(ds), "set",
                   how='regex_findall(pattern="\\d{4}-\\d{2}-\\d{2}", text=<the text>) -> drop any with month > 12 (e.g. 2026-13-xx)')

    def hashtags(rng):
        tags = list(dict.fromkeys(rng.sample(["#coldbrew", "#BloomPaloAlto", "#coffee", "#LatteArt", "#MondayMotivation", "#beans"], 3)))
        text = f"Loved the {tags[0]} at {tags[1]}! {tags[2]} {tags[0]} again tomorrow. Price: $5 #1 fan"
        return _mk("extraction", f"List the distinct hashtags (a # followed by letters only) in: \"{text}\" Comma separated, keep the # and original case.",
                   ", ".join(tags), "set",
                   how='regex_findall(pattern="#[A-Za-z]+\\b", text=<the text>) -> unique, keep case; "#1" has a digit so it is excluded')

    def phones(rng):
        nums = [(rng.choice([650, 415, 408, 510]), rng.randint(200, 999), rng.randint(1000, 9999)) for _ in range(3)]
        text = f"Store phones: ({nums[0][0]}) {nums[0][1]}-{nums[0][2]}, {nums[1][0]}-{nums[1][1]}-{nums[1][2]}, and {nums[2][0]}.{nums[2][1]}.{nums[2][2]}. Fax 555-0100 is local only."
        return _mk("extraction", f"Extract the 10-digit US phone numbers from: \"{text}\" and write each as ###-###-####, comma separated.",
                   ", ".join(f"{a}-{b}-{c}" for a, b, c in nums), "set",
                   how='regex_findall(pattern="\\(?\\d{3}\\)?[ .-]?\\d{3}[.-]\\d{4}", text=<the text>) -> normalize each to ###-###-####; skip the 7-digit fax')

    def skus(rng):
        ss = list(dict.fromkeys(f"{rng.choice(['BEAN', 'CUP', 'LID', 'SYR'])}-{rng.choice(['ETH', 'COL', 'PAPER', 'VAN', 'KEN'])}-{rng.randint(1, 20):02d}" for _ in range(3)))
        text = "Restock " + " and ".join(f"{s} x{rng.randint(2, 500)}" for s in ss) + ". Discontinued: bean-old-1."
        return _mk("extraction", f"List the SKUs (uppercase letters and digits in dash-separated groups, e.g. ABC-DEF-01) in: \"{text}\" Comma separated.",
                   ", ".join(ss), "set",
                   how='regex_findall(pattern="\\b[A-Z]+-[A-Z]+-\\d{2}\\b", text=<the text>) -> lowercase "bean-old-1" is excluded')

    def temps(rng):
        ts = [rng.choice([66, 67.5, 68, 69.25, 70.5, 71, 72.75, 74.25]) for _ in range(3)]
        ts = list(dict.fromkeys(ts))
        fmt = lambda v: f"{v:g}"  # noqa: E731
        text = "Temps logged: " + ", ".join(f"{fmt(t)}F at {when}" for t, when in zip(ts, ["open", "noon", "close"])) + "; target 70F."
        return _mk("extraction", f"List the logged temperature readings (numbers only, excluding the target) from: \"{text}\" Comma separated.",
                   ", ".join(fmt(t) for t in ts), "set",
                   how='regex_findall(pattern="\\d+(?:\\.\\d+)?(?=F at)", text=<the text>) -> the logged readings; exclude the 70F target')

    def urls(rng):
        paths = list(dict.fromkeys(rng.sample(["menu", "loyalty", "careers", "stores/palo-alto", "gift-cards", "blog/cold-brew"], 3)))
        text = f"See https://bloom.coffee/{paths[0]} and https://bloom.coffee/{paths[1]}; old link bloom.coffee/{paths[2]} has no scheme. Also https://bloom.coffee/{paths[2]}."
        found = [f"https://bloom.coffee/{p}" for p in paths]
        return _mk("extraction", f"List the distinct URLs that start with https:// in: \"{text}\" Comma separated, without trailing punctuation.",
                   ", ".join(found), "set",
                   how='regex_findall(pattern="https://[^\\s,;]*[^\\s,;.]", text=<the text>) -> unique URLs (the pattern excludes a trailing ".")')

    return [order_ids, emails, iso_dates, hashtags, phones, skus, temps, urls]


GENERATORS = {
    "sql": _sql_templates,
    "stats": _stats_templates,
    "dates": _dates_templates,
    "units": _units_templates,
    "extraction": _extraction_templates,
}


def build() -> list[dict]:
    rng = random.Random(SEED)
    tasks: list[dict] = []
    for category in CATEGORIES:
        templates = GENERATORS[category]()
        seen: set[str] = set()
        made: list[dict] = []
        i = 0
        while len(made) < PER_CATEGORY:
            t = templates[i % len(templates)](rng)
            i += 1
            if t["prompt"] in seen:
                continue
            seen.add(t["prompt"])
            made.append(t)
        for n, t in enumerate(made, 1):
            if isinstance(t["answer"], float) and t["answer"].is_integer() and t["check"] == "number":
                t["answer"] = int(t["answer"])
            split = "dev" if n <= DEV_PER_CATEGORY else "test"
            tasks.append({"id": f"{category}-{n:02d}", "split": split, "difficulty": "standard", **t})
    return tasks + build_hard()


HARD_PER_CATEGORY = 12
HARD_DEV_PER_CATEGORY = 4


def build_hard() -> list[dict]:
    """Multi-step tasks (tasks/hard_tasks.py), separate seed so standard tasks never change."""
    from tasks.hard_tasks import HARD_GENERATORS

    rng = random.Random(SEED + 100)
    out: list[dict] = []
    for category in CATEGORIES:
        templates = HARD_GENERATORS[category]()
        seen: set[str] = set()
        made: list[dict] = []
        i = 0
        while len(made) < HARD_PER_CATEGORY and i < 200:
            t = templates[i % len(templates)](rng)
            i += 1
            if t["prompt"] in seen:
                continue
            seen.add(t["prompt"])
            made.append(t)
        for n, t in enumerate(made, 1):
            if isinstance(t["answer"], float) and t["answer"].is_integer() and t["check"] == "number":
                t["answer"] = int(t["answer"])
            split = "dev" if n <= HARD_DEV_PER_CATEGORY else "test"
            out.append({"id": f"{category}-h{n:02d}", "split": split, "difficulty": "hard", **t})
    return out


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    counts = {c: {f"{d}/{s}": sum(t["category"] == c and t["split"] == s and t["difficulty"] == d for t in tasks)
                  for d in ("standard", "hard") for s in ("dev", "test")} for c in CATEGORIES}
    print(f"Wrote {len(tasks)} tasks to {OUT}: {counts}")


if __name__ == "__main__":
    main()
