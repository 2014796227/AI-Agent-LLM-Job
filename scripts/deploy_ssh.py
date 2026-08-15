"""部署用 SSH 执行器（M2）：密码经环境变量 SRV_IP/SRV_PW 传入，不落盘不回显。
腾讯云轻量 Ubuntu 镜像默认用户=ubuntu（免密 sudo）；特权命令需显式 sudo。
用法:
  SRV_IP=x SRV_PW=y python scripts/deploy_ssh.py run  "命令"
  SRV_IP=x SRV_PW=y python scripts/deploy_ssh.py put  <本地路径> <远端路径>
  SRV_IP=x SRV_PW=y python scripts/deploy_ssh.py putdir <本地目录> <远端目录>
"""
import os, sys
import paramiko

def client():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(os.environ["SRV_IP"],
              username=os.environ.get("SRV_USER", "ubuntu"),
              password=os.environ["SRV_PW"], timeout=20,
              look_for_keys=False, allow_agent=False)
    return c

def run(cmd: str, timeout: int = 600):
    c = client()
    try:
        stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
        rc = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print("[stderr]", err.rstrip()[:2000])
        sys.exit(rc)
    finally:
        c.close()

def put(local: str, remote: str):
    import time
    # 注意：Git Bash 调用本脚本时远端绝对路径参数会被 MSYS 路径转换改写
    # （/home/x → D:/Git/home/x）——必须以 MSYS_NO_PATHCONV=1 调用，或改用
    # push 模式（exec+base64）。曾经误诊为"服务器安全层 SFTP 节流"。
    for attempt in range(3):
        try:
            c = client()
            try:
                s = c.open_sftp()
                s.put(local, remote)
                print(f"put {local} -> {remote}")
                return
            finally:
                c.close()
        except Exception as e:
            if attempt == 2:
                raise
            print(f"[retry {attempt + 1}] {type(e).__name__}: {str(e)[:80]}")
            time.sleep(2)

def putdir(local: str, remote: str):
    c = client()
    try:
        s = c.open_sftp()

        def ensure(d):
            parts = d.strip("/").split("/")
            cur = ""
            for p in parts:
                cur += "/" + p
                try:
                    s.stat(cur)
                except FileNotFoundError:
                    s.mkdir(cur)

        import pathlib
        ensure(remote)
        n = 0
        for f in pathlib.Path(local).rglob("*"):
            if f.is_file():
                dest = remote + "/" + f.relative_to(local).as_posix()
                ensure(str(pathlib.PurePosixPath(dest).parent))
                s.put(str(f), dest)
                n += 1
        print(f"putdir {local} -> {remote} ({n} files)")
    finally:
        c.close()

def push(local: str, remote: str):
    """SFTP 通道被安全层间歇拦截后的兜底：exec stdin + base64 传输（二进制安全）。"""
    import base64
    data = base64.b64encode(open(local, "rb").read())
    c = client()
    try:
        stdin, stdout, stderr = c.exec_command(
            f"base64 -d > {remote}", timeout=300)
        stdin.write(data)
        stdin.channel.shutdown_write()
        rc = stdout.channel.recv_exit_status()
        err = stderr.read().decode("utf-8", "replace")
        assert rc == 0, f"rc={rc} {err[:200]}"
        _, so, _ = c.exec_command(f"stat -c %s {remote}")
        size = int(so.read().decode().strip())
        import os
        assert size == os.path.getsize(local), f"size mismatch {size}"
        print(f"push {local} -> {remote} ({size}B, 校验一致)")
    finally:
        c.close()

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "run":
        run(sys.argv[2], timeout=int(sys.argv[4]) if len(sys.argv) > 4 else 600)
    elif mode == "put":
        put(sys.argv[2], sys.argv[3])
    elif mode == "push":
        push(sys.argv[2], sys.argv[3])
    elif mode == "putdir":
        putdir(sys.argv[2], sys.argv[3])
    else:
        sys.exit(f"未知模式 {mode}")
