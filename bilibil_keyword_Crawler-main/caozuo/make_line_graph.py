import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates
from scipy.interpolate import make_interp_spline

# 1. 读取原始数据
df = pd.read_csv('emotion_count_by_time_full.csv')

# 2. 时间转 datetime，并设为索引
df['time'] = pd.to_datetime(df['time'])
emotion_categories = [
    'Sadness', 'Anger', 'Regret', 'Disgust', 'Joy',
    'Expectation', 'Surprise', 'Love'
]

# 3. 按天重采样统计各情感数目
daily = df.set_index('time')[emotion_categories].resample('D').sum()

# 4. 7 天滑动窗口累加（窗口大小可改）
window_days = 7
rolling = daily.rolling(window=window_days, min_periods=1).sum()

# 5. 计算比例
rolling['total'] = rolling.sum(axis=1)
for emo in emotion_categories:
    rolling[f'{emo}_ratio'] = rolling[emo] / rolling['total'].replace(0, 1)

# 6. 绘制 7 天滑动窗口下的数量折线
plt.figure(figsize=(13,7))
dates = mdates.date2num(rolling.index.to_pydatetime())
smooth_dates = np.linspace(dates.min(), dates.max(), len(dates)*10)
for emo in emotion_categories:
    # 如果想继续平滑曲线，可使用 spline；也可直接 plt.plot(rolling.index, rolling[emo], ...)
    spline = make_interp_spline(dates, rolling[emo], k=3)
    smooth_vals = spline(smooth_dates)
    plt.plot(mdates.num2date(smooth_dates), smooth_vals, label=emo)
plt.xlabel('Date')
plt.ylabel(f'{window_days}-Day Rolling Count')
plt.title(f'{window_days}-Day Rolling Emotion Count (Daily Step)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.5)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# 7. 绘制 7 天滑动窗口下的比例折线
plt.figure(figsize=(13,7))
for emo in emotion_categories:
    spline = make_interp_spline(dates, rolling[f'{emo}_ratio'], k=3)
    smooth_vals = spline(smooth_dates)
    plt.plot(mdates.num2date(smooth_dates), np.clip(smooth_vals, 0, 1), label=emo)
plt.xlabel('Date')
plt.ylabel(f'{window_days}-Day Rolling Ratio')
plt.title(f'{window_days}-Day Rolling Emotion Ratio (Daily Step)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.5)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
