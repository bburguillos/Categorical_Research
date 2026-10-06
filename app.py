import base64
import json
import re

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Sports Association Lab",
    page_icon="📊",
    layout="wide"
)

ESPN_NBA_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

# ----------------------------
# Styling
# ----------------------------
st.markdown("""
<style>
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
    .big-title {
        font-size: 2.25rem;
        font-weight: 800;
        margin-bottom: 0.1rem;
    }
    .subtitle {
        font-size: 1.05rem;
        opacity: .8;
        margin-bottom: 1rem;
    }
    .step-card {
        border: 1px solid rgba(120,120,120,.25);
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 12px;
    }
    .good {
        border-left: 5px solid #2e7d32;
        padding: 10px 12px;
        border-radius: 8px;
        background: rgba(46,125,50,.08);
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# General helpers
# ----------------------------
def safe_get(url, params=None, timeout=25):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
    }

    r = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout
    )

    r.raise_for_status()
    return r.json()


def norm(s):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(s).lower()
    )


def as_number(v):
    if v is None:
        return None

    s = (
        str(v)
        .replace("%", "")
        .replace(",", "")
        .strip()
    )

    if (
        "-" in s
        and re.fullmatch(
            r"\d+(\.\d+)?-\d+(\.\d+)?",
            s
        )
    ):
        s = s.split("-")[0]

    try:
        return float(s)
    except Exception:
        return None


def parse_pct(v):
    x = as_number(v)

    if x is None:
        return None

    return x * 100 if x <= 1.0 else x


def encode_task(payload):
    raw = json.dumps(
        payload,
        separators=(",", ":")
    ).encode("utf-8")

    return (
        base64
        .urlsafe_b64encode(raw)
        .decode("utf-8")
        .rstrip("=")
    )


def decode_task(code):
    try:
        padding = "=" * (-len(code) % 4)

        raw = base64.urlsafe_b64decode(
            code + padding
        )

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:
        return None


def percent(n, d):
    return (
        0.0
        if d == 0
        else 100.0 * n / d
    )


def two_way(df, a1, a2):

    out = pd.crosstab(
        df["expected_category"],
        df["result"]
    )

    for r in [a1, a2]:

        if r not in out.index:
            out.loc[r] = 0

    for c in [
        "Win",
        "Did Not Win"
    ]:

        if c not in out.columns:
            out[c] = 0

    out = out.loc[
        [a1, a2],
        [
            "Win",
            "Did Not Win"
        ]
    ]

    out["Total"] = (
        out.sum(axis=1)
    )

    total_row = pd.DataFrame(
        [[
            out["Win"].sum(),
            out["Did Not Win"].sum(),
            out["Total"].sum()
        ]],
        index=["Total"],
        columns=[
            "Win",
            "Did Not Win",
            "Total"
        ]
    )

    return pd.concat(
        [
            out,
            total_row
        ]
    )


# ============================================================
# NBA
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def get_nba_teams():

    data = safe_get(
        f"{ESPN_NBA_BASE}/teams"
    )

    teams = []

    sports = data.get(
        "sports",
        []
    )

    if sports:

        leagues = sports[0].get(
            "leagues",
            []
        )

        if leagues:

            for item in leagues[0].get(
                "teams",
                []
            ):

                t = item.get(
                    "team",
                    {}
                )

                if (
                    t.get("id")
                    and t.get("displayName")
                ):

                    teams.append({
                        "id": str(t["id"]),
                        "name": t["displayName"]
                    })

    return sorted(
        teams,
        key=lambda x: x["name"]
    )


def nba_season_end_year(label):

    m = re.match(
        r"(\d{4})-(\d{2})",
        label
    )

    if not m:
        return int(label)

    return int(
        m.group(1)
    ) + 1


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def get_nba_schedule(
    team_id,
    season_label
):

    season = nba_season_end_year(
        season_label
    )

    data = safe_get(
        f"{ESPN_NBA_BASE}/teams/{team_id}/schedule",
        params={
            "season": season,
            "seasontype": 2
        }
    )

    return data.get(
        "events",
        []
    )


def nba_competitors(event):

    comps = event.get(
        "competitions",
        []
    )

    if not comps:
        return []

    return comps[0].get(
        "competitors",
        []
    )


def nba_score_number(score_obj):

    if score_obj is None:
        return None

    if isinstance(
        score_obj,
        (int, float)
    ):
        return float(score_obj)

    if isinstance(
        score_obj,
        str
    ):

        try:
            return float(score_obj)

        except Exception:
            return None

    if isinstance(
        score_obj,
        dict
    ):

        for key in [
            "value",
            "displayValue",
            "score"
        ]:

            if key in score_obj:

                try:
                    return float(
                        score_obj[key]
                    )

                except Exception:
                    pass

    return None


def nba_game_core(
    event,
    team_id
):

    competitors = nba_competitors(
        event
    )

    if len(competitors) < 2:
        return None

    team_comp = None
    opp_comp = None

    for c in competitors:

        cid = str(
            c.get(
                "team",
                {}
            ).get(
                "id",
                ""
            )
        )

        if cid == str(team_id):

            team_comp = c

        else:

            opp_comp = c

    if not team_comp or not opp_comp:
        return None

    team_score_raw = nba_score_number(
        team_comp.get("score")
    )

    opp_score_raw = nba_score_number(
        opp_comp.get("score")
    )

    if (
        team_score_raw is None
        or opp_score_raw is None
    ):

        return None

    team_score = int(
        round(team_score_raw)
    )

    opp_score = int(
        round(opp_score_raw)
    )

    result = (
        "Win"
        if (
            team_comp.get("winner") is True
            or team_score > opp_score
        )
        else "Did Not Win"
    )

    home_away = (
        "Home"
        if team_comp.get(
            "homeAway"
        ) == "home"
        else "Away"
    )

    try:

        date_display = (
            pd.to_datetime(
                event.get(
                    "date",
                    ""
                )
            )
            .strftime(
                "%b %d, %Y"
            )
        )

    except Exception:

        date_display = str(
            event.get(
                "date",
                ""
            )
        )[:10]

    return {
        "event_id": str(
            event.get(
                "id",
                ""
            )
        ),
        "date": date_display,
        "opponent": (
            opp_comp
            .get(
                "team",
                {}
            )
            .get(
                "displayName",
                "Opponent"
            )
        ),
        "home_away": home_away,
        "team_score": team_score,
        "opp_score": opp_score,
        "result": result,
    }


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_nba_summary(event_id):

    return safe_get(
        f"{ESPN_NBA_BASE}/summary",
        params={
            "event": event_id
        }
    )


def nba_find_box(
    summary,
    team_id,
    opponent=False
):

    teams = (
        summary
        .get(
            "boxscore",
            {}
        )
        .get(
            "teams",
            []
        )
    )

    for tb in teams:

        tid = str(
            tb.get(
                "team",
                {}
            ).get(
                "id",
                ""
            )
        )

        if (
            not opponent
            and tid == str(team_id)
        ):

            return tb

        if (
            opponent
            and tid
            and tid != str(team_id)
        ):

            return tb

    return None


def nba_stat_map(team_box):

    out = {}

    if not team_box:
        return out

    for s in team_box.get(
        "statistics",
        []
    ):

        value = s.get(
            "displayValue",
            s.get("value")
        )

        candidates = [
            s.get("name", ""),
            s.get("displayName", ""),
            s.get("label", ""),
            s.get("abbreviation", "")
        ]

        for c in candidates:

            if c:
                out[norm(c)] = value

    return out


def first_stat_value(
    stats,
    keys
):

    for key in keys:

        nk = norm(key)

        if nk in stats:
            return stats[nk]

    for k, v in stats.items():

        for key in keys:

            if norm(key) in k:
                return v

    return None


def nba_halftime_points(
    summary,
    team_id
):

    comps = (
        summary
        .get(
            "header",
            {}
        )
        .get(
            "competitions",
            []
        )
    )

    if not comps:
        return None, None

    team_lines = None
    opp_lines = None

    for c in comps[0].get(
        "competitors",
        []
    ):

        tid = str(
            c.get(
                "team",
                {}
            ).get(
                "id",
                ""
            )
        )

        vals = []

        for ls in c.get(
            "linescores",
            []
        ):

            try:

                vals.append(
                    float(
                        ls.get(
                            "value",
                            0
                        )
                    )
                )

            except Exception:

                vals.append(0)

        if tid == str(team_id):

            team_lines = vals

        else:

            opp_lines = vals

    if (
        team_lines is None
        or opp_lines is None
        or len(team_lines) < 2
        or len(opp_lines) < 2
    ):

        return None, None

    return (
        sum(team_lines[:2]),
        sum(opp_lines[:2])
    )


def nba_metric_values(
    summary,
    team_id
):

    ts = nba_stat_map(
        nba_find_box(
            summary,
            team_id
        )
    )

    os = nba_stat_map(
        nba_find_box(
            summary,
            team_id,
            opponent=True
        )
    )

    team_3pm = as_number(
        first_stat_value(
            ts,
            [
                "threePointFieldGoalsMade",
                "3PT Made",
                "3PM",
                "threePointersMade",
                "three point field goals made"
            ]
        )
    )

    opp_3pm = as_number(
        first_stat_value(
            os,
            [
                "threePointFieldGoalsMade",
                "3PT Made",
                "3PM",
                "threePointersMade",
                "three point field goals made"
            ]
        )
    )

    team_to = as_number(
        first_stat_value(
            ts,
            [
                "turnovers",
                "TO"
            ]
        )
    )

    opp_to = as_number(
        first_stat_value(
            os,
            [
                "turnovers",
                "TO"
            ]
        )
    )

    team_reb = as_number(
        first_stat_value(
            ts,
            [
                "totalRebounds",
                "rebounds",
                "REB",
                "total rebounds"
            ]
        )
    )

    opp_reb = as_number(
        first_stat_value(
            os,
            [
                "totalRebounds",
                "rebounds",
                "REB",
                "total rebounds"
            ]
        )
    )

    team_ast = as_number(
        first_stat_value(
            ts,
            [
                "assists",
                "AST"
            ]
        )
    )

    team_fg = parse_pct(
        first_stat_value(
            ts,
            [
                "fieldGoalPct",
                "field goal percentage",
                "FG%"
            ]
        )
    )

    ht_team, ht_opp = (
        nba_halftime_points(
            summary,
            team_id
        )
    )

    return {
        "team_3pm": team_3pm,
        "opp_3pm": opp_3pm,
        "team_turnovers": team_to,
        "opp_turnovers": opp_to,
        "team_rebounds": team_reb,
        "opp_rebounds": opp_reb,
        "team_assists": team_ast,
        "team_fg_pct": team_fg,
        "halftime_team": ht_team,
        "halftime_opp": ht_opp,
    }


NBA_PRESETS = {

    "Home vs. Away": {
        "type": "home_away",
        "a1": "Home",
        "a2": "Away",
        "evidence_label": "Location",
        "question":
            "Does playing at home appear associated with whether the team wins?"
    },

    "Team scores at least 110 points": {
        "type": "team_points_threshold",
        "threshold": 110,
        "a1": "110 Plus Points",
        "a2": "Under 110",
        "evidence_label": "Team points",
        "question":
            "Is scoring 110 or more points associated with whether the team wins?"
    },

    "More 3-pointers than opponent": {
        "type": "compare_more",
        "metric_team": "team_3pm",
        "metric_opp": "opp_3pm",
        "a1": "More 3-Pointers",
        "a2": "Not More 3-Pointers",
        "evidence_label":
            "Team 3PM vs. opponent 3PM",
        "question":
            "Is making more three-pointers than the opponent associated with whether the team wins?"
    },

    "Fewer turnovers than opponent": {
        "type": "compare_fewer",
        "metric_team": "team_turnovers",
        "metric_opp": "opp_turnovers",
        "a1": "Fewer Turnovers",
        "a2": "Not Fewer Turnovers",
        "evidence_label":
            "Team turnovers vs. opponent turnovers",
        "question":
            "Is having fewer turnovers than the opponent associated with whether the team wins?"
    },

    "Field goal percentage at least 50%": {
        "type": "metric_threshold",
        "metric_team": "team_fg_pct",
        "threshold": 50,
        "a1": "50 Percent Plus FG",
        "a2": "Under 50 Percent",
        "evidence_label": "Team FG%",
        "question":
            "Is shooting at least 50 percent from the field associated with whether the team wins?"
    },

    "More rebounds than opponent": {
        "type": "compare_more",
        "metric_team": "team_rebounds",
        "metric_opp": "opp_rebounds",
        "a1": "More Rebounds",
        "a2": "Not More Rebounds",
        "evidence_label":
            "Team rebounds vs. opponent rebounds",
        "question":
            "Is outrebounding the opponent associated with whether the team wins?"
    },

    "Led at halftime": {
        "type": "compare_more",
        "metric_team": "halftime_team",
        "metric_opp": "halftime_opp",
        "a1": "Led at Halftime",
        "a2": "Did Not Lead at Halftime",
        "evidence_label": "Halftime score",
        "question":
            "Does leading at halftime appear associated with whether the team wins?"
    },

    "Made at least 12 three-pointers": {
        "type": "metric_threshold",
        "metric_team": "team_3pm",
        "threshold": 12,
        "a1": "12 Plus 3-Pointers",
        "a2": "Fewer Than 12",
        "evidence_label": "Team 3PM",
        "question":
            "Is making 12 or more three-pointers associated with whether the team wins?"
    },

    "Held opponent under 110 points": {
        "type": "opp_points_under",
        "threshold": 110,
        "a1": "Opponent Under 110",
        "a2": "Opponent 110 Plus",
        "evidence_label": "Opponent points",
        "question":
            "Is holding the opponent under 110 points associated with whether the team wins?"
    },

    "At least 25 assists": {
        "type": "metric_threshold",
        "metric_team": "team_assists",
        "threshold": 25,
        "a1": "25 Plus Assists",
        "a2": "Under 25 Assists",
        "evidence_label": "Team assists",
        "question":
            "Are 25 or more team assists associated with whether the team wins?"
    },
}


def nba_classify(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_points_threshold":

        return (
            cfg["a1"]
            if row["team_score"] >= cfg["threshold"]
            else cfg["a2"]
        )

    if t == "opp_points_under":

        return (
            cfg["a1"]
            if row["opp_score"] < cfg["threshold"]
            else cfg["a2"]
        )

    if t == "metric_threshold":

        v = row.get(
            cfg["metric_team"]
        )

        if (
            v is None
            or pd.isna(v)
        ):
            return None

        return (
            cfg["a1"]
            if float(v) >= float(cfg["threshold"])
            else cfg["a2"]
        )

    if t in (
        "compare_more",
        "compare_fewer"
    ):

        a = row.get(
            cfg["metric_team"]
        )

        b = row.get(
            cfg["metric_opp"]
        )

        if (
            a is None
            or b is None
            or pd.isna(a)
            or pd.isna(b)
        ):

            return None

        if t == "compare_more":

            return (
                cfg["a1"]
                if float(a) > float(b)
                else cfg["a2"]
            )

        return (
            cfg["a1"]
            if float(a) < float(b)
            else cfg["a2"]
        )

    return None


def nba_evidence_text(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_points_threshold":
        return str(row["team_score"])

    if t == "opp_points_under":
        return str(row["opp_score"])

    if t == "metric_threshold":

        v = row.get(
            cfg["metric_team"]
        )

        if (
            v is None
            or pd.isna(v)
        ):
            return "Unavailable"

        if (
            cfg["metric_team"]
            == "team_fg_pct"
        ):

            return (
                f"{float(v):.1f}%"
            )

        return f"{float(v):g}"

    if t in (
        "compare_more",
        "compare_fewer"
    ):

        a = row.get(
            cfg["metric_team"]
        )

        b = row.get(
            cfg["metric_opp"]
        )

        if (
            a is None
            or b is None
            or pd.isna(a)
            or pd.isna(b)
        ):

            return "Unavailable"

        if (
            "halftime"
            in cfg["metric_team"]
        ):

            return (
                f"{float(a):g} – "
                f"{float(b):g}"
            )

        return (
            f"{float(a):g} vs. "
            f"{float(b):g}"
        )

    return ""


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def build_nba_dataset(
    team_id,
    season_label,
    sample_size,
    variable_name
):

    events = get_nba_schedule(
        team_id,
        season_label
    )

    completed = []

    for e in events:

        comps = e.get(
            "competitions",
            []
        )

        if not comps:
            continue

        status_type = (
            comps[0]
            .get(
                "status",
                {}
            )
            .get(
                "type",
                {}
            )
        )

        completed_flag = (
            status_type
            .get("completed")
        )

        state = str(
            status_type.get(
                "state",
                ""
            )
        ).lower()

        name = str(
            status_type.get(
                "name",
                ""
            )
        ).lower()

        short_detail = str(
            status_type.get(
                "shortDetail",
                ""
            )
        ).lower()

        core = nba_game_core(
            e,
            team_id
        )

        is_completed = (
            completed_flag is True
            or state == "post"
            or "final" in name
            or "final" in short_detail
            or core is not None
        )

        if (
            is_completed
            and core is not None
        ):

            completed.append(core)

    def sort_key(g):

        try:

            return pd.to_datetime(
                g["date"]
            )

        except Exception:

            return pd.Timestamp.max

    completed = sorted(
        completed,
        key=sort_key
    )[:sample_size]

    cfg = NBA_PRESETS[
        variable_name
    ]

    rows = []

    for g in completed:

        row = dict(g)

        if cfg["type"] in (
            "metric_threshold",
            "compare_more",
            "compare_fewer"
        ):

            try:

                summary = get_nba_summary(
                    g["event_id"]
                )

                row.update(
                    nba_metric_values(
                        summary,
                        team_id
                    )
                )

            except Exception:

                row.update({
                    "team_3pm": None,
                    "opp_3pm": None,
                    "team_turnovers": None,
                    "opp_turnovers": None,
                    "team_rebounds": None,
                    "opp_rebounds": None,
                    "team_assists": None,
                    "team_fg_pct": None,
                    "halftime_team": None,
                    "halftime_opp": None,
                })

        row["expected_category"] = (
            nba_classify(
                row,
                cfg
            )
        )

        row["evidence"] = (
            nba_evidence_text(
                row,
                cfg
            )
        )

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# MLB
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def get_mlb_teams(season):

    data = safe_get(
        f"{MLB_API_BASE}/teams",
        params={
            "sportId": 1,
            "season": season
        }
    )

    teams = []

    for t in data.get(
        "teams",
        []
    ):

        if (
            t.get("id")
            and t.get("name")
        ):

            teams.append({
                "id": str(t["id"]),
                "name": t["name"]
            })

    return sorted(
        teams,
        key=lambda x: x["name"]
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def get_mlb_schedule(
    team_id,
    season
):

    data = safe_get(
        f"{MLB_API_BASE}/schedule",
        params={
            "sportId": 1,
            "teamId": team_id,
            "season": season,
            "gameType": "R"
        }
    )

    games = []

    for date_block in data.get(
        "dates",
        []
    ):

        games.extend(
            date_block.get(
                "games",
                []
            )
        )

    return games


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_mlb_game_feed(game_pk):

    return safe_get(
        f"{MLB_API_BASE}.1/game/{game_pk}/feed/live"
    )


def mlb_game_core(
    game,
    team_id
):

    teams = game.get(
        "teams",
        {}
    )

    home = teams.get(
        "home",
        {}
    )

    away = teams.get(
        "away",
        {}
    )

    home_id = str(
        home.get(
            "team",
            {}
        ).get(
            "id",
            ""
        )
    )

    away_id = str(
        away.get(
            "team",
            {}
        ).get(
            "id",
            ""
        )
    )

    if str(team_id) == home_id:

        team_side = "home"
        opp_side = "away"

        team_obj = home
        opp_obj = away

        home_away = "Home"

    elif str(team_id) == away_id:

        team_side = "away"
        opp_side = "home"

        team_obj = away
        opp_obj = home

        home_away = "Away"

    else:

        return None

    try:

        team_score = int(
            team_obj.get("score")
        )

        opp_score = int(
            opp_obj.get("score")
        )

    except Exception:

        return None

    result = (
        "Win"
        if team_score > opp_score
        else "Did Not Win"
    )

    try:

        date_display = (
            pd.to_datetime(
                game.get(
                    "gameDate",
                    ""
                )
            )
            .strftime(
                "%b %d, %Y"
            )
        )

    except Exception:

        date_display = str(
            game.get(
                "officialDate",
                ""
            )
        )

    return {
        "game_pk": str(
            game.get(
                "gamePk",
                ""
            )
        ),
        "date": date_display,
        "opponent": (
            opp_obj
            .get(
                "team",
                {}
            )
            .get(
                "name",
                "Opponent"
            )
        ),
        "home_away": home_away,
        "team_side": team_side,
        "opp_side": opp_side,
        "team_score": team_score,
        "opp_score": opp_score,
        "result": result,
    }


def mlb_team_stats(
    feed,
    side
):

    return (
        feed
        .get(
            "liveData",
            {}
        )
        .get(
            "boxscore",
            {}
        )
        .get(
            "teams",
            {}
        )
        .get(
            side,
            {}
        )
        .get(
            "teamStats",
            {}
        )
    )


def mlb_batting_stat(
    feed,
    side,
    key
):

    return (
        mlb_team_stats(
            feed,
            side
        )
        .get(
            "batting",
            {}
        )
        .get(key)
    )


def mlb_pitching_stat(
    feed,
    side,
    key
):

    return (
        mlb_team_stats(
            feed,
            side
        )
        .get(
            "pitching",
            {}
        )
        .get(key)
    )


def mlb_fielding_stat(
    feed,
    side,
    key
):

    return (
        mlb_team_stats(
            feed,
            side
        )
        .get(
            "fielding",
            {}
        )
        .get(key)
    )


def mlb_scored_first(
    feed,
    team_side
):

    plays = (
        feed
        .get(
            "liveData",
            {}
        )
        .get(
            "plays",
            {}
        )
    )

    all_plays = plays.get(
        "allPlays",
        []
    )

    for p in all_plays:

        if (
            p.get(
                "about",
                {}
            ).get(
                "isScoringPlay"
            ) is True
        ):

            half = str(
                p.get(
                    "about",
                    {}
                ).get(
                    "halfInning",
                    ""
                )
            ).lower()

            scoring_side = (
                "away"
                if half == "top"
                else "home"
            )

            return (
                scoring_side
                == team_side
            )

    return False


def mlb_quality_start(
    feed,
    team_side
):

    side_box = (
        feed
        .get(
            "liveData",
            {}
        )
        .get(
            "boxscore",
            {}
        )
        .get(
            "teams",
            {}
        )
        .get(
            team_side,
            {}
        )
    )

    players = side_box.get(
        "players",
        {}
    )

    pitcher_ids = side_box.get(
        "pitchers",
        []
    )

    if not pitcher_ids:

        return None, None, None

    starter = players.get(
        f"ID{pitcher_ids[0]}",
        {}
    )

    pitching = (
        starter
        .get(
            "stats",
            {}
        )
        .get(
            "pitching",
            {}
        )
    )

    ip = as_number(
        pitching.get(
            "inningsPitched"
        )
    )

    er = as_number(
        pitching.get(
            "earnedRuns"
        )
    )

    if (
        ip is None
        or er is None
    ):

        return None, ip, er

    return (
        (
            ip >= 6
            and er <= 3
        ),
        ip,
        er
    )


MLB_PRESETS = {

    "Home vs. Away": {
        "type": "home_away",
        "a1": "Home",
        "a2": "Away",
        "evidence_label": "Location",
        "question":
            "Does playing at home appear associated with whether the team wins?"
    },

    "Hit at least 1 home run": {
        "type": "metric_threshold",
        "metric": "home_runs",
        "threshold": 1,
        "a1": "Hit 1 Plus HR",
        "a2": "Hit 0 HR",
        "evidence_label": "Team HR",
        "question":
            "Is hitting at least one home run associated with whether the team wins?"
    },

    "Scored first": {
        "type": "boolean",
        "metric": "scored_first",
        "a1": "Scored First",
        "a2": "Did Not Score First",
        "evidence_label":
            "First scoring team",
        "question":
            "Does scoring first appear associated with whether the team wins?"
    },

    "Committed at least 1 error": {
        "type": "metric_threshold",
        "metric": "errors",
        "threshold": 1,
        "a1": "Committed 1 Plus Error",
        "a2": "Committed 0 Errors",
        "evidence_label":
            "Team errors",
        "question":
            "Is committing an error associated with whether the team wins?"
    },

    "Scored at least 5 runs": {
        "type": "team_score_threshold",
        "threshold": 5,
        "a1": "5 Plus Runs",
        "a2": "Under 5 Runs",
        "evidence_label":
            "Team runs",
        "question":
            "Is scoring five or more runs associated with whether the team wins?"
    },

    "At least 10 hits": {
        "type": "metric_threshold",
        "metric": "hits",
        "threshold": 10,
        "a1": "10 Plus Hits",
        "a2": "Under 10 Hits",
        "evidence_label":
            "Team hits",
        "question":
            "Are 10 or more team hits associated with whether the team wins?"
    },

    "Quality start": {
        "type": "boolean",
        "metric": "quality_start",
        "a1": "Quality Start",
        "a2": "No Quality Start",
        "evidence_label":
            "Starter IP / ER",
        "question":
            "Is a quality start associated with whether the team wins?"
    },

    "At least 2 home runs": {
        "type": "metric_threshold",
        "metric": "home_runs",
        "threshold": 2,
        "a1": "2 Plus HR",
        "a2": "Fewer Than 2 HR",
        "evidence_label":
            "Team HR",
        "question":
            "Are two or more team home runs associated with whether the team wins?"
    },

    "At least 4 walks": {
        "type": "metric_threshold",
        "metric": "walks",
        "threshold": 4,
        "a1": "4 Plus Walks",
        "a2": "Fewer Than 4 Walks",
        "evidence_label":
            "Team walks",
        "question":
            "Are four or more walks associated with whether the team wins?"
    },

    "At least 10 pitching strikeouts": {
        "type": "metric_threshold",
        "metric": "pitching_strikeouts",
        "threshold": 10,
        "a1":
            "10 Plus Pitching Strikeouts",
        "a2":
            "Under 10",
        "evidence_label":
            "Pitching strikeouts",
        "question":
            "Are 10 or more team strikeouts by the team's pitchers associated with whether the team wins?"
    },
}


def mlb_metric_values(
    feed,
    core
):

    team_side = core[
        "team_side"
    ]

    quality_start, starter_ip, starter_er = (
        mlb_quality_start(
            feed,
            team_side
        )
    )

    return {
        "home_runs": as_number(
            mlb_batting_stat(
                feed,
                team_side,
                "homeRuns"
            )
        ),
        "hits": as_number(
            mlb_batting_stat(
                feed,
                team_side,
                "hits"
            )
        ),
        "walks": as_number(
            mlb_batting_stat(
                feed,
                team_side,
                "baseOnBalls"
            )
        ),
        "errors": as_number(
            mlb_fielding_stat(
                feed,
                team_side,
                "errors"
            )
        ),
        "pitching_strikeouts": as_number(
            mlb_pitching_stat(
                feed,
                team_side,
                "strikeOuts"
            )
        ),
        "scored_first": mlb_scored_first(
            feed,
            team_side
        ),
        "quality_start": quality_start,
        "starter_ip": starter_ip,
        "starter_er": starter_er,
    }


def mlb_classify(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_score_threshold":

        return (
            cfg["a1"]
            if row["team_score"] >= cfg["threshold"]
            else cfg["a2"]
        )

    if t == "metric_threshold":

        v = row.get(
            cfg["metric"]
        )

        if (
            v is None
            or pd.isna(v)
        ):

            return None

        return (
            cfg["a1"]
            if float(v) >= float(cfg["threshold"])
            else cfg["a2"]
        )

    if t == "boolean":

        v = row.get(
            cfg["metric"]
        )

        if v is None:
            return None

        return (
            cfg["a1"]
            if bool(v)
            else cfg["a2"]
        )

    return None


def mlb_evidence_text(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_score_threshold":
        return str(
            row["team_score"]
        )

    if t == "metric_threshold":

        v = row.get(
            cfg["metric"]
        )

        if (
            v is None
            or pd.isna(v)
        ):
            return "Unavailable"

        return f"{float(v):g}"

    if t == "boolean":

        if (
            cfg["metric"]
            == "scored_first"
        ):

            return (
                "Team scored first"
                if row.get(
                    "scored_first"
                )
                else "Opponent scored first"
            )

        if (
            cfg["metric"]
            == "quality_start"
        ):

            ip = row.get(
                "starter_ip"
            )

            er = row.get(
                "starter_er"
            )

            if (
                ip is None
                or er is None
            ):

                return "Unavailable"

            return (
                f"{float(ip):g} IP / "
                f"{float(er):g} ER"
            )

    return ""


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def build_mlb_dataset(
    team_id,
    season,
    sample_size,
    variable_name
):

    games = get_mlb_schedule(
        team_id,
        season
    )

    completed = []

    for g in games:

        status = g.get(
            "status",
            {}
        )

        abstract = str(
            status.get(
                "abstractGameState",
                ""
            )
        ).lower()

        coded = str(
            status.get(
                "codedGameState",
                ""
            )
        ).upper()

        detailed = str(
            status.get(
                "detailedState",
                ""
            )
        ).lower()

        is_completed = (
            abstract == "final"
            or coded == "F"
            or "final" in detailed
            or "game over" in detailed
        )

        if not is_completed:
            continue

        core = mlb_game_core(
            g,
            team_id
        )

        if core:
            completed.append(
                core
            )

    def sort_key(g):

        try:

            return pd.to_datetime(
                g["date"]
            )

        except Exception:

            return pd.Timestamp.max

    completed = sorted(
        completed,
        key=sort_key
    )[:sample_size]

    cfg = MLB_PRESETS[
        variable_name
    ]

    rows = []

    for core in completed:

        row = dict(core)

        if cfg["type"] not in (
            "home_away",
            "team_score_threshold"
        ):

            try:

                feed = get_mlb_game_feed(
                    core["game_pk"]
                )

                row.update(
                    mlb_metric_values(
                        feed,
                        core
                    )
                )

            except Exception:

                row.update({
                    "home_runs": None,
                    "hits": None,
                    "walks": None,
                    "errors": None,
                    "pitching_strikeouts": None,
                    "scored_first": None,
                    "quality_start": None,
                    "starter_ip": None,
                    "starter_er": None,
                })

        row["expected_category"] = (
            mlb_classify(
                row,
                cfg
            )
        )

        row["evidence"] = (
            mlb_evidence_text(
                row,
                cfg
            )
        )

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# Sport configuration
# ============================================================

SPORTS = [
    "NBA",
    "MLB"
]

SPORT_SEASONS = {

    "NBA": [
        "2025-26",
        "2024-25",
        "2023-24",
        "2022-23"
    ],

    "MLB": [
        "2025",
        "2024",
        "2023",
        "2022"
    ]
}


def get_presets(sport):

    if sport == "NBA":
        return NBA_PRESETS

    return MLB_PRESETS


def get_teams_for_sport(
    sport,
    season
):

    if sport == "NBA":

        return get_nba_teams()

    return get_mlb_teams(
        int(season)
    )


def build_dataset(
    sport,
    team_id,
    season,
    sample_size,
    variable_name
):

    if sport == "NBA":

        return build_nba_dataset(
            team_id,
            season,
            sample_size,
            variable_name
        )

    return build_mlb_dataset(
        team_id,
        int(season),
        sample_size,
        variable_name
    )


# ============================================================
# Header
# ============================================================

st.markdown(
    '<div class="big-title">📊 Sports Association Lab</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Use real game data to investigate whether two categorical variables appear associated.</div>',
    unsafe_allow_html=True
)

mode = st.radio(
    "Choose a mode",
    [
        "Student Research",
        "Teacher Assignment Builder"
    ],
    horizontal=True
)


# ============================================================
# Teacher Mode
# ============================================================

if mode == "Teacher Assignment Builder":

    st.subheader(
        "Teacher Assignment Builder"
    )

    st.write(
        "Create a setup code so students cannot accidentally choose the wrong sport, team, season, variable, or sample."
    )

    t_sport = st.selectbox(
        "Sport",
        SPORTS,
        key="teacher_sport"
    )

    t_season = st.selectbox(
        "Season",
        SPORT_SEASONS[
            t_sport
        ],
        key="teacher_season"
    )

    try:

        t_teams = (
            get_teams_for_sport(
                t_sport,
                t_season
            )
        )

    except Exception as e:

        st.error(
            "The team list could not be loaded."
        )

        st.code(
            str(e)
        )

        st.stop()

    t_team_names = [
        t["name"]
        for t in t_teams
    ]

    t_presets = get_presets(
        t_sport
    )

    c1, c2 = st.columns(2)

    with c1:

        t_team = st.selectbox(
            "Team",
            t_team_names
        )

        t_variable = st.selectbox(
            "Categorical variable",
            list(
                t_presets.keys()
            )
        )

    with c2:

        t_sample = st.selectbox(
            "Sample size",
            [
                10,
                15,
                20
            ],
            index=2
        )

    cfg = t_presets[
        t_variable
    ]

    st.info(
        "Research question: "
        + cfg["question"].replace(
            "the team",
            t_team
        )
    )

    st.write(
        f"**Variable A categories:** "
        f"{cfg['a1']} / {cfg['a2']}"
    )

    st.write(
        "**Outcome categories:** "
        "Win / Did Not Win"
    )

    if st.button(
        "Create Assignment Code",
        type="primary"
    ):

        payload = {
            "sport": t_sport,
            "team": t_team,
            "season": t_season,
            "variable": t_variable,
            "sample": t_sample
        }

        st.success(
            "Assignment code created."
        )

        st.code(
            encode_task(payload),
            language=None
        )

        st.caption(
            "Students paste this code into Student Research mode."
        )

    st.stop()


# ============================================================
# Student Mode
# ============================================================

st.subheader(
    "Student Research"
)

task_code = st.text_input(
    "Have an assignment code? Paste it here (optional).",
    placeholder="Paste teacher code here"
)

preset = (
    decode_task(
        task_code.strip()
    )
    if task_code.strip()
    else None
)

if (
    task_code.strip()
    and preset is None
):

    st.warning(
        "That code could not be read. You can still choose the settings manually."
    )

default_sport = (
    preset.get(
        "sport",
        "NBA"
    )
    if preset
    else "NBA"
)

if default_sport not in SPORTS:
    default_sport = "NBA"

sport = st.selectbox(
    "1. Sport",
    SPORTS,
    index=SPORTS.index(
        default_sport
    ),
    disabled=bool(preset)
)

season_options = (
    SPORT_SEASONS[
        sport
    ]
)

default_season = (
    preset.get("season")
    if preset
    else season_options[0]
)

if (
    default_season
    not in season_options
):

    default_season = (
        season_options[0]
    )

season = st.selectbox(
    "2. Season",
    season_options,
    index=season_options.index(
        default_season
    ),
    disabled=bool(preset)
)

try:

    teams = get_teams_for_sport(
        sport,
        season
    )

except Exception as e:

    st.error(
        "The team list could not be loaded."
    )

    st.code(
        str(e)
    )

    st.stop()

team_names = [
    t["name"]
    for t in teams
]

team_map = {
    t["name"]: t["id"]
    for t in teams
}

default_team = (
    preset.get("team")
    if preset
    else team_names[0]
)

if default_team not in team_names:
    default_team = team_names[0]

presets = get_presets(
    sport
)

variable_options = list(
    presets.keys()
)

default_variable = (
    preset.get("variable")
    if preset
    else variable_options[0]
)

if (
    default_variable
    not in variable_options
):

    default_variable = (
        variable_options[0]
    )

default_sample = (
    preset.get(
        "sample",
        20
    )
    if preset
    else 20
)

if default_sample not in [
    10,
    15,
    20
]:

    default_sample = 20

c1, c2, c3 = st.columns(3)

with c1:

    team_name = st.selectbox(
        "3. Team",
        team_names,
        index=team_names.index(
            default_team
        ),
        disabled=bool(preset)
    )

with c2:

    variable_name = st.selectbox(
        "4. Variable",
        variable_options,
        index=variable_options.index(
            default_variable
        ),
        disabled=bool(preset)
    )

with c3:

    sample_size = st.selectbox(
        "5. Sample",
        [
            10,
            15,
            20
        ],
        index=[
            10,
            15,
            20
        ].index(
            default_sample
        ),
        disabled=bool(preset)
    )

cfg = presets[
    variable_name
]

team_id = team_map[
    team_name
]

st.markdown(
    '<div class="step-card">',
    unsafe_allow_html=True
)

st.write(
    "### Research Question"
)

st.write(
    cfg["question"].replace(
        "the team",
        team_name
    )
)

st.write(
    f"**Variable A:** "
    f"{cfg['a1']} / {cfg['a2']}"
)

st.write(
    "**Outcome:** "
    "Win / Did Not Win"
)

st.markdown(
    '</div>',
    unsafe_allow_html=True
)

if st.button(
    "Load Game Data",
    type="primary"
):

    st.session_state[
        "loaded_key"
    ] = (
        sport,
        team_id,
        team_name,
        season,
        sample_size,
        variable_name
    )

    st.session_state[
        "classification_ok"
    ] = False

loaded_key = st.session_state.get(
    "loaded_key"
)

if not loaded_key:

    st.info(
        "Choose your investigation and click **Load Game Data**."
    )

    st.stop()

(
    loaded_sport,
    loaded_team_id,
    loaded_team_name,
    loaded_season,
    loaded_sample,
    loaded_variable
) = loaded_key

loaded_presets = (
    get_presets(
        loaded_sport
    )
)

cfg = loaded_presets[
    loaded_variable
]

with st.spinner(
    "Loading completed games and box-score data..."
):

    try:

        df = build_dataset(
            loaded_sport,
            loaded_team_id,
            loaded_season,
            loaded_sample,
            loaded_variable
        )

    except Exception as e:

        st.error(
            "The game data could not be loaded."
        )

        st.code(
            str(e)
        )

        st.stop()

if df.empty:

    st.error(
        "No completed games were found for this selection."
    )

    st.stop()

missing = int(
    df[
        "expected_category"
    ]
    .isna()
    .sum()
)

if missing:

    st.warning(
        f"{missing} game(s) are missing the statistic needed for this variable. "
        "Those rows were left out of the classification activity."
    )

df_valid = (
    df[
        df["expected_category"]
        .notna()
    ]
    .copy()
)

if df_valid.empty:

    st.error(
        "The statistic needed for this investigation was unavailable for the selected games."
    )

    st.stop()

st.write(
    "## Step 1 — Examine the evidence"
)

st.caption(
    "Do not jump straight to the category. Look at the evidence first."
)

student_table = (
    df_valid[
        [
            "date",
            "opponent",
            "evidence",
            "result"
        ]
    ]
    .copy()
)

student_table.columns = [
    "Date",
    "Opponent",
    cfg["evidence_label"],
    "Outcome"
]

student_table.insert(
    0,
    "Game",
    range(
        1,
        len(student_table) + 1
    )
)

st.dataframe(
    student_table,
    use_container_width=True,
    hide_index=True
)

st.write(
    "## Step 2 — Classify each game"
)

st.caption(
    f"For each row, choose "
    f"**{cfg['a1']}** or "
    f"**{cfg['a2']}**."
)

edit = (
    student_table[
        [
            "Game",
            "Date",
            "Opponent",
            cfg["evidence_label"],
            "Outcome"
        ]
    ]
    .copy()
)

edit[
    "Your Category"
] = ""

edited = st.data_editor(
    edit,
    use_container_width=True,
    hide_index=True,
    disabled=[
        "Game",
        "Date",
        "Opponent",
        cfg["evidence_label"],
        "Outcome"
    ],
    column_config={
        "Your Category":
            st.column_config.SelectboxColumn(
                "Your Category",
                options=[
                    "",
                    cfg["a1"],
                    cfg["a2"]
                ],
                required=False
            )
    },
    key=(
        f"editor_"
        f"{loaded_sport}_"
        f"{loaded_team_id}_"
        f"{loaded_season}_"
        f"{loaded_variable}_"
        f"{loaded_sample}"
    )
)

if st.button(
    "Check My Classifications"
):

    answers = (
        edited[
            "Your Category"
        ]
        .tolist()
    )

    expected = (
        df_valid[
            "expected_category"
        ]
        .tolist()
    )

    correct = [
        a == e
        for a, e
        in zip(
            answers,
            expected
        )
    ]

    num_correct = sum(
        correct
    )

    st.session_state[
        "classification_ok"
    ] = all(correct)

    if all(correct):

        st.success(
            f"Perfect — {num_correct} of {len(correct)} classifications are correct."
        )

    else:

        st.warning(
            f"{num_correct} of {len(correct)} are correct. "
            "Fix the row numbers below and check again."
        )

        wrong_games = [
            str(i + 1)
            for i, ok
            in enumerate(correct)
            if not ok
        ]

        st.write(
            "Rows to fix: **"
            + ", ".join(
                wrong_games
            )
            + "**"
        )

if not st.session_state.get(
    "classification_ok",
    False
):

    st.info(
        "When all classifications are correct, the analysis section will unlock."
    )

    st.stop()

st.write(
    "## Step 3 — Build the two-way table"
)

tw = two_way(
    df_valid,
    cfg["a1"],
    cfg["a2"]
)

st.dataframe(
    tw,
    use_container_width=True
)

a1_win = int(
    tw.loc[
        cfg["a1"],
        "Win"
    ]
)

a1_total = int(
    tw.loc[
        cfg["a1"],
        "Total"
    ]
)

a2_win = int(
    tw.loc[
        cfg["a2"],
        "Win"
    ]
)

a2_total = int(
    tw.loc[
        cfg["a2"],
        "Total"
    ]
)

p1 = percent(
    a1_win,
    a1_total
)

p2 = percent(
    a2_win,
    a2_total
)

diff = abs(
    p1 - p2
)

st.write(
    "## Step 4 — Conditional percentages"
)

pcol1, pcol2 = (
    st.columns(2)
)

with pcol1:

    st.metric(
        cfg["a1"],
        f"{p1:.1f}% win rate"
    )

    st.caption(
        f"{a1_win} ÷ {a1_total} × 100 = {p1:.1f}%"
    )

with pcol2:

    st.metric(
        cfg["a2"],
        f"{p2:.1f}% win rate"
    )

    st.caption(
        f"{a2_win} ÷ {a2_total} × 100 = {p2:.1f}%"
    )

st.metric(
    "Difference",
    f"{diff:.1f} percentage points"
)

chart_df = pd.DataFrame({
    "Category": [
        cfg["a1"],
        cfg["a2"]
    ],
    "Win %": [
        p1,
        p2
    ]
}).set_index(
    "Category"
)

st.bar_chart(
    chart_df
)

st.write(
    "## Step 5 — Write the verdict"
)

st.markdown(
    f"""
<div class="good">

<b>Use the numbers — but make the claim yourself.</b>

<br><br>

When <b>{cfg['a1']}</b> occurred,
the team won <b>{p1:.1f}%</b> of the time.

<br>

When <b>{cfg['a2']}</b> occurred,
the team won <b>{p2:.1f}%</b> of the time.

<br>

The difference was
<b>{diff:.1f} percentage points</b>.

</div>
""",
    unsafe_allow_html=True
)

st.radio(
    "Do the variables appear associated in this sample?",
    [
        "YES",
        "NO",
        "UNCLEAR"
    ],
    horizontal=True
)

st.text_area(
    "Explain your reasoning using both percentages.",
    placeholder="Our data suggests ... because ..."
)

st.text_area(
    "Name one limitation of the investigation.",
    placeholder="One limitation is ..."
)

st.caption(
    "Reminder: an association does not prove that one variable caused the other."
)

with st.expander(
    "Source information"
):

    if loaded_sport == "NBA":

        st.write(
            "NBA schedules and box-score statistics in this version are retrieved from ESPN's public sports data endpoints."
        )

    else:

        st.write(
            "MLB schedules and game feeds in this version are retrieved from MLB's Stats API. "
            "Students should still record the original game schedule or box score in their project source log."
        )
