
# Sports Association Lab — NBA Starter Version

A Streamlit app for middle-school categorical data investigations using NBA game data.

## What this starter version includes
- NBA team selector
- Seasons 2022-23 through 2025-26
- 10, 15, or 20-game samples
- Variables aligned to the classroom project:
  - Home vs Away
  - Team points threshold
  - More 3-pointers than opponent
  - Fewer turnovers than opponent
  - FG% threshold
  - More rebounds than opponent
  - Led at halftime
  - Three-pointer threshold
  - Opponent points threshold
  - Assists threshold
- Student classification checking
- Two-way frequency table
- Conditional percentages
- Percentage-point difference
- Comparison graph
- Teacher assignment-code builder

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push these files to a GitHub repository.
2. Go to https://share.streamlit.io
3. Click **Create app**.
4. Choose the repository.
5. Set the main file path to `app.py`.
6. Deploy.

## Important
This starter version retrieves NBA schedule/box-score data from ESPN public sports endpoints.
The app also tells students to record the original schedule or box score in their source log.

Next planned additions:
- MLB
- NHL
- MLS
- Custom thresholds
- More teacher controls
