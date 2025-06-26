from flask import Flask, render_template, request
import pandas as pd
import os

app = Flask(__name__)

"""Simple Flask app to browse comments_maixiaowen by date and emotion.

The comment CSV files are stored in a batch directory. By default the
application will try to locate ``emotion_count_by_time_full.csv`` in one of
``comments_batch2``, ``comments_batch1`` or ``comments_maixiaowen`` under the project
root.  You can override the directory by setting the ``BATCH_DIR`` environment
variable.
"""

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def detect_batch_dir() -> str:
    """Return the directory containing the comment CSV files."""

    custom = os.environ.get("BATCH_DIR")
    if custom:
        path = os.path.join(BASE_DIR, custom)
        csv_path = os.path.join(path, "emotion_count_by_time_full.csv")
        if os.path.isfile(csv_path):
            return path

    for name in ("comments_batch2", "comments_batch1", "comments_maixiaowen"):
        path = os.path.join(BASE_DIR, name)
        csv_path = os.path.join(path, "emotion_count_by_time_full.csv")
        if os.path.isfile(csv_path):
            return path

    raise FileNotFoundError(
        "emotion_count_by_time_full.csv not found in default batch directories"
    )


BATCH_DIR = detect_batch_dir()
COUNT_CSV = os.path.join(BATCH_DIR, "emotion_count_by_time_full.csv")

# load count data
count_df = pd.read_csv(COUNT_CSV)
EMOTIONS = [c for c in count_df.columns if c not in ['bvid', 'time']]
DATES = sorted(count_df['time'].unique())


def load_comments(start_date: str, end_date: str, emotion: str):
    """Return comments_maixiaowen within ``start_date`` and ``end_date`` for ``emotion``."""

    results = []
    mask = (
        (count_df['time'] >= start_date)
        & (count_df['time'] <= end_date)
        & (count_df[emotion] > 0)
    )
    filtered = count_df.loc[mask]

    for bvid in filtered['bvid'].unique():
        fname = os.path.join(BATCH_DIR, f"{bvid}_comments.csv")
        if not os.path.exists(fname):
            continue

        df = pd.read_csv(fname)
        if 'emotion' not in df.columns or '评论时间' not in df.columns:
            continue

        df['date'] = df['评论时间'].astype(str).str[:10]
        subset = df[
            (df['emotion'] == emotion)
            & (df['date'] >= start_date)
            & (df['date'] <= end_date)
        ]
        results.extend(subset['评论内容'].dropna().tolist())
    return results


@app.route('/', methods=['GET', 'POST'])
def filter_comments():
    selected_start = DATES[0]
    selected_end = DATES[-1]
    selected_emotion = None
    comments = None

    if request.method == 'POST':
        start = request.form.get('start_date')
        end = request.form.get('end_date')
        selected_emotion = request.form.get('emotion')

        if start:
            selected_start = start
        if end:
            selected_end = end

        if selected_start and selected_end and selected_emotion:
            comments = load_comments(selected_start, selected_end, selected_emotion)

    return render_template(
        'filter_comments.html',
        min_date=DATES[0],
        max_date=DATES[-1],
        emotions=EMOTIONS,
        comments=comments,
        selected_start=selected_start,
        selected_end=selected_end,
        selected_emotion=selected_emotion,
    )


if __name__ == '__main__':
    app.run(debug=True)
