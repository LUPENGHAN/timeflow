# 地理围栏提醒说明

## 1. 问题定义

地点提醒需要解决两件不同的事情：

1. 系统能否在应用进入后台、甚至应用进程不存活时，判断设备是否穿过围栏边界。
2. 系统判断完成后，能否把提醒可靠地展示出来，并且使用和时间提醒一致的全局提醒页面。

这两个问题不能用“应用启动时读到一次当前位置”来证明。一次主动定位只能回答“此刻设备大概在哪里”，不能证明 Android 已经产生了地理围栏 `enter` 或 `exit` 事件。

## 2. 当前架构

当前地点提醒使用 Expo Location 的系统地理围栏能力：

```text
Android GeofencingClient / iOS CLCircularRegion
    -> 系统判断 enter / exit
    -> Expo TaskManager 地理围栏任务
    -> frontend/src/infrastructure/location/geofenceTask.ts
    -> LocalReminderApplication 的围栏状态机
    -> Android nativePresentNow
    -> AlarmSoundService 全局提醒页面
```

### 哪一部分由系统完成

- 围栏中心、半径和进出判断由 Android/iOS 的系统定位服务完成。
- JS 不负责持续轮询 GPS，也不在正常系统回调路径中重新计算距离。
- 系统只在它认为发生了 `enter` 或 `exit` 后回调任务。

### 哪一部分仍然经过 JS

Expo 的 `startGeofencingAsync()` 使用 TaskManager 把系统事件交给 JavaScript 任务。因此当前实现不是“完全不经过 JS”：

- 系统负责计算边界。
- JS 负责接收系统事件、更新提醒状态并调用原生展示接口。
- Android 最终通过 `AlarmSoundService` 显示全局页面。

应用进程被系统回收时，Expo 可能启动 headless JS 任务接收围栏回调。这个能力受系统、省电策略、权限和厂商 ROM 影响，不能等同于时间闹钟的纯原生链路。

## 3. 与时间提醒的区别

时间提醒的路径是：

```text
Android AlarmManager
    -> AlarmReceiver
    -> AlarmSoundService
```

它不依赖 React 页面或 Metro，也不需要 JS 参与触发，所以应用被杀后更稳定。

地点提醒当前的后台路径是：

```text
Android GeofencingClient
    -> Expo headless TaskManager / JS
    -> nativePresentNow
    -> AlarmSoundService
```

因此地点提醒日志中通常不会出现 `AlarmReceiver: onReceive action=com.timeflow.FIRE_ALARM`。出现 `geofence-...` 的 `presentNow` 才表示地点提醒路径请求了原生全局页面。

如果产品要求地点提醒和时间提醒一样完全不依赖 JS，需要进一步实现 Android 原生 `GeofencingClient + BroadcastReceiver`，由原生 Receiver 直接启动 `AlarmSoundService`。当前 Expo 方案还没有达到这个级别。

## 4. 围栏状态机

到达地点提醒采用边沿触发：

```text
初始在圈内       -> 不提醒
圈外             -> geofence_armed = true
圈外进入圈内     -> 触发提醒，并将 geofence_armed 置回 false
圈内继续停留     -> 不重复提醒
```

这意味着创建日程时设备已经在围栏内，不会被当作一次新的进入。必须先产生有效的圈外状态，再产生进入事件。

当前代码已经移除了“应用启动时首次读到圈内就立即提醒”的临时测试策略。应用启动或重建时主动读取当前位置只用于初始化状态，不应直接产生提醒。

## 5. 日志如何判断来源

### 时间提醒

```text
AlarmReceiver: onReceive action=com.timeflow.FIRE_ALARM
AlarmSoundService: onStartCommand alarmId=<uuid> scheduleId=<id>
```

这是时间闹钟。

### 地点提醒

```text
TimeflowAlarm: presentNow requested alarmId=geofence-<scheduleId>-<timestamp>
AlarmSoundService: onStartCommand alarmId=geofence-...
AlarmSoundService: showAlarmOverlay addView succeeded
```

这证明地点提醒请求已经到达原生服务，并且全局页面的 View 添加成功；它本身不能单独证明 Android 刚刚发送了 `enter` 回调。

### 不能作为围栏回调证据的日志

```text
ReactNativeJS: Running "main"
```

这只表示 React Native JS runtime 启动或重载。它可能由打开应用、刷新 bundle、后台任务恢复或开发环境重启引起。

```text
ReactNativeJS: URL: localhost:8081
ReactNativeJS: Cannot connect to Expo CLI.
```

这表示当前安装的是依赖 Metro 的开发包。用于后台测试时应安装 release APK，使 JS bundle 内嵌在包内。

## 6. 调试面板的事件含义

开发构建中的地理围栏调试面板保存最近事件时间线：

- `系统围栏已注册`：`startGeofencingAsync()` 成功返回，只能证明注册请求成功。
- `应用首次读取位置`：监听建立时应用主动调用 `getCurrentPositionAsync()`。
- `手动读取位置`：点击刷新按钮后应用主动获取位置。
- `系统回调已收到 · enter/exit`：Expo TaskManager 的真实地理围栏任务已收到系统事件，这是验证系统围栏回调的关键证据。
- `业务处理完成`：JS listener 已处理该回调。
- `已请求原生提醒`：JS 已调用 `nativePresentNow`。
- `已安排系统通知`：没有原生全局页面时，回退安排了系统通知。
- `等待会话恢复`：headless 期间无法完成投递，事件进入待处理队列。

“刷新定位状态”会主动请求一次 GPS。它不能伪造系统围栏回调，也不能证明系统内部何时完成计算。打开 Google 地图后提醒，可能是 Google Play Services 因新的定位更新重新评估了围栏，但应用无法从普通日志知道 Google 地图是否直接促成了这次更新。必须看时间线中是否出现真实的 `系统回调已收到`。

## 7. 真实测试流程

### 实体设备

1. 安装不依赖 Metro 的 release APK。
2. 授予前台定位和后台定位权限。
3. 确认系统围栏显示为“已注册”。
4. 清空调试事件。
5. 让设备先处于目标围栏外。
6. 创建或重建地点日程。
7. 按 Home 或锁屏，不要使用 `adb shell am force-stop`。
8. 真实移动进入围栏。
9. 回到应用查看事件时间线，确认出现 `系统回调已收到 · enter`。
10. 同时检查原生日志中的 `showAlarmOverlay addView succeeded`。

如果只出现 `应用首次读取位置` 或 `手动读取位置`，不能算系统围栏测试成功。

### Android Emulator

模拟器可以使用：

```bash
adb devices
adb -s <serial> emu geo fix <longitude> <latitude>
```

顺序必须是先圈外、后圈内。例如目标点是纬度 `31.2304`、经度 `121.4737`：

```bash
# 圈外
adb -s <serial> emu geo fix 121.4737 31.2404

# 等待系统处理后进入圈内
adb -s <serial> emu geo fix 121.4737 31.2304
```

`geo fix` 的参数顺序是经度在前、纬度在后。实体手机不能仅靠普通 adb 注入 fake location，需要 Mock Location 应用并在开发者选项中选择它。

## 8. 权限、系统和厂商限制

地理围栏不是高频连续定位保证。Android 会根据电量、定位开关、网络、设备运动状态和系统策略决定何时获取位置、何时评估围栏。因此回调可能有延迟，不能把围栏半径当成米级实时定位。

实体设备还可能受到以下因素影响：

- 后台定位权限没有设置为“始终允许”。
- 应用被 MIUI/其他厂商的省电策略冻结。
- 自启动权限关闭。
- 系统定位或 Google Location Accuracy 关闭。
- 用户执行了强制停止。
- 系统围栏数量达到平台限制。
- 设备处于室内、信号弱或长期静止，系统降低定位频率。

打开 Google 地图后才触发，通常说明设备此时获得了新的定位更新；这不是应用能够控制或准确观测的系统内部细节。测试时应把它作为设备定位更新行为记录，而不是把地图调用当作围栏 API 的一部分。

## 9. 当前结论和后续方案

当前实现已经能够验证并使用：

- 系统围栏注册。
- 系统 `enter/exit` 回调到 Expo TaskManager。
- App 在后台或 headless 场景下的回调处理尝试。
- Android 原生全局提醒页面。
- 事件诊断和待处理事件队列。

当前不能保证：

- 系统一定在某个固定时间内产生回调。
- 所有厂商 ROM 在应用进程被杀后都启动 headless JS。
- 地点提醒像 AlarmManager 一样完全脱离 JS 工作。

如果要达到时间提醒的可靠性，下一步应把 Android 地理围栏接收端下沉到原生：

```text
GeofencingClient
    -> 原生 BroadcastReceiver
    -> SQLite 原生状态去重
    -> AlarmSoundService
```

JS 可以继续用于创建、编辑和查看日程，但不应成为后台地点提醒投递的必经路径。

