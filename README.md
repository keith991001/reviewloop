# reviewloop

把「PR review comment → 修改 → 自查 → push」的循环交给一组分工明确的 agent,人只在风险闸门处审批。

## 它解决什么问题

AI 辅助开发普及后,开发者的日常变成:把 review comment 转发给 AI → 看一眼修改 → push → 等下一轮。
这些动作机械,但又不能全放手——AI 的修改可能触碰危险区域(迁移、认证、密钥、批量删除)。

reviewloop 的回答:**机械的部分全自动,危险的部分强制人审。**

```
review comment ──► Implementer(修改+跑测试)──► Reviewer(独立评审,带 rulebook)
                        ▲                            │打回(≤3轮)
                        └────────────────────────────┘
                                                     │通过
                                              Risk Gate(规则分类)
                                     无风险 │            │ 命中规则
                                          push      ⏸ 暂停等人批准(CLI)
```

三个关键设计(详见 [design.md](docs/design.md)):

- **利益分离**:写代码的 agent 和评审的 agent 上下文完全隔离,Reviewer 每轮全新、只看 diff + rulebook。
- **权限设计代替行为约束**:agent 工作目录的 git push URL 被物理禁用,全系统唯一能 push 的是编排层的确定性代码,且必须先过 Reviewer 和 Risk Gate。
- **rulebook 让 review 意见变成资产**:人类指出过的问题沉淀为规则,之后由 Reviewer agent 在内部循环拦截,同类意见不会被人类提出第二次。

## 技术栈

LangGraph(状态机编排 + `interrupt()` 人工审批 + SQLite 断点续跑)/ Claude Agent SDK(Implementer 与 Reviewer 的执行引擎)/ gh CLI(GitHub 访问层)。选型对比见 design.md 第 5 节。

## 使用

前提:`gh auth login` 已完成,`claude` CLI 可用(Agent SDK 依赖其登录态)。

```bash
export REVIEWLOOP_REPO="owner/name"        # 目标仓库
export REVIEWLOOP_GIT_NAME="Your Name"     # 提交身份(可选)
export REVIEWLOOP_GIT_EMAIL="you@example"  # 提交身份(可选)

uv run reviewloop once          # 处理一轮新 comment 后退出
uv run reviewloop poll          # 持续轮询(默认 120s)
uv run reviewloop pending       # 查看等待人工审批的风险变更
uv run reviewloop approve pr12-c3456789   # 批准 → 从断点恢复并 push
uv run reviewloop reject  pr12-c3456789   # 驳回 → 丢弃变更并回复说明
```

## 仓库结构

```
docs/design.md       设计:状态机、角色、选型理由、范围决策
docs/pitfalls.md     构建过程踩坑实录(按时间序,不事后美化)
rulebook/rules.md    Reviewer agent 每轮加载的评审规则(人类意见的沉淀)
src/reviewloop/      ~600 行 Python:graph(编排)/ agents(LLM 角色)/
                     github(唯一写路径)/ risk(确定性风险分类)/ cli
```

## 状态

- [x] 状态机 + 双 agent 循环 + 风险闸门 + CLI 审批
- [ ] demo 仓库实录(GIF)
