# Timeflow MVP Plan

原则：每一步只做可验证的最小增量；未激活能力只保留 skeleton，不提前做复杂实现。

## Commit Slicing

1. `docs`: product + architecture references
2. `docs`: MVP plan + architecture split and API contract
3. `feat(backend)`: health check + base config
4. `feat(client)`: single-page shell + health probe
5. `feat(backend)`: agenda/items schema + empty list
6. `feat(client)`: agenda shell + empty state rendering
7. `feat(backend)`: manual item create
8. `feat(client)`: quick add form + local cache
9. `feat(backend)`: voice command mock parse
10. `feat(client)`: voice overlay skeleton
11. `feat(backend)`: command/reference resolver
12. `feat(backend)`: write request gate
13. `feat(backend)`: item apply handlers
14. `feat(backend)`: reminder model skeleton
15. `feat(backend)`: time reminder delivery skeleton
16. `feat(backend)`: place model skeleton
17. `feat(backend)`: place reminder skeleton
18. `feat(backend)`: repeat rule skeleton
19. `feat(sync)`: ws/outbox skeleton
20. `feat(sync)`: single-device LWW skeleton
21. `feat(fallback)`: local-first cloud fallback skeleton
22. `feat(perms)`: permission and degrade paths
23. `feat(e2e)`: user stories
24. `chore`: validation and demo scripts

## Plan

| Step | 客户端 | 云端 | 联调 |
|---|---|---|---|
| 1. 项目骨架 | Expo / RN / TS，单页主面板，底部语音按钮 | FastAPI，health check，基础配置 | 客户端请求 health check |
| 2. 数据模型骨架 | `Item` / `Reminder` / `Place` / `WriteRequest` 类型，本地缓存结构 | `items` / `reminders` / `places` / `write_requests` 表，SQLAlchemy model / migration | `GET /agenda` 返回空列表 |
| 3. 单页日程主面板 | 今日 / 周 / 月视图，`ItemCard`，reminder / repeat badge | `GET /agenda`，`GET /items` | 主面板拉取并展示服务端事项 |
| 4. 手动新增事项 | 轻量新增表单，本地先写，上传后下拉 | `POST /items`，`version` / `updated_at` | 新增 calendar_event / todo 后主面板刷新 |
| 5. 语音弹层 | `RecordingCard` / `TranscriptCard` / `ClarificationCard` / `CandidateListCard` / `WriteRequestPreviewCard` / `ResultCard` | `POST /voice/commands`，Mock ASR，Mock Parser | 语音 mock 输入返回 `ParsedCommand` |
| 6. Command / ReferenceResolver | 展示候选，支持用户选择 | `CommandParser` / `ReferenceResolver` / 当前待确认对象 / 最近候选 / 查库候选 | “把明天会议改到四点”返回候选或确认卡 |
| 7. WriteRequest 确认门禁 | 确认卡片，编辑字段，确认 / 取消 / 改一下 | `write_requests`，`operations[]`，`payload` / `preview`，`payload_hash`，`risk_level` / `expires_at` | 确认后写入，取消不写入 |
| 8. Item 写入能力 | 创建 / 修改 / 删除 / 完成，`ItemCard` 状态刷新 | item handlers，transaction apply operations，domain event | 语音和手动都能改同一套数据 |
| 9. Reminder 数据模型 | 多提醒展示，badge，状态展示 | `reminders` 表，`time` / `enter_place` / `leave_place` / `return_to_place`，状态机 | 为同一 item 创建多条 reminder |
| 10. 时间提醒 | 本地通知注册，`delivered` / `failed` 回传，`snooze` / `dismiss` / `cancel` | `trigger_at`，notification registration 状态，reminder action API | 时间提醒触发后状态同步 |
| 11. Place / 地点模型 | 定位权限，一键保存当前位置，半径 50 / 100 / 200 | `places` 表，`home` / `work` / `custom` / `temporary_parking`，`accuracy` / `description` | 保存家 / 公司 / 自定义 / 停车位置 |
| 12. 地点提醒 | `enter_place` / `leave_place` / `return_to_place`，`armed` 状态 | 地点 reminder rule，`place_id` 绑定，状态持久化 | 到家取快递，停车位置提醒 |
| 13. 重复规则骨架 | `repeat` badge，重复确认卡片 | `repeat_pattern` / `repeat_weekdays` / `repeat_time_of_day` / `series_status` | 每天 / 工作日 / 自定义周几能保存和展示 |
| 14. WS / Outbox | WS connection states，`sync.request`，cursor 保存 | `domain_events` / `outbox_messages` / WS endpoint / event projection | 写入后 WS 推送，断线后补拉 |
| 15. 单设备 LWW 同步 | 本地先写，上传队列，下拉覆盖 | `version` / `updated_at`，latest write wins | 离线改动恢复后按队列上传并回灌 |
| 16. 本地优先 + 云端兜底骨架 | 本地通知状态回传，本地不可达状态 | `CloudFallbackPolicy` minimal，`fallback_status`，`fallback_after_seconds`，`Sms` / `Email` / `Call` adapter skeleton | 本地 failed 后生成 fallback requested，不真实发短信电话 |
| 17. 权限与降级 | 麦克风 / 通知 / 定位权限，权限拒绝 UI | 稳定错误码，failed reason | 定位拒绝降级为普通 Todo + 文字地点 |
| 18. E2E 用户故事 | 语音新增日历 / 待办，到家提醒取快递，停车位置提醒，修改 / 删除 / 完成，多提醒展示，WS 断线补拉 | 保持同一数据模型与事件流 | 全链路演示 |
| 19. 验证与演示 | 真机通知 / 定位验证 | API 测试，迁移测试 | 演示脚本，已知风险说明 |

## Architecture Split

### Client
- Expo / React Native / TypeScript.
- 单页主面板优先。
- 语音、确认、日程、提醒、地点都通过可替换的 UI 卡片承载。
- 本地缓存先行，网络只是同步通道。

### Cloud
- FastAPI 负责 HTTP / WS 接口。
- SQLAlchemy + migration 负责持久化。
- 应用层只负责编排，业务事实通过明确的 command / write request / domain event 走。
- 未激活能力只保留模块目录和空 handler。

### Contract
- 客户端只调用公开 API，不直连内部 store。
- 写操作必须先进入 `WriteRequest` 确认门禁。
- WS 只同步事件和 cursor，不承担业务写入。
- Mock ASR / Mock Parser 只产生命令候选，不直接写库。

