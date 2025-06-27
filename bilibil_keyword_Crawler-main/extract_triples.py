import os
import re
import sys
from time import sleep

try:
    import openai
except ImportError:  # pragma: no cover - runtime check
    sys.exit("请先安装 openai 模块: pip install openai")

API_KEY = os.getenv('OPENAI_API_KEY')
BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.kksj.org/v1')

if not API_KEY:
    sys.exit('请在环境变量 OPENAI_API_KEY 中设置 API 密钥')

client = openai.OpenAI(api_key=API_KEY, base_url=BASE_URL)

PROMPT_TEMPLATE = (
    "请从以下文本中尽可能多地抽取三元组(主体, 关系, 客体)，"
    "要求覆盖文章中的信息，构建完整、充分且合理的长条逻辑链。"
    "按行输出所有三元组，格式为 主体|关系|客体。\n文本:\n{content}\n三元组:\n"
)


def slugify(name: str) -> str:
    """Sanitize filename for cross-platform safety."""
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    return name.strip()


def extract_triples(text: str, retries: int = 3, delay: float = 2.0) -> list[str]:
    """Call the model API to extract triples with basic retry logic."""

    prompt = PROMPT_TEMPLATE.format(content=text)
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            content = response.choices[0].message.content
            break
        except Exception as e:
            print(f"API 调用失败(第{attempt}次): {e}")
            if attempt == retries:
                return []
            sleep(delay)


    triples = []
    for line in content.splitlines():
        line = line.strip().strip('、').strip('。').strip()
        if not line:
            continue
        # 使用常见分隔符拆分
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
        elif ',' in line:
            parts = [p.strip() for p in line.split(',')]
        elif '，' in line:
            parts = [p.strip() for p in line.split('，')]
        else:
            continue
        if len(parts) >= 3:
            triples.append('|'.join(parts[:3]))
    return triples


def process_guides(guides_dir: str):
    if not os.path.isdir(guides_dir):
        print(f"目录不存在: {guides_dir}")
        return

    txt_files = [
        f for f in os.listdir(guides_dir)
        if f.lower().endswith('.txt')
    ]
    if not txt_files:
        print("未找到任何 txt 文件")
        return

    output_dir = os.path.join(guides_dir, 'triples')
    os.makedirs(output_dir, exist_ok=True)

    txt_files = [f for f in os.listdir(guides_dir) if f.lower().endswith('.txt')]
    print("发现的txt文件：", txt_files)

    for fname in txt_files:
        src_path = os.path.join(guides_dir, fname)
        try:
            with open(src_path, 'r', encoding='utf-8') as f:
                text = f.read().strip()
        except Exception as e:
            print(f"读取失败: {fname} -> {e}")
            continue

        if not text:
            continue

        triples = extract_triples(text)
        base = slugify(os.path.splitext(fname)[0])
        out_path = os.path.join(output_dir, f"{base}_triples.txt")
        try:
            with open(out_path, 'w', encoding='utf-8') as out:
                out.write('\n'.join(triples))
            print(f"{fname}: 提取 {len(triples)} 条三元组")
        except Exception as e:
            print(f"写入失败: {out_path} -> {e}")


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    guides_dir = os.path.join(base, 'guides')
    if len(sys.argv) > 1:
        guides_dir = sys.argv[1]
    process_guides(guides_dir)
