# Information sources domain

## T201（已实现）

- `models.py` — `SourceConfig` / `SourceManifest` / `FetchBatch` / `FetchItem` / `HealthResult`
- `protocol.py` — `SourceConnector` Protocol + `SourceRegistry`
- `ssrf.py` — scheme/host/IP/redirect SSRF guards
- `connectors/` — `fixture`, `rss`, `web`, `json_api`
- `scheduler.py` — 协议级 `fetch_many`（单来源失败隔离）

依赖方向：connector 可依赖本包；本包不依赖 FastAPI 或 TradingAgents。

## 后续

`EvidenceRecord` / 去重落盘 / reputation 见 T203；目录研究见 Codex T202。
