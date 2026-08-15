"""知识库摄取 CLI（M4 起的主入口；rag.ingest_pdf 的唯一调用方）。
用法: python scripts/ingest.py --pdf <path> --title <标题>
      [--source-url <url>] [--type official|curated]"""
import argparse, asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

async def main(a):
    from app.db import init_schema
    from app import rag
    await init_schema()
    ok = await rag.probe()          # 先探针（选定嵌入模型并记录 VECTOR_OK）
    doc_id = await rag.ingest_pdf(a.pdf, a.title, a.source_url, a.type)
    print({"doc_id": doc_id, "vector_ok": ok})

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--source-url", default=None)
    ap.add_argument("--type", choices=("official", "curated"),
                    default="official")
    asyncio.run(main(ap.parse_args()))
