import pandas as pd
import matplotlib.pyplot as plt

# 1. 读取原始数据
df = pd.read_csv('emotion_count_by_time_full.csv')

# 2. 时间转datetime
df['time'] = pd.to_datetime(df['time'])

# 3. 定义情感类别
emotion_categories = ['Sadness', 'Anger', 'Regret', 'Disgust', 'Joy',
                      'Expectation', 'Surprise', 'Love', 'Neutral']

# 4. 增加week列，采用周一为一周起点（可按需求改）
df['week'] = df['time'].dt.to_period('W').apply(lambda r: r.start_time)
# 或者只用：df['week'] = df['time'].dt.to_period('W').astype(str)，此时 week 形如 "2024-07-08/2024-07-14"
# 但用时间戳绘图更好看

# 5. 按week合并总数
df_week_sum = df.groupby('week')[emotion_categories].sum().reset_index()
df_week_sum = df_week_sum.sort_values('week')

# 6. 计算比例（每情感/每周总评论）
df_week_sum['total'] = df_week_sum[emotion_categories].sum(axis=1)
for emo in emotion_categories:
    df_week_sum[emo+'_ratio'] = df_week_sum[emo] / df_week_sum['total'].replace(0, 1)  # 防止除以0

# ========== a) 数量折线图（一周为单位） ==========
plt.figure(figsize=(13,7))
for emo in emotion_categories:
    plt.plot(df_week_sum['week'], df_week_sum[emo], marker='o', label=emo)
plt.xlabel('Week')
plt.ylabel('Comment Count')
plt.title('Weekly Comment Emotion Count (All BVs)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.xticks(rotation=45)
plt.show()

# ========== b) 比例折线图（一周为单位） ==========
plt.figure(figsize=(13,7))
for emo in emotion_categories:
    plt.plot(df_week_sum['week'], df_week_sum[emo+'_ratio'], marker='o', label=emo)
plt.xlabel('Week')
plt.ylabel('Ratio')
plt.title('Weekly Comment Emotion Ratio (All BVs)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.xticks(rotation=45)
plt.show()