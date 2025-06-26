import os
import pandas as pd
from tqdm import tqdm
import openai

API_KEY = 'sk-c6YAeki46tu91kRHbCiZRwTEWuRtsUUbaHL21fX87HHt1fb1'
BASE_URL = 'https://api.kksj.org/v1'
openai.api_key = API_KEY
openai.api_base = BASE_URL

import openai

API_KEY = 'sk-c6YAeki46tu91kRHbCiZRwTEWuRtsUUbaHL21fX87HHt1fb1'
BASE_URL = 'https://api.kksj.org/v1'

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)

def extract_entities_text(text):
    prompt = f"请从下面这句游戏评论中抽取所有可能的‘实体’（如人物、游戏名、角色、道具等），仅用逗号分隔返回所有实体：\n评论：{text}\n实体："
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{
                "role": "user",
                "content": prompt
            }],
            temperature=0.0,
            max_tokens=128,
        )
        # 健壮性处理
        choices = response.choices
        if not choices or not hasattr(choices[0], "message") or not choices[0].message or not getattr(choices[0].message, "content", None):
            print("警告：API返回内容为空或字段缺失")
            return []
        answer = choices[0].message.content
        entities = [e.strip() for e in answer.strip().split(',') if e.strip()]
        return entities
    except Exception as e:
        print(f"API异常: {e}")
        return []
def find_all_csv_files(folder):
    csv_files = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith('.csv'):
                csv_files.append(os.path.join(root, file))
    return csv_files

def main():
    input_folder = '../comments_maixiaowen'
    comment_col_name = '评论内容'
    output_file = 'output_entities.csv'

    csv_files = find_all_csv_files(input_folder)[0:300]
    all_entities = set()
    for csv_file in csv_files:
        print(f'处理 {csv_file}')
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            print(f"读取 {csv_file} 时出错：{e}")
            continue

        if comment_col_name not in df.columns:
            print(f"{csv_file} 文件没有 '{comment_col_name}' 字段")
            continue

        for content in tqdm(df[comment_col_name].dropna(), desc=f'抽取 {os.path.basename(csv_file)}'):
            entities = extract_entities_text(content)
            all_entities.update(entities)

    # 输出到CSV
    pd.DataFrame({'entity': list(all_entities)}).to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"共抽取去重实体 {len(all_entities)} 个，已保存至 {output_file}")

if __name__ == "__main__":
    main()