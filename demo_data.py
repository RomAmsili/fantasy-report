"""Generate a fake 12-team 9-cat league so you can preview the report without Yahoo access.

python demo_data.py && python report.py data/demo.json site/demo.html
"""
import json
import os
import random

random.seed(7)
CATS = [("5", "FG%", True), ("8", "FT%", True), ("11", "3PT%", True), ("10", "3PTM", True), ("12", "PTS", True),
        ("13", "OREB", True), ("15", "REB", True), ("16", "AST", True), ("17", "ST", True), ("18", "BLK", True),
        ("19", "TO", False), ("20", "A/T", True), ("27", "DD", True)]
BASE = {"5": (.475, .015), "8": (.785, .03), "11": (.360, .025), "10": (45, 9), "12": (390, 45),
        "13": (38, 7), "15": (165, 22), "16": (92, 14), "17": (28, 6), "18": (19, 5), "19": (48, 8),
        "20": (1.9, .3), "27": (5, 2)}
PCT = {"5", "8", "11", "20"}
NAMES = ["Rom's Ringers", "Tel Aviv Triples", "Jaffa Jumpers", "Brick City", "Splash Bros 2.0", "Glass Cleaners",
         "Dime Dropperz", "Swat Team", "Pick & Roll Call", "Free Throw Frenzy", "Bench Mob", "Fast Break Fam"]
N, WEEKS = 12, 6
LK = "466.l.12345"
keys = [f"{LK}.t.{i + 1}" for i in range(N)]
skill = {k: {c: random.gauss(0, 0.8) for c, _, _ in CATS} for k in keys}
skill[keys[0]].update({"10": 1.2, "16": 1.0, "5": -0.9, "18": -1.1, "17": 0.4})


def week_stats(k):
    out = {}
    for c, _, hb in CATS:
        m, s = BASE[c]
        v = m + s * (skill[k][c] * (1 if hb else 1) + random.gauss(0, 0.9))
        out[c] = (f"{v:.2f}" if c == "20" else f"{v:.3f}".lstrip("0")) if c in PCT else str(max(0, round(v)))
    return out


def schedule(w):
    ks = keys[:]
    rot = ks[1:]
    r = (w - 1) % (N - 1)
    rot = rot[r:] + rot[:r]
    ks = [ks[0]] + rot
    return [(ks[i], ks[N - 1 - i]) for i in range(N // 2)]


PLAYERS = [("Tyrese Maxey", "PG,SG"), ("Trae Young", "PG"), ("Mikal Bridges", "SG,SF"), ("Jalen Johnson", "SF,PF"),
           ("Evan Mobley", "PF,C"), ("Jarrett Allen", "C"), ("Derrick White", "PG,SG"), ("Josh Giddey", "PG,SG"),
           ("Naz Reid", "PF,C"), ("Keegan Murray", "SF,PF"), ("Herb Jones", "SF")]
my_players = []
for nm, pos in PLAYERS:
    g = random.randint(2, 3)
    big = "C" in pos
    fga = round(g * random.uniform(9, 19)); fgm = round(fga * random.uniform(.40, .60 if big else .50))
    fta = round(g * random.uniform(1, 6)); ftm = round(fta * random.uniform(.55 if big else .72, .92))
    tpa = round(g * random.uniform(0.5 if big else 4, 2 if big else 9)); tpm = round(tpa * random.uniform(.25, .42))
    tpm = min(tpm, fgm)
    st = {"10": tpm, "12": 2 * fgm + tpm + ftm, "13": round(g * random.uniform(2.5 if big else .4, 4 if big else 1.5)),
          "15": round(g * random.uniform(8 if big else 3, 12 if big else 7)),
          "16": round(g * random.uniform(1.5 if big else 3, 3 if big else 9)),
          "17": round(g * random.uniform(.5, 1.8)), "18": round(g * random.uniform(1 if big else .1, 2.5 if big else .7)),
          "19": round(g * random.uniform(1, 3.2)), "27": random.randint(0, g if big else 1)}
    my_players.append({"name": nm, "pos": pos, "games": g, "stats": {k: float(v) for k, v in st.items()},
                       "splits": {"9004003": [fgm, fga], "9007006": [ftm, fta], "9011010": [tpm, tpa]}})
tot = lambda k: sum(p["stats"][k] for p in my_players)
spl = lambda k: [sum(p["splits"][k][i] for p in my_players) for i in (0, 1)]
mine = {k: str(int(tot(k))) for k in ("10", "12", "13", "15", "16", "17", "18", "19", "27")}
for c, k in (("5", "9004003"), ("8", "9007006"), ("11", "9011010")):
    m_, a_ = spl(k); mine[c] = f"{m_ / a_:.3f}".lstrip("0")
mine["20"] = f"{tot('16') / tot('19'):.2f}"
rec = {k: [0, 0, 0] for k in keys}
weeks = {}
for w in range(1, WEEKS + 1):
    ms = []
    for a, b in schedule(w):
        sa, sb = week_stats(a), week_stats(b)
        if w == WEEKS and keys[0] in (a, b):
            if a == keys[0]: sa = mine
            else: sb = mine
        wa = wb = 0
        for c, _, hb in CATS:
            x, y = float(sa[c]), float(sb[c])
            if x == y:
                continue
            if (x > y) == hb:
                wa += 1
            else:
                wb += 1
        tie = len(CATS) - wa - wb
        rec[a][0] += wa; rec[a][1] += wb; rec[a][2] += tie
        rec[b][0] += wb; rec[b][1] += wa; rec[b][2] += tie
        ms.append({"status": "postevent", "winner": a if wa > wb else b if wb > wa else None, "tied": wa == wb,
                   "teams": [a, b], "stats": {a: sa, b: sb}, "points": {a: str(wa), b: str(wb)}})
    weeks[str(w)] = ms

order = sorted(keys, key=lambda k: -(rec[k][0] + rec[k][2] / 2) / max(1, sum(rec[k])))
teams = {k: {"name": NAMES[i], "logo": None, "manager": f"mgr{i}", "rank": str(order.index(k) + 1),
             "wins": str(rec[k][0]), "losses": str(rec[k][1]), "ties": str(rec[k][2]),
             "pct": f"{(rec[k][0] + rec[k][2] / 2) / sum(rec[k]):.3f}", "points_for": None}
         for i, k in enumerate(keys)}
up = [{"status": "preevent", "winner": None, "tied": False, "teams": [a, b], "stats": {}, "points": {}}
      for a, b in schedule(WEEKS + 1)]
data = {"league": {"league_key": LK, "name": "Demo League (fake data)", "season": "2026", "scoring_type": "head",
                   "num_teams": str(N), "current_week": str(WEEKS + 1), "start_week": "1", "end_week": "22",
                   "is_finished": "0", "url": ""},
        "my_team": keys[0], "categories": [{"id": c, "name": n, "higher_better": hb} for c, n, hb in CATS],
        "teams": teams, "weeks": weeks, "upcoming": {"week": WEEKS + 1, "matchups": up},
        "display_stats": [{"id": "9004003", "name": "FGM/FGA"}, {"id": "9007006", "name": "FTM/FTA"},
                          {"id": "9011010", "name": "3PTM/3PTA"}],
        "my_players": {"week": str(WEEKS), "players": my_players},
        "fetched_at": "2026-11-02 10:17 UTC"}
os.makedirs("data", exist_ok=True)
json.dump(data, open("data/demo.json", "w"), indent=1)
print("wrote data/demo.json")
