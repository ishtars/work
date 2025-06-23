import os
import shutil
import random

BATCH1_DIR = "comments_batch1"
BATCH2_DIR = "comments_batch2"
COMMENTS_DIR = "comments"


def main():
    os.makedirs(BATCH2_DIR, exist_ok=True)

    copied = []

    # copy all *_comments.csv from comments_batch1
    for fname in os.listdir(BATCH1_DIR):
        if fname.endswith("_comments.csv"):
            src = os.path.join(BATCH1_DIR, fname)
            dst = os.path.join(BATCH2_DIR, fname)
            shutil.copy2(src, dst)
            copied.append(fname)

    # gather csv files from comments directory
    all_comments = [f for f in os.listdir(COMMENTS_DIR)
                    if f.endswith("_comments.csv") and os.path.isfile(os.path.join(COMMENTS_DIR, f))]
    sample_count = min(50, len(all_comments))
    sampled = random.sample(all_comments, sample_count)

    for fname in sampled:
        src = os.path.join(COMMENTS_DIR, fname)
        dst = os.path.join(BATCH2_DIR, fname)
        shutil.copy2(src, dst)
        copied.append(fname)

    print("Copied files:")
    for name in copied:
        print(name)


if __name__ == "__main__":
    main()
