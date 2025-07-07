import os
import csv
import sys


def is_empty_csv(path: str) -> bool:
    """Return True if CSV has only header or is blank"""
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)
            # consider file empty if length <=1 or all comment fields empty
            if len(rows) <= 1:
                return True
            # check if all comment content columns are empty
            # header should contain '评论内容'
            content_idx = None
            header = rows[0]
            for i, col in enumerate(header):
                if col.strip() == '评论内容':
                    content_idx = i
                    break
            if content_idx is None:
                return False
            return all(not r[content_idx].strip() for r in rows[1:])
    except Exception as e:
        print(f'无法读取{path}: {e}')
        return False


def deduplicate_csv(path: str) -> bool:
    """Remove duplicate comments in CSV. Return True if file became empty."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception as e:
        print(f"无法读取{path}: {e}")
        return False

    if len(rows) <= 1:
        return True

    header = rows[0]
    content_idx = None
    for i, col in enumerate(header):
        if col.strip() == "评论内容":
            content_idx = i
            break
    if content_idx is None:
        return False

    seen = set()
    new_rows = [header]
    for row in rows[1:]:
        comment = row[content_idx].strip()
        if not comment:
            continue
        if comment not in seen:
            seen.add(comment)
            new_rows.append(row)

    if len(new_rows) <= 1:
        return True

    if len(new_rows) != len(rows):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(new_rows)
        print(f"已去重: {path}")

    return False


def clean_comment_dirs(dirs):
    removed = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for name in files:
                if not name.endswith('.csv'):
                    continue
                fpath = os.path.join(root, name)
                empty = deduplicate_csv(fpath)
                if empty or is_empty_csv(fpath):
                    os.remove(fpath)
                    removed += 1
                    print(f'已删除空评论文件: {fpath}')
    print(f'共删除 {removed} 个空评论文件')


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    dirs = [os.path.join(base, 'comments'),
            # os.path.join(base, 'comments_batch1'),
            # os.path.join(base, 'comments_batch2'),
            # os.path.join(base, 'comments_maixiaowen')
            ]
    if len(sys.argv) > 1:
        dirs = sys.argv[1:]
    clean_comment_dirs(dirs)


if __name__ == '__main__':
    main()
