import os
import pandas as pd

target_col = '上级评论ID'

for fname in os.listdir('.'):
    if fname.endswith('.csv'):
        try:
            df = pd.read_csv(fname)
            if target_col not in df.columns:
                print(f'文件 {fname} 不包含列 "{target_col}"，跳过。')
                continue
            # 保留“上级评论ID”为0的
            filtered_df = df[df[target_col] == 0]
            filtered_df.to_csv(fname, index=False, encoding='utf-8-sig')
            print(f'文件 {fname} 已更新，保留{len(filtered_df)}条顶层评论。')
        except Exception as e:
            print(f"处理文件 {fname} 时出错: {e}")