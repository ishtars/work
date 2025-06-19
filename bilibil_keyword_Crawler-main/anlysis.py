import os
import pandas as pd

folder_path = 'comments_batch1'
result = []

# 时间区间
start_date = pd.to_datetime('2025-02-10')
end_date = pd.to_datetime('2025-02-18')

# 1. 读取bilibili_search.csv，建立bv号到keywords/description的字典
search_df = pd.read_csv('bilibili_search.csv', encoding='utf-8')
# 假设BV号字段为'bv号'或'bvid'，请按实际字段替换
bv_col = 'bv号' if 'bv号' in search_df.columns else 'bvid'
bv_meta = search_df.set_index(bv_col)[['keywords', 'description']].to_dict(orient='index')

for filename in os.listdir(folder_path):
    if filename.endswith('.csv'):
        bv_id = filename.split('_')[0]
        file_path = os.path.join(folder_path, filename)
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            df['评论时间'] = pd.to_datetime(df['评论时间'], errors='coerce')

            filtered = df[
                (df['emotion'] == 'Regret') &
                (df['评论时间'] >= start_date) &
                (df['评论时间'] <= end_date)
            ]

            for idx, row in filtered.iterrows():
                # 取keywords和description，找不到则置空
                meta = bv_meta.get(bv_id, {})
                keywords = meta.get('keywords', '')
                description = meta.get('description', '')
                result.append({
                    'bv号': bv_id,
                    '评论内容': row['评论内容'],
                    'keywords': keywords,
                    'description': description
                })
        except Exception as e:
            print(f"{filename} 处理失败: {e}")

result_df = pd.DataFrame(result)
result_df.to_csv('Regret_comment_with_meta_20250210_20250218.csv', index=False, encoding='utf-8-sig')
print('目标csv已保存：Disgust_comment_with_meta_20241123_20241130.csv')