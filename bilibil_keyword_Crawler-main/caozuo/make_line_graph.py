import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates
from scipy.interpolate import make_interp_spline

# 1. 读取原始数据
df = pd.read_csv('emotion_count_by_time_full.csv')

# 2. 时间转datetime
df['time'] = pd.to_datetime(df['time'])

# 3. 定义情感类别
# "Neutral" 情感在展示时不需要体现，因此在绘图计算时将其排除
emotion_categories = [
    'Sadness', 'Anger', 'Regret', 'Disgust', 'Joy',
    'Expectation', 'Surprise', 'Love'
]

# 4. 增加week列，采用周一为一周起点（可按需求改）
df['week'] = df['time'].dt.to_period('W').apply(lambda r: r.start_time)
# 或者只用：df['week'] = df['time'].dt.to_period('W').astype(str)，此时 week 形如 "2024-07-08/2024-07-14"
# 但用时间戳绘图更好看

# 5. 按week合并总数
df_week_sum = df.groupby('week')[emotion_categories].sum().reset_index()
df_week_sum = df_week_sum.sort_values('week')

# 6. 使用兩周滑動窗口計算數量
window_weeks = 2
rolling_df = df_week_sum.set_index('week')[emotion_categories].rolling(window=window_weeks, min_periods=1).sum()
df_week_sum[emotion_categories] = rolling_df.values

# 7. 計算比例（每情感/兩周總評論）
df_week_sum['total'] = df_week_sum[emotion_categories].sum(axis=1)
for emo in emotion_categories:
    df_week_sum[emo + '_ratio'] = df_week_sum[emo] / df_week_sum['total'].replace(0, 1)  # 防止除以0

# ========== a) 数量折线图（两周滑动窗口） ==========
plt.figure(figsize=(13,7))
dates = mdates.date2num(pd.to_datetime(df_week_sum['week']))
smooth_dates = np.linspace(dates.min(), dates.max(), len(dates) * 10)
for emo in emotion_categories:
    spline = make_interp_spline(dates, df_week_sum[emo], k=3)
    smooth_values = spline(smooth_dates)
    smooth_values = np.clip(smooth_values, 0, None)
    plt.plot(mdates.num2date(smooth_dates), smooth_values, label=emo)
plt.xlabel('Week')
plt.ylabel('Comment Count')
plt.title('Rolling 2-Week Comment Emotion Count (All BVs)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.xticks(rotation=45)
plt.show()

# ========== b) 比例折线图（两周滑动窗口） ==========
plt.figure(figsize=(13,7))
for emo in emotion_categories:
    spline = make_interp_spline(dates, df_week_sum[emo + '_ratio'], k=3)
    smooth_values = spline(smooth_dates)
    smooth_values = np.clip(smooth_values, 0, 1)
    plt.plot(mdates.num2date(smooth_dates), smooth_values, label=emo)
plt.xlabel('Week')
plt.ylabel('Ratio')
plt.title('Rolling 2-Week Comment Emotion Ratio (All BVs)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.xticks(rotation=45)
plt.show()