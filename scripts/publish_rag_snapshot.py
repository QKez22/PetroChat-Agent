"""管理员 CLI：显式策略清单 + 语料快照 -> 不覆盖旧数据的新索引。"""

import argparse
import json
from pathlib import Path

from petrochat.app.rag.catalog import VersionPolicy, build_snapshot
from petrochat.app.rag.corpus import load_corpus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--policies", type=Path, required=True)
    args = parser.parse_args()
    policies = [
        VersionPolicy.model_validate(v)
        for v in json.loads(args.policies.read_text(encoding="utf-8"))
    ]
    print(json.dumps(build_snapshot(load_corpus(args.corpus), policies)))


if __name__ == "__main__":
    main()
