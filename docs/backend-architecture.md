# Timeflow 后端架构设计（现状版）

> 本文档基于 `backend/src/timeapp` 的实际代码整理，描述"现在是什么"，不是"P0 计划做什么"。P0 范围、能力激活状态、后续演进方向等规划性内容仍以 `docs/architecture.md` 为准；两份文档冲突时，以本文档反映的代码事实为准，`docs/architecture.md` 应据此更新。

## 1. 分层总览

```text
Mobile App / HTTP / WS
        |
Application Layer  (application/)
        |
Capability Packs   (capabilities/)
        |
Domain Core         (domain/)
        |
Infrastructure       (infrastructure/, core/)

AI 层 (ai/) 独立于以上主链路，只产出 Command，不参与写入
Context & Policy 层 (context/) 部分接入 reminder 能力
```

依赖方向（实际代码遵守）：

```text
api          -> application
application  -> ai + capabilities + domain + application.store
capabilities -> application.store (通过 Store Protocol) + domain + context.policies
ai           -> domain only（不 import application/capabilities/infrastructure）
domain       -> 不依赖任何具体实现
```

## 2. 目录结构与职责

| 目录 | 职责 | 关键文件 |
| --- | --- | --- |
| `main.py` | FastAPI 应用入口，挂载 CORS 和路由 | - |
| `api/` | HTTP/WS 接口层，只做协议转换和依赖注入，不含业务逻辑 | `router.py`、`dependencies.py`、`schemas.py`、`realtime.py` |
| `ai/` | 语音转文字 + 语义解析，只产出 `Command`，不碰数据库（见 §6） | `asr/client.py`（`AsrClient`）、`parser.py`（`LLMCommandParser`/`MockCommandParser`） |
| `application/` | 编排：命令生命周期、write-request 确认门禁、查询、存储接口 | `service.py`（`TimeflowApplication`）、`store.py`（`Store` Protocol + 两个实现）、`reference_resolver.py` |
| `capabilities/` | 业务逻辑真正的归属地 | 见下表 |
| `context/` | 提醒触发条件和投递策略 | `policies.py`、`triggers.py`、`providers.py`、`conditions.py` |
| `domain/` | 稳定内核：纯数据结构、枚举、错误码，不依赖任何框架 | `models.py`、`enums.py`、`errors.py` |
| `infrastructure/` | SQLAlchemy ORM 模型 | `models.py` |
| `core/` | 配置和数据库连接 | `config.py`（`Settings`）、`db.py`（engine/session） |

### 2.1 Capability 包

| 包 | 状态 | 持有的业务逻辑 |
| --- | --- | --- |
| `capabilities/calendar/` | 实现 | 日历事项创建（`apply`）+ update/delete（委托 `item_common`） |
| `capabilities/todo/` | 实现 | 待办创建 + update/delete/complete（委托 `item_common`） |
| `capabilities/item_common.py` | 实现 | calendar/todo 共用的 Item CRUD（因为两者共用同一张 `items` 表、同一套规则） |
| `capabilities/reminder/` | 实现 | Reminder 创建/动作状态机 + **RepeatRule 的 CRUD**（RepeatRule 目前只服务于提醒，没有独立能力包；地点数据已并入 `Item`，不再是 reminder 单独管理的实体，见 §3/§5） |
| `capabilities/voice_command/` | 空包 | 语音入口不是"写业务事实"的能力，真实逻辑在 `ai/parser.py` + `application/service.py.submit_voice_command` |
| `capabilities/realtime/` | 空包 | WS 不持有业务事件，真实逻辑在 `api/realtime.py` 的 `RealtimeConnectionManager` |

`long_task_split`/`replan`/`smart_reminder` 三个骨架能力包已删除（原来只有一行说明文档，没有任何实现，代码里没有任何地方引用）。其中 `smart_reminder` 不是被删掉后"以后再补"，而是这个能力划分本身被否掉了：天气、噪声、设备状态这些不是一个独立的"智能提醒能力"，是 `reminder` 能获取的更多上下文输入。以后要做"下雨提醒带伞""嘈杂环境改用震动"这类功能，直接在 `reminder` capability 里加，不再单独设一层 `smart_reminder`。对应的 `context/providers.py` 里的 `WeatherContextProvider`/`NoiseContextProvider`/`DeviceStateContextProvider`/`UserPreferenceContextProvider` 骨架类保留，作为以后 `reminder` 能力要用到的上下文输入点。

## 3. 核心领域模型（`domain/models.py`）

| 类型 | 字段 | 说明 |
| --- | --- | --- |
| `Identity` | `user_id`、`device_id`、`session_id` | 当前 `get_identity()` 返回硬编码的 demo 身份，还没接入真实鉴权 |
| `Command` | `action`/`entity`/`title`/`start_at`/`end_at`/`due_at`/`payload` 等 | 语义解析后的统一命令模型 |
| `VoiceCommand` | `transcript`/`status`（`parsed`/`needs_clarification`）/`command_id` | 语音输入审计记录 |
| `WriteRequest` | `candidate_payload`/`payload_hash`/`status`/`expires_at`/`idempotency_key` | 所有写入的确认门禁，`status` ∈ `pending/applied/rejected/expired` |
| `DomainEvent` | `event_type`/`aggregate_type`/`aggregate_id`/`version`/`payload` | 领域事实变化的统一表达，驱动 WS 广播 |
| `Item` | `item_type`（`calendar_event`/`todo`）/`status`/`start_at`/`due_at`/`version`/`place_text`/`place_type`/`latitude`/`longitude`/`accuracy_meters`/`radius_meters` | 日历和待办的统一事项表；地点数据直接挂在 item 上，没有独立的 Place 实体（见 §5） |
| `RepeatRule` | `pattern`（`daily`/`weekdays`/`custom_weekdays`）/`weekdays`/`time_of_day`/`series_status` | 重复规则 |
| `Reminder` | `trigger_type`/`trigger_at`/`status`/`snooze_count`/`fallback_status` | 提醒规则与状态机；地点触发提醒的位置信息从它绑定的 `item_id` 上读，不再有自己的 `place_id` |

## 4. 接口设计

### 4.1 HTTP API（前缀 `/api/v1`）

| Method | Path | 作用 | 说明 |
| --- | --- | --- | --- |
| GET | `/health` | 健康检查 | - |
| GET | `/agenda` | 日程主面板投影 | 返回按创建时间排序的 items + reminders |
| POST | `/voice/commands` | 文本命令入口 | 输入 `transcript`，走语义解析 -> write-request -> 确认门禁 |
| POST | `/voice/commands/audio` | 音频命令入口 | 上传音频 -> ASR 转写 -> 复用文本命令流程；未配置 ASR 返回 `503 asr_not_configured` |
| POST | `/write-requests` | 直接创建 write-request | 供非语音客户端提交候选 payload |
| GET | `/write-requests/pending` | 列出待确认的 write-request | 过期自动标记为 `expired` |
| GET | `/write-requests/{id}` | 查询单个 write-request | - |
| PATCH | `/write-requests/{id}` | 编辑待确认的候选 payload | 重新计算 `payload_hash` |
| POST | `/write-requests/{id}/confirm` | 确认写入 | 分发给对应 capability，产出 `DomainEvent` |
| POST | `/write-requests/{id}/reject` | 拒绝写入 | 不触碰业务事实 |
| GET | `/items` | 列出事项 | 附带每个事项的提醒列表 |
| POST | `/items` | 手动创建事项 | 不经过确认门禁（非语音路径） |
| PATCH | `/items/{id}` | 更新事项字段 | 只更新显式传入的字段 |
| POST | `/items/{id}/complete` | 标记完成 | - |
| POST | `/items/{id}/cancel-complete` | 取消完成 | 回到 `active` |
| DELETE | `/items/{id}` | 删除事项 | 软删除（`status=deleted`） |
| POST | `/permissions/degrade` | 权限降级 | 目前只支持 `location` 权限拒绝后降级为文字地点待办 |
| GET | `/repeat-rules` | 列出重复规则 | - |
| POST | `/repeat-rules` | 创建重复规则 | 校验 `pattern`/`weekdays`/`time_of_day`/`series_status` |
| GET | `/reminders` | 列出提醒 | - |
| POST | `/reminders` | 创建提醒 | 绑定到已存在的 `item_id`；地点触发提醒要求目标 item 已有 `place_text`（先 `PATCH /items/{id}` 写地点，再创建提醒） |
| POST | `/reminders/{id}/actions` | 上报提醒动作 | `registered`/`armed`/`delivered`/`dismiss`/`snooze`/`cancel`/失败类 action；`snooze` 受 `CooldownPolicy` 限制（P0 只允许一次） |
| GET | `/events` | 断线补拉 | 客户端传 `after` 游标（裸整数），服务端从 `domain_events` 表按游标之后返回 |

### 4.2 WebSocket（`/ws`）

连接建立后服务端立即推送 `connection.ready`；客户端发送 `{"type": "sync.request", "after": <cursor>}` 触发补拉，其余消息触发 `connection.heartbeat` 回执。

WS 广播是**同步直达**：`api/*` 每次写入产生 `DomainEvent` 后，直接调用 `RealtimeConnectionManager.broadcast_events()` 推给所有连接，不经过任何持久化的 Outbox/投影器（`application/store.py` 里已经没有 outbox 相关代码，见 §5.3）。

`DomainEventType`（`domain/enums.py`）当前定义的事件类型：

```text
connection.ready          write_request.created      item.created
command.status.changed    write_request.updated      item.updated
sync.response              write_request.applied       reminder.armed / .due / .delivered
permission.degraded        write_request.rejected      reminder.dismissed / .snoozed / .cancelled
                                                        reminder.expired / .failed
notification.registration.failed
notification.fallback.requested
```

`reminder.due`、`reminder.expired` 目前只在枚举里定义，代码里没有任何地方产出这两个事件——服务端没有到期扫描任务，没人会在提醒到期或过期时主动发出这两个事件（见 §7）。

### 4.3 鉴权现状

`api/dependencies.py` 的 `get_identity()` 返回硬编码的 `demo-user`/`demo-device`/`demo-session`，还没有真实的登录/鉴权机制。所有 `user_id` 隔离逻辑（`store` 层的 `user_id ==` 过滤）已经就位，接入真实鉴权时只需要替换这一个依赖函数。

## 5. 数据库设计

### 5.1 表结构（`infrastructure/models.py`，通过 `application/store.py` 的 `SqlAlchemyStore` 读写）

| 表 | 主要字段 | 说明 |
| --- | --- | --- |
| `domain_events` | `event_type`、`aggregate_type`、`aggregate_id`、`version`、`payload`（JSON） | 事件溯源与补拉来源，`version` 全局自增 |
| `items` | `item_type`、`status`、`start_at`/`end_at`/`due_at`、`place_text`、`place_type`、`latitude`、`longitude`、`accuracy_meters`、`radius_meters`、`version`、`deleted_at` | 日历/待办统一表，与 `reminders` 是 1-N 关系（`cascade="all, delete-orphan"`）；地点数据直接挂在这张表上 |
| `reminders` | `item_id`（FK -> `items.id`）、`trigger_type`、`trigger_at`、`status`、`snooze_count`、`fallback_status` 等 | 提醒规则与状态机，字段最多的表；没有自己的地点字段，地点触发时读 `item_id` 对应 item 的 `place_text`/`latitude`/`longitude` |
| `reminder_rules` | `rule_payload`（JSON，存 `pattern`/`weekdays`/`time_of_day`）、`status` | **不是骨架表**：这张表原本是为 smart_reminder 预留的，现在被 `RepeatRule`（重复提醒规则）复用为真实存储，见 `application/store.py` 的 `add_repeat_rule`/`list_repeat_rules` |

`voice_commands`、`write_requests` 两张表在数据库里还在（见 §5.3），但已经没有对应的 ORM 类了：

- `VoiceCommand` 只在内存里构造，用于 API 响应，不再落库——`submit_voice_command()` 不再调用任何 `add_voice_command`/`update_voice_command`。
- `WriteRequest` 改成进程内存储（`WriteRequestMemoryStore`，见下），不再经过 SQLAlchemy。确认门禁这个行为本身没变：AI 解析出的候选还是要等用户确认才真正写入，只是"待确认"这个状态不再落库，服务进程重启会丢失所有还没确认的候选。

### 5.2 关系

```text
items (1) ----< reminders (N)     -- ForeignKey items.id, ON DELETE 由 ORM cascade 处理
```

其余表之间没有数据库级外键约束，靠应用层 `user_id` 过滤隔离数据。

### 5.3 WriteRequest 内存存储

`WriteRequestMemoryStore`（`application/store.py`）是一个进程级单例：`dict[str, WriteRequest]` + 锁，不落库。

这里有一个容易踩的坑：`SqlAlchemyStore` 是每个 HTTP 请求都重新构造一个新实例（`api/dependencies.py` 的 `get_timeflow_app()` 用 FastAPI `Depends` 做请求级依赖注入）。如果直接把 write_requests 存成 `SqlAlchemyStore` 实例自己的字段，每个新请求会拿到一个全新的空字典——上一个请求创建的 write_request 到下一个"确认"请求时就已经不存在了。

解决方式是参照 `api/realtime.py` 里 `realtime_manager` 的写法：在 `api/dependencies.py` 里模块级构造一个 `_write_request_store = WriteRequestMemoryStore()`，每次 `get_timeflow_app()` 都把这个共享实例传给新建的 `SqlAlchemyStore(session, write_requests=_write_request_store)`。这样 write_request 能在同一进程内跨请求存活，但服务进程重启就会全部丢失（见 §5.1 的说明）。`InMemoryStore` 不需要这个处理，因为测试里 `TimeflowApplication(InMemoryStore())` 只构造一次、整个测试复用同一个实例。

### 5.4 已知的 Schema 与代码不一致

`alembic/versions/20260727_0002_ms1_architecture_baseline.py` 建过以下几张表，但代码里已经**没有**对应的 ORM 类或写入路径：

- `outbox_messages`、`sync_cursors` —— Outbox 机制已经从代码里整体移除。
- `user_reminder_preferences`、`reminder_rule_conditions`、`reminder_occurrences` —— 只服务于已删除的 `smart_reminder` 骨架能力包，随能力包一起从代码里删掉。
- `voice_commands`、`write_requests` —— 分别改成纯内存构造和 `WriteRequestMemoryStore`（见 §5.3），不再有 `VoiceCommandRecord`/`WriteRequestRecord` 这两个 ORM 类。

这意味着：

- 已经跑过 `alembic upgrade head` 的数据库里物理上还有这七张表。
- 没有任何 Python 代码再读写它们。
- 没有写新的 migration 去 drop 这些表（drop table 是有数据风险的操作，需要单独评估再做）。

如果要彻底清干净，需要一条新的 Alembic migration 显式 drop 上述七张表；在那之前，它们是数据库里的历史遗留，不代表设计意图。`reminder_rules` **不在此列**——它现在是 `RepeatRule` 的真实存储表，见 §5.1。

## 6. AI 层边界

`ai/` 是唯一处理"自然语言 -> 结构化数据"的地方，物理上不 import `application.store`/`capabilities.*`/`infrastructure.*`（只 import `domain/` 和外部库），这个 import 边界本身就是"AI 不能直接写数据库"这条规则的强制实现，不是靠约定。

- `ai/asr/client.py` —— `AsrClient`：音频 -> 文字，支持 `openai_transcription`（标准 multipart）和 `qwen_chat`（Base64 音频走 Chat Completions）两种协议。
- `ai/parser.py` —— `LLMCommandParser`（调用外部 LLM 做结构化解析，失败自动降级）+ `MockCommandParser`（本地正则规则解析，未配置 LLM 时使用）。两者都产出 `domain.models.Command`，不直接操作任何存储。

## 7. 关键流程

### 7.1 语音/文本命令确认流程

```text
transcript
  -> ai.parser.{LLMCommandParser|MockCommandParser}.parse()   # 语义识别，产出 Command
  -> TimeflowApplication.submit_voice_command()
       - action == QUERY            -> 直接查询返回，不建 WriteRequest
       - action in {UPDATE/DELETE/COMPLETE}
           -> ReferenceResolver.resolve_item_candidates()      # 确定性查库，不是 AI 查库
           -> 0 个候选  -> NEEDS_CLARIFICATION，返回反问
           -> >1 个候选 -> NEEDS_CLARIFICATION，返回候选列表 + WriteRequest
           -> 1 个候选  -> 直接建 WriteRequest
       - action == CREATE            -> 直接建 WriteRequest
  -> 用户确认 (POST /write-requests/{id}/confirm)
  -> TimeflowApplication._apply_write_request()
       -> 按 candidate_payload.operation 分发给 calendar/todo/reminder capability
  -> capability 写入 store，产出 DomainEvent
  -> api 层同步调用 RealtimeConnectionManager.broadcast_events()
```

### 7.2 提醒动作流程

```text
POST /reminders/{id}/actions {action: "registered"|"armed"|"delivered"|"dismiss"|"snooze"|"cancel"|失败类}
  -> ReminderCapability.apply_action()
       - snooze 前先过 CooldownPolicy.can_snooze()（P0 只允许一次）
       - 失败类 action 触发 CloudFallbackPolicy.should_request()/request()
  -> 更新 Reminder 状态，产出 DomainEvent（+ 可能的 fallback 事件）
  -> WS 广播
```

提醒的**到期判定**完全由客户端驱动（客户端本地判断时间/地点到达后主动上报 action），服务端没有到期扫描任务，`TimeTrigger`/`EnterPlaceTrigger`/`LeavePlaceTrigger` 目前是未接入运行时的骨架类（定义在 `context/triggers.py`）。

## 8. Context & Policy 现状

| 类 | 状态 | 说明 |
| --- | --- | --- |
| `CooldownPolicy`（`context/policies.py`） | 真正接入 | 限制提醒只能 snooze 一次 |
| `CloudFallbackPolicy`（`context/policies.py`） | 真正接入 | 记录本地不可达时的云端兜底请求 |
| `TimeContextProvider`/`PlaceContextProvider`（`context/providers.py`） | 定义但未接入 | 没有调用点 |
| `TimeTrigger`/`EnterPlaceTrigger`/`LeavePlaceTrigger`（`context/triggers.py`） | 定义但未接入 | 需要服务端到期扫描机制才有意义，属于后续独立功能 |
| `LocalNotificationPolicy`、`VibrationPolicy`、`VoicePolicy`、`QuietPeriodPolicy` | 骨架 | 未接入 |
| `WeatherContextProvider`、`NoiseContextProvider`、`DeviceStateContextProvider`、`UserPreferenceContextProvider`、各 `*Condition` | 骨架 | 未接入，等以后要做天气/噪声/设备状态相关提醒功能时，直接扩展 `reminder` capability 去用它们，不再经过一层单独的 `smart_reminder` 能力包（该能力包已删除，见 §2.1） |

## 9. 已知的结构性问题（暂不处理，记录在案）

- `capabilities/reminder/handler.py` 同时管 Reminder 和 RepeatRule 两件事，因为后者目前只服务于提醒。以后如果加天气/噪声/设备状态相关的提醒功能，也会继续加在这里而不是拆一个新能力包（见 §2.1）。
- `application/service.py`（约 880 行）体量大，但内容是合理的编排代码（语音命令状态机、write-request 生命周期、查询），不是业务逻辑堆积。
- `application/store.py` 的 `InMemoryStore`/`SqlAlchemyStore` 两套实现现在有 `Store` Protocol（`typing.Protocol`）做结构化约束，mypy 会在两边签名不一致时报错，但底层实现仍然是两份手写代码，字段级别的语义漂移（比如某个方法在一边有额外的边界处理、另一边没有）不在 Protocol 的检查范围内。
- `outbox_messages`/`sync_cursors`/`user_reminder_preferences`/`reminder_rule_conditions`/`reminder_occurrences`/`voice_commands`/`write_requests` 七张表是数据库里的历史遗留（见 §5.4）。
- 地点数据并入 `Item` 之后，失去了"家/公司"这种一次保存、多处复用的能力——每个需要地点触发的事项要各自带一份地点数据（这是有意的取舍，见开发时的讨论）。
- 鉴权还没接入，`get_identity()` 是硬编码的 demo 身份（见 §4.3）。
