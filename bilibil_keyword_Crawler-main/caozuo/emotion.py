from tqdm import tqdm
import os
import pandas as pd
import openai
import time

API_KEY = 'sk-c6YAeki46tu91kRHbCiZRwTEWuRtsUUbaHL21fX87HHt1fb1'
BASE_URL = 'https://api.kksj.org/v1'
client = openai.OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)

EMOTION_COLS = [
    "Sadness",
    "Anger",
    "Regret",
    "Disgust",
    "Joy",
    "Expectation",
    "Surprise",
    "Love",
    "Neutral",
]

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SEARCH_CSV = os.path.join(BASE_DIR, 'bilibili_search.csv')
COMMENTS_DIR = os.path.join(BASE_DIR, 'comments_batch1')
STATS_PATH = os.path.join(os.path.dirname(__file__), 'emotion_count_by_time_full.csv')

search_df = pd.read_csv(SEARCH_CSV)
bvid_to_info = {
    row['bvid']: (str(row['description']), str(row['keywords']))
    for idx, row in search_df.iterrows()
}

def get_sentiment_from_llm(description, keywords, comment, max_retry=3):
    prompt = (
        "You are an expert in emotion classification. "
        "Based on the following video description, keywords, and comment, "
        "please judge which of the 9 emotions the comment expresses (choose only one), "
        "and return ONLY the emotion English name (one of: Sadness, Anger, Regret, Disgust, Joy, Expectation, Surprise, Love, Neutral):\n\n"
        f"Video Description: {description}\n"
        f"Keywords: {keywords}\n"
        f"Comment: {comment}\n"
        "Output ONLY the English category (e.g., Joy), nothing else."
    )
    for _ in range(max_retry):
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            result = response.choices[0].message.content.strip()
            allowed = EMOTION_COLS
            for a in allowed:
                if a.lower() == result.lower():
                    return a
            for a in allowed:
                if a.lower() in result.lower():
                    return a
            return "Neutral"
        except Exception as e:
            print(f"API调用失败，重试：{e}")
            time.sleep(2)
    return "Neutral"

# 关键！统一归一化
def normalize_emotion(x):
    if pd.isna(x):           # 处理nan、None
        return "Neutral"
    x = str(x).strip()
    if x in EMOTION_COLS:
        return x
    return "Neutral"

def update_stats(df: pd.DataFrame, bvid: str) -> None:
    """Update daily emotion counts for the given BV video."""

    if not os.path.exists(STATS_PATH):
        stats_df = pd.DataFrame(columns=['bvid', 'time'] + EMOTION_COLS)
    else:
        stats_df = pd.read_csv(STATS_PATH)

    df['emotion'] = df['emotion'].apply(normalize_emotion)
    df['time'] = pd.to_datetime(df['评论时间']).dt.date.astype(str)
    counts = (
        df.groupby('time')['emotion']
        .value_counts()
        .unstack()
        .reindex(columns=EMOTION_COLS, fill_value=0)
        .astype(int)
        .reset_index()
    )

    counts.insert(0, 'bvid', bvid)

    if not stats_df.empty:
        stats_df.set_index(['bvid', 'time'], inplace=True)

    for _, row in counts.iterrows():
        key = (row['bvid'], row['time'])
        values = row[EMOTION_COLS]
        if key in stats_df.index:
            stats_df.loc[key, EMOTION_COLS] = (
                stats_df.loc[key, EMOTION_COLS].astype(int) + values
            )
        else:
            stats_df.loc[key, EMOTION_COLS] = values

    stats_df = stats_df.reset_index()
    stats_df.to_csv(STATS_PATH, index=False, encoding='utf-8-sig')

def compute_batch_stats(directory=COMMENTS_DIR):
    all_stats = []
    for fname in os.listdir(directory):
        if not fname.endswith('_comments.csv'):
            continue
        path = os.path.join(directory, fname)
        df = pd.read_csv(path)
        if 'emotion' not in df.columns:
            continue
        df['emotion'] = df['emotion'].apply(normalize_emotion)
        df['time'] = pd.to_datetime(df['评论时间']).dt.date.astype(str)
        counts = (
            df.groupby('time')['emotion']
            .value_counts()
            .unstack()
            .reindex(columns=EMOTION_COLS, fill_value=0)
        )
        for col in EMOTION_COLS:
            counts[col] = pd.to_numeric(counts[col], errors='coerce').fillna(0).astype(int)
        counts = counts.reset_index()
        counts.insert(0, 'bvid', fname.replace('_comments.csv', ''))
        all_stats.append(counts)
    if not all_stats:
        return
    stats_df = pd.concat(all_stats, ignore_index=True)
    stats_df = (
        stats_df.groupby(['bvid', 'time'])[EMOTION_COLS]
        .sum()
        .reset_index()
    )
    stats_df.to_csv(STATS_PATH, index=False, encoding='utf-8-sig')

def process_file(file_path, desc, kw, fname):
    df = pd.read_csv(file_path)
    if '评论内容' not in df.columns:
        print(f"{file_path} 缺少评论内容字段，跳过")
        return
    emotion_list = []
    for idx, row in tqdm(
        df.iterrows(),
        total=len(df),
        desc=f"{fname}情感标注",
        leave=False,
    ):
        comment = str(row['评论内容'])
        emotion = get_sentiment_from_llm(desc, kw, comment)
        emotion_list.append(emotion)
        print(
            f"【{fname} 第{idx+1}条】评论: {comment[:40]}... | 分类: {emotion}"
        )
    df['emotion'] = emotion_list
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"{fname} 已直接更新情感分类到原csv")

def process_new_files(directory=COMMENTS_DIR):
    files = [f for f in os.listdir(directory) if f.endswith('_comments.csv')]
    for fname in tqdm(files, desc='检查评论文件'):
        file_path = os.path.join(directory, fname)
        header = pd.read_csv(file_path, nrows=0)
        bv = fname.replace('_comments.csv', '')
        if bv not in bvid_to_info:
            print(f"BV号{bv}未出现在bilibili_search.csv，跳过")
            continue
        desc, kw = bvid_to_info[bv]
        if 'emotion' not in header.columns:
            process_file(file_path, desc, kw, fname)
    compute_batch_stats(directory)

if __name__ == '__main__':
    process_new_files()
