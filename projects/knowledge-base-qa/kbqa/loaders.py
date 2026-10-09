"""文档加载与落盘模块（spec §7.3）。

职责边界：
  ① 把磁盘上的 .txt/.md 读成纯文本（`load_document`）；
  ② 把上传的字节落盘，并按内容哈希去重（`save_upload`）；
  ③ 列出上传目录，并合并"是否已索引 / chunk 数"（`list_documents`）——
     这里只 **读取** 索引元数据（经 vectorstore.read_indexed_docs），不写、不碰向量本身。
不做切分、不做向量化、不写向量索引：那些分别属于 chunking / embeddings / vectorstore。

存储约定（为什么这么设计）：
    data/uploads/ 下的文件名统一为 f"{doc_id}_{原始文件名}"。
    - 前缀 doc_id 让"内容是否已存在"只需一次 glob 就能判断，去重是 O(1)；
    - 原始文件名保留在磁盘名里，list_documents 无需额外元数据即可还原展示名；
    - doc_id 直接可见，便于对照日志排查（对应 §1.2 的可观测目标）。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path

from kbqa.models import Document
from kbqa.vectorstore import read_indexed_docs

logger = logging.getLogger(__name__)

# 本期只支持这两种（spec §1.3 非目标：不做 PDF / Word / 网页解析）
SUPPORTED_SUFFIXES = {".txt", ".md"}

_DOC_ID_LEN = 16  # sha256 前 16 位：够短，碰撞概率又低到可忽略


def _compute_doc_id(content: bytes) -> str:
    """由文件内容算出去重用的 doc_id。内容相同 → doc_id 相同（内容寻址）。"""
    return hashlib.sha256(content).hexdigest()[:_DOC_ID_LEN]


def _stored_name(doc_id: str, filename: str) -> str:
    """磁盘上的文件名 = doc_id + 下划线 + 原始文件名。"""
    return f"{doc_id}_{filename}"


def _parse_stored_name(name: str) -> tuple[str, str]:
    """从磁盘文件名反解出 (doc_id, 原始文件名)，格式见模块顶部存储约定。"""
    return name[:_DOC_ID_LEN], name[_DOC_ID_LEN + 1 :]


def _is_upload_file(name: str) -> bool:
    """判断一个文件名是否符合本模块的落盘命名，用于过滤 .gitkeep 等非文档文件。"""
    if len(name) <= _DOC_ID_LEN + 1 or name[_DOC_ID_LEN] != "_":
        return False
    if not all(c in "0123456789abcdef" for c in name[:_DOC_ID_LEN]):
        return False
    return Path(name).suffix.lower() in SUPPORTED_SUFFIXES


def _to_document(path: Path, doc_id: str, filename: str) -> Document:
    """由磁盘文件构造 Document。size/uploaded_at 一律以真实文件为准，避免与磁盘不一致。"""
    stat = path.stat()
    return Document(
        doc_id=doc_id,
        filename=filename,
        path=path,
        size=stat.st_size,
        uploaded_at=datetime.fromtimestamp(stat.st_mtime),
        # 单篇构造时无从判断索引状态，先给安全默认值；
        # list_documents 会基于 data/index/docs.json 覆盖这两个字段（§7.3）
        indexed=False,
        chunk_count=0,
    )


def load_document(path: Path) -> str:
    """读取一篇 txt/md 文档为纯文本。

    Args:
        path: 文档路径。

    Returns:
        文件全文（UTF-8 解码）。

    Raises:
        ValueError: 后缀不在 SUPPORTED_SUFFIXES 中。
        FileNotFoundError: 文件不存在。
        UnicodeDecodeError: 文件不是 UTF-8 编码。
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"不支持的文件类型：{path.name}（仅支持 {sorted(SUPPORTED_SUFFIXES)}）"
        )
    # md 保留 # 标题等原始标记：标题层级是切分时的强边界，提前剥掉会丢信息（§7.3）
    return path.read_text(encoding="utf-8")


def save_upload(filename: str, content: bytes, data_dir: Path) -> Document:
    """把上传内容落盘，并按内容去重。

    Args:
        filename: 客户端传来的原始文件名（可能含路径，会被安全化处理）。
        content: 文件字节。
        data_dir: 数据根目录，实际写入 {data_dir}/uploads/。

    Returns:
        对应的 Document；若内容已存在，返回已存在的那一份（不重复落盘）。

    Raises:
        ValueError: 文件名后缀不是 .txt / .md。
    """
    uploads_dir = data_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # filename 来自外部输入，先取 basename 防止 "../" 之类的路径穿越
    safe_name = Path(filename).name
    if Path(safe_name).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"不支持的文件类型：{safe_name}（仅支持 {sorted(SUPPORTED_SUFFIXES)}）"
        )

    doc_id = _compute_doc_id(content)

    # 命中已有内容 → 直接返回，避免同一篇文档在 uploads 里存多份（FR-1 按内容去重）
    existing = next(iter(uploads_dir.glob(_stored_name(doc_id, "*"))), None)
    if existing is not None:
        _, original_name = _parse_stored_name(existing.name)
        logger.info(
            "上传完成 filename=%s size=%d doc_id=%s 命中去重=是",
            safe_name,
            len(content),
            doc_id,
        )
        return _to_document(existing, doc_id, original_name)

    stored_path = uploads_dir / _stored_name(doc_id, safe_name)
    stored_path.write_bytes(content)
    logger.info(
        "上传完成 filename=%s size=%d doc_id=%s 命中去重=否",
        safe_name,
        len(content),
        doc_id,
    )
    return _to_document(stored_path, doc_id, safe_name)


def list_documents(data_dir: Path) -> list[Document]:
    """扫描上传目录，列出全部文档。

    Args:
        data_dir: 数据根目录，扫描 {data_dir}/uploads/。

    Returns:
        按文件名排序的 Document 列表；目录不存在时返回空列表。
        indexed / chunk_count 由 data/index/docs.json 合并而来（只有已索引的文档才为 True / >0）。
    """
    uploads_dir = data_dir / "uploads"
    if not uploads_dir.is_dir():
        return []

    # 索引状态是"单独一份元数据"，先一次性读进来，避免每篇文档都去读一遍文件
    indexed = read_indexed_docs(data_dir / "index")

    docs: list[Document] = []
    for path in sorted(uploads_dir.iterdir()):
        if not path.is_file() or not _is_upload_file(path.name):
            # .gitkeep 等占位文件、以及人工塞进来的文件都不算文档，跳过
            logger.debug("跳过非上传文件：%s", path.name)
            continue
        doc_id, filename = _parse_stored_name(path.name)
        doc = _to_document(path, doc_id, filename)
        # 合并索引状态：docs.json 里出现过才算"已索引"，chunk 数也从那里取（§7.3）
        doc.indexed = doc_id in indexed
        doc.chunk_count = indexed.get(doc_id, 0)
        docs.append(doc)

    logger.info("扫描上传目录 文档数=%d", len(docs))
    return docs
