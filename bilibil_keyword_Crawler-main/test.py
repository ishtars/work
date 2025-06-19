import jieba
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel


# 计算余弦相似度
def cosine_similarity_np(a, b):
    denom = (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)
    num = np.dot(a, b)
    return float(num) / float(denom)


# 获取文本嵌入向量（ERNIE专用）
def get_ernie_embedding(text, tokenizer, model):
    # 对文本进行编码，获取token ids和attention mask
    inputs = tokenizer(
        text,
        padding=True,
        truncation=True,
        max_length=64,  # ERNIE推荐最大长度
        return_tensors="pt"
    )

    # 前向传播
    with torch.no_grad():
        outputs = model(**inputs)

    # 使用均值池化代替CLS向量（ERNIE效果更优）
    last_hidden = outputs.last_hidden_state
    embeddings = torch.mean(last_hidden, dim=1).numpy()
    return embeddings[0]


if __name__ == '__main__':
    try:
        # 加载ERNIE 3.0模型
        print("正在加载ERNIE 3.0模型...")
        model_name = "nghuyong/ernie-3.0-base-zh"  # HuggingFace官方模型
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        print("ERNIE 3.0模型加载成功！")

        # 测试数据
        comment = '大乱炖，腊鸡腾讯游戏'
        relationships = ['融合']

        # 获取评论嵌入（ERNIE版本）
        comment_emb = get_ernie_embedding(comment, tokenizer, model)

        # 1. 整句与关系词的相似度
        print("句子级别相似度：")
        for rel in relationships:
            rel_emb = get_ernie_embedding(rel, tokenizer, model)
            sim = cosine_similarity_np(comment_emb, rel_emb)
            print(f"评论整体与关系 '{rel}' 的相似度: {sim:.4f}")

        # 2. 分词后与关系词的相似度
        print("\n词语级别相似度：")
        # 使用ERNIE兼容的分词策略（保留特殊符号处理）
        words = [w for w in jieba.cut(comment) if len(w.strip()) > 0]
        print(f"分词结果: {words}")

        for rel in relationships:
            rel_emb = get_ernie_embedding(rel, tokenizer, model)

            max_sim = 0
            max_word = ""
            all_sims = []

            print(f"\n关系：{rel}")
            for word in words:
                # 特殊处理表情符号（ERNIE需要显式识别）
                if word.startswith('[') and word.endswith(']'):
                    word_emb = get_ernie_embedding("[特殊表情]", tokenizer, model)
                else:
                    word_emb = get_ernie_embedding(word, tokenizer, model)

                sim = cosine_similarity_np(rel_emb, word_emb)
                all_sims.append(sim)
                print(f"  - 与分词 '{word}' 相似度: {sim:.4f}")

                if sim > max_sim:
                    max_sim = sim
                    max_word = word

            avg_sim = np.mean(all_sims)
            print(f"  -> 最大相似度: {max_sim:.4f} （与 '{max_word}'）")
            print(f"  -> 均值相似度: {avg_sim:.4f}")

    except Exception as e:
        print(f"发生错误: {e}")
        import traceback

        print(traceback.format_exc())