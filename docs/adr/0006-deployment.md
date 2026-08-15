# ADR-0006：部署形态——单机 Compose、备份顺序推导、TTL 互斥与迁移约定

- 状态：已接受
- 日期：2026-08-15
- 决策人：＿＿＿＿（待签名）
- 关联：蓝图 Part 6 / deploy/backup.sh / scripts/reconcile.py；第五~七轮评审

## 决策 1：单机 Docker Compose（db/api/web 三容器，三数据卷）

生产对应 K8s；本项目单机足够且故障面小。妥协（如实告知）：内存限流与单进程租约均为单实例设计，多实例需 Redis 化。api 端口仅绑 127.0.0.1（供 backup.sh 调用 admin，nginx 层再 deny /api/admin/ 双保险）。

## 决策 2：备份顺序 = 先 pg_dump 后 tar 数据卷（推导）

- 单条写入不变式：工件先原子落盘（tmp→fsync→os.replace）后写 PG 行 ⇒ 任意时刻"PG 有行 ⇒ 文件已存在"
- 备份批次：dump 中每一行的文件必在 dump 时刻前已落盘，tar 在 dump 之后执行必包含之 ⇒ **恢复集保持同一不变式，悬空引用在数学上不可能**（反向顺序才会产生悬空）
- 残余风险=孤儿文件（行未写时文件已存在）→ 恢复后 reconcile() 清理，零悬空为演练验收标准

## 决策 3：TTL 清理与备份互斥 = 主机 cron 串行链（应用内不自动跑）

第五轮审计证明：TTL 删除若与备份窗口重叠，**任何删除顺序都会在恢复集产生悬空**。故 TTL 仅由 backup.sh 第③步（备份完成后）调用 /api/admin/ttl 触发；互斥由主机调度保证。TTL 删除顺序=先 PG 行后文件（运行时不变式在写入/删除两条路径均成立）。

## 决策 4：迁移 = migrations/ 目录顺序脚本，不引入 Alembic

CREATE TABLE IF NOT EXISTS 只够首建；后续 schema 变更以 `migrations/NNN_*.sql` 按序号手工执行并在升级 runbook 记录。取舍理由：演示规模下迁移工具的维护成本 > 收益；生产化路径明确（Alembic/dbmate，ADR 记录在案）。

## 决策 5：前端本地构建、只传 dist

小内存服务器 `npm run build` 会 OOM；CI/本地构建产物为纯静态文件，nginx 托管。
