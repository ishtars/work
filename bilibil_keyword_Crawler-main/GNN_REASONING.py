import re
import torch
import numpy as np
import pandas as pd
from neo4j import GraphDatabase
from torch_geometric.data import Data
from torch_geometric.nn import GATConv
import torch.nn.functional as F
import os
import jieba
from transformers import AutoTokenizer, AutoModel
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm

# Neo4j连接配置
NEO4J_CONFIG = {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "8168377qwe"
}

# 9种情感
EMOTIONS = ["Sadness", "Anger", "Regret", "Disgust", "Joy", "Expectation", "Surprise", "Love", "Neutral"]

EMOTION_RELATION_KEYWORDS = {
    "Sadness": ["失望", "悲伤", "遗憾", "哀叹", "伤心"],
    "Anger": ["愤怒", "指责", "谴责", "批评", "抗议"],
    "Regret": ["后悔", "遗憾", "自责", "惋惜", "忏悔"],
    "Disgust": ["融合", "逼氪","经常出现","戏称为","存在安全漏洞","存在设计缺陷","被骂","阻挡"],
    "Joy": ["加入","戏称为"],
    "Expectation": ["推出"],
    "Surprise": ["惊讶", "震惊", "意外", "吃惊", "不可思议"],
    "Love": ["融合","特色"],
    "Neutral": ["旗下", "推出", "属于", "提供", "有"]
}

class KnowledgeGraphExtractor:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    def close(self):
        self.driver.close()
    def extract_triples(self):
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a)-[r]->(b)
                RETURN a.name AS source, type(r) AS relation, b.name AS target
            """)
            triples = [(record["source"], record["relation"], record["target"])
                       for record in result]
            return triples
    def extract_entities_and_relations(self):
        with self.driver.session() as session:
            entities_result = session.run("MATCH (n) RETURN DISTINCT n.name AS entity")
            entities = [record["entity"] for record in entities_result]
            relations_result = session.run("MATCH ()-[r]->() RETURN DISTINCT type(r) AS relation")
            relations = [record["relation"] for record in relations_result]
            return entities, relations
    def find_3_hop_paths(self, start_entity):
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = (start {name: $start_entity})-[*1..3]->(end)
                RETURN path LIMIT 100
            """, start_entity=start_entity)
            paths = []
            for record in result:
                path = record["path"]
                nodes = [node["name"] for node in path.nodes]
                relationships = [rel.type for rel in path.relationships]
                paths.append((nodes, relationships))
            return paths
    def extract_entities_from_comment(self, comment, entities):
        found_entities = []
        sorted_entities = sorted(entities, key=len, reverse=True)
        for entity in sorted_entities:
            if entity in comment:
                found_entities.append(entity)
        return found_entities

class TextProcessor:
    def __init__(self, model_name="moka-ai/m3e-base"):
        print(f"加载文本编码模型: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
    def encode_text(self, text):
        if isinstance(text, str):
            texts = [text]
        else:
            texts = text
        inputs = self.tokenizer(texts, padding=True, truncation=True, max_length=64, return_tensors="pt")
        with torch.no_grad():
            outputs = self.model(**inputs)
        last_hidden = outputs.last_hidden_state
        attention_mask = inputs['attention_mask']
        mask = attention_mask.unsqueeze(-1).float()
        masked_hidden = last_hidden * mask
        summed = masked_hidden.sum(1)
        counts = mask.sum(1)
        counts = torch.clamp(counts, min=1)
        mean_pooled = summed / counts
        arr = mean_pooled.cpu().numpy()
        if len(arr) == 1:
            return arr[0]
        return arr
    def path_to_text(self, nodes, relationships):
        text = f"{nodes[0]}"
        for i in range(len(relationships)):
            text += f" {relationships[i]} {nodes[i+1]}"
        return text

def get_comment_keywords(comment):
    tokens = list(jieba.cut(comment))
    filtered = [t for t in tokens if re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]+$', t)]
    return filtered


def match_emotion_for_relation(rel_name, text_processor):
    # 1. 首先严格检查关键词命中
    for emo in EMOTIONS:
        if rel_name in EMOTION_RELATION_KEYWORDS[emo]:
            return (emo, 1.0)  # 命中关键词，即为该情感最高分
    # 2. 否则返回Neutral或标记为未命中
    return ("Neutral", 0.0)


def get_gnn_path_relation_sem_score(comment, relationships, text_processor, model, relation_to_idx, method='max'):
    comment_keywords = get_comment_keywords(comment)
    if not comment_keywords:
        return 0, None, None
    kw_embs = text_processor.encode_text(comment_keywords)
    if kw_embs.ndim == 1:
        kw_embs = kw_embs[np.newaxis, :]
    kw_embs_norm = kw_embs / np.linalg.norm(kw_embs, axis=1, keepdims=True)
    max_score = -1
    max_rel, max_kw = None, None
    hop_detail = []
    for rel in relationships:
        rel_idx = relation_to_idx[rel]
        rel_emb = model.relation_embedding.weight[rel_idx].detach().cpu().numpy()
        rel_emb = rel_emb / np.linalg.norm(rel_emb)
        sim_scores = np.dot(kw_embs_norm, rel_emb)
        max_idx = np.argmax(sim_scores)
        this_max = sim_scores[max_idx]
        hop_detail.append((rel, comment_keywords[max_idx], this_max))
        if this_max > max_score:
            max_score = this_max
            max_rel = rel
            max_kw = comment_keywords[max_idx]
    if method == 'max':
        return max_score, max_rel, max_kw
    else:
        mean_score = np.mean([item[2] for item in hop_detail])
        return mean_score, max_rel, max_kw

class EmotionAwareGNNModel(torch.nn.Module):
    def __init__(self, hidden_channels, num_entities, num_relations, text_processor):
        super().__init__()
        self.text_processor = text_processor
        self.hidden_channels = hidden_channels
        self.entity_embedding = torch.nn.Embedding(num_entities, hidden_channels)
        self.relation_embedding = torch.nn.Embedding(num_relations, hidden_channels)
        self.emotion_embedding = torch.nn.Embedding(len(EMOTIONS), hidden_channels)
        self.conv1 = GATConv(hidden_channels, hidden_channels, heads=4, dropout=0.2)
        self.conv2 = GATConv(hidden_channels * 4, hidden_channels, heads=1, dropout=0.2)
        self.conv3 = GATConv(hidden_channels, hidden_channels, heads=1, dropout=0.2)
    def forward(self, x, edge_index, edge_type, emotion_idx=None):
        x = self.entity_embedding(x)
        if emotion_idx is not None:
            emotion_emb = self.emotion_embedding(torch.tensor(emotion_idx).to(x.device))
            attention_weights = torch.matmul(x, emotion_emb.unsqueeze(0).t())
            attention_weights = F.softmax(attention_weights, dim=0)
            x = x * attention_weights
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.conv2(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.conv3(x, edge_index)
        return x
    def get_relation_score(self, source_emb, relation_type, target_emb, emotion_idx=None):
        relation_emb = self.relation_embedding(relation_type)
        score = torch.sum(source_emb * relation_emb * target_emb, dim=1)
        return score

def emotion_driven_reasoning(comment, emotion, model, data, extractor, entities, relations, entity_to_idx,
                             relation_to_idx, text_processor, fusion_weights={'emotion':0.5, 'sem':0.5}):
    if emotion not in EMOTIONS:
        print(f"警告: 情感'{emotion}'不在支持的情感列表中。将使用中性情感。")
        emotion = "Neutral"
    emotion_idx = EMOTIONS.index(emotion)
    print(f"评论: '{comment}'\n使用指定情感: {emotion}")
    found_entities = extractor.extract_entities_from_comment(comment, entities)
    if not found_entities:
        print("评论中未找到知识图谱中的实体")
        return []
    print(f"在评论中找到以下实体: {', '.join(found_entities)}")
    model.eval()
    with torch.no_grad():
        node_emb = model(data.x, data.edge_index, data.edge_type, emotion_idx)
    all_paths_with_scores = []
    for start_entity in found_entities:
        paths = extractor.find_3_hop_paths(start_entity)
        if not paths:
            print(f"没有找到从 '{start_entity}' 出发的3跳路径")
            continue
        for path_idx, (nodes, rels) in enumerate(paths):
            # 情感匹配规则法，每hop
            emotion_score = 0
            emotion_match_detail = []
            rel_emotions = []
            hop_scores = []
            for i in range(len(rels)):
                match_emotion, matched_value = match_emotion_for_relation(rels[i], text_processor)
                if match_emotion == emotion:
                    emotion_score += 1
                    hop_scores.append(0.8)
                    emotion_match_detail.append(True)
                else:
                    hop_scores.append(0.1)
                    emotion_match_detail.append(False)
                rel_emotions.append(match_emotion)
            emotion_score = emotion_score / len(rels)
            emotion_w_score = np.mean(hop_scores)
            # 使用GNN空间的语义分
            sem_score, sem_rel, sem_kw = get_gnn_path_relation_sem_score(
                comment, rels, text_processor, model, relation_to_idx, method='max')
            final_score = fusion_weights['emotion'] * emotion_w_score + fusion_weights['sem'] * sem_score * 10
            path_text = text_processor.path_to_text(nodes, rels)
            all_paths_with_scores.append({
                'start_entity': start_entity,
                'path_idx': path_idx,
                'nodes': nodes,
                'relations': rels,
                'path_text': path_text,
                'emotion_w_score': emotion_w_score,
                'emotion_score': emotion_score,
                'sem_score': sem_score,
                'sem_score_rel': sem_rel,
                'sem_score_kw': sem_kw,
                'final_score': final_score,
                'emotion_match_detail': emotion_match_detail,
                'rel_emotions': rel_emotions
            })
    all_paths_with_scores.sort(key=lambda x: x['final_score'], reverse=True)
    return all_paths_with_scores

def main():
    extractor = KnowledgeGraphExtractor(
        NEO4J_CONFIG["uri"], NEO4J_CONFIG["user"], NEO4J_CONFIG["password"])
    print("从Neo4j提取知识图谱数据...")
    triples = extractor.extract_triples()
    entities, relations = extractor.extract_entities_and_relations()
    print(f"提取了 {len(triples)} 个三元组, {len(entities)} 个实体, {len(relations)} 个关系类型")
    entity_to_idx = {entity: idx for idx, entity in enumerate(entities)}
    relation_to_idx = {relation: idx for idx, relation in enumerate(relations)}
    source_nodes = [entity_to_idx[triple[0]] for triple in triples]
    target_nodes = [entity_to_idx[triple[2]] for triple in triples]
    edge_index = torch.tensor([source_nodes, target_nodes], dtype=torch.long)
    edge_types = [relation_to_idx[triple[1]] for triple in triples]
    edge_type = torch.tensor(edge_types, dtype=torch.long)
    x = torch.arange(len(entities), dtype=torch.long)
    data = Data(x=x, edge_index=edge_index, edge_type=edge_type)
    text_processor = TextProcessor(model_name="moka-ai/m3e-base")
    model = EmotionAwareGNNModel(768, len(entities), len(relations), text_processor)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    # ★ Step 1: 预先取得所有关系的语义embedding，用于semantic alignment loss
    # 放在GNN训练外面即可（关系类型通常很少）
    relation_text_embs = text_processor.encode_text(relations)   # shape: (num_rel, 768)
    relation_text_embs = torch.tensor(relation_text_embs, dtype=torch.float32)
    if torch.cuda.is_available():
        device = torch.device('cuda')
        model = model.to(device)
        relation_text_embs = relation_text_embs.to(device)
        data = data.to(device)
    else:
        device = torch.device('cpu')

    alpha = 5.0  # ★ 语义loss权重，可调

    print("GNN模型训练中...")
    model.train()
    for epoch in range(50):
        optimizer.zero_grad()
        node_emb = model(data.x, data.edge_index, data.edge_type)
        source_emb = node_emb[data.edge_index[0]]
        target_emb = node_emb[data.edge_index[1]]
        relation_type = data.edge_type
        pos_score = model.get_relation_score(source_emb, relation_type, target_emb)
        neg_target_idx = torch.randint(0, len(entities), (len(source_nodes),), dtype=torch.long).to(device)
        neg_target_emb = node_emb[neg_target_idx]
        neg_score = model.get_relation_score(source_emb, relation_type, neg_target_emb)
        loss_link = -torch.mean(F.logsigmoid(pos_score - neg_score))

        # ★ Step 2: 计算关系语义alignment loss
        # GNN中的relation embedding 与 语义空间relation embedding 对齐
        rel_emb = model.relation_embedding.weight                # (num_rel, 768)
        rel_emb_norm = F.normalize(rel_emb, dim=1)
        rel_text_embs_norm = F.normalize(relation_text_embs, dim=1)
        cos_sim = (rel_emb_norm * rel_text_embs_norm).sum(dim=1)  # (num_rel,)
        loss_sem = (1 - cos_sim).mean()

        # ★ Step 3: 总损失=结构任务loss+语义辅助loss
        loss = loss_link + alpha * loss_sem

        loss.backward()
        optimizer.step()

        if (epoch+1) % 10 == 0:
            print(f"Epoch: {epoch+1:03d}, Loss: {loss:.4f}, LinkLoss: {loss_link:.4f}, SemLoss: {loss_sem:.4f}")

    print("GNN模型训练完成")
    while True:
        comment = input("\n请输入评论内容 (输入'q'退出): ")
        if comment.lower() == 'q':
            break
        print("\n请选择评论的情感类型:")
        for i, emotion in enumerate(EMOTIONS):
            print(f"{i + 1}. {emotion}")
        emotion_choice = input("请输入情感编号 (1-9): ")
        try:
            emotion_idx = int(emotion_choice) - 1
            emotion = EMOTIONS[emotion_idx] if 0 <= emotion_idx < len(EMOTIONS) else "Neutral"
        except ValueError:
            emotion = "Neutral"
        reasoning_results = emotion_driven_reasoning(
            comment, emotion, model, data, extractor, entities, relations,
            entity_to_idx, relation_to_idx, text_processor)
        if not reasoning_results:
            print("未找到相关推理路径")
            continue
        print(f"\n基于评论 '{comment}' 的路径推理TOP10结果 (情感: {emotion}):")
        for i, result in enumerate(reasoning_results[:10]):
            emo_detail = " > ".join([
                f"{rel}{'(✓)' if match else ''}[{e}]"
                for rel, match, e in zip(result['relations'], result['emotion_match_detail'], result['rel_emotions'])
            ])
            print(f"\n路径 {i+1}, 综合得分: {result['final_score']:.4f}")
            print(f"链路: {result['path_text']}")
            print(f"细节: 情感{result['emotion_w_score']:.2f} 语义{result['sem_score']:.2f}")
            print(f"语义最高匹配: \"{result['sem_score_kw']}\" <--> \"{result['sem_score_rel']}\" ，分数: {result['sem_score']:.4f}")
            print(f"情感贴合链: {emo_detail}")
    extractor.close()

def process_comments_from_csv(csv_path, emotion="Disgust", output_path=None):
    print(f"读取CSV文件: {csv_path}")
    df = pd.read_csv(csv_path)
    comment_column = None
    possible_comment_names = ['评论内容', '评论', 'comment', 'content', 'text']
    for name in possible_comment_names:
        if name in df.columns:
            comment_column = name
            break
    if not comment_column:
        raise ValueError(f"无法在CSV文件中找到评论内容列。可用列: {df.columns.tolist()}")
    print(f"找到评论列: {comment_column}")
    print(f"所有评论都将使用情感: {emotion}")

    extractor = KnowledgeGraphExtractor(
        NEO4J_CONFIG["uri"], NEO4J_CONFIG["user"], NEO4J_CONFIG["password"])
    triples = extractor.extract_triples()
    entities, relations = extractor.extract_entities_and_relations()
    entity_to_idx = {entity: idx for idx, entity in enumerate(entities)}
    relation_to_idx = {relation: idx for idx, relation in enumerate(relations)}
    source_nodes = [entity_to_idx[triple[0]] for triple in triples]
    target_nodes = [entity_to_idx[triple[2]] for triple in triples]
    edge_index = torch.tensor([source_nodes, target_nodes], dtype=torch.long)
    edge_types = [relation_to_idx[triple[1]] for triple in triples]
    edge_type = torch.tensor(edge_types, dtype=torch.long)
    x = torch.arange(len(entities), dtype=torch.long)
    data = Data(x=x, edge_index=edge_index, edge_type=edge_type)
    text_processor = TextProcessor()
    model = EmotionAwareGNNModel(
        64, len(entities), len(relations), text_processor)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    print("训练情感感知的GNN模型...")
    model.train()
    for epoch in range(30):
        optimizer.zero_grad()
        node_emb = model(data.x, data.edge_index, data.edge_type)
        source_emb = node_emb[data.edge_index[0]]
        target_emb = node_emb[data.edge_index[1]]
        relation_type = data.edge_type
        pos_score = model.get_relation_score(source_emb, relation_type, target_emb)
        neg_target_idx = torch.randint(0, len(entities), (len(source_nodes),), dtype=torch.long)
        neg_target_emb = node_emb[neg_target_idx]
        neg_score = model.get_relation_score(source_emb, relation_type, neg_target_emb)
        loss = -torch.mean(F.logsigmoid(pos_score - neg_score))
        loss.backward()
        optimizer.step()
    results = []
    print("处理评论...")
    for idx, row in tqdm(df.iterrows(), total=len(df)):
        comment = row[comment_column]
        if pd.isna(comment) or not comment:
            continue
        reasoning_results = emotion_driven_reasoning(
            comment, emotion, model, data, extractor, entities, relations,
            entity_to_idx, relation_to_idx, text_processor)
        if not reasoning_results:
            continue
        for rank, result in enumerate(reasoning_results[:3]):
            results.append({
                'comment_id': idx,
                'comment': comment,
                'emotion': emotion,
                'start_entity': result['start_entity'],
                'path': result['path_text'],
                'final_score': result['final_score'],
                'emotion_w_score': result['emotion_w_score'],
                'sem_score': result['sem_score'],
                'emotion_chain': " > ".join([
                    f"{rel}{'(✓)' if match else ''}[{e}]"
                    for rel, match, e in zip(result['relations'], result['emotion_match_detail'], result['rel_emotions'])
                ]),
                'rank': rank + 1
            })
    results_df = pd.DataFrame(results)
    if output_path is None:
        output_path = os.path.splitext(csv_path)[0] + '_emotion_guided_reasoning.csv'
    results_df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"结果已保存到: {output_path}")
    extractor.close()
    return results_df

if __name__ == "__main__":
    print("请选择模式:")
    print("1. 交互式模式 - 输入单条评论进行推理")
    print("2. 批处理模式 - 处理CSV文件中的所有评论")
    choice = input("请输入选择 (1/2): ")
    if choice == "1":
        main()
    elif choice == "2":
        csv_path = input("请输入CSV文件路径: ")
        process_comments_from_csv(csv_path)
    else:
        print("无效选择")