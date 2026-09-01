# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-07-11T16:32:13.139Z
> Files: 511 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `PLAN.md` — 模型准入与运营控制总纲；已切换为 Lenovo 可管可证优先（来源降权、控管优先）；§11 记录控制台↔准入引擎对接架构
- `TODOS.md` — 准入系统执行清单；P0–P10（TA01–TA09 控制台真实对接）全阶段已全部完成
- `src/frontend/__tests__/clearance-cockpit-wiring.test.js` — 控制台去金融化与准入 API 真实对接回归测试
- `scripts/audit_sampling.py` — 每周活跃准入模型抽样审计与可验证性检查脚本
- `tests/test_model_clearance_operability.py` — Lenovo 直管矩阵、Kill-Switch、Rollback 与抽样审计测试用例
- `src/frontend/plaza.html` — 议事广场页面；接入共享 i18n 脚本与顶部语言切换按钮
- `src/frontend/js/plaza.js` — 议事广场交互、3D 场景和页面专用中英词条；动态翻译观察器避免自触发循环
- `tests/test_workflow_pipeline_mode.py` — 团队流水线模式与多智能体分工验证用例（AgentTeam + TeamStore + _generate_workflow 角色匹配）
- `docs/任务页面Build与AWS运维流程优化plan.md` — Build System/AWS 运维任务页面流程审计与分阶段优化计划
- `docs/任务页面Build与AWS运维流程优化todos.md` — Build System/AWS 运维任务页面可执行任务与验收清单
- `docs/论文对齐plan.md` — 论文《Agent skill evolution under ecological selection》24 项机制 vs 代码的逐条缺口表与分期规划
- `docs/论文对齐todos.md` — 论文对齐 P0-P2 全部 10 项任务（已全量完成，50 项测试通过）
- `src/backend/agents/skill_gates.py` — 论文 Section 5.1/5.2 六道验证门统一裁决引擎与证据三元组 (b_m, r_m, E_m)
- `src/backend/agents/version_competition.py` — 论文 Section 5.4 版本竞争与 Student-t 单侧下置信界 LCB 裁决
- `src/backend/agents/task_bounded_fitness.py` — 论文 Section 5.3 任务界定适应度六因子加权与配置指纹落盘
- `src/backend/agents/memory_contamination.py` — 论文 Section 7.14 记忆迁移高召回污染筛查与隔离
- `src/backend/agents/tse/dartnet.py` — 论文 Section 4.4 DART-Net 门面装配与感受野公式
- `src/backend/agents/plaza_challenge_routing.py` — 论文 Eq.(3)(4) 的 Γ_k：CHALLENGE 按 Niche 环回退 ORID 阶段，带每对回退预算与硬上限防死循环
- `src/backend/sandbox/eco_feedback.py` — 论文 §5.7 差异化留存证据回流：drill 结果抽取持续留存组合/未覆盖需求/反复失败 → 落盘 → Plaza O 阶段注入
- `src/backend/tests/test_skill_gates.py` — 六门裁决单元测试（10 用例）
- `src/backend/tests/test_version_competition.py` — 版本竞争与 LCB 测试（5 用例）
- `src/backend/tests/test_task_bounded_fitness.py` — 任务界定适应度测试（3 用例）
- `src/backend/tests/test_memory_contamination.py` — 记忆污染筛查测试（2 用例）
- `src/backend/tests/test_swei_import_gates.py` — SWEI 导入五道具名门测试（2 用例）
- `src/backend/tests/test_lifecycle_v2.py` — 生命周期六态与 2-of-3 去抖测试（3 用例）
- `src/backend/tests/test_skill_router_paper_alignment.py` — 路由状态硬过滤与字符 n-gram 测试（3 用例）
- `src/backend/tests/test_paper_p2_routing_feedback.py` — P2-8/P2-9 自检测试（17 用例）
- `src/backend/tests/test_dartnet_and_niche.py` — DART-Net、12-Niche 三环与共识公式测试（5 用例）

- `.dockerignore` — Docker ignore rules (~48 tok)
- `.DS_Store` (~2729 tok)
- `.gitignore` — Git ignore rules (~103 tok)
- `AgentCostContainerTodo.md` — AgentsGroup K8s 容器化 & OpenCost 真实成本数据链路 — 工作项 (~1214 tok)
- `AgentDigitalTwinPlan.md` — Agent Digital Twin 全局优化计划 (~1122 tok)
- `AGENTS.md` — AGENTS.md (~599 tok)
- `claude.md` — OpenWolf (~643 tok)
- `Dockerfile` — Docker container definition (~146 tok)
- `FrontBackEndOptimize.md` — 前后端代码优化建议 (Frontend + Backend) (~2527 tok)
- `FrontBackEndTodos.md` — FrontBackEnd TODOs — 完整任务清单 (~604 tok)
- `OptimizePlan.md` — OptimizePlan: AgentsGroup2026 Core Evolution Board (~4579 tok)
- `OptimizePlan1.md` — OptimizePlan1 — 前后端全貌优化方案 (~2770 tok)
- `OptimizePlan1Todos.md` — OptimizePlan1 — 前后端统一 TODOs (~1545 tok)
- `OptimizePlanTodos.md` — OptimizePlanTodos: AgentsGroup2026 Execution Board (~4840 tok)
- `output.log` (~2473 tok)
- `package-lock.json` — npm lock file (~17161 tok)
- `package.json` — Node.js package manifest (~261 tok)
- `pyproject.toml` — Python project configuration (~193 tok)
- `README.md` — 智能体数字孪生与效能演进平台核心介绍、技术栈与规模矩阵、九大业务域、19 页面全景、核心机制与权威文档导航 (~13000 tok)
- `SandboxTwinFrontendTodos.md` — sandbox-twin.html 前端剩余工作交接 (~1908 tok)
- `SECSOptimize.md` — SECSOptimize — sandbox-twin.html 功能手册 & 优化清单 (~2024 tok)
- `start_run.log` (~1932 tok)
- `start.bat` (~27 tok)
- `start.log` (~162748 tok)
- `start.ps1` — AgentsGroup2026 — Windows Start Script (~1612 tok)
- `start.sh` — AgentsGroup2026 — Quick Start Script (~2195 tok)
- `startup_new.log` (~914 tok)
- `startup.log` (~902 tok)
- `vite.config.mjs` — Declares frontendRoot (~358 tok)

## .claude/

- `settings.json` (~441 tok)
- `settings.local.json` (~714 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## .codebuddy/plans/

- `agent-digital-twin-button-level-refactor_a1d7a84c(未完成).md` — 产品定位 (~1884 tok)
- `agent-digital-twin-button-level-refactor_a44b6751.md` — 产品定位 (~2354 tok)
- `agent-digital-twin-button-level-refactor_a64267f8(未完成).md` — 需求概述 (~802 tok)
- `agentsgroup-k8s-cost-deployment_8a0a7981.md` — 用户需求 (~1019 tok)
- `digital-twin-vision-center-refactor_1a545acd.md` — Product Overview (~2083 tok)
- `revise-todos-with-all-buttons_aa15681a.md` — 用户需求 (~564 tok)
- `sandbox-twin-global-optimize_de0918c7.md` (~332 tok)
- `sandbox-twin-optimization_14c6e0bc(未完成).md` — 产品概述 (~1455 tok)
- `system-evolution-optimization_802df068(未完成).md` — 用户需求 (~1051 tok)

## .github/workflows/

- `backend-tests.yml` — CI: Backend Tests (~257 tok)
- `sandbox-docker.yml` — CI: Sandbox Docker Self Check (~227 tok)

## .huashu-skills/

- `.DS_Store` (~3263 tok)
- `README.md` — Project documentation (~985 tok)

## .huashu-skills/huashu-agent-swarm/

- `.DS_Store` (~1639 tok)
- `SKILL.md` — Infinite Agent Loop - 无限Agent蜂群模式 (~576 tok)

## .huashu-skills/huashu-agent-swarm/references/

- `agent-prompt-template.md` — 项目：{PROJECT_NAME} (~636 tok)
- `carlini-lessons.md` — Carlini实验经验教训 (~405 tok)

## .huashu-skills/huashu-agent-swarm/scripts/

- `agent_loop.sh` — agent_loop.sh - 单个Agent的无限循环逻辑 (~727 tok)
- `dashboard.py` — run_cmd, get_status, send_human_input (~5962 tok)
- `send_input.sh` — send_input.sh - 向蜂群发送人类指令 (~238 tok)
- `setup_project.sh` — setup_project.sh - 初始化项目结构，为蜂群模式做准备 (~649 tok)
- `start_swarm.sh` — start_swarm.sh - 启动Agent蜂群（tmux多pane） (~876 tok)
- `status.sh` — status.sh - 查看蜂群状态 (~714 tok)
- `stop_swarm.sh` — stop_swarm.sh - 停止所有Agent并清理worktrees (~598 tok)

## .huashu-skills/huashu-article-edit/

- `SKILL.md` — 文章编辑 Skill (~230 tok)

## .huashu-skills/huashu-article-to-x/

- `SKILL.md` — 长文转X内容 (~311 tok)

## .huashu-skills/huashu-data-pro/

- `.DS_Store` (~1639 tok)
- `SKILL.md` — 数据分析与办公提效助手 (~928 tok)

## .huashu-skills/huashu-data-pro/references/

- `ad-analytics.md` — 投放/广告分析领域知识 (~188 tok)
- `html-templates.md` — HTML可视化模板库 (~3765 tok)
- `report-style-gallery.md` — 可视化报告风格库 (~1515 tok)
- `visual-design-system.md` — 视觉设计系统 — 数据分析与办公场景 (~3580 tok)
- `workflows.md` — 详细工作流参考 (~1157 tok)

## .huashu-skills/huashu-data-pro/scripts/

- `build_pptx.js` — build_pptx.js — 将多个 HTML 幻灯片文件构建为一个 PPTX 文件 (~1791 tok)
- `html2pptx.js` — html2pptx - Convert HTML slide to pptxgenjs slide with positioned elements (~10789 tok)
- `read_excel.py` — ensure_dependencies, read_excel, main (~993 tok)
- `read_pptx.py` — ensure_dependencies, read_pptx, export_thumbnails, main (~2010 tok)

## .huashu-skills/huashu-design/

- `SKILL.md` — Design Philosophy Consultant (~1077 tok)

## .huashu-skills/huashu-design/references/

- `critique-guide.md` — 设计评审深度指南 (~868 tok)
- `design-styles.md` — 设计哲学风格库：20种体系 (~3296 tok)
- `scene-templates.md` — 场景模板库：按输出类型组织 (~1297 tok)

## .huashu-skills/huashu-douyin-script/

- `.DS_Store` (~1639 tok)
- `install.sh` — douyin-viral-script skill 安装脚本 (~476 tok)
- `SKILL.md` — 抖音爆款脚本创作 (~1681 tok)

## .huashu-skills/huashu-douyin-script/references/

- `analysis-dimensions.md` — 抖音爆款视频分析维度框架 (~674 tok)
- `proven-formulas.md` — 已验证的爆款公式库 (~727 tok)
- `script-style-samples.md` — 真实脚本样本库（口语风格参考） (~710 tok)

## .huashu-skills/huashu-douyin-script/scripts/

- `analyze_video.py` — /// script (~2186 tok)
- `download_douyin.py` — /// script (~1840 tok)

## .huashu-skills/huashu-image-upload/

- `SKILL.md` — 图片配图与上传 (~989 tok)

## .huashu-skills/huashu-info-search/

- `SKILL.md` — 信息搜索与知识管理 (~320 tok)

## .huashu-skills/huashu-material-search/

- `SKILL.md` — 个人素材库搜索 (~1306 tok)

## .huashu-skills/huashu-md-to-pdf/

- `EXAMPLES.md` — Markdown to PDF Skill 使用示例 (~679 tok)
- `README.md` — Project documentation (~377 tok)
- `SKILL.md` — Markdown to PDF Skill (~642 tok)

## .huashu-skills/huashu-md-to-pdf/scripts/

- `convert.py` — extract_metadata, extract_toc_structure, generate_toc_html, create_cover_and_toc + 4 more (~4600 tok)

## .huashu-skills/huashu-prompt-save/

- `SKILL.md` — Prompt分类保存 (~319 tok)

## .huashu-skills/huashu-proofreading/

- `SKILL.md` — AI味审校 (~1226 tok)

## .huashu-skills/huashu-research/

- `SKILL.md` — 调研 Skill (~367 tok)

## .huashu-skills/huashu-script-polish/

- `SKILL.md` — 视频脚本口语化审校 (~254 tok)

## .huashu-skills/huashu-slides/

- `.DS_Store` (~1638 tok)
- `SKILL.md` — AI Presentation Workflow (~7091 tok)

## .huashu-skills/huashu-slides/assets/

- `.DS_Store` (~1640 tok)

## .huashu-skills/huashu-slides/references/

- `design-movements.md` — 设计运动与风格参考库 (~1146 tok)
- `design-principles.md` — Presentation Design Principles (~1989 tok)
- `prompt-templates.md` — Presentation Prompt Templates (~5872 tok)
- `proven-styles-gallery.md` — Proven Styles Gallery: 18 Tested Visual Styles for AI Slides + 5 Professional Editorial Styles (~1902 tok)
- `proven-styles-snoopy.md` — Proven Style Guide: Snoopy / Peanuts 温暖漫画风 (~594 tok)

## .huashu-skills/huashu-slides/scripts/

- `create_slides.py` — /// script (~2756 tok)

## .huashu-skills/huashu-speech-coach/

- `SKILL.md` — 演讲教练 Presentation Coach (~1285 tok)

## .huashu-skills/huashu-speech-coach/references/

- `patrick-winston-how-to-speak.md` (~1209 tok)

## .huashu-skills/huashu-topic-gen/

- `SKILL.md` — 选题生成 (~304 tok)

## .huashu-skills/huashu-video-check/

- `SKILL.md` — 视频封标与承接检查 (~1410 tok)

## .huashu-skills/huashu-video-outline/

- `SKILL.md` — 视频大纲生成 (~264 tok)

## .huashu-skills/huashu-wechat-image/

- `.DS_Store` (~1639 tok)
- `SKILL.md` — 公众号配图工作流 (~2390 tok)

## .huashu-skills/huashu-wechat-image/references/

- `design-guidelines.md` — 公众号平台设计规范 (~1193 tok)
- `style-gallery.md` — 公众号配图风格库 (~1419 tok)

## .huashu-skills/huashu-wechat-image/scripts/

- `generate_image.py` — /// script (~2082 tok)

## .huashu-skills/huashu-xhs-image/

- `.DS_Store` (~1639 tok)
- `SKILL.md` — 小红书配图工作流 (~1502 tok)

## .huashu-skills/huashu-xhs-image/references/

- `design-guidelines.md` — 小红书平台设计规范 (~774 tok)
- `style-gallery.md` — 小红书配图风格库 (~1360 tok)

## .huashu-skills/huashu-xhs-image/scripts/

- `generate_image.py` — /// script (~1791 tok)

## .playwright-cli/

- `console-2026-06-07T11-09-48-084Z.log` (~2698 tok)
- `console-2026-06-11T03-47-50-613Z.log` (~2470 tok)
- `page-2026-06-07T11-09-49-895Z.yml` (~231 tok)
- `page-2026-06-07T11-10-12-175Z.yml` (~231 tok)
- `page-2026-06-11T03-47-52-885Z.yml` (~231 tok)
- `page-2026-06-11T03-48-04-747Z.yml` (~231 tok)
- `page-2026-06-11T03-48-19-120Z.yml` (~232 tok)
- `page-2026-06-11T03-48-28-883Z.yml` (~233 tok)
- `page-2026-06-11T03-48-36-067Z.yml` (~1972 tok)
- `page-2026-06-11T03-48-57-232Z.yml` (~5816 tok)
- `page-2026-06-11T03-50-22-884Z.yml` (~1972 tok)

## .pytest_cache/

- `.DS_Store` (~1639 tok)
- `.gitignore` — Git ignore rules (~10 tok)
- `CACHEDIR.TAG` (~51 tok)
- `README.md` — Project documentation (~76 tok)

## .pytest_cache/v/

- `.DS_Store` (~1640 tok)

## .pytest_cache/v/cache/

- `lastfailed` (~904 tok)
- `nodeids` (~30602 tok)

## _temp/design-demos/

- `demo-fieldio-particles.html` — Demo B — Field.io 粒子生成艺术 (~2959 tok)
- `demo-lupi-data-humanism.html` — Demo C — Giorgia Lupi 数据人文主义 (~3605 tok)
- `demo-takram-biosynthetic.html` — Demo A — Takram 思辨生物学 (~3717 tok)

## config/

- `.api_keys.json` (~232 tok)
- `.dev_admin_password` (~6 tok)
- `.master_key` (~12 tok)
- `model_pool.json` (~849 tok)
- `settings.json` (~399 tok)
- `users.json` (~45160 tok)

## config/launchd/

- `com.agentsgroup.nightly-4h-optimize.plist` (~268 tok)
- `com.agentsgroup.nightly-global-loops.plist` (~287 tok)

## config/scenarios/

- `capacity_incident.json` (~1629 tok)
- `code_review_delivery.json` (~1616 tok)
- `cs_ticket_surge.json` (~1541 tok)
- `data_pipeline_recovery.json` (~1625 tok)
- `marketing_campaign.json` (~1370 tok)

## docker/sandbox/

- `Dockerfile` — Docker container definition (~148 tok)

## docs/

- `Agent数字孪生优化plan.md` — Agent 数字孪生优化计划 (~5452 tok)
- `Agent数字孪生优化todos.md` — Agent 数字孪生 — 按钮级功能 TODO（代码对齐版） (~2430 tok)
- `Agent数字孪生场景演练与技能进化plan.md` — Agent 数字孪生 v4 — 场景化演练 × 技能进化闭环 Plan (~1829 tok)
- `Agent数字孪生场景演练与技能进化todos.md` — Agent 数字孪生 v4 — 场景化演练 × 技能进化 TODOS（代码对齐版） (~4710 tok)
- `EVOLUTION_PLAN.md` — AgentsGroup 系统演进 — 自我进化优化管线 (~4994 tok)
- `NIGHTLY_0000_4H_PLAN.md` — Nightly 00:00-04:00 Optimization Plan (~782 tok)
- `全局优化todos.md` — AgentsGroup2026 全局优化 TODOS（v1.0） (~1835 tok)
- `全局优化计划.md` — AgentsGroup2026 全局优化计划（Global Optimization Plan v1.0） (~1836 tok)

## k8s/

- `agentsgroup-configmap.yaml` — K8s ConfigMap: agentsgroup-config (~518 tok)
- `agentsgroup-deployment.yaml` — K8s Deployment: agentsgroup (~700 tok)
- `agentsgroup-namespace.yaml` — K8s Namespace: agentsgroup (~62 tok)
- `agentsgroup-secret.yaml` — K8s Secret: agentsgroup-secret (~87 tok)
- `agentsgroup-service.yaml` — K8s Service: agentsgroup (~118 tok)
- `agentsgroup-teams-deployment.yaml` — ===== Team: build_system ===== (~3044 tok)
- `kind-cluster.yaml` — K8s Cluster (~207 tok)

## scripts/

- `build_sandbox_image.sh` (~417 tok)
- `frontend_build.sh` (~157 tok)
- `frontend_test.sh` (~150 tok)
- `nightly_4h_optimize.sh` (~3507 tok)
- `start_tts.sh` — Start GPT-SoVITS TTS API server (~266 tok)
- `verify_v4_local.sh` — 本机一键复核 v4 接口通路门+全程回归，全绿回写 [~]→[x] (~700 tok)
- `verify_eco_feedback_xf.py` — 物竞反馈台 XF + 物竞×成本 XC + Token 治理 TG 符号验收(~1000 tok)

## src/

- `.DS_Store` (~1639 tok)

## src/agentsgroup2026.egg-info/

- `dependency_links.txt` (~1 tok)
- `PKG-INFO` (~123 tok)
- `requires.txt` (~37 tok)
- `SOURCES.txt` (~1680 tok)
- `top_level.txt` (~8 tok)

## src/backend/

- `__init__.py` (~0 tok)
- `0tfuaiyp` (~2 tok)
- `agent_team_api.py` — -*- coding: utf-8 -*- (~12454 tok)
- `ci_cost_gate.py` — CI/CD Cost Gate CLI — Integration script for CI/CD pipelines. (~4954 tok)
- `config.py` — -*- coding: utf-8 -*- (~627 tok)
- `datacenter_api.py` — Lightweight datacenter ratchet API used by the self-evolving frontend. (~2862 tok)
- `main.py` — -*- coding: utf-8 -*- (~15636 tok)
- `main.py.bak` — -*- coding: utf-8 -*- (~9828 tok)
- `server.log` (~1922 tok)
- `startup_check.py` — -*- coding: utf-8 -*- (~527 tok)
- `startup_validator.py` — -*- coding: utf-8 -*- (~5291 tok)
- `token_factory.py` — Token Factory API — LLM inference infrastructure health & management. (~2383 tok)

## src/backend/agents/

- `__init__.py` (~0 tok)
- `ab_testing.py` — A/B测试框架 — 基于EWMA和Lamport时钟的因果一致性升级策略. (~10083 tok)
- `agent_loop.py` — Deprecated compatibility shim over the shared tool-loop runtime. (~610 tok)
- `agent_toolbox.py` — /*.py", (~4478 tok)
- `api.py` — AgentsGroup2026 Agent Team Framework -- REST API Router. (~107152 tok)
- `api.py.bak` — -*- coding: utf-8 -*- (~80932 tok)
- `audit_store.py` — 审核存储 — JSON 文件持久化，幂等写入. (~2249 tok)
- `chaos_engine.py` — -*- coding: utf-8 -*- (~10488 tok)
- `chat_harness.py` — AgentsGroup2026 Chat Harness — Unified LLM Chat Module. (~15164 tok)
- `cost_aggregator.py` — Cost Aggregator — OpenCost data polling, label-based aggregation & caching. (~8010 tok)
- `cost_gate_routes.py` — Cost Gate API Routes — FastAPI endpoints for CI/CD cost gate. (~4067 tok)
- `cost_models.py` — Cost monitoring data models — OpenCost integration & label-based aggregation. (~1364 tok)
- `cost_policy.py` — Cost Policy Engine — Terraform resource cost evaluation rules. (~12196 tok)
- `cost_policy.py.bak` — -*- coding: utf-8 -*- (~11229 tok)
- `cost_routes.py` — Cost monitoring REST API — OpenCost data query, aggregation, and dashboard endpoints. (~2254 tok)
- `domain_events.py` — Domain Events — 领域事件定义，携带完整上下文而非仅 ID。 (~2891 tok)
- `domain_events.py.bak` — -*- coding: utf-8 -*- (~2681 tok)
- `event_bus.py` — Event Bus — 轻量级进程内发布 / 订阅事件总线。 (~1522 tok)
- `evidence_store.py` — Unified evidence run storage for verifiable agent/system execution. (~4094 tok)
- `execution_registry.py` — AgentsGroup2026 Execution Registry — Unified command/tool routing & execution. (~4487 tok)
- `extraction_models.py` — 萃取管线状态机 — 数据模型 (Extraction Pipeline State Machine Models). (~2776 tok)
- `extraction_pipeline.py` — 萃取管线状态机 — Pipeline State Machine + Gate Validation. (~4461 tok)
- `extraction_pipeline.py.bak` — -*- coding: utf-8 -*- (~4133 tok)
- `extraction_routes.py` — 萃取管线 REST API — State Transitions + Todo-driven API. (~4105 tok)
- `extraction_store.py` — 萃取管线事件溯源存储 — Append-only Event Store. (~4388 tok)
- `fingerprint.py` — -*- coding: utf-8 -*- (~7247 tok)
- `fingerprint.py.bak` — -*- coding: utf-8 -*- (~6748 tok)
- `gate_evaluator.py` — 门禁评估器 — 无状态纯函数 evaluate(context) → {score, level}. (~2261 tok)
- `hermes_research.py` — AgentsGroup2026 — Hermes-style Research Agent Module. (~4970 tok)
- `k8s_webhook_handler.py` — K8s MutatingAdmissionWebhook handler for cost label auto-injection. (~3264 tok)
- `knowledge_base.py` — AgentsGroup2026 Agent Knowledge Base — Document store with RAG search. (~2667 tok)
- `merge_engine.py` — Merge Engine — asynchronous similarity-based merge processor. (~3344 tok)
- `merge_models.py` — Similarity Merge Plugin — Core Data Models. (~2204 tok)
- `models.py` — AgentsGroup2026 Agent Team Framework — Core Data Models. (~4881 tok)
- `models.py.bak` — -*- coding: utf-8 -*- (~3822 tok)
- `operation_api.py` — 操作事件 & 情境切片 API — 查询/追溯/统计 REST 端点. (~4565 tok)
- `operation_models.py` — 操作事件 & 情境切片数据模型 — OperationEvent & ContextSlice. (~4011 tok)
- `operation_store.py` — 操作存储 — JSON 文件持久化，append-only 不可变存储。 (~6098 tok)
- `plaza_consensus.py` — Plaza 五指量表(Fist-to-Five) + ORID 决策层共识度量与根本性反对检测. (~1701 tok)
- `plaza_engine.py` — 智能体广场引擎 — ORID 四层(事实→风险→对立辩论→五指决策)审议编排与多 Agent 协同. (~13420 tok)
- `plaza_routes.py` — 智能体广场 API 路由 + SSE 实时推送. (~15114 tok)
- `plaza_routes.py.bak` — -*- coding: utf-8 -*- (~3180 tok)
- `plaza_store.py` — 广场持久化存储 — 将广场、参与者、讨论及消息序列化到 JSON 文件. (~2396 tok)
- `plaza.py` — 智能体广场 — 数据模型. (~2140 tok)
- `plaza.py.bak` — -*- coding: utf-8 -*- (~1998 tok)
- `ratchet_ledger.py` — Ratchet Ledger — 全局正向棘轮账本 (全局优化 G-4). (~1840 tok)
- `ratchet_routes.py` — Ratchet API — 全局正向棘轮账本 (全局优化 G4-4). (~408 tok)
- `review_models.py` — 门禁评估与审核数据模型 — Gate Evaluation & Review Data Models. (~1934 tok)
- `review_routes.py` — 审核路由 — SSE 推送审核队列变化 + 状态更新 API. (~2722 tok)
- `review_service.py` — 审核服务 — ReviewService 幂等记录审核动作并回写版本增量. (~3548 tok)
- `secret_store.py` — provider_api_key_envs, load_secret_store, save_secret_store, load_model_api_keys + 4 more (~1696 tok)
- `session_store.py` — AgentsGroup2026 Session Store — Persistent session storage. (~1364 tok)
- `similarity_engine.py` — Similarity Engine — pluggable similarity computation strategies. (~2428 tok)
- `skill_classifier_routes.py` — Skill Classification API — 技能三类分类 (全局优化 G2-4). (~724 tok)
- `skill_classifier.py` — Skill Classifier — 技能三类分类器 (全局优化 G-2). (~3164 tok)
- `skill_evolver.py` — 技能演化引擎 — Evidence→Attribution→Evolution. (~2666 tok)
- `skill_extract_ws.py` — -*- coding: utf-8 -*- (~3018 tok)
- `skill_extractor.py` — 技能萃取引擎 — approve_item 支持跨团队赋予(target_team_id)与团队级特质(assign_scope=team). (~11669 tok)
- `skill_indexer.py` — SkillIndexer — 异步 Indexing Worker，消费领域事件构建向量索引。 (~3443 tok)
- `skill_publish_gate.py` — 技能发布量化门禁 (pass_rate/twin gain/samples, env AG_SKILL_PUBLISH_*). (~2.5k tok)
- `skill_library.py` — 统一技能库 — 桥接 SkillRegistry + SkillStore + Team-local 三套存储. (~6985 tok)
- `skill_querier.py` — SkillQuerier — 技能检索器，带衰减策略与相关性排序。 (~2952 tok)
- `skill_registry.py` — AgentsGroup2026 Agent Team Framework — Skill Registry. (~6750 tok)
- `skill_router_routes.py` — SkillRouter API routes — /api/v1/skill-router. (~1701 tok)
- `skill_router.py` — SkillRouter — 2-Stage Retrieve-and-Rerank skill selection for agents. (~11211 tok)
- `skill_store.py` — SkillStore — 技能主表持久化，支持幂等写入与 schema_version。 (~3402 tok)
- `skill_tracker.py` — 技能效果追踪器 — 订阅 EventBus 的 TASK_COMPLETED 事件，更新技能使用指标. (~1605 tok)
- `skill_verifier.py` — 技能验证框架 — 自动生成测试场景 → 沙箱执行 → 评估 pass_rate. (~6355 tok)
- `sustainability_routes.py` — Sustainability API — Token 可持续性评估 (全局优化 G5-4). (~1205 tok)
- `sustainability.py` — Sustainability Evaluator — Token 可持续性评估器 (全局优化 G-5). (~4190 tok)
- `task_engine.py` — AgentsGroup2026 Agent Team Framework -- Concurrent Task Execution Engine. (~4720 tok)
- `task_engine.py.bak` — -*- coding: utf-8 -*- (~3901 tok)
- `task_store.py` — 任务持久化存储 — 将任务序列化到 JSON 文件. (~614 tok)
- `team_manager.py` — AgentsGroup2026 Agent Team Framework — Team Manager. (~1727 tok)
- `team_manager.py.bak` — -*- coding: utf-8 -*- (~1717 tok)
- `team_store.py` — 团队持久化存储 — 将团队配置序列化到 JSON 文件. (~3082 tok)
- `tool_executor.py` — AgentsGroup2026 Tool Executor — Actually runs tools when agents invoke them. (~18380 tok)
- `tool_registry.py` — AgentsGroup2026 Agent Team Framework — Tool Registry. (~6506 tok)
- `trajectory_analyzer.py` — 轨迹分析器 — LLM分析会话 → 提取 skills_referenced / outcome / evidence. (~1667 tok)
- `tts_routes.py` — TTS route — Edge-TTS (Microsoft Neural) as primary engine. (~3581 tok)

## src/backend/agents/budget/

- `__init__.py` (~115 tok)
- `guard.py` — BudgetExceededError: save_budget_settings, update_budget, check, record_usage + 2 more (~1507 tok)
- `models.py` — class: to_dict, date, date (~453 tok)
- `store.py` — UsageStore: record_usage, record_event, get_session_total, get_agent_daily_total + 4 more (~2221 tok)

## src/backend/agents/evolution/

- `__init__.py` — 演化优化引擎 — Qwen3 反思式演化 (类GEPA). (~75 tok)
- `auto_triage.py` — 自动诊断 — 识别最弱目标并触发优化. (~1563 tok)
- `comparator.py` — 对比器 — baseline vs evolved 并排对比. (~917 tok)
- `constraints.py` — 约束验证器 — 确保演化变体在安全边界内. (~852 tok)
- `dataset_builder.py` — 评估数据集生成器 — 多来源构建 train/val/holdout. (~2442 tok)
- `fitness.py` — Fitness 评分函数 — LLM-as-Judge. (~2677 tok)
- `mutator.py` — 反思式变异器 — Qwen3 驱动 (类GEPA). (~2451 tok)
- `optimizer.py` — 主优化循环 — 照搬 Hermes Optimization Loop. (~4250 tok)

## src/backend/agents/runtime/

- `__init__.py` — Shared runtime helpers for agent execution loops. (~288 tok)
- `events.py` — Shared runtime event envelope helpers. (~315 tok)
- `plan_loop.py` — Shared plan-based loop runtime used by ChatHarness agent_loop APIs. (~2744 tok)
- `state_machine.py` — Unified State Machine + Watchdog for Agent / Task / Session states. (~2521 tok)
- `tool_loop.py` — Shared multi-turn tool loop runtime used by coding agents. (~4626 tok)

## src/backend/agents/security/

- `__init__.py` — Security helpers for agent tool execution. (~14 tok)
- `permission_resolver.py` — PermissionResolver: build_context, filter_tool_names (~1498 tok)

## src/backend/agents/skills/

- `__init__.py` (~0 tok)
- `greeting.py` — Greeting tool function — returns a simple greeting message. (~97 tok)
- `hello.py` — Hello-world skill module — end-to-end pipeline verification. (~94 tok)

## src/backend/agents/teams/

- `__init__.py` (~0 tok)
- `ai_coding_team.py` — AI 编程团队 — 专注软件开发的智能体团队. (~2030 tok)
- `build_team.py` — create_build_team (~2862 tok)
- `cloud_ops_team.py` — -*- coding: utf-8 -*- (~3215 tok)
- `energy_team.py` — Energy First Principle — 数据中心能耗第一性原理团队. (~3197 tok)
- `xops_team.py` — 公有云 xOPs 团队 — 多云运维与平台工程智能体团队. (~4214 tok)

## src/backend/channels/

- `__init__.py` (~0 tok)
- `bridge_chat.py` — -*- coding: utf-8 -*- (~5326 tok)
- `cost_channel.py` — Cost Monitoring Channel — MarineChannel for OpenCost integration. (~2374 tok)
- `cost_channel.py.bak` — -*- coding: utf-8 -*- (~2302 tok)
- `cost_gate.py` — Cost Gate Channel — CI/CD Cost Gate based on Terraform Policy. (~4838 tok)
- `cost_gate.py.bak` — -*- coding: utf-8 -*- (~4395 tok)
- `cost_monitor.py` — Cost Monitor Channel — 成本异常监控与 SLO 告警 Channel. (~8724 tok)
- `cost_rollback.py` — Cost Rollback Channel — 成本异常应急回滚操作 Channel. (~10283 tok)
- `cost_rollback.py.bak` — -*- coding: utf-8 -*- (~9602 tok)
- `event_bridge.py` — Channel-Event Bridge — connects EventBus to Marine Channel system. (~2253 tok)
- `evolution_executor.py` — -*- coding: utf-8 -*- (~2956 tok)
- `marine_base.py` — -*- coding: utf-8 -*- (~3464 tok)
- `merge_channel.py` — Merge Channel — MarineChannel wrapper for the Similarity Merge Plugin. (~3771 tok)
- `network_egress.py` — -*- coding: utf-8 -*- (~5989 tok)
- `openclaw_sync.py` — OpenClaw 智能体同步 Channel — 基于 MarineChannel 的因果一致性同步模块. (~4566 tok)
- `openclaw_sync.py.bak` — -*- coding: utf-8 -*- (~4058 tok)
- `storage_lifecycle.py` — -*- coding: utf-8 -*- (~6116 tok)
- `system_evolution.py` — -*- coding: utf-8 -*- (~25241 tok)

## src/backend/monitoring/

- `__init__.py` — -*- coding: utf-8 -*- (~230 tok)
- `__init__.py.bak` — -*- coding: utf-8 -*- (~215 tok)
- `aggregation_window.py` — Aggregation Window Engine — sliding-window state management, persistence, (~8095 tok)
- `aggregation_window.py.bak` — -*- coding: utf-8 -*- (~7472 tok)
- `collector.py` — -*- coding: utf-8 -*- (~2219 tok)
- `collector.py.bak` — -*- coding: utf-8 -*- (~2071 tok)
- `fingerprint_bypass.py` — -*- coding: utf-8 -*- (~3976 tok)
- `models.py` — -*- coding: utf-8 -*- (~2917 tok)
- `models.py.bak` — -*- coding: utf-8 -*- (~2767 tok)
- `monitoring_routes.py` — -*- coding: utf-8 -*- (~2498 tok)
- `plaza_monitor.py` — -*- coding: utf-8 -*- (~4176 tok)
- `plaza_monitor.py.bak` — -*- coding: utf-8 -*- (~3873 tok)
- `sampler.py` — -*- coding: utf-8 -*- (~1316 tok)
- `trace_bridge.py` — -*- coding: utf-8 -*- (~4094 tok)
- `tracing.py` — OpenTelemetry integration — optional tracing for LLM / tool / task / plaza. (~1670 tok)

## src/backend/sandbox/

- `__init__.py` — SECS — Self-Evolving Collaborative Sandbox (自进化协同沙箱系统). (~92 tok)
- `api.py` — Sandbox API — FastAPI 路由 + SSE 实时流. (~6659 tok)
- `channel.py` — Sandbox Channel — MarineChannel 集成. (~1508 tok)
- `drift_detector.py` — Drift Detector — 环境偏移检测与仿真触发. (~2420 tok)
- `evolution_api.py` — Evolution API — 演练驱动技能进化 REST 接口 (v4 B-3). (~2444 tok)
- `evolution_bridge.py` — Evolution Bridge — 演练数据驱动的技能进化编排器 (v4 C-3). (~6164 tok)
- `global_critic.py` — Global Critic — DT-MADDPG 全局评论家. (~2976 tok)
- `llm_decision.py` — LLM 驱动的 Agent Twin 决策引擎. (~1687 tok)
- `memory_system.py` — Memory System — AAS 双记忆系统. (~2745 tok)
- `models.py` — SECS Core Data Models — 自进化协同沙箱核心数据模型. (~6239 tok)
- `orchestrator.py` — SECS Orchestrator — 系统编排器. (~3330 tok)
- `proficiency_store.py` — Proficiency Store — 技能使用记录 + 熟练度持久化 (v4 A-4.3/A-4.4). (~2342 tok)
- `python_runner_docker.py` — Docker-backed sandbox for stronger Python / pytest isolation. (~2058 tok)
- `python_runner_lite.py` — Lightweight Python / pytest sandbox for local development. (~3487 tok)
- `python_runner.py` — Shared sandbox facade for Python and pytest execution. (~1946 tok)
- `scenario_api.py` — Scenario API — 业务场景 REST 接口 (v4 B-1). (~1405 tok)
- `scenario_compiler.py` — Scenario Compiler — 场景实例化引擎 (v4 C-1). (~2224 tok)
- `scenario_models.py` — Scenario Models — 业务场景模型 (v4 A-1). (~3301 tok)
- `scenario_store.py` — Scenario Store — 场景库持久化 (v4 A-4.1). (~1315 tok)
- `strategy_aligner.py` — Strategy Aligner — 集体智慧对齐与协同优化. (~2067 tok)
- `trial_api.py` — Trial API — 数字孪生试炼三层模型 REST 接口. (~13149 tok)
- `trial_store.py` — 试炼存储 — JSON 文件持久化，幂等写入. (~2716 tok)
- `twin_loop.py` — TwinLoop Engine — 策略试错实验层 (仿真在环控制). (~16661 tok)
- `world_state.py` — World State Manager — MADTwin 环境语义映射层. (~2200 tok)
- `zero_exp_engine.py` — Zero-Exp Engine — AAS 认知进化循环层. (~2769 tok)

## src/backend/scripts/

- `__init__.py` — AgentsGroup2026 CLI scripts. (~17 tok)
- `migrate_trials_v4.py` — v4 存量 Trial 数据迁移 — 幂等 (A-4.5). (~518 tok)
- `migrate.py` — -*- coding: utf-8 -*- (~4811 tok)
- `nightly_global_loops.py` — Nightly 全局循环任务 — 每日技能重分类 + 可持续性报告 (全局优化 GP2-4). (~1817 tok)
- `validate_startup.py` — -*- coding: utf-8 -*- (~376 tok)
- `validate_telemetry.py` — -*- coding: utf-8 -*- (~3023 tok)

## src/backend/tests/

- `__init__.py` — AgentsGroup2026 Test Pipeline — 自动化测试流水线. (~48 tok)
- `conftest.py` — pytest 共享 Fixtures — 测试流水线基础设施. (~1185 tok)
- `conftest.py.bak` — -*- coding: utf-8 -*- (~1082 tok)
- `test_ab_testing.py` — A/B 测试框架单元测试 — LamportClock, EWMA, TrafficStainer, ABTestManager. (~4619 tok)
- `test_agent_skill_binding.py` — Agent-skill binding regression tests. (~2075 tok)
- `test_agent_toolbox.py` — AgentToolbox 单元测试 — 工具函数 (read_file, grep, list_files, dispatch). (~2690 tok)
- `test_api_handler_integration.py` — HTTP-level regressions for selected agent team and digital twin handlers. (~991 tok)
- `test_api_integration_extended.py` — Extended HTTP integration tests for core backend handlers. (~12810 tok)
- `test_api_pagination.py` — Pagination regressions for agent-config list endpoints. (~1547 tok)
- `test_api_rate_limit.py` — Regression tests for generic API rate limiting buckets. (~956 tok)
- `test_auth_csrf.py` — Tests: generate_returns_token, generated_token_is_valid, invalid_token_rejected, empty_token_rejected + 17 more (~3006 tok)
- `test_channel_event_bridge.py` — Tests for Channel-Event Bridge. (~1067 tok)
- `test_chaos_stability.py` — 混沌工程稳定性测试集 — Spot 实例 / 缓存 / 数据分层 SLO 验收. (~7814 tok)
- `test_core_api_smoke.py` — HTTP smoke coverage for core protected and public API paths. (~2794 tok)
- `test_cost_gate.py` — Cost Gate Tests — CI/CD Cost Gate comprehensive test suite. (~11167 tok)
- `test_cost_monitor.py` — Cost monitoring tests — OpenCost integration, label injection, and dashboard API. (~4314 tok)
- `test_datacenter_api.py` — Regression tests for the datacenter ratchet demo API. (~1050 tok)
- `test_evidence_store.py` — Unified EvidenceRun storage regressions. (~414 tok)
- `test_evolution_evidence_detail.py` — System evolution item evidence detail regressions. (~1092 tok)
- `test_evolution_race.py` — 审核流竞态与断网场景测试 — EvolutionExecutor / Audit 并发 & 网络容错. (~5445 tok)
- `test_evolution_race.py.bak` — -*- coding: utf-8 -*- (~4504 tok)
- `test_execution_evidence.py` — Agent execution EvidenceRun regressions. (~686 tok)
- `test_fingerprint.py` — Fingerprint 模块单元测试 — 模板提取、动态剔除、哈希、自检、稳定性监控. (~6672 tok)
- `test_fingerprint.py.bak` — -*- coding: utf-8 -*- (~6215 tok)
- `test_frontend_auth_contract.py` — Frontend auth/CSRF contract checks for cookie-only mode. (~775 tok)
- `test_gate_evaluator.py` — 测试门禁评估器 — evaluate(context) 纯函数测试. (~2606 tok)
- `test_gate_evaluator.py.bak` — -*- coding: utf-8 -*- (~2395 tok)
- `test_main_health.py` — Health endpoint regression tests. (~362 tok)
- `test_merge_plugin.py` — Similarity Merge Plugin — 单元测试. (~6701 tok)
- `test_merge_plugin.py.bak` — -*- coding: utf-8 -*- (~6263 tok)
- `test_models.py` — 数据模型单元测试 — AgentProfile, AgentTeam, ModelConfig 等. (~2939 tok)
- `test_models.py.bak` — -*- coding: utf-8 -*- (~1718 tok)
- `test_network_egress.py` — Network Egress Channel — 单元测试. (~2686 tok)
- `test_network_egress.py.bak` — -*- coding: utf-8 -*- (~2510 tok)
- `test_operation_store.py` — 操作事件 & 情境切片存储 单元测试. (~8556 tok)
- `test_permissions_and_secrets.py` — Security regression tests for secret resolution and tool permissions. (~2783 tok)
- `test_plan_loop_runtime.py` — Regression tests for the shared plan-loop runtime. (~1884 tok)
- `test_plaza_consensus.py` — Tests for plaza consensus measurement. (~1008 tok)
- `test_plaza_dispatch.py` — Plaza discussion dispatch tests. (~2946 tok)
- `test_plaza_evolution_bridge.py` — Plaza to evolution bridge tests. (~5000 tok)
- `test_plaza_retry_escalation.py` — Tests for Plaza retry + failure escalation. (~1776 tok)
- `test_plaza_structured_outputs.py` — Plaza structured output metadata regressions. (~863 tok)
- `test_plaza_task_artifact_bridge.py` — Plaza task artifact and evolution bridge tests. (~8551 tok)
- `test_qa_gate_pipeline.py` — QA Gate Pipeline 验证测试 — 当 QA verdict=PASS 时 pipeline 不应被阻断. (~6854 tok)
- `test_qa_gate_pipeline.py.bak` — -*- coding: utf-8 -*- (~6163 tok)
- `test_request_models.py` — Regression coverage for recently migrated Pydantic request models. (~1708 tok)
- `test_review_integration.py` — 审核集成测试 — 覆盖4阶段状态流转、异常跳转、交叉复核越权、带偏差标注数据下的复核准确率验证. (~9833 tok)
- `test_review_integration.py.bak` — -*- coding: utf-8 -*- (~9156 tok)
- `test_sandbox_docker.py` — Docker-backed sandbox integration tests. (~706 tok)
- `test_sandbox_security.py` — Security regression tests for lightweight sandboxed execution. (~3545 tok)
- `test_sandbox_smoke.py` — Minimal sandbox smoke test used by docker self-checks. (~50 tok)
- `test_security_headers.py` — Tests for security response headers and request_id middleware. (~590 tok)
- `test_skill_loop_e2e.py` — P2-1 skill closed loop e2e (verify→gate→publish→route). (~1.5k tok)
- `test_tse_experiments.py` — TSE paper 9.3/9.4 experiment unit+CLI tests. (~3k tok)
- `test_skill_publish_gate.py` — Skill publish quality gate regressions. (~1037 tok)
- `test_skill_verifier.py` — SkillVerifier sandbox evidence regressions. (~1614 tok)
- `test_start_script_auth_bootstrap.py` — Regression checks for local quick-start auth bootstrap. (~259 tok)
- `test_startup_validator.py` — Startup validator regressions for auth-protected runtime APIs. (~812 tok)
- `test_state_machine.py` — Tests for unified state machine + timeout watchdog. (~1322 tok)
- `test_storage_lifecycle.py` — Storage Lifecycle Channel — 单元测试. (~2701 tok)
- `test_storage_lifecycle.py.bak` — -*- coding: utf-8 -*- (~2524 tok)
- `test_task_engine.py` — 任务引擎单元测试 — TaskEngine / AgentTask 调度与状态管理. (~3541 tok)
- `test_task_engine.py.bak` — -*- coding: utf-8 -*- (~1927 tok)
- `test_team_manager.py` — 团队管理器单元测试 — TeamManager CRUD 操作. (~2173 tok)
- `test_team_manager.py.bak` — -*- coding: utf-8 -*- (~2088 tok)
- `test_template_variants.py` — 模板变体注入测试 — Plaza 多模板 XSS、结构完整性及 CSS 一致性验证. (~3514 tok)
- `test_template_variants.py.bak` — -*- coding: utf-8 -*- (~3202 tok)
- `test_token_budget.py` — Token budget and usage tracking regression tests. (~2597 tok)
- `test_unified_tool_loop.py` — Regression tests for the shared tool-loop runtime migration. (~2046 tok)

## src/docs/agent_handoffs/

- `017a695e-ad5_executor_started_20260611T093734.md` — Agent Handoff — executor_started (~110 tok)
- `017a695e-ad5_task_init_20260611T093733.md` — Agent Handoff — task_init (~170 tok)
- `01d37305-090_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~94 tok)
- `0261754d-288_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~123 tok)
- `02e075a5-5fb_executor_started_20260510T110855.md` — Agent Handoff — executor_started (~93 tok)
- `05014547-ce8_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~95 tok)
- `0597d622-ad4_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~95 tok)
- `05a62056-3a9_architecture_20260510T111409.md` — Agent Handoff — architecture (~135 tok)
- `05a62056-3a9_deploy_20260510T112220.md` — Agent Handoff — deploy (~166 tok)
- `05a62056-3a9_develop_20260510T111830.md` — Agent Handoff — develop (~236 tok)
- `05a62056-3a9_document_20260510T112320.md` — Agent Handoff — document (~168 tok)
- `05a62056-3a9_executor_started_20260510T110854.md` — Agent Handoff — executor_started (~107 tok)
- `05a62056-3a9_pipeline_complete_20260510T112320.md` — Agent Handoff — pipeline_complete (~390 tok)
- `05a62056-3a9_pm_decompose_20260510T111019.md` — Agent Handoff — pm_decompose (~135 tok)
- `05a62056-3a9_research_20260510T111229.md` — Agent Handoff — research (~170 tok)
- `05a62056-3a9_test_20260510T112120.md` — Agent Handoff — test (~238 tok)
- `06d3f2a5-82c_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~94 tok)
- `073864e5-58b_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~93 tok)
- `073a3fe7-4d5_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~95 tok)
- `09ff3a16-710_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~92 tok)
- `0a242acf-f52_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~95 tok)
- `0af6e1cb-61c_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~93 tok)
- `0c263083-1c8_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~93 tok)
- `0f6d4e48-ea3_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~92 tok)
- `10857dbb-a51_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~116 tok)
- `1176fc3b-697_executor_started_20260510T110855.md` — Agent Handoff — executor_started (~93 tok)
- `11e9b4b9-283_architecture_20260509T075556.md` — Agent Handoff — architecture (~135 tok)
- `11e9b4b9-283_deploy_20260509T081242.md` — Agent Handoff — deploy (~129 tok)
- `11e9b4b9-283_develop_20260509T080722.md` — Agent Handoff — develop (~145 tok)
- `11e9b4b9-283_document_20260509T081332.md` — Agent Handoff — document (~183 tok)
- `11e9b4b9-283_executor_started_20260509T074916.md` — Agent Handoff — executor_started (~101 tok)
- `11e9b4b9-283_pipeline_complete_20260509T081332.md` — Agent Handoff — pipeline_complete (~390 tok)
- `11e9b4b9-283_pm_decompose_20260509T075116.md` — Agent Handoff — pm_decompose (~135 tok)
- `11e9b4b9-283_research_20260509T075401.md` — Agent Handoff — research (~132 tok)
- `11e9b4b9-283_test_20260509T081127.md` — Agent Handoff — test (~259 tok)
- `1356f045-d02_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~94 tok)
- `13903e4c-2ad_executor_started_20260510T110855.md` — Agent Handoff — executor_started (~92 tok)
- `151d3199-b28_executor_started_20260510T110855.md` — Agent Handoff — executor_started (~94 tok)
- `15554439-6aa_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~94 tok)
- `15a7e2eb-cd1_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~95 tok)
- `17d0eaa2-bd5_architecture_20260509T091002.md` — Agent Handoff — architecture (~200 tok)
- `17d0eaa2-bd5_deploy_20260509T092453.md` — Agent Handoff — deploy (~244 tok)
- `17d0eaa2-bd5_develop_20260509T092102.md` — Agent Handoff — develop (~170 tok)
- `17d0eaa2-bd5_document_20260509T092558.md` — Agent Handoff — document (~206 tok)
- `17d0eaa2-bd5_pipeline_complete_20260509T092558.md` — Agent Handoff — pipeline_complete (~390 tok)
- `17d0eaa2-bd5_pm_decompose_20260509T090646.md` — Agent Handoff — pm_decompose (~146 tok)
- `17d0eaa2-bd5_research_20260509T090757.md` — Agent Handoff — research (~132 tok)
- `17d0eaa2-bd5_task_init_20260509T090531.md` — Agent Handoff — task_init (~145 tok)
- `17d0eaa2-bd5_test_20260509T092347.md` — Agent Handoff — test (~282 tok)
- `18211ad2-e95_executor_started_20260510T110855.md` — Agent Handoff — executor_started (~93 tok)
- `18d4b20f-c33_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~94 tok)
- `1aed56ed-eda_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~95 tok)
- `1b713286-262_executor_started_20260611T093734.md` — Agent Handoff — executor_started (~105 tok)
- `1b713286-262_task_init_20260611T093733.md` — Agent Handoff — task_init (~175 tok)
- `1cc2c0fb-90b_executor_started_20260509T073232.md` — Agent Handoff — executor_started (~93 tok)
- `1ce78c0e-062_architecture_20260503T045804.md` — Agent Handoff — architecture (~135 tok)
- `1ce78c0e-062_deploy_FAILED_20260503T050220.md` — Agent Handoff — deploy_FAILED (~90 tok)
- `1ce78c0e-062_develop_20260503T045845.md` — Agent Handoff — develop (~145 tok)
- `1ce78c0e-062_develop_20260503T050025.md` — Agent Handoff — develop (~171 tok)
- `1ce78c0e-062_develop_20260503T050150.md` — Agent Handoff — develop (~145 tok)
- `1ce78c0e-062_pm_decompose_20260503T045724.md` — Agent Handoff — pm_decompose (~135 tok)
- `1ce78c0e-062_research_20260503T045739.md` — Agent Handoff — research (~132 tok)
- `1ce78c0e-062_task_init_20260503T045659.md` — Agent Handoff — task_init (~152 tok)
- `1ce78c0e-062_test_20260503T045905.md` — Agent Handoff — test (~337 tok)
- `1ce78c0e-062_test_20260503T050050.md` — Agent Handoff — test (~458 tok)
- `1ce78c0e-062_test_20260503T050210.md` — Agent Handoff — test (~467 tok)
- `1d2d7607-8a3_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~94 tok)
- `1d7ec3bb-a6f_executor_started_20260510T110855.md` — Agent Handoff — executor_started (~94 tok)
- `1e04fc38-6e9_executor_started_20260509T073231.md` — Agent Handoff — executor_started (~111 tok)
- `1ebf4f3a-24b_architecture_FAILED_20260611T093926.md` — Agent Handoff — architecture_FAILED (~136 tok)
- `1ebf4f3a-24b_deploy_FAILED_20260611T094410.md` — Agent Handoff — deploy_FAILED (~94 tok)
- `1ebf4f3a-24b_develop_FAILED_20260611T093947.md` — Agent Handoff — develop_FAILED (~124 tok)
- `1ebf4f3a-24b_develop_FAILED_20260611T094140.md` — Agent Handoff — develop_FAILED (~124 tok)
- `1ebf4f3a-24b_develop_FAILED_20260611T094303.md` — Agent Handoff — develop_FAILED (~124 tok)
- `1ebf4f3a-24b_pm_decompose_FAILED_20260611T093814.md` — Agent Handoff — pm_decompose_FAILED (~135 tok)
- `1ebf4f3a-24b_research_FAILED_20260611T093850.md` — Agent Handoff — research_FAILED (~134 tok)
- `1ebf4f3a-24b_task_init_20260611T093738.md` — Agent Handoff — task_init (~180 tok)
- `1ebf4f3a-24b_test_FAILED_20260611T094008.md` — Agent Handoff — test_FAILED (~121 tok)
- `1ebf4f3a-24b_test_FAILED_20260611T094201.md` — Agent Handoff — test_FAILED (~121 tok)
- `1ebf4f3a-24b_test_FAILED_20260611T094324.md` — Agent Handoff — test_FAILED (~121 tok)
- `1f0da2f7-522_architecture_20260510T111515.md` — Agent Handoff — architecture (~135 tok)

## src/frontend/js/digital-twin/

- `eco-console.js` — eco-console.js — 物竞天择生境控制台逻辑层 (v2 XT-4.2) (~14168 tok)

## src/frontend/js/office/

- `office-state.js` — office-state.js — 统一办公室场景的单一数据源 (P7-1) (~5165 tok)

## 本轮改动(2026-06-13, plaza 优化 plan+todos)


## 本轮改动(2026-06-13, skill-extract 优化 + 技能闭环)


## 本轮改动(2026-06-13, system-evolution 实时更新修复)


## 本轮改动(2026-06-18, docs 签名治理规则)


## 本轮改动(2026-06-18, skill-extract fallback 议题化)


## 本轮改动(2026-06-18, skill-extract 删除后复活)


## 本轮改动(2026-06-18, skill-extract 弹窗按钮可见性)


## 本轮改动(2026-06-18, skill-extract 跨议题误去重)


## 本轮改动(2026-06-18, skill-extract 队列来源隔离)


## Manual note 2026-07-13
- `docs/物竞天择任务闭环与Skill遗传plan.md` — v4 task-loop + skill inheritance plan
- `docs/物竞天择任务闭环与Skill遗传todos.md` — v4 XG/XR checklist (XG-0..13, XR-1 全勾)
- `src/backend/sandbox/plan_eco_bridge.py` — TaskHabitatContract compiler (v4)
- `src/backend/sandbox/skill_identity.py` — skill canonicalize (v4)
- `src/backend/sandbox/skill_integration.py` — integration report (v4)
- `src/backend/sandbox/survival_decompose.py` — T_i → skill/collab/residual attribution (v4 XG-13)
- `tests/test_plan_eco_bridge.py` — v4 unit tests
- `tests/test_survival_decompose.py` — T_i decomposition unit tests
- `tests/test_eco_smoke_static.py` — XR-1.5 static smoke (no browser)
- `src/frontend/__tests__/eco-genetics-v4.test.js` — genetics skill UI vitest
- `src/backend/sandbox/relation_integration.py` — 物竞 timeline→关系边建议（XF-7.1）
- `tests/test_relation_integration.py` — 关系边 suggest/apply 单测
- `docs/物竞适者反馈调整台plan.md` / `todos.md` — 适者反馈台（含 XF-7 关系/通道）

- `src/backend/agents/token_governance/lever_params.py` — R10 杠杆可调参数 schema/clamp (~2k tok)

- `src/frontend/css/taste-light.css` — Taste Skill 全站浅色壳(除孪生)；html.taste-light token 映射 (~2k tok)

- `.agents/skills/design-taste-frontend/SKILL.md` — 官方 Taste Skill (tasteskill.dev / Leonxlnx) design-taste-frontend v2 (~8k tok)

## src/backend/agents/tse/

- `__init__.py` — TSE public API: extract_skills, pipeline, schema (~80 tok)
- `config.py` — TSE hyperparameters (TCN d=1,2,4, 5 queries, loss weights) (~120 tok)
- `transcript.py` — Plaza transcript parse from structured meta or free-form chat (~220 tok)
- `encoder.py` — Stage1 hash n-gram utterance encoder + aux role/signal/niche/round (~180 tok)
- `tcn.py` — Stage2 pure-numpy dilated depthwise TCN residual stack (~160 tok)
- `skill_attention.py` — Stage3 5-field multi-head cross-attention + skill moments (~160 tok)
- `decoder.py` — Stage4 constrained JSON via ChatHarness + schema retry (~200 tok)
- `pipeline.py` — Full TSE orchestration for skill_extractor prefill (~200 tok)
- `schema.py` — Skill JSON validate/parse grammar helpers (~140 tok)
- `heads.py` — Multi-task category CE + tools multi-label heads (~140 tok)
- `dataset.py` — PlazaExtractionDataset JSONL silver/gold pairs (~200 tok)
- `silver.py` — LLM/heuristic silver label bootstrap (~180 tok)
- `trainer.py` — Numpy multi-task SGD trainer AE+cat+tools (~280 tok)
- `checkpoint.py` — save/load npz weights into pipeline (~160 tok)
- `experiments.py` — Paper §9.3/9.4 pure experiment APIs (benchmark/keyword attn/compare). (~5k tok)
- `evaluate.py` — name P/R/F1 + head metrics (~120 tok)
- `active.py` — uncertainty active-learning queue (~100 tok)


## scripts/

- `train_tse.py` — TSE silver bootstrap + multi-task train CLI (~120 tok)
- `run_tse_paper_experiments.py` — Paper §9.3/9.4 reproducible CLI (latency/attention/all). (~2k tok)
- `experiment_agent_memory_adaptation.py` — 五组记忆适应确定性机制实验（隔离 tempfile）(~400 tok)
- `experiment_agent_memory_adaptation_llm.py` — 真实 LLM 五组记忆行为实验；blocked 不冒充(~700 tok)
- `audit_agent_memory_migration_counts.py` — 20/40 迁移计数生产扫描+协议重跑(~400 tok)

## src/backend/agents/ (agent memory)

- `agent_memory_migration.py` — v2 导出/三策略导入/Will/继承分区/软检索 inherited_hits (~8k tok)
- `agent_memory_core.py` — 四层+语义核+半衰期+export_v2
- `agent_memory_runtime.py` — prepare inject / update_from_evidence / plaza 回写
- `agent_memory_transfer.py` — transfer_via_will 薄适配
- `agent_memory_routes.py` — hub wills/migrations/inherited API

## src/backend/domain/model_clearance/ (assurance report)

- `assurance_record.py` — §9 保障记录装配器；`GATE_CRITERIA` 是 G0-G8 → 标准正文要点的映射；只装配不判定（~3k tok）

## src/frontend/js/ (assurance deliverable)

- `assurance-report-doc.js` — §9 保障记录 → 单文件可打印 HTML 交付物；`AssuranceReportDoc.build(record)`；样式内联、零外链（~4k tok）

## src/backend/domain/model_clearance/ (blocker advisory)

- `blocker_advisor.py` — 阻断项 LLM 分析建议；`advise_blockers(app, llm=)` 可注入，判定字段绝不从模型取（~3k tok）

## src/frontend/js/ (clearance intake)

- `open-weights-models.js` — `buildClearanceHref(m)` 是跳准入控制台的唯一入口构造器，卡片与弹窗共用
- `ai-model-entry-clearance.js` — `readIncoming`/`applyIncoming`/`renderIntakeNotice` 处理 `?model_id=` 带入与启动
