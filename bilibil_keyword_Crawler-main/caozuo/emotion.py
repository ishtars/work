from tqdm import tqdm
import os
import pandas as pd
import openai
import time
import argparse

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
STATS_PATH = os.path.join(os.path.dirname(__file__), 'emotion_count_by_time_full.csv')


def find_comment_dirs() -> list:
    """Return available comment directories in BASE_DIR."""

    defaults = [
        "comments_batch1",
        "comments_batch2",
        "comments_batch3",
        "comments_maixiaowen",
        "comments",
    ]
    dirs = []
    for name in defaults:
        path = os.path.join(BASE_DIR, name)
        if os.path.isdir(path):
            dirs.append(name)
    # discover any additional "comments_batch*" folders
    for name in os.listdir(BASE_DIR):
        if (
            name.startswith("comments_batch")
            and name not in dirs
            and os.path.isdir(os.path.join(BASE_DIR, name))
        ):
            dirs.append(name)
    return dirs


def select_directory() -> str:
    """Return the directory chosen by the user from available comment dirs."""

    env_dir = os.environ.get("BATCH_DIR")
    if env_dir and os.path.isdir(os.path.join(BASE_DIR, env_dir)):
        return os.path.join(BASE_DIR, env_dir)

    candidates = find_comment_dirs()
    if not candidates:
        return os.path.join(BASE_DIR, "comments_maixiaowen") #没有的情况下用默认目录
    if len(candidates) == 1:
        return os.path.join(BASE_DIR, candidates[0])

    print("可用评论目录：")
    for i, name in enumerate(candidates, 1):
        print(f"{i}. {name}")
    choice = input(f"选择目录 [1-{len(candidates)}] (默认1): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(candidates):
        idx = int(choice) - 1
    else:
        idx = 0
    return os.path.join(BASE_DIR, candidates[idx])

search_df = pd.read_csv(SEARCH_CSV)
bvid_to_info = {
    row['bvid']: (str(row['description']), str(row['keywords']))
    for idx, row in search_df.iterrows()
}

def get_sentiment_from_llm(description, keywords, comment, max_retry=3):
     prompt = (
        "You are an expert in emotion classification. "
        "Based on the following video description, keywords, and comment, please do the following:\n"
        "1. Judge whether the comment contains a meaningful discussion, opinion, or evaluation about the game itself (such as gameplay, mechanics, graphics, events, specific experiences, or emotions related to the game).\n"
        "2. If the comment does not discuss the game content (for example, only shares personal luck, drops, greetings, general chatting, or self-boasting such as 'I also got it!', 'My account is always lucky', 'Everyone is so nice', etc.), or is otherwise irrelevant to the game itself, classify it as 'Neutral'.\n"
        "3. If the comment is related to the game content, then judge which of the following 9 emotions it expresses (choose only one): Sadness, Anger, Regret, Disgust, Joy, Expectation, Surprise, Love, Neutral.\n"
        "Output ONLY the English emotion name (e.g., Joy), nothing else.\n"
        "\n"
        f"Video Description: {description}\n"
        f"Keywords: {keywords}\n"
        f"Comment: {comment}\n"
        "Output ONLY the English category (e.g., Joy), nothing else."
          "For example:"
          "- Comment: '我也出了' → Neutral"
          "- Comment: '地图太大了，玩起来累' → Sadness"
          "- Comment: '官方太良心了，今天奖励好多' → Joy"
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
    """Update daily emotion counts for ``bvid`` in ``STATS_PATH``."""

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
    )
    for col in EMOTION_COLS:
        counts[col] = pd.to_numeric(counts[col], errors="coerce").fillna(0).astype(int)
    counts = counts.reset_index()

    counts.insert(0, 'bvid', bvid)

    # create a MultiIndex so new rows can be assigned via .loc
    stats_df.set_index(['bvid', 'time'], inplace=True)

    for _, row in counts.iterrows():
        key = (row['bvid'], row['time'])
        values = row[EMOTION_COLS]
        # overwrite any existing stats for this BV/time combination
        stats_df.loc[key, EMOTION_COLS] = values

    stats_df = stats_df.reset_index()
    stats_df.to_csv(STATS_PATH, index=False, encoding='utf-8-sig')


def compute_batch_stats(directory: str) -> None:
    """Recalculate emotion counts for ``directory`` and write CSV."""

    stats_path = os.path.join(directory, 'emotion_count_by_time_full.csv')
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
    stats_df.to_csv(stats_path, index=False, encoding='utf-8-sig')
    # also update the global summary CSV in the script directory
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
    bv = fname.replace('_comments.csv', '')
    update_stats(df, bv)

def process_new_files(directory: str, force: bool = False) -> None:
    """Process comment CSVs in ``directory``.

    Parameters
    ----------
    directory : str
        Directory containing ``*_comments.csv`` files.
    force : bool
        If ``True``, classify comments_maixiaowen even if the file already contains an
        ``emotion`` column. Otherwise only files without this column are
        processed (the previous behaviour).
    """

    files = [f for f in os.listdir(directory) if f.endswith('_comments.csv')]
    for fname in tqdm(files, desc='检查评论文件'):
        file_path = os.path.join(directory, fname)
        header = pd.read_csv(file_path, nrows=0)
        bv = fname.replace('_comments.csv', '')
        if bv not in bvid_to_info:
            print(f"BV号{bv}未出现在bilibili_search.csv，跳过")
            continue
        desc, kw = bvid_to_info[bv]
        if force or 'emotion' not in header.columns:
            process_file(file_path, desc, kw, fname)
    compute_batch_stats(directory)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Classify comment emotions')
    parser.add_argument(
        '-d', '--directory', default=None,
        help='Directory containing comment CSV files'
    )
    parser.add_argument(
        '-f', '--force', action='store_true',
        help='Re-classify even if emotion column already exists'
    )
    args = parser.parse_args()

    directory = args.directory
    if directory is None:
        directory = select_directory()
    else:
        if not os.path.isabs(directory):
            directory = os.path.join(BASE_DIR, directory)

    force = args.force
    if not force:
        choice = input('选择模式：1=仅处理新增文件，2=重新分类所有文件 [1/2]: ').strip()
        if choice == '2':
            force = True

    process_new_files(directory=directory, force=force)
