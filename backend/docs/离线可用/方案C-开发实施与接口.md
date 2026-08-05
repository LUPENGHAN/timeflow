# 方案 C 开发实施与接口契约

本文把方案 C 分成两个边界：

1. **开发验证边界**：固定用户 `default_user`，验证 PowerSync SDK、Postgres 下行、SQLite 本地写入和上传回调。
2. **生产同步边界**：接入账号体系、服务端幂等、版本冲突和提醒计划。

开发验证边界不能部署到生产，也不能用来判断鉴权、幂等和冲突方案已经完成。

## 客户端能力分流与现有接口保留

方案 C 按**是否具备 PowerSync 能力**分流,不按 Android / iOS / Web 平台分流。

| 客户端 | 日程读取 | 日程写入 |
| --- | --- | --- |
| PowerSync 客户端 | PowerSync SQLite 查询和订阅 | 本地 SQLite → CRUD 队列 → `POST /api/v1/sync/push` |
| 非 PowerSync 在线客户端 | `schedule.list.query` / `schedule.updated` | 现有 WebSocket 日程命令 |

现有 `schedule.upsert.command`、`schedule.status.command`、`schedule.deleted`、`schedule.list.query` 和 `schedule.updated` 必须保留,用于硬件、未接入 PowerSync 的 Web 客户端及其他仅在线终端。PowerSync 客户端的一次操作不能同时调用这些接口和 `/sync/push`。

`/sync/push` 与现有 WebSocket handler 不是两套业务实现。二者必须作为协议适配器调用相同的 `ScheduleService`、领域校验、冲突检测、提醒计划计算和 `ScheduleRepository`。普通 WS 创建允许服务端生成 ID;PowerSync 离线创建必须由客户端先生成 UUID 并作为 `entity_id` 上传。

本文当前开发和生产目标契约仍使用 HTTP `POST /api/v1/sync/push`。如果后续决定让 PowerSync 上传复用 WebSocket 传输,应增加专用的 `sync.push.command` / `sync.push.result`,保持本节批次、幂等和版本契约不变;不能在 `uploadData` 中逐条调用普通 `schedule.upsert.command`。

## 一、最小验证闭环

```text
PowerSync Service  ──logical replication──>  Postgres.schedules
       │                                      ▲
       │ sync rules                           │
       ▼                                      │
App PowerSync SQLite ──uploadData──>  POST /api/v1/sync/push
```

PowerSync 服务负责下行同步和本地 CRUD 队列；TimeFlow 后端负责接收上传并写入 Postgres。提醒、TTS、WebSocket、闹钟都不属于这次最小闭环。

## 一、本地服务拓扑与启动顺序

你现在的 Brew PostgreSQL 可以继续作为**源数据库**。但还需要单独运行 PowerSync Service；PowerSync Service 不是 `timeflow-backend` 的 Python 包，也不是客户端 SDK。

```text
Brew PostgreSQL :5432
       ▲                 ┌───────────────┐
       │ logical WAL     │ PowerSync     │ :8080
       └─────────────────│ Service       │
                         └───────┬───────┘
                                 │ sync stream
                                 ▼
                         Timeflow App SQLite

Timeflow App ──uploadData──> TimeFlow API :8000──> Brew PostgreSQL
```

完整测试需要按下面顺序启动：

1. Brew PostgreSQL
2. PowerSync Service（本地 Docker 或 PowerSync Cloud 二选一）
3. TimeFlow FastAPI
4. Expo Development Build 真机/模拟器

### 1.1 准备 Brew PostgreSQL

先确认逻辑复制已经开启：

```bash
psql -h 127.0.0.1 -U timeapp -d timeapp -c "SHOW wal_level;"
```

结果必须是 `logical`。然后创建 PowerSync 只读复制账号和 publication（只执行一次）：

```sql
CREATE ROLE powersync_role WITH REPLICATION BYPASSRLS LOGIN PASSWORD 'change-this-password';
GRANT CONNECT ON DATABASE timeapp TO powersync_role;
GRANT USAGE ON SCHEMA public TO powersync_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO powersync_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO powersync_role;
CREATE PUBLICATION powersync FOR ALL TABLES;
```

如果角色或 publication 已经存在，不要重复执行创建语句，先查询：

```sql
SELECT rolname FROM pg_roles WHERE rolname = 'powersync_role';
SELECT pubname FROM pg_publication WHERE pubname = 'powersync';
```

### 1.2 启动本地 PowerSync Service

本地自托管需要 Docker；PowerSync Service 还需要自己的 bucket storage，不能只安装一个 npm 包。官方当前推荐用 PowerSync CLI 生成 Docker 配置：

```bash
npm install -g powersync
mkdir -p powersync-local
cd powersync-local
powersync init self-hosted
powersync docker configure --database external --storage postgres
```

这里的 `external` 很重要：它表示不再启动第二套 PostgreSQL，PowerSync 的 source 直接连接现有 Brew PostgreSQL；`storage postgres` 只启动 PowerSync 保存 bucket 元数据所需的内部 PostgreSQL。编辑生成的 `powersync/docker/.env`，把源数据库 URI 指向 Brew PostgreSQL。macOS Docker 通常使用 `host.docker.internal`：

```dotenv
PS_DATA_SOURCE_URI=postgresql://powersync_role:change-this-password@host.docker.internal:5432/timeapp
```

如果容器无法连接 Brew PostgreSQL，需要检查 PostgreSQL 的 `listen_addresses` 和 `pg_hba.conf`，允许 Docker 到主机的连接。不要直接把 PostgreSQL 端口开放到公网。

编辑 `powersync/sync-config.yaml`，开发阶段先只同步固定测试用户：

```yaml
config:
  edition: 3

streams:
  schedules:
    auto_subscribe: true
    queries:
      - SELECT * FROM schedules WHERE user_id = 'default_user'
```

启动并查看状态：

```bash
powersync docker start
powersync status
```

默认把 PowerSync Service 暴露在 `8080`。如果你不想在本机维护 Docker，也可以使用 PowerSync Cloud；但 Brew PostgreSQL 必须能被云端访问，`127.0.0.1` 不能直接作为 Cloud 的数据库地址。

### 1.3 启动 TimeFlow API 和 App

```bash
cd backend
TIMEFLOW_ENVIRONMENT=development .venv/bin/uvicorn timeflow.main:app --reload
```

前端 `.env`：

```dotenv
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1
EXPO_PUBLIC_POWERSYNC_URL=http://10.0.2.2:8080
EXPO_PUBLIC_POWERSYNC_TOKEN=<local-jwt-expiring-within-24-hours>
EXPO_PUBLIC_POWERSYNC_ENABLED=true
EXPO_PUBLIC_POWERSYNC_UPLOAD_SMOKE=false
```

然后必须使用 Development Build：

```bash
cd frontend
npx expo run:android
```

Android 模拟器访问宿主机用 `10.0.2.2`；iOS 模拟器通常用 `127.0.0.1`；真机使用 Mac 的局域网 IP。

PowerSync Service 也需要客户端凭证。即使 PowerSync 在本地运行，`EXPO_PUBLIC_POWERSYNC_TOKEN` 仍不能留空；它需要由鉴权工作流提供一个开发 token。没有 token 时，App 不会建立同步连接。

这里必须使用 PowerSync 能验证的标准 JWT；`service.yaml` 中 `api.tokens` 的管理 token 不能作为客户端 token。PowerSync 要求客户端 JWT 的有效期不超过 24 小时。本地验证配置使用 `sub=default_user`，生产环境改为由账号服务签发短期 JWT。

App 启动后会自动创建 PowerSync SQLite 并连接 Service。当前正式日程 UI 已从 PowerSync SQLite 读取和订阅,但新增、编辑、状态修改和删除仍暂时委托给原 WebSocket Repository。当前阶段应同时检查设备 SQLite、Postgres 和 `/sync/push` 请求,不要把日程页面显示正常误认为上行同步已经完成。

需要验证本地 SQLite 上行时，可临时设置
`EXPO_PUBLIC_POWERSYNC_UPLOAD_SMOKE=true`。App 会以固定 ID
`powersync_live_upload_test` 写入一次本地日程，并经 `uploadData` 调用
`POST /api/v1/sync/push`。验证完成后必须恢复为 `false`，并删除服务端测试数据。

## 二、开发验证接口

### 2.1 `POST /api/v1/sync/push`

该路由只在 `TIMEFLOW_ENVIRONMENT=development` 或 `test` 时注册，固定把所有操作写入 `default_user`。

请求：

```json
{
  "operations": [
    {
      "operation_id": "powersync-client:12:48",
      "entity": "schedules",
      "entity_id": "schedule_dev_1",
      "operation": "create",
      "base_version": null,
      "payload": {
        "source_mode": "manual",
        "schedule_type": "time",
        "status": "scheduled",
        "title": "PowerSync 验证",
        "notes": null,
        "start_time": "2026-08-04T07:00:00+00:00",
        "end_time": null,
        "timezone": "UTC",
        "location_name": null,
        "location_address": null,
        "latitude": null,
        "longitude": null,
        "geofence_radius_meters": 100,
        "geofence_armed": 0,
        "time_remind_offset_minutes": 15,
        "time_triggered_at": null,
        "geo_triggered_at": null,
        "created_at": "2026-08-04T06:00:00+00:00",
        "updated_at": "2026-08-04T06:00:00+00:00"
      }
    }
  ]
}
```

`operation` 的含义：

| 值 | 开发验证行为 |
| --- | --- |
| `create` | 以 `entity_id` 新建一条日程；ID 已存在返回 `conflict` |
| `update` | 只更新 `payload` 中出现的字段 |
| `delete` | 把 `status` 改为 `deleted`，不物理删除 |

成功响应：

```json
{
  "results": [
    {
      "operation_id": "powersync-client:12:48",
      "entity_id": "schedule_dev_1",
      "status": "applied",
      "message": null
    }
  ]
}
```

开发模式的结果状态：`applied`、`not_found`、`conflict`、`rejected`。

开发模式明确**没有**：

- `Authorization` 校验
- `sync_operations` 幂等表
- `version` / `base_version` 冲突判定
- 字段级合并
- 服务端提醒计划返回

因此，网络请求在服务端提交成功、客户端响应丢失时，重复提交可能返回 `conflict`。这是测试边界，不是生产错误处理策略。

### 2.2 生产接口目标契约

开发接口的 JSON 结构保留为生产接口的基础，后续由账号和同步负责人补充以下语义：

请求头：

```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

生产结果状态：

| 状态 | 客户端行为 |
| --- | --- |
| `applied` | 接受服务端结果并完成 PowerSync transaction |
| `duplicate` | 幂等终态，接受已存在的服务端结果并完成 transaction |
| `conflict` | 用服务端版本覆盖本地，提示用户，不自动重试原操作 |
| `rejected` | 校验失败，记录错误并由产品决定是否丢弃本地操作 |

HTTP 状态建议：

| HTTP | 语义 | PowerSync 行为 |
| --- | --- | --- |
| `200` | 批次已处理，逐条结果见 `results` | 解析结果后完成 transaction |
| `401` | 凭证失效 | 刷新凭证后重试 |
| `403` | 用户无权操作实体 | 终态错误，不能继续重试 |
| `422` | 请求结构或业务字段非法 | 终态错误，不能把数据静默丢掉 |
| `500/502/503` | 服务端暂时失败 | 抛异常，保留本地队列并重试 |

生产端必须从 token 的用户身份取得 `user_id`，不能接受 payload 中的 `user_id` 作为授权依据。

## 三、PowerSync 客户端验证代码

已加入以下验证骨架：

- [schema.ts](../../../frontend/src/infrastructure/powersync/schema.ts)：`schedules` 本地 Schema
- [connector.ts](../../../frontend/src/infrastructure/powersync/connector.ts)：`fetchCredentials` 与 `uploadData`
- [database.ts](../../../frontend/src/infrastructure/powersync/database.ts)：React Native 数据库实例

本地环境变量：

```dotenv
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1
EXPO_PUBLIC_POWERSYNC_URL=https://<powersync-endpoint>
EXPO_PUBLIC_POWERSYNC_TOKEN=<development-token>
```

`EXPO_PUBLIC_POWERSYNC_TOKEN` 仍然需要一个能被 PowerSync 服务接受的开发凭证；这个值由鉴权工作流提供。Connector 已经把凭证读取抽成 `tokenProvider`，不需要改同步协议。

验证启动方式：

```typescript
const database = createTimeflowPowerSyncDatabase();
const connector = createDevelopmentPowerSyncConnector();

await database.connect(connector);
```

首次验证建议单独做一个开发页面，只提供三项操作：查询 `schedules`、插入一条本地日程、修改/删除这条日程。不要先替换正式 `ScheduleRepository`，先观察本地 SQLite 查询和上传队列是否符合预期。

后端本地启动：

```bash
cd backend
TIMEFLOW_ENVIRONMENT=development .venv/bin/uvicorn timeflow.main:app --reload
```

开发接口可以先用 curl 验证：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sync/push \
  -H 'Content-Type: application/json' \
  -d '{
    "operations": [{
      "operation_id": "curl-create-1",
      "entity": "schedules",
      "entity_id": "schedule_curl_1",
      "operation": "create",
      "payload": {
        "source_mode": "manual",
        "schedule_type": "time",
        "status": "scheduled",
        "title": "curl 验证",
        "start_time": "2026-08-04T07:00:00+00:00",
        "timezone": "UTC",
        "geofence_radius_meters": 100,
        "geofence_armed": 0,
        "time_remind_offset_minutes": 15,
        "created_at": "2026-08-04T06:00:00+00:00",
        "updated_at": "2026-08-04T06:00:00+00:00"
      }
    }]
  }'
```

验证完成后用现有 WebSocket 日程删除协议或直接删除测试数据，避免污染开发数据库。

## 四、PowerSync 配置要求

### 4.1 Postgres

- `wal_level=logical`
- PowerSync 使用的数据库账号能读取逻辑复制所需的变更
- 测试数据库允许 PowerSync 服务访问
- publication / replication slot 由 PowerSync 部署方式按官方配置创建

### 4.2 Sync rules

规则必须按当前 PowerSync 服务版本的配置格式编写。语义应当是：只下发当前用户的日程。

```yaml
streams:
  schedules:
    query: |
      SELECT * FROM schedules
      WHERE user_id = token_parameters.user_id
```

上面的字段名是契约示意，正式提交前要按实际 PowerSync 版本确认 token 参数名称和 YAML 结构。

### 4.3 三处字段一致

以下三份定义必须同步更新：

1. Postgres/Alembic `schedules`
2. PowerSync sync rules
3. 客户端 `timeflowPowerSyncSchema`

当前验证骨架沿用现有 `schedules` 表字段，尚未加入生产所需的 `version`；生产同步切换前必须补版本列和迁移。

## 五、正式实现分阶段

### 阶段 0：本次验证

- 安装 PowerSync 2.0.0、`@op-engineering/op-sqlite` 17.x
- 真机 Development Build 启动数据库
- PowerSync 下行收到一条 Postgres 日程
- 本地 INSERT / PATCH / DELETE 能调用开发 push 接口
- App 重启后本地 SQLite 数据仍存在

### 阶段 1：生产同步基础

- `schedules.version`
- `sync_operations(operation_id, applied_at)`
- 客户端 UUID 创建
- 服务端按用户授权
- push 批次事务、幂等、版本冲突
- 生产错误状态与重试策略
- `/sync/push` 与现有 WS handler 复用同一个 `ScheduleService` 和仓储

### 阶段 2：正式客户端接入

- PowerSync Provider 放入 App composition root
- `ScheduleRepository` 改为 SQLite 查询/订阅
- PowerSync 客户端的日程 CRUD 全部本地优先,禁止与普通 WS 日程命令双写
- 保留现有 WS upsert/list/status/delete/push 接口供非 PowerSync 客户端使用
- 保留 WebSocket 作为提醒、语音、位置通道
- 网络恢复和回前台触发同步
- 加入多用户隔离、重启、杀进程、重复提交测试

### 阶段 3：提醒集成

- 服务端权威提醒计划的传输模型
- 客户端只执行计划，不重新计算权威触发时刻
- `time_triggered_at` 改为 ACK 后写入
- 本地兜底、内存去重、闹钟重建
- 计划恢复不能只依赖 push 响应；建议增加服务端只读的 `reminder_plans` 投影

## 六、验收清单

- [ ] 真机能编译并打开 PowerSync SQLite
- [ ] Postgres 新增日程能下发到本地
- [ ] 本地离线新增/修改/删除跨 App 重启保留
- [ ] 恢复网络后开发 push 接口收到对应 CRUD
- [ ] 开发模式重复 create 明确返回 `conflict`，没有被误称为幂等成功
- [ ] 正式接口已经接入 JWT 后再开放共享环境
- [ ] 正式接口完成 `operation_id` 幂等后，才测试响应丢失重试
- [ ] 提醒计划设计完成后，再把正式日程 CRUD 写入切到 PowerSync 本地优先路径
- [ ] PowerSync 客户端和普通 WS 客户端写入相同业务数据时执行同一套领域校验
- [ ] 同一个客户端的一次操作不会同时进入 `/sync/push` 和普通 WS 日程接口
