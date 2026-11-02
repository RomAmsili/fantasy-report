"""Turn data/league.json into site/index.html.

Usage: python report.py [path/to/league.json] [out.html]
"""
import html
import json
import math
import os
import statistics as st
import sys


# ---------------------------------------------------------------- helpers
def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def fmt(v, cat_name):
    if v is None:
        return "–"
    if "%" in cat_name:
        return f"{v:.3f}".lstrip("0") if v < 1 else f"{v:.3f}"
    if abs(v - round(v)) < 1e-9:
        return f"{v:.0f}"
    return f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}"


def e(s):
    return html.escape(str(s if s is not None else ""))


def cmp(a, b, hb):
    """+1 a wins, -1 b wins, 0 tie/unknown."""
    if a is None or b is None or a == b:
        return 0
    return 1 if (a > b) == hb else -1


def rank_of(value, values, hb):
    vals = [v for v in values if v is not None]
    if value is None:
        return None
    better = sum(1 for v in vals if (v > value if hb else v < value))
    return better + 1


# ---------------------------------------------------------------- analysis
def analyze(d):
    me = d["my_team"]
    cats = d["categories"]
    teams = d["teams"]
    points_league = "point" in (d["league"].get("scoring_type") or "")
    weeks = sorted(d["weeks"], key=int)

    # W[w][team][cat] = value ; P[w][team] = points ; opp[w][team] = opponent ; res[w][team]
    W, P, OPP, RES = {}, {}, {}, {}
    for w in weeks:
        W[w], P[w], OPP[w], RES[w] = {}, {}, {}, {}
        for m in d["weeks"][w]:
            for k in m["teams"]:
                W[w][k] = {c["id"]: num(m["stats"].get(k, {}).get(c["id"])) for c in cats}
                P[w][k] = num(m["points"].get(k))
            if len(m["teams"]) == 2:
                a, b = m["teams"]
                OPP[w][a], OPP[w][b] = b, a
                for k in (a, b):
                    RES[w][k] = "T" if m["tied"] else ("W" if m["winner"] == k else "L")

    def head2head(w, a, b):
        """(wins, losses, ties) for a vs b in week w (categories, or points)."""
        if points_league:
            r = cmp(P[w].get(a), P[w].get(b), True)
            return (r == 1, r == -1, r == 0)
        wi = lo = ti = 0
        for c in cats:
            r = cmp(W[w][a][c["id"]], W[w][b][c["id"]], c["higher_better"])
            wi += r == 1
            lo += r == -1
            ti += r == 0
        return wi, lo, ti

    # all-play per week
    AP = {}          # AP[w][team] = [W, L, T] matchup-level
    VS = {}          # VS[w][other] = (cw, cl, ct) me vs other
    for w in weeks:
        AP[w] = {}
        ks = list(W[w])
        for a in ks:
            rec = [0, 0, 0]
            for b in ks:
                if a == b:
                    continue
                wi, lo, _ = head2head(w, a, b)
                rec[0 if wi > lo else 1 if lo > wi else 2] += 1
            AP[w][a] = rec
        if me in W[w]:
            VS[w] = {b: head2head(w, me, b) for b in ks if b != me}

    def ap_pct(rec):
        n = sum(rec)
        return (rec[0] + 0.5 * rec[2]) / n if n else None

    season_ap = {}
    for k in teams:
        tot = [0, 0, 0]
        for w in weeks:
            for i, x in enumerate(AP[w].get(k, [0, 0, 0])):
                tot[i] += x
        season_ap[k] = tot

    # weekly category ranks for me
    rank_hist = {c["id"]: {} for c in cats}
    for w in weeks:
        if me not in W[w]:
            continue
        for c in cats:
            vals = [W[w][k][c["id"]] for k in W[w]]
            rank_hist[c["id"]][w] = rank_of(W[w][me][c["id"]], vals, c["higher_better"])

    # season & recent averages per team per category
    def avg_over(k, cid, ws):
        return mean([W[w][k][cid] for w in ws if k in W[w]])

    recent = weeks[-3:]
    season_avg = {k: {c["id"]: avg_over(k, c["id"], weeks) for c in cats} for k in teams}
    recent_avg = {k: {c["id"]: avg_over(k, c["id"], recent) for c in cats} for k in teams}
    weekly_sd = {}
    for c in cats:
        vals = [W[w][k][c["id"]] for w in weeks for k in W[w] if W[w][k][c["id"]] is not None]
        weekly_sd[c["id"]] = st.pstdev(vals) if len(vals) > 1 else None

    profile = []
    for c in cats:
        cid, hb = c["id"], c["higher_better"]
        vals = [season_avg[k][cid] for k in teams if season_avg[k][cid] is not None]
        mine = season_avg[me][cid]
        sd = st.pstdev(vals) if len(vals) > 1 else 0
        z = ((mine - st.mean(vals)) / sd * (1 if hb else -1)) if (mine is not None and sd) else 0
        profile.append({"cat": c, "mine": mine, "league": st.mean(vals) if vals else None,
                        "rank": rank_of(mine, vals, hb), "z": z,
                        "best": (max if hb else min)(vals) if vals else None})

    # last completed week detail
    last = weeks[-1] if weeks else None
    lastweek = None
    if last and me in W[last]:
        opp = OPP[last].get(me)
        rows = []
        for c in cats:
            cid = c["id"]
            vals = [W[last][k][cid] for k in W[last]]
            mv = W[last][me][cid]
            ov = W[last][opp][cid] if opp else None
            r = cmp(mv, ov, c["higher_better"])
            rows.append({"cat": c, "mine": mv, "opp": ov, "res": "W" if r == 1 else "L" if r == -1 else "T",
                         "league": mean(vals), "rank": rank_of(mv, vals, c["higher_better"])})
        lastweek = {"week": last, "opp": opp, "rows": rows, "result": RES[last].get(me),
                    "score": head2head(last, me, opp) if opp else None,
                    "ap": AP[last][me], "ap_rank": rank_of(ap_pct(AP[last][me]),
                                                           [ap_pct(AP[last][k]) for k in AP[last]], True),
                    "points": (P[last].get(me), P[last].get(opp))}

    # upcoming opponent preview
    preview = None
    up = d.get("upcoming")
    if up:
        for m in up["matchups"]:
            if me in m["teams"] and len(m["teams"]) == 2:
                opp = [k for k in m["teams"] if k != me][0]
                rows, exp = [], 0.0
                for c in cats:
                    cid, hb = c["id"], c["higher_better"]
                    blend = lambda k: mean([season_avg[k][cid], recent_avg[k][cid]])
                    mv, ov = blend(me), blend(opp)
                    sd = weekly_sd[cid]
                    if mv is None or ov is None or not sd:
                        p = 0.5
                    else:
                        p = phi((mv - ov) * (1 if hb else -1) / (sd * math.sqrt(2)))
                    exp += p
                    rows.append({"cat": c, "mine_season": season_avg[me][cid], "opp_season": season_avg[opp][cid],
                                 "mine_recent": recent_avg[me][cid], "opp_recent": recent_avg[opp][cid], "p": p})
                preview = {"week": up["week"], "opp": opp, "rows": rows, "expected": exp}
                # their profile: league rank per category
                for r in rows:
                    cid, hb = r["cat"]["id"], r["cat"]["higher_better"]
                    vals = [season_avg[k][cid] for k in teams]
                    r["opp_rank"] = rank_of(season_avg[opp][cid], vals, hb)
                    r["my_rank"] = rank_of(season_avg[me][cid], vals, hb)
                if points_league:
                    mp = mean([P[w].get(me) for w in weeks])
                    op = mean([P[w].get(opp) for w in weeks])
                    sdp = st.pstdev([P[w][k] for w in weeks for k in P[w] if P[w][k] is not None] or [0, 0])
                    preview["points"] = (mp, op, phi((mp - op) / (sdp * math.sqrt(2))) if sdp and mp and op else 0.5)
                break

    # league table
    table = []
    for k, tm in teams.items():
        n = sum(season_ap[k])
        table.append({"key": k, "team": tm, "ap": season_ap[k], "ap_pct": ap_pct(season_ap[k]),
                      "last_ap": AP[last].get(k) if last else None,
                      "vs": VS.get(last, {}).get(k) if last else None, "me": k == me})
    table.sort(key=lambda r: int(r["team"]["rank"] or 99))
    ap_sorted = sorted(table, key=lambda r: -(r["ap_pct"] or 0))
    for i, r in enumerate(ap_sorted):
        r["ap_rank"] = i + 1

    # luck = actual win% - all-play win%
    my = next(r for r in table if r["me"])
    actual = num(teams[me]["pct"])
    luck = (actual - my["ap_pct"]) if (actual is not None and my["ap_pct"] is not None) else None

    return {"me": me, "weeks": weeks, "cats": cats, "teams": teams, "points_league": points_league,
            "profile": profile, "rank_hist": rank_hist, "lastweek": lastweek, "preview": preview,
            "table": table, "my_row": my, "luck": luck, "AP": AP, "RES": RES, "OPP": OPP, "W": W}


# ---------------------------------------------------------------- render
CSS = """
.viz-root{color-scheme:light;--surface-0:#f4f3ef;--surface-1:#fcfcfb;--border:#e2e1dc;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#7a7974;--good:#2a78d6;--bad:#e34948;--mid:#f0efec;--me:#2a78d61a;
--good-text:#1c5cab;--bad-text:#b73433}
@media (prefers-color-scheme:dark){.viz-root{color-scheme:dark;--surface-0:#121211;--surface-1:#1a1a19;--border:#2e2e2c;
--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--good:#3987e5;--bad:#e66767;--mid:#383835;
--me:#3987e526;--good-text:#86b6ef;--bad-text:#f09a99}}
*{box-sizing:border-box}body{margin:0}
.viz-root{background:var(--surface-0);color:var(--text-primary);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;min-height:100vh;padding:24px 16px 48px}
.wrap{max-width:980px;margin:0 auto}
h1{font-size:22px;margin:0 0 2px}h2{font-size:16px;margin:0 0 4px}.sub{color:var(--text-secondary);margin:0 0 20px}
.note{color:var(--text-muted);font-size:12px;margin:2px 0 12px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:18px 18px 14px;margin-bottom:16px;overflow-x:auto}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.tile .lbl{color:var(--text-secondary);font-size:12px}.tile .big{font-size:26px;font-weight:650;margin:2px 0}
.tile .small{color:var(--text-muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{font-size:12px;color:var(--text-secondary);font-weight:550;text-align:right;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--border);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
tr.me td{background:var(--me);font-weight:600}
.pill{display:inline-block;min-width:22px;padding:1px 7px;border-radius:999px;font-size:12px;font-weight:600;text-align:center}
.W{color:var(--good-text);background:color-mix(in oklab,var(--good) 16%,transparent)}
.L{color:var(--bad-text);background:color-mix(in oklab,var(--bad) 16%,transparent)}
.T{color:var(--text-secondary);background:var(--mid)}
.heat td.c{text-align:center;color:var(--text-primary);font-weight:550;min-width:38px}
.bars .row{display:grid;grid-template-columns:70px 1fr 120px;align-items:center;gap:10px;margin:6px 0}
.bars .track{position:relative;height:18px}.bars .axis{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--text-muted)}
.bars .bar{position:absolute;top:2px;height:14px}.bars .pos{background:var(--good);border-radius:0 4px 4px 0}
.bars .neg{background:var(--bad);border-radius:4px 0 0 4px}
.bars .meta{color:var(--text-secondary);font-size:12px}
.legend{display:flex;gap:14px;font-size:12px;color:var(--text-secondary);margin:4px 0 8px;flex-wrap:wrap}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.prob{position:relative;display:inline-block;width:90px;height:8px;background:var(--mid);border-radius:4px;vertical-align:middle;margin-right:6px}
.prob i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--good)}
.prob.lo i{background:var(--bad)}
.tag{font-size:12px;color:var(--text-secondary)}
.grid th.tn{white-space:normal;max-width:84px;min-width:64px;text-align:center;vertical-align:bottom;line-height:1.2}
.grid .you{font-weight:700;border-left:2px solid var(--text-muted);border-right:2px solid var(--text-muted)}
.grid .opp{color:var(--text-muted);font-weight:400}
.grid td.c{font-size:13px}.tot td{font-weight:650;border-top:2px solid var(--border)}
#tip{position:fixed;pointer-events:none;background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);
border-radius:8px;padding:6px 9px;font-size:12px;box-shadow:0 4px 14px #0002;display:none;z-index:9;max-width:260px}
"""

JS = """
const tip=document.getElementById('tip');
document.addEventListener('mousemove',ev=>{const t=ev.target.closest('[data-tip]');
if(!t){tip.style.display='none';return}tip.innerHTML=t.dataset.tip;tip.style.display='block';
const x=Math.min(ev.clientX+14,innerWidth-tip.offsetWidth-8);tip.style.left=x+'px';tip.style.top=(ev.clientY+14)+'px'});
"""


def heat_style(rank, n):
    if rank is None or n <= 1:
        return ""
    t = (rank - 1) / (n - 1)          # 0 best .. 1 worst
    if t <= 0.5:
        return f"background:color-mix(in oklab,var(--good) {round((0.5 - t) * 2 * 55)}%,var(--mid))"
    return f"background:color-mix(in oklab,var(--bad) {round((t - 0.5) * 2 * 55)}%,var(--mid))"


def players_section(d, a, mp):
    cats = a["cats"]
    disp = {x["name"]: x["id"] for x in d.get("display_stats", [])}
    name_to_id = {c["name"]: c["id"] for c in cats}

    def split_id(cname):  # "FG%" -> id of "FGM/FGA"
        if "%" not in cname:
            return None
        pre = cname.replace("%", "") + "M/"
        return next((i for n, i in disp.items() if n.startswith(pre)), None)

    players = [p for p in mp["players"] if p["games"] > 0]
    if not players:
        return ""
    players.sort(key=lambda p: -(p["stats"].get(name_to_id.get("PTS", "12"), 0)))

    # team totals from the players (active slots only)
    cols = []
    for c in cats:
        cid, cn = c["id"], c["name"]
        sid = split_id(cn)
        if sid:
            M = sum(p["splits"].get(sid, [0, 0])[0] for p in players)
            A = sum(p["splits"].get(sid, [0, 0])[1] for p in players)
            cols.append({"c": c, "kind": "pct", "sid": sid, "team": M / A if A else None})
        elif cn in ("A/T", "AST/TO") and "16" in name_to_id.values() and "19" in name_to_id.values():
            cols.append({"c": c, "kind": "ratio", "team": None})
        elif "%" in cn or "/" in cn:
            cols.append({"c": c, "kind": "plain", "team": None})
        else:
            cols.append({"c": c, "kind": "count", "team": sum(p["stats"].get(cid, 0) for p in players)})
    # scale for % impact
    for col in cols:
        if col["kind"] == "pct" and col["team"] is not None:
            imps = [abs(p["splits"].get(col["sid"], [0, 0])[0] - col["team"] * p["splits"].get(col["sid"], [0, 0])[1])
                    for p in players]
            col["imp_max"] = max(imps + [1e-9])

    h = [f"<div class='card'><h2>Your players, week {mp['week']}</h2>"
         "<p class='note'>Only games where the player was in your starting lineup count. Bench and IL days are left out. "
         "For counting stats, darker blue means a bigger share of your team's total. For turnovers, darker red means more of them. "
         "For percentages, blue means the player raised your team %, red means he dragged it down, weighted by how many shots he took. "
         "Hover a cell for the details.</p>"
         "<table class='heat grid'><tr><th>Player</th><th>GP</th>"
         + "".join(f"<th style='text-align:center'>{e(col['c']['name'])}</th>" for col in cols) + "</tr>"]
    for p in players:
        h.append(f"<tr><td>{e(p['name'])} <span class='tag'>{e(p.get('pos') or '')}</span></td><td class='c'>{p['games']}</td>")
        for col in cols:
            c, cid, kind = col["c"], col["c"]["id"], col["kind"]
            style, tip, val = "", "", "–"
            if kind == "count":
                v = p["stats"].get(cid, 0)
                val = fmt(v, c["name"])
                share = v / col["team"] if col["team"] else 0
                var = "--good" if c["higher_better"] else "--bad"
                style = f"background:color-mix(in oklab,var({var}) {min(70, round(share * 140))}%,var(--mid))"
                tip = f"{e(p['name'])}: {val} {e(c['name'])} ({share * 100:.0f}% of your team)"
            elif kind == "pct":
                m_, a_ = p["splits"].get(col["sid"], [0, 0])
                if a_:
                    val = fmt(m_ / a_, c["name"])
                    imp = m_ - (col["team"] or 0) * a_
                    pctg = min(60, round(abs(imp) / col["imp_max"] * 60))
                    var = "--good" if imp >= 0 else "--bad"
                    style = f"background:color-mix(in oklab,var({var}) {pctg}%,var(--mid))"
                    tip = (f"{e(p['name'])}: {m_:.0f}/{a_:.0f} ({val}). "
                           f"{'+' if imp >= 0 else ''}{imp:.1f} makes vs. your team average on the same shots")
            elif kind == "ratio":
                ast, to = p["stats"].get("16", 0), p["stats"].get("19", 0)
                val = fmt(ast / to, c["name"]) if to else ("–" if not ast else "∞")
                tip = f"{e(p['name'])}: {ast:.0f} AST / {to:.0f} TO"
            else:
                v = p["stats"].get(cid)
                val = fmt(v, c["name"]) if v is not None else "–"
            h.append(f"<td class='c' style='{style}' data-tip=\"{tip}\">{val}</td>")
        h.append("</tr>")
    # totals row: official team numbers for the week
    tw = a["W"].get(mp["week"], {}).get(a["me"], {})
    h.append("<tr class='tot'><td>Team total</td><td class='c'>" + str(sum(p["games"] for p in players)) + "</td>"
             + "".join(f"<td class='c'>{fmt(tw.get(col['c']['id']), col['c']['name'])}</td>" for col in cols) + "</tr>")
    h.append("</table><p class='note'>The team total row shows Yahoo's official numbers. Stat corrections can make them differ slightly from the sum of the rows.</p></div>")
    return "".join(h)


def rec(r):
    if not r:
        return "–"
    return f"{r[0]}-{r[1]}" + (f"-{r[2]}" if r[2] else "")


def render(d, a):
    T = a["teams"]
    name = lambda k: e(T[k]["name"]) if k in T else "?"
    n = len(T)
    me = a["me"]
    L = d["league"]
    out = []
    out.append(f"<h1>{e(T[me]['name'])}</h1><p class='sub'>{e(L['name'])} · {e(L['season'])} season · "
               f"{len(a['weeks'])} weeks played · updated {e(d['fetched_at'])}</p>")

    # tiles
    lw, my = a["lastweek"], a["my_row"]
    tiles = [("League standing", f"{T[me]['rank']}<span style='font-size:15px;color:var(--text-muted)'> / {n}</span>",
              f"Record {T[me]['wins']}-{T[me]['losses']}-{T[me]['ties']}")]
    if lw:
        sc = lw["score"]
        res = {"W": "Won", "L": "Lost", "T": "Tied"}.get(lw["result"], "–")
        tiles.append((f"Week {lw['week']} result", f"{res} {sc[0]}-{sc[1]}" + (f"-{sc[2]}" if sc[2] else ""),
                      f"vs {name(lw['opp'])}"))
        tiles.append((f"Week {lw['week']} vs everyone", rec(lw["ap"]),
                      f"#{lw['ap_rank']} of {n} teams if you played all of them"))
    tiles.append(("Season vs everyone", f"{(my['ap_pct'] or 0) * 100:.0f}%",
                  f"#{my['ap_rank']} of {n} · record {rec(my['ap'])}"))
    if a["luck"] is not None:
        l = a["luck"] * 100
        tiles.append(("Luck", f"{l:+.0f}%",
                      "Your real win % minus your win % vs everyone. Above zero means the schedule helped you."))
    out.append("<div class='tiles'>" + "".join(
        f"<div class='tile'><div class='lbl'>{x}</div><div class='big'>{y}</div><div class='small'>{z}</div></div>"
        for x, y, z in tiles) + "</div>")

    # next opponent
    p = a["preview"]
    if p:
        opp = p["opp"]
        fav = sum(r["p"] >= 0.6 for r in p["rows"])
        dog = sum(r["p"] <= 0.4 for r in p["rows"])
        toss = len(p["rows"]) - fav - dog
        h = [f"<div class='card'><h2>Next up: week {p['week']} vs {name(opp)}</h2>"
             f"<p class='note'>{name(opp)} is #{T[opp]['rank']} in the standings ({T[opp]['wins']}-{T[opp]['losses']}-{T[opp]['ties']}). "
             f"You're favored in <b>{fav}</b> categories, they're favored in <b>{dog}</b>, and <b>{toss}</b> are toss-ups. "
             f"Expected categories won: <b>{p['expected']:.1f}</b> of {len(p['rows'])}.</p>"]
        if a["points_league"] and p.get("points"):
            mp, op, pr = p["points"]
            h.append(f"<p class='note'>Avg points/week: you {mp:.1f} vs them {op:.1f}. Rough win chance {pr * 100:.0f}%.</p>")
        h.append("<table><tr><th>Category</th><th>You (season)</th><th>Them (season)</th><th>You (last 3)</th>"
                 "<th>Them (last 3)</th><th>Your rank</th><th>Their rank</th><th style='text-align:left'>Your win chance</th><th style='text-align:left'>What to do</th></tr>")
        for r in sorted(p["rows"], key=lambda r: abs(r["p"] - 0.5)):
            c = r["cat"]
            pr = r["p"]
            todo = ("Toss-up: stream for it" if 0.4 < pr < 0.6 else
                    "Lean you: protect it" if 0.6 <= pr < 0.8 else
                    "Safe" if pr >= 0.8 else
                    "Long shot: consider punting" if pr <= 0.2 else "Lean them: push if cheap")
            low = " lo" if pr < 0.5 else ""
            h.append(f"<tr><td>{e(c['name'])}{'' if c['higher_better'] else ' <span class=tag>(lower wins)</span>'}</td>"
                     f"<td>{fmt(r['mine_season'], c['name'])}</td><td>{fmt(r['opp_season'], c['name'])}</td>"
                     f"<td>{fmt(r['mine_recent'], c['name'])}</td><td>{fmt(r['opp_recent'], c['name'])}</td>"
                     f"<td>#{r['my_rank']}</td><td>#{r['opp_rank']}</td>"
                     f"<td style='text-align:left' data-tip='Rough estimate from season and last-3-week averages'>"
                     f"<span class='prob{low}'><i style='width:{pr * 100:.0f}%'></i></span>{pr * 100:.0f}%</td>"
                     f"<td style='text-align:left' class='tag'>{todo}</td></tr>")
        h.append("</table><p class='note'>Sorted with the closest categories first, since those are where lineup moves matter most. "
                 "Doesn't account for injuries or how many games each team plays that week.</p></div>")
        out.append("".join(h))

    # last week detail
    if lw:
        h = [f"<div class='card'><h2>Week {lw['week']}: you vs {name(lw['opp'])}</h2>"
             f"<p class='note'>Your rank shows where your number placed among all {n} teams that week.</p>"
             "<table><tr><th>Category</th><th>You</th><th>Them</th><th>Result</th><th>League avg</th><th>Your rank</th></tr>"]
        for r in lw["rows"]:
            c = r["cat"]
            h.append(f"<tr><td>{e(c['name'])}</td><td>{fmt(r['mine'], c['name'])}</td><td>{fmt(r['opp'], c['name'])}</td>"
                     f"<td><span class='pill {r['res']}'>{r['res']}</span></td><td>{fmt(r['league'], c['name'])}</td>"
                     f"<td><span class='pill' style='{heat_style(r['rank'], n)}'>{r['rank'] or '–'}</span></td></tr>")
        h.append("</table></div>")
        out.append("".join(h))


    # last week: you vs every team, category by category
    if lw:
        w = lw["week"]
        others = [r["key"] for r in a["table"] if r["key"] != me and r["key"] in a["W"][w]]
        h = [f"<div class='card'><h2>Week {w}: you vs every team</h2>"
             "<p class='note'>Each cell is that team's number in that category last week. The color shows whether you would have beaten them. "
             "Look across a row to see how good your number really was. Look down a column to see how you'd have done against that team.</p>"
             "<div class='legend'><span><span class='sw' style='background:color-mix(in oklab,var(--good) 45%,var(--mid))'></span>You beat them</span>"
             "<span><span class='sw' style='background:color-mix(in oklab,var(--bad) 45%,var(--mid))'></span>They beat you</span>"
             "<span><span class='sw' style='background:var(--mid)'></span>Tie</span></div>"
             "<table class='heat grid'><tr><th>Category</th><th class='you'>You</th>"]
        for k in others:
            star = " <span class='opp'>(opp)</span>" if k == lw["opp"] else ""
            h.append(f"<th class='tn'>{name(k)}{star}</th>")
        h.append("</tr>")
        for c in a["cats"]:
            cid, hb = c["id"], c["higher_better"]
            mv = a["W"][w][me][cid]
            h.append(f"<tr><td>{e(c['name'])}{'' if hb else ' <span class=tag>(low)</span>'}</td><td class='c you'>{fmt(mv, c['name'])}</td>")
            for k in others:
                ov = a["W"][w][k][cid]
                r = cmp(mv, ov, hb)
                bg = ("color-mix(in oklab,var(--good) 45%,var(--mid))" if r == 1 else
                      "color-mix(in oklab,var(--bad) 45%,var(--mid))" if r == -1 else "var(--mid)")
                verdict = "you win" if r == 1 else "they win" if r == -1 else "tie"
                h.append(f"<td class='c' style='background:{bg}' data-tip='{e(c['name'])}: you {fmt(mv, c['name'])}, "
                         f"{name(k)} {fmt(ov, c['name'])}, {verdict}'>{fmt(ov, c['name'])}</td>")
            h.append("</tr>")
        h.append("<tr class='tot'><td>Your score</td><td></td>")
        for k in others:
            vs = next((r["vs"] for r in a["table"] if r["key"] == k), None)
            kk = "W" if vs and vs[0] > vs[1] else "L" if vs and vs[1] > vs[0] else "T"
            h.append(f"<td class='c'><span class='pill {kk}'>{rec(vs)}</span></td>")
        h.append("</tr></table></div>")
        out.append("".join(h))

    # my players' contributions
    mp = d.get("my_players")
    if mp and mp.get("players"):
        out.append(players_section(d, a, mp))

    # season strengths
    prof = sorted(a["profile"], key=lambda r: -r["z"])
    zmax = max([abs(r["z"]) for r in prof] + [1.5])
    h = ["<div class='card'><h2>Season strengths and weaknesses</h2>"
         "<p class='note'>Each bar shows how far your weekly average is from the league average, measured against how spread out the teams are. "
         "Right means a strength, left means a weakness. The rank is among all teams.</p>"
         "<div class='legend'><span><span class='sw' style='background:var(--good)'></span>Better than league avg</span>"
         "<span><span class='sw' style='background:var(--bad)'></span>Worse than league avg</span></div><div class='bars'>"]
    for r in prof:
        c, z = r["cat"], r["z"]
        w = abs(z) / zmax * 50
        cls, left = ("pos", 50) if z >= 0 else ("neg", 50 - w)
        tip = (f"<b>{e(c['name'])}</b><br>You: {fmt(r['mine'], c['name'])} / week<br>League avg: {fmt(r['league'], c['name'])}"
               f"<br>Best team: {fmt(r['best'], c['name'])}<br>Rank #{r['rank']} of {n}")
        h.append(f"<div class='row' data-tip=\"{tip}\"><div>{e(c['name'])}</div><div class='track'><div class='axis'></div>"
                 f"<div class='bar {cls}' style='left:{left:.1f}%;width:{max(w, .6):.1f}%'></div></div>"
                 f"<div class='meta'>#{r['rank']} · {fmt(r['mine'], c['name'])}/wk</div></div>")
    h.append("</div></div>")
    out.append("".join(h))

    # rank heatmap by week
    weeks = a["weeks"]
    if weeks:
        h = ["<div class='card'><h2>Your category rank, week by week</h2>"
             f"<p class='note'>1 is best of {n}. Blue means near the top, red means near the bottom. The bottom row is your actual result that week.</p>"
             "<table class='heat'><tr><th>Category</th>" + "".join(f"<th style='text-align:center'>W{w}</th>" for w in weeks) + "</tr>"]
        for c in a["cats"]:
            h.append(f"<tr><td>{e(c['name'])}</td>")
            for w in weeks:
                rk = a["rank_hist"][c["id"]].get(w)
                h.append(f"<td class='c' style='{heat_style(rk, n)}' data-tip='{e(c['name'])}, week {w}: #{rk or '–'} of {n}'>{rk or '–'}</td>")
            h.append("</tr>")
        h.append("<tr><td>Result</td>" + "".join(
            f"<td class='c' data-tip='vs {name(a['OPP'][w].get(me))}'><span class='pill {a['RES'][w].get(me, 'T')}'>{a['RES'][w].get(me, '–')}</span></td>"
            for w in weeks) + "</tr></table></div>")
        out.append("".join(h))

    # league table
    lab = f"W{lw['week']}" if lw else ""
    h = ["<div class='card'><h2>Where you stand</h2>"
         "<p class='note'>The 'vs everyone' columns show how each team would do if it played every other team every week. "
         f"That takes schedule luck out of the picture. 'You vs them' is your category score against each team in {lab}.</p>"
         "<table><tr><th>#</th><th style='text-align:left'>Team</th><th>Record</th><th>Season vs everyone</th><th>vs everyone rank</th>"
         f"<th>{lab} vs everyone</th><th>You vs them ({lab})</th></tr>"]
    for r in a["table"]:
        tm = r["team"]
        vs = r["vs"]
        if vs:
            k = "W" if vs[0] > vs[1] else "L" if vs[1] > vs[0] else "T"
            vs_html = f"<span class='pill {k}'>{rec(vs)}</span>"
        else:
            vs_html = "–"
        h.append(f"<tr class='{'me' if r['me'] else ''}'><td>{e(tm['rank'])}</td><td style='text-align:left'>{e(tm['name'])}</td>"
                 f"<td>{e(tm['wins'])}-{e(tm['losses'])}-{e(tm['ties'])}</td><td>{(r['ap_pct'] or 0) * 100:.0f}%</td>"
                 f"<td>{r['ap_rank']}</td><td>{rec(r['last_ap'])}</td><td>{vs_html}</td></tr>")
    h.append("</table></div>")
    out.append("".join(h))

    return ("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{e(T[me]['name'])} · weekly report</title><style>{CSS}</style></head><body><div class='viz-root'><div class='wrap'>"
            + "".join(out) + f"</div></div><div id='tip'></div><script>{JS}</script></body></html>")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/league.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "site/index.html"
    with open(src) as f:
        d = json.load(f)
    if not d["weeks"]:
        html_out = "<!DOCTYPE html><meta charset='utf-8'><p style='font-family:system-ui;padding:24px'>No completed weeks yet. Check back after week 1.</p>"
    else:
        html_out = render(d, analyze(d))
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "w") as f:
        f.write(html_out)
    print(f"Wrote {dst}")


if __name__ == "__main__":
    main()
