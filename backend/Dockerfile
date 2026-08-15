FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt
COPY . .
# --proxy-headers：经 nginx 反代时 request.client 取 X-Forwarded-For（限流按真实访客 IP）。
# 信任边界：api 仅绑 127.0.0.1:8000（compose 端口映射）+ docker 内网可达，故允许全部转发来源。
# v19（M0-D1 实测发现）：exec 形式 JSON 数组不可跨行（v18 拆行致 parse error
# "unknown instruction: --proxy-headers"），合并为单行。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
