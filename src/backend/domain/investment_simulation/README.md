# Investment simulation domain

已实现（T401–T406）：

- `models.py` — `InvestmentSimulation` / `InvestmentEvent`（无 Plaza ID）
- `portfolio.py` — Paper Portfolio（BUY/SELL/HOLD，无真实券商）
- `store.py` — 运行持久化、事件 jsonl、checkpoint 游标
- `orchestrator.py` — 创建/启动/取消、fixture graph、预算门禁、事件流

与 `integrations/tradingagents` 适配层协作；API 见 `domain/api_routes.py`。
