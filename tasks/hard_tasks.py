"""Hard, multi-step benchmark templates (answers computed by code, with worked methods).

These are where a focused specialist (curated tools, worked examples, self-check) should
matter most versus a generalist with every tool: each needs 2+ dependent steps, has an
off-by-one or near-miss trap, or needs a precise final transformation.
"""

from __future__ import annotations

import calendar
import re

from bloom.tools import dates, stats, units
from tasks import local_db as sql
from tasks.build_benchmark import BD, DIAGNOSES, MONTHS, SCHEMA_DESCRIPTION, WARDS, _mk, _nums, _rand_date

P_SQL = f"You have access to Hospital A's patient records. {SCHEMA_DESCRIPTION} "
MONTH_NAMES = list(calendar.month_name)


def _rows(q: str):
    return sql.query(q)[1]


def _daily_admissions(ym: str) -> list[tuple[str, int]]:
    return _rows(f"SELECT admit_date, COUNT(*) FROM admissions WHERE admit_date LIKE '{ym}%' GROUP BY admit_date ORDER BY admit_date")


# ── SQL ────────────────────────────────────────────────────────────────────
def sql_hard():
    def largest_drop(rng):
        q = ("SELECT ward, AVG(CASE WHEN protocol='old' THEN readmitted_30d END) AS old_rate, "
             "AVG(CASE WHEN protocol='new' THEN readmitted_30d END) AS new_rate FROM admissions GROUP BY ward")
        rows = _rows(q)
        best = max(rows, key=lambda r: r[1] - r[2])
        rng.random()  # keep the rng stream stable
        return _mk("sql", P_SQL + "Which ward had the largest drop (in percentage points) in 30-day readmission rate "
                   "from the old to the new discharge protocol? Answer with the ward name.", best[0], "exact",
                   how=f'run_sql(query="{q}") -> per-ward old/new rates; largest old-new difference -> {best[0]} '
                       f"({100 * (best[1] - best[2]):.2f} pts)")

    def busy_days(rng):
        m = rng.randint(1, 6)
        daily = _daily_admissions(f"2026-{m:02d}")
        avg = sum(n for _, n in daily) / len(daily)
        k = sum(1 for _, n in daily if n > avg)
        return _mk("sql", P_SQL + f"On how many days in {MONTHS[m]} 2026 did admissions exceed that month's average "
                   "admissions per day (counting only days with at least one admission)?", k, "number", {"abs": 0},
                   how=f"run_sql(admissions per admit_date in {MONTHS[m]}) -> {len(daily)} days, mean {avg:.3f}; "
                       f"count days above -> {k}")

    def older_effect(rng):
        age = rng.choice([65, 70])
        q = (f"SELECT a.protocol, AVG(a.readmitted_30d) FROM admissions a JOIN patients p ON p.patient_id = a.patient_id "
             f"WHERE p.age >= {age} GROUP BY a.protocol")
        rates = dict(_rows(q))
        ans = round(100 * (rates["new"] - rates["old"]), 2)
        return _mk("sql", P_SQL + f"For patients aged {age} or older, what is the new-protocol 30-day readmission rate "
                   "minus the old-protocol rate, in percentage points? Round to 2 decimals.", ans, "number", {"abs": 0.02},
                   how=f'run_sql(query="{q}") -> old {rates["old"]:.5f}, new {rates["new"]:.5f}; 100*(new-old) -> {ans}')

    def los_readmitted(rng):
        q = ("SELECT diagnosis FROM admissions WHERE readmitted_30d = 1 GROUP BY diagnosis "
             "ORDER BY AVG(length_of_stay) DESC LIMIT 1")
        ans = _rows(q)[0][0]
        rng.random()
        return _mk("sql", P_SQL + "Among admissions that were readmitted within 30 days, which diagnosis had the longest "
                   "average length of stay? Answer with the diagnosis.", ans, "exact", how=f'run_sql(query="{q}") -> {ans}')

    def busiest_day(rng):
        m = rng.randint(1, 6)
        q = (f"SELECT admit_date, COUNT(*) AS n FROM admissions WHERE admit_date LIKE '2026-{m:02d}%' "
             "GROUP BY admit_date ORDER BY n DESC, admit_date LIMIT 1")
        d, n = _rows(q)[0]
        return _mk("sql", P_SQL + f"Which date in {MONTHS[m]} 2026 had the most admissions (earliest date if tied)? "
                   "Answer as YYYY-MM-DD.", d, "date", how=f'run_sql(query="{q}") -> {d} ({n} admissions)')

    def long_stays(rng):
        ward, days = rng.choice(WARDS), rng.choice([6, 7, 8])
        q = (f"SELECT AVG(CASE WHEN length_of_stay >= {days} THEN 1.0 ELSE 0 END) FROM admissions WHERE ward='{ward}'")
        ans = round(100 * _rows(q)[0][0], 1)
        return _mk("sql", P_SQL + f"What percentage of {ward} admissions stayed {days} or more days? Round to 1 decimal.",
                   ans, "number", {"abs": 0.1}, how=f'run_sql(query="{q}") -> {ans / 100:.4f} -> {ans}%')

    return [largest_drop, busy_days, older_effect, los_readmitted, busiest_day, long_stays]


# ── stats ──────────────────────────────────────────────────────────────────
def stats_hard():
    def cv(rng):
        v = _nums(rng, rng.randint(20, 30), rng.uniform(40, 90), rng.uniform(5, 15))
        d = stats.describe(v)
        ans = round(100 * d["stdev"] / d["mean"], 2)
        return _mk("stats", f"What is the coefficient of variation (sample standard deviation divided by the mean, "
                   f"as a percentage) of: {v}? Round to 2 decimals.", ans, "number", {"abs": 0.02},
                   how=f"describe(values) -> stdev={d['stdev']:.5f}, mean={d['mean']:.5f}; "
                       f"calculate(100*stdev/mean) -> {100 * d['stdev'] / d['mean']:.4f}")

    def zmax(rng):
        v = _nums(rng, rng.randint(18, 28), 100, 15)
        d = stats.describe(v)
        z = (d["max"] - d["mean"]) / d["stdev"]
        return _mk("stats", f"Using the sample standard deviation, what is the z-score of the largest value in: {v}? "
                   "Round to 3 decimals.", round(z, 3), "number", {"abs": 0.002},
                   how=f"describe(values) -> max={d['max']}, mean={d['mean']:.5f}, stdev={d['stdev']:.5f}; "
                       f"calculate((max-mean)/stdev) -> {z:.5f}")

    def predict(rng):
        xs = list(range(1, rng.randint(12, 18)))
        k, b = rng.uniform(1.5, 4.0), rng.uniform(2, 20)
        ys = [round(k * x + b + rng.gauss(0, 3), 1) for x in xs]
        x_new = rng.choice([25, 30, 40])
        lr = stats.linregress(xs, ys)
        ans = round(lr["slope"] * x_new + lr["intercept"], 2)
        return _mk("stats", f"Fit a least-squares line to x={xs}, y={ys}, then predict y at x={x_new}. "
                   "Round to 2 decimals.", ans, "number", {"abs": 0.02},
                   how=f"linregress(x, y) -> slope={lr['slope']:.5f}, intercept={lr['intercept']:.5f}; "
                       f"calculate(slope*{x_new}+intercept) -> {lr['slope'] * x_new + lr['intercept']:.4f}")

    def halves(rng):
        v = _nums(rng, 15, 50, 6) + _nums(rng, 15, 50 + rng.uniform(0, 5), 7)
        a, b = v[:15], v[15:]
        p = stats.ttest_welch(a, b)["p_value"]
        return _mk("stats", f"Split this list of 30 measurements into the first 15 and the last 15: {v}. "
                   "Run a two-sided Welch t-test comparing the two halves. What is the p-value? Round to 3 decimals.",
                   round(p, 3), "number", {"abs": 0.002},
                   how=f"a = first 15, b = last 15; ttest_welch(a, b) -> p_value={p:.6f}")

    def iqr(rng):
        v = _nums(rng, rng.randint(25, 40), 70, 12)
        q1, q3 = stats.percentile(v, 25), stats.percentile(v, 75)
        return _mk("stats", f"What is the interquartile range (Q3 minus Q1, linear interpolation like numpy's "
                   f"default) of: {v}? Round to 2 decimals.", round(q3 - q1, 2), "number", {"abs": 0.01},
                   how=f"percentile(values, 25) -> {q1:.4f}; percentile(values, 75) -> {q3:.4f}; "
                       f"calculate(q3-q1) -> {q3 - q1:.4f}")

    def outliers(rng):
        v = _nums(rng, rng.randint(25, 35), 20, 4) + [round(rng.uniform(30, 40), 1) for _ in range(rng.randint(1, 3))]
        d = stats.describe(v)
        n = sum(1 for x in v if x > d["mean"] + 1.5 * d["stdev"])
        return _mk("stats", f"How many values are more than 1.5 sample standard deviations above the mean in: {v}?",
                   n, "number", {"abs": 0},
                   how=f"describe(values) -> mean={d['mean']:.4f}, stdev={d['stdev']:.4f}; threshold "
                       f"{d['mean'] + 1.5 * d['stdev']:.4f}; count values above -> {n}")

    return [cv, zmax, predict, halves, iqr, outliers]


# ── dates ──────────────────────────────────────────────────────────────────
def _last_weekday(year: int, month: int, weekday: int) -> str:
    last = calendar.monthrange(year, month)[1]
    for day in range(last, 0, -1):
        if calendar.weekday(year, month, day) == weekday:
            return f"{year}-{month:02d}-{day:02d}"
    raise ValueError


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> str:
    days = [d for d in range(1, calendar.monthrange(year, month)[1] + 1) if calendar.weekday(year, month, d) == weekday]
    return f"{year}-{month:02d}-{days[n - 1]:02d}"


DAYNAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def dates_hard():
    def after_last_friday(rng):
        y, m, n = rng.choice([2026, 2027]), rng.randint(1, 12), rng.randint(10, 40)
        lf = _last_weekday(y, m, 4)
        ans = dates.add_business_days(lf, n)
        return _mk("dates", f"What date is {n} business days after the last Friday of {MONTH_NAMES[m]} {y}? {BD} "
                   "The start day is not counted. Answer as YYYY-MM-DD.", ans, "date",
                   how=f"last Friday of {MONTH_NAMES[m]} {y} = {lf} (check with weekday); "
                       f'add_business_days(start="{lf}", days={n}) -> {ans}')

    def since_first_monday(rng):
        m = rng.randint(1, 9)
        fm = _nth_weekday(2026, m, 0, 1)
        end = dates.add_days(fm, rng.randint(40, 150))
        ans = dates.business_days_between(fm, end)
        return _mk("dates", f"How many business days are there after the first Monday of {MONTH_NAMES[m]} 2026 up to "
                   f"and including {end}? {BD}", ans, "number", {"abs": 0},
                   how=f"first Monday = {fm}; business_days_between(start=\"{fm}\", end=\"{end}\") -> {ans}")

    def nth_weekday(rng):
        y, m = rng.choice([2026, 2027]), rng.randint(1, 12)
        wd, n = rng.randint(0, 4), rng.randint(2, 4)
        ans = _nth_weekday(y, m, wd, n)
        return _mk("dates", f"What is the date of the {ORD[n]} {DAYNAMES[wd]} of {MONTH_NAMES[m]} {y}? "
                   "Answer as YYYY-MM-DD.", ans, "date",
                   how=f"list the {DAYNAMES[wd]}s of {MONTH_NAMES[m]} {y} with weekday(); take number {n} -> {ans}")

    def net_terms(rng):
        issued, terms = _rand_date(rng, span=500), rng.choice([30, 45, 60])
        due = dates.add_days(issued, terms)
        wd = dates.weekday(due)
        ans = dates.add_days(due, {"Saturday": 2, "Sunday": 1}.get(wd, 0))
        return _mk("dates", f"An invoice is issued on {issued} with net-{terms} terms (calendar days). If the due date "
                   "falls on a Saturday or Sunday, it moves to the following Monday. What is the due date? "
                   "Answer as YYYY-MM-DD.", ans, "date",
                   how=f'add_days(start="{issued}", days={terms}) -> {due} ({wd}); roll weekend to Monday -> {ans}')

    def quarter_bdays(rng):
        y, q = rng.choice([2026, 2027]), rng.randint(1, 4)
        start = f"{y}-{3 * q - 2:02d}-01"
        end = f"{y}-{3 * q:02d}-{calendar.monthrange(y, 3 * q)[1]:02d}"
        ans = len(dates.business_days_in_range(start, end))
        return _mk("dates", f"How many business days are there in Q{q} {y} ({start} to {end} inclusive)? {BD}",
                   ans, "number", {"abs": 0},
                   how=f'business_days_in_range(start="{start}", end="{end}") -> count = {ans}')

    def full_weeks(rng):
        a = _rand_date(rng, "2025-06-01", 400)
        b = dates.add_days(a, rng.randint(100, 600))
        ans = dates.days_between(a, b) // 7
        return _mk("dates", f"How many full weeks (7-day periods) are there from {a} to {b}?", ans, "number", {"abs": 0},
                   how=f'days_between(start="{a}", end="{b}") -> {dates.days_between(a, b)}; floor divide by 7 -> {ans}')

    return [after_last_friday, since_first_monday, nth_weekday, net_terms, quarter_bdays, full_weeks]


# ── units ──────────────────────────────────────────────────────────────────
def units_hard():
    def discounted_per_oz(rng):
        kg, price, disc = rng.choice([0.5, 1.0, 1.2, 2.0]), round(rng.uniform(20, 70), 2), rng.choice([10, 15, 20, 25])
        oz = units.convert(kg, "kg", "oz")
        ans = round(price * (1 - disc / 100) / oz, 3)
        return _mk("units", f"A {kg} kg bag of beans costs ${price:.2f}, and it's on sale for {disc}% off. What is the "
                   "sale price per ounce in USD? Round to 3 decimals.", ans, "number", {"abs": 0.001},
                   how=f'convert_units({kg}, "kg", "oz") -> {oz:.5f}; calculate({price}*(1-{disc}/100)/{oz:.5f}) '
                       f"-> {price * (1 - disc / 100) / oz:.5f}")

    def recipe_scale(rng):
        g, serv, target = rng.choice([250, 300, 350, 420]), rng.choice([4, 6, 8]), rng.randint(10, 30)
        ans = round(units.convert(g * target / serv, "g", "lb"), 3)
        return _mk("units", f"A recipe for {serv} servings needs {g} g of flour. How many pounds of flour are needed "
                   f"for {target} servings? Round to 3 decimals.", ans, "number", {"abs": 0.001},
                   how=f'calculate({g}*{target}/{serv}) -> {g * target / serv:.3f} g; convert_units(..., "g", "lb") -> '
                       f"{units.convert(g * target / serv, 'g', 'lb'):.5f}")

    def temp_gap(rng):
        f, c = round(rng.uniform(33, 42), 1), round(rng.uniform(2, 9), 1)
        ans = round(c - units.convert(f, "f", "c"), 2)
        return _mk("units", f"The cold room is at {f}°F and the display case is at {c}°C. How many degrees Celsius "
                   "warmer is the display case than the cold room? Round to 2 decimals.", ans, "number", {"abs": 0.01},
                   how=f'convert_units({f}, "f", "c") -> {units.convert(f, "f", "c"):.4f}; '
                       f"calculate({c} - that) -> {c - units.convert(f, 'f', 'c'):.4f}")

    def courier_minutes(rng):
        km, mph = round(rng.uniform(5, 30), 1), rng.choice([12, 15, 18, 22, 25])
        mi = units.convert(km, "km", "mi")
        ans = round(60 * mi / mph, 1)
        return _mk("units", f"A courier rides {km} km at an average of {mph} mph. How many minutes does it take? "
                   "Round to 1 decimal.", ans, "number", {"abs": 0.1},
                   how=f'convert_units({km}, "km", "mi") -> {mi:.5f}; calculate(60*{mi:.5f}/{mph}) -> {60 * mi / mph:.3f}')

    def flooring(rng):
        w, l, per_sqft = round(rng.uniform(3, 8), 1), round(rng.uniform(3, 8), 1), round(rng.uniform(2.5, 9), 2)
        sqft = units.convert(w, "m", "ft") * units.convert(l, "m", "ft")
        ans = round(sqft * per_sqft, 2)
        return _mk("units", f"Flooring costs ${per_sqft:.2f} per square foot. What does it cost to floor a {w} m × {l} m "
                   "room? Round to 2 decimals.", ans, "number", {"abs": 0.05},
                   how=f'convert_units({w}, "m", "ft") and convert_units({l}, "m", "ft") -> area {sqft:.4f} sq ft; '
                       f"calculate(area*{per_sqft}) -> {sqft * per_sqft:.3f}")

    def cups_from_jugs(rng):
        gal, liters, cup_oz = rng.choice([1, 2, 3]), rng.choice([1.5, 2, 3]), rng.choice([8, 12, 16])
        total_floz = units.convert(gal, "gal", "floz") + units.convert(liters, "l", "floz")
        ans = int(total_floz // cup_oz)
        return _mk("units", f"How many full {cup_oz}-fluid-ounce cups can be filled from {gal} US gallon(s) plus a "
                   f"{liters} L bottle combined? Answer with a whole number.", ans, "number", {"abs": 0},
                   how=f'convert_units({gal}, "gal", "floz") + convert_units({liters}, "l", "floz") -> '
                       f"{total_floz:.3f} fl oz; floor divide by {cup_oz} -> {ans}")

    return [discounted_per_oz, recipe_scale, temp_gap, courier_minutes, flooring, cups_from_jugs]


# ── extraction ─────────────────────────────────────────────────────────────
def extraction_hard():
    def order_ids_traps(rng):
        good = [f"ORD-{rng.randint(10000, 99999)}" for _ in range(rng.randint(3, 5))]
        traps = [f"ORD-{rng.randint(100000, 999999)}", f"ord-{rng.randint(10000, 99999)}", f"ORD-{rng.randint(1000, 9999)}"]
        text = (f"Ticket mentions {good[0]}, {traps[0]} (legacy 6-digit), {good[1]} and {traps[1]}. "
                + " ".join(f"See {g}." for g in good[2:]) + f" {traps[2]} was a typo. {good[0]} again.")
        return _mk("extraction", "List every distinct valid order ID in this text. A valid ID is uppercase ORD- followed "
                   f"by exactly five digits. Comma separated: \"{text}\"", ", ".join(dict.fromkeys(good)), "set",
                   how='regex_findall(pattern="\\\\bORD-\\\\d{5}\\\\b", text=<the text>) -> excludes 6-digit, 4-digit, '
                       "and lowercase traps; dedupe")

    def emails_valid(rng):
        names = rng.sample(["ana", "ben", "chen", "dana", "eli", "gus"], 3)
        good = [f"{names[0]}@bloom.coffee", f"{names[1]}.ops@example.org", f"{names[2]}@beans.io"]
        text = (f"Reach {good[0]} or {good[1]}. Bounced: {names[0]}@bloom (no domain suffix), "
                f"{names[1]}@@example.org, @beans.io. Also {good[2]}.")
        return _mk("extraction", "Extract only the well-formed email addresses (local@domain.tld with a TLD of at least "
                   f"2 letters) from: \"{text}\" Comma separated.", ", ".join(good), "set",
                   how='regex_findall(pattern="\\\\b[\\\\w.+-]+@[\\\\w-]+(?:\\\\.[\\\\w-]+)*\\\\.[A-Za-z]{2,}\\\\b", '
                       'text=<the text>) -> drop "@@" and suffix-less addresses')

    def calendar_valid_dates(rng):
        valid = sorted({_rand_date(rng, span=360) for _ in range(3)})
        invalid = rng.sample(["2026-02-30", "2026-04-31", "2026-06-31", "2026-02-29", "2026-11-31"], 2)
        mixed = valid[:1] + invalid[:1] + valid[1:2] + invalid[1:] + valid[2:]
        text = "Shipments logged on " + ", ".join(mixed) + "."
        return _mk("extraction", "List only the real calendar dates (YYYY-MM-DD that actually exist; 2026 is not a leap "
                   f"year) in: \"{text}\" Comma separated.", ", ".join(valid), "set",
                   how='regex_findall(pattern="\\\\d{4}-\\\\d{2}-\\\\d{2}", text=<the text>) -> check each with '
                       f"weekday() (invalid dates error): drop {', '.join(invalid)}")

    def amounts_over(rng):
        amts = [round(rng.uniform(20, 900), 2) for _ in range(5)]
        limit = 100
        fmt = lambda a: f"${a:,.2f}"  # noqa: E731
        text = ("Invoice lines: " + "; ".join(f"item {i + 1} {fmt(a)}" for i, a in enumerate(amts))
                + f"; shipping USD 150; deposit 250 dollars.")
        keep = [fmt(a) for a in amts if a > limit]
        return _mk("extraction", f"List the amounts written with a $ sign that are greater than ${limit}, exactly as "
                   f"written, from: \"{text}\" Comma separated.", ", ".join(keep), "set",
                   how='regex_findall(pattern="\\\\$[\\\\d,]+\\\\.\\\\d{2}", text=<the text>) -> keep values > 100 '
                       '(ignore "USD 150" and "250 dollars")')

    def valid_times(rng):
        good = [f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}" for _ in range(3)]
        good = list(dict.fromkeys(good))
        bad = [f"{rng.randint(24, 29)}:{rng.randint(0, 59):02d}", f"{rng.randint(10, 23)}:{rng.randint(60, 99)}"]
        text = f"Deliveries at {good[0]}, {bad[0]}, " + ", ".join(good[1:]) + f" and {bad[1]} (typo)."
        return _mk("extraction", "List the valid 24-hour times (HH:MM with hour 00-23 and minute 00-59) in: "
                   f"\"{text}\" Comma separated.", ", ".join(good), "set",
                   how='regex_findall(pattern="\\\\b(?:[01]\\\\d|2[0-3]):[0-5]\\\\d\\\\b", text=<the text>) -> '
                       "rejects hour >= 24 and minute >= 60")

    def us_phones(rng):
        us = [(rng.choice([650, 415, 408]), rng.randint(200, 999), rng.randint(1000, 9999)) for _ in range(2)]
        text = (f"Call +1 {us[0][0]}-{us[0][1]}-{us[0][2]} (SF) or ({us[1][0]}) {us[1][1]}-{us[1][2]}. "
                f"London office: +44 20 {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}. Ext 5501.")
        return _mk("extraction", "Extract only the US phone numbers from this text and write each as ###-###-####, "
                   f"comma separated: \"{text}\"", ", ".join(f"{a}-{b}-{c}" for a, b, c in us), "set",
                   how='regex_findall(pattern="(?:\\\\+1 )?\\\\(?\\\\d{3}\\\\)?[ -]?\\\\d{3}-\\\\d{4}", text=<the text>) '
                       "-> normalize; skip the +44 number and the extension")

    return [order_ids_traps, emails_valid, calendar_valid_dates, amounts_over, valid_times, us_phones]


HARD_GENERATORS = {"sql": sql_hard, "stats": stats_hard, "dates": dates_hard, "units": units_hard,
                   "extraction": extraction_hard}
