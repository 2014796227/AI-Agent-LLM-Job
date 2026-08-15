from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class AgentSpec:
    name: str
    model: str
    system_prompt: str
    tools: list[str]
    max_steps: int = 6

def _validate_tools(specs: dict[str, AgentSpec]):
    """agents/*.yaml 配置了不存在工具→启动即失败（而非运行期静默缺schema）。"""
    from app.tools import REGISTRY
    unknown = {t for s in specs.values() for t in s.tools if t not in REGISTRY}
    assert not unknown, f"AgentSpec 配置了未知工具: {sorted(unknown)}"

def load_agents(dir_: Path) -> dict[str, AgentSpec]:
    specs = {}
    for f in dir_.glob("*.yaml"):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        specs[raw["name"]] = AgentSpec(
            name=raw["name"], model=raw["model"],
            system_prompt=raw["system_prompt"].strip(),
            tools=raw.get("tools", []), max_steps=raw.get("max_steps", 6))
    _validate_tools(specs)
    return specs

AGENTS = load_agents(Path(__file__).parent.parent / "agents")
