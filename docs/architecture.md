# 语音时间管理产品：可扩展架构设计

> 文档状态：MS1 架构基线
>
> 技术边界：React Native + Expo 移动端，Python 后端，WebSocket + HTTP 并行。本文支撑 P0 MVP，同时允许先搭好可扩展骨架，再只激活当前需要的最小路径。

## 1. 架构目标

本架构要解决两件事：

1. 让 P0 先跑通一个完整闭环：语音进入、候选生成、确认门禁、写入事项、提醒触达、实时同步。
2. 让后续新能力可以通过新增 capability、context provider 或 policy，而不是改动核心骨架。
3. 允许 P0 先生成宽而浅的架构骨架：目录、请求响应结构、消息结构、占位包和验收说明可以存在，但未进入 P0 范围的能力不激活、不接真实实现。

核心原则：

- 语音只是入口，AI 只负责把自然语言转成结构化候选。
- 所有写入都必须经过确认门禁。
- WebSocket 是一等实时通道，但不承担业务写入逻辑。
- 核心领域保持稳定，新增功能优先落在 capability pack 中。
- 时间、地点、天气、噪声、设备状态、用户偏好属于 context / policy，不和 capability 混成一类。
- 架构可以先设计完整，运行路径必须保持收缩；P0 只启用语音、确认、事项、时间/地点提醒、本地通知和 WS 同步。

## 2. 分层总览

```text
Mobile App / HTTP / WS
        |
Application Layer
        |
Domain Core
        |
Capability Packs
        |
Context & Policy Layer
        |
Infrastructure Adapters
```

### 2.1 Layer 职责

| 层级 | 负责 | 不负责 |
| --- | --- | --- |
| Mobile App / HTTP / WS | 录音、展示、实时事件接收、用户动作提交 | 业务规则判断 |
| Application Layer | 编排命令、确认、查询、写入、同步 | 直接耦合外部 SDK |
| Domain Core | 命令模型、确认门禁、事件、幂等、时间、错误码 | 具体产品逻辑 |
| Capability Packs | calendar、todo、reminder、long task split、replan、smart reminder 等 | 改写核心协议 |
| Context & Policy Layer | 时间、地点、天气、噪声、设备状态、用户偏好、触发条件、投递策略 | 业务持久化写入；P0 不激活复杂环境判断 |
| Infrastructure Adapters | 数据库、通知、ASR、LLM、外部环境服务、WS 连接 | 业务决策 |

## 3. 核心设计原则

### 3.1 稳定内核

以下对象属于稳定内核，后续新增 capability 不应反复改它们的结构：

- `Command`
- `WriteRequest`
- `DomainEvent`
- `IdempotencyKey`
- `Identity`（user / device / session）
- `Clock` 和 `Timezone`
- `ErrorCode`

### 3.2 Go 风格约束

后端即使使用 Python 实现，也按 Go 风格控制复杂度：

- 优先普通结构体和显式函数调用，不引入重型框架。
- 接口保持小而稳定，由调用方需要的行为来定义。
- 依赖显式注入，不做隐藏的全局注册魔法。
- capability handler 可以由启动代码显式装配到路由表，不需要自动发现。
- P0 不引入复杂泛型、DSL、反射式插件系统或运行时动态加载。

### 3.3 能力可插拔

新增功能必须以 capability pack 的形式接入。P0 可以先保留能力说明或空 handler，但未进入范围的 handler 不应被路由调用。

- 注册命令处理器
- 注册查询处理器
- 注册领域事件映射
- 注册写入校验和确认 payload
- 注册迁移和测试

### 3.4 上下文与策略独立

时间、地点、天气、噪声、设备状态不是“新产品线”，而是 reminder / smart_reminder 内部的上下文和策略来源。

它们应该以 provider / policy / condition 的方式组合，而不是写进主业务流程。

P0 只激活：

- `TimeContextProvider`
- `PlaceContextProvider`
- `TimeTrigger`
- `EnterPlaceTrigger`
- `LeavePlaceTrigger`
- `LocalNotificationPolicy`
- `CooldownPolicy` 的最小版本

其他 provider、condition、policy 可以保留小接口或占位包，不接真实权限、传感器和外部服务。

### 3.5 事件驱动同步

业务事实变化后统一产出领域事件，再分发到：

- WebSocket 实时推送
- 本地通知
- 查询缓存刷新
- 审计记录

P0 是单进程同步直达：写入产生 `DomainEvent` 后，API 层直接同步调用 WS 广播，不经过持久化的 Outbox/投影器。可靠投递（离线补发、多实例广播、失败重试）需要 Outbox 时再引入，不要在没有消费者的情况下先建表占位。

## 4. 领域与能力模型

### 4.1 Stable Core

Stable Core 只定义通用骨架：

| 对象 | 说明 |
| --- | --- |
| `Command` | 统一命令模型，承载 action / entity / payload |
| `WriteRequest` | 所有写入的确认门禁 |
| `DomainEvent` | 领域事实变化的统一表达 |
| `Identity` | user_id / device_id / session_id |
| `Time` | 时区、当前时间、时间解析 |
| `ErrorCode` | 稳定错误码 |

### 4.2 Capability Packs

能力包是“用户能做什么”：

- `calendar`
- `todo`
- `reminder`
- `voice_command`
- `long_task_split`
- `replan`
- `smart_reminder`

P0 至少启用：

- `calendar`
- `todo`
- `reminder`
- `voice_command`
- `realtime`

P0 可以创建但不激活：

- `long_task_split`
- `replan`
- `smart_reminder`

这些目录可以先只有能力说明、小接口和验收占位，不能参与默认路由和生产执行。

### 4.3 Context & Policy Layer

上下文和策略是“系统在什么条件下做”：

#### Context Providers

- `TimeContextProvider`
- `PlaceContextProvider`
- `WeatherContextProvider`
- `NoiseContextProvider`
- `DeviceStateContextProvider`
- `UserPreferenceContextProvider`

#### Conditions

- `TimeCondition`
- `LocationCondition`
- `WeatherCondition`
- `NoiseCondition`
- `DeviceStateCondition`
- `PreferenceCondition`

#### Triggers

- `TimeTrigger`
- `EnterPlaceTrigger`
- `LeavePlaceTrigger`
- `EnvironmentTrigger`

#### Delivery Policies

- `LocalNotificationPolicy`
- `VibrationPolicy`
- `VoicePolicy`
- `CloudFallbackPolicy`
- `QuietPeriodPolicy`
- `CooldownPolicy`

这些对象不属于 AI capability，它们属于 reminder / smart_reminder 内部的执行和判定层。

P0 实现时可以只落一个 `ReminderDecisionService`，内部调用最小的时间和地点触发、以及本地通知策略。云端兜底策略先保留状态和接口，真实短信、邮件、电话供应商后续接入。后续再把它逐步拆成 Trigger、Condition、ContextProvider、Policy 和 DeliveryChannel。

#### 4.3.1 当前接入状态（避免和实现产生偏差）

提醒的触发状态机目前完全由客户端显式上报的 action 驱动（`POST /reminders/{id}/actions`），服务端还没有到期扫描或推送机制。因此：

- `CooldownPolicy` 已真正接入 `ReminderCapability.apply_action`，用于限制 P0 只允许一次 snooze。
- `CloudFallbackPolicy` 已真正接入，用于本地不可达时记录云端兜底请求。
- `TimeTrigger`、`EnterPlaceTrigger`、`LeavePlaceTrigger`、`TimeContextProvider`、`PlaceContextProvider`、`LocalNotificationPolicy` 以及其余 Condition/Policy 仍然只是接口骨架，没有被运行时调用。把它们接入需要先实现服务端到期扫描/推送机制，这是独立于本次重构的后续功能，不要在没有该机制的情况下强行接入。

## 5. 命令与写入流程

### 5.1 统一命令流

```text
Voice / WS / HTTP
  -> ASR / Parser
  -> Command Router
  -> Parameter Validation
  -> Clarification / Coreference Resolution / Candidate Selection
  -> WriteRequest
  -> Confirmation Gate
  -> Capability Handler
  -> Domain Event
  -> Projection / Notification / WS
```

### 5.2 Command 模型

P0 命令对象使用统一字段：

| 字段 | 说明 |
| --- | --- |
| `action` | `create/query/update/delete/complete/remind/split/replan` |
| `entity` | `calendar_event/todo/reminder/rule` |
| `target_id` | 已定位对象 ID，可空 |
| `title` / `description` | 内容 |
| `start_at` / `end_at` | 日历时间 |
| `due_at` | 待办截止时间 |
| `reminder_at` | 时间提醒 |
| `priority` | `low/normal/high` |
| `time_range_start/end` | 查询范围 |
| `context` | 位置、天气、噪声、设备状态等结构化上下文 |
| `reference_context` | 最近待确认操作、最近候选、当前会话引用 |
| `payload` | capability 专属参数 |

规则：

- 创建必须有最小可执行字段。
- 更新、删除、完成必须唯一定位。
- 未知动作不得落库。
- 任何写入候选都必须可回放、可确认、可拒绝。
- 反问和指代消解必须先于写入决策发生，无法唯一定位时必须返回澄清问题。

### 5.3 WriteRequest 门禁

所有会改变业务事实的动作先进入 `WriteRequest`：

```text
AI Candidate -> WriteRequest -> User Decision -> Capability Handler -> Commit
```

`WriteRequest` 必须包含：

- 来源命令
- 候选 payload
- `payload_hash`
- 过期时间
- 幂等键
- 当前状态

#### 复合写入

`WriteRequest` 必须支持 `operations[]`，用于一次用户确认后写入多个对象。

示例：

```text
operations
├─ create todo temp_id=item_1
└─ create reminder depends_on=item_1
```

要求：

- 复合写入必须在一个事务里执行。
- 任一 operation 失败，整个 `WriteRequest` 回滚并进入 `failed`。
- operation 可以通过 `temp_id` 和 `depends_on` 引用同一请求中刚创建的对象。
- `payload` 面向机器执行，`preview` 面向用户确认，两者必须分离。
- 服务端使用 `payload_hash` 校验客户端不能篡改候选。

#### WriteRequest 状态

```text
pending
confirmed
applied
rejected
expired
failed
superseded
```

#### 风险等级

| 风险 | 示例 |
| --- | --- |
| `low` | 查询、延后提醒、标记完成 |
| `normal` | 新增待办、新增日历、新增提醒、保存地点 |
| `high` | 修改时间、修改地点、删除提醒、删除事项、覆盖已有地点 |
| `critical` | 批量删除、批量重排、覆盖多个提醒、后续云端电话或短信触达 |

#### 过期时间

| 请求类型 | 过期时间 |
| --- | --- |
| 普通新增 / 修改 | 15 分钟 |
| 删除 / 取消提醒 | 5 分钟 |
| 定位相关请求 | 5 分钟 |
| 停车位置保存 | 2 分钟 |

#### 确认卡片可编辑字段

| 对象 | P0 可编辑字段 |
| --- | --- |
| 日历 | 标题、开始时间、结束时间、地点文本、备注 |
| 待办 | 标题、截止时间、备注 |
| 提醒 | 提醒时间、触发地点、半径、提醒方式 |
| 地点 | 地点名称、地点类型、半径、文字描述 |

## 6. WebSocket 架构

### 6.1 WS 职责

WebSocket 只做实时同步：

- 连接管理
- 命令状态推送
- 待确认状态推送
- 写入结果推送
- 提醒触发推送
- 断线补拉协调
- 活跃会话状态同步

不负责：

- ASR
- 业务写入
- 规则引擎执行
- 数据库读写

### 6.1.1 WS 连接策略

WS 只保证活跃会话的实时同步，不保证 App 后台或被系统杀死后仍持续在线。

策略：

- 前台活跃时优先保持 WS 连接
- 进入后台后允许短时间保活，超时后断开并进入重连状态
- 设备离线、网络中断、心跳超时、App 被系统杀死后，WS 视为不可达
- 断线后优先通过 `sync.request` 补拉状态，必要时回退到 HTTP 全量刷新
- 地点提醒不能依赖 WS 长连本身触发，只能依赖设备侧位置事件或云端兜底策略
- 时间提醒在 WS 不可达时，仍可由服务端按 `trigger_at` 进入云端兜底
- WS 不承载跨设备一致性；单设备同步的最终事实以服务端 LWW 结果为准

连接状态：

```text
connecting
connected
reconnecting
syncing
offline
failed
```

### 6.2 WS 消息类型

- `connection.ready`
- `connection.heartbeat`
- `command.status.changed`
- `write_request.created`
- `write_request.updated`
- `write_request.applied`
- `write_request.rejected`
- `reminder.armed`
- `reminder.due`
- `reminder.delivered`
- `reminder.dismissed`
- `reminder.snoozed`
- `reminder.cancelled`
- `reminder.expired`
- `reminder.failed`
- `notification.registration.succeeded`
- `notification.registration.failed`
- `notification.fallback.requested`
- `notification.fallback.sent`
- `notification.fallback.failed`
- `sync.request`
- `sync.response`

### 6.3 事件格式

所有事件都带统一元数据：

```text
event_id
event_type
aggregate_type
aggregate_id
version
occurred_at
payload
```

### 6.4 断线与补拉

- 客户端保存 `last_event_cursor`
- 重连后发起 `sync.request`
- 服务端按 cursor 补发遗漏事件
- 相同事件按 `event_id` 去重
- 乱序按 `version` 收敛
- 本期只做单设备同步，不做多设备抢写、抢提醒或主设备切换
- 本地编辑先写入本地缓存，再上传到服务端，再回灌下载最新状态
- 同步采用 LWW 语义，以服务端接受的最新写入作为事实来源
- 如果本地提交早于服务端最新版本，则服务端返回最新状态，客户端覆盖本地视图
- 如果本地离线期间有积压变更，恢复连接后按本地队列顺序逐个上传，再以服务端最新快照回灌

## 7. AI 层

AI 层只做两件事：

1. 把自然语言转成结构化命令
2. 给出候选，不直接写库

### 7.1 AI 组件

- `ASRProvider`
- `CommandParser`
- `CandidateResolver`

代码实现位于 `timeapp/ai`（`ai/asr` 是 ASR 客户端，`ai/parser` 是 `LLMCommandParser`/`MockCommandParser`），不要放进未分层的顶层包。

### 7.2 AI 与 capability 的关系

AI 不决定 capability 的存在与否，只负责生成对应能力的候选命令。

例如：

- “明天下午三点开会” -> `calendar.create`
- “把这个长待办拆一下” -> `long_task_split.request`
- “明天太满了帮我重排” -> `replan.request`
- “工作日早上到公司提醒我打卡” -> `smart_reminder.create`

地点提醒示例：

```text
“到家后提醒我取快递”
  -> ParsedCommand(action=create, entity=todo, title=取快递)
  -> ParsedCommand(action=remind, entity=reminder, trigger_type=enter_place, place_ref=家)
  -> ReferenceResolver 解析或反问确认 Place
  -> WriteRequest(payload = create Todo + create Reminder)
  -> 用户确认
  -> Todo + Reminder 写入同一事务
```

该场景属于 P0 基础地点提醒，不是独立地点产品。提醒必须绑定 `item_id`，因此系统先创建 `Todo`，再创建 `Reminder`。

### 7.3 指代消解和候选定位

指代消解采用“LLM 解析约束，系统查库定位”的方式：

```text
用户语音
  -> ASR
  -> LLM 解析意图和约束
  -> ReferenceResolver 确定性查库
  -> CandidateList / Clarification / WriteRequest
  -> 用户选择或补充
  -> WriteRequest
  -> 用户确认
  -> Capability Handler 写入
```

LLM 可以做：

- 解析动作、对象类型、时间范围、标题关键词、地点表达和修改内容
- 抽取“刚才那个”“第二个”“明天的会议”等引用表达
- 生成自然语言反问文案
- 解析用户对反问的补充回答

LLM 不可以做：

- 直接查数据库
- 直接决定数据库 ID
- 编造候选列表
- 直接写入
- 跳过 `WriteRequest`

`ReferenceResolver` 负责：

- 当前待确认对象
- 最近候选列表
- 最近交互对象窗口
- 带明确约束的业务查询
- 多候选排序
- 返回候选列表或澄清问题

匹配结果规则：

| 结果 | 处理 |
| --- | --- |
| 唯一匹配 | 生成候选或 `WriteRequest` |
| 多个匹配 | 返回候选列表，让用户选择 |
| 无匹配 | 反问或提示未找到 |
| 低置信度 | 反问 |
| 高风险操作 | 即使唯一匹配也必须强确认 |

## 8. Capability Packs 设计

### 8.1 能力包最小清单

每个 capability 至少说明这些内容。它是工程清单，不是运行时插件框架：

```text
Capability Package
├─ name
├─ command_handlers
├─ query_handlers
├─ domain_events
├─ projections
├─ policies
├─ permissions
├─ migrations
└─ acceptance_tests
```

P0 实现时可以用普通模块和显式路由表表达，不要求自动发现或动态注册。

#### 8.1.1 `voice_command` 和 `realtime` 不是同一种 capability

`calendar`/`todo`/`reminder`/`long_task_split`/`replan`/`smart_reminder` 都是"通过 `WriteRequest` 确认门禁写入业务事实"的能力，符合 8.1 的最小清单。

`voice_command` 和 `realtime` 不是这种能力：

- `voice_command` 是语音进入命令管道的入口，真实实现是 `ai/asr`（转录）+ `ai/parser`（解析）+ `application/service.py` 的 `submit_voice_command`（编排反问、候选、写入请求）。它不持有自己的 `command_handlers`，而是产出交给其他 capability 处理的 `Command`。
- `realtime` 是 WS 连接和事件广播的传输边界，真实实现是 `api/realtime.py` 的 `RealtimeConnectionManager`。它不持有业务事件，只订阅其他 capability 产出的 `DomainEvent` 并广播。

`capabilities/voice_command/`、`capabilities/realtime/` 保留为空包只是文档对齐的命名占位，不需要把 `application`/`api` 里的实现搬进去——这样搬只是把代码挪个地方，不会让架构更清楚。15.2 节里把它们标记为 "active" 指的是链路已激活，不代表它们应该长成 calendar/todo/reminder 那种带 `command_handlers` 的能力包。

### 8.2 Calendar Capability

负责：

- 日历事项创建、修改、删除、查询
- 时间校验
- 冲突提示

### 8.3 Todo Capability

负责：

- 待办创建、修改、删除、查询
- 完成 / 取消完成
- 截止时间和状态管理

### 8.4 Reminder Capability

负责：

- 时间提醒
- 基础地点提醒
- 提醒状态流转
- 通知投递
- 单事项多提醒
- 提醒动作处理
- 所有提醒绑定 `item_id`
- 独立地点提醒通过系统创建轻量 Todo 后绑定提醒
- `Place` 和 `RepeatRule` 目前只服务于提醒触发，没有独立 capability；它们的创建、更新、校验也由 reminder capability 持有

### 8.5 Long Task Split Capability

负责：

- 将一个长待办拆成多个待确认子事项
- 生成拆分候选
- 复用 confirmation gate 和 items

### 8.6 Replan Capability

负责：

- 根据冲突和用户明确请求生成调整候选
- 不自动应用
- 复用 write request、version、event、ws

### 8.7 Smart Reminder Capability

负责：

- 组合时间、地点、天气、噪声、设备状态、用户偏好
- 生成提醒规则
- 选择触发和投递策略
- 拆分为本地提醒和云端提醒两个演进方向

它不是“环境能力集合”，而是一个使用 context / policy 的高级提醒能力。

#### 本地提醒方向

- 主要使用设备本地的时间和地点触发
- 主要使用本地通知、震动和语音播报
- 适合 P0/P1 的即时提醒链路

#### 云端提醒方向

- 通过短信、邮件、电话等通道兜底或升级触达
- 适合更高优先级或本地不可达场景
- P0 只保留结构和接口，不接真实供应商
- 若后续接入 Expo Push Service，Android 远程推送链路需要考虑 FCM、Google Play services 和厂商后台限制；无 GMS 或 MIUI 省电限制下不能承诺稳定送达
- 云端兜底由 `DeliveryPolicy` 决定，触发条件包括 WS 心跳超时、本地通知注册失败、设备未回传 delivered、用户启用高优先级兜底等
- 时间提醒可以由云端按服务端时间触发；地点提醒依赖设备侧定位事件，设备进程被杀且无位置事件回传时，云端只能发送延迟兜底提示，不能准确判断到达或离开

## 9. 数据模型

### 9.1 Core Tables

| 表 | 作用 |
| --- | --- |
| `voice_commands` | 保存识别结果、解析状态、错误码 |
| `write_requests` | 所有写入的确认门禁 |
| `domain_events` | 领域事件审计与补拉来源 |

P0 断线补拉不持久化服务端游标：客户端在 WS `sync.request` 里带上自己保存的 `last_event_cursor`（一个整数），服务端按这个游标从 `domain_events` 里补发。多设备各自独立游标、服务端不需要按用户/设备存储游标状态。等到需要多设备协同游标或跨会话补发时，再引入按用户/设备持久化的游标表。

### 9.2 Shared Item Tables

| 表 | 作用 |
| --- | --- |
| `items` | calendar / todo 的统一事项表 |
| `reminders` | 提醒规则与触发状态 |

#### `reminders` P0 字段

```text
id
user_id
item_id
version
trigger_type: time / enter_place / leave_place / return_to_place
trigger_at
place_id
priority
delivery_channel: local_notification
repeat_pattern: none / daily / weekdays / custom_weekdays
repeat_weekdays
repeat_time_of_day
repeat_end_at
repeat_timezone
series_status: active / paused / stopped
status: pending / armed / triggered / delivered / dismissed / snoozed / cancelled / expired / failed
snooze_count
last_triggered_at
local_notification_id
local_registration_status: pending / registered / failed / unavailable
last_delivery_ack_at
fallback_policy: none / cloud_if_unreachable / cloud_after_timeout
fallback_channels: push / sms / email / call
fallback_after_seconds
fallback_sent_at
fallback_status: not_required / pending / sent / failed
expires_at
failed_reason
created_at
updated_at
cancelled_at
```

约束：

- `item_id` 必填，提醒不能脱离事项存在。
- 一个 `item` 可以绑定多条 `reminder`。
- 时间提醒使用 `trigger_at`。
- 地点提醒使用 `place_id` 和 `trigger_type`。
- `return_to_place` 创建后先等待用户离开原地点，再进入 `armed`，下一次进入才触发。
- P0 只启用 `delivery_channel=local_notification`。
- 云端兜底字段可先保留但不接真实供应商；当本地不可达时由后续 `CloudDeliveryAdapter` 使用。
- `repeat_pattern` 只保留最小集合：`daily`、`weekdays`、`custom_weekdays`。
- 重复规则必须至少有 `repeat_time_of_day`；地点重复还必须有 `place_id`。
- 不支持月度、年度、cron、复杂例外、单次补做、单次跳过或单次例外编辑。
- 重复规则只支持整条系列的开启、关闭和未来修改。
- 重复规则与普通提醒各自独立触发，但展示时仍挂在同一事项卡片内。
- 删除和停用只支持整条系列级别操作，不支持单次 occurrence 独立删除或改写。

### 9.3 Smart Reminder Tables

| 表 | 作用 |
| --- | --- |
| `places` | 用户确认后的固定地点 |
| `reminder_rules` | 提醒规则 |
| `user_reminder_preferences` | 静默时段、音量、震动、频率等偏好 |
| `reminder_rule_conditions` | 多条件组合 |
| `reminder_occurrences` | 触发记录与冷却控制 |

### 9.4 Extension Tables

后续 capability 可自带自己的表，但必须通过统一命名和迁移方式接入。

示例：

- `long_task_plans`
- `split_candidates`
- `replan_requests`
- `replan_candidates`

## 10. 上下文与策略

### 10.1 时间

- 时区统一保存为 `timestamptz`
- 所有展示使用用户时区
- 时间窗口和周期规则在 context 层解析

### 10.2 地点

- 固定地点使用用户确认过的 `Place`
- 当前位置只作为本次判断输入，不形成持续轨迹历史
- 地点权限拒绝时降级为文字地点或时间提醒
- P0 固定地点先支持“家”“公司”和自定义地点
- P0 支持一键保存当前地点，用于临时地点提醒和停车找车场景
- 临时地点保存 `latitude`、`longitude`、`accuracy_meters`、`radius_meters`、`description` 和 `created_at`
- 地点提醒半径默认 `100m`，允许用户选择 `50m / 100m / 200m`
- 停车位置只是临时地点的一种，不单独建立停车模块
- P0 不支持停留时长触发；停留触发是指进入地点后持续停留超过指定时长才触发，后续作为位置增强能力实现

### 10.3 天气

- 天气作为 context provider 输入
- provider 不可用时，依规则降级或不触发

### 10.4 噪声

- 噪声仅影响提醒触达方式或延后策略
- 不把噪声本身写成核心业务事实

### 10.5 设备状态

- 耳机、电量、勿扰、驾驶模式等进入 context layer
- device state 影响 policy，不直接修改事项

### 10.6 用户偏好

- 静默时段
- 声音 / 震动
- 频率限制
- 低电量策略
- 低优先级策略

## 11. 提醒执行链路

```text
ReminderRule
  -> Context Providers
  -> Condition Evaluation
  -> Delivery Policy Selection
  -> Trigger Occurrence
  -> Local Notification / WS
  -> Delivery Ack Check
  -> Optional Cloud Fallback
```

### 11.1 P0 Trigger 行为

| Trigger | 输入 | 行为 |
| --- | --- | --- |
| `time` | `trigger_at`、`timezone` | 到指定时间触发 |
| `enter_place` | `place_id`、`radius_meters` | 进入地点半径后触发 |
| `leave_place` | `place_id`、`radius_meters` | 离开地点半径后触发 |
| `return_to_place` | 当前地点、`radius_meters`、文字描述 | 先等待离开，再次进入后触发 |

规则：

- 过去时间不能创建时间提醒，必须反问。
- 当前已在目标地点内创建 `enter_place` 时，不能立即触发，必须反问是否下次到达提醒。
- 当前不在目标地点创建 `leave_place` 时，允许创建，但确认卡片必须提示风险。
- `return_to_place` 创建后初始为 `pending`，检测到用户离开半径后进入 `armed`，再次进入后触发。
- 定位精度差于触发半径时允许创建，但必须在 preview 中提示提醒可能不准。
- 定位权限拒绝时，不创建后台位置监听，降级为普通 Todo + 文字地点记录或时间提醒。

### 11.2 投递策略

默认投递顺序：

```text
本地通知 / 前台 WS
  -> 等待设备注册和 delivered 回执
  -> 若不可达或超时，按 fallback_policy 判断是否云端兜底
  -> 云端短信 / 邮件 / 电话
```

本地路径不可达的判断信号：

- WS 心跳超时
- 客户端离线
- 本地通知注册失败
- 本地通知权限拒绝
- 提醒触发后超过等待窗口仍无 `delivered` 回执

云端兜底规则：

- 时间提醒可以由服务端按 `trigger_at` 触发云端兜底。
- 地点提醒需要设备侧位置事件；如果设备进程被杀且没有位置事件，云端不能准确判断进入或离开，只能在配置的等待窗口后发送补救提示。
- P0 可以保留 `fallback_policy` 和状态字段；真实短信、邮件、电话 adapter 后续接入。

### 11.3 触发结果

触发后产生统一事件：

- `reminder.due`
- `reminder.armed`
- `reminder.delivered`
- `notification.registration.succeeded`
- `notification.registration.failed`
- `notification.fallback.requested`
- `notification.fallback.sent`
- `notification.fallback.failed`
- `reminder.dismissed`
- `reminder.snoozed`
- `reminder.cancelled`
- `reminder.expired`
- `reminder.failed`

### 11.4 冷却与去重

- 同一规则在冷却期内不重复触发
- 事项删除或取消后对应提醒失效
- 事项变更后，受影响的提醒取消或重新计算；不受影响的提醒继续有效

## 12. 接口边界

### 12.1 HTTP

HTTP 负责：

- 创建音频命令
- 查询事项、提醒、规则
- 提交确认 / 拒绝
- 管理设置和权限状态

### 12.2 WS

WS 负责：

- 实时事件接收
- 状态更新
- 提醒弹出协调
- 前台 / 后台同步

### 12.3 统一约束

- HTTP 和 WS 都必须进入同一 application layer
- 不允许各自实现一套业务逻辑
- 写入只能走 capability handler + confirmation gate

## 13. 移动端单页结构

P0 移动端不拆多页导航，只做一个日程主面板和一个语音弹出层。

### 13.1 主面板

```text
CalendarShell
├─ ViewModeSwitch: today / week / month
├─ ScheduleSurface
├─ ItemInlineReminderBadges
├─ SyncStatus
└─ VoiceDockButton
```

职责：

- 展示今日、周、月日程视图
- 展示手动添加和语音创建的事项
- 待办作为事项展示，可以没有具体开始时间
- 提醒作为事项附属信息展示，不做独立一级提醒列表
- 展示同步状态和离线状态

### 13.1.1 ItemCard 语义

主面板以统一事项卡片为基本渲染单元：

- 主对象只有 `calendar_event` 和 `todo`
- 提醒以 badge、副文案或折叠摘要显示
- 一个事项可有多条提醒，默认折叠，超过两条显示 `+N`
- 卡片点击后在底部浮层展开详情和编辑动作
- 完成、取消、删除都走卡片内动作，不开新页面
- 日程视图按时间排序，地点提醒以附属信息形式补充在卡片中

#### 字段优先级

##### `calendar_event`

1. 时间
2. 标题
3. 地点
4. 提醒 badge
5. 备注摘要

##### `todo`

1. 标题
2. 截止时间或提醒时间
3. 提醒 badge
4. 状态
5. 备注摘要

##### 动作优先级

- `todo` 未完成：`完成` -> `编辑` -> `删除`
- `todo` 已完成：`取消完成` -> `编辑` -> `删除`
- `calendar_event`：`编辑` -> 提醒相关动作 -> `删除`
- 提醒相关动作只出现在提醒 badge 或详情浮层内：`延后` -> `取消提醒` -> `编辑规则`
- 危险动作永远放最后

#### RepeatBadge 语义

- 重复 badge 只在 `repeat_pattern != none` 时显示
- 重复 badge 始终排在提醒 badge 之前
- 重复 badge 只显示短摘要，不展开完整规则
- 摘要由 `repeat_pattern`、`repeat_time_of_day`、`repeat_weekdays`、`place_id` 和当前时区计算得到
- 文案示例：
  - `每天 8:00`
  - `工作日 8:00`
  - `周一·周三·周五 8:00`
  - `每天到家后`
  - `工作日到公司 8:00`
- 同一事项有重复和提醒时，先渲染 RepeatBadge，再渲染 ReminderBadge
- RepeatBadge 只表达系列规则，不表达单次 occurrence

### 13.2 语音弹出层

```text
VoiceCommandSheet
├─ RecordingCard
├─ TranscriptCard
├─ ClarificationCard
├─ CandidateListCard
├─ WriteRequestPreviewCard
└─ ResultCard
```

职责：

- 录音和转写
- 展示反问
- 展示候选列表
- 展示确认卡片
- 支持确认、取消、改一下
- 支持卡片内编辑时间、地点、半径和标题等 P0 字段

#### 顺序约束

语音弹层按固定状态流切换：

```text
RecordingCard -> TranscriptCard -> ClarificationCard -> CandidateListCard -> WriteRequestPreviewCard -> ResultCard
```

规则：

- 录音中优先显示 `RecordingCard`
- 转写完成进入 `TranscriptCard`
- 缺参或指代不清时进入 `ClarificationCard`
- 多候选时进入 `CandidateListCard`
- 生成写入候选后进入 `WriteRequestPreviewCard`
- 成功、失败、取消后进入 `ResultCard`
- 同一时刻只显示一个主卡片，不做多层页面堆叠

#### 重复规则确认卡片

`WriteRequestPreviewCard` 对重复规则的展示字段：

1. 规则标题
2. 重复类型：daily / weekdays / custom_weekdays
3. 重复时间：`repeat_time_of_day`
4. 重复日期：`repeat_start_at`、`repeat_end_at`
5. 地点：仅地点型重复显示
6. 触发方式：time / place / time + place
7. 生效范围：future series only
8. 提醒方式：local_notification
9. 风险提示：不支持单次例外、补做、跳过和 cron
10. 操作范围：series only

按钮顺序：

- Confirm
- Edit
- Cancel

#### 云端兜底窗口

- 时间提醒：本地触发后等待 `60s` 未确认送达时进入云端兜底；高优先级可缩短到 `15s`
- 地点提醒：本地触发后等待 `5min` 未确认送达时进入云端兜底；高优先级可缩短到 `2min`
- 地点提醒云端兜底只做补救提示，不承诺替代设备侧定位事件

### 13.3 交互边界

- 语音弹出层不跳转页面栈。
- 日程主面板不复制业务逻辑，只消费后端状态和本地缓存。
- 提醒触发、失败、权限异常以通知动作、顶部提示或语音卡片出现，不常驻独立提醒页。

## 14. P0 需要保留的扩展位

P0 先不实现，但架构必须已经容纳：

- 长任务拆分
- 重排
- 批量提醒管理
- 复杂位置条件
- 天气提醒
- 噪声提醒
- 设备状态提醒
- 云端通知
- 日程摘要

这些能力都应当通过新增 capability、context provider、policy、projection 或 channel adapter 加入，而不是重写主流程。

## 15. P0 激活范围

### 15.1 已激活路径

P0 运行时只激活以下链路：

```text
语音输入
  -> Mock / Real ASR
  -> CommandParser
  -> CommandRouter
  -> WriteRequest
  -> ConfirmationGate
  -> calendar / todo / reminder(time/place)
  -> DomainEvent
  -> WS Projection
  -> Local Notification Registration
  -> Optional Cloud Fallback State
  -> Mobile UI
```

### 15.2 已激活 capability

| Capability | P0 状态 | 范围 |
| --- | --- | --- |
| `voice_command` | active | 录音、转写、命令解析、反问、候选 |
| `calendar` | active | 一次性日历事项 CRUD 和查询 |
| `todo` | active | 一次性待办 CRUD、查询、完成 |
| `reminder` | active | 单事项多时间/地点提醒、本地通知、延后一次、取消 |
| `realtime` | active | WS 连接、事件推送、断线补拉 |

### 15.3 仅保留骨架的 capability

| Capability | P0 状态 | 允许存在的内容 | 禁止内容 |
| --- | --- | --- | --- |
| `long_task_split` | skeleton | 能力说明、小接口、验收占位 | 默认路由、真实写入 |
| `replan` | skeleton | 能力说明、小接口、验收占位 | 自动移动日程、真实写入 |
| `smart_reminder` | skeleton | 能力说明、规则结构、小接口占位 | 复杂地点围栏、天气、噪声、设备状态真实接入 |

### 15.4 已激活 context / policy

| 类型 | P0 状态 | 范围 |
| --- | --- | --- |
| `TimeContextProvider` | active | 用户时区、当前时间、时间窗口 |
| `PlaceContextProvider` | active | 固定地点、临时地点、当前位置记录 |
| `TimeTrigger` | active | 指定时间触发 |
| `EnterPlaceTrigger` | active | 进入地点触发 |
| `LeavePlaceTrigger` | active | 离开地点触发 |
| `LocalNotificationPolicy` | active | 本地通知 |
| `CloudFallbackPolicy` | minimal | 记录本地不可达判断、fallback 状态和待发送事件，不接真实供应商 |
| `CooldownPolicy` | minimal | 延后一次和基础去重 |

### 15.5 仅保留接口的 context / policy

| 类型 | P0 状态 |
| --- | --- |
| `WeatherContextProvider` | skeleton |
| `NoiseContextProvider` | skeleton |
| `DeviceStateContextProvider` | skeleton |
| `UserPreferenceContextProvider` | skeleton |
| `LocationCondition` | skeleton |
| `WeatherCondition` | skeleton |
| `NoiseCondition` | skeleton |
| `DeviceStateCondition` | skeleton |
| `VoicePolicy` | skeleton |
| `SmsDeliveryAdapter` | skeleton |
| `EmailDeliveryAdapter` | skeleton |
| `CallDeliveryAdapter` | skeleton |

### 15.6 P0 代码生成约束

- 可以生成目录、小接口、请求响应结构、消息结构、测试占位和 README。
- 不应接入真实天气、噪声、设备状态、地图、短信、邮件或电话服务。
- 不应让 skeleton handler 出现在默认 command route 中。
- 不应让 skeleton provider 参与 reminder decision。
- 不应为了未来能力引入复杂 DSL 或完整策略引擎。

## 16. 关键依赖规则

```text
interfaces -> application
application -> core + capabilities
capabilities -> core
core -> nothing concrete
ai -> command generation only
ws -> events only
infrastructure -> interface implementations
```

### 16.1 绝对禁止

- AI 直接写数据库
- WS 直接改业务事实
- capability 之间互相硬耦合
- context provider 反向依赖业务写入
- 新功能绕过 confirmation gate

## 17. MS1 骨架清单

- [x] Expo 项目可启动，录音可用
- [x] FastAPI 项目可启动，健康检查可用
- [x] WS 连接可建立并接收事件
- [x] `voice_commands` / `write_requests` / `domain_events` 基础表可迁移
- [x] Mock ASR 和 Mock Parser 可运行
- [x] 日历 / 待办 / 提醒的最小写入链路可确认
- [x] 今日列表和待确认列表可实时刷新
- [x] 断线补拉可用

## 18. 后续扩展建议

### 18.1 长任务拆分

新增 `long_task_split` capability，复用：

- `Command`
- `WriteRequest`
- `items`
- `DomainEvent`
- `WS projection`

### 18.2 重排

新增 `replan` capability，只产出候选，不自动应用。

### 18.3 智能提醒

新增 `smart_reminder` capability，复用 reminder 的 trigger / condition / policy / delivery 体系，扩展地点、天气、噪声、设备状态等上下文。

### 18.4 更多环境检测

后续如需加入周围空间是否嘈杂、空气质量、通勤状态等，只需新增 context provider 和 condition，不需要重建架构。
