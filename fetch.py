"""Pull everything the report needs from the Yahoo Fantasy API (stdlib only).

Env vars:
  YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_REFRESH_TOKEN  (required)
  YAHOO_LEAGUE_ID   (optional - the number in your league URL; needed only if you're in >1 NBA league)
  YAHOO_REDIRECT_URI (optional, default https://localhost:8080 - must match your Yahoo app)
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API = "https://fantasysports.yahooapis.com/fantasy/v2/"
REDIRECT_URI = os.environ.get("YAHOO_REDIRECT_URI", "https://localhost:8080")


def token_request(client_id, client_secret, fields):
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def access_token():
    try:
        cid = os.environ["YAHOO_CLIENT_ID"]
        sec = os.environ["YAHOO_CLIENT_SECRET"]
        ref = os.environ["YAHOO_REFRESH_TOKEN"]
    except KeyError as e:
        sys.exit(f"Missing env var {e}. See README.")
    tok = token_request(cid, sec, {"grant_type": "refresh_token",
                                   "refresh_token": ref,
                                   "redirect_uri": REDIRECT_URI})
    return tok["access_token"]


def _strip_ns(root):
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def get(tok, path):
    url = API + path
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return _strip_ns(ET.fromstring(r.read()))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 999) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            body = e.read().decode(errors="replace")[:500]
            raise RuntimeError(f"Yahoo API error {e.code} on {path}:\n{body}")


def t(el, path, default=None):
    x = el.find(path) if el is not None else None
    return x.text if x is not None and x.text is not None else default


def find_league(tok):
    root = get(tok, "users;use_login=1/games;game_keys=nba/leagues")
    leagues = [(t(l, "league_key"), t(l, "name")) for l in root.iter("league")]
    if not leagues:
        sys.exit("No NBA leagues found for this Yahoo account (this season).")
    wanted = os.environ.get("YAHOO_LEAGUE_ID", "").strip()
    if wanted:
        for k, n in leagues:
            if k.endswith(f".l.{wanted}"):
                return k
        sys.exit(f"League id {wanted} not found. Your leagues: {leagues}")
    if len(leagues) > 1:
        print(f"Several leagues found, using the first. Set YAHOO_LEAGUE_ID to choose: {leagues}")
    return leagues[0][0]


def find_my_team(tok, league_key):
    root = get(tok, "users;use_login=1/games;game_keys=nba/teams")
    for tm in root.iter("team"):
        k = t(tm, "team_key", "")
        if k.startswith(league_key + ".t."):
            return k
    sys.exit("Couldn't find your team in that league.")


def parse_matchups(root):
    out = []
    for m in root.iter("matchup"):
        mt = {"status": t(m, "status"), "winner": t(m, "winner_team_key"),
              "week_start": t(m, "week_start"), "week_end": t(m, "week_end"),
              "tied": t(m, "is_tied") == "1", "teams": [], "stats": {}, "points": {}}
        for tm in m.findall("teams/team"):
            k = t(tm, "team_key")
            mt["teams"].append(k)
            mt["stats"][k] = {t(s, "stat_id"): t(s, "value") for s in tm.findall("team_stats/stats/stat")}
            mt["points"][k] = t(tm, "team_points/total")
        out.append(mt)
    return out


BENCH = {"BN", "IL", "IL+", "NA"}


def fetch_my_players(tok, me, week, matchups):
    """Sum each player's stats over the days he was in an active lineup slot."""
    import datetime as dt
    m = next(x for x in matchups if me in x["teams"])
    day = dt.date.fromisoformat(m["week_start"])
    end = dt.date.fromisoformat(m["week_end"])
    players = {}
    while day <= end:
        ds = day.isoformat()
        root = get(tok, f"team/{me}/roster;date={ds}/players/stats;type=date;date={ds}")
        for pl in root.iter("player"):
            pk = t(pl, "player_key")
            p = players.setdefault(pk, {"name": t(pl, "name/full"),
                                        "pos": t(pl, "display_position"),
                                        "games": 0, "stats": {}, "splits": {}})
            if t(pl, "selected_position/position") in BENCH:
                continue
            played = False
            for s in pl.findall("player_stats/stats/stat"):
                sid, v = t(s, "stat_id"), t(s, "value")
                if v is None or v.strip() in ("", "-"):
                    continue
                if "/" in v:
                    a, b = v.split("/", 1)
                    try:
                        mk, at = float(a), float(b)
                    except ValueError:
                        continue
                    acc = p["splits"].setdefault(sid, [0.0, 0.0])
                    acc[0] += mk
                    acc[1] += at
                    played = played or at > 0
                    continue
                try:
                    x = float(v)
                except ValueError:
                    continue
                p["stats"][sid] = p["stats"].get(sid, 0.0) + x
                played = True
            p["games"] += played
        day += dt.timedelta(days=1)
    return {"week": week, "players": list(players.values())}


def fetch_all():
    tok = access_token()
    lk = find_league(tok)
    me = find_my_team(tok, lk)

    s = get(tok, f"league/{lk}/settings").find(".//league")
    league = {k: t(s, k) for k in ("league_key", "name", "season", "scoring_type",
                                   "num_teams", "current_week", "start_week",
                                   "end_week", "is_finished", "url")}
    cats, display = [], []
    for st in s.findall("settings/stat_categories/stats/stat"):
        if t(st, "enabled", "1") == "0":
            continue
        if t(st, "is_only_display_stat") == "1":
            display.append({"id": t(st, "stat_id"), "name": t(st, "display_name") or t(st, "name")})
            continue
        cats.append({"id": t(st, "stat_id"), "name": t(st, "display_name") or t(st, "name"),
                     "higher_better": t(st, "sort_order", "1") == "1"})

    teams = {}
    for tm in get(tok, f"league/{lk}/standings").iter("team"):
        k = t(tm, "team_key")
        teams[k] = {
            "name": t(tm, "name"), "logo": t(tm, "team_logos/team_logo/url"),
            "manager": t(tm, "managers/manager/nickname"),
            "rank": t(tm, "team_standings/rank"),
            "wins": t(tm, "team_standings/outcome_totals/wins"),
            "losses": t(tm, "team_standings/outcome_totals/losses"),
            "ties": t(tm, "team_standings/outcome_totals/ties"),
            "pct": t(tm, "team_standings/outcome_totals/percentage"),
            "points_for": t(tm, "team_standings/points_for"),
        }

    weeks, upcoming = {}, None
    start, cur = int(league["start_week"]), int(league["current_week"])
    end = int(league["end_week"])
    for w in range(start, cur + 1):
        ms = parse_matchups(get(tok, f"league/{lk}/scoreboard;week={w}"))
        if ms and all(m["status"] == "postevent" for m in ms):
            weeks[str(w)] = ms
        elif upcoming is None:
            upcoming = {"week": w, "matchups": ms}
    if upcoming is None and cur < end:
        upcoming = {"week": cur + 1,
                    "matchups": parse_matchups(get(tok, f"league/{lk}/scoreboard;week={cur + 1}"))}

    my_players = None
    if weeks:
        last = max(weeks, key=int)
        try:
            my_players = fetch_my_players(tok, me, last, weeks[last])
        except Exception as ex:  # report still works without this section
            print("Player breakdown skipped:", ex)

    return {"league": league, "my_team": me, "categories": cats, "display_stats": display,
            "teams": teams, "weeks": weeks, "upcoming": upcoming, "my_players": my_players,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}


if __name__ == "__main__":
    try:
        data = fetch_all()
    except RuntimeError as ex:
        sys.exit(str(ex))
    os.makedirs("data", exist_ok=True)
    with open("data/league.json", "w") as f:
        json.dump(data, f, indent=1)
    print(f"Saved data/league.json - {len(data['weeks'])} completed weeks")
