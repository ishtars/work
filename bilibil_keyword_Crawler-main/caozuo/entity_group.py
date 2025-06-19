import pandas as pd
from difflib import SequenceMatcher
import itertools

def similar(a, b, threshold=0.75):
    return SequenceMatcher(None, a, b).ratio() >= threshold

# 1. エンティティのCSV読み込み
df = pd.read_csv('output_entities.csv')
entities = list(df['entity'].unique())  # 既に重複除去（完全一致）される

# 2. 高類似度グループ化
groups = []
used = set()

for e1 in entities:
    if e1 in used:
        continue
    group = {e1}
    for e2 in entities:
        if e1 != e2 and e2 not in used and similar(e1, e2):
            group.add(e2)
    groups.append(group)
    used.update(group)

# 3. グループを保存
# 結果：各行が1つのグループ（カンマ区切り）
with open('entity_similar_groups.csv', 'w', encoding='utf-8') as f:
    f.write('group\n')
    for group in groups:
        f.write(','.join(group) + '\n')