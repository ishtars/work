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
            allowed = ["Sadness", "Anger", "Regret", "Disgust", "Joy",
                       "Expectation", "Surprise", "Love", "Neutral"]
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

# 加载全视频信息
search_df = pd.read_csv('../bilibili_search.csv')
bvid_to_info = {row['bvid']: (str(row['description']), str(row['keywords'])) for idx, row in search_df.iterrows()}

# 列出所有评论csv
test_files = [f for f in os.listdir('../comments_batch1') if f.endswith('_comments.csv')]

for fname in tqdm(test_files, desc='处理视频评论文件'):
    bv = fname.replace('_comments.csv', '')
    if bv not in bvid_to_info:
        print(f"BV号{bv}未出现在bilibili_search.csv，跳过")
        continue
    desc, kw = bvid_to_info[bv]
    file_path = os.path.join('../comments_batch1', fname)
    df = pd.read_csv(file_path)
    if '评论内容' not in df.columns:
        print(f"{file_path} 缺少评论内容字段，跳过")
        continue

    # 情感分析，并实时写入新列
    emotion_list = []
    for idx, row in tqdm(df.iterrows(), total=len(df), desc=f"{fname}情感标注", leave=False):
        comment = str(row['评论内容'])
        emotion = get_sentiment_from_llm(desc, kw, comment)
        emotion_list.append(emotion)
        print(f"【{fname} 第{idx+1}条】评论: {comment[:40]}... | 分类: {emotion}")

    df['emotion'] = emotion_list
    # 直接覆盖写回原csv文件
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"{fname} 已直接更新情感分类到原csv")