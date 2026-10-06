import base64
import json
import re

import pandas as pd
import requests
import streamlit as st


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Sports Association Lab",
    page_icon="📊",
    layout="wide"
)

NBA_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
MLB_BASE = "https://statsapi.mlb.com/api/v1"
NHL_BASE = "https://api-web.nhle.com/v1"
MLS_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1"


# ============================================================
# STYLING
# ============================================================

st.markdown("""
<style>

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}

.big-title {
    font-size: 2.35rem;
    font-weight: 800;
    margin-bottom: .1rem;
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


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_get(url, params=None, timeout=25):

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*"
    }

    r = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout
    )

    r.raise_for_status()

    return r.json()


def norm(value):

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower()
    )


def as_number(value):

    if value is None:
        return None

    s = (
        str(value)
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


def parse_pct(value):

    x = as_number(value)

    if x is None:
        return None

    return x * 100 if x <= 1 else x


def percent(n, d):

    if d == 0:
        return 0.0

    return 100.0 * n / d


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


def two_way(df, a1, a2):

    out = pd.crosstab(
        df["expected_category"],
        df["result"]
    )

    for row_name in [a1, a2]:

        if row_name not in out.index:
            out.loc[row_name] = 0

    for col_name in [
        "Win",
        "Did Not Win"
    ]:

        if col_name not in out.columns:
            out[col_name] = 0

    out = out.loc[
        [a1, a2],
        [
            "Win",
            "Did Not Win"
        ]
    ]

    out["Total"] = out.sum(axis=1)

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
        f"{NBA_BASE}/teams"
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


def nba_season_id(label):

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
    season
):

    data = safe_get(
        f"{NBA_BASE}/teams/{team_id}/schedule",
        params={
            "season": nba_season_id(
                season
            ),
            "seasontype": 2
        }
    )

    return data.get(
        "events",
        []
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_nba_summary(
    event_id
):

    return safe_get(
        f"{NBA_BASE}/summary",
        params={
            "event": event_id
        }
    )


def nba_score(value):

    if isinstance(
        value,
        (int, float)
    ):
        return float(value)

    if isinstance(
        value,
        str
    ):

        try:
            return float(value)

        except Exception:
            return None

    if isinstance(
        value,
        dict
    ):

        for key in [
            "value",
            "displayValue",
            "score"
        ]:

            if key in value:

                try:
                    return float(
                        value[key]
                    )

                except Exception:
                    pass

    return None


def nba_core(
    event,
    team_id
):

    comps = event.get(
        "competitions",
        []
    )

    if not comps:
        return None

    competitors = comps[0].get(
        "competitors",
        []
    )

    team = None
    opp = None

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
            team = c

        else:
            opp = c

    if not team or not opp:
        return None

    team_score = nba_score(
        team.get("score")
    )

    opp_score = nba_score(
        opp.get("score")
    )

    if (
        team_score is None
        or opp_score is None
    ):
        return None

    team_score = int(
        round(team_score)
    )

    opp_score = int(
        round(opp_score)
    )

    try:

        date = (
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

        date = str(
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

        "date": date,

        "opponent": (
            opp.get(
                "team",
                {}
            ).get(
                "displayName",
                "Opponent"
            )
        ),

        "home_away": (
            "Home"
            if team.get(
                "homeAway"
            ) == "home"
            else "Away"
        ),

        "team_score": team_score,

        "opp_score": opp_score,

        "result": (
            "Win"
            if (
                team.get(
                    "winner"
                ) is True
                or team_score > opp_score
            )
            else "Did Not Win"
        )
    }


def nba_box(
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


def stat_map(box):

    out = {}

    if not box:
        return out

    for s in box.get(
        "statistics",
        []
    ):

        value = s.get(
            "displayValue",
            s.get("value")
        )

        for key in [
            "name",
            "displayName",
            "label",
            "abbreviation"
        ]:

            if s.get(key):

                out[
                    norm(
                        s[key]
                    )
                ] = value

    return out


def find_stat(
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


def nba_halftime(
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

        if str(
            c.get(
                "team",
                {}
            ).get(
                "id",
                ""
            )
        ) == str(team_id):

            team_lines = vals

        else:

            opp_lines = vals

    if (
        not team_lines
        or not opp_lines
        or len(team_lines) < 2
        or len(opp_lines) < 2
    ):

        return None, None

    return (
        sum(team_lines[:2]),
        sum(opp_lines[:2])
    )


def nba_metrics(
    summary,
    team_id
):

    team_stats = stat_map(
        nba_box(
            summary,
            team_id
        )
    )

    opp_stats = stat_map(
        nba_box(
            summary,
            team_id,
            True
        )
    )

    halftime_team, halftime_opp = (
        nba_halftime(
            summary,
            team_id
        )
    )

    return {

        "team_3pm": as_number(
            find_stat(
                team_stats,
                [
                    "threePointFieldGoalsMade",
                    "3PT Made",
                    "3PM",
                    "threePointersMade"
                ]
            )
        ),

        "opp_3pm": as_number(
            find_stat(
                opp_stats,
                [
                    "threePointFieldGoalsMade",
                    "3PT Made",
                    "3PM",
                    "threePointersMade"
                ]
            )
        ),

        "team_turnovers": as_number(
            find_stat(
                team_stats,
                [
                    "turnovers",
                    "TO"
                ]
            )
        ),

        "opp_turnovers": as_number(
            find_stat(
                opp_stats,
                [
                    "turnovers",
                    "TO"
                ]
            )
        ),

        "team_rebounds": as_number(
            find_stat(
                team_stats,
                [
                    "totalRebounds",
                    "rebounds",
                    "REB"
                ]
            )
        ),

        "opp_rebounds": as_number(
            find_stat(
                opp_stats,
                [
                    "totalRebounds",
                    "rebounds",
                    "REB"
                ]
            )
        ),

        "team_assists": as_number(
            find_stat(
                team_stats,
                [
                    "assists",
                    "AST"
                ]
            )
        ),

        "team_fg_pct": parse_pct(
            find_stat(
                team_stats,
                [
                    "fieldGoalPct",
                    "field goal percentage",
                    "FG%"
                ]
            )
        ),

        "halftime_team":
            halftime_team,

        "halftime_opp":
            halftime_opp
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
        "type": "team_points",
        "threshold": 110,
        "a1": "110 Plus Points",
        "a2": "Under 110",
        "evidence_label": "Team points",
        "question":
            "Is scoring 110 or more points associated with whether the team wins?"
    },

    "More 3-pointers than opponent": {
        "type": "more",
        "m1": "team_3pm",
        "m2": "opp_3pm",
        "a1": "More 3-Pointers",
        "a2": "Not More 3-Pointers",
        "evidence_label":
            "Team 3PM vs. opponent 3PM",
        "question":
            "Is making more three-pointers than the opponent associated with whether the team wins?"
    },

    "Fewer turnovers than opponent": {
        "type": "fewer",
        "m1": "team_turnovers",
        "m2": "opp_turnovers",
        "a1": "Fewer Turnovers",
        "a2": "Not Fewer Turnovers",
        "evidence_label":
            "Team turnovers vs. opponent turnovers",
        "question":
            "Is having fewer turnovers than the opponent associated with whether the team wins?"
    },

    "Field goal percentage at least 50%": {
        "type": "metric",
        "metric": "team_fg_pct",
        "threshold": 50,
        "a1": "50 Percent Plus FG",
        "a2": "Under 50 Percent",
        "evidence_label": "Team FG%",
        "question":
            "Is shooting at least 50 percent from the field associated with whether the team wins?"
    },

    "More rebounds than opponent": {
        "type": "more",
        "m1": "team_rebounds",
        "m2": "opp_rebounds",
        "a1": "More Rebounds",
        "a2": "Not More Rebounds",
        "evidence_label":
            "Team rebounds vs. opponent rebounds",
        "question":
            "Is outrebounding the opponent associated with whether the team wins?"
    },

    "Led at halftime": {
        "type": "more",
        "m1": "halftime_team",
        "m2": "halftime_opp",
        "a1": "Led at Halftime",
        "a2": "Did Not Lead at Halftime",
        "evidence_label":
            "Halftime score",
        "question":
            "Does leading at halftime appear associated with whether the team wins?"
    },

    "Made at least 12 three-pointers": {
        "type": "metric",
        "metric": "team_3pm",
        "threshold": 12,
        "a1": "12 Plus 3-Pointers",
        "a2": "Fewer Than 12",
        "evidence_label":
            "Team 3PM",
        "question":
            "Is making 12 or more three-pointers associated with whether the team wins?"
    },

    "Held opponent under 110 points": {
        "type": "opp_under",
        "threshold": 110,
        "a1": "Opponent Under 110",
        "a2": "Opponent 110 Plus",
        "evidence_label":
            "Opponent points",
        "question":
            "Is holding the opponent under 110 points associated with whether the team wins?"
    },

    "At least 25 assists": {
        "type": "metric",
        "metric": "team_assists",
        "threshold": 25,
        "a1": "25 Plus Assists",
        "a2": "Under 25 Assists",
        "evidence_label":
            "Team assists",
        "question":
            "Are 25 or more team assists associated with whether the team wins?"
    }
}


def nba_classify(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_points":

        return (
            cfg["a1"]
            if row["team_score"] >= cfg["threshold"]
            else cfg["a2"]
        )

    if t == "opp_under":

        return (
            cfg["a1"]
            if row["opp_score"] < cfg["threshold"]
            else cfg["a2"]
        )

    if t == "metric":

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
            if float(v) >= cfg["threshold"]
            else cfg["a2"]
        )

    a = row.get(
        cfg["m1"]
    )

    b = row.get(
        cfg["m2"]
    )

    if (
        a is None
        or b is None
        or pd.isna(a)
        or pd.isna(b)
    ):
        return None

    if t == "more":

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


def nba_evidence(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_points":
        return str(
            row["team_score"]
        )

    if t == "opp_under":
        return str(
            row["opp_score"]
        )

    if t == "metric":

        v = row.get(
            cfg["metric"]
        )

        if (
            v is None
            or pd.isna(v)
        ):
            return "Unavailable"

        if cfg["metric"] == "team_fg_pct":

            return (
                f"{float(v):.1f}%"
            )

        return f"{float(v):g}"

    a = row.get(
        cfg["m1"]
    )

    b = row.get(
        cfg["m2"]
    )

    if (
        a is None
        or b is None
        or pd.isna(a)
        or pd.isna(b)
    ):
        return "Unavailable"

    if "halftime" in cfg["m1"]:

        return (
            f"{float(a):g} – "
            f"{float(b):g}"
        )

    return (
        f"{float(a):g} vs. "
        f"{float(b):g}"
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def build_nba(
    team_id,
    season,
    sample,
    variable
):

    cores = []

    for e in get_nba_schedule(
        team_id,
        season
    ):

        core = nba_core(
            e,
            team_id
        )

        if core:
            cores.append(core)

    cores = sorted(
        cores,
        key=lambda g:
            pd.to_datetime(
                g["date"]
            )
    )[:sample]

    cfg = NBA_PRESETS[
        variable
    ]

    rows = []

    for core in cores:

        row = dict(core)

        if cfg["type"] in (
            "metric",
            "more",
            "fewer"
        ):

            try:

                row.update(
                    nba_metrics(
                        get_nba_summary(
                            core[
                                "event_id"
                            ]
                        ),
                        team_id
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            nba_classify(
                row,
                cfg
            )
        )

        row["evidence"] = (
            nba_evidence(
                row,
                cfg
            )
        )

        rows.append(row)

    return pd.DataFrame(
        rows
    )


# ============================================================
# MLB
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def get_mlb_teams(
    season
):

    data = safe_get(
        f"{MLB_BASE}/teams",
        params={
            "sportId": 1,
            "season": season
        }
    )

    return sorted(
        [
            {
                "id": str(t["id"]),
                "name": t["name"]
            }
            for t in data.get(
                "teams",
                []
            )
            if (
                t.get("id")
                and t.get("name")
            )
        ],
        key=lambda x:
            x["name"]
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
        f"{MLB_BASE}/schedule",
        params={
            "sportId": 1,
            "teamId": team_id,
            "season": season,
            "gameType": "R"
        }
    )

    return [
        game
        for day
        in data.get(
            "dates",
            []
        )
        for game
        in day.get(
            "games",
            []
        )
    ]


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_mlb_feed(
    game_pk
):

    return safe_get(
        f"{MLB_BASE}.1/game/{game_pk}/feed/live"
    )


def mlb_core(
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

        team = home
        opp = away
        side = "home"
        opp_side = "away"
        home_away = "Home"

    elif str(team_id) == away_id:

        team = away
        opp = home
        side = "away"
        opp_side = "home"
        home_away = "Away"

    else:
        return None

    try:

        team_score = int(
            team.get("score")
        )

        opp_score = int(
            opp.get("score")
        )

    except Exception:
        return None

    try:

        date = (
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

        date = str(
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

        "date": date,

        "opponent": (
            opp.get(
                "team",
                {}
            ).get(
                "name",
                "Opponent"
            )
        ),

        "home_away":
            home_away,

        "team_side":
            side,

        "opp_side":
            opp_side,

        "team_score":
            team_score,

        "opp_score":
            opp_score,

        "result": (
            "Win"
            if team_score > opp_score
            else "Did Not Win"
        )
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


def mlb_scored_first(
    feed,
    side
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
        .get(
            "allPlays",
            []
        )
    )

    for play in plays:

        if (
            play.get(
                "about",
                {}
            ).get(
                "isScoringPlay"
            ) is True
        ):

            half = str(
                play.get(
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

            return scoring_side == side

    return False


def mlb_quality_start(
    feed,
    side
):

    box = (
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
    )

    pitcher_ids = box.get(
        "pitchers",
        []
    )

    if not pitcher_ids:

        return None, None, None

    starter = (
        box
        .get(
            "players",
            {}
        )
        .get(
            f"ID{pitcher_ids[0]}",
            {}
        )
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
        starter.get(
            "inningsPitched"
        )
    )

    er = as_number(
        starter.get(
            "earnedRuns"
        )
    )

    if (
        ip is None
        or er is None
    ):

        return (
            None,
            ip,
            er
        )

    return (
        ip >= 6
        and er <= 3,
        ip,
        er
    )


def mlb_metrics(
    feed,
    core
):

    stats = mlb_team_stats(
        feed,
        core[
            "team_side"
        ]
    )

    batting = stats.get(
        "batting",
        {}
    )

    fielding = stats.get(
        "fielding",
        {}
    )

    pitching = stats.get(
        "pitching",
        {}
    )

    qs, ip, er = (
        mlb_quality_start(
            feed,
            core[
                "team_side"
            ]
        )
    )

    return {

        "home_runs":
            as_number(
                batting.get(
                    "homeRuns"
                )
            ),

        "hits":
            as_number(
                batting.get(
                    "hits"
                )
            ),

        "walks":
            as_number(
                batting.get(
                    "baseOnBalls"
                )
            ),

        "errors":
            as_number(
                fielding.get(
                    "errors"
                )
            ),

        "pitching_strikeouts":
            as_number(
                pitching.get(
                    "strikeOuts"
                )
            ),

        "scored_first":
            mlb_scored_first(
                feed,
                core[
                    "team_side"
                ]
            ),

        "quality_start":
            qs,

        "starter_ip":
            ip,

        "starter_er":
            er
    }


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
        "type": "metric",
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
        "type": "metric",
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
        "type": "team_score",
        "threshold": 5,
        "a1": "5 Plus Runs",
        "a2": "Under 5 Runs",
        "evidence_label":
            "Team runs",
        "question":
            "Is scoring five or more runs associated with whether the team wins?"
    },

    "At least 10 hits": {
        "type": "metric",
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
        "type": "metric",
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
        "type": "metric",
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
        "type": "metric",
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
    }
}


def mlb_classify(
    row,
    cfg
):

    if cfg["type"] == "home_away":
        return row["home_away"]

    if cfg["type"] == "team_score":

        return (
            cfg["a1"]
            if row["team_score"] >= cfg["threshold"]
            else cfg["a2"]
        )

    v = row.get(
        cfg["metric"]
    )

    if (
        v is None
        or pd.isna(v)
    ):
        return None

    if cfg["type"] == "boolean":

        return (
            cfg["a1"]
            if bool(v)
            else cfg["a2"]
        )

    return (
        cfg["a1"]
        if float(v) >= cfg["threshold"]
        else cfg["a2"]
    )


def mlb_evidence(
    row,
    cfg
):

    if cfg["type"] == "home_away":
        return row["home_away"]

    if cfg["type"] == "team_score":
        return str(
            row["team_score"]
        )

    v = row.get(
        cfg["metric"]
    )

    if (
        v is None
        or pd.isna(v)
    ):
        return "Unavailable"

    if cfg["metric"] == "scored_first":

        return (
            "Team scored first"
            if v
            else "Opponent scored first"
        )

    if cfg["metric"] == "quality_start":

        return (
            f"{row.get('starter_ip'):g} IP / "
            f"{row.get('starter_er'):g} ER"
        )

    return f"{float(v):g}"


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def build_mlb(
    team_id,
    season,
    sample,
    variable
):

    cores = []

    for game in get_mlb_schedule(
        team_id,
        int(season)
    ):

        state = str(
            game.get(
                "status",
                {}
            ).get(
                "abstractGameState",
                ""
            )
        ).lower()

        if state != "final":
            continue

        core = mlb_core(
            game,
            team_id
        )

        if core:
            cores.append(core)

    cores = sorted(
        cores,
        key=lambda g:
            pd.to_datetime(
                g["date"]
            )
    )[:sample]

    cfg = MLB_PRESETS[
        variable
    ]

    rows = []

    for core in cores:

        row = dict(core)

        if cfg["type"] not in (
            "home_away",
            "team_score"
        ):

            try:

                row.update(
                    mlb_metrics(
                        get_mlb_feed(
                            core[
                                "game_pk"
                            ]
                        ),
                        core
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            mlb_classify(
                row,
                cfg
            )
        )

        row["evidence"] = (
            mlb_evidence(
                row,
                cfg
            )
        )

        rows.append(row)

    return pd.DataFrame(
        rows
    )


# ============================================================
# NHL
# ============================================================

NHL_TEAMS = [

    ("Anaheim Ducks", "ANA"),
    ("Boston Bruins", "BOS"),
    ("Buffalo Sabres", "BUF"),
    ("Calgary Flames", "CGY"),
    ("Carolina Hurricanes", "CAR"),
    ("Chicago Blackhawks", "CHI"),
    ("Colorado Avalanche", "COL"),
    ("Columbus Blue Jackets", "CBJ"),
    ("Dallas Stars", "DAL"),
    ("Detroit Red Wings", "DET"),
    ("Edmonton Oilers", "EDM"),
    ("Florida Panthers", "FLA"),
    ("Los Angeles Kings", "LAK"),
    ("Minnesota Wild", "MIN"),
    ("Montreal Canadiens", "MTL"),
    ("Nashville Predators", "NSH"),
    ("New Jersey Devils", "NJD"),
    ("New York Islanders", "NYI"),
    ("New York Rangers", "NYR"),
    ("Ottawa Senators", "OTT"),
    ("Philadelphia Flyers", "PHI"),
    ("Pittsburgh Penguins", "PIT"),
    ("San Jose Sharks", "SJS"),
    ("Seattle Kraken", "SEA"),
    ("St. Louis Blues", "STL"),
    ("Tampa Bay Lightning", "TBL"),
    ("Toronto Maple Leafs", "TOR"),
    ("Utah Mammoth", "UTA"),
    ("Vancouver Canucks", "VAN"),
    ("Vegas Golden Knights", "VGK"),
    ("Washington Capitals", "WSH"),
    ("Winnipeg Jets", "WPG")
]


def get_nhl_teams():

    return [
        {
            "id": abbr,
            "name": name
        }
        for name, abbr
        in NHL_TEAMS
    ]


def nhl_season_id(
    label
):

    m = re.match(
        r"(\d{4})-(\d{2})",
        label
    )

    if not m:
        return str(label)

    start = int(
        m.group(1)
    )

    return (
        f"{start}"
        f"{start + 1}"
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def get_nhl_schedule(
    abbr,
    season
):

    data = safe_get(
        f"{NHL_BASE}/club-schedule-season/{abbr}/{nhl_season_id(season)}"
    )

    return data.get(
        "games",
        []
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_nhl_boxscore(
    game_id
):

    return safe_get(
        f"{NHL_BASE}/gamecenter/{game_id}/boxscore"
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_nhl_landing(
    game_id
):

    return safe_get(
        f"{NHL_BASE}/gamecenter/{game_id}/landing"
    )


def nhl_core(
    game,
    abbr
):

    if game.get("gameType") != 2:
        return None

    away = game.get(
        "awayTeam",
        {}
    )

    home = game.get(
        "homeTeam",
        {}
    )

    away_abbr = away.get(
        "abbrev"
    )

    home_abbr = home.get(
        "abbrev"
    )

    if abbr == home_abbr:

        team = home
        opp = away
        side = "homeTeam"
        home_away = "Home"

    elif abbr == away_abbr:

        team = away
        opp = home
        side = "awayTeam"
        home_away = "Away"

    else:
        return None

    team_score = as_number(
        team.get(
            "score"
        )
    )

    opp_score = as_number(
        opp.get(
            "score"
        )
    )

    state = str(
        game.get(
            "gameState",
            ""
        )
    ).upper()

    if (
        team_score is None
        or opp_score is None
        or state not in (
            "FINAL",
            "OFF"
        )
    ):
        return None

    try:

        date = (
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

        date = str(
            game.get(
                "gameDate",
                ""
            )
        )

    opp_name = (
        opp.get(
            "placeName",
            {}
        ).get(
            "default",
            opp.get(
                "abbrev",
                "Opponent"
            )
        )
        + " "
        + opp.get(
            "commonName",
            {}
        ).get(
            "default",
            ""
        )
    ).strip()

    return {
        "game_id": str(
            game.get(
                "id",
                ""
            )
        ),

        "date":
            date,

        "opponent":
            opp_name,

        "home_away":
            home_away,

        "team_side":
            side,

        "team_score":
            int(team_score),

        "opp_score":
            int(opp_score),

        "result": (
            "Win"
            if team_score > opp_score
            else "Did Not Win"
        )
    }


def goal_team_abbr(
    goal
):

    value = goal.get(
        "teamAbbrev"
    )

    if isinstance(
        value,
        dict
    ):
        return value.get(
            "default"
        )

    if isinstance(
        value,
        str
    ):
        return value

    return goal.get(
        "eventOwnerTeamAbbrev"
    )


def nhl_scoring_metrics(
    landing,
    abbr
):

    first_goal = None

    first_period_team = 0
    first_period_opp = 0

    power_play_goals = 0

    for block in landing.get(
        "scoring",
        []
    ):

        period = (
            block
            .get(
                "periodDescriptor",
                {}
            )
            .get(
                "number"
            )
        )

        for goal in block.get(
            "goals",
            []
        ):

            goal_abbr = goal_team_abbr(
                goal
            )

            if first_goal is None:
                first_goal = goal_abbr

            if period == 1:

                if goal_abbr == abbr:
                    first_period_team += 1

                else:
                    first_period_opp += 1

            strength = str(
                goal.get(
                    "strength",
                    ""
                )
            ).upper()

            if (
                goal_abbr == abbr
                and (
                    "PP" in strength
                    or strength == "POWER PLAY"
                )
            ):

                power_play_goals += 1

    return {

        "scored_first": (
            first_goal == abbr
            if first_goal
            else None
        ),

        "first_period_team":
            first_period_team,

        "first_period_opp":
            first_period_opp,

        "power_play_goals":
            power_play_goals
    }


def nhl_goalie_save_pct(
    box,
    side
):

    goalies = (
        box
        .get(
            "playerByGameStats",
            {}
        )
        .get(
            side,
            {}
        )
        .get(
            "goalies",
            []
        )
    )

    total_saves = 0
    total_shots = 0

    for goalie in goalies:

        saves = as_number(
            goalie.get(
                "saves"
            )
        )

        shots_against = as_number(
            goalie.get(
                "shotsAgainst"
            )
        )

        if (
            saves is not None
            and shots_against is not None
        ):

            total_saves += saves
            total_shots += shots_against

        else:

            value = str(
                goalie.get(
                    "saveShotsAgainst",
                    ""
                )
            )

            m = re.match(
                r"(\d+)\s*/\s*(\d+)",
                value
            )

            if m:

                total_saves += float(
                    m.group(1)
                )

                total_shots += float(
                    m.group(2)
                )

    if total_shots == 0:
        return None

    return total_saves / total_shots


def nhl_metrics(
    box,
    landing,
    core,
    abbr
):

    team = box.get(
        core[
            "team_side"
        ],
        {}
    )

    opp_side = (
        "awayTeam"
        if core[
            "team_side"
        ] == "homeTeam"
        else "homeTeam"
    )

    opp = box.get(
        opp_side,
        {}
    )

    metrics = nhl_scoring_metrics(
        landing,
        abbr
    )

    metrics.update({

        "team_sog":
            as_number(
                team.get(
                    "sog"
                )
            ),

        "opp_sog":
            as_number(
                opp.get(
                    "sog"
                )
            ),

        "save_pct":
            nhl_goalie_save_pct(
                box,
                core[
                    "team_side"
                ]
            )
    })

    return metrics


NHL_PRESETS = {

    "Home vs. Away": {
        "type": "home_away",
        "a1": "Home",
        "a2": "Away",
        "evidence_label":
            "Location",
        "question":
            "Does playing at home appear associated with whether the team wins?"
    },

    "Scored first": {
        "type": "boolean",
        "metric": "scored_first",
        "a1": "Scored First",
        "a2": "Did Not Score First",
        "evidence_label":
            "First goal",
        "question":
            "Does scoring the first goal appear associated with whether the team wins?"
    },

    "Scored at least 4 goals": {
        "type": "team_score",
        "threshold": 4,
        "a1": "4 Plus Goals",
        "a2": "Under 4 Goals",
        "evidence_label":
            "Team goals",
        "question":
            "Is scoring four or more goals associated with whether the team wins?"
    },

    "More shots than opponent": {
        "type": "more",
        "m1": "team_sog",
        "m2": "opp_sog",
        "a1": "More Shots",
        "a2": "Not More Shots",
        "evidence_label":
            "Team SOG vs. opponent SOG",
        "question":
            "Is outshooting the opponent associated with whether the team wins?"
    },

    "Scored a power-play goal": {
        "type": "metric",
        "metric":
            "power_play_goals",
        "threshold": 1,
        "a1":
            "Scored 1 Plus Power-Play Goal",
        "a2":
            "Scored 0",
        "evidence_label":
            "Power-play goals",
        "question":
            "Is scoring a power-play goal associated with whether the team wins?"
    },

    "Team save percentage .900 or higher": {
        "type": "metric",
        "metric": "save_pct",
        "threshold": 0.900,
        "a1":
            ".900 Plus Save Percentage",
        "a2":
            "Below .900",
        "evidence_label":
            "Team save percentage",
        "question":
            "Is a team save percentage of .900 or higher associated with whether the team wins?"
    },

    "Led after the 1st period": {
        "type": "more",
        "m1":
            "first_period_team",
        "m2":
            "first_period_opp",
        "a1":
            "Led After 1st Period",
        "a2":
            "Did Not Lead",
        "evidence_label":
            "1st-period score",
        "question":
            "Does leading after the first period appear associated with whether the team wins?"
    },

    "Held opponent to 2 or fewer goals": {
        "type": "opp_at_most",
        "threshold": 2,
        "a1":
            "Opponent 2 or Fewer Goals",
        "a2":
            "Opponent 3 Plus",
        "evidence_label":
            "Opponent goals",
        "question":
            "Is holding the opponent to two or fewer goals associated with whether the team wins?"
    },

    "Scored at least 3 goals": {
        "type": "team_score",
        "threshold": 3,
        "a1":
            "3 Plus Goals",
        "a2":
            "Under 3 Goals",
        "evidence_label":
            "Team goals",
        "question":
            "Is scoring at least three goals associated with whether the team wins?"
    },

    "Allowed 30 or fewer shots": {
        "type":
            "opp_metric_at_most",
        "metric":
            "opp_sog",
        "threshold":
            30,
        "a1":
            "Allowed 30 or Fewer Shots",
        "a2":
            "Allowed 31 Plus",
        "evidence_label":
            "Opponent SOG",
        "question":
            "Is allowing 30 or fewer shots on goal associated with whether the team wins?"
    }
}


def nhl_classify(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_score":

        return (
            cfg["a1"]
            if row["team_score"] >= cfg["threshold"]
            else cfg["a2"]
        )

    if t == "opp_at_most":

        return (
            cfg["a1"]
            if row["opp_score"] <= cfg["threshold"]
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

    if t == "metric":

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
            if float(v) >= cfg["threshold"]
            else cfg["a2"]
        )

    if t == "opp_metric_at_most":

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
            if float(v) <= cfg["threshold"]
            else cfg["a2"]
        )

    a = row.get(
        cfg["m1"]
    )

    b = row.get(
        cfg["m2"]
    )

    if (
        a is None
        or b is None
        or pd.isna(a)
        or pd.isna(b)
    ):
        return None

    return (
        cfg["a1"]
        if float(a) > float(b)
        else cfg["a2"]
    )


def nhl_evidence(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":
        return row["home_away"]

    if t == "team_score":
        return str(
            row["team_score"]
        )

    if t == "opp_at_most":
        return str(
            row["opp_score"]
        )

    if t == "boolean":

        return (
            "Team scored first"
            if row.get(
                cfg["metric"]
            )
            else "Opponent scored first"
        )

    if t in (
        "metric",
        "opp_metric_at_most"
    ):

        v = row.get(
            cfg["metric"]
        )

        if (
            v is None
            or pd.isna(v)
        ):
            return "Unavailable"

        if cfg["metric"] == "save_pct":

            return (
                f"{float(v):.3f}"
            )

        return f"{float(v):g}"

    a = row.get(
        cfg["m1"]
    )

    b = row.get(
        cfg["m2"]
    )

    if (
        a is None
        or b is None
        or pd.isna(a)
        or pd.isna(b)
    ):
        return "Unavailable"

    return (
        f"{float(a):g} vs. "
        f"{float(b):g}"
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def build_nhl(
    abbr,
    season,
    sample,
    variable
):

    cores = []

    for game in get_nhl_schedule(
        abbr,
        season
    ):

        core = nhl_core(
            game,
            abbr
        )

        if core:
            cores.append(core)

    cores = sorted(
        cores,
        key=lambda g:
            pd.to_datetime(
                g["date"]
            )
    )[:sample]

    cfg = NHL_PRESETS[
        variable
    ]

    rows = []

    for core in cores:

        row = dict(core)

        if cfg["type"] not in (
            "home_away",
            "team_score",
            "opp_at_most"
        ):

            try:

                row.update(
                    nhl_metrics(
                        get_nhl_boxscore(
                            core[
                                "game_id"
                            ]
                        ),
                        get_nhl_landing(
                            core[
                                "game_id"
                            ]
                        ),
                        core,
                        abbr
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            nhl_classify(
                row,
                cfg
            )
        )

        row["evidence"] = (
            nhl_evidence(
                row,
                cfg
            )
        )

        rows.append(row)

    return pd.DataFrame(
        rows
    )


# ============================================================
# MLS
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def get_mls_teams():

    data = safe_get(
        f"{MLS_BASE}/teams"
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

                team = item.get(
                    "team",
                    {}
                )

                if (
                    team.get("id")
                    and team.get("displayName")
                ):

                    teams.append({
                        "id":
                            str(
                                team["id"]
                            ),

                        "name":
                            team[
                                "displayName"
                            ]
                    })

    return sorted(
        teams,
        key=lambda x:
            x["name"]
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def get_mls_schedule(
    team_id,
    season
):

    data = safe_get(
        f"{MLS_BASE}/teams/{team_id}/schedule",
        params={
            "season":
                int(season)
        }
    )

    return data.get(
        "events",
        []
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_mls_summary(
    event_id
):

    return safe_get(
        f"{MLS_BASE}/summary",
        params={
            "event":
                event_id
        }
    )


def soccer_score(
    value
):

    if isinstance(
        value,
        (int, float)
    ):
        return float(value)

    if isinstance(
        value,
        str
    ):

        try:
            return float(value)

        except Exception:
            return None

    if isinstance(
        value,
        dict
    ):

        for key in [
            "value",
            "displayValue",
            "score"
        ]:

            if key in value:

                try:
                    return float(
                        value[key]
                    )

                except Exception:
                    pass

    return None


def mls_core(
    event,
    team_id
):

    comps = event.get(
        "competitions",
        []
    )

    if not comps:
        return None

    competition = comps[0]

    status = (
        competition
        .get(
            "status",
            {}
        )
        .get(
            "type",
            {}
        )
    )

    completed = (
        status.get(
            "completed"
        ) is True
        or str(
            status.get(
                "state",
                ""
            )
        ).lower() == "post"
    )

    if not completed:
        return None

    competitors = competition.get(
        "competitors",
        []
    )

    team = None
    opp = None

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
            team = c

        else:
            opp = c

    if not team or not opp:
        return None

    team_score = soccer_score(
        team.get(
            "score"
        )
    )

    opp_score = soccer_score(
        opp.get(
            "score"
        )
    )

    if (
        team_score is None
        or opp_score is None
    ):
        return None

    try:

        date = (
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

        date = str(
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

        "date":
            date,

        "opponent": (
            opp.get(
                "team",
                {}
            ).get(
                "displayName",
                "Opponent"
            )
        ),

        "home_away": (
            "Home"
            if team.get(
                "homeAway"
            ) == "home"
            else "Away"
        ),

        "team_score":
            int(team_score),

        "opp_score":
            int(opp_score),

        "result": (
            "Win"
            if team_score > opp_score
            else "Did Not Win"
        )
    }


def mls_box_team(
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

    for box in teams:

        tid = str(
            box.get(
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
            return box

        if (
            opponent
            and tid
            and tid != str(team_id)
        ):
            return box

    return None


def mls_stat_map(
    team_box
):

    out = {}

    if not team_box:
        return out

    for stat in team_box.get(
        "statistics",
        []
    ):

        value = stat.get(
            "displayValue",
            stat.get(
                "value"
            )
        )

        for key in [
            "name",
            "displayName",
            "label",
            "abbreviation"
        ]:

            candidate = stat.get(
                key
            )

            if candidate:

                out[
                    norm(candidate)
                ] = value

    return out


def mls_find_stat(
    stats,
    names
):

    for name in names:

        key = norm(name)

        if key in stats:
            return stats[key]

    for stored_key, value in stats.items():

        for name in names:

            if norm(name) in stored_key:
                return value

    return None


def mls_scored_first(
    summary,
    team_id
):

    scoring_plays = summary.get(
        "scoringPlays",
        []
    )

    if scoring_plays:

        first = scoring_plays[0]

        team = first.get(
            "team",
            {}
        )

        scorer_team_id = str(
            team.get(
                "id",
                ""
            )
        )

        if scorer_team_id:

            return (
                scorer_team_id
                == str(team_id)
            )

    plays = summary.get(
        "plays",
        []
    )

    for play in plays:

        scoring = (
            play.get(
                "scoringPlay"
            ) is True
            or play.get(
                "scoreValue",
                0
            ) not in (
                None,
                0
            )
        )

        if scoring:

            play_team_id = str(
                play.get(
                    "team",
                    {}
                ).get(
                    "id",
                    ""
                )
            )

            if play_team_id:

                return (
                    play_team_id
                    == str(team_id)
                )

    return None


def mls_halftime_score(
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

    team_halftime = None
    opp_halftime = None

    for competitor in comps[0].get(
        "competitors",
        []
    ):

        linescores = competitor.get(
            "linescores",
            []
        )

        if not linescores:
            continue

        try:

            first_half = float(
                linescores[0].get(
                    "value",
                    0
                )
            )

        except Exception:

            first_half = None

        cid = str(
            competitor.get(
                "team",
                {}
            ).get(
                "id",
                ""
            )
        )

        if cid == str(team_id):
            team_halftime = first_half

        else:
            opp_halftime = first_half

    return (
        team_halftime,
        opp_halftime
    )


def mls_metrics(
    summary,
    team_id
):

    team_stats = mls_stat_map(
        mls_box_team(
            summary,
            team_id
        )
    )

    opp_stats = mls_stat_map(
        mls_box_team(
            summary,
            team_id,
            True
        )
    )

    team_shots = as_number(
        mls_find_stat(
            team_stats,
            [
                "totalShots",
                "shots",
                "Total Shots"
            ]
        )
    )

    opp_shots = as_number(
        mls_find_stat(
            opp_stats,
            [
                "totalShots",
                "shots",
                "Total Shots"
            ]
        )
    )

    shots_on_target = as_number(
        mls_find_stat(
            team_stats,
            [
                "shotsOnTarget",
                "Shots on Target",
                "shots on goal"
            ]
        )
    )

    possession = parse_pct(
        mls_find_stat(
            team_stats,
            [
                "possessionPct",
                "possession",
                "Possession"
            ]
        )
    )

    halftime_team, halftime_opp = (
        mls_halftime_score(
            summary,
            team_id
        )
    )

    return {

        "team_shots":
            team_shots,

        "opp_shots":
            opp_shots,

        "shots_on_target":
            shots_on_target,

        "possession_pct":
            possession,

        "scored_first":
            mls_scored_first(
                summary,
                team_id
            ),

        "halftime_team":
            halftime_team,

        "halftime_opp":
            halftime_opp
    }


MLS_PRESETS = {

    "Home vs. Away": {

        "type":
            "home_away",

        "a1":
            "Home",

        "a2":
            "Away",

        "evidence_label":
            "Location",

        "question":
            "Does playing at home appear associated with whether the team wins?"
    },

    "Scored first": {

        "type":
            "boolean",

        "metric":
            "scored_first",

        "a1":
            "Scored First",

        "a2":
            "Did Not Score First",

        "evidence_label":
            "First goal",

        "question":
            "Does scoring first appear associated with whether the team wins?"
    },

    "Scored at least 2 goals": {

        "type":
            "team_score",

        "threshold":
            2,

        "a1":
            "2 Plus Goals",

        "a2":
            "Fewer Than 2 Goals",

        "evidence_label":
            "Team goals",

        "question":
            "Is scoring two or more goals associated with whether the team wins?"
    },

    "At least 55% possession": {

        "type":
            "metric",

        "metric":
            "possession_pct",

        "threshold":
            55,

        "a1":
            "55 Percent Plus Possession",

        "a2":
            "Under 55 Percent",

        "evidence_label":
            "Possession %",

        "question":
            "Is having at least 55 percent possession associated with whether the team wins?"
    },

    "At least 5 shots on target": {

        "type":
            "metric",

        "metric":
            "shots_on_target",

        "threshold":
            5,

        "a1":
            "5 Plus Shots on Target",

        "a2":
            "Fewer Than 5",

        "evidence_label":
            "Shots on target",

        "question":
            "Are five or more shots on target associated with whether the team wins?"
    },

    "Clean sheet": {

        "type":
            "opp_at_most",

        "threshold":
            0,

        "a1":
            "Clean Sheet",

        "a2":
            "Allowed 1 Plus Goal",

        "evidence_label":
            "Opponent goals",

        "question":
            "Is keeping a clean sheet associated with whether the team wins?"
    },

    "At least 10 total shots": {

        "type":
            "metric",

        "metric":
            "team_shots",

        "threshold":
            10,

        "a1":
            "10 Plus Shots",

        "a2":
            "Under 10 Shots",

        "evidence_label":
            "Team shots",

        "question":
            "Are 10 or more total shots associated with whether the team wins?"
    },

    "Led at halftime": {

        "type":
            "more",

        "m1":
            "halftime_team",

        "m2":
            "halftime_opp",

        "a1":
            "Led at Halftime",

        "a2":
            "Did Not Lead at Halftime",

        "evidence_label":
            "Halftime score",

        "question":
            "Does leading at halftime appear associated with whether the team wins?"
    },

    "Held opponent under 2 goals": {

        "type":
            "opp_under",

        "threshold":
            2,

        "a1":
            "Opponent 0 or 1 Goal",

        "a2":
            "Opponent 2 Plus Goals",

        "evidence_label":
            "Opponent goals",

        "question":
            "Is holding the opponent under two goals associated with whether the team wins?"
    },

    "More shots than opponent": {

        "type":
            "more",

        "m1":
            "team_shots",

        "m2":
            "opp_shots",

        "a1":
            "More Shots",

        "a2":
            "Not More Shots",

        "evidence_label":
            "Team shots vs. opponent shots",

        "question":
            "Is taking more total shots than the opponent associated with whether the team wins?"
    }
}


def mls_classify(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":

        return row[
            "home_away"
        ]

    if t == "team_score":

        return (
            cfg["a1"]
            if row[
                "team_score"
            ] >= cfg[
                "threshold"
            ]
            else cfg["a2"]
        )

    if t == "opp_at_most":

        return (
            cfg["a1"]
            if row[
                "opp_score"
            ] <= cfg[
                "threshold"
            ]
            else cfg["a2"]
        )

    if t == "opp_under":

        return (
            cfg["a1"]
            if row[
                "opp_score"
            ] < cfg[
                "threshold"
            ]
            else cfg["a2"]
        )

    if t == "boolean":

        value = row.get(
            cfg["metric"]
        )

        if value is None:
            return None

        return (
            cfg["a1"]
            if bool(value)
            else cfg["a2"]
        )

    if t == "metric":

        value = row.get(
            cfg["metric"]
        )

        if (
            value is None
            or pd.isna(value)
        ):
            return None

        return (
            cfg["a1"]
            if float(value)
            >= cfg["threshold"]
            else cfg["a2"]
        )

    a = row.get(
        cfg["m1"]
    )

    b = row.get(
        cfg["m2"]
    )

    if (
        a is None
        or b is None
        or pd.isna(a)
        or pd.isna(b)
    ):
        return None

    return (
        cfg["a1"]
        if float(a) > float(b)
        else cfg["a2"]
    )


def mls_evidence(
    row,
    cfg
):

    t = cfg["type"]

    if t == "home_away":

        return row[
            "home_away"
        ]

    if t == "team_score":

        return str(
            row[
                "team_score"
            ]
        )

    if t in (
        "opp_at_most",
        "opp_under"
    ):

        return str(
            row[
                "opp_score"
            ]
        )

    if t == "boolean":

        value = row.get(
            cfg["metric"]
        )

        if value is None:

            return "Unavailable"

        return (
            "Team scored first"
            if value
            else "Opponent scored first"
        )

    if t == "metric":

        value = row.get(
            cfg["metric"]
        )

        if (
            value is None
            or pd.isna(value)
        ):
            return "Unavailable"

        if cfg["metric"] == "possession_pct":

            return (
                f"{float(value):.1f}%"
            )

        return (
            f"{float(value):g}"
        )

    a = row.get(
        cfg["m1"]
    )

    b = row.get(
        cfg["m2"]
    )

    if (
        a is None
        or b is None
        or pd.isna(a)
        or pd.isna(b)
    ):

        return "Unavailable"

    if "halftime" in cfg["m1"]:

        return (
            f"{float(a):g} – "
            f"{float(b):g}"
        )

    return (
        f"{float(a):g} vs. "
        f"{float(b):g}"
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def build_mls(
    team_id,
    season,
    sample,
    variable
):

    cores = []

    for event in get_mls_schedule(
        team_id,
        season
    ):

        core = mls_core(
            event,
            team_id
        )

        if core:
            cores.append(core)

    cores = sorted(
        cores,
        key=lambda g:
            pd.to_datetime(
                g["date"]
            )
    )[:sample]

    cfg = MLS_PRESETS[
        variable
    ]

    rows = []

    for core in cores:

        row = dict(core)

        if cfg["type"] not in (
            "home_away",
            "team_score",
            "opp_at_most",
            "opp_under"
        ):

            try:

                summary = get_mls_summary(
                    core[
                        "event_id"
                    ]
                )

                row.update(
                    mls_metrics(
                        summary,
                        team_id
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            mls_classify(
                row,
                cfg
            )
        )

        row["evidence"] = (
            mls_evidence(
                row,
                cfg
            )
        )

        rows.append(
            row
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# SPORT CONFIGURATION
# ============================================================

SPORTS = [
    "NBA",
    "MLB",
    "NHL",
    "MLS"
]


SEASONS = {

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
    ],

    "NHL": [
        "2025-26",
        "2024-25",
        "2023-24",
        "2022-23"
    ],

    "MLS": [
        "2025",
        "2024",
        "2023",
        "2022"
    ]
}


def presets_for(
    sport
):

    return {

        "NBA":
            NBA_PRESETS,

        "MLB":
            MLB_PRESETS,

        "NHL":
            NHL_PRESETS,

        "MLS":
            MLS_PRESETS

    }[sport]


def teams_for(
    sport,
    season
):

    if sport == "NBA":

        return get_nba_teams()

    if sport == "MLB":

        return get_mlb_teams(
            int(season)
        )

    if sport == "NHL":

        return get_nhl_teams()

    return get_mls_teams()


def build_data(
    sport,
    team_id,
    season,
    sample,
    variable
):

    if sport == "NBA":

        return build_nba(
            team_id,
            season,
            sample,
            variable
        )

    if sport == "MLB":

        return build_mlb(
            team_id,
            season,
            sample,
            variable
        )

    if sport == "NHL":

        return build_nhl(
            team_id,
            season,
            sample,
            variable
        )

    return build_mls(
        team_id,
        season,
        sample,
        variable
    )


# ============================================================
# HEADER
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
# TEACHER MODE
# ============================================================

if mode == "Teacher Assignment Builder":

    st.subheader(
        "Teacher Assignment Builder"
    )

    st.write(
        "Create a code that locks the sport, team, season, variable, and sample."
    )

    sport = st.selectbox(
        "Sport",
        SPORTS,
        key="teacher_sport"
    )

    season = st.selectbox(
        "Season",
        SEASONS[
            sport
        ],
        key="teacher_season"
    )

    try:

        teams = teams_for(
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
        team["name"]
        for team in teams
    ]

    presets = presets_for(
        sport
    )

    c1, c2 = st.columns(2)

    with c1:

        team = st.selectbox(
            "Team",
            team_names
        )

        variable = st.selectbox(
            "Categorical variable",
            list(
                presets.keys()
            )
        )

    with c2:

        sample = st.selectbox(
            "Sample size",
            [
                10,
                15,
                20
            ],
            index=2
        )

    cfg = presets[
        variable
    ]

    st.info(
        "Research question: "
        + cfg[
            "question"
        ].replace(
            "the team",
            team
        )
    )

    st.write(
        f"**Variable A categories:** "
        f"{cfg['a1']} / "
        f"{cfg['a2']}"
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
            "sport":
                sport,

            "team":
                team,

            "season":
                season,

            "variable":
                variable,

            "sample":
                sample
        }

        st.success(
            "Assignment code created."
        )

        st.code(
            encode_task(
                payload
            ),
            language=None
        )

        st.caption(
            "Students paste this code into Student Research mode."
        )

    st.stop()


# ============================================================
# STUDENT MODE
# ============================================================

st.subheader(
    "Student Research"
)


task_code = st.text_input(
    "Have an assignment code? Paste it here (optional).",
    placeholder=
        "Paste teacher code here"
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


sport_default = (
    preset.get(
        "sport",
        "NBA"
    )
    if preset
    else "NBA"
)


if sport_default not in SPORTS:
    sport_default = "NBA"


sport = st.selectbox(
    "1. Sport",
    SPORTS,
    index=SPORTS.index(
        sport_default
    ),
    disabled=bool(
        preset
    )
)


season_options = SEASONS[
    sport
]


season_default = (
    preset.get(
        "season",
        season_options[0]
    )
    if preset
    else season_options[0]
)


if (
    season_default
    not in season_options
):
    season_default = (
        season_options[0]
    )


season = st.selectbox(
    "2. Season",
    season_options,
    index=season_options.index(
        season_default
    ),
    disabled=bool(
        preset
    )
)


try:

    teams = teams_for(
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
    team["name"]
    for team in teams
]


team_map = {
    team["name"]:
        team["id"]
    for team in teams
}


team_default = (
    preset.get(
        "team",
        team_names[0]
    )
    if preset
    else team_names[0]
)


if team_default not in team_names:
    team_default = team_names[0]


presets = presets_for(
    sport
)


variables = list(
    presets.keys()
)


variable_default = (
    preset.get(
        "variable",
        variables[0]
    )
    if preset
    else variables[0]
)


if (
    variable_default
    not in variables
):
    variable_default = (
        variables[0]
    )


sample_default = (
    preset.get(
        "sample",
        20
    )
    if preset
    else 20
)


if sample_default not in [
    10,
    15,
    20
]:
    sample_default = 20


c1, c2, c3 = (
    st.columns(3)
)


with c1:

    team = st.selectbox(
        "3. Team",
        team_names,
        index=team_names.index(
            team_default
        ),
        disabled=bool(
            preset
        )
    )


with c2:

    variable = st.selectbox(
        "4. Variable",
        variables,
        index=variables.index(
            variable_default
        ),
        disabled=bool(
            preset
        )
    )


with c3:

    sample = st.selectbox(
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
            sample_default
        ),
        disabled=bool(
            preset
        )
    )


cfg = presets[
    variable
]


st.markdown(
    '<div class="step-card">',
    unsafe_allow_html=True
)


st.write(
    "### Research Question"
)


st.write(
    cfg[
        "question"
    ].replace(
        "the team",
        team
    )
)


st.write(
    f"**Variable A:** "
    f"{cfg['a1']} / "
    f"{cfg['a2']}"
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
        team_map[
            team
        ],
        team,
        season,
        sample,
        variable
    )

    st.session_state[
        "classification_ok"
    ] = False


loaded = st.session_state.get(
    "loaded_key"
)


if not loaded:

    st.info(
        "Choose your investigation and click **Load Game Data**."
    )

    st.stop()


(
    loaded_sport,
    loaded_team_id,
    loaded_team,
    loaded_season,
    loaded_sample,
    loaded_variable
) = loaded


loaded_presets = presets_for(
    loaded_sport
)


cfg = loaded_presets[
    loaded_variable
]


with st.spinner(
    "Loading completed games and box-score data..."
):

    try:

        df = build_data(
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
        "Those rows were left out."
    )


df_valid = (
    df[
        df[
            "expected_category"
        ]
        .notna()
    ]
    .copy()
)


if df_valid.empty:

    st.error(
        "The statistic needed for this investigation was unavailable for the selected games."
    )

    st.stop()


# ============================================================
# STEP 1
# ============================================================

st.write(
    "## Step 1 — Examine the evidence"
)


st.caption(
    "Do not jump straight to the category. Look at the evidence first."
)


table = (
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


table.columns = [
    "Date",
    "Opponent",
    cfg[
        "evidence_label"
    ],
    "Outcome"
]


table.insert(
    0,
    "Game",
    range(
        1,
        len(table) + 1
    )
)


st.dataframe(
    table,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# STEP 2
# ============================================================

st.write(
    "## Step 2 — Classify each game"
)


st.caption(
    f"For each row, choose "
    f"**{cfg['a1']}** or "
    f"**{cfg['a2']}**."
)


edit = table.copy()


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
        cfg[
            "evidence_label"
        ],
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

    st.session_state[
        "classification_ok"
    ] = all(
        correct
    )

    if all(correct):

        st.success(
            f"Perfect — {sum(correct)} of {len(correct)} classifications are correct."
        )

    else:

        st.warning(
            f"{sum(correct)} of {len(correct)} are correct. "
            "Fix the row numbers below and check again."
        )

        st.write(
            "Rows to fix: **"
            + ", ".join(
                str(i + 1)
                for i, ok
                in enumerate(
                    correct
                )
                if not ok
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


# ============================================================
# STEP 3
# ============================================================

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


a1_wins = int(
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


a2_wins = int(
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
    a1_wins,
    a1_total
)


p2 = percent(
    a2_wins,
    a2_total
)


difference = abs(
    p1 - p2
)


# ============================================================
# STEP 4
# ============================================================

st.write(
    "## Step 4 — Conditional percentages"
)


c1, c2 = st.columns(2)


with c1:

    st.metric(
        cfg["a1"],
        f"{p1:.1f}% win rate"
    )

    st.caption(
        f"{a1_wins} ÷ "
        f"{a1_total} × 100 "
        f"= {p1:.1f}%"
    )


with c2:

    st.metric(
        cfg["a2"],
        f"{p2:.1f}% win rate"
    )

    st.caption(
        f"{a2_wins} ÷ "
        f"{a2_total} × 100 "
        f"= {p2:.1f}%"
    )


st.metric(
    "Difference",
    f"{difference:.1f} percentage points"
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


# ============================================================
# STEP 5
# ============================================================

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
<b>{difference:.1f} percentage points</b>.

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
    placeholder=
        "Our data suggests ... because ..."
)


st.text_area(
    "Name one limitation of the investigation.",
    placeholder=
        "One limitation is ..."
)


st.caption(
    "Reminder: an association does not prove that one variable caused the other."
)


with st.expander(
    "Source information"
):

    if loaded_sport == "NBA":

        st.write(
            "NBA schedules and box-score statistics are retrieved from ESPN public sports data."
        )

    elif loaded_sport == "MLB":

        st.write(
            "MLB schedules and game feeds are retrieved from MLB's Stats API."
        )

    elif loaded_sport == "NHL":

        st.write(
            "NHL schedules, box scores, and scoring summaries are retrieved from the NHL Web API."
        )

    else:

        st.write(
            "MLS schedules and match summaries are retrieved from ESPN's MLS data endpoints."
        )

    st.write(
        "Students should still record the original game schedule or box score in their project source log."
    )
