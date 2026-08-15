# 评测冻结快照（fixtures）

- 生成方式（M0-B3）：`market.fetch_combined(symbol, start, end)` 的**完整帧**
  落盘 parquet——必须保留 hfq+raw 双口径全部 10 列（date 索引 +
  open/high/low/close/volume × hfq/raw）。文件名中的 `hfq` 指**信号计算
  口径**，不代表仅含 hfq 列；`tools._load_fixture` 加载即校验列齐备
  （v18 P2-1）。
- meta 必含：`fetched_at`（UTC）、`akshare_version`、`checksum`（sha1）。
- 用途：跨版本对比一律对快照复算（消除数据源漂移，ADR-0003）；禁止手工
  编辑数据内容。
