package com.timeflow.alarm;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * 持久化原生 fire/dismiss，供 JS 在进程死后补水 disposition；
 * 并在 React 上下文存活时向 AlarmModule 转发事件。
 *
 * peekDispositions()/ackDispositions() 是两阶段读取：peek 只读不删，JS 把结果
 * 写进自己的持久化存储（SQLite）之后再显式 ack 传回处理成功的 schedule_id，
 * ackDispositions() 才真正从这里的缓冲区删除。原来的单次 consume（读完立刻清空）
 * 在 JS 侧还没落盘完就进程被杀、Promise 回调失败、或桥接重载的窗口里会把这批
 * fired/dismissed/snoozed 状态永久丢掉——这正是这层持久化机制本该防住的情况
 * （Issue #263：App 被杀死后事件不丢失），不能只留一个已知会丢数据的消费接口。
 */
public final class AlarmNativeBridge {
    private AlarmNativeBridge() {
    }

    public static final class DispositionRecord {
        public final String scheduleId;
        public final String alarmId;
        public final String state;
        public final long updatedAtMillis;

        DispositionRecord(String scheduleId, String alarmId, String state, long updatedAtMillis) {
            this.scheduleId = scheduleId;
            this.alarmId = alarmId;
            this.state = state;
            this.updatedAtMillis = updatedAtMillis;
        }
    }

    public static void notifyFired(
            Context context,
            String scheduleId,
            String alarmId,
            String title
    ) {
        upsertDisposition(context, scheduleId, alarmId, "pending");
        sendLocalEvent(context, AlarmContract.EVENT_FIRED, scheduleId, alarmId, title);
        AlarmModule.emitAlarmEvent(AlarmContract.EVENT_FIRED, scheduleId, alarmId, title);
    }

    public static void notifyDismissed(
            Context context,
            String scheduleId,
            String alarmId,
            String title
    ) {
        upsertDisposition(context, scheduleId, alarmId, "confirmed");
        sendLocalEvent(context, AlarmContract.EVENT_DISMISSED, scheduleId, alarmId, title);
        AlarmModule.emitAlarmEvent(AlarmContract.EVENT_DISMISSED, scheduleId, alarmId, title);
    }

    /** 延后：落 snoozed disposition，并由调用方负责重新 schedule。 */
    public static void notifySnoozed(
            Context context,
            String scheduleId,
            String alarmId,
            String title
    ) {
        upsertDisposition(context, scheduleId, alarmId, "snoozed");
        sendLocalEvent(context, AlarmContract.EVENT_SNOOZED, scheduleId, alarmId, title);
        AlarmModule.emitAlarmEvent(AlarmContract.EVENT_SNOOZED, scheduleId, alarmId, title);
    }

    /** 只读：不清空缓冲区，JS 落盘成功后必须调用 ackDispositions() 才会真正删除。 */
    public static List<DispositionRecord> peekDispositions(Context context) {
        List<DispositionRecord> records = new ArrayList<>();
        for (JSONObject object : loadDispositionObjects(context)) {
            String scheduleId = object.optString("schedule_id", "");
            String state = object.optString("state", "");
            if (scheduleId.isEmpty() || state.isEmpty()) {
                continue;
            }
            records.add(new DispositionRecord(
                    scheduleId,
                    object.optString("alarm_id", ""),
                    state,
                    object.optLong("updated_at", System.currentTimeMillis())
            ));
        }
        return records;
    }

    /**
     * 只删除 scheduleIds 里点名的记录；调用方（JS）确认这些已经durably处理完才应该
     * 调这个。期间新落的记录（比如 ack 还没返回时又响了一次）不受影响，留给下次
     * peek。
     */
    public static void ackDispositions(Context context, Set<String> scheduleIds) {
        if (scheduleIds == null || scheduleIds.isEmpty()) {
            return;
        }
        JSONArray remaining = new JSONArray();
        for (JSONObject object : loadDispositionObjects(context)) {
            String scheduleId = object.optString("schedule_id", "");
            if (scheduleId.isEmpty() || scheduleIds.contains(scheduleId)) {
                continue;
            }
            remaining.put(object);
        }
        context.getSharedPreferences(AlarmContract.PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(AlarmContract.DISPOSITIONS_KEY, remaining.toString())
                .apply();
    }

    private static List<JSONObject> loadDispositionObjects(Context context) {
        SharedPreferences preferences =
                context.getSharedPreferences(AlarmContract.PREFS_NAME, Context.MODE_PRIVATE);
        String serialized = preferences.getString(AlarmContract.DISPOSITIONS_KEY, "[]");
        List<JSONObject> objects = new ArrayList<>();
        try {
            JSONArray array = new JSONArray(serialized);
            for (int index = 0; index < array.length(); index++) {
                Object value = array.get(index);
                if (value instanceof JSONObject) {
                    objects.add((JSONObject) value);
                }
            }
        } catch (JSONException ignored) {
            return new ArrayList<>();
        }
        return objects;
    }

    public static final class TtsDiagnostics {
        public final boolean ready;
        public final int statusCode;
        public final String detail;
        public final String source;
        public final long checkedAtMillis;

        TtsDiagnostics(
                boolean ready, int statusCode, String detail, String source, long checkedAtMillis
        ) {
            this.ready = ready;
            this.statusCode = statusCode;
            this.detail = detail;
            this.source = source;
            this.checkedAtMillis = checkedAtMillis;
        }
    }

    /**
     * 每次设备 TTS 引擎初始化/探测出结果（不管成不成功）都落一次盘，覆盖上一条——
     * 只关心"最近一次"，不像 dispositions 那样需要保留多条历史。source 区分是真的
     * 闹钟触发时记的（"alarm"，最贴近真实故障场景），还是调试面板手动探测的
     * （"manual"，跑在前台 App 进程里，跟后台闹钟触发时的进程状态可能不一样，
     * 仅供参考）。
     */
    public static void recordTtsDiagnostics(
            Context context, boolean ready, int statusCode, String detail, String source
    ) {
        try {
            JSONObject object = new JSONObject();
            object.put("ready", ready);
            object.put("status_code", statusCode);
            object.put("detail", detail == null ? "" : detail);
            object.put("source", source == null ? "" : source);
            object.put("checked_at", System.currentTimeMillis());
            context.getSharedPreferences(AlarmContract.PREFS_NAME, Context.MODE_PRIVATE)
                    .edit()
                    .putString(AlarmContract.TTS_DIAGNOSTICS_KEY, object.toString())
                    .apply();
        } catch (JSONException ignored) {
            // 记录失败不影响响铃本身，纯诊断信息尽力而为。
        }
    }

    /** 还没记录过任何结果时返回 null（比如 App 装好之后从没真的响过一次闹钟）。 */
    public static TtsDiagnostics getTtsDiagnostics(Context context) {
        SharedPreferences preferences =
                context.getSharedPreferences(AlarmContract.PREFS_NAME, Context.MODE_PRIVATE);
        String serialized = preferences.getString(AlarmContract.TTS_DIAGNOSTICS_KEY, null);
        if (serialized == null) {
            return null;
        }
        try {
            JSONObject object = new JSONObject(serialized);
            return new TtsDiagnostics(
                    object.optBoolean("ready", false),
                    object.optInt("status_code", 0),
                    object.optString("detail", ""),
                    object.optString("source", ""),
                    object.optLong("checked_at", 0L)
            );
        } catch (JSONException ignored) {
            return null;
        }
    }

    public static void stopRinging(Context context) {
        AlarmSoundService.stop(context);
        RingActivity.finishIfOpen();
    }

    private static void sendLocalEvent(
            Context context,
            String type,
            String scheduleId,
            String alarmId,
            String title
    ) {
        Intent intent = new Intent(AlarmContract.ACTION_ALARM_EVENT)
                .setPackage(context.getPackageName())
                .putExtra(AlarmContract.EXTRA_EVENT_TYPE, type)
                .putExtra(AlarmContract.EXTRA_SCHEDULE_ID, scheduleId)
                .putExtra(AlarmContract.EXTRA_ALARM_ID, alarmId)
                .putExtra(AlarmContract.EXTRA_TITLE, title);
        context.sendBroadcast(intent);
    }

    private static void upsertDisposition(
            Context context,
            String scheduleId,
            String alarmId,
            String state
    ) {
        if (scheduleId == null || scheduleId.isEmpty()) {
            return;
        }
        JSONArray remaining = new JSONArray();
        for (JSONObject object : loadDispositionObjects(context)) {
            if (scheduleId.equals(object.optString("schedule_id", ""))) {
                continue;
            }
            remaining.put(object);
        }
        try {
            JSONObject next = new JSONObject();
            next.put("schedule_id", scheduleId);
            next.put("alarm_id", alarmId == null ? "" : alarmId);
            next.put("state", state);
            next.put("updated_at", System.currentTimeMillis());
            remaining.put(next);
        } catch (JSONException ignored) {
            return;
        }
        context.getSharedPreferences(AlarmContract.PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(AlarmContract.DISPOSITIONS_KEY, remaining.toString())
                .apply();
    }
}
