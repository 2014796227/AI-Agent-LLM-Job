"""仅做 sys.path 注入（v18 钉死）：使 `from app import ...` 在从仓库根或
任意 cwd 运行 pytest 时均可导入（backend/ 加入 sys.path）。无 fixture 定义。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
