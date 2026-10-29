"""第 1 步：清洗 kb_source → 锁定 eval/corpus_v1，发 doc_id，写 manifest。

不做切块、不做向量化。
已有 manifest 时：同一 path_source（或同 sha256）复用旧 doc_id，避免扩库后 GT 全错位。

用法（在 backend 目录）：
  PYTHONPATH=src .venv/bin/python eval/lock_corpus_v1.py
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_KB = _BACKEND / "kb_source"
_OUT = Path(__file__).resolve().parent / "corpus_v1"
_DOCS = _OUT / "docs"
_MANIFEST = _OUT / "manifest.jsonl"
_SKIP_NAMES = {"README.md", "readme.md"}
_CATEGORIES = ("account", "device", "network", "permission")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _title_of(path: Path, text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or path.stem
    return path.stem


def _is_junk(text: str) -> bool:
    body = text.strip()
    if len(body) < 40:
        return True
    lines = [l for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
    return len(lines) < 2


def collect_candidates() -> list[tuple[str, Path, str]]:
    items: list[tuple[str, Path, str]] = []
    for cat in _CATEGORIES:
        folder = _KB / cat
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md"), key=lambda p: p.name):
            if path.name in _SKIP_NAMES:
                continue
            raw = path.read_bytes()
            for enc in ("utf-8", "utf-8-sig", "gbk"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    text = ""
            else:
                text = raw.decode("utf-8", errors="ignore")
            if _is_junk(text):
                print(f"skip junk: {path.relative_to(_BACKEND)}")
                continue
            items.append((cat, path, text))
    return items


def _load_old_manifest() -> list[dict]:
    if not _MANIFEST.is_file():
        return []
    rows = []
    for line in _MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _next_id(cat: str, used: set[str], counters: dict[str, int]) -> str:
    while True:
        counters[cat] += 1
        doc_id = f"doc_{cat}_{counters[cat]:03d}"
        if doc_id not in used:
            return doc_id


def main() -> None:
    rows_in = collect_candidates()
    seen_hash: set[str] = set()
    unique: list[tuple[str, Path, str, str]] = []
    for cat, path, text in rows_in:
        h = _sha256_text(text)
        if h in seen_hash:
            print(f"skip dup: {path.relative_to(_BACKEND)}")
            continue
        seen_hash.add(h)
        unique.append((cat, path, text, h))

    old = _load_old_manifest()
    by_path = {r["path_source"]: r["doc_id"] for r in old if r.get("path_source")}
    by_hash = {r["sha256"]: r["doc_id"] for r in old if r.get("sha256")}
    used_ids = set(by_path.values()) | set(by_hash.values())

    # 从旧 id 推每类已用最大序号，新文档接着编号
    counters: dict[str, int] = {c: 0 for c in _CATEGORIES}
    pat = re.compile(r"^doc_([a-z]+)_(\d+)$")
    for doc_id in used_ids:
        m = pat.match(doc_id)
        if not m:
            continue
        cat, n = m.group(1), int(m.group(2))
        if cat in counters:
            counters[cat] = max(counters[cat], n)

    # 先写到临时目录，再替换，避免中途失败毁掉旧包
    tmp = _OUT.parent / "_corpus_v1_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    docs_tmp = tmp / "docs"
    docs_tmp.mkdir(parents=True)

    locked_at = date.today().isoformat()
    manifest: list[dict] = []

    for cat, path, text, h in unique:
        rel_src = str(path.relative_to(_BACKEND)).replace("\\", "/")
        doc_id = by_path.get(rel_src) or by_hash.get(h)
        if not doc_id:
            doc_id = _next_id(cat, used_ids, counters)
            used_ids.add(doc_id)
            print(f"new id {doc_id} ← {rel_src}")
        else:
            print(f"keep id {doc_id} ← {rel_src}")

        dest = docs_tmp / cat / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        rel_locked = str(dest.relative_to(tmp)).replace("\\", "/")
        title = _title_of(path, text)
        manifest.append(
            {
                "doc_id": doc_id,
                "path_source": rel_src,
                "path_locked": rel_locked,
                "category": cat,
                "title": title,
                "sha256": h,
                "locked_at": locked_at,
                "bytes": len(text.encode("utf-8")),
            }
        )

    # 按 doc_id 排序写 manifest，方便人读
    manifest.sort(key=lambda r: r["doc_id"])

    if _OUT.exists():
        shutil.rmtree(_OUT)
    tmp.rename(_OUT)

    with _MANIFEST.open("w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_cat = {c: 0 for c in _CATEGORIES}
    for row in manifest:
        by_cat[row["category"]] = by_cat.get(row["category"], 0) + 1

    meta = {
        "version": "corpus_v1",
        "locked_at": locked_at,
        "doc_count": len(manifest),
        "note": "评测锁定语料：扩库时尽量复用旧 doc_id；不切块、不向量化。",
        "by_category": by_cat,
    }
    (_OUT / "LOCK.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"manifest → {_MANIFEST}")


if __name__ == "__main__":
    main()
