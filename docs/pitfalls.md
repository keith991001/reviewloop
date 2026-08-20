# 踩坑日志

> 规则:卡住超过 30 分钟就记一条。格式:现象 → 原因 → 解法。按时间顺序追加,不事后美化。

## 2026-08-20 项目初始化

**P001: Python 3.14 太新,主动降级 3.12。**
本机默认 Python 3.14.4。claude-agent-sdk / langgraph 的生态对最新大版本的兼容通常滞后数月,为避免把时间花在排查"是我的代码错了还是依赖不支持 3.14",用 `uv init --python 3.12` 锁定到成熟版本。教训:搭 agent 项目时,Python 版本选"最新减一"。

**P002: 脚手架工具会静默泄漏身份信息。**
`uv init` 自动把**全局 git 配置**里的姓名/邮箱写进 `pyproject.toml` 的 `authors` 字段。如果全局配置是工作身份,公开仓库就会带出去。教训:要求匿名/换身份的仓库,初始化后先 grep 一遍所有生成文件(`grep -ri <邮箱域名>`),不能只盯 commit author。

**P003: LangGraph 的 checkpointer 不在主包里。**
`from langgraph.checkpoint.sqlite import SqliteSaver` 会 ImportError——SQLite 持久化拆在独立包 `langgraph-checkpoint-sqlite` 里,需要单独安装。LangGraph 把所有 checkpointer 后端(SQLite/Postgres/Redis)都做成了插件包,主包只含内存版。
