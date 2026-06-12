"""启动后端服务"""

import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PORT = 8000


def _free_port(port: int) -> None:
    """释放占用端口的旧进程，避免代码更新后仍命中无 DELETE 等旧路由的实例。"""
    pids: set[int] = set()
    if platform.system() == "Windows":
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, check=False
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit():
                    pids.add(int(pid))
    else:
        result = subprocess.run(
            ["sh", "-c", f"lsof -ti:{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        for pid in result.stdout.split():
            if pid.isdigit():
                pids.add(int(pid))

    for pid in pids:
        if pid != os.getpid():
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                subprocess.run(
                    ["kill", "-9", str(pid)],
                    capture_output=True,
                    check=False,
                )


# Windows/Codex 环境下 uvicorn --reload 容易遗留 worker，导致 8000 被旧实例抢占。
# 默认使用单进程启动；如确实需要热重载，可设置 JINGHENG_BACKEND_RELOAD=1。
_free_port(PORT)

cmd = [
    sys.executable, "-m", "uvicorn",
    "backend.app:app",
    "--host", "0.0.0.0",
    "--port", str(PORT),
]

if os.getenv("JINGHENG_BACKEND_RELOAD") == "1":
    cmd.append("--reload")

subprocess.run(cmd, cwd=str(ROOT))
