# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-06-12

## User Preferences
- [2026-08-20] 模型准入治理不应过度依赖来源/产地判断；文档与实现应改为 Lenovo 可直接管理和验证的控制体系优先（owner、kill-switch、rollback、SLA、可验签处置证据），来源信息仅作风险信号与条件收紧依据。
- [2026-08-15] 议事广场国际化不接受页面内巨型中英文本映射 + 全 body MutationObserver 重扫方案；应使用明确翻译键、可控动态渲染和项目共享 i18n 接口，避免隐式文本替换与主线程风险。
- [2026-07-25] 模型与连接里配的全局 LLM 必须全局生效，其它路由/团队模型/硬编码一律不要生效。
- [2026-07-16] **Taste Skill 官方源** = https://www.tasteskill.dev （`npx skills add Leonxlnx/taste-skill --skill design-taste-frontend`；本地 `.agents/skills/design-taste-frontend/SKILL.md`）。规则要点：Page Theme Lock / Color Consistency Lock（单 accent）/ 禁 AI-purple·mesh / off-white+off-black 勿纯色。产品台浅色壳：`html.taste-light` + `css/taste-light.css`（除数字孪生暗色沉浸）；Skill 原文偏 landing，控制台取 cockpit 密度 dials。
- [2026-07-16] skill-extract 3D 用 **TASTE3D**（`skill-extract.js`）：背景 `#F3F5F8`、accent `#1F6B4A`、冷 slate 基质；技能私有=forest 系、公共=warn amber 语义色；**禁止** twin sexy 彩虹（紫/粉/霓虹青）。数字孪生页仍可暗色沉浸，勿与 skill-extract 浅色培养皿混用同一套 neon palette。
- [2026-07-16] 浅色壳对比度：任何「近白字 #EEF2F5 / shironeri」在白底 modal 上必须重映射；skill-extract 详情 tab（编辑/演化/验证/效果/版本/智线）用 `--modal-tab-fg*` 变量，active=accent 绿，禁止白字。
- [2026-07-16] 衰老 senescence_rate 属 **Agent 生命史**（metabolism），不是环境选择压；勿与 habitat / evolution_pressure 混装。UI：A 生境 / B 环境 Darwin / C Agent 衰老。

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- [2026-07-15] Token 治理杠杆区：长文只在 README；UI 一行管线（接线/启用/试跑/旋钮）；算法参数必须进 settings.params 并真接 prepare（含 budget alert_threshold）。
- [2026-07-15] 论文/research 线（paper/、*.md 研究流水线、research-state）用户明确要求 agent 不要参合；除非用户再点名，禁止改 paper/ 与研究稿。
- [2026-07-04] 数字孪生统一办公室里的 Agent 造型必须复用 plaza 的 agent 模型骨架/视觉语言；不要做成黑色圆柱、棋子或“站桩胶囊”。参考 Marvis 办公室时保持极简白空间，但 Agent 本体用 plaza 风格。
- [2026-07-05] 统一办公室里的猫不是静态摆件；需要有 Agent↔猫互动过程。基础规则：离猫最近的 Agent 会转身面向猫，并通过闪烁/放大的脚下光圈吸引猫。
- [2026-07-05] 猫「按有效技能数跳到 Agent 桌上」的逻辑用户明确不要，已撤销；不要再加回。猫互动只保留最近 Agent 转身+光圈吸引。
- [2026-07-11] 用户世界观（物竞天择，最高设计约束）：Agent 不是人类模仿，应有自己的生态/沟通/繁衍/成长方式；以「感知-意图-行为」存在；skill 与协作过程都是被环境选择的可遗传单元（不是 skill 选路径、不是主动换协作方式）；主动学习是盲目的、选择是客观的；生存时长是唯一适应度，禁止人工评分。办公室视图(?office3d=1)=物竞天择试验田：右侧演练菜单整体换成生境控制台，3D 窗口必须始终保留且有内容。
- [2026-07-11] 演练类页面右侧菜单重构时用户要求「完全与以前不一样」，不接受在旧 SECS 菜单上叠加小块——要整面板替换。
- [2026-07-14] 用户 UX：生境参数应在数字孪生左侧用「音量式旋钮」调节（非抽象按钮名）；团队+智能体合并树状；pet-config 保留深参实验室。旋钮语义=客观环境强度，不是评分。
- [2026-07-15] cost 页 UX：顶部导航与下方全链步骤必须合并为一层（cost-shell），禁止 topbar 序号 + 再画一条 pipe 重复；动作栏并入壳右侧，筛选+OpenCost 并入 detail-bar。
- [2026-07-15] Token 治理 v2：禁止「四卡片演示皮」。业界四车道=归因(Helicone式)/缓存(exact+semantic-lite)/路由(model+skill)/预算；上下文工程=simplify+compress+compact。统一 `TokenGovernanceService.prepare_request` 接 chat_harness；UI 单工作台 `token-workbench.js` + `/dashboard`。Taste Skill：控制台 density 高、单 accent、无紫渐变。Plaza 仍不做 token 优化。
- [2026-07-15] SkillRouter.route 返回 **RoutingSession 对象**（非 dict）；`_skill_hint` 必须读 `.results`/`.skill_id`。pool=0 时关键词回退团队 skills。prepare 节省 JSONL + `GET .../savings`；usage 可观测行 phase=`tg_prepare` total=0。

- [2026-07-14] 数字办公室 3D 不展示生境「当前需求」蓝柱黄球图腾，也不默认播觅食光点——办公室没有「觅食」孪生语义；需求 skill 用右侧控制台 chips/反馈台表达。实验可视化仅 window.__ECO_HABITAT_3D__=true。

- [2026-07-14] 物竞试验田必须以任务（业务场景实例）为主闭环：演练控制选择种群后都要提供任务挂载菜单；无任务空跑为次要/须显式确认。

- [2026-07-14] 物竞协作的**真正变化**是团队配置页「关系」+「通道绑定」经人确认写回，不是只写 metadata.eco_collab 四维基因。基因=仿真表型；关系边/通道=通信拓扑。须 suggest→确认 apply，禁止静默建边；mate/COURT 不映射业务 collaborator。设计见 docs 适者反馈 plan §3.5 / todos XF-7。

- [2026-07-14] 用户校准：同队 peer 与共总线（如 aws_ops_bus）**就是协作关系**，不得说成「假/软/不算」。协作三层都真：①同队编制 ②通道协作 ③点对点门禁边；差别只在运行时 enforce 点，不是「算不算协作」。


## Key Learnings
- [2026-08-15] DOM-walker i18n 与 MutationObserver 组合时，调用 `applyAll()` 前必须 `disconnect()`，完成后再 `observe()`；`applyAll()` 会重写语言按钮 `textContent`，若观察 `childList` 且不断开会自触发微任务循环，页面表现为永久加载、Playwright 无法执行。
- [2026-08-05] 用户确认「智能体团队→模型与连接」的模型连接测试可用；排查任务 `token_factory_ready=false` 时，不能把它归因于上游大模型不可用，需区分模型连接状态与 TokenFactory 运行时类/适配器是否存在。
- [2026-08-04] 任务页审计：AWS 运维团队 Agent 的展示 role 是中文业务角色，不能直接假设等于 `_ROLE_WORKFLOW_MAP` 的规范 role；任务 workflow 必须显式保存 `workflow_role` 并在启动前拒绝 unresolved agent。`tasks.html` 仍有旧数组读取，不能只看 `tasks-view.js` 的分页测试。
- [2026-08-04] 任务提交存在单条 REST、批量、手动启动三条不同路径；任何新增字段（如 `execution_mode`）和预检都必须在三条路径共享，否则 UI 选择值会被丢弃或流程行为不一致。
- [2026-07-28] Agent记忆补完收口：M-3.2b 真 LLM 五组（`experiment_agent_memory_adaptation_llm.py`，glm-5.1，30 cells）；`inherited_hits_for_recall` 必须软相关（token/bigram/hash），禁止整句精确子串——否则中文标题召不回 es_scale 继承记忆（首轮全 mem_chars=67 假阳性）。M-3.3b 审计：生产 team_v/* log=20+sum=40 + 协议重跑。
- [2026-07-27] Agent记忆补完：迁移引擎 `agent_memory_migration.py`（export v2 强校验/三策略/inherited 分区/事务回滚/Will preflight+execute）；默认 merge；旧 /transfer 走 Will；AFFECT 72h 半衰期用 0.5**(dt/half_life)；Plaza 发言后 after_agent_plaza_message；实验 `scripts/experiment_agent_memory_adaptation.py` 隔离 tempfile。
- [2026-07-27] S1 L3：数字孪生 loadLiveMetrics=/tasks/stats+/extraction/stats 是全局 KPI，不按 team/trial 过滤；「当前演练」卡只读 dtContext/_sx（team/scene/task/steps/reward/trial），经 dtRefresh→renderArchitecture→renderDashboard；task_engine.stats 的 running 是 engine bool，前端用 by_status 计数（_mapTaskEngineStats）。
- [2026-07-27] 9.3/9.4 后续增强：完整注意力反传=`tse/full_attention_trainer.py`（trainer=full_attention_v1）；证据定位 Hit@1/Recall@k/F1=`evidence_localization_metrics`；schema v2；sweep CLI 12/24/48/96×seeds；图5/6 只读 JSON 渲染（render_tse_experiment_figures.py，需 matplotlib/venv）；禁止把关键词基线/规模当相变真值。
- [2026-07-27] 论文 9.3/9.4 复现入口=`scripts/run_tse_paper_experiments.py`；夹具 `tse/fixtures/latency_9_3.jsonl`(5×5) 与 `attention_9_4.jsonl`(12/53)；关键词注意力算法版本 `field-keyword-cosine-v2-shared-hash-space`（同 hash_seed）；checkpoint 必须显式且 epoch=30；勿用旧 fig6 异种子口径拟合。
- [2026-07-27] 技能发布门禁 `skill_publish_gate`：pass_rate≥0.70、min_samples≥3、twin 实际跑过时 target_gain≥0.05（或 twin_passed）；env `AG_SKILL_PUBLISH_PASS_RATE_MIN`/`TWIN_GAIN_MIN`/`MIN_SAMPLES`/`MIN_USAGE`；不达标 `publish_gate_blocked` + `candidate_held`，lifecycle 保持 verified/private。EvidenceRun.metrics_after 写 twin_* 扁平字段供门禁读取。E2E：`pytest -k skill_loop_e2e`。
- [2026-07-25] 数字孪生 3D（office3d）猫静音：#office-cat-mute-btn（🐱🔊/🔇），OfficeAPI.toggleCatMute，LS=ag-office-cat-muted；静音只停语音，气泡仍可显示。
- [2026-07-25] 用户铁律：在「模型与连接」配置了全局 LLM 后，全系统只走该连接；resolve_effective_config/model 忽略 config_override、model_override、model_route、团队槽；tool_loop 入口强制替换 config；仅 __model_test__ 等探针可临时测其它 model。
- [2026-07-25] 产品铁律「全局配置为主」：默认 prefer_global_model=True，chat_harness/tool_loop 上游 model=连接配置；model_route 只记 tier；仅 AG_MODEL_ROUTE_ALLOW_SWITCH=1 才允许 deepseek 多档改名。
- [2026-07-25] 「全局 LLM 配置=全局效果」：权威源=ChatHarness.get_provider_config()；model_route 经 clamp_model_to_global；prepare_request/tool_loop/chat_harness 全路径钳制；非 deepseek 网关三档同用全局 model；set_global_override/init 时 resync。
- [2026-07-25] 演练 403 `team_model_access_denied` deepseek-v4-pro：全局已配 glm-5.1 仍中招，因 TG `model_route` + ModelRouter 硬编码 standard=deepseek-v4-pro；测试连接因 `__model_test__`/model_override 跳过所以「成功」。修复：非 deepseek 网关三档同用全局 model；drill/twin skip；set_global_override 时 resync。
- [2026-07-25] 议事大厅执行计划可多选 team_ids 并行派发（dispatch_group_id）；孪生深链 team_ids/extra_team_ids 接 eco drill 多队对抗。
- [2026-07-24] 拟生记忆全收口：EventType.ECO_SURVIVAL_UPDATED + collab apply emit；vector-lite 哈希余弦（AG_MEMORY_VECTOR_LITE）；工作台配置页 pane；README 已改拟生专章。
- [2026-07-24] 拟生记忆 P2/P3：drift_topology(fitness/survival)；working 槽位；transfer_narrative 小满连续/沈弥安凭吊；电荷 charge_transfer never/soft；中枢 systems 分栏+遗忘审计。
- [2026-07-24] 拟生记忆：前瞻意图(prospective)=过程非层；affect=电荷场；层=感觉/情节/语义。consolidate_tick 情节→语义核；forget_tick soft-forget；感情=fitness→电荷→巩固。API: systems/consolidate/forget；UI 已正名。
- [2026-07-24] `GET /api/v1/agent-config/teams` 控制台 500：api.js:363 只是全局 fetch 包装行号；常因 Vite 反代时后端重启瞬时失败。list_teams 已防御性跳过坏 team；配置页 loadAgent 须委托 window.loadAgent（agent-detail IIFE）否则记忆绑定 tab 空白。
- [2026-07-24] 记忆默认 state=unbound（无 meta 非 active）；`ensure_memory_ready` 首次使用 auto-bind；`record_chat_turn` 对话入感知+日志；沈弥安 `maybe_reflect` 高重要度反思；中枢支持 ?team_id&agent_id&seg 深链。
- [2026-07-24] Agent记忆 P3 收口：README 专章；配置页记忆 tab 对齐 lifecycle/persona/中枢；AAS `bridge_aas_experience`（`AG_MEMORY_AAS_BRIDGE=1`）。P0–P3 主链路完成。
- [2026-07-24] Agent记忆 P2：`agent_memory_runtime` prepare/inject；chat_harness 注入 tone+recall（plaza 跳过）；TASK_COMPLETED/FAILED→record_task_outcome；tool_loop→record_perception+阈值compress；Persona autonomy 旋钮控制。
- [2026-07-24] Agent记忆 P1：`agent_memory_share` ACL(reader/co_writer+layer_mask，默认无affect；沈弥安强制剥affect)；`agent_memory_transfer` 复制传递+意图auto/ask/drop+凭吊archived；UI 共享矩阵/传递台。
- [2026-07-24] Agent记忆 P0：`agent_memory_lifecycle` 状态机(bind/save/seal/unseal/share/destroy+tombstone)；hub `/api/v1/agent-memory`；站级菜单「Agent记忆」`agent-memory.html`；Persona 小满/沈弥安/hybrid。P1 共享ACL+传递；P2 运行时自主挂钩。
- [2026-07-24] 智能体记忆绑定（TigerInBamboo 移植）：四层 `log/perception/intentions/affect` 服务端落盘 `storage/agent_memory/<team>/<agent>/`；API `/api/v1/agent-config/teams/{team}/agents/{agent}/memory-core/*`；智能体配置页 tab「记忆绑定」(`ag-memory`) 支持绑定/封存/导出导入/时间轴；与人格页 `memory_files` 文件记忆并存（文件=文档，四层=运行时遗体）。
- [2026-07-24] Twin 闭环可视化：`apply_evolution` 写 `twin_before_evolve`；`verify` 写 `twin_history`+`twin_compare`(before/after/delta_gain_pp) 并回 `verification_evidence`；UI `_renderTwinCompareHtml` 双条柱+增益轨迹。证据加厚：`task_usage`(usage/success/fail) + `SkillRouter.get_skill_affinity_evidence` 入 evolve prompt。
- [2026-07-23] 技能闭环：`verify` 写 `skill.config.last_verify`（status/pass_rate/failed_checks/twin_ab 摘要）；`_gather_evidence` 喂 usage+last_verify+last_evolution 进演化 prompt；验证失败 UI「根据失败回演化」→ `user_feedback` + 可选 auto triggerEvolve。
- [2026-07-20] skill 闭环：`acceptEvolution` / 效果页应用改进后自动 `switchModalTab('verify')` + `triggerVerify`（语义+沙箱+Twin A/B）；`apply_evolution` 回 `next_step=verify` 并将 changelog 写入 skill.config.last_evolution。
- [2026-07-18] 技能验证 Twin A/B：skill_twin_ab 按 metadata.scenario+target_skill（或 code_delivery→code_review_delivery）跑 baseline/treatment 熟练度+instructions override；增益≥5pp 为 twin 通过；UI 展示对照表。env: AG_SKILL_TWIN_AB_SEEDS/GAIN/MAX_STEPS。
- [2026-07-18] 技能验证=语义层(步骤/工具落地与 mock/场景对齐/拒离线占位)+沙箱结构；hard_fail 挡回退草稿。路由结果含 lifecycle_stage/note/mult，UI 徽章展示。
- [2026-07-18] SkillRouter：retrieve+rerank 后乘 lifecycle（verified/solidified↑ draft/degraded↓）；affinity/feedback 持久化 storage/skill_router_state.json。
- [2026-07-18] 技能演化=证据→JSON草稿(improved_instructions/changelog/preserved_intent)→语言硬守卫(flip 拒绝交付)→人审可编辑 apply；禁止自由散文英文化 SOP。验证=沙箱结构启发式非业务实跑。路由=BM25/IDF 两段词法检索（名 Bi/Cross 实非神经网络）。
- [2026-07-18] 萃取成果三 tab = **skill_type**（trait/reserve/public），不是 draft_scope。默认批准=**reserve**；personal≠特质。classifySkill(distilled→trait) 已废，禁止再用「非公共=特质」。

- [2026-07-18] 技能萃取失败占位：**禁止** draft_name 带「【回退草稿】」；优先 TSE `synthesize_skills_local`；最后兜底 1 条议题名离线占位 + model=`deterministic-fallback`/`tse+local(offline)`；UI 用 cleanDraftName 剥历史前缀并标「离线」。

- [2026-07-17] 技能萃取 LLM 必须 **跳过 TG model_route**：agent_id∈{skill_extractor,tse_skill_extractor,tse_silver} 或 phase=extract，并 `model_override=provider.model`（如 qwen-36）。否则 cost_tier 改写成 deepseek-v4-flash/pro → 上游 not supported → 假离线 → 回退草稿。已修 chat_harness + TSE decoder。

- [2026-07-17] TSE **训练链路**（无 torch）：`silver` 银标 → `PlazaExtractionDataset` JSONL → `train_tse` 多任务 loss(AE=1.0, cat=0.1, tools=0.1) 更新 query_vectors+heads(+TCN W_out) → `storage/tse/checkpoints/latest.npz`；推理 `get_tse_pipeline(load_checkpoint=True)` 自动加载。CLI：`PYTHONPATH=src/backend python3 scripts/train_tse.py --demo`。Active learning：`active.py` 按 category 熵选人审。

- [2026-07-16] 技能萃取主路径 = **TSE** (`agents/tse/`): transcript→hash encoder→TCN(d=1,2,4)→5-field skill-query cross-attn→ChatHarness constrained JSON。`skill_extractor._llm_prefill` 调用 `tse.extract_skills`；telemetry 写 `source_meta.tse`。无 torch 时 pure-numpy；CodeLLaMA/QLoRA 为训练向可选，运行时解码走系统 LLM。

- [2026-07-16] 物竞 Darwin 扩展四键：`sexual_selection_strength`（性选择×mate_choosiness+COURT/互补质量）、`freq_dep_strength`（负频率依赖防 skill 垄断）、`epistasis_strength`（demand 相邻 skill 对非加性）、`senescence_rate`（μ×age 防不死垄断）。EcoDrill economics 默认 0 零回归；生产走 evolution_pressure → `_habitat_params` 注入。B 加压旋钮 11（性选择/频依/上位等）；C=metabolism.senescence。


- [2026-07-15] Token 治理 R9：真省不靠页面罗列。prepare 管线=simplify→ponytail/caveman→rtk_tool→compress→progressive_mem→codegraph→cache→skill→cost_tier+model→budget。rtk 压缩 tool 噪声；claude-mem 式折叠旧轮次；codegraph MIT CLI+本地符号切片；flowork cost_tier 推 economy。OpenWolf 仅模仿思想（AGPL 不拷源码）。

- [2026-07-15] Token 治理 KPI：`saved_tokens_est` 与 counters 只认 prepare 净 before→after；`cache_mode=observe` 的 HIT 不计入已省（serve 短路才计）。skill 注入可能使 after>before，净省=0 但分杠杆仍可显示 simplify/compress 省量。

- [2026-07-15] 治理杠杆权威源=lever_catalog.py（industry.inspired_by + ours.module/algorithm + exec_path）；GET /levers 必须带 catalog+architecture；UI 只渲染 catalog，禁止前端硬编码空开关文案。试跑结果写回卡片 data-sim-slot + 全字段表（kind/module/before→after/saved）。


- [2026-07-16] **编辑模型「测试连接」≠ 全局测连接**：`POST /llm/test-model` 必须 `model_override=编辑框 name`，且 agent_id=`__model_test__` 跳过 TG `model_route`。否则 cost_tier 短句 → economy → 硬编码 `deepseek-v4-flash`，上游报 model_not_found，UI 却显示 requested_model=用户填的 qwen 名（假象）。响应字段：`requested_model`（编辑框）+ `sent_model`（实际上游）。
- [2026-07-11] 密钥有两类槽位：全局默认 provider 槽（PUT /llm/provider → secret store __default__，cat-speak/广场/萃取等默认调用读它）与团队模型槽（编辑模型保存 → teams 段）。用户在编辑模型里存 key 不会自动喂饱默认 provider（除非 _sync_default_model_to_harness 同步 api_key——XB-8.2 待验证）。排查"LLM 未连接"先分清调用方读哪个槽。
- [2026-07-11] 判断线上行为是否为旧代码：先比对后端进程启动时间与相关文件 git 提交时间（XC-6.1 建议在 /health 暴露 git rev）。旧任务的会话 lines 缓存会回放旧引擎日志头，易被误判为"改了没生效"。

- **Project:** agentsgroup2026
- **Description:** Standalone Agent Management, Evolution & Chat Platform — extracted from PoseidonX
- G1-2 约定：萃取审批通过时即写入 skill_classification 初始 reserve 记录（幂等），后续由 verifier + 周期 reclassify 决定毕业。
- G3-2 约定：试炼评估结果需携带 routing_comparison/routing_benefit（相对 baseline 的策略收益），并在 branches 接口返回 routing_strategy 供导演台直接展示。
- 任务执行（agent_team 工作流分步）的"系统配置 LLM"权威来源是 ChatHarness 的 provider 配置（由"模型与连接页"→ `update_default_provider` → `config/model_pool.json`），用 `get_chat_harness().get_provider_config()` 读（字段 provider/api_key/api_base_url/model，`resolve_base_url()` 给 base）。**不要**用 `~/.claude/settings.json` / 本地 `claude` CLI 作为任务执行 LLM 来源——那是历史写死路径，本地不可达会导致任务无限 `running`。api.py `_get_deepseek_credentials()` 已改为优先 harness 配置。
- 任务执行三条路径：tool 角色→`_run_tool_loop`；文本角色(_TEXT_ONLY_ROLES)→`_run_openai_compatible`；其余→`_should_use_direct_api` 决定直连 vs 本地 CLI。`_run_openai_compatible` 用 urlparse(base_url) 拼 `{path}/chat/completions`，deepseek/codebuddy 的 base（有无 /v1 均可）兼容。

- [2026-08-31] 合规类页面的「报告」区不能只做一行摘要索引。用户明确要求按 Open-Weight Model Assurance Standard §9 出完整审核报告：受评制品与版本、已复核证据、测试方法与结果、对比测试、重大发现与缓解、残余风险、条件/限制/例外、最终裁决，缺一不可，并要能导出。
- [2026-08-31] 报告装配器绝不能在没有门禁裁决时调用 `adjudicate()` —— 空 verdicts 会被判成「全通过」，报告会凭空给出批准结论。必须先用 `assessed = bool(app.verdicts)` 挡住。

- [2026-08-31] 生成交付型文档（报告、存证、可归档产物）时一律走 Blob 下载，不要 `window.open`：非用户手势触发的新窗口会被弹窗拦截，自动化环境里也拿不到 popup 事件。
- [2026-08-31] 自包含 HTML 交付物不得外链字体或任何 http 资源，必须用系统字体栈——离线评审、邮件转发与归档环境都会让外链降级。此约束要有测试兜底（断言产物中不含 http/script/link）。

- [2026-08-31] 让 LLM 参与合规评审时，"不影响判定"必须是结构性保证而非提示词约束：判定字段只从 GateVerdict 读，模型返回里的 result/verdict/severity 一律丢弃，并用测试锁死这条。
- [2026-08-31] 写进合规记录的 LLM 文本必须持久化 + 署名模型 + 带时间戳。标准 §5 要求过程可重复，每次打开报告都重新问模型会让同一份记录内容漂移。

- [2026-08-31] 排查 CSS 被覆盖时，不要只扫 `document.styleSheets` 就下结论——遍历写法很容易漏掉分组规则导致「查无此规则」的假象。可靠做法：改写目标规则的 style 看计算值跟不跟随，不跟随就说明胜出规则在别处。
- [2026-08-31] `taste-light.css` 用 `html.taste-light .btn`（特异度 0,2,1）定义浅色按钮。页面若把 `.btn` 做成深底实心按钮，必须用同特异度选择器夺回文字色，裸 `.btn` 一定输。
- [2026-08-31] 跨页跳转带参数时（如 `?model_id=`），接收页必须真的读 `location.search`。发起方带了参数不等于接收方用了，这类断链在 UI 上表现为「点过去什么都没发生」。
- [2026-08-31] 主操作按钮要放在用户视线所在处。把视图滚到表单却把启动按钮留在页头，等于没有按钮。

## Do-Not-Repeat

- [2026-07-17] 技能删除必须同时：team.skills + agent 绑定 + skill_store + registry + **萃取队列 approved 项** + skill_versions；否则 `_rehydrate_approved_skill` 启动复活。队列是 dict[item_id→item]，勿 `for item in q` 当 list。墓碑 `deleted_skill_keys` / `_skill_tombstones.json`。

- [2026-07-11] 给用户交付后端改动时必须显式说明『此改动在 XX:XX 落盘，需要在此之后的重启』；更好的做法已落地——start.sh 默认 uvicorn --reload，后端与前端一样热更（AG_NO_RELOAD=1 关闭）。连环后端修复期间不要让用户手动追重启。

- [2026-07-11] 代码代龄指标必须在进程启动时缓存（git rev + process_started_at）；请求时现查 git 报告的是磁盘 HEAD 不是进程代码——commit 后未重启会谎报新版本（bug-052 实锤误导了一轮排查）。判断'改了没生效'一律看 process_started_at 是否晚于最后一次代码落盘。

- [2026-07-11] 拆分前端模块时（如 tasks-view.js 从 agent-team-config.js 抽出），新文件引用的每个助手函数（hideViewLoading 等）必须确认在 utils.js/全局已定义；且同名函数导出 window 会覆盖旧文件的可用实现——列表『完全空白连占位行都没有』九成是 load 函数首行 ReferenceError（bug-044）。排查先看 console 而不是后端数据。

- [2026-07-11] 加密密钥库(.api_keys.json)必须合并式写入：teams.json 反序列化按设计丢明文 key，任何“按内存全集整体重写”的持久化都会在内存缺 key 的时机把磁盘 key 连锅端（bug-043，症状=重启后密钥全丢要求重输）。删除 key 只能走显式 delete_model_api_key。

- [2026-07-11] 页面新增 right-panel 类面板必须放进布局容器内与既有面板同级（rp-secs depth1）；放在容器闭合标签之后（depth0）时隐藏期无症状、显示后会把 3D 主视图挤出布局（bug-028）。交付前用 div 深度扫描校验。
- [2026-07-11] CodeBuddy 与 Fable 5 会并行改同一工作树：整文件 Write 重写前先 grep 最新内容确认无并行新增（本次覆盖了 CodeBuddy 的 on_step/cat_commentary/write_lineage，靠 todos 契约才复原）。优先 Edit 局部替换而非 Write 整写。

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-06-13] 执行沙箱无 fastapi/pytest 且 pip 被防火墙拦截（proxy 403），无法安装。所有"接口通路门"(2xx)类验收只能在本机 `rtk` 环境复跑，不要尝试在沙箱跑 test_v4_apis 等依赖 fastapi 的用例；可在沙箱跑的仅 `node --check` 与纯逻辑（但纯逻辑也需 pytest，沙箱同样缺）。
- [2026-06-13 更正上一条] Cowork 沙箱环境已变化：**pip 现可用**（pypi 在网络白名单内，`pip install fastapi pytest httpx` 成功）；**前端 vitest 也能在沙箱跑**——先 `npm i @rollup/rollup-linux-arm64-gnu @esbuild/linux-arm64` 补 linux 原生二进制（项目 node_modules 是 macOS arm64 装的），再从**项目根目录** `npx vitest run src/frontend/__tests__/xxx.test.js`（现有 system-evolution 3 用例全绿）。真正的硬限制是**网络白名单**：LLM 域名（api.deepseek.com、copilot.tencent.com/v2）DNS 解析直接失败、本机后端 8080、本机 5173 全部不可达。故依赖**真 LLM / 起后端 / 浏览器**的验收仍必须本机 `rtk`；纯代码/语法检查/前端单测可在沙箱完成。codebuddy 的 key 即使配在 app 里，沙箱也调不到该 LLM（域名不可达，非 key 问题）。
- [2026-06-13] 跨文档状态会滞后：本文件 v4 的 C-4.1/D-0.2 标 [~]，实际已由 frontendBigChangeTodos F3/F4 完成。核对 todos 时必须跨 5 份文档交叉比对（全局优化 / 数字孪生v3.1 / 场景演练v4 / AgentsGroupConfig / frontendBigChange），避免误报未完成。
- [2026-06-17] 弹窗"点击只出遮罩、内容不显示"几乎都是 CSS 级联污染：页面把 `.modal` 当弹窗内容面板用，同时链入全局 `css/components.css`（其中 `.modal{display:none}`）。页面局部 `.modal` 若不声明 display，全局 display:none 按属性级联胜出 → 面板被隐藏。修法固定：在该页局部 `.modal` 规则加 `display:block`（单处）。已发生于 plaza.html 与 agent-team-config.css。**不要**误诊为 JS/ID 编码问题去改逻辑。排查命令：浏览器对 overlay 与 `.modal` 取 getComputedStyle，看 panel display 是否 none。
- [2026-06-17] 前端文件若用 IIFE 封装且模板内使用 inline onclick，必须把每个 onclick 引用函数显式挂到 window。仅在文件内定义函数不等于全局可见；漏导出会在点击时报 `ReferenceError: <fn> is not defined`（本次为 wizard.js 的 addExp）。
- [2026-06-17] 本机重启服务验证时必须用项目 `./start.sh`（会进入项目 virtualenv 并带齐 aiohttp 等依赖）。直接 `python3 src/backend/main.py` 可能使用系统解释器，导致会话聊天接口报 `ModuleNotFoundError: aiohttp` 假性回归，干扰真实问题定位。
- [2026-06-17] 智能体详情「技能」行操作不要把“删除”放进绑定状态分支里。删除是行级通用操作（无论当前是绑定还是未绑定都应可见）；仅“绑定/解绑”按钮按 isBound 切换，避免出现只有“绑定”但没有“删除”的页面回归。
- [2026-06-17] inline onclick 传参不能用 HTML 转义值（如 `escapeHtml(skill_id)`）直接当业务 ID；`&amp;` 等实体会导致后端删除/更新命中失败。参数应 `encodeURIComponent` 传递，在处理函数内 `decodeURIComponent` 还原，并在 URL path 段再次 `encodeURIComponent`。
- [2026-06-18] skill-extract 去重不能只看 source_text 前缀（如前 2000 字）且不能丢失来源上下文；不同讨论常有模板化前缀，会发生跨议题误判“已萃取过”。应使用来源签名（source_plaza_id/source_discussion_id/source_output_id）+ 全文哈希，至少要比对全文哈希而非前缀。
- [2026-06-18] 队列删除语义不能只删除当前项；若希望“删除后不再自动出现”，必须写 tombstone（来源指纹）并在 start_extraction 前拦截。否则同来源再次触发会复活，造成“删了又出现”。
- [2026-06-18] LLM 不可用时不能用固定兜底技能模板（同一组 ES/Terraform/成本等）；这会让不同议题看起来都萃取成“其他议题”。兜底也要绑定 source_title/source_text 动态生成，至少名称需体现当前议题关键词。
- [2026-06-18] skill-extract 队列 UI 不能无条件展示团队全部历史项；从议事厅跳转场景必须按 source_meta(plaza/discussion/output)做来源隔离，否则用户会把历史项误认为“当前萃取结果”。
- [2026-06-18] skill-extract 详情弹窗里“按钮没展示出来”优先排查 CSS 布局裁切（tab 条/usage 头部动作区的 flex 单行挤压），不要先怀疑 JS 显隐。先查元素是否在 DOM 中且无 `display:none`，再修为 `flex-wrap`/`overflow-x:auto` 并给动作区在窄宽度下换行。


- [2026-07-14] 演化加压第二层：predator_bias_unskilled（捕食加权无 skill）、scarce_share_boost（稀缺分享溢价）、same_pop_share_bias（同队分享）；LOOP 判定排除 abundant 负对照；mixed 出 dominant=Skill 可进化信号，对抗 collab≥15%=团队演化信号。ECO_LOOP_SKIP_LLM=1 可加速闭环脚本。
## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- 任务执行支持两种模式(execution_mode)：linear=原线性 Claude 流水线(默认)；collaborative=智能体广场多轮讨论(`_start_task_collaboration`→plaza create_plaza/add_participant/create_discussion/run_discussion→共识→回写 task.metadata.collaboration+artifacts→_finalize_task_terminal_state)。广场用 set_chat_fn(harness.chat) 即系统配置 LLM。批量/队列路径(_real_task_executor)暂仍线性。

- [用户校准 2026-07-04] 两阶段经济学铁律: Plaza集体智慧阶段绝不做token优化/预算约束/效能计量(智慧无价,只求不跑题+计划落地); 成本纪律从执行计划产生后开始; 数字孪生的意义=对同一计划做团队×技能×协作的候选组合竞标,质量达标中选token效益最优者执行。任何成本优化建议不得触碰讨论阶段。
- [用户原则 2026-07-04] 考察智能体之间的协作能力必须在 Agents 数字孪生场景下完成——孪生3D不是装饰,是协作的观测仪器(协作光线/热度统计/镜像层)。

- [2026-07-13] 物竞 v4：步数/生态位由 ExecutionPlan→TaskHabitatContract 驱动；skill 身份归一；mixed 接 run_eras；集成默认 suggest_only。
- [2026-07-13] infer_skills 时 empty role 不可 `\"\" in key`（会匹配全部角色映射）。

- [2026-07-13] 物竞赛制用户校准：①分场=多队Agent比个体skill（同一任务环境）；②多队对抗=协作+策略；③混合=个体+团队。加对比种群不得自动改赛制。

- [2026-07-13] 物竞赛制世界杯隐喻：①分场=各队球星(Agent)skill评比；②多队对抗=球队协作与策略；③混合=世界杯(球星+协作)。客观环境=奖杯只有一座/同一任务过滤，不是天选任务。加对比种群不自动改赛制。

- [2026-07-14] 存活唯一适应度=survival_ticks；T_i 分解（skill/协作/残差）只可解释不另评分。对比种群任务选择=Apple-to-apple 共用考卷，非天选。EcoDrill 需求池字段是 env.demanded_skills（不是 _demanded）。
- [2026-07-14] LLM 演练分析提示词在 eco_runtime_config.llm_analysis（pet-config 可编辑）；演化加压=skill_idle_penalty + prefer_forage_when_can_serve + 契约 min_steps/gens；一键预设 applyEvolutionPressurePreset。

- [2026-07-14] 通道绑定已落地为可编辑+persist+运行时门禁（agent_channel_bus）；空绑定 legacy 放行，有绑定则 enforce publish/subscribe。物竞写回走 channel-integration。

- [2026-07-14] 关系边物竞写回已落地：`relation_integration` suggest→confirm apply → RelationshipStore（created_by=human_via_eco_feedback）；mate/COURT 不映射。团队配置「关系」tab 读 agent-employee Relationships（真边）+ 通道绑定；深链 `?team_id&view=agent&atab=ag-relations`。
- [2026-07-14] AWS运维「关系」用户记忆多半=同队 peer API 假边 或 aws_ops_bus 通道共总线；RelationshipStore 实际为空。Before 图须叠 channel soft 层，勿只读 store。
- [2026-07-14] 任务执行必须走协作拓扑：check_can_communicate=门禁边|同队peer|共总线；delegate/send_message/workflow handoff 接 gate；step prompt 注入拓扑。hard=enforce_relationship_gate。
- [2026-07-14] 适者反馈验收入口：scripts/verify_eco_feedback_xf.py（静态+离线+活后端）。通道写回必须 resolve_team_bus 优先真身 channel_name。
- [2026-07-14] XF-5 决策：任务型考卷可视化=2D HUD（3D 窗右上）+右侧步骤 chips；仅挂接契约时开；禁止蓝柱图腾；旧 __ECO_HABITAT_3D__ 默认关。
- [2026-07-14] 物竞×成本：先适者后省钱。BidCandidate 存 storage/eco_bid_candidates；Q1 task+Q2 feedback 硬门；推送 ecoFeedbackPushBid；cost 页列表/填 token/lock。生产读 locked=XC-4.4 后续。
- [2026-07-14] XC-4.4：任务 submit/_submit_internal/batch 自动 apply_locked_config_to_task（metadata.required_skills+champion agent）；不静默改 agent.skills 真身；skip_locked_bid 可关。
- [2026-07-14] locked BidCandidate：SkillRouter.assign 静默写 agent.skills（lock 时绑适者 + 任务提交再幂等）；skip_locked_skill_bind 可关；失败不挡 lock/submit。
- [2026-07-14] XF+XC 统一验收：`scripts/verify_eco_feedback_xf.py` 含静态+离线+活后端 BidCandidate（create→PATCH→quality→lock 拒绝/成功→GET production）；离线用 tempfile 不碰真存储；live 用 `task_xc_verify_live` + 空 dominant_skills 避免 SkillRouter 写真身。PASS≈51。
- [2026-07-14] cost-dashboard 与物竞结合：`#eco-hub` **始终可见**（不依赖 deep-link）；团队下拉默认 aws-ops 拉 BidCandidate + production locked；旧达尔文棘轮标「副轴」。孪生顶栏「物竞×成本」+ 步骤 ④ `ecoGoCostStep` 双向深链。
- [2026-07-15] 用户校正：cost 页主题=**任务 Token 治理**（非物竞主轴）。全链序号固定 1团队→2议事→3寻技能→4物竞→**5 Token治理**→6生产注入。物竞 BidCandidate 用 `<details>` **默认折叠**。主轴四能力：计量(by_task) / 缓存+压缩(prompt_cache) / ModelRouter / BudgetGuard+verify。API 前缀 `/api/v1/cost/token-governance/*`。chat_harness 默认 compress（`AG_PROMPT_COMPRESS=0` 关）。
- [2026-07-15] 任务 token 归因：contextvar 不跨线程 → 用 `AG_TASK_ID`/`AG_TEAM_ID` + session 字段；tool_loop 与直连 API 写 `phase=task`+`scenario_id=task_id`。`submit_task` 预算 halt 返回 402（`metadata.skip_token_budget` 跳过）。历史 unscoped 大盘不回写，只告警。
