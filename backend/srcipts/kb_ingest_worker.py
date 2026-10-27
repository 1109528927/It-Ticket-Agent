"""可选：消费 Redis 列表 kb:ingest，跑入库任务。

未配 REDIS_URL 时接口会走 FastAPI BackgroundTasks，不必起本脚本。

用法：
  cd backend && REDIS_URL=redis://127.0.0.1:6379/0 \\
    PYTHONPATH=src .venv/bin/python srcipts/kb_ingest_worker.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("kb_ingest_worker")


def main() -> None:
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        raise SystemExit("请设置 REDIS_URL")

    import redis
    from utils.kb_ingest import REDIS_QUEUE_KEY, run_ingest_job

    client = redis.from_url(redis_url, decode_responses=True)
    logger.info("监听队列 %s", REDIS_QUEUE_KEY)
    while True:
        item = client.brpop(REDIS_QUEUE_KEY, timeout=5)
        if not item:
            continue
        _, raw = item
        try:
            job_id = int(raw)
        except ValueError:
            logger.warning("非法 job id: %s", raw)
            continue
        logger.info("开始处理 job_id=%s", job_id)
        try:
            run_ingest_job(job_id)
        except Exception:
            logger.exception("处理异常 job_id=%s", job_id)
        time.sleep(0.05)


if __name__ == "__main__":
    main()
