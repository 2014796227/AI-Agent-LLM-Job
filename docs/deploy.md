# 部署运维手册（runbook）

> 适用：单机 Docker Compose 部署（国内云服务器，香港节点免备案）。容器拓扑：db(pgvector:pg16) / api(uvicorn) / web(nginx)。数据卷：pgdata、appdata(工件+文档统一卷)、marketcache。

## 1. 首次部署

```bash
# 服务器上
git clone <repo> /opt/alphadesk && cd /opt/alphadesk
# 1) 配置密钥（三个变量必填，空值=fail-closed/连不上）
cp backend/.env.example backend/.env && vi backend/.env
# 2) 本地构建前端（小内存服务器 npm build 会 OOM——只上传 dist）
#    本地: cd frontend && npm ci && npm run build → 上传 dist/
# 3) 启动
cd deploy && docker compose up -d --build
# 4) 冒烟
curl -s http://127.0.0.1/api/healthz        # {"ok":true,...}
curl -s http://127.0.0.1:8000/metrics | head # 仅 loopback
```

**安全检查单**（每次部署后执行并留痕到验收报告）：
- [ ] 安全组仅开放 80/22
- [ ] `backend/.env` 权限 600，不入 git（.gitignore 已覆盖）
- [ ] `/api/admin/` 外部访问 403（nginx deny）；`/metrics` 外部 403（仅 loopback）
- [ ] ADMIN_TOKEN 非空非默认；DB_PASS 强密码
- [ ] 限流按真实客户端 IP 生效（nginx 覆写 X-Forwarded-For + uvicorn --proxy-headers；同一访客超 20 次/小时应 429，不同访客互不影响）

## 2. 备份（主机 cron 串行链）

`deploy/backup.sh` 由主机 cron 每日 04:00 执行（需要环境变量 `ADMIN_TOKEN`、`DB_PASS`）：
1. `flock` 防重入
2. **先** pg_dump（`-e PGPASSWORD` 注入密码；MVCC 快照）
3. **后** tar appdata 数据卷（工件写入为 tmp→fsync→原子 replace，tar 任意时刻只见完整文件；顺序保证"PG 有行⇒tar 有文件"）
4. **最后** 调用 `/api/admin/ttl` 执行 TTL 清理（与备份互斥由本链顺序保证）

恢复集不变式：**绝不出现"PG 有行、文件缺失"**；孤儿文件由 reconcile 清理。

## 3. 恢复演练（M5 验收项，演练全程留痕）

```bash
# 1) 停应用（保留 db 或使用新实例）
cd deploy && docker compose stop api web
# 2) 恢复数据库
docker compose exec -T db psql -U alphadesk alphadesk \
  < <(gunzip -c /var/backups/alphadesk/<日期>/db.sql.gz)
# 3) 恢复数据卷
docker run --rm -v alphadesk_appdata:/data \
  -v /var/backups/alphadesk/<日期>:/bk alpine \
  sh -c "rm -rf /data/* && tar xzf /bk/appdata.tar.gz -C /data"
# 4) 对账（零悬空为验收标准；孤儿与 .tmp 残留自动清理）
#    必须在 api 容器内执行：宿主机连不上 db（端口未发布），数据也在 appdata 卷内
docker compose cp ../scripts/reconcile.py api:/tmp/reconcile.py
docker compose exec -e PYTHONPATH=/app api python /tmp/reconcile.py --data-dir .data
# 5) 起服务+冒烟
docker compose up -d && curl -s http://127.0.0.1/api/healthz
```

## 4. 升级流程

备份（手动跑一次 backup.sh）→ `docker compose down` → `git pull` → 逐条执行 `migrations/` 新增 SQL（当前无自动迁移工具，ADR-006 记录取舍）→ `docker compose up -d --build` → 健康检查 → 冒烟（发一条测试任务）→ 验收报告留痕。

## 5. 监控

- /metrics（loopback）供主机 Prometheus 采集：关注 `task_status_total{status="failed"}`、`budget_exceeded_total`、`bus_dropped_events_total`、`event_emit_fail_total`、`task_finish_conflict_total`、`embedding_dim_ok`、`rag_search_fallback_total`（查询级向量降级，v17 新增）、`critic_parse_failopen_total`（critic 解析放行，v17 拆分）
- uptime 拨测对 `http://<host>/api/healthz`（任何免费拨测服务即可）
- 告警阈值建议：failed 占比 >20%/日、embedding_dim_ok=0、连续 2 次备份失败

## 6. 已知边界（如实告知面试官）

- 单实例设计：内存限流/单进程租约；多实例需 Redis 化（ADR-006）
- TTL 与备份互斥依赖主机 cron 串行；手工调 `/api/admin/ttl` 必须避开 04:00-04:30 窗口
- migrations 无 Alembic（演示规模取舍，ADR-006）
