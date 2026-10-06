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
    layout="wide",
)

NBA_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
MLS_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1"
MLB_BASE = "https://statsapi.mlb.com/api/v1"
NHL_BASE = "https://api-web.nhle.com/v1"


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
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
    opacity: .80;
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
    padding: 12px 14px;
    border-radius: 8px;
    background: rgba(46,125,50,.08);
}

.small-note {
    font-size: .9rem;
    opacity: .75;
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_get(url, params=None, timeout=30):
    response = requests.get(
        url,
        params=params,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
        timeout=timeout,
    )

    response.raise_for_status()
    return response.json()


def norm(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower(),
    )


def as_number(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, dict):
        for key in [
            "value",
            "displayValue",
            "score",
        ]:
            if key in value:
                result = as_number(value[key])
                if result is not None:
                    return result

        return None

    text = (
        str(value)
        .replace("%", "")
        .replace(",", "")
        .strip()
    )

    try:
        return float(text)
    except Exception:
        return None


def parse_percent(value):
    number = as_number(value)

    if number is None:
        return None

    if number <= 1:
        return number * 100

    return number


def percent(numerator, denominator):
    if denominator == 0:
        return 0.0

    return 100.0 * numerator / denominator


def format_date(value):
    try:
        return pd.to_datetime(value).strftime(
            "%b %d, %Y"
        )
    except Exception:
        return str(value)[:10]


def encode_task(payload):
    raw = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    return (
        base64.urlsafe_b64encode(raw)
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


def two_way_table(df, category_1, category_2):
    table = pd.crosstab(
        df["expected_category"],
        df["result"],
    )

    for category in [
        category_1,
        category_2,
    ]:
        if category not in table.index:
            table.loc[category] = 0

    for result in [
        "Win",
        "Did Not Win",
    ]:
        if result not in table.columns:
            table[result] = 0

    table = table.loc[
        [category_1, category_2],
        ["Win", "Did Not Win"],
    ]

    table["Total"] = table.sum(axis=1)

    total_row = pd.DataFrame(
        [[
            table["Win"].sum(),
            table["Did Not Win"].sum(),
            table["Total"].sum(),
        ]],
        index=["Total"],
        columns=[
            "Win",
            "Did Not Win",
            "Total",
        ],
    )

    return pd.concat(
        [
            table,
            total_row,
        ]
    )


# ============================================================
# GENERIC CLASSIFICATION
# ============================================================

def classify_row(row, cfg):
    kind = cfg["type"]

    if kind == "home_away":
        return row.get("home_away")

    if kind == "team_score_at_least":
        value = row.get("team_score")

        if value is None:
            return None

        return (
            cfg["a1"]
            if value >= cfg["threshold"]
            else cfg["a2"]
        )

    if kind == "opp_score_under":
        value = row.get("opp_score")

        if value is None:
            return None

        return (
            cfg["a1"]
            if value < cfg["threshold"]
            else cfg["a2"]
        )

    if kind == "opp_score_at_most":
        value = row.get("opp_score")

        if value is None:
            return None

        return (
            cfg["a1"]
            if value <= cfg["threshold"]
            else cfg["a2"]
        )

    if kind == "metric_at_least":
        value = row.get(
            cfg["metric"]
        )

        if value is None or pd.isna(value):
            return None

        return (
            cfg["a1"]
            if float(value) >= cfg["threshold"]
            else cfg["a2"]
        )

    if kind == "metric_at_most":
        value = row.get(
            cfg["metric"]
        )

        if value is None or pd.isna(value):
            return None

        return (
            cfg["a1"]
            if float(value) <= cfg["threshold"]
            else cfg["a2"]
        )

    if kind == "boolean":
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

    if kind == "more":
        first = row.get(
            cfg["m1"]
        )

        second = row.get(
            cfg["m2"]
        )

        if (
            first is None
            or second is None
            or pd.isna(first)
            or pd.isna(second)
        ):
            return None

        return (
            cfg["a1"]
            if float(first) > float(second)
            else cfg["a2"]
        )

    if kind == "fewer":
        first = row.get(
            cfg["m1"]
        )

        second = row.get(
            cfg["m2"]
        )

        if (
            first is None
            or second is None
            or pd.isna(first)
            or pd.isna(second)
        ):
            return None

        return (
            cfg["a1"]
            if float(first) < float(second)
            else cfg["a2"]
        )

    return None


def evidence_text(row, cfg):
    evidence_type = cfg.get(
        "evidence_type",
        "metric",
    )

    if evidence_type == "location":
        return row.get(
            "home_away",
            "Unavailable",
        )

    if evidence_type == "team_score":
        return str(
            row.get(
                "team_score",
                "Unavailable",
            )
        )

    if evidence_type == "opp_score":
        return str(
            row.get(
                "opp_score",
                "Unavailable",
            )
        )

    if evidence_type == "boolean_first":
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

    if evidence_type == "quality_start":
        ip = row.get("starter_ip")
        er = row.get("starter_er")

        if (
            ip is None
            or er is None
        ):
            return "Unavailable"

        return (
            f"{float(ip):g} IP / "
            f"{float(er):g} ER"
        )

    if evidence_type == "percent":
        value = row.get(
            cfg["metric"]
        )

        if value is None or pd.isna(value):
            return "Unavailable"

        return f"{float(value):.1f}%"

    if evidence_type == "decimal3":
        value = row.get(
            cfg["metric"]
        )

        if value is None or pd.isna(value):
            return "Unavailable"

        return f"{float(value):.3f}"

    if evidence_type == "comparison":
        first = row.get(
            cfg["m1"]
        )

        second = row.get(
            cfg["m2"]
        )

        if (
            first is None
            or second is None
            or pd.isna(first)
            or pd.isna(second)
        ):
            return "Unavailable"

        return (
            f"{float(first):g} vs. "
            f"{float(second):g}"
        )

    if evidence_type == "score_comparison":
        first = row.get(
            cfg["m1"]
        )

        second = row.get(
            cfg["m2"]
        )

        if (
            first is None
            or second is None
            or pd.isna(first)
            or pd.isna(second)
        ):
            return "Unavailable"

        return (
            f"{float(first):g} – "
            f"{float(second):g}"
        )

    metric = cfg.get("metric")

    if metric:
        value = row.get(metric)

        if value is None or pd.isna(value):
            return "Unavailable"

        return f"{float(value):g}"

    return "Unavailable"


# ============================================================
# NBA
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_nba_teams():
    data = safe_get(
        f"{NBA_BASE}/teams"
    )

    teams = []

    sports = data.get(
        "sports",
        [],
    )

    if sports:
        leagues = sports[0].get(
            "leagues",
            [],
        )

        if leagues:
            for item in leagues[0].get(
                "teams",
                [],
            ):
                team = item.get(
                    "team",
                    {},
                )

                if (
                    team.get("id")
                    and team.get("displayName")
                ):
                    teams.append({
                        "id": str(team["id"]),
                        "name": team["displayName"],
                    })

    return sorted(
        teams,
        key=lambda x: x["name"],
    )


def nba_season_id(label):
    match = re.match(
        r"(\d{4})-(\d{2})",
        label,
    )

    if match:
        return int(
            match.group(1)
        ) + 1

    return int(label)


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def get_nba_schedule(
    team_id,
    season,
):
    data = safe_get(
        f"{NBA_BASE}/teams/{team_id}/schedule",
        params={
            "season": nba_season_id(
                season
            ),
            "seasontype": 2,
        },
    )

    return data.get(
        "events",
        [],
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def get_nba_summary(event_id):
    return safe_get(
        f"{NBA_BASE}/summary",
        params={
            "event": event_id,
        },
    )


def espn_game_core(
    event,
    team_id,
):
    competitions = event.get(
        "competitions",
        [],
    )

    if not competitions:
        return None

    competition = competitions[0]

    competitors = competition.get(
        "competitors",
        [],
    )

    team_comp = None
    opp_comp = None

    for competitor in competitors:
        competitor_id = str(
            competitor.get(
                "team",
                {},
            ).get(
                "id",
                "",
            )
        )

        if competitor_id == str(team_id):
            team_comp = competitor
        else:
            opp_comp = competitor

    if not team_comp or not opp_comp:
        return None

    team_score = as_number(
        team_comp.get("score")
    )

    opp_score = as_number(
        opp_comp.get("score")
    )

    if (
        team_score is None
        or opp_score is None
    ):
        return None

    return {
        "event_id": str(
            event.get(
                "id",
                "",
            )
        ),
        "date": format_date(
            event.get(
                "date",
                "",
            )
        ),
        "opponent": (
            opp_comp
            .get(
                "team",
                {},
            )
            .get(
                "displayName",
                "Opponent",
            )
        ),
        "home_away": (
            "Home"
            if team_comp.get(
                "homeAway"
            ) == "home"
            else "Away"
        ),
        "team_score": int(
            round(team_score)
        ),
        "opp_score": int(
            round(opp_score)
        ),
        "result": (
            "Win"
            if team_score > opp_score
            else "Did Not Win"
        ),
    }


def espn_box_team(
    summary,
    team_id,
    opponent=False,
):
    teams = (
        summary
        .get(
            "boxscore",
            {},
        )
        .get(
            "teams",
            [],
        )
    )

    for team_box in teams:
        box_id = str(
            team_box.get(
                "team",
                {},
            ).get(
                "id",
                "",
            )
        )

        if (
            not opponent
            and box_id == str(team_id)
        ):
            return team_box

        if (
            opponent
            and box_id
            and box_id != str(team_id)
        ):
            return team_box

    return None


def espn_stat_map(team_box):
    values = {}

    if not team_box:
        return values

    for stat in team_box.get(
        "statistics",
        [],
    ):
        value = stat.get(
            "displayValue",
            stat.get("value"),
        )

        for field in [
            "name",
            "displayName",
            "label",
            "abbreviation",
        ]:
            name = stat.get(field)

            if name:
                values[
                    norm(name)
                ] = value

    return values


def find_stat(stats, names):
    for name in names:
        key = norm(name)

        if key in stats:
            return stats[key]

    for stored_name, value in stats.items():
        for name in names:
            if norm(name) in stored_name:
                return value

    return None


def nba_halftime(
    summary,
    team_id,
):
    competitions = (
        summary
        .get(
            "header",
            {},
        )
        .get(
            "competitions",
            [],
        )
    )

    if not competitions:
        return None, None

    team_lines = None
    opp_lines = None

    for competitor in competitions[0].get(
        "competitors",
        [],
    ):
        values = []

        for line in competitor.get(
            "linescores",
            [],
        ):
            value = as_number(
                line.get("value")
            )

            if value is None:
                value = 0

            values.append(value)

        competitor_id = str(
            competitor.get(
                "team",
                {},
            ).get(
                "id",
                "",
            )
        )

        if competitor_id == str(team_id):
            team_lines = values
        else:
            opp_lines = values

    if (
        team_lines is None
        or opp_lines is None
        or len(team_lines) < 2
        or len(opp_lines) < 2
    ):
        return None, None

    return (
        sum(team_lines[:2]),
        sum(opp_lines[:2]),
    )


def nba_metrics(
    summary,
    team_id,
):
    team_stats = espn_stat_map(
        espn_box_team(
            summary,
            team_id,
        )
    )

    opp_stats = espn_stat_map(
        espn_box_team(
            summary,
            team_id,
            opponent=True,
        )
    )

    halftime_team, halftime_opp = (
        nba_halftime(
            summary,
            team_id,
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
                    "threePointersMade",
                ],
            )
        ),

        "opp_3pm": as_number(
            find_stat(
                opp_stats,
                [
                    "threePointFieldGoalsMade",
                    "3PT Made",
                    "3PM",
                    "threePointersMade",
                ],
            )
        ),

        "team_turnovers": as_number(
            find_stat(
                team_stats,
                [
                    "turnovers",
                    "TO",
                ],
            )
        ),

        "opp_turnovers": as_number(
            find_stat(
                opp_stats,
                [
                    "turnovers",
                    "TO",
                ],
            )
        ),

        "team_rebounds": as_number(
            find_stat(
                team_stats,
                [
                    "totalRebounds",
                    "rebounds",
                    "REB",
                ],
            )
        ),

        "opp_rebounds": as_number(
            find_stat(
                opp_stats,
                [
                    "totalRebounds",
                    "rebounds",
                    "REB",
                ],
            )
        ),

        "team_assists": as_number(
            find_stat(
                team_stats,
                [
                    "assists",
                    "AST",
                ],
            )
        ),

        "team_fg_pct": parse_percent(
            find_stat(
                team_stats,
                [
                    "fieldGoalPct",
                    "field goal percentage",
                    "FG%",
                ],
            )
        ),

        "halftime_team":
            halftime_team,

        "halftime_opp":
            halftime_opp,
    }


NBA_PRESETS = {
    "Home vs. Away": {
        "type": "home_away",
        "a1": "Home",
        "a2": "Away",
        "evidence_label": "Location",
        "evidence_type": "location",
        "question":
            "Does playing at home appear associated with whether the team wins?",
    },

    "Team scores at least 110 points": {
        "type": "team_score_at_least",
        "threshold": 110,
        "a1": "110 Plus Points",
        "a2": "Under 110",
        "evidence_label": "Team points",
        "evidence_type": "team_score",
        "question":
            "Is scoring 110 or more points associated with whether the team wins?",
    },

    "More 3-pointers than opponent": {
        "type": "more",
        "m1": "team_3pm",
        "m2": "opp_3pm",
        "a1": "More 3-Pointers",
        "a2": "Not More 3-Pointers",
        "evidence_label":
            "Team 3PM vs. opponent 3PM",
        "evidence_type": "comparison",
        "question":
            "Is making more three-pointers than the opponent associated with whether the team wins?",
    },

    "Fewer turnovers than opponent": {
        "type": "fewer",
        "m1": "team_turnovers",
        "m2": "opp_turnovers",
        "a1": "Fewer Turnovers",
        "a2": "Not Fewer Turnovers",
        "evidence_label":
            "Team turnovers vs. opponent turnovers",
        "evidence_type": "comparison",
        "question":
            "Is having fewer turnovers than the opponent associated with whether the team wins?",
    },

    "Field goal percentage at least 50%": {
        "type": "metric_at_least",
        "metric": "team_fg_pct",
        "threshold": 50,
        "a1": "50 Percent Plus FG",
        "a2": "Under 50 Percent",
        "evidence_label": "Team FG%",
        "evidence_type": "percent",
        "question":
            "Is shooting at least 50 percent from the field associated with whether the team wins?",
    },

    "More rebounds than opponent": {
        "type": "more",
        "m1": "team_rebounds",
        "m2": "opp_rebounds",
        "a1": "More Rebounds",
        "a2": "Not More Rebounds",
        "evidence_label":
            "Team rebounds vs. opponent rebounds",
        "evidence_type": "comparison",
        "question":
            "Is outrebounding the opponent associated with whether the team wins?",
    },

    "Led at halftime": {
        "type": "more",
        "m1": "halftime_team",
        "m2": "halftime_opp",
        "a1": "Led at Halftime",
        "a2": "Did Not Lead at Halftime",
        "evidence_label": "Halftime score",
        "evidence_type": "score_comparison",
        "question":
            "Does leading at halftime appear associated with whether the team wins?",
    },

    "Made at least 12 three-pointers": {
        "type": "metric_at_least",
        "metric": "team_3pm",
        "threshold": 12,
        "a1": "12 Plus 3-Pointers",
        "a2": "Fewer Than 12",
        "evidence_label": "Team 3PM",
        "question":
            "Is making 12 or more three-pointers associated with whether the team wins?",
    },

    "Held opponent under 110 points": {
        "type": "opp_score_under",
        "threshold": 110,
        "a1": "Opponent Under 110",
        "a2": "Opponent 110 Plus",
        "evidence_label": "Opponent points",
        "evidence_type": "opp_score",
        "question":
            "Is holding the opponent under 110 points associated with whether the team wins?",
    },

    "At least 25 assists": {
        "type": "metric_at_least",
        "metric": "team_assists",
        "threshold": 25,
        "a1": "25 Plus Assists",
        "a2": "Under 25 Assists",
        "evidence_label": "Team assists",
        "question":
            "Are 25 or more team assists associated with whether the team wins?",
    },
}


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def build_nba(
    team_id,
    season,
    sample,
    variable,
):
    games = []

    for event in get_nba_schedule(
        team_id,
        season,
    ):
        core = espn_game_core(
            event,
            team_id,
        )

        if core:
            games.append(core)

    games = sorted(
        games,
        key=lambda game:
            pd.to_datetime(
                game["date"]
            ),
    )[:sample]

    cfg = NBA_PRESETS[
        variable
    ]

    rows = []

    for game in games:
        row = dict(game)

        if cfg["type"] in [
            "metric_at_least",
            "metric_at_most",
            "more",
            "fewer",
        ]:
            try:
                row.update(
                    nba_metrics(
                        get_nba_summary(
                            game["event_id"]
                        ),
                        team_id,
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            classify_row(
                row,
                cfg,
            )
        )

        row["evidence"] = (
            evidence_text(
                row,
                cfg,
            )
        )

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# MLB
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_mlb_teams(season):
    data = safe_get(
        f"{MLB_BASE}/teams",
        params={
            "sportId": 1,
            "season": season,
        },
    )

    teams = []

    for team in data.get(
        "teams",
        [],
    ):
        if (
            team.get("id")
            and team.get("name")
        ):
            teams.append({
                "id": str(team["id"]),
                "name": team["name"],
            })

    return sorted(
        teams,
        key=lambda x: x["name"],
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def get_mlb_schedule(
    team_id,
    season,
):
    data = safe_get(
        f"{MLB_BASE}/schedule",
        params={
            "sportId": 1,
            "teamId": team_id,
            "season": season,
            "gameType": "R",
        },
    )

    games = []

    for date_block in data.get(
        "dates",
        [],
    ):
        games.extend(
            date_block.get(
                "games",
                [],
            )
        )

    return games


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def get_mlb_feed(game_pk):
    return safe_get(
        f"{MLB_BASE}.1/game/{game_pk}/feed/live"
    )


def mlb_core(
    game,
    team_id,
):
    teams = game.get(
        "teams",
        {},
    )

    home = teams.get(
        "home",
        {},
    )

    away = teams.get(
        "away",
        {},
    )

    home_id = str(
        home.get(
            "team",
            {},
        ).get(
            "id",
            "",
        )
    )

    away_id = str(
        away.get(
            "team",
            {},
        ).get(
            "id",
            "",
        )
    )

    if str(team_id) == home_id:
        team = home
        opp = away
        side = "home"
        home_away = "Home"

    elif str(team_id) == away_id:
        team = away
        opp = home
        side = "away"
        home_away = "Away"

    else:
        return None

    team_score = as_number(
        team.get("score")
    )

    opp_score = as_number(
        opp.get("score")
    )

    if (
        team_score is None
        or opp_score is None
    ):
        return None

    return {
        "game_pk": str(
            game.get(
                "gamePk",
                "",
            )
        ),
        "date": format_date(
            game.get(
                "gameDate",
                game.get(
                    "officialDate",
                    "",
                ),
            )
        ),
        "opponent": (
            opp.get(
                "team",
                {},
            ).get(
                "name",
                "Opponent",
            )
        ),
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
        ),
    }


def mlb_team_stats(
    feed,
    side,
):
    return (
        feed
        .get(
            "liveData",
            {},
        )
        .get(
            "boxscore",
            {},
        )
        .get(
            "teams",
            {},
        )
        .get(
            side,
            {},
        )
        .get(
            "teamStats",
            {},
        )
    )


def mlb_scored_first(
    feed,
    side,
):
    plays = (
        feed
        .get(
            "liveData",
            {},
        )
        .get(
            "plays",
            {},
        )
        .get(
            "allPlays",
            [],
        )
    )

    for play in plays:
        if (
            play.get(
                "about",
                {},
            ).get(
                "isScoringPlay"
            ) is True
        ):
            half = str(
                play.get(
                    "about",
                    {},
                ).get(
                    "halfInning",
                    "",
                )
            ).lower()

            scoring_side = (
                "away"
                if half == "top"
                else "home"
            )

            return (
                scoring_side == side
            )

    return None


def mlb_quality_start(
    feed,
    side,
):
    team_box = (
        feed
        .get(
            "liveData",
            {},
        )
        .get(
            "boxscore",
            {},
        )
        .get(
            "teams",
            {},
        )
        .get(
            side,
            {},
        )
    )

    pitcher_ids = team_box.get(
        "pitchers",
        [],
    )

    if not pitcher_ids:
        return None, None, None

    starter = (
        team_box
        .get(
            "players",
            {},
        )
        .get(
            f"ID{pitcher_ids[0]}",
            {},
        )
        .get(
            "stats",
            {},
        )
        .get(
            "pitching",
            {},
        )
    )

    innings = as_number(
        starter.get(
            "inningsPitched"
        )
    )

    earned_runs = as_number(
        starter.get(
            "earnedRuns"
        )
    )

    if (
        innings is None
        or earned_runs is None
    ):
        return (
            None,
            innings,
            earned_runs,
        )

    quality_start = (
        innings >= 6
        and earned_runs <= 3
    )

    return (
        quality_start,
        innings,
        earned_runs,
    )


def mlb_metrics(
    feed,
    core,
):
    team_stats = mlb_team_stats(
        feed,
        core["team_side"],
    )

    batting = team_stats.get(
        "batting",
        {},
    )

    pitching = team_stats.get(
        "pitching",
        {},
    )

    fielding = team_stats.get(
        "fielding",
        {},
    )

    quality_start, ip, er = (
        mlb_quality_start(
            feed,
            core["team_side"],
        )
    )

    return {
        "home_runs": as_number(
            batting.get(
                "homeRuns"
            )
        ),

        "hits": as_number(
            batting.get(
                "hits"
            )
        ),

        "walks": as_number(
            batting.get(
                "baseOnBalls"
            )
        ),

        "errors": as_number(
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
                core["team_side"],
            ),

        "quality_start":
            quality_start,

        "starter_ip":
            ip,

        "starter_er":
            er,
    }


MLB_PRESETS = {
    "Home vs. Away": {
        "type": "home_away",
        "a1": "Home",
        "a2": "Away",
        "evidence_label": "Location",
        "evidence_type": "location",
        "question":
            "Does playing at home appear associated with whether the team wins?",
    },

    "Hit at least 1 home run": {
        "type": "metric_at_least",
        "metric": "home_runs",
        "threshold": 1,
        "a1": "Hit 1 Plus HR",
        "a2": "Hit 0 HR",
        "evidence_label": "Team HR",
        "question":
            "Is hitting at least one home run associated with whether the team wins?",
    },

    "Scored first": {
        "type": "boolean",
        "metric": "scored_first",
        "a1": "Scored First",
        "a2": "Did Not Score First",
        "evidence_label":
            "First scoring team",
        "evidence_type":
            "boolean_first",
        "question":
            "Does scoring first appear associated with whether the team wins?",
    },

    "Committed at least 1 error": {
        "type": "metric_at_least",
        "metric": "errors",
        "threshold": 1,
        "a1":
            "Committed 1 Plus Error",
        "a2":
            "Committed 0 Errors",
        "evidence_label":
            "Team errors",
        "question":
            "Is committing an error associated with whether the team wins?",
    },

    "Scored at least 5 runs": {
        "type":
            "team_score_at_least",
        "threshold": 5,
        "a1": "5 Plus Runs",
        "a2": "Under 5 Runs",
        "evidence_label":
            "Team runs",
        "evidence_type":
            "team_score",
        "question":
            "Is scoring five or more runs associated with whether the team wins?",
    },

    "At least 10 hits": {
        "type":
            "metric_at_least",
        "metric":
            "hits",
        "threshold":
            10,
        "a1":
            "10 Plus Hits",
        "a2":
            "Under 10 Hits",
        "evidence_label":
            "Team hits",
        "question":
            "Are 10 or more team hits associated with whether the team wins?",
    },

    "Quality start": {
        "type":
            "boolean",
        "metric":
            "quality_start",
        "a1":
            "Quality Start",
        "a2":
            "No Quality Start",
        "evidence_label":
            "Starter IP / ER",
        "evidence_type":
            "quality_start",
        "question":
            "Is a quality start associated with whether the team wins?",
    },

    "At least 2 home runs": {
        "type":
            "metric_at_least",
        "metric":
            "home_runs",
        "threshold":
            2,
        "a1":
            "2 Plus HR",
        "a2":
            "Fewer Than 2 HR",
        "evidence_label":
            "Team HR",
        "question":
            "Are two or more team home runs associated with whether the team wins?",
    },

    "At least 4 walks": {
        "type":
            "metric_at_least",
        "metric":
            "walks",
        "threshold":
            4,
        "a1":
            "4 Plus Walks",
        "a2":
            "Fewer Than 4 Walks",
        "evidence_label":
            "Team walks",
        "question":
            "Are four or more walks associated with whether the team wins?",
    },

    "At least 10 pitching strikeouts": {
        "type":
            "metric_at_least",
        "metric":
            "pitching_strikeouts",
        "threshold":
            10,
        "a1":
            "10 Plus Pitching Strikeouts",
        "a2":
            "Under 10",
        "evidence_label":
            "Pitching strikeouts",
        "question":
            "Are 10 or more pitching strikeouts associated with whether the team wins?",
    },
}


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def build_mlb(
    team_id,
    season,
    sample,
    variable,
):
    games = []

    for game in get_mlb_schedule(
        team_id,
        int(season),
    ):
        status = str(
            game.get(
                "status",
                {},
            ).get(
                "abstractGameState",
                "",
            )
        ).lower()

        if status != "final":
            continue

        core = mlb_core(
            game,
            team_id,
        )

        if core:
            games.append(core)

    games = sorted(
        games,
        key=lambda game:
            pd.to_datetime(
                game["date"]
            ),
    )[:sample]

    cfg = MLB_PRESETS[
        variable
    ]

    rows = []

    for game in games:
        row = dict(game)

        if cfg["type"] not in [
            "home_away",
            "team_score_at_least",
        ]:
            try:
                feed = get_mlb_feed(
                    game["game_pk"]
                )

                row.update(
                    mlb_metrics(
                        feed,
                        game,
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            classify_row(
                row,
                cfg,
            )
        )

        row["evidence"] = (
            evidence_text(
                row,
                cfg,
            )
        )

        rows.append(row)

    return pd.DataFrame(rows)


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
    ("Winnipeg Jets", "WPG"),
]


def get_nhl_teams():
    return [
        {
            "id": abbr,
            "name": name,
        }
        for name, abbr
        in NHL_TEAMS
    ]


def nhl_season_id(label):
    match = re.match(
        r"(\d{4})-(\d{2})",
        label,
    )

    if not match:
        return str(label)

    start_year = int(
        match.group(1)
    )

    return (
        f"{start_year}"
        f"{start_year + 1}"
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def get_nhl_schedule(
    abbr,
    season,
):
    data = safe_get(
        f"{NHL_BASE}/club-schedule-season/{abbr}/{nhl_season_id(season)}"
    )

    return data.get(
        "games",
        [],
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def get_nhl_boxscore(game_id):
    return safe_get(
        f"{NHL_BASE}/gamecenter/{game_id}/boxscore"
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def get_nhl_landing(game_id):
    return safe_get(
        f"{NHL_BASE}/gamecenter/{game_id}/landing"
    )


def nhl_core(
    game,
    abbr,
):
    # 2 = NHL regular season
    if game.get("gameType") != 2:
        return None

    game_state = str(
        game.get(
            "gameState",
            "",
        )
    ).upper()

    if game_state not in [
        "FINAL",
        "OFF",
    ]:
        return None

    home = game.get(
        "homeTeam",
        {},
    )

    away = game.get(
        "awayTeam",
        {},
    )

    if abbr == home.get("abbrev"):
        team = home
        opp = away
        team_side = "homeTeam"
        home_away = "Home"

    elif abbr == away.get("abbrev"):
        team = away
        opp = home
        team_side = "awayTeam"
        home_away = "Away"

    else:
        return None

    team_score = as_number(
        team.get("score")
    )

    opp_score = as_number(
        opp.get("score")
    )

    if (
        team_score is None
        or opp_score is None
    ):
        return None

    opponent_name = (
        str(
            opp.get(
                "placeName",
                {},
            ).get(
                "default",
                "",
            )
        )
        + " "
        + str(
            opp.get(
                "commonName",
                {},
            ).get(
                "default",
                "",
            )
        )
    ).strip()

    if not opponent_name:
        opponent_name = opp.get(
            "abbrev",
            "Opponent",
        )

    return {
        "game_id": str(
            game.get(
                "id",
                "",
            )
        ),
        "date": format_date(
            game.get(
                "gameDate",
                "",
            )
        ),
        "opponent":
            opponent_name,
        "home_away":
            home_away,
        "team_side":
            team_side,
        "team_score":
            int(team_score),
        "opp_score":
            int(opp_score),
        "result": (
            "Win"
            if team_score > opp_score
            else "Did Not Win"
        ),
    }


# ============================================================
# NHL SCORING FIX
# ============================================================

def nhl_goal_team_abbr(goal):
    value = goal.get(
        "teamAbbrev"
    )

    if isinstance(
        value,
        dict,
    ):
        return value.get(
            "default"
        )

    if isinstance(
        value,
        str,
    ):
        return value

    fallback = goal.get(
        "eventOwnerTeamAbbrev"
    )

    if isinstance(
        fallback,
        dict,
    ):
        return fallback.get(
            "default"
        )

    return fallback


def nhl_scoring_metrics(
    landing,
    abbr,
):
    goals = []

    for period_block in landing.get(
        "scoring",
        [],
    ):
        period_number = (
            period_block
            .get(
                "periodDescriptor",
                {},
            )
            .get(
                "number"
            )
        )

        for goal in period_block.get(
            "goals",
            [],
        ):
            team_abbr = nhl_goal_team_abbr(
                goal
            )

            if not team_abbr:
                continue

            strength = str(
                goal.get(
                    "strength",
                    "",
                )
            ).upper()

            goals.append({
                "team": team_abbr,
                "period": period_number,
                "time": goal.get(
                    "timeInPeriod",
                    "",
                ),
                "strength": strength,
            })

    # NHL supplies scoring blocks chronologically.
    # The first goal found is therefore the first goal of the game.
    if goals:
        first_goal_team = (
            goals[0]["team"]
        )

        scored_first = (
            first_goal_team == abbr
        )

    else:
        scored_first = None

    first_period_team = 0
    first_period_opp = 0
    power_play_goals = 0

    for goal in goals:
        if goal["period"] == 1:
            if goal["team"] == abbr:
                first_period_team += 1
            else:
                first_period_opp += 1

        strength = goal["strength"]

        if (
            goal["team"] == abbr
            and (
                strength == "PP"
                or strength == "PPG"
                or "POWER PLAY" in strength
                or strength.startswith("PP")
            )
        ):
            power_play_goals += 1

    return {
        "scored_first":
            scored_first,

        "first_period_team":
            first_period_team,

        "first_period_opp":
            first_period_opp,

        "power_play_goals":
            power_play_goals,
    }


def nhl_goalie_save_pct(
    box,
    team_side,
):
    goalies = (
        box
        .get(
            "playerByGameStats",
            {},
        )
        .get(
            team_side,
            {},
        )
        .get(
            "goalies",
            [],
        )
    )

    total_saves = 0.0
    total_shots = 0.0

    for goalie in goalies:
        saves = as_number(
            goalie.get("saves")
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
            continue

        save_shots = str(
            goalie.get(
                "saveShotsAgainst",
                "",
            )
        )

        match = re.match(
            r"(\d+)\s*/\s*(\d+)",
            save_shots,
        )

        if match:
            total_saves += float(
                match.group(1)
            )

            total_shots += float(
                match.group(2)
            )

    if total_shots == 0:
        return None

    return (
        total_saves
        / total_shots
    )


def nhl_metrics(
    box,
    landing,
    core,
    abbr,
):
    team_side = core[
        "team_side"
    ]

    opp_side = (
        "awayTeam"
        if team_side == "homeTeam"
        else "homeTeam"
    )

    team = box.get(
        team_side,
        {},
    )

    opponent = box.get(
        opp_side,
        {},
    )

    metrics = nhl_scoring_metrics(
        landing,
        abbr,
    )

    metrics.update({
        "team_sog": as_number(
            team.get("sog")
        ),

        "opp_sog": as_number(
            opponent.get("sog")
        ),

        "save_pct":
            nhl_goalie_save_pct(
                box,
                team_side,
            ),
    })

    return metrics


NHL_PRESETS = {
    "Home vs. Away": {
        "type": "home_away",
        "a1": "Home",
        "a2": "Away",
        "evidence_label": "Location",
        "evidence_type": "location",
        "question":
            "Does playing at home appear associated with whether the team wins?",
    },

    "Scored first": {
        "type": "boolean",
        "metric": "scored_first",
        "a1": "Scored First",
        "a2": "Did Not Score First",
        "evidence_label": "First goal",
        "evidence_type":
            "boolean_first",
        "question":
            "Does scoring the first goal appear associated with whether the team wins?",
    },

    "Scored at least 4 goals": {
        "type":
            "team_score_at_least",
        "threshold": 4,
        "a1":
            "4 Plus Goals",
        "a2":
            "Under 4 Goals",
        "evidence_label":
            "Team goals",
        "evidence_type":
            "team_score",
        "question":
            "Is scoring four or more goals associated with whether the team wins?",
    },

    "More shots than opponent": {
        "type": "more",
        "m1": "team_sog",
        "m2": "opp_sog",
        "a1": "More Shots",
        "a2": "Not More Shots",
        "evidence_label":
            "Team SOG vs. opponent SOG",
        "evidence_type":
            "comparison",
        "question":
            "Is outshooting the opponent associated with whether the team wins?",
    },

    "Scored a power-play goal": {
        "type":
            "metric_at_least",
        "metric":
            "power_play_goals",
        "threshold":
            1,
        "a1":
            "Scored 1 Plus Power-Play Goal",
        "a2":
            "Scored 0",
        "evidence_label":
            "Power-play goals",
        "question":
            "Is scoring a power-play goal associated with whether the team wins?",
    },

    "Team save percentage .900 or higher": {
        "type":
            "metric_at_least",
        "metric":
            "save_pct",
        "threshold":
            0.900,
        "a1":
            ".900 Plus Save Percentage",
        "a2":
            "Below .900",
        "evidence_label":
            "Team save percentage",
        "evidence_type":
            "decimal3",
        "question":
            "Is a team save percentage of .900 or higher associated with whether the team wins?",
    },

    "Led after the 1st period": {
        "type":
            "more",
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
        "evidence_type":
            "score_comparison",
        "question":
            "Does leading after the first period appear associated with whether the team wins?",
    },

    "Held opponent to 2 or fewer goals": {
        "type":
            "opp_score_at_most",
        "threshold":
            2,
        "a1":
            "Opponent 2 or Fewer Goals",
        "a2":
            "Opponent 3 Plus",
        "evidence_label":
            "Opponent goals",
        "evidence_type":
            "opp_score",
        "question":
            "Is holding the opponent to two or fewer goals associated with whether the team wins?",
    },

    "Scored at least 3 goals": {
        "type":
            "team_score_at_least",
        "threshold":
            3,
        "a1":
            "3 Plus Goals",
        "a2":
            "Under 3 Goals",
        "evidence_label":
            "Team goals",
        "evidence_type":
            "team_score",
        "question":
            "Is scoring at least three goals associated with whether the team wins?",
    },

    "Allowed 30 or fewer shots": {
        "type":
            "metric_at_most",
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
            "Is allowing 30 or fewer shots on goal associated with whether the team wins?",
    },
}


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def build_nhl(
    abbr,
    season,
    sample,
    variable,
):
    games = []

    for game in get_nhl_schedule(
        abbr,
        season,
    ):
        core = nhl_core(
            game,
            abbr,
        )

        if core:
            games.append(core)

    games = sorted(
        games,
        key=lambda game:
            pd.to_datetime(
                game["date"]
            ),
    )[:sample]

    cfg = NHL_PRESETS[
        variable
    ]

    rows = []

    for game in games:
        row = dict(game)

        if cfg["type"] not in [
            "home_away",
            "team_score_at_least",
            "opp_score_under",
            "opp_score_at_most",
        ]:
            try:
                box = get_nhl_boxscore(
                    game["game_id"]
                )

                landing = get_nhl_landing(
                    game["game_id"]
                )

                row.update(
                    nhl_metrics(
                        box,
                        landing,
                        game,
                        abbr,
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            classify_row(
                row,
                cfg,
            )
        )

        row["evidence"] = (
            evidence_text(
                row,
                cfg,
            )
        )

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# MLS
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_mls_teams():
    data = safe_get(
        f"{MLS_BASE}/teams"
    )

    teams = []

    sports = data.get(
        "sports",
        [],
    )

    if sports:
        leagues = sports[0].get(
            "leagues",
            [],
        )

        if leagues:
            for item in leagues[0].get(
                "teams",
                [],
            ):
                team = item.get(
                    "team",
                    {},
                )

                if (
                    team.get("id")
                    and team.get("displayName")
                ):
                    teams.append({
                        "id": str(team["id"]),
                        "name": team["displayName"],
                    })

    return sorted(
        teams,
        key=lambda x: x["name"],
    )


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def get_mls_schedule(
    team_id,
    season,
):
    data = safe_get(
        f"{MLS_BASE}/teams/{team_id}/schedule",
        params={
            "season": int(season),
        },
    )

    return data.get(
        "events",
        [],
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def get_mls_summary(event_id):
    return safe_get(
        f"{MLS_BASE}/summary",
        params={
            "event": event_id,
        },
    )


def mls_core(
    event,
    team_id,
):
    competitions = event.get(
        "competitions",
        [],
    )

    if not competitions:
        return None

    competition = competitions[0]

    status = (
        competition
        .get(
            "status",
            {},
        )
        .get(
            "type",
            {},
        )
    )

    completed = (
        status.get(
            "completed"
        ) is True
        or str(
            status.get(
                "state",
                "",
            )
        ).lower() == "post"
        or "final" in str(
            status.get(
                "name",
                "",
            )
        ).lower()
    )

    if not completed:
        return None

    return espn_game_core(
        event,
        team_id,
    )


def mls_scored_first(
    summary,
    team_id,
):
    scoring_plays = summary.get(
        "scoringPlays",
        [],
    )

    for play in scoring_plays:
        scoring_team_id = str(
            play.get(
                "team",
                {},
            ).get(
                "id",
                "",
            )
        )

        if scoring_team_id:
            return (
                scoring_team_id
                == str(team_id)
            )

    plays = summary.get(
        "plays",
        [],
    )

    for play in plays:
        is_score = (
            play.get(
                "scoringPlay"
            ) is True
        )

        if not is_score:
            continue

        scoring_team_id = str(
            play.get(
                "team",
                {},
            ).get(
                "id",
                "",
            )
        )

        if scoring_team_id:
            return (
                scoring_team_id
                == str(team_id)
            )

    return None


def mls_halftime(
    summary,
    team_id,
):
    competitions = (
        summary
        .get(
            "header",
            {},
        )
        .get(
            "competitions",
            [],
        )
    )

    if not competitions:
        return None, None

    team_half = None
    opp_half = None

    for competitor in competitions[0].get(
        "competitors",
        [],
    ):
        lines = competitor.get(
            "linescores",
            [],
        )

        if not lines:
            continue

        first_half = as_number(
            lines[0].get(
                "value"
            )
        )

        competitor_id = str(
            competitor.get(
                "team",
                {},
            ).get(
                "id",
                "",
            )
        )

        if competitor_id == str(team_id):
            team_half = first_half
        else:
            opp_half = first_half

    return (
        team_half,
        opp_half,
    )


def mls_metrics(
    summary,
    team_id,
):
    team_stats = espn_stat_map(
        espn_box_team(
            summary,
            team_id,
        )
    )

    opp_stats = espn_stat_map(
        espn_box_team(
            summary,
            team_id,
            opponent=True,
        )
    )

    halftime_team, halftime_opp = (
        mls_halftime(
            summary,
            team_id,
        )
    )

    return {
        "team_shots": as_number(
            find_stat(
                team_stats,
                [
                    "totalShots",
                    "shots",
                    "Total Shots",
                ],
            )
        ),

        "opp_shots": as_number(
            find_stat(
                opp_stats,
                [
                    "totalShots",
                    "shots",
                    "Total Shots",
                ],
            )
        ),

        "shots_on_target": as_number(
            find_stat(
                team_stats,
                [
                    "shotsOnTarget",
                    "Shots on Target",
                    "shots on goal",
                ],
            )
        ),

        "possession_pct": parse_percent(
            find_stat(
                team_stats,
                [
                    "possessionPct",
                    "possession",
                    "Possession",
                ],
            )
        ),

        "scored_first":
            mls_scored_first(
                summary,
                team_id,
            ),

        "halftime_team":
            halftime_team,

        "halftime_opp":
            halftime_opp,
    }


MLS_PRESETS = {
    "Home vs. Away": {
        "type": "home_away",
        "a1": "Home",
        "a2": "Away",
        "evidence_label": "Location",
        "evidence_type": "location",
        "question":
            "Does playing at home appear associated with whether the team wins?",
    },

    "Scored first": {
        "type": "boolean",
        "metric": "scored_first",
        "a1": "Scored First",
        "a2": "Did Not Score First",
        "evidence_label": "First goal",
        "evidence_type":
            "boolean_first",
        "question":
            "Does scoring first appear associated with whether the team wins?",
    },

    "Scored at least 2 goals": {
        "type":
            "team_score_at_least",
        "threshold": 2,
        "a1":
            "2 Plus Goals",
        "a2":
            "Fewer Than 2 Goals",
        "evidence_label":
            "Team goals",
        "evidence_type":
            "team_score",
        "question":
            "Is scoring two or more goals associated with whether the team wins?",
    },

    "At least 55% possession": {
        "type":
            "metric_at_least",
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
        "evidence_type":
            "percent",
        "question":
            "Is having at least 55 percent possession associated with whether the team wins?",
    },

    "At least 5 shots on target": {
        "type":
            "metric_at_least",
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
            "Are five or more shots on target associated with whether the team wins?",
    },

    "Clean sheet": {
        "type":
            "opp_score_at_most",
        "threshold":
            0,
        "a1":
            "Clean Sheet",
        "a2":
            "Allowed 1 Plus Goal",
        "evidence_label":
            "Opponent goals",
        "evidence_type":
            "opp_score",
        "question":
            "Is keeping a clean sheet associated with whether the team wins?",
    },

    "At least 10 total shots": {
        "type":
            "metric_at_least",
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
            "Are 10 or more total shots associated with whether the team wins?",
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
        "evidence_type":
            "score_comparison",
        "question":
            "Does leading at halftime appear associated with whether the team wins?",
    },

    "Held opponent under 2 goals": {
        "type":
            "opp_score_under",
        "threshold":
            2,
        "a1":
            "Opponent 0 or 1 Goal",
        "a2":
            "Opponent 2 Plus Goals",
        "evidence_label":
            "Opponent goals",
        "evidence_type":
            "opp_score",
        "question":
            "Is holding the opponent under two goals associated with whether the team wins?",
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
        "evidence_type":
            "comparison",
        "question":
            "Is taking more total shots than the opponent associated with whether the team wins?",
    },
}


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def build_mls(
    team_id,
    season,
    sample,
    variable,
):
    games = []

    for event in get_mls_schedule(
        team_id,
        season,
    ):
        core = mls_core(
            event,
            team_id,
        )

        if core:
            games.append(core)

    games = sorted(
        games,
        key=lambda game:
            pd.to_datetime(
                game["date"]
            ),
    )[:sample]

    cfg = MLS_PRESETS[
        variable
    ]

    rows = []

    for game in games:
        row = dict(game)

        if cfg["type"] not in [
            "home_away",
            "team_score_at_least",
            "opp_score_under",
            "opp_score_at_most",
        ]:
            try:
                summary = get_mls_summary(
                    game["event_id"]
                )

                row.update(
                    mls_metrics(
                        summary,
                        team_id,
                    )
                )

            except Exception:
                pass

        row["expected_category"] = (
            classify_row(
                row,
                cfg,
            )
        )

        row["evidence"] = (
            evidence_text(
                row,
                cfg,
            )
        )

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# SPORT SETTINGS
# ============================================================

SPORTS = [
    "NBA",
    "MLB",
    "NHL",
    "MLS",
]


SEASONS = {
    "NBA": [
        "2025-26",
        "2024-25",
        "2023-24",
        "2022-23",
    ],

    "MLB": [
        "2025",
        "2024",
        "2023",
        "2022",
    ],

    "NHL": [
        "2025-26",
        "2024-25",
        "2023-24",
        "2022-23",
    ],

    "MLS": [
        "2025",
        "2024",
        "2023",
        "2022",
    ],
}


def presets_for(sport):
    return {
        "NBA": NBA_PRESETS,
        "MLB": MLB_PRESETS,
        "NHL": NHL_PRESETS,
        "MLS": MLS_PRESETS,
    }[sport]


def teams_for(
    sport,
    season,
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
    variable,
):
    if sport == "NBA":
        return build_nba(
            team_id,
            season,
            sample,
            variable,
        )

    if sport == "MLB":
        return build_mlb(
            team_id,
            season,
            sample,
            variable,
        )

    if sport == "NHL":
        return build_nhl(
            team_id,
            season,
            sample,
            variable,
        )

    return build_mls(
        team_id,
        season,
        sample,
        variable,
    )


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="big-title">📊 Sports Association Lab</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="subtitle">
Use real professional sports data to investigate whether
two categorical variables appear associated.
</div>
""",
    unsafe_allow_html=True,
)


mode = st.radio(
    "Choose a mode",
    [
        "Student Research",
        "Teacher Assignment Builder",
    ],
    horizontal=True,
)


# ============================================================
# TEACHER MODE
# ============================================================

if mode == "Teacher Assignment Builder":

    st.subheader(
        "Teacher Assignment Builder"
    )

    st.write(
        "Create a code that locks the sport, team, season, variable, and sample for students."
    )

    teacher_sport = st.selectbox(
        "Sport",
        SPORTS,
        key="teacher_sport",
    )

    teacher_season = st.selectbox(
        "Season",
        SEASONS[
            teacher_sport
        ],
        key="teacher_season",
    )

    try:
        teacher_teams = teams_for(
            teacher_sport,
            teacher_season,
        )

    except Exception as error:
        st.error(
            "The team list could not be loaded."
        )
        st.code(str(error))
        st.stop()

    teacher_team_names = [
        team["name"]
        for team
        in teacher_teams
    ]

    teacher_presets = presets_for(
        teacher_sport
    )

    col1, col2 = st.columns(2)

    with col1:
        teacher_team = st.selectbox(
            "Team",
            teacher_team_names,
        )

        teacher_variable = st.selectbox(
            "Categorical variable",
            list(
                teacher_presets.keys()
            ),
        )

    with col2:
        teacher_sample = st.selectbox(
            "Sample size",
            [
                10,
                15,
                20,
            ],
            index=2,
        )

    teacher_cfg = teacher_presets[
        teacher_variable
    ]

    st.info(
        "Research question: "
        + teacher_cfg[
            "question"
        ].replace(
            "the team",
            teacher_team,
        )
    )

    st.write(
        f"**Variable A categories:** "
        f"{teacher_cfg['a1']} / "
        f"{teacher_cfg['a2']}"
    )

    st.write(
        "**Outcome categories:** "
        "Win / Did Not Win"
    )

    if st.button(
        "Create Assignment Code",
        type="primary",
    ):
        payload = {
            "sport":
                teacher_sport,
            "team":
                teacher_team,
            "season":
                teacher_season,
            "variable":
                teacher_variable,
            "sample":
                teacher_sample,
        }

        code = encode_task(
            payload
        )

        st.success(
            "Assignment code created."
        )

        st.code(
            code,
            language=None,
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
    placeholder="Paste teacher code here",
)


preset = None

if task_code.strip():
    preset = decode_task(
        task_code.strip()
    )

    if preset is None:
        st.warning(
            "That code could not be read. You can still choose the settings manually."
        )


# ----------------------------
# SPORT
# ----------------------------

default_sport = (
    preset.get(
        "sport",
        "NBA",
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
    disabled=bool(preset),
)


# ----------------------------
# SEASON
# ----------------------------

season_options = SEASONS[
    sport
]

default_season = (
    preset.get(
        "season",
        season_options[0],
    )
    if preset
    else season_options[0]
)

if default_season not in season_options:
    default_season = season_options[0]


season = st.selectbox(
    "2. Season",
    season_options,
    index=season_options.index(
        default_season
    ),
    disabled=bool(preset),
)


# ----------------------------
# TEAMS
# ----------------------------

try:
    teams = teams_for(
        sport,
        season,
    )

except Exception as error:
    st.error(
        "The team list could not be loaded."
    )
    st.code(str(error))
    st.stop()


if not teams:
    st.error(
        "No teams were returned for this sport."
    )
    st.stop()


team_names = [
    team["name"]
    for team
    in teams
]

team_map = {
    team["name"]:
        team["id"]
    for team
    in teams
}


default_team = (
    preset.get(
        "team",
        team_names[0],
    )
    if preset
    else team_names[0]
)

if default_team not in team_names:
    default_team = team_names[0]


# ----------------------------
# VARIABLES
# ----------------------------

presets = presets_for(
    sport
)

variable_options = list(
    presets.keys()
)

default_variable = (
    preset.get(
        "variable",
        variable_options[0],
    )
    if preset
    else variable_options[0]
)

if default_variable not in variable_options:
    default_variable = variable_options[0]


# ----------------------------
# SAMPLE
# ----------------------------

default_sample = (
    preset.get(
        "sample",
        20,
    )
    if preset
    else 20
)

if default_sample not in [
    10,
    15,
    20,
]:
    default_sample = 20


col1, col2, col3 = st.columns(3)


with col1:
    team_name = st.selectbox(
        "3. Team",
        team_names,
        index=team_names.index(
            default_team
        ),
        disabled=bool(preset),
    )


with col2:
    variable = st.selectbox(
        "4. Variable",
        variable_options,
        index=variable_options.index(
            default_variable
        ),
        disabled=bool(preset),
    )


with col3:
    sample = st.selectbox(
        "5. Sample",
        [
            10,
            15,
            20,
        ],
        index=[
            10,
            15,
            20,
        ].index(
            default_sample
        ),
        disabled=bool(preset),
    )


cfg = presets[
    variable
]

team_id = team_map[
    team_name
]


# ============================================================
# RESEARCH QUESTION
# ============================================================

st.markdown(
    '<div class="step-card">',
    unsafe_allow_html=True,
)

st.write(
    "### Research Question"
)

st.write(
    cfg[
        "question"
    ].replace(
        "the team",
        team_name,
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
    "</div>",
    unsafe_allow_html=True,
)


# ============================================================
# LOAD DATA
# ============================================================

if st.button(
    "Load Game Data",
    type="primary",
):
    st.session_state[
        "loaded_key"
    ] = (
        sport,
        team_id,
        team_name,
        season,
        sample,
        variable,
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
    loaded_team_name,
    loaded_season,
    loaded_sample,
    loaded_variable,
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
            loaded_variable,
        )

    except Exception as error:
        st.error(
            "The game data could not be loaded."
        )

        st.code(
            str(error)
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
        f"{missing} game(s) were missing the statistic needed for this investigation. "
        "Those games were left out."
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
        "The statistic needed for this investigation was unavailable for all of the selected games."
    )
    st.stop()


if len(df_valid) < loaded_sample:
    st.caption(
        f"Using {len(df_valid)} usable games from the requested sample of {loaded_sample}."
    )


# ============================================================
# STEP 1
# ============================================================

st.write(
    "## Step 1 — Examine the evidence"
)

st.caption(
    "Look at the evidence first. Then decide which category each game belongs in."
)


student_table = (
    df_valid[
        [
            "date",
            "opponent",
            "evidence",
            "result",
        ]
    ]
    .copy()
)


student_table.columns = [
    "Date",
    "Opponent",
    cfg[
        "evidence_label"
    ],
    "Outcome",
]


student_table.insert(
    0,
    "Game",
    range(
        1,
        len(student_table) + 1,
    ),
)


st.dataframe(
    student_table,
    use_container_width=True,
    hide_index=True,
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


editable_table = (
    student_table.copy()
)

editable_table[
    "Your Category"
] = ""


edited = st.data_editor(
    editable_table,
    use_container_width=True,
    hide_index=True,
    disabled=[
        "Game",
        "Date",
        "Opponent",
        cfg[
            "evidence_label"
        ],
        "Outcome",
    ],
    column_config={
        "Your Category":
            st.column_config.SelectboxColumn(
                "Your Category",
                options=[
                    "",
                    cfg["a1"],
                    cfg["a2"],
                ],
                required=False,
            )
    },
    key=(
        f"editor_"
        f"{loaded_sport}_"
        f"{loaded_team_id}_"
        f"{loaded_season}_"
        f"{loaded_variable}_"
        f"{loaded_sample}"
    ),
)


if st.button(
    "Check My Classifications"
):
    answers = edited[
        "Your Category"
    ].tolist()

    expected = df_valid[
        "expected_category"
    ].tolist()

    correct = [
        answer == correct_answer
        for answer, correct_answer
        in zip(
            answers,
            expected,
        )
    ]

    number_correct = sum(
        correct
    )

    st.session_state[
        "classification_ok"
    ] = all(correct)

    if all(correct):
        st.success(
            f"Perfect — {number_correct} of {len(correct)} classifications are correct."
        )

    else:
        st.warning(
            f"{number_correct} of {len(correct)} are correct. "
            "Fix the rows listed below and try again."
        )

        wrong_rows = [
            str(index + 1)
            for index, is_correct
            in enumerate(correct)
            if not is_correct
        ]

        st.write(
            "Rows to fix: **"
            + ", ".join(
                wrong_rows
            )
            + "**"
        )


if not st.session_state.get(
    "classification_ok",
    False,
):
    st.info(
        "When all classifications are correct, the analysis section will unlock."
    )

    st.stop()


# ============================================================
# STEP 3
# ============================================================

st.write(
    "## Step 3 — Two-Way Frequency Table"
)


table = two_way_table(
    df_valid,
    cfg["a1"],
    cfg["a2"],
)


st.dataframe(
    table,
    use_container_width=True,
)


category_1_wins = int(
    table.loc[
        cfg["a1"],
        "Win",
    ]
)

category_1_total = int(
    table.loc[
        cfg["a1"],
        "Total",
    ]
)

category_2_wins = int(
    table.loc[
        cfg["a2"],
        "Win",
    ]
)

category_2_total = int(
    table.loc[
        cfg["a2"],
        "Total",
    ]
)


# ============================================================
# STEP 4
# ============================================================

st.write(
    "## Step 4 — Compare Conditional Percentages"
)


p1 = percent(
    category_1_wins,
    category_1_total,
)

p2 = percent(
    category_2_wins,
    category_2_total,
)

difference = abs(
    p1 - p2
)


col1, col2 = st.columns(2)


with col1:
    st.metric(
        cfg["a1"],
        f"{p1:.1f}% win rate",
    )

    st.caption(
        f"{category_1_wins} ÷ "
        f"{category_1_total} × 100 "
        f"= {p1:.1f}%"
    )


with col2:
    st.metric(
        cfg["a2"],
        f"{p2:.1f}% win rate",
    )

    st.caption(
        f"{category_2_wins} ÷ "
        f"{category_2_total} × 100 "
        f"= {p2:.1f}%"
    )


st.metric(
    "Difference",
    f"{difference:.1f} percentage points",
)


chart_data = pd.DataFrame({
    "Category": [
        cfg["a1"],
        cfg["a2"],
    ],

    "Win %": [
        p1,
        p2,
    ],
}).set_index(
    "Category"
)


st.bar_chart(
    chart_data
)


# ============================================================
# STEP 5
# ============================================================

st.write(
    "## Step 5 — Make Your Claim"
)


st.markdown(
    f"""
<div class="good">

<b>Use the numbers as evidence.</b>

<br><br>

When <b>{cfg['a1']}</b> occurred,
the team won <b>{p1:.1f}%</b> of the time.

<br><br>

When <b>{cfg['a2']}</b> occurred,
the team won <b>{p2:.1f}%</b> of the time.

<br><br>

The difference between the two win rates was
<b>{difference:.1f} percentage points</b>.

</div>
""",
    unsafe_allow_html=True,
)


verdict = st.radio(
    "Do the variables appear associated in this sample?",
    [
        "YES",
        "NO",
        "UNCLEAR",
    ],
    horizontal=True,
)


reasoning = st.text_area(
    "Explain your reasoning using both percentages.",
    placeholder=(
        "Our data suggests that the variables..."
    ),
)


limitation = st.text_area(
    "Name one limitation of the investigation.",
    placeholder=(
        "One limitation of this investigation is..."
    ),
)


st.caption(
    "Remember: association does not prove causation."
)


# ============================================================
# SOURCE INFORMATION
# ============================================================

with st.expander(
    "Source information"
):
    if loaded_sport == "NBA":
        st.write(
            "NBA schedules and box-score statistics are retrieved from ESPN sports data."
        )

    elif loaded_sport == "MLB":
        st.write(
            "MLB schedules and game data are retrieved from MLB's Stats API."
        )

    elif loaded_sport == "NHL":
        st.write(
            "NHL schedules, box scores, and scoring summaries are retrieved from NHL game data."
        )

    elif loaded_sport == "MLS":
        st.write(
            "MLS schedules and match statistics are retrieved from ESPN soccer data."
        )

    st.write(
        "For the class project, students should still record the original schedule or box score as their source."
    )
