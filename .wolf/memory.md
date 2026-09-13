# Memory

> Chronological action log. Hooks and AI append to this file automatically.
> Old sessions are consolidated by the daemon weekly.

- 2026-08-28T04:00:00Z | 全量落地论文对齐 P0-P2 全部 10 项机制（补齐 50 项测试，100% 验证通过） | src/backend/agents/*, src/backend/sandbox/*, src/backend/tests/*, docs/论文对齐todos.md, .wolf/* | P0-1(六门统一裁决 skill_gates.py + G_e 溯源熵), P0-2(版本竞争 version_competition.py + Student-t LCB + Cornish-Fisher), P0-3(任务界定适应度 task_bounded_fitness.py + 6因子归一化), P0-4(记忆污染筛查 memory_contamination.py + 恶意隔离), P1-5(生命周期六态 models.py + 2-of-3 去抖 skill_classifier.py), P1-6(路由硬过滤与字符 n-gram skill_router.py), P1-7(SWEI 导入五道具名门 agent_memory_migration.py), P2-8(CHALLENGE 议程路由 plaza_challenge_routing.py), P2-9(生态证据回流 eco_feedback.py), P2-10(DART-Net 门面 dartnet.py + 12-Niche 三环 plaza.py + 共识公式 plaza_consensus.py)。修复 Windows 缺 fcntl 兼容问题。全套 9 个测试套件 50 项测试全绿，npm run lint 编译检查通过 | ~12k |
- 2026-08-28T02:30:00Z | 落地论文对齐 P2-8 CHALLENGE 议程路由 + P2-9 生态证据回流 | src/backend/agents/plaza_challenge_routing.py(新), plaza_engine.py, src/backend/sandbox/eco_feedback.py(新), eco_drill.py, src/backend/tests/test_paper_p2_routing_feedback.py(新), docs/论文对齐todos.md, .wolf/buglog.json | P2-8: `_run_orid_phases` 由 4 次顺序硬调用改为带回跳状态机，Γ_k 双重防死循环（同(from,target)对 ≤2 次 + MAX_PHASE_RUNS=10 硬上限），环复用既有 SeatTier 而非新建枚举；P2-9: 字段名按真实产物修正（final_ranking[].survival_ticks/skill_genome、gene_pool.deprecated、integration.missing_plan_skills，而非伪代码里的 agents[].survival_time/failures），落盘路径做穿越消毒，Plaza O 阶段 prompt 注入。新测试 17/17 绿；plaza/eco 相关既有测试 278/278 绿；全量 21 failed 经 git stash 基线比对确认为既有失败（与改动无关）；3 个收集错误为 Windows 缺 fcntl 的既有问题 | ~6k |
- 2026-08-26T01:10:00Z | 深入阅读全仓代码，全面重写并优化项目 README.md | README.md, .wolf/* | 修正技术栈规模数据（389 后端文件/12.4万行 Python，19个前端页面，218个测试套件，31个路由域）；系统化梳理九大业务域、19个页面矩阵、TwinLoop/TSE/EcoDrill/TokenPrepare/拟生记忆/Ratchet/准入治理七大核心机制及权威设计文档导航 | ~3k |
- 2026-08-21T00:25:00Z | 团队与定时任务配置入库并修复空安全缺陷 | storage/teams/teams.json, src/frontend/*, .gitignore, .wolf/* | 开放权重资源团队纳入 teams.json 并在 .gitignore 显式放行；修复 loadSchedules 与 createSchedule 在网络或 401 场景下直接访问 null 对象的崩溃；data-intelligence 补全各下拉中的开放权重选项；提交 commit 194480b | ~2k |
- 2026-08-20T03:15:00Z | 修复 ai-model-entry-clearance.js 尾部重复代码导致的 Vite 语法解析错误 | src/frontend/js/ai-model-entry-clearance.js, .wolf/buglog.json | 清理 IIFE 闭包后的多余重复代码；node --check 与 28 项前端单元测试通过 | ~1k |
- 2026-08-20T03:05:00Z | 完成 P10（TA01–TA09）控制台与准入引擎真实对接与全面验证 | src/frontend/*, src/backend/domain/api_routes.py, TODOS.md, .wolf/* | 表单字段与校验正则全面正名（model_id / revision / as_of / target_qpm 等）；彻底断开并删除遗留 investment_simulation 目录与路由；启动/轮询/会签全面直连 /api/v1/model-clearance/applications 与 submit；门禁矩阵吃真实 GateVerdict 与 evidence；新增 clearance-cockpit-wiring.test.js，全套 12 后端测试、Phase 1 出口验证与 28 项前端单元测试 100% 通过 | ~4k |
- 2026-08-20T02:10:00Z | 核实控制台仍连旧模拟引擎并写入 P10 计划 | PLAN.md, TODOS.md, .wolf/anatomy.md | 核实三处硬证据：(1) engine-state.js 的 `^[A-Za-z0-9.]{1,12}$` 拒绝页面自己的默认值 meta-llama/Llama-3.1-8B-Instruct，故必弹「请填写合法 Ticker」；(2) 控制台 create/start/poll/restore 仍打 /api/v1/investment-simulations；(3) 其 orchestrator import 的 integrations.tradingagents.graph_adapter 在仓库中不存在，链路事实上是死的。PLAN 增 §11 断点表与目标形态，TODOS 增 P10 TA01–TA09 | ~3k |
- 2026-08-20T00:15:00Z | 落地 P9 全部 10 项 Lenovo 直管与运营控制能力 | config/clearance_policy.yaml, src/backend/domain/model_clearance/*, src/frontend/*, scripts/*, tests/*, TODOS.md | 策略降来源依赖(origin_signal_only)；清单责任矩阵字段(owner/SLA/refs/audit)；API 增加 Kill-Switch 与 Rollback 双闸；新增每周抽样审计脚本；新增 P9 单测与 Phase 1 控管优先出口脚本；全套 12 测试与前端单测 100% 绿 | ~4k |
- 2026-08-20T00:00:00Z | PLAN/TODOS 战略改写：来源降权，Lenovo 直管优先 | PLAN.md, TODOS.md, .wolf/cerebrum.md, .wolf/anatomy.md | 将准入逻辑从“模型来自哪里”转为“Lenovo 可直接管理和验证”：新增控管优先原则、P9 运营补强任务（owner/kill-switch/rollback/SLA）、更新 Phase 1 出口条件并去除 TODOS 重复验收段 | ~2k |

- 2026-08-15T07:55:00Z | 议事广场国际化并修复页面无限加载 | src/frontend/plaza.html, src/frontend/js/plaza.js | 接入共享 i18n 与顶部语言切换；补广场静态/动态中英词条；修复 MutationObserver 调 applyAll 后因语言按钮 textContent 重写而自触发的主线程无限循环。node --check、编辑器诊断、Vite 资源 200、浏览器 401 自动跳登录页均通过 | ~3k |

| 08:45 | 审计任务页面 Build System/AWS Ops 流程并产出专用 plan/todos | docs/任务页面Build与AWS运维流程优化plan.md, docs/任务页面Build与AWS运维流程优化todos.md | 确认 AWS 中文 role 未映射到 workflow、execution_mode 未进请求模型、启动失败不回滚、独立 tasks.html 未兼容分页；后端基线因 .venv 缺 pytest 未执行 | ~4k |

- 2026-07-05T02:11:00Z | 撤销猫按有效技能跳桌逻辑(用户要求) | src/frontend/js/office/office-scene.js, office-state.js, office-boot.js, __tests__/office-state.test.js | 移除 skills/effectiveSkillCount 透传+跳桌+阈值+相关单测; 保留最近Agent转身+光圈吸引; office-state 13/13, node --check, build 通过 | ~1k |

- 2026-07-05T01:55:00Z | 设计并落地撸猫过程 | src/frontend/js/office/office-scene.js | 动画层新增 nearestCatLure(): 最近的非递文件 Agent 转身面向猫, 脚下 glowRing 按正弦脉冲闪烁/放大吸引猫; 其他 Agent 光圈复位。node --check、office-state 13/13、vite build 通过 | ~1k |
- 2026-07-05T02:01:00Z | 猫按有效技能数判断并跳上桌 | src/frontend/js/office/office-state.js, office-boot.js, office-scene.js, src/frontend/__tests__/office-state.test.js | roster 透传 skills/effectiveSkillCount; OfficeState 保存/估算有效技能数; 最近 Agent 有效 skill >=3 时光圈增强, 猫跳到该 Agent 桌面停留; office-state 15/15、node --check、vite build 通过 | ~2k |
- 2026-07-04T09:30:00Z | 修复 office3d Agent 造型跑偏 | src/frontend/js/office/office-scene.js | 按用户校准，Agent-digital-twin.html?office3d=1 的 Agent 从胶囊/球头/尖耳站桩改为复用 plaza 头环+U形身体+地面光环模型语言；动画改 bobRoot，避免依赖旧 child[0]；office-state 9/9、node --check、vite build 通过 | ~1k |
- 2026-06-12T14:48:00Z | G1-2 完成收口：在 skill_extractor.approve_item 接入 ClassificationStore.seed_reserve_from_extraction（幂等），实现“萃取完成即写入 reserve 分类记录”；新增 tests/test_skill_classifier.py::test_seed_reserve_from_extraction_idempotent，pytest 14 passed。
- 2026-06-12T14:58:00Z | G3-2 本机联测收口：trial_api 增加 routing_comparison/routing_benefit 输出，branches 列表暴露 routing_strategy；新增 tests/test_v4_apis.py::test_routing_strategy_fork_comparison；pytest tests/test_v4_apis.py 14 passed。
| 04:36 | 核对5份todos+排查协作图空白(已修复) | docs/Agent数字孪生场景演练与技能进化todos.md | C-4.1/D-0.2核销为[x]+新增G分派章节(Claude/Reasonix) | ~3k |
| 04:59 | 新增本机验收脚本(rtk pytest+全绿回写[~]→[x]) | scripts/verify_v4_local.sh | 覆盖test_v4_apis/secs/full_flow/move,排除真LLM项 | ~1k |
| 05:07 | verify脚本加--with-server(E-5活后端脚本跑法) | scripts/verify_v4_local.sh | test_full_flow非pytest需脚本式跑8080,secs+flow全绿才回写E-5 | ~0.6k |
| 05:40 | 修复system-evolution实时更新链路(P0) | src/frontend/js/system-evolution.js + src/backend/agent_team_api.py | 后端补GET /evolution/stream(SSE,只读快照,不改引擎)+前端onerror轮询降级修复;node --check+py_compile+vitest(3 passed)通过;真实SSE需本机rtk验;记buglog bug-002 | ~3k |
| 05:42 | 产出system-evolution优化plan+事无巨细todos(Claude/Reasonix分派,Reasonix多领) | docs/system-evolution优化plan.md, docs/system-evolution优化todos.md | 现状=已v2优化;头号缺陷=SSE实时更新整条死;cerebrum更正沙箱pip/vitest现可用但LLM域名+8080+5173不可达 | ~2k |
| 06:10 | 产出plaza优化plan+带伪代码todos(前后端,Reasonix多领) | docs/plaza优化plan.md, docs/plaza优化todos.md | 真实缺陷:SSE无onerror/无重连(后端全量重放需配重连去重)、Three.js不dispose致GPU泄漏、live消息esc vs 重载mdLite不一致、隐藏页仍渲染、confirm阻塞、escalation按index脆弱、SSE可加Last-Event-ID断点续传 | ~3k |
| 14:15 | 落地plaza Claude项(A-1/A-2/B-1/C-1) | src/frontend/js/plaza.js | SSE加onerror+指数退避重连+teardownSSE统一收口;_seenMsgKeys去重(去掉init门控,改去重既不重复又补断线期消息);disposeObject3D/disposeSceneAgents释放GPU;live分支esc→mdLite;beforeunload清理。7个plaza vitest全绿。F-2核对:escalation无稳定id需引擎改造(留本机) | ~3k |
| 06:30 | skill-extract调研+plan/todos+技能闭环实现 | docs/skill-extract优化plan.md, docs/skill-extract优化todos.md, storage/skills/c0de7a11.json, scripts/skill_closed_loop_demo.py, README.md | 现状最成熟(SSE重连/dispose/CSRF已健全);头号bug=HTML 10个重复id致第二复核UI错位;旗舰=设计"结构化代码评审"skill并在沙箱真跑闭环:twin_loop success_p=clamp(0.3+0.6*prof);code_review_delivery场景baseline 0.45 vs treatment 0.85,30种子,code_review成功率72.1%→90.4%(+18.3pp);README加"技能闭环演示"章节 | ~5k |
| 16:05 | 修复skill-extract P0重复id | src/frontend/skill-extract.html, src/frontend/js/skill-extract.js | block2快速确认面板10个重复id加-pipe后缀;JS新增_eachGateEl显示同时更新两套门禁UI,toggleReviewForm(scope)/submitReviewAction(action,scope)按''/'pipe'作用域读写;终检无重复id;vitest 5用例全绿;闭环demo exit=0。C-1 request_id已由Reasonix做 | ~2k |
| 16:40 | 本机真后端闭环脚本+模拟按钮改赋予注入(plan/todos) | scripts/skill_closed_loop_live.py, docs/skill-extract优化todos.md(S-5), docs/skill-extract优化plan.md(4.6) | 挖出真实缺口:skill_router.assign()只append agent.skills不写proficiency_store→UI赋予不抬升孪生熟练度,闭环UI这环断;S-5方案:⚡模拟→⚡赋予/注入真动作+assign按metadata.target_skill抬proficiency≥0.8返回proficiency_boosted;live脚本打8080试炼API设0.45/0.85对照离线+18.3pp,py_compile通过 | ~2k |
| 22:45 | 恢复误删build_system团队+硬化批量删团队 | storage/teams/teams.json(+bak), src/frontend/js/agent-team-config.js | 用种子create_build_team().to_dict()重建build_system(7 agent/2模型,与现有团队同schema)写回teams.json,先备份teams.json.bak.*;需用户重启后端加载。删除bug根因:agent-team-config与tasks-view同页共享隐式全局tid,批量删除用裸fetch+手动csrf且删后AG.state/loadView可能不刷新→"无效"。重写deleteSelectedTeams:只认勾选id、循环变量改名解耦tid、改用统一api()鉴权、404视为成功、finally必loadTeams刷新。node--check+team-unified 8/8+config 4/4全绿 | ~2k |
| 16:30 | 落地C-1.2(进化拒绝结构化原因前端) | src/frontend/js/digital-twin/v4-evolution.js | _evoErrCN(code,detail)升级:no_weak_skills_identified追加后端error_detail(扫描N试炼/usage M条/无数据or都达标);两处rejected/failed渲染统一传run.error_detail+_dtLogConsole。node--check+5 vitest绿。试炼页Claude项全done(A-1.1/B-1 Reasonix做、A-2/C-1/D-1 我做、C-2.1/C-2模型字段 Reasonix);剩C-2.2真LLM/D-2/D-3打磨/E-1留本机或Reasonix | ~1k |
| 12:10 | 落地试炼页Claude项(A-2/B-1/C-1/D-1) | src/backend/sandbox/trial_api.py, src/frontend/js/digital-twin/secs-core.js, v4-evolution.js, docs/试炼页优化todos.md | A-2.2 evaluate响应加meaningful+note(有场景且task>0.01);A-2.1/D-1 secs-core控制台无场景标"基线分"+task≈0警告;C-1 v4-evolution加_evoErrCN中文映射(no_weak_skills_identified→可操作引导)两处rejected渲染+console。node--check(secs-core/v4-evolution)+vitest 14/14;trial_api改动语法OK(py_compile仅卡既有3.12多行f-string,沙箱py3.10所致)。未做:A-1.1启动确认弹窗/C-2.1后端结构化原因(模型改动风险)/C-1.2链路UI失败态,留本机 | ~2.5k |
| 2026-06-15 | 任务执行防卡死+协作前端(T1.1/T4.2/T2.1/T3.1/T3.2/T5.5) | src/backend/agents/api.py, src/frontend/js/tasks-view.js, src/frontend/agent-team-config.html, docs/任务执行协作化plan与todos.md | T1.1:_STEP_WALL_TIMEOUT_SEC=1200墙钟超时(monitor running分支,stall检测前,超时kill proc→failed→复用重试逻辑);T4.2:_run()顶部无LLM配置fail-fast(no_llm_configured);T2.1:_reconcile_orphan_tasks()启动对账(无monitor无活session或超_TASK_MAX_RUN_SEC=10800→failed orphaned);T3.1:_annotate_stuck补current_step/last_activity_sec;T5.5:HTML加tk-exec-mode选择器+JS提交带execution_mode+协作badge;T3.2:retryStep/skipStep按钮(复用现有endpoint)。py_compile+node--check全绿 | ~4k |
| 11:30 | 本机验收脚本+试炼页plan/todos | scripts/local_acceptance.sh(新), docs/试炼页优化plan.md(新), docs/试炼页优化todos.md(新) | local_acceptance.sh汇总本机验证(vitest/py_compile/闭环demo/--with-server跑pytest+SSE+live闭环+浏览器清单),沙箱离线7PASS/0FAIL/3SKIP。试炼页两根因:无场景空跑(_generate_default_tasks→reward≈0,0.315是其它维度基线分,误导)+ no_weak_skills_identified(identify_weak_skills无usage即拒,UI不可操作)。plan/todos出P0无场景校验+评分语义标注、P1五维breakdown+进化拒绝中文可操作、P2可读性,带伪代码+Claude/Reasonix分派 | ~3k |
| 10:52 | L4接入补齐三页(实时跟随) | src/frontend/js/agent-team-config.js, system-evolution.js, docs/联动优化todos.md | Reasonix已给三页接入AGCtx(include+set+init-read);我补缺口=实时跟随AGCtx.on订阅:agent-team-config(下拉同步+loadView)、system-evolution(ev-team-select同步+loadEvolveSkills,防重复订阅);plaza无页面级团队选择器仅作基座引入。node--check全过+25 vitest全绿。跨页实时跟随浏览器验证留本机 | ~1.5k |
| 10:05 | T1任务卡死只读标注+L4推广skill-extract | src/backend/agents/api.py, src/frontend/skill-extract.html, src/frontend/js/skill-extract.js, docs/任务执行优化todos.md, docs/联动优化todos.md | T1安全部分:advance_workflow给next_step打started_at;list/detail端点加只读_annotate_stuck(elapsed_sec/stuck/threshold,running超1800s标stuck,不改状态)。L4.2:skill-extract引入ag-context.js+selectTeamChip上报AGCtx.set。py_compile+node--check+vitest 8/8。自动失败(T1.1状态改动)留本机 | ~2k |
| 06:10 | L4 AGCtx总线+聊天乐观渲染+任务卡死分析 | src/frontend/js/ag-context.js(新), __tests__/ag-context.test.js(新), Agent-digital-twin.html, digital-twin-cli.js, agent-detail.js, docs/任务执行优化todos.md(新) | L4.1总线落地(get/set/on+localStorage ag_ctx_*跨页+storage静默入站去重防循环;team双写兼容ag_current_team);数字孪生页接入(dtSetCurrentTeam→AGCtx.set+on订阅fromCtx防循环);ag-context单测4/4+合计22 vitest全绿。聊天sendChatMsg加乐观渲染(立即插用户气泡+正在思考占位,修"像没发出"问题)。任务卡死根因:每步真起Claude会话靠monitor推进、无超时→LLM不可达即无限running,出T1-T4优化todos | ~4k |
| 01:20 | 联动审计+plan/todos+数字孪生左右联动落地 | docs/联动优化plan.md, docs/联动优化todos.md, src/frontend/js/digital-twin/secs-core.js, src/frontend/js/digital-twin-cli.js | 根因:同一"当前团队"被三套状态各自持有(S.selectedTeams左多选/_selectedTeamId右SECS/localStorage selected_team)+跨页不共享;SECS→左早已联动但左→SECS缺失;L0已落地:secsSyncTeamFromLeft+secsSyncSceneFromRoom单向setter,toggleTeam/switchRoom/showRoom调用,room_<id>场景映射;node--check+数字孪生vitest 16/16;待做L1(三套统一)/L2(跨页ag_current_team)/L4(AGCtx总线) | ~3k |
| 01:00 | S-6.1 赋予/注入改必须显式勾选 | src/frontend/js/skill-extract.js, docs/skill-extract优化todos.md(S-6) | 实测发现左右栏联动(共享routerResults/routerSelectedSkills/selectedAgentId)但赋予/注入未勾选时盲选Top-K塞松匹配技能;改为仅注入显式勾选项,未选则提示+Toast不自动注入;todos加S-6(多需求支持/雷达文案澄清待做);vitest 4/4 | ~1k |
| 00:45 | 落地S-5.1/5.2/5.3代码 | src/frontend/skill-extract.html, src/frontend/js/skill-extract.js, src/backend/agents/skill_router.py | 前端:按钮⚡模拟→⚡赋予/注入(_executeInjectSkills:选中直接赋予/未选则路由→自动选TopK→赋予),注入成功提示proficiency_boosted+计数;后端:assign()加_resolve_target_skill+_boost_proficiency抬proficiency≥0.8返回proficiency_boosted(try/except容错)。py_compile OK,vitest 5/5,无重复id。真效果本机用skill_closed_loop_live.py验 | ~2k |
| 00:18 | designqc: captured 2 screenshots (38KB, ~5000 tok) | / | ready for eval | ~0 |
| 00:18 | designqc: captured 2 screenshots (38KB, ~5000 tok) | /system-evolution.html,/plaza.html,/Agent-digital-twin.html,/skill-extract.html,/cost-dashboard.html,/sandbox-twin.html,/agent-team-config.html | ready for eval | ~0 |
| 00:19 | designqc: captured 2 screenshots (38KB, ~5000 tok) | /system-evolution.html | ready for eval | ~0 |
| 00:19 | designqc: captured 2 screenshots (38KB, ~5000 tok) | /plaza.html | ready for eval | ~0 |
| 00:19 | designqc: captured 2 screenshots (38KB, ~5000 tok) | /Agent-digital-twin.html | ready for eval | ~0 |
| 00:19 | designqc: captured 2 screenshots (62KB, ~5000 tok) | /skill-extract.html | ready for eval | ~0 |
| 00:19 | designqc: captured 6 screenshots (181KB, ~15000 tok) | /cost-dashboard.html | ready for eval | ~0 |
| 00:20 | designqc: captured 6 screenshots (218KB, ~15000 tok) | /sandbox-twin.html | ready for eval | ~0 |
| 00:20 | designqc: captured 2 screenshots (38KB, ~5000 tok) | /agent-team-config.html | ready for eval | ~0 |
| 09:54 | designqc: captured 2 screenshots (38KB, ~5000 tok) | /system-evolution.html | ready for eval | ~0 |

## Session: 2026-06-14 23:25

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-06-14 23:31

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-06-14 23:32

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-06-14 23:42

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-06-14 06:26

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-06-14 06:26

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 03:45 | 任务执行LLM改读系统配置(根因修复) | src/backend/agents/api.py · docs/任务执行优化todos.md | _harness_provider_credentials+优先harness;T4.1→[~]待本机 | ~2k |
| 05:48 | 任务新增协作模式(广场驱动,与线性并存) | src/backend/agents/api.py · docs/任务执行优化todos.md | _start_task_collaboration+execution_mode开关;plaza多轮讨论→共识→回写任务;py_compile通过 | ~3k |
| 05:56 | 落自包含规划+伪代码todos(任务协作化+防卡死) | docs/任务执行协作化plan与todos.md | 含落点/行锚/伪代码/验收/回滚,不打工具标签可被任意工具接续 | ~3k |
| 16:05 | skill-extract 批准入库静默失败修复+重登验证 | src/frontend/js/skill-extract.js · .wolf/buglog.json | approveAs 失败弹明确提示;浏览器重登后 approve HTTP200 ready→approved | ~4k |
| 16:06 | awsOps 两个非LLM待优化项修复 | src/frontend/js/skill-extract.js · docs/awsOpsE2ETestPlanTodos.md | renderRouterResults 按skill_id去重+版本徽章;init加_ensureAuthOrRedirect认证门禁;vitest 171 passed | ~3k |
| 16:08 | awsOps E2E复跑+标注 | docs/awsOpsE2ETestPlanTodos.md · docs/reports/aws-ops-e2e-report.* | PASS=8/FAIL=5,FAIL全为DeepSeek key无效(secret,需用户填)根因 | ~2k |
| 06:28 | 修复技能页LLM路由与版本创建耦合问题 | src/backend/agents/api.py, chat_harness.py, skill_evolver.py, skill_verifier.py, src/frontend/js/skill-extract.js, src/frontend/skill-extract.html | 演化/验证按team默认模型路由(config_override)+api_base_url统一strip；效果页新增“展示对比”按钮；版本创建改走/version/snapshot脱离LLM依赖；后端健康恢复 | ~3k |
| 16:32 | 修复plaza控制台CSP/Three废弃警告 | src/frontend/plaza.html, src/frontend/js/plaza.js, .wolf/buglog.json | connect-src放行ga.jspm.io sourcemap；Clock→performance.now；PCFSoftShadowMap→PCFShadowMap；plaza vitest 10/10 + node --check 通过 | ~1k |
| 17:18 | 修复删除叉触发灰屏与data:audio CSP噪音 | src/frontend/plaza.html, src/frontend/js/plaza.js, .wolf/buglog.json | 移除unlockAudio data:audio播放；CSP增media-src；新增静态m-confirm并修正overlay关闭守卫；plaza vitest 10/10 + node --check通过 | ~1.5k |
| 18:51 | 修复数字孪生页运行时无限连接中 | src/frontend/js/digital-twin/secs-core.js, .wolf/buglog.json | runtime bootstrap 从 load 前移到 DOMContentLoaded；runtime-status 加4s超时，避免永远转圈；digital-twin vitest 10/10 + node --check通过 | ~1.5k |
| 18:52 | 移除数字孪生页失效 Lucide 样式依赖 | src/frontend/Agent-digital-twin.html, .wolf/buglog.json | 外链 lucide.min.css 返回404且页面未使用；删除引用，rg 无残留；digital-twin vitest 10/10 通过 | ~0.8k |
| 2026-06-17 | 修复模型与连接页 CodeBuddy 编辑不弹窗 | src/frontend/js/agent-team-config.js, .wolf/buglog.json | loadModels 的 inline onclick 改为传 URL 编码 model_id；openEditModel/delModel/setModelDefault 统一解码；编辑前查找模型增加 trim 兜底与 cache fallback，恢复 CodeBuddy 编辑弹窗 | ~1k |
| 19:22 | 修复智能体技能删除不生效 | src/frontend/js/agent-detail.js, .wolf/buglog.json | 删除按钮参数改为 encodeURIComponent 传递，deleteSkillWithContext 内 decode；DELETE 路径段也 encode，修复特殊字符 ID 删除失败；node --check + get_errors 通过 | ~1k |
| 18:25 | 修复智能体详情可读性与会话LLM回退 | src/frontend/js/agent-detail.js, src/backend/agents/api.py, src/backend/agents/chat_harness.py | 人格页技能ID→名称映射、关系页优先name；会话聊天针对CodeBuddy跳过tools并加11133参数错误降级重试，浏览器实测 send_session_message 返回 assistant=“连接正常” 非 fallback | ~4k |
| 19:05 | 修复智能体技能页缺少删除入口 | src/frontend/js/agent-detail.js, .wolf/buglog.json | 智能体详情→技能列表将“删除技能”按钮从仅已绑定可见改为所有技能行可见；已绑定仍保留“解绑”，未绑定保留“绑定”；node --check + get_errors 通过 | ~0.8k |

## 2026-06-17 — fix: agent-team-config 编辑弹窗不显示
- 根因: 全局 components.css `.modal{display:none}` 污染本页用作内容面板的 `.modal`（局部未声明 display），属性级联致面板隐藏，仅遮罩可见。
- 修复: src/frontend/css/agent-team-config.css 局部 `.modal` 加 `display:block`（单处）。
- 还原: 之前误诊的 agent-team-config.js encode/decode 改动已 git checkout 还原。
- 验证: 浏览器复现 openEditModel(qwen3) → panelDisplay block、面板 456x257 可见、编辑表单完整渲染。

## 2026-06-17 — fix: 向导专长领域 addExp 未定义
- 现象: 新建智能体 → 人格设定 → 专长领域点击「+ 添加」报 ReferenceError: addExp is not defined。
- 根因: wizard.js 为 IIFE，模板用 inline onclick；addExp/addPerm/rmPerm/togWzChan/wzFinish 未导出到 window。
- 修复: 在 wizard.js 底部补齐 window 导出上述函数。
- 验证: node --check 通过；浏览器里 typeof window.addExp===function，执行后可新增专长 chip。

## 2026-06-17 — fix: 智能体技能页无删除按钮
- 现象: 智能体详情→技能中，部分页面仅显示“绑定”按钮，没有技能删除入口。
- 根因: ag-skills 行模板把删除按钮放在 `isBound` 分支内，未绑定技能行不会渲染删除操作。
- 修复: 将删除按钮提升为行级通用操作（绑定与未绑定均可见），仅绑定/解绑按钮继续按状态分支。
- 验证: node --check src/frontend/js/agent-detail.js + get_errors 均通过。

## 2026-06-17 — fix: 议事广场底部按钮被挤出视口（前端优化回归）
- 现象: plaza.html 底部「+ 新建广场」「开始」按钮看不见（以前修过又复现），用户疑前端优化导致。
- 根因: UI美化(8a420c7)把顶栏换成普通流的 .topbar-ws(position:relative,56px)，但 .layout 仍保留固定顶栏时代的 margin-top:56px，叠加 height:calc(100vh-56px) 使内容溢出视口 56px，底部按钮被推出可视区。
- 修复: 删除 .layout 的 margin-top:56px 并加注释。浏览器实测 .btn-new/#btn-start 回到视口内(inView=true)，.left/.right 正好 56→561 填满。
- 关联: bug-021 / 同源回归 bug-016。

## 2026-06-17 — doc: 冻结 UI美化plan/todos 阶段A
- 决策: 用户选「方案A 保留但冻结」。UI美化优化plan.md/UI美化todos.md 不删除。
- 动作: plan 顶部加 ⚠️暂停 banner（A1/A4/A6 已致 bug-016/bug-021）；todos A4 加「步骤0 固定顶栏偏移审计」+ 浏览器实测验收项；plan §6 三决策未拍板前不得续推 A1/A4/A6。

## 2026-06-17 — fix: plaza escalations 404 持续刷屏
- 现象: 控制台反复报 `API 404: /api/v1/agent-config/plaza/escalations?... 广场不存在`，同一讨论上下文每 2~3 秒重复触发。
- 根因: `refreshEscalationState` 被多处并发/定时触发；后端返回 404 时前端没有熔断与并发去重，导致同一上下文持续重试。另有深链/本地缓存上下文需前端容错自愈。
- 修复: plaza.js 增加按讨论维度熔断(`escalationFetchBlocked`) + in-flight 去重(`escalationFetchInFlight`)；`refreshEscalationState` 增加 DOM/localStorage 上下文回补与已知广场校验；init 深链讨论选择改为仅在 deepLink plaza 与当前选中一致时采用。
- 验证: 浏览器并发触发 3 次 `refreshEscalationState(true)` 仅 1 次 escalations 请求；不再出现持续 404 请求风暴。
- 关联: bug-022。

## 2026-06-18 — fix: ASSIGN 下拉 Build System 选不中
- 现象: 在 plaza 执行计划卡片里将 ASSIGN 选为 Build System 后，几秒后又自动跳回 AI 编程团队，用户体感“选不中”。
- 根因: renderPlanCard 重渲染会替换整块 DOM，`#assign-team` 新节点默认选中第一个 option；未保留旧值。
- 修复: renderPlanCard 渲染前读取旧值 `previousTeam`，回退 `AGCtx.get('team')` 作为 `preferredTeam`；options 对匹配项加 selected，并在渲染后再次赋值 `assign-team.value=preferredTeam`。
- 验证: 浏览器实测选择 build_system 后等待 6 秒（节点重建 sameNode=false）仍保持 build_system。
- 关联: bug-023。

## 2026-06-18 — fix: QA 误判导致 deploy 被阻断
- 现象: deploy 报“部署已被 QA 阻断: QA 验证结论 = FAIL”，并最终“重试上限已达(2)”。但任务 metadata 里 `qa_feedback.verdict` 已是 PASS。
- 根因: deploy QA Gate 在已有结构化 verdict 的情况下仍做 test markdown 正则扫描，文本内出现 FAIL/BLOCKER 关键词会误触发 gate_blocked。
- 修复: backend `api.py` 中 QA Gate 改为优先使用结构化 verdict；若 verdict=PASS/PASSED/OK/SUCCESS 则跳过 markdown 正则兜底，仅在 verdict 缺失/未知时才回退文本规则。
- 验证: py_compile + get_errors 通过；新任务不会再因 PASS 场景被 regex 误判阻断。
- 关联: bug-024。

## 2026-06-18 — fix: 删除任务 404(Task not found) 的幂等处理
- 现象: 控制台出现 `DELETE .../tasks/<id>/remove 404`，前端提示删除失败。
- 根因: 任务 ID 已陈旧/已不存在；删除语义本应幂等，但前端把 404 作为硬失败。
- 修复: `src/frontend/js/tasks-view.js` 中单条删除与批量清理都对 404+Task not found 视为“已删除”；并在 `src/backend/agents/api.py` 把 remove 路由改为幂等（missing -> already_absent）。
- 验证: 浏览器同 ID 返回 404 时前端判定 `treatedAsSuccess=true`；语法/错误检查通过。
- 关联: bug-025。

## 2026-06-18 — fix: 讨论结束后看不到萃取等按钮
- 现象: 已结束讨论卡片在长标题场景下只看到部分按钮或看不到“萃取/网页”。
- 根因: `plaza.js` 把结束态按钮和标题塞在同一行，标题过长挤压按钮区域；样式未做独立动作行与换行容错。
- 修复: 结束态按钮改为独立 `.disc-actions` 行；`plaza.html` 增加 `.disc-actions` 可换行，`.disc-act` 强制 nowrap，标题 `.tp` 支持 `min-width:0 + word-break`。
- 验证: 浏览器检查已结束讨论 actions=`[重新讨论, 萃取, 网页]`。
- 关联: bug-026。

## 2026-06-18 — fix: 清掉 escalations 的“广场不存在”提示
- 现象: 控制台出现 `API 404 /api/v1/agent-config/plaza/escalations ... 广场不存在`。
- 根因: `refreshEscalationState` 使用全局 `api()`，404 会被 `api.js` 统一 `console.warn`，即便前端已做熔断也会先打印噪音。
- 修复: `plaza.js` 改为该接口使用 scoped `fetch`，在本地处理 404（广场/讨论不存在）并熔断，不再触发全局 API 警告。
- 验证: 浏览器两次触发 refreshEscalationState 后 `hasEscalation404Log=false`。
- 关联: bug-027。

- 2026-06-18 docs 签名治理:总规则 docs/SIGNING_RULE.md + 校验器 check-docs-signoff.cjs(selftest 5/5,全量 0 FAIL/29 WARN);ponytail 一行注入(copilot-instructions L19 + AGENTS.md §5);用户选 WARN-only、不挂钩子
- 2026-06-18 skill-extract 跨议题误去重修复: 去重从 source_text 前2000字改为 source_meta(plaza/discussion/output)+全文SHA-256；API start 支持 source_meta 透传，skill-extract.js 自动带来源元数据；不同议题不再误命中“该文本已萃取过”。(bug-028)
- 2026-06-18 skill-extract 删除后复活修复: delete_item 增加来源墓碑(source_key+全文sha256)并持久化；start_extraction 命中墓碑时不再入队，仅返回 dedup_skipped/rejected，避免“右侧删了再萃取又出现”。(bug-029)
- 2026-06-18 skill-extract fallback 议题化: LLM 不可用时不再输出固定ES/Terraform/成本模板，改为根据 source_title+source_text 关键词动态生成候选，避免跨议题同名误导。(bug-030)
- 2026-06-18 skill-extract 队列来源隔离: 从议事厅跳转时，右侧队列按 currentExtractSourceMeta 过滤，只显示当前讨论来源的项目，不再混入历史旧议题。(bug-031)
- 2026-06-18 skill-extract 详情弹窗按钮缺失修复: 按钮并非 JS 隐藏，而是 modal tab/usage action 的 flex 单行裁切；在 skill-extract.html 增加稳定 class 并在 skill-extract.css 增加 wrap/overflow 响应式规则，确保“展示对比/刷新/快捷建议”可见。(bug-032)
- 2026-06-22T18:08:00Z | 全局重构收尾:实现10.6.1 ensureTeamPositioned + 10.9 regression测试补全 + 文档状态标记 | secs-core.js, regression-smoke.cjs, docs/全局重构todos.md | secs-core.js新增ensureTeamPositioned(teamId,team,fallbackRoom)在sexySelectTeam内调用;regression-smoke.cjs第21b节新增breakdown/trend/detail/lever-split/ratchet/targets/duplicates 7个测试;todos.md已标记项的[x]状态+签名时间戳更新;所有Python/JS编译通过+check-docs-signoff 0 FAIL | ~3k
- 2026-07-04T05:25:00Z | Fable5 全面修复: pytest 96/46失败→0失败(1388过), build修复, vitest 12→7(剩cost-dashboard旧口径待重写) | main.py, agents/api.py, sandbox/{orchestrator,trial_api,python_runner_lite}.py, startup_validator.py, 前端8文件 | 详见 docs/reports/test-triage-2026H2.md; 新文档: README重写+docs/OPTIMIZATION_PLAN_2026H2.md+OPTIMIZATION_TODOS_2026H2.md(F5/GLM分层) | ~60k
- 2026-07-04T06:48Z | P7-1 统一办公室3D落地: js/office/{office-state,office-scene,office-boot}.js + office-state 9单测 | 协作考察=孪生场景内进行(cerebrum已记); flag ?office3d=1; rest-area枯山水委托旧实现保留; 协作光线+热度TOP5面板 | build✓ vitest 173过(仅剩cost-dashboard旧口径7个) | ~8k
- 2026-07-04T07:02Z | P5-1/P6-2/P5-2 主链路落地: agents/execution_plan.py(结构化契约+落地性审查) + plaza_routes 三端点(execution-plan GET/approve/step-status) + dispatch 关卡与步骤绑定 + 11 测试 | 全量 1399 过/0 失败 | P7 办公室补马桶趣味角+页内切换按钮 | ~15k
- 2026-07-04T07:15Z | 办公室3D v3(按Owner截屏反馈): OrbitControls交互(拖拽旋转/滚轮缩放/右键平移), 4列工位+中央共享区(咖啡/跑步机/马桶+玻璃护栏), 背后屋顶视角, Agent落座椅面(y=0.97), 猫9点位巡逻+随机停留, 递文件动画(协作边→Agent持文件走到下游工位交接1.5s后返回) | office-scene.js 全量重写 | build✓ 9单测✓ | ~6k
- 2026-07-04T07:30Z | 办公室3D v4(Owner第二轮反馈): Agent改用plaza霓虹线框模型, 默认落座working, 共享区三件套前后均匀分布(-6.5/0.5/7)+玻璃护栏加长, 团队筛选生效(S.selectedTeams→team_reset整体重置+资源释放), OfficeAPI.setRoster支持成员级筛选(树状选择器的后端就绪) | 10单测✓ build✓ | 剩余: 左栏树状成员选择器UI(GLM, P7-2) | ~5k
- 2026-07-04T07:45Z | 办公室3D v5(Owner第三轮): 白底光照重调(环境光1.45/直射0.85/shadow.radius=8软阴影), 线框主体加深(deep色+0.95不透明), 屏幕全黑(IT界蓝屏=故障), 共享区拉开(-6.5/4/14+护栏26m), 跑步机双侧扶手+仪表板, 猫头部引导转向(转身对准再前进,消除平移), Agent作息调度(咖啡1h/马桶2h/跑步机6h±40%, 演练/开会时不摸鱼) | 10单测✓ build✓ | ~4k
- 2026-07-04T08:05Z | 协作图↔3D对不上根治: world_state.sync_agents_from_team 改整队替换(replace=True默认,根治跨团队幽灵成员累积→协作图40节点), SSE step 事件新增 twin_agents(twin_id→真身)映射, office-boot 按映射把 agent_actions/target 对齐回真身 | 全量1399过 build✓ | 注意: 用户需重新选团队触发一次 sync 后世界才收敛
- 2026-07-04T08:25Z | 作息排队论落地: 设施占位模型(容量1,FIFO,咖啡1min/跑步机5min/马桶5min,到时释放队首补位), 错峰算法=团队内相位均匀分布 due=mean×(i+0.5)/N + 团队并发闸(同队有人在该设施则顺延), 3D排队站位沿queueDir成列, team_reset清理离编占位 | office-state 12单测✓ build✓
- 2026-07-04T08:50Z | 座位语义定稿=保序前移压缩: 同批人顺序抖动→恒等映射不动座; 减员→保留者按原相对次序前移补位(不互换); 新人排其后; 场景空桌随编制收缩拆除+资源释放 | 修复: 幽灵清退后7人坐后排20+号桌的问题 | 13单测✓ build✓
- 2026-07-04T09:05Z | 混沌增援进办公室: office-boot 合并 _chaosTopoState(added并入roster标记增援/removed剔除, 与协作图同口径), 包裹 _dt2dChaosJoin/Leave/Reset 即时同步不等轮询 | 增援Agent按保序压缩坐到队尾新桌, 离开者桌子拆除 | build✓ 13单测✓
- 2026-07-05T01:30Z | 猫气泡=演练解说员: office-state catNote + cat_say; office-scene 猫头顶画布气泡(圆角+尾巴,3行折行); office-boot 优先级 种子技能注入(45s置顶,#btn-inject-skill捕获)>运行中仿真参数(secs-mode/steps/speed)>演练任务(_sx.scenarioSpec.name/dp-task-name) 2s轮询 | 19单测✓ build✓
- 2026-07-05T01:40Z | 测试数据污染清理: ai_coding 移除6个测试Agent(TestAgent01/GetDetailAgent/StartStopAgent×2, 名字判据防误伤), 删2个空测试团队(413abed4/aac93c93), 归档a7c36670测试工作区; 均备份至 storage/_cleanup_backup | 教训: 集成测试写入了真实 team store→已入buglog, 根治=测试store隔离(fixture已有,少数smoke走活服务需排查) | 公有云xOPs为真实团队(uuid id+真实角色名)未动
| 01:58 | 物竞天择 v2：plan/todos 重写+eco_drill v2(协作基因/信号/盲目学习/漂移/timeline)+生境控制台八区块 UI 全量重构+剧场回放+3D 保障+参数页扩容+bug-028/042 修复 | docs/物竞天择* eco_drill.py eco_runtime_config.py trial_api.py Agent-digital-twin.html eco-console.js eco-replay.js office-*.js pet-config.html test_eco_drill_v2.py | 后端 py_compile 全过/前端 node --check 全过/pytest 待沙箱依赖 | ~85k |
| 06:23 | 修复 bug-043 密钥重启即丢：secret_store 合并式写入+显式删除，remove_model 接线；临时库单测全过 | secret_store.py api.py | PASS | ~6k |
| 06:34 | 修复 bug-044 并发任务列表空白：utils.js 补 hideViewLoading（此前未定义致 loadTasks ReferenceError）；任务本身派发成功(build_system 30条) | utils.js | node --check PASS | ~8k |
| 06:51 | v2.2 物竞做实(niche_capacity 竞争+剧本预设)+bug-045/046 修复+新建 任务执行去CLI化 plan/todos(全归 CodeBuddy) | eco_drill.py eco-console.js Agent-digital-twin.html api.py docs/任务执行去CLI化* | 烟测+py_compile+node--check 全过 | ~30k |
| 07:17 | v2.3 第二批：多种群同场竞争全链路+恐惧永锁修复(bug-047)+死亡帧保真采样(bug-048)+平衡定档(gain8/cap3)+生境报告(个体排行/种群裁决)+技能名可读化+退场/幽灵修复 | eco_drill.py trial_api.py eco_runtime_config.py eco-console.js office-*.js Agent-digital-twin.html test_eco_drill_v2.py docs | 综合冒烟 PASS(3代/繁衍/双种群裁决/死亡帧保留) | ~60k |
| 11:17 | v2.4：分场锦标赛赛制(前端编排,旧后端可跑)+锦标赛冠军裁决报告+赛制radio；取证#2(小虎断在默认provider密钥槽,skill链路通)+#3(回退CLI日志来自旧进程,源码已无该分支)；todos 增 XT-10/XB-8/XC-6 彻查作业单 | eco-console.js Agent-digital-twin.html docs/物竞天择* docs/任务执行去CLI化todos.md | node--check PASS | ~25k |
| 11:44 | 复查 CodeBuddy XB-8/XC-6：9/10 项合格；发现并修复 bug-049（cat_speak env 兜底 NameError 静默失效）；确认 _run_claude_cli 已删/health 带 git rev/test_cli_deprecation 覆盖 XC-6.4 | api.py buglog | py_compile PASS | ~8k |
| 11:47 | bug-050 前端猫台词净化护栏（气泡+TTS 双路径），不依赖后端重启即止血 | pet-ecosystem.js office-boot.js | node --check PASS | ~6k |
| 11:56 | bug-051 诊断硬化：cat_speak chat 异常转 JSON+日志，前端 console 打印 HTTP/error | api.py pet-ecosystem.js | compile+node PASS | ~5k |
| 12:02 | bug-052：/health git_rev 改进程启动时缓存+process_started_at；沙箱 e2e 证明多种群函数层 PASS，问题=进程未真正重启 | api.py | compile PASS | ~10k |
| 12:03 | bug-053：cat_speak 团队旧 key 鉴权失败自动降级全局默认重试；用户 console 实锤 authentication_error | api.py | compile PASS | ~5k |
| 12:10 | 恢复『设为全局默认』：新端点 set-global-default（服务端一键提升模型+密钥到全局默认 provider，复用 update_llm_provider 全链持久化）+ 模型行 🌐 按钮 | api.py agent-team-config.js | compile+node PASS | ~6k |
| 12:24 | bug-055：start.sh 默认开 uvicorn --reload 根治重启疲劳；404 定性=时序错位(重启03:53<端点落盘04:10) | start.sh | bash -n PASS | ~4k |

## Session: 2026-07-11 12:38

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-07-11 12:38

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-07-11 12:45

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-07-11 12:58

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 00:31 | Edited src/frontend/js/office/office-state.js | 5→9 lines | ~141 |
| 00:31 | Edited src/frontend/js/digital-twin/eco-console.js | added error handling | ~184 |
| 00:32 | Edited src/frontend/js/digital-twin/eco-console.js | modified function() | ~133 |
| 13:21 | eco 重跑修复: team_reset noBreaks 对留任 agent 生效(排队跑出镜头) + eco2RunDrill 重跑先停旧回放(误认 replay) | office-state.js, eco-console.js | node --check 通过, bug-056 | ~4k |

## Session: 2026-07-12 13:44

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-07-12 13:45

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

| 14:34 | 落盘物竞天择v4 plan+todos | docs/物竞天择任务闭环与Skill遗传{plan,todos}.md | XG-0 docs written | ~8k |
| 14:50 | v4 XG1-8 实现任务闭环+Skill遗传 | execution_plan,plan_eco_bridge,skill_*,eco_drill,trial_api,eco-console | 30 pytest pass | ~20k |
| 15:01 | v4 全量收口 XG1-10 Plaza深链/集成API/遗传UI/棘轮派发 | plaza,eco-*,eco_runtime_routes,eco_drill | pytest32+vitest4 green | ~25k |
| 15:30 | XG-11 物竞入口：先派发团队任务再进试验田 | plaza,tasks-view,eco-console | team_id deep link + 物竞按钮 | ~8k |
| 16:00 | XG-12 对比种群可选任务·同计划apple-to-apple | eco-console,Agent-digital-twin.html | rival task select | ~6k |
| 16:20 | 双队对比：有rival自动多队对抗+预览两队agent | eco-console.js | 种群面板应见两队 | ~4k |
| 16:40 | 赛制语义校准：分场=多队比skill；取消加rival自动切对抗 | eco-console | user correction | ~3k |
| 16:45 | 撤销加对比自动切对抗；分场=多队比skill | eco-console | user correction | ~2k |
| 09:00 | T_i 分解 skill/协作/残差 | survival_decompose.py,eco_drill,eco-console | 份额和为1 | ~8k |
| 01:00 | v4 todos 全量收口：XG-12/13 + XB-6.1/7.1 + 测试修复 | pet-config,office-scene,survival_*,todos | 73 pytest + 4 vitest green | ~12k |
| 01:25 | 闭环LOOP: aws×build 9跑次+分析改造+can_serve扩窗 | eco_runtime_routes,eco_drill,scripts/eco_closed_loop_eval | skill弱→能 collab弱 报告已写 | ~30k |
| 07:00 | LLM分析提示词可配置 + 演化加压旋钮 | eco_runtime_config,pet-config,eco_drill,eco_runtime_routes | llm_analysis textarea + skill_idle 税 | ~8k |

| 10:56 | 继续LOOP: 捕食偏无技能+稀缺分享/同队分享 + 闭环加压复验 | eco_drill.py eco_runtime_config.py pet-config eco_closed_loop_eval | skill/team 弱→能(mixed dominant+对抗collab); pytest 56 passed | ~8k |

| 11:15 | 孪生左栏：树状团队/智能体 + 音量式生境旋钮台 | Agent-digital-twin.html digital-twin-cli.js eco-console.js pet-config | 旋钮与右侧压力台双向同步写回 config；弃用「Skill/团队变强」文案 | ~5k |
| 11:40 | 旋钮对齐: A生境4 + B加压8 与 pet-config evolution_pressure 同键 | eco-console.js Agent-digital-twin.html | 盘下显示 field key | ~3k |
| 12:05 | 根 README 写入物竞 T_i/加压8钮公式与 A4+B8 对照表 | README.md | 非 docs/README | ~2k |
| 13:10 | 设计物竞适者反馈调整台(③面板@孪生页) plan+todos | docs/物竞适者反馈调整台* | 先反馈Skill+协作再进成本页 | ~3k |
| 13:40 | 适者反馈台P0+精简演练控制描述文案 | Agent-digital-twin.html eco-feedback.js eco-console.js | 步骤条③反馈门禁进成本页 | ~4k |
| 14:15 | 适者反馈P1协作写回+P2成本候选条 | collab_integration.py eco_runtime_routes eco-feedback cost-dashboard | pytest 12 passed | ~5k |
| 14:40 | 修 skill apply applied=0 静默: agent解析+audit诊断 | eco_runtime_routes.py eco-feedback.js | 区分 already_present/agent_not_found | ~2k |
| 15:05 | 修 skill 建议:仅未绑定+优先reserve/plan_demand;UI禁止回退genome | skill_integration.py eco-feedback.js | 解释aws_mon勾已绑定导致0写回 | ~3k |
| 15:30 | 反馈台 skill 显示名:加载团队库+分类池 name，hex 标未命名 | eco-feedback.js | 回答「数字串看不懂能力」 | ~1k |
| 15:50 | 适者反馈台 skill 旁 📖 查看描述/指令(对齐团队技能列表) | eco-feedback.js | 用户确认应加问号/书本按钮 | ~1k |
| 16:20 | 关闭办公室3D生态位图腾/觅食光点(默认) | office-scene.js | 用户:无觅食孪生语义+hex不可读 | ~1k |
| 17:05 | todos 记入 XF-5 任务型演练生态位可视化待讨论 | docs/物竞适者反馈调整台todos.md | 默认关图腾；任务型可视化需重设计 | ~0.5k |
| 17:25 | todos XF-6: 选种群后必须任务挂载菜单(任务主闭环) | docs/物竞适者反馈调整台todos.md | 用户明确要求写入 | ~0.8k |
| 18:00 | XF-6任务挂载+物竞成本结合plan/todos | eco-console.html/js docs/物竞与成本优化结合* | 先适者后省钱 | ~6k |

| 10:33 | 修 3D 左下双蓝信息窗重叠 | office-boot.js Agent-digital-twin.html | habitat 并入 env-3d-bottom-hud | ~1k |
| 10:57 | 写入物竞协作→关系/通道 plan§3.5 + todos XF-7 | docs/物竞适者反馈调整台{plan,todos}.md docs/README | 用户校准：真协作=关系+通道 | ~2k |
| 11:07 | XF-7 通道能力全量落地 | agent_channel_bus channel_integration eco-feedback team-config | 5 pytest pass；关系边仍待 | ~8k |
| 11:07 | XF-7通道全量落地 | agent_channel_bus channel_integration eco-feedback team-config | 5 pytest；关系边仍待 | ~8k |

## Session: 2026-07-14 20:31

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 12:36 | XF-7.1/7.3 关系边 suggest→confirm apply | relation_integration.py eco_runtime_routes eco-feedback agent-team-config | 4 pytest pass；深链关系 tab；通道后补齐关系拓扑 | ~6k |
| 12:40 | 关系边写回前 Before/After 对照 | eco-feedback.js relation_integration.py | suggest 带 before 快照；反馈台双栏+勾选实时 After | ~2k |
| 12:48 | 关系边 Before/After 改 SVG 拓扑图 | eco-feedback.js | 椭圆布局+有向箭头；新增虚线青边；勾选实时刷新 | ~2k |
| 12:55 | 修复关系 Before 空白：通道共总线软边 | relation_integration eco_runtime_routes eco-feedback | aws-ops store=0 但 channel=15；图示紫点线 | ~3k |
| 13:05 | 校准协作语义：同队/通道=真协作三层 | relation_integration eco-feedback cerebrum | 去掉「软/假」表述；图例改协作三层 | ~1k |
| 13:20 | 任务执行接入协作三层拓扑 | agent_relationships api tool_executor | peer/channel/store 门禁；handoff+delegate+prompt；18 tests | ~5k |
| 13:35 | 修复反馈台 Before/After 图不显示 | eco-feedback.js | team 多源解析+本地 peer 兜底+图壳始终渲染+SVG 加固 | ~2k |
| 13:45 | 修 _renderSkillTable boundMap undefined.length | eco-feedback.js | agent 无 recommend 行时用 [] 兜底 | ~0.5k |
| 13:55 | 审计并修通道写回总线名分叉 | channel_integration eco-feedback | resolve 优先真身 channel；apply 用 _resolveTeamId | ~2k |
| 14:05 | 收口 XF todos：eco_collab UI + 空关系 CTA + 验收脚本 | agent-detail agent-team-config verify_eco_feedback_xf.py todos | PASS=29；XF-5 仍待讨论 | ~6k |
| 14:42 | 落地 XF-5 任务型考卷 2D HUD | eco-task-hud.js eco-console office-boot html | B+右侧chips；仅契约挂接；无蓝柱 | ~4k |
| 14:46 | 落地物竞×成本 BidCandidate 全链路 | bid_candidate.py eco_runtime_routes eco-feedback cost-dashboard | create/list/patch/lock；③推送；cost 面板；3 tests+live | ~8k |
| 15:07 | XC-4.4 生产任务注入 locked BidCandidate | bid_candidate.py api.py eco_runtime_routes | submit 注 skill/适者；GET locked；step prompt；4 tests | ~3k |
| 15:10 | XC-4.4b SkillRouter 静默绑定 locked skill | bid_candidate.py api.py cost-dashboard | lock+任务提交 assign 幂等；5 tests | ~2k |
| 15:17 | 收口：verify 纳入 XC BidCandidate 全链路 + plan 待建文案 | verify_eco_feedback_xf.py docs/物竞与成本* | PASS=51 FAIL=0；pytest 5 | ~2k |
| 15:30 | cost 页物竞主轴常驻+双向深链+同task token 条 | cost-dashboard.html eco-feedback Agent-digital-twin | 直接打开也见竞标；④可点 | ~3k |
| 07:06 | Token治理主轴：全链1-6+计量缓存路由预算+物竞折叠 | cost-dashboard prompt_cache token_governance_routes token_ledger chat_harness | pytest10; verify PASS=39; live API ok | ~12k |
| 07:45 | TG-7: 任务归因 env+记账 + submit 预算402 + unscoped UI | api.py tool_loop token_governance cost-dashboard | pytest 7; 归因/门禁落地 | ~6k |
| 08:05 | cost 顶栏合并：全链1-6+动作+筛选条 | cost-dashboard.html | 去重复 pipe/topbar/action-bar | ~2k |
| 08:20 | TG v2: 调研plan+TokenGovernanceService+workbench一体 | token_governance/* token-workbench.js cost-dashboard chat_harness | pytest9; dashboard live; 去两张皮 | ~15k |
| 08:10 | R3: tool_loop prepare + skill/model 节省 + 预算感知 compact | tool_loop chat_harness service workbench | pytest 11 | ~5k |
| 08:25 | cost 页 Taste 浅色：冷灰白+森林 accent 强制 light | cost-dashboard.css/.html | 去紫/奶白；sticky 白玻璃顶栏 | ~2k |
| 08:30 | R5: skill缩短+savings JSONL+工作台按task节省+浅色 | token_governance savings_store workbench | pytest13 | ~4k |
| 08:40 | R6: SkillRouter RoutingSession 解析+关键词回退+savings API+tg_prepare usage | token_governance service routes | pytest15 | ~3k |
| 08:50 | 工作台布局：动作(杠杆/预算)在前，报表(账单/节省/prepare)在后 | cost-dashboard.html token-workbench.js | UX 重排 | ~1k |
| 09:00 | 杠杆区改为实现卡+试跑效果表，修正 skill 虚增 saved | token-workbench.js service | 可证 before/after | ~2k |
| 09:20 | R7 杠杆 catalog 全量 UI+plan+关compress可测+lever字段 catalog_id/module/before/after | lever_catalog service workbench plan todos | 19 pytest green, live levers/sim OK | ~5k |

## Session: 2026-07-15 11:06

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 11:20 | R8 节省计量诚实化 | token_governance/service.py tests plan/todos | saved=before-after净减; observe HIT不虚增; 21 pytest; 恢复 settings 全开 | ~2k |
| 12:00 | R9 六源调研真算法入 prepare | rtk/progressive/codegraph/behavior/cost_tier service lever catalog | live 12593→4838 saved7755; 26 pytest; codegraph MIT CLI | ~8k |
| 12:25 | fix 试跑 toast null textContent | system-evolution.js token-workbench.js | cost 页无#toast; 全局 toast 空指针; 改安全 toast+collectBody 不全 false | ~1k |
| 13:10 | 真实 task 试跑 | task_messages.py routes tool_loop workbench | snapshot 落盘+reconstruct; 29 pytest; live task saved 8774 | ~3k |
| 13:40 | 试跑改为用户点选 task | cost-dashboard.html token-workbench.js | 独立面板列表+团队过滤+账单行联动 | ~2k |

## Session: 2026-07-15 20:28

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 12:31 | paper consistency pass + research-state COMPLETE | paper/paper.tex analysis.md research-state.md paper/paper.docx | peak collab band fixed; ANOVA p>0.7; docs synced | ~2k |
| 12:31 | user: do not touch paper/research | .wolf/cerebrum.md | preference logged | ~0.2k |
| 14:57 | R10 杠杆一行表+params旋钮 | lever_params settings service routes workbench README tests | 33 pytest green; UI 去长文; budget/threshold 可调 | ~8k |
| 15:01 | R10.1 收口: 预算面板只读+测隔离settings+恢复默认 | token-workbench tests settings | 33 green; 无双写预算表单 | ~2k |
| 16:44 | R10.10 试跑前自动保存+submit开关+dirty+试跑列精简 | token-workbench.js todos | node ok; 33 pytest; live max_tool 生效 | ~2k |
| 17:20 | R10.11 预算验证并入试跑建议+账单合并+竞标末位 | cost-dashboard token-workbench | 去掉独立预算验证菜单；细节中文；eco 非侧支 | ~3k |
| 17:31 | R10.12 合并效率/建议/构成/明细为分析台 | cost-dashboard.html | 共用筛选条；棘轮副轴折叠 | ~2k |
| 17:33 | R11 H0+H1 启动: 段导航 sticky 窗口统一 空状态 账单高亮 | cost-dashboard* token-workbench | scheduler 25m; node ok; 33 pytest | ~4k |
| 17:40 | R11 COMPLETE H0-H4 全勾 | cost-dashboard token-workbench cost-dashboard.js | 明细空态/建议动词/窄屏/compress恢复/竞标步骤6/去抖/错误可见 | ~6k |
| 17:45 | 竞标区强化: 过程条/能力/排行卡/比价/质量Q/冠军锁定 | cost-dashboard.html | BidCandidate 竞价台可见 | ~4k |
| 17:58 | R11 scheduler polish: bid focus + quality recheck + error empty | cost-dashboard.html | H0-H4 still COMPLETE; node+33 pytest | ~1k |
| 18:48 | R11 COMPLETE 停调度019f66d64812 | docs/任务Token治理-5h连续优化todos.md | 无未完成H项; node+33pytest 绿; 停止重复劳动 | ~0.3k |
| 23:42 | 任务token归因加固: session/tool_loop token_scope+team 必写 | api.py tool_loop.py workbench KPI | build_system 历史0=未记账; 新任务应进分析台 | ~3k |
| 00:03 | 新增 verify_task_token_attribution.py | scripts/ | 离线写入路径+usage.db诊断+可选live | ~1k |
| 00:18 | 物竞四机制: 性选择/频依/上位/衰老 + 全链核对 | eco_drill.py eco_runtime_config eco-console pet-config README nature-audit | 65 pytest 绿; A4+B12; 生产默认注入 | ~8k |
| 00:25 | 右侧环境压力台补 Darwin 四滑杆(性选择/稀有利/协同/衰老) | Agent-digital-twin.html eco-console.js | 用户可见A4下新增B段 | ~1k |
| 00:35 | 衰老率迁 metabolism(Agent侧) 与环境加压分离 | eco_runtime_config eco_drill eco-console pet-config | A生境/B环境选择/C Agent 生命 | ~2k |

## Session: 2026-07-16 11:40

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 03:43 | 物竞四机制全链核对+habitat注入测试+写回文案A+B+C | eco-console eco_runtime_config tests Agent-digital-twin.html | 30 pytest绿; 生产注入OK; 压力台仅demand skills | ~2k |
| 06:10 | 分析台：构成/趋势两图并入优化栏；标题改 skill萃取+路由 成本构成与趋势 | cost-dashboard.html | 嵌套 charts 上下叠；id 不变 | ~0.5k |
| 06:15 | 消耗明细并入优化 skill/构成/趋势 右栏 | cost-dashboard.html | pods-table id 不变 | ~0.3k |
| 06:50 | Token节省命名 + cost 页补生态配置站导航 | nav.js cost-dashboard pet-config | 🐾→生态配置文字；全站 Token节省/生态配置 | ~1k |
| 06:53 | 修 cost 导航重叠: 去掉 topbar-ws__nav absolute 叠层 | cost-dashboard.html | site-nav 文档流; 生态配置仅在站导航 | ~0.5k |
| 06:58 | Taste 浅色全站(除数字孪生) | css/taste-light.css + 13 html | twin 保持暗色; 其余 cold-light | ~3k |
| 07:00 | 对齐官方 Taste Skill tasteskill.dev + 安装 SKILL.md | .agents/skills/design-taste-frontend taste-light.css cerebrum | 用户纠正官方源 | ~1k |
| 08:05 | plaza 3D 浅色议事厅 + 气泡/TTS 配色协调 | plaza.js plaza.html | bg fog 0xE8EDF3 石台浅灰; 议事台白底气泡 | ~2k |
| 08:09 | skill-extract 3D 浅色培养皿(对齐 plaza Taste) | skill-extract.js | bg/fog E8EDF3 基质/灯/菌丝/标签/团队皿 | ~2k |
| 08:14 | skill-extract 3D 对比度修复: 基质/菌丝/尘埃/皿可见 | skill-extract.js | 降雾 提 opacity 加 rim accent 加厚 hypha | ~1.5k |
| 08:16 | 修 skill-extract 3D 全空: viewport 不透明盖住 canvas | taste-light.css | viewport background transparent | ~0.5k |
| 08:29 | skill-extract 3D sexy twin 配色+skill 自发光+萤火虫尘埃 | skill-extract.js | vivid palette; mycelium 34d399; additive skill rings; firefly dust | ~3k |
| 09:03 | llm 测试连接显示实际 model@base + tip 解释 model_not_found | api.py agent-team-config.js | 全局 vs 单模型区分 | ~1.5k |
| 09:04 | skill-extract 弹窗 tab 浅色字对比修复 | taste-light.css skill-extract.html | modal-tab active 深色/accent; 面板正文 ink | ~1.5k |
| 17:05 | skill-extract modal tab 白字→深色/accent（token+force fill） | skill-extract.css taste-light.css skill-extract.html | 编辑/演化/验证等可读 | ~1k |
| 17:09 | 修 test-model 被 TG 改写成 deepseek-v4-flash | chat_harness api agent-team-config.js | model_override+sent_model | ~2k |
| 17:18 | skill-extract 3D Taste 配色：forest+slate，去霓虹紫粉 | skill-extract.js | TASTE3D 单 accent | ~2k |
| 17:19 | skill-extract 3D 标签可读：白底 chip + 深字 + 放大 | skill-extract.js | makeSpriteLabel | ~1k |
| 17:21 | 菌丝改冷色 teal 系+提高透明度/粗细 | skill-extract.js | MYC palette | ~1k |
| 17:22 | skill-extract 3D 字对齐 plaza makeTextCanvas 800/34 + scale | skill-extract.js | 去 chip | ~0.8k |
| 17:49 | 全站「数字孪生」入口统一 ?office3d=1 | nav.js global-nav 各页 topbar | 物竞试验田默认 | ~0.5k |
| 18:14 | plaza LLM 不可用=INVALID_API_KEY；改进 abort 提示；plaza 跳过 model_route | plaza_engine chat_harness | 用户需更新 Key | ~1.5k |
| 18:43 | 修技能删除404：按 id/slug/registry/store/队列解析 | api.py tools-skills skill-extract | delete_skill 增强 | ~2k |
| 18:48 | 修技能DELETE 403：api()走CSRF重试 + fetch包装 | api.js agent-team-config tools-skills | CSRF | ~1k |
| 18:51 | Agent 列表加编辑/删除按钮 | agent-team-config.js | editAgentFromList deleteAgentFromList | ~0.5k |
| 18:54 | 技能删除幂等：二次删除 already_deleted + 防连点刷新 | api tools-skills | 避免假 404 | ~0.8k |
| 19:25 | Agent技能删除：就地移除+幂等+禁整页刷新 | agent-detail.js | deleteSkillWithContext | ~1.2k |
| 19:37 | 演化LLM：磁盘拉Key+override优先+错误可读+回退命名 | skill_evolver chat_harness skill-extract | 解释技能名 | ~2k |
| 19:37 | 修 resolve_api_key：UI密钥优先于 OPENAI_API_KEY 环境变量 | secret_store skill_evolver | 演化可用 | ~1k |
| 20:18 | Implement TSE skill extractor pipeline + wire skill_extractor | tse/*, skill_extractor.py, test_tse_pipeline.py | 8 tests pass | ~4k |
| 00:30 | TSE training: silver/dataset/trainer/checkpoint/active + CLI | tse/*.py, scripts/train_tse.py, test_tse_train.py | 15 tests pass, demo train ok | ~5k |
| 13:45 | Fix extract LLM route + local TSE decoder; verified real skill AWS ES auto-scale | chat_harness.py, tse/decoder.py | tse+qwen-36 ready_for_review | ~1k |
| 14:10 | Document TSE skill-extract arch in README; confirm available (tse+qwen-36) | README.md | extraction OK + docs | ~0.8k |
| 15:20 | Fix deleted skills resurrect via extract queue rehydrate | api.py, skill_extractor.py, skill_library.py | tombstone+queue dict fix | ~1.2k |
| 14:45 | Fix plaza extract: full transcript not plan-only; skill-extract hydrate+auto TSE | plaza.js, skill-extract.js | 3 fe tests pass | ~1k |
| 15:00 | skill-extract UX: queue=pending only; taxonomy=approved library; no left skill-card dup | skill-extract.js/html | vitest ok | ~0.8k |

## Session: 2026-07-17 02:01

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 02:05 | 修回退草稿标题：TSE local 优先+去【回退草稿】前缀+前端离线徽章 | skill_extractor.py skill-extract.js | smoke OK; vitest 20; tse 8 | ~3k |
| 02:15 | 萃取进度条显示 TSE 引擎徽章+model | skill-extract.html/js/css + skill_extractor SSE | vitest 20; 文案/徽章随 tse_extract_done | ~1.5k |
| 02:12 | 修特质/储备 tab 误分类：skill_type 持久化+默认储备 | skill_extractor + skill-extract.js | 非公共≠特质；旧数据回填 reserve | ~2k |
| 02:24 | 重写 skill 演化：JSON草稿+语言硬守卫+前端可编辑changelog | skill_evolver.py skill-extract.* tests/test_skill_evolver.py | 9 pytest; vitest 20 | ~4k |
| 02:35 | 路由 lifecycle 加权+affinity 落盘+README 演化/验证/路由速查 | skill_router.py README tests | 12 pytest | ~2k |
| 08:05 | 语义验证(步骤/工具mock/场景对齐)+路由 lifecycle 徽章 UI | skill_verifier skill_router skill-extract README tests | 15 pytest + 20 vitest | ~4k |
| 08:20 | Twin A/B 全量接入 skill 验证：skill_twin_ab + UI 对照表 | skill_twin_ab.py skill_verifier.py skill-extract.js README tests | 7+ twin/semantic tests pass | ~5k |
| 08:40 | 修演化卡死：独立 session + 60s 超时 + 最多2次LLM + 取消语言二次修复 | skill_evolver.py skill-extract.js | 11 pytest | ~2k |

## Session: 2026-07-20 17:29

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 09:31 | resume: 核对 skill 演化卡死修复仍在位 + 21 skill 单测绿 | skill_evolver.py skill-extract.js tests | 独立 session/60s/≤2 LLM/前端90s；无未提交业务 diff | ~1k |
| 09:43 | 演化应用后自动验证闭环 | skill_evolver.py api.py skill-extract.js/html tests | apply 写 changelog/next_step；accept→verify tab+triggerVerify；verify 防连点finally | ~2k |

## Session: 2026-07-23 23:25

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 15:32 | skill闭环: 演化证据加厚(usage+last_verify/twin)+验证失败一键回演化 | skill_evolver skill_verifier skill-extract | 6 pytest + 13 vitest green | ~3k |
| 15:35 | fix verify error_detail prioritize sandbox/docker err + last_verify persist tests | skill_verifier tests | 8 pytest green | ~1k |
| 00:08 | Twin前后对比图+affinity/task usage进演化证据 | skill_evolver skill_verifier skill_router skill-extract | 10 pytest + 14 vitest | ~4k |
| 00:25 | Agent四层记忆绑定：TigerInBamboo移植+配置页记忆绑定tab | agent_memory_core routes agent-detail | 3 pytest green | ~5k |
| 03:05 | P0 Agent记忆生命周期+站级菜单Agent记忆+小满/沈弥安Persona | lifecycle routes agent-memory.html nav | 6 pytest | ~6k |
| 04:10 | P1 记忆共享ACL+传递遗嘱执行+中枢UI共享矩阵/传递台 | share transfer agent-memory-page | 8 pytest | ~5k |
| 05:20 | P2 记忆运行时: chat注入+任务EventBus日志+tool感知压缩 | agent_memory_runtime chat_harness tool_loop | 11 pytest | ~4k |
| 06:00 | P3 README记忆章节+detail Persona/中枢深链+AAS桥接 | README agent-detail memory_system runtime | 12 pytest | ~3k |
| 06:40 | 夜间优化: auto-bind/对话写记忆/反思/深链/state=unbound默认 | runtime lifecycle agent-detail memory-page | 14 pytest + 4 vitest | ~4k |
| 07:25 | 续优化: 共享预览/co_write/健康分/对话反思 | share lifecycle memory-page | 15 pytest + 5 vitest | ~3k |

## 2026-07-23T23:43:31Z
- Fixed /api/v1/agent-config/teams 500 report: endpoint 200 after restart; hardened list_teams; Cloud Ops factory kwargs now load (7 teams).
- agent-team-config loadAgent delegates to agent-detail window.loadAgent; ag-memory tab fallback + cache-bust v=20260724-teams-mem.
- getTeamsList tolerates {items} envelope and keeps last-good cache on empty/fail.

## 2026-07-23T23:46:48Z
- Root cause of agent-team-config API 500 noise: `async function api` clobbered window.api; fixed via const api + 5xx retry on getTeamsList.

## 2026-07-23T23:53:06Z
- 深链 atab=ag-memory 空白：config/detail 双 loadAgent 竞态，已 wait __detailLoadAgent + detail 二次加载。

## 2026-07-24T00:45Z
- 拟生记忆 P0+P1：SemanticCore/consolidate/forget/systems；UI 正名；18 memory tests pass

## 2026-07-24T01:10Z
- 拟生记忆 P2+P3：drift_topology / working / transfer_narrative / hub 层场过程分栏；20 memory tests pass

## 2026-07-24T01:40Z
- 拟生记忆收口：ECO_SURVIVAL_UPDATED EventBus、vector-lite、配置页工作台 pane、README 专章；21 tests pass

## 2026-07-25T02:00Z
- 广场多队派发：team_ids 并行赛道 + twin extra_team_ids 深链；13 dispatch tests pass

## 2026-07-25T03:00Z
- 多队派发加固：PlanStep.task_ids_by_team、multi_dispatch API、前两队对抗、多选记忆；14 tests pass
| 02:13 | 修演练 model_route 改写 deepseek-v4-pro 403 | model_router/chat_harness/llm_decision | 三档跟随全局 glm-5.1 + twin skip | ~2k |
| 10:17 | 全局LLM真正全局：clamp+prepare/tool_loop/harness 同步 | model_router/service/tool_loop/chat_harness | glm-5.1 不被 deepseek-v4-pro 覆盖 | ~2k |
| 10:23 | 全局配置为主：prefer_global_model 默认锁 model 名 | model_router/service/tool_loop/harness | model_route 只记档位 | ~1k |
| 10:29 | 全局LLM绝对锁定：has_global_llm时忽略override/route/团队槽 | chat_harness/tool_loop/api | 仅__探针可临时改 | ~1k |
| 10:31 | 补全模型与连接 global-model-banner 已启用态 | agent-team-config.js | 与全局LLM硬锁语义对齐 | ~0.5k |
| 10:33 | 数字孪生3D窗口加猫静音按键 | office-boot.js | localStorage+停播TTS | ~0.8k |

## Session: 2026-07-27 10:06

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 10:13 | S4 P2-1/P2-2 skill publish gate + loop e2e | skill_publish_gate.py skill_library skill_verifier tests | 19 skill tests pass | ~3k |
| 10:48 | 9.3/9.4 TSE paper experiments: fixtures+experiments+CLI+tests+local runs | tse/experiments.py fixtures run_tse_paper_experiments.py test_tse_experiments.py | 10 pytest; tse_9_3/9_4_local.json | ~4k |
| 10:53 | Close 9.3/9.4 todos E-11/F: publish_gate isolation review + repro notes | docs/结构群体协商9.3与9.4实验实现todos.md | all items [x]; 19 tests green | ~0.5k |
| 11:18 | P0/P1 9.3/9.4 follow-up: full attn trainer, evidence metrics, sweep, fig5/6 | full_attention_trainer synthetic_corpus experiments CLI renderer fixtures tests | 29 joint tests; sweep 12×3 seeds failed=0; figures PNG/SVG | ~8k |

## Session: 2026-07-27 21:54

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 22:25 | Agent记忆补完 M-0.1~M-3.4：v2迁移/Will/半衰期/Plaza证据/UI/五组实验 | agent_memory_migration.py core transfer routes runtime page tests reports | 39 pytest + 7 vitest; todos all [x] | ~12k |
| 22:12 | S1 L3 当前演练卡：全局 KPI 不按 team 过滤 + dtContext 摘要卡 + by_status 映射 + vitest | digital-twin-cli.js secs-core.js 收口冲刺todos | 3 vitest pass; L3 [x] | ~2k |
| 21:56 | 续会话验收：9.3/9.4 后续增强全 [x]；skill 目录赋予+同队绑定落盘改动 31 pytest + 7 vitest 绿 | tse/* skill_extractor skill-extract agent-detail tests | ready, 无未完成 todo | ~1k |

## Session: 2026-07-28 08:06

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 08:19 | Agent记忆 M-3.2b/M-3.3b 收口：修继承软检索+真LLM 30 cells+审计 | migration.py llm实验脚本 reports todos | 49 pytest+7 vitest；inheritance_injected=1.0 | ~8k |

| 16:30 | 团队流水线模式（full/single）支持，消除 build_system 硬编码，支持公有云xOPs开启 7 步分工 | models.py team_store.py api.py agent-team-config.html/js | round-trip + 单元逻辑通过 | ~2k |

| 16:15 | 团队成员环状拓扑图与可视化连线设计落地，支持预设拓扑（xOPs运维/研发/能效/星型/网状）与用户交互式自由连线编辑 | models.py api.py agent-team-config.html/js | test_workflow_pipeline_mode.py 自动化测试全通过 | ~3k |

| 17:30 | 修复拓扑连线编辑在内存数组被重新渲染重置的bug，确保点击两成员即时绘制高亮连线并与metadata双向同步 | agent-team-config.js | 测试通过 | ~1k |

| 17:36 | 优化自定义拓扑连线行为：首次选择自定义拓扑时默认给出一张干净无连线的空白画布，不继承预设连线；点击两节点直接画线 | agent-team-config.js/html | 测试通过 | ~1k |

| 17:42 | 拓扑连线编辑工具栏新增「↩ 回退」与「↪ 下一步」Undo/Redo功能，支持多步历史回退与重做 | agent-team-config.html/js | 测试通过 | ~1k |

| 18:28 | 修复团队拓扑模式与当前选中团队自动对齐逻辑：切换团队自动切至团队所属领域专属拓扑（Build System->研发全流水线/公有云xOPs->xOPs运营环/Energy->能效治理环），下拉菜单动态显示当前团队智能自适应匹配项 | agent-team-config.js | 测试通过 | ~1k |

## 2026-08-20 model-clearance 模块并入
- 从分支 model-clearance-wip (2f692a9) 并入 src/backend/domain (information_sources + investment_simulation)、data-intelligence.html、ai-model-entry-clearance.html、engine-*.js 及 5 个测试文件
- main.py 挂载 domain.api_routes (36 条路由)；nav.js / global-nav.js 新增 data-intelligence、model-clearance 两个导航项
- 验证：vitest 19/19 通过；test_workflow_pipeline_mode.py 通过；/api/v1/information-sources 返回 401（路由已挂，需登录态）
- 遗留：domain 内 investment/投资 术语共 68 处待按 TODOS T002-T006 改名

## 2026-08-20 ModelClearance 全量任务落地与验收通过
- 完成 P0 术语净化与 guard 测试（vitest 6/6 suites，20/20 tests passed）
- 完成 P1 数据底座（config/model_license_registry.json 22 款主流模型 + scripts/validate_model_registry.py 校验通过 + domain/model_clearance 数据模型与只追加存储）
- 完成 P2 证据层 Scanner（Manifest/Sigstore/PlatformEndorsement/Format/ML-BOM/CVE/License/Resource/RedTeam）
- 完成 P3 策略引擎（clearance_policy.yaml + AST safe_eval + policy_evaluator + fail-closed 门禁编排器 + adjudicate）
- 完成 P4 Agent 评审团队（5 Agent 评审、单向收紧守卫、证据摘录幻觉守卫、法律会签触发器）
- 完成 P5 准入清单与 in-toto DSSE attestation 签发及验证 + 完整 REST 接口（/api/v1/model-clearance/*）
- 完成 P6 运行时基线（3档 profile yaml + K8s NetworkPolicy/Pod/Quota 模板 + 11项不变量与权重哈希校验器 + 多阶段 Dockerfile）
- 完成 P7 持续验证 L5（30分钟基线巡检 + 每日 CVE/许可证重评 + 到期降档调度 + 月度报告）
- 完成 P8 控制台前端与知识库自动联想对接
- 运行 10 组后端测试套件 + Phase 1 出口条件验证：全部 100% 通过（Permissive/Conditional/Restricted 真实路径验证）。

## 2026-08-31 ModelClearance §9 保障记录报告

- 新增 `src/backend/domain/model_clearance/assurance_record.py`：按标准 §9 装配保障记录（受评制品 / 已复核证据 / 测试方法与结果 / 对比与外部情报 / 发现与缓解 / 残余风险 / 条件限制例外 / 最终裁决，另附 §10 许可用途与 §11 治理归属）。
- 新增 `GATE_CRITERIA`：G0-G8 各门对应标准正文的评估要点，报告能回答「这道门照着标准哪几条在看」。
- 新增端点 `GET /api/v1/model-clearance/applications/{app_id}/assurance-record`。
- 前端 `renderReportIndex` 重写为拉取 §9 记录并渲染 8 个章节 + 逐门 details 展开 + JSON 导出；轮询期间以 `application_id|updated_at|status` 为缓存键，避免每 500ms 打一次后端。
- 新增 `tests/test_clearance_assurance_record.py`（6 项）；clearance 套件 57 passed。
- 端到端验证：customer_facing 且未完成附加评估 → G7-USE-01 blocker → not_approved；报告 8 个 block、9 道门全部渲染。

## 2026-08-31 独立保障记录交付文档（tasteskill）

- 新增 `src/frontend/js/assurance-report-doc.js`：把 §9 记录渲染成单文件、可离线打开、可打印的独立 HTML 交付物。
- Design read：受监管保障文档 / 评审与法务小组 / trust-first / 档案式排版，三档 `VARIANCE 3 · MOTION 1 · DENSITY 5`。
- 已锁定三条系统规则：圆角一律 0；唯一强调色 archive navy 只用于结构件，pass/fail/needs_info 是功能令牌不作装饰；字体走系统栈（交付物不得外链字体，否则离线与归档环境降级）。
- 控制台报告区新增「下载独立报告页 HTML」按钮；window.open 会被弹窗拦截，改为 Blob 下载。
- 新增 `src/frontend/__tests__/assurance-report-doc.test.js`（5 项）：自包含（无 http / script / link）、10 个章节齐全、9 格门禁条带、外部标签转义、无裁决时不得出现批准字样。
- 浏览器实测：产出 25.8KB 单文件，`selfContained=true`，含 §11 三方签署块。

## 2026-08-31 Blocker 检查项的 LLM 分析与建议

- 新增 `src/backend/domain/model_clearance/blocker_advisor.py`：为每道已评估门禁的阻断项生成分析 / 建议 / 不处理的风险，每道门一次调用、`asyncio.gather` 并发。
- 结构性红线：调用方只读 analysis / recommendation / risk_if_ignored 三个字符串，`result` 取自 GateVerdict 而非模型输出，不存在让 LLM 影响裁决的代码路径。产出 `advisory=True` 并署名 provider/model。
- 新增 `BlockerAdvisory` 模型并持久化到 `ModelApplication.blocker_advisories`——标准 §5 要求可重复，报告每次渲染读同一份文本，不重新问模型。
- 新增端点 `POST /api/v1/model-clearance/applications/{id}/blocker-advisories`；未起评时返回 409。
- 报告两处渲染：控制台 `#reports` 的检查项行内 `.adv` 块，独立报告页表格内 `.adv-row` 整行，均带「不参与门禁规则求值」免责语。
- 测试：后端 `tests/test_clearance_blocker_advisor.py` 7 项（含"模型给出 verdict 字段必须被丢弃"与"上游失败必须留痕"），clearance 套件 64 passed；前端 12 passed。
- 真实 LLM 端到端：16 条全部生成、0 错误、37 秒，generated_by=`openai/qwen-36`，内容确实引用了 `prohibited_clear` / `data_egress_to_prc` 等真实证据字段。

## 2026-08-31 从开放权重资源直达准入评审（带入 / 可见 / 可点）

- 根因：`open-weights-models.js` 一直带着 `?model_id=` 跳转，但准入控制台从不读 `location.search`，点过去等于打开一张空表单。
- 控制台新增 `readIncoming` / `applyIncoming` / `renderIntakeNotice`：带入 model_id + revision + weights_uri，实时列出还差哪些标准必填项（§7.3 intended_use、§8/§11 named_owner）。
- 带入模型时不再 `restore()` 上一份申请，否则页面显示的是另一个模型的评审过程。
- 浮动标签防线：带过来的 revision 命中 main/latest/master/head 一律不填，逼评审人指定不可变版本（§6.1 / G1-PROV-02）。
- 发起方改用 `buildClearanceHref(m)`，卡片与弹窗两个入口共用，顺带带上 `latest_version` 与 `weights_url`。
- run 按钮问题：`#btn-engine-start` 在页头，带入模型时视图停在下方表单卡片，按钮被滚出视野。解法是把「启动准入评审」按钮直接放进提示条，启动后滚到时间线。
- 顺手修掉一个静默失败：`createApplication` / `submitApplication` 拿到 null 不再直接清空控制台，改为回填错误原因并提示。
- 端到端：DeepSeek-V3 走完 9 道门禁，时间线逐条出结果，报告 8 个 block，裁决 Approved。

## 2026-08-31 按钮文字对比度（taste-light 特异度冲突）

- 现象：报告区按钮文字灰暗不可读，实测 `#4B5568` 压 `#0f172a`，对比度 2.38:1。
- 误判过程：先当成 `:disabled` 默认样式，加了 `.btn:disabled` 无效；扫描 `document.styleSheets` 的写法有 bug，一度得出「没有任何规则匹配」的错误结论。
- 真因：`taste-light.css` 的 `html.taste-light .btn, ... .btn-sm { color: var(--tg-ink-2) }` 特异度 (0,2,1) 压过页面裸 `.btn` (0,1,0)，无需 !important。主题假定 .btn 是浅色按钮，本页却是深底实心按钮。
- 解法：页面内联 `<style>` 在 taste-light.css 之后加载，用同特异度 `html.taste-light .btn` 夺回。修复后 17.85:1。

## 2026-09-01 准入门禁流水线步骤与执行智能体可视化展示

- 在准入流水线 9 道门禁泳道（G0-G8）的卡片头部增加了明确的「步骤序号」与「状态徽标」：
  - `步骤 #1` ~ `步骤 #9`，对应 standard 章节顺序。
  - 状态标签支持 `待执行`、`执行中...`、`通过 ✓`、`未通过 ✗`、`待补证 ?`、`未执行`。
- 在每个门禁泳道标题下方展示专属的负责智能体卡片与当前执行动态：
  - 例如 `🤖 基础设施架构师 [mc_infra]`、`🤖 供应链与制品完整性工程师 [mc_supply]`、`🤖 AI模型安全审核人 [mc_security]`、`🤖 红队与威胁情报分析师 [mc_redteam]`、`🤖 AI模型法务审核人 [mc_legal]`、`🤖 持续保障与运营负责人 [mc_operations]`。
  - 动态执行状态文字：`mc_infra 取证完成 (1项)`、`mc_legal 待补: G7-USE-02`、`🤖 mc_infra 正在审核...`、`mc_infra 待命`。
- 泳道边框支持运行中发光（`is-running`）、通过绿框（`is-pass`）、失败红框（`is-fail`）、待补证黄框（`is-needs_info`）的状态变色。
- 新增/更新单元测试，前端 44 项 tests、后端 64 项 clearance tests 全部通过，实机浏览器端到端截图验证通过。

## 2026-09-07 数据情报默认开放权重页

| 17:11 | 将「开放权重资源」移至主 Tab 首位并设为无查询参数时的默认页；保留显式 `?tab=` 行为，测试及浏览器实测通过 | `src/frontend/data-intelligence.html`, `src/frontend/js/data-intelligence.js`, `src/frontend/__tests__/data-intelligence-brief.test.js` | PASS（Vitest 6/6，JS syntax，localhost:5173） | ~1k |
| 11:45 | 修复模型准入 G1 假失败认知与终态重试：模型审核不依赖申请人/用途/负责人，未知制品证据标待补证，流水线新增可用启动/重试按钮，参考情报删除控件去失败化 | `src/backend/domain/api_routes.py`, `src/backend/domain/model_clearance/*`, `src/frontend/ai-model-entry-clearance.html`, `src/frontend/js/{ai-model-entry-clearance,engine-state}.js`, clearance tests | PASS（后端 18、前端 18、py_compile；浏览器确认按钮发起请求，受登录态阻断后续） | ~5k |

## 2026-09-11 启动服务

| 16:17 | npm start 启动后端+前端 | concurrently / main.py / vite | 前端 http://localhost:5173/ ；后端 0.0.0.0:8080 Application startup complete | ~0.2k |
