from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    zhipu_api_key: str = ""
    database_url: str = "postgresql://alphadesk:dev@localhost:5432/alphadesk"
    admin_token: str = ""
    data_dir: str = ".data"
    cache_dir: str = ".cache"
    planner_model: str = "glm-4.6"
    worker_model: str = "glm-4.7-flash"
    judge_model: str = "glm-4.7-flash"
    fallback_model: str = "glm-4.7-flash"
    embedding_model: str = "embedding-3"
    embedding_model_fallback: str = "embedding-2"
    embedding_dim: int = 1024
    tool_result_max_chars: int = 6000
    budget_max_dag_nodes: int = 6
    budget_max_llm_calls: int = 25
    budget_max_tool_calls: int = 40
    budget_max_tokens: int = 120_000
    budget_wall_clock_s: int = 300
    critic_max_rounds: int = 2
    artifact_ttl_hours: int = 168
    rate_limit_per_ip_per_hour: int = 20
    daily_token_budget: int = 2_000_000

    # v19（M0-A 实测发现）：pydantic-settings v2 默认 extra='forbid'——.env 里的
    # DB_PASS/ADMIN_TOKEN（compose/backup.sh 用的共享变量，非应用字段）会使
    # Settings() 抛 extra_forbidden（本地 pytest 全挂、api 容器启动即崩）。
    # .env 按部署设计为应用与 compose 共用，应用侧必须忽略不认识的键。
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
