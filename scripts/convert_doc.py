"""把 .doc 文件批量转成 .docx。

用法（在项目根目录）：
    uv run python scripts/convert_doc.py data/raw/

依赖：需要安装 LibreOffice（soffice 命令）。
  Windows: https://www.libreoffice.org/download/
  Mac:     brew install --cask libreoffice
  Linux:   apt install libreoffice

如果不想装 LibreOffice，也可以用 Word 手动打开 .doc 文件并"另存为 .docx"。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def find_soffice() -> str | None:
    """查找 soffice 可执行文件。Windows 上 soffice.exe 通常不在 PATH 里。"""
    name = shutil.which("soffice") or shutil.which("libreoffice")
    if name:
        return name
    # Windows 常见安装路径
    for p in [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]:
        if Path(p).exists():
            return p
    return None


def convert(doc_path: Path, soffice: str) -> Path | None:
    """转换单个 .doc 为 .docx，返回新文件路径。"""
    if doc_path.suffix.lower() != ".doc":
        return None
    out_dir = doc_path.parent
    cmd = [
        soffice,
        "--headless",
        "--convert-to", "docx",
        "--outdir", str(out_dir),
        str(doc_path),
    ]
    print(f"→ converting {doc_path.name} ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ failed: {result.stderr}", file=sys.stderr)
        return None
    new_path = out_dir / (doc_path.stem + ".docx")
    if not new_path.exists():
        print(f"  ✗ output not found: {new_path}", file=sys.stderr)
        return None
    print(f"  ✓ → {new_path.name}")
    return new_path


def main(target_dir: str = "data/raw") -> int:
    target = Path(target_dir)
    if not target.exists():
        print(f"目录不存在：{target.resolve()}", file=sys.stderr)
        return 1

    soffice = find_soffice()
    if not soffice:
        print(
            "未找到 LibreOffice (soffice)。\n"
            "请安装 LibreOffice，或用 Word 手动把 .doc 另存为 .docx。\n"
            "  Windows 下载: https://www.libreoffice.org/download/",
            file=sys.stderr,
        )
        return 1

    doc_files = sorted(target.glob("*.doc"))
    # 排除 .docx（glob 不区分但实际会包含 docx 同前缀的情况）
    doc_files = [p for p in doc_files if p.suffix.lower() == ".doc"]
    if not doc_files:
        print(f"目录 {target} 中没有 .doc 文件。")
        return 0

    success = 0
    for d in doc_files:
        if convert(d, soffice):
            success += 1
    print(f"\n完成：{success}/{len(doc_files)}")
    return 0 if success == len(doc_files) else 2


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
    raise SystemExit(main(target))
