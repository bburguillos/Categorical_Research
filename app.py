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

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

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
# Helpers
# ----------------------------
def safe_get(url, params=None, timeout=20):
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


@st.cache_data(ttl=3600, show_spinner=False)
def get_nba_teams():
    data = safe_get(f"{ESPN_BASE}/teams")

    teams = []

    sports = data.get("sports", [])

    if sports:
        leagues = sports[0].get("leagues", [])

        if leagues:
            for item in leagues[0].get("teams", []):
                t = item.get("team", {})

                if t.get("id") and t.get("displayName"):
                    teams.append({
                        "id": str(t["id"]),
                        "name": t["displayName"],
                        "abbr": t.get("abbreviation", ""),
                        "slug": t.get("slug", "")
                    })

    return sorted(
        teams,
        key=lambda x: x["name"]
    )


def season_end_year(label: str) -> int:
    m = re.match(r"(\d{4})-(\d{2})", label)

    if not m:
        return int(label)

    start = int(m.group(1))

    return start + 1


@st.cache_data(ttl=1800, show_spinner=False)
def get_schedule(team_id: str, season_label: str):

    season = season_end_year(season_label)

    url = f"{ESPN_BASE}/teams/{team_id}/schedule"

    data = safe_get(
        url,
        params={
            "season": season,
            "seasontype": 2
        }
    )

    return data.get("events", [])


def get_competitors(event):

    comps = event.get("competitions", [])

    if not comps:
        return []

    return comps[0].get("competitors", [])


def score_number(score_obj):

    if score_obj is None:
        return None

    if isinstance(score_obj, (int, float)):
        return float(score_obj)

    if isinstance(score_obj, str):

        try:
            return float(score_obj)

        except Exception:
            return None

    if isinstance(score_obj, dict):

        for key in [
            "value",
            "displayValue",
            "score"
        ]:

            if key in score_obj:

                try:
                    return float(score_obj[key])

                except Exception:
                    pass

    return None


def get_game_core(event, team_id):

    competitors = get_competitors(event)

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

    team_score_raw = score_number(
        team_comp.get("score")
    )

    opp_score_raw = score_number(
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

    winner_flag = team_comp.get("winner")

    if (
        winner_flag is True
        or team_score > opp_score
    ):

        result = "Win"

    else:

        result = "Did Not Win"

    home_away = (
        "Home"
        if team_comp.get("homeAway") == "home"
        else "Away"
    )

    date = event.get("date", "")

    try:

        dt = pd.to_datetime(date)

        date_display = dt.strftime(
            "%b %d, %Y"
        )

    except Exception:

        date_display = date[:10]

    return {
        "event_id": str(
            event.get(
                "id",
                ""
            )
        ),
        "date": date_display,
        "opponent": opp_comp.get(
            "team",
            {}
        ).get(
            "displayName",
            "Opponent"
        ),
        "home_away": home_away,
        "team_score": team_score,
        "opp_score": opp_score,
        "result": result,
    }


@st.cache_data(ttl=86400, show_spinner=False)
def get_summary(event_id: str):

    return safe_get(
        f"{ESPN_BASE}/summary",
        params={
            "event": event_id
        }
    )


def norm(s):

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(s).lower()
    )


def find_team_box(summary, team_id):

    teams = summary.get(
        "boxscore",
        {}
    ).get(
        "teams",
        []
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

        if tid == str(team_id):
            return tb

    return None


def find_opponent_box(summary, team_id):

    teams = summary.get(
        "boxscore",
        {}
    ).get(
        "teams",
        []
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

        if tid and tid != str(team_id):
            return tb

    return None


def stat_map(team_box):

    out = {}

    if not team_box:
        return out

    for s in team_box.get(
        "statistics",
        []
    ):

        candidates = [
            s.get("name", ""),
            s.get("displayName", ""),
            s.get("label", ""),
            s.get("abbreviation", ""),
        ]

        value = s.get(
            "displayValue",
            s.get("value")
        )

        for c in candidates:

            if c:

                out[norm(c)] = value

    return out


def first_stat_value(stats, keys):

    for key in keys:

        nk = norm(key)

        if nk in stats:

            return stats[nk]

    for k, v in stats.items():

        for key in keys:

            if norm(key) in k:

                return v

    return None


def as_number(v):

    if v is None:
        return None

    s = str(v)

    s = s.replace(
        "%",
        ""
    )

    s = s.replace(
        ",",
        ""
    )

    s = s.strip()

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

    if x <= 1.0:

        return x * 100

    return x


def halftime_points(summary, team_id):

    header = summary.get(
        "header",
        {}
    )

    comps = header.get(
        "competitions",
        []
    )

    if not comps:
        return None, None

    competitors = comps[0].get(
        "competitors",
        []
    )

    team_lines = None
    opp_lines = None

    for c in competitors:

        tid = str(
            c.get(
                "team",
                {}
            ).get(
                "id",
                ""
            )
        )

        lines = c.get(
            "linescores",
            []
        )

        vals = []

        for ls in lines:

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


def metric_values(summary, team_id):

    tbox = find_team_box(
        summary,
        team_id
    )

    obox = find_opponent_box(
        summary,
        team_id
    )

    ts = stat_map(tbox)
    os = stat_map(obox)

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

    ht_team, ht_opp = halftime_points(
        summary,
        team_id
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


PRESETS = {

    "Home vs. Away": {

        "type": "home_away",

        "a1": "Home",

        "a2": "Away",

        "evidence_label": "Location",

        "question":
            "Does playing at home appear associated with whether the team wins?"
    },

    "Team scores at least 110 points": {

        "type":
            "team_points_threshold",

        "threshold":
            110,

        "a1":
            "110 Plus Points",

        "a2":
            "Under 110",

        "evidence_label":
            "Team points",

        "question":
            "Is scoring 110 or more points associated with whether the team wins?"
    },

    "More 3-pointers than opponent": {

        "type":
            "compare_more",

        "metric_team":
            "team_3pm",

        "metric_opp":
            "opp_3pm",

        "a1":
            "More 3-Pointers",

        "a2":
            "Not More 3-Pointers",

        "evidence_label":
            "Team 3PM vs. opponent 3PM",

        "question":
            "Is making more three-pointers than the opponent associated with whether the team wins?"
    },

    "Fewer turnovers than opponent": {

        "type":
            "compare_fewer",

        "metric_team":
            "team_turnovers",

        "metric_opp":
            "opp_turnovers",

        "a1":
            "Fewer Turnovers",

        "a2":
            "Not Fewer Turnovers",

        "evidence_label":
            "Team turnovers vs. opponent turnovers",

        "question":
            "Is having fewer turnovers than the opponent associated with whether the team wins?"
    },

    "Field goal percentage at least 50%": {

        "type":
            "metric_threshold",

        "metric_team":
            "team_fg_pct",

        "threshold":
            50,

        "a1":
            "50 Percent Plus FG",

        "a2":
            "Under 50 Percent",

        "evidence_label":
            "Team FG%",

        "question":
            "Is shooting at least 50 percent from the field associated with whether the team wins?"
    },

    "More rebounds than opponent": {

        "type":
            "compare_more",

        "metric_team":
            "team_rebounds",

        "metric_opp":
            "opp_rebounds",

        "a1":
            "More Rebounds",

        "a2":
            "Not More Rebounds",

        "evidence_label":
            "Team rebounds vs. opponent rebounds",

        "question":
            "Is outrebounding the opponent associated with whether the team wins?"
    },

    "Led at halftime": {

        "type":
            "compare_more",

        "metric_team":
            "halftime_team",

        "metric_opp":
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

    "Made at least 12 three-pointers": {

        "type":
            "metric_threshold",

        "metric_team":
            "team_3pm",

        "threshold":
            12,

        "a1":
            "12 Plus 3-Pointers",

        "a2":
            "Fewer Than 12",

        "evidence_label":
            "Team 3PM",

        "question":
            "Is making 12 or more three-pointers associated with whether the team wins?"
    },

    "Held opponent under 110 points": {

        "type":
            "opp_points_under",

        "threshold":
            110,

        "a1":
            "Opponent Under 110",

        "a2":
            "Opponent 110 Plus",

        "evidence_label":
            "Opponent points",

        "question":
            "Is holding the opponent under 110 points associated with whether the team wins?"
    },

    "At least 25 assists": {

        "type":
            "metric_threshold",

        "metric_team":
            "team_assists",

        "threshold":
            25,

        "a1":
            "25 Plus Assists",

        "a2":
            "Under 25 Assists",

        "evidence_label":
            "Team assists",

        "question":
            "Are 25 or more team assists associated with whether the team wins?"
    },
}


def classify(row, cfg):

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


def evidence_text(row, cfg):

    t = cfg["type"]

    if t == "home_away":

        return row["home_away"]

    if t == "team_points_threshold":

        return str(
            row["team_score"]
        )

    if t == "opp_points_under":

        return str(
            row["opp_score"]
        )

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

            return f"{float(v):.1f}%"

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

        if "halftime" in cfg["metric_team"]:

            return (
                f"{float(a):g} – "
                f"{float(b):g}"
            )

        return (
            f"{float(a):g} vs. "
            f"{float(b):g}"
        )

    return ""


@st.cache_data(ttl=1800, show_spinner=False)
def build_dataset(
    team_id,
    season_label,
    sample_size,
    variable_name
):

    events = get_schedule(
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
            .get("status", {})
            .get("type", {})
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

        core = get_game_core(
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

    cfg = PRESETS[
        variable_name
    ]

    rows = []

    for g in completed:

        row = dict(g)

        needs_box = (
            cfg["type"]
            in (
                "metric_threshold",
                "compare_more",
                "compare_fewer"
            )
        )

        if needs_box:

            try:

                summary = get_summary(
                    g["event_id"]
                )

                row.update(
                    metric_values(
                        summary,
                        team_id
                    )
                )

            except Exception:

                row.update({
                    "team_3pm":
                        None,

                    "opp_3pm":
                        None,

                    "team_turnovers":
                        None,

                    "opp_turnovers":
                        None,

                    "team_rebounds":
                        None,

                    "opp_rebounds":
                        None,

                    "team_assists":
                        None,

                    "team_fg_pct":
                        None,

                    "halftime_team":
                        None,

                    "halftime_opp":
                        None,
                })

        row["expected_category"] = (
            classify(
                row,
                cfg
            )
        )

        row["evidence"] = (
            evidence_text(
                row,
                cfg
            )
        )

        rows.append(row)

    return pd.DataFrame(rows)


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

        padding = "=" * (
            -len(code) % 4
        )

        raw = (
            base64
            .urlsafe_b64decode(
                code + padding
            )
        )

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:

        return None


def two_way(df, a1, a2):

    work = df.copy()

    out = pd.crosstab(
        work["expected_category"],
        work["result"]
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


def percent(n, d):

    return (
        0.0
        if d == 0
        else 100.0 * n / d
    )


# ----------------------------
# Header
# ----------------------------

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


try:

    teams = get_nba_teams()

except Exception as e:

    st.error(
        "The NBA team list could not be loaded."
    )

    st.code(
        str(e)
    )

    st.stop()


if not teams:

    st.error(
        "The NBA team list could not be loaded. Please try again in a moment."
    )

    st.stop()


team_name_to_id = {
    t["name"]: t["id"]
    for t in teams
}

team_names = list(
    team_name_to_id.keys()
)

season_options = [
    "2025-26",
    "2024-25",
    "2023-24",
    "2022-23"
]


# ----------------------------
# Teacher mode
# ----------------------------

if mode == "Teacher Assignment Builder":

    st.subheader(
        "Teacher Assignment Builder"
    )

    st.write(
        "Create a setup code so students cannot accidentally choose the wrong team, season, variable, or sample."
    )

    c1, c2 = st.columns(2)

    with c1:

        t_team = st.selectbox(
            "Team",
            team_names,
            key="teacher_team"
        )

        t_season = st.selectbox(
            "Season",
            season_options,
            key="teacher_season"
        )

    with c2:

        t_var = st.selectbox(
            "Categorical variable",
            list(PRESETS.keys()),
            key="teacher_var"
        )

        t_sample = st.selectbox(
            "Sample size",
            [
                10,
                15,
                20
            ],
            index=2,
            key="teacher_sample"
        )

    cfg = PRESETS[t_var]

    st.info(
        f"Research question: {cfg['question']}"
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
            "sport":
                "NBA",

            "team":
                t_team,

            "season":
                t_season,

            "variable":
                t_var,

            "sample":
                t_sample
        }

        code = encode_task(
            payload
        )

        st.success(
            "Assignment code created."
        )

        st.code(
            code,
            language=None
        )

        st.caption(
            "Students paste this code into Student Research mode."
        )

    st.stop()


# ----------------------------
# Student mode
# ----------------------------

st.subheader(
    "Student Research"
)

task_code = st.text_input(
    "Have an assignment code? Paste it here (optional).",
    placeholder="Paste teacher code here"
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


default_team_idx = 0
default_season_idx = 0
default_var_idx = 0
default_sample_idx = 2


if preset:

    if preset.get("team") in team_names:

        default_team_idx = (
            team_names.index(
                preset["team"]
            )
        )

    if preset.get("season") in season_options:

        default_season_idx = (
            season_options.index(
                preset["season"]
            )
        )

    if preset.get("variable") in PRESETS:

        default_var_idx = (
            list(PRESETS.keys()).index(
                preset["variable"]
            )
        )

    if preset.get("sample") in [
        10,
        15,
        20
    ]:

        default_sample_idx = (
            [
                10,
                15,
                20
            ].index(
                preset["sample"]
            )
        )


c1, c2, c3, c4 = st.columns(4)


with c1:

    team_name = st.selectbox(
        "1. Team",
        team_names,
        index=default_team_idx,
        disabled=bool(preset)
    )


with c2:

    season_label = st.selectbox(
        "2. Season",
        season_options,
        index=default_season_idx,
        disabled=bool(preset)
    )


with c3:

    variable_name = st.selectbox(
        "3. Variable",
        list(PRESETS.keys()),
        index=default_var_idx,
        disabled=bool(preset)
    )


with c4:

    sample_size = st.selectbox(
        "4. Sample",
        [
            10,
            15,
            20
        ],
        index=default_sample_idx,
        disabled=bool(preset)
    )


cfg = PRESETS[
    variable_name
]

team_id = team_name_to_id[
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
        team_id,
        season_label,
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
    team_id,
    season_label,
    sample_size,
    variable_name
) = loaded_key


cfg = PRESETS[
    variable_name
]


team_name = next(
    (
        n
        for n, tid
        in team_name_to_id.items()
        if tid == team_id
    ),
    team_name
)


with st.spinner(
    "Loading completed games and box-score data..."
):

    try:

        df = build_dataset(
            team_id,
            season_label,
            sample_size,
            variable_name
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

    with st.expander(
        "Show schedule diagnostic"
    ):

        try:

            raw_events = get_schedule(
                team_id,
                season_label
            )

            st.write(
                f"Events returned by ESPN: **{len(raw_events)}**"
            )

            if raw_events:

                preview = []

                for e in raw_events[:5]:

                    comps = e.get(
                        "competitions",
                        []
                    )

                    status = {}

                    if comps:

                        status = (
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

                    competitors2 = (
                        comps[0]
                        .get(
                            "competitors",
                            []
                        )
                        if comps
                        else []
                    )

                    score_preview = []

                    for c in competitors2:

                        score_preview.append({
                            "team":
                                c.get(
                                    "team",
                                    {}
                                ).get(
                                    "displayName"
                                ),

                            "score":
                                c.get("score")
                        })

                    preview.append({

                        "name":
                            e.get("name"),

                        "date":
                            e.get("date"),

                        "completed":
                            status.get(
                                "completed"
                            ),

                        "state":
                            status.get(
                                "state"
                            ),

                        "status_name":
                            status.get(
                                "name"
                            ),

                        "scores":
                            str(
                                score_preview
                            )
                    })

                st.dataframe(
                    pd.DataFrame(
                        preview
                    ),
                    use_container_width=True
                )

        except Exception as e:

            st.code(
                str(e)
            )

    st.stop()


missing = (
    df[
        "expected_category"
    ]
    .isna()
    .sum()
)


if missing:

    st.warning(
        f"{missing} game(s) are missing the statistic needed for this variable. "
        "Those rows should be checked against the original box score before using them."
    )


df_valid = df[
    df["expected_category"]
    .notna()
].copy()


st.write(
    "## Step 1 — Examine the evidence"
)

st.caption(
    "Do not jump straight to the category. Look at the evidence first."
)


student_table = df_valid[
    [
        "date",
        "opponent",
        "evidence",
        "result"
    ]
].copy()


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
    f"For each row, choose **{cfg['a1']}** or **{cfg['a2']}**."
)


edit = student_table[
    [
        "Game",
        "Date",
        "Opponent",
        cfg["evidence_label"],
        "Outcome"
    ]
].copy()


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
        f"{team_id}_"
        f"{season_label}_"
        f"{variable_name}_"
        f"{sample_size}"
    )
)


if st.button(
    "Check My Classifications"
):

    answers = (
        edited[
            "Your Category"
        ].tolist()
    )

    expected = (
        df_valid[
            "expected_category"
        ].tolist()
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
            f"{num_correct} of {len(correct)} are correct. Fix the row numbers below and check again."
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


pcol1, pcol2 = st.columns(2)


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

    st.write(
        "Game schedules and box-score statistics in this NBA version "
        "are retrieved from ESPN's public sports data endpoints. "
        "For graded work, students should still use the original "
        "game schedule or box score as the source they record in the packet."
    )
