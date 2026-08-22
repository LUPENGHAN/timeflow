import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import * as Location from 'expo-location';

import { ExpoSystemNotification } from '../../../infrastructure/notifications';
import {
  GEOFENCE_TASK_NAME,
  clearGeofenceDiagnostics,
  getGeofenceDiagnostics,
  recordGeofenceDiagnostic,
  simulateGeofenceEventForTesting,
  type GeofenceDiagnostic,
} from '../../../infrastructure/location/geofenceTask';
import type { LocationScheduleView } from '../application';
import { colors, spacing } from '../../../shared/ui/theme';

type DiagnosticState = {
  foreground: string;
  background: string;
  geofence: string;
  position: string;
  systemCallback: string;
  events: readonly GeofenceDiagnostic[];
};

const INITIAL_STATE: DiagnosticState = {
  foreground: '未读取',
  background: '未读取',
  geofence: '未读取',
  position: '未读取',
  systemCallback: '本次未收到系统回调',
  events: [],
};

/** 仅在开发构建挂载，用来验证权限、围栏注册和提醒投递。 */
export function GeofenceDiagnosticsPanel({
  schedules,
}: {
  schedules: readonly LocationScheduleView[];
}) {
  const [state, setState] = useState(INITIAL_STATE);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const [foreground, background, geofence, position] = await Promise.all([
        Location.getForegroundPermissionsAsync(),
        Location.getBackgroundPermissionsAsync(),
        Location.hasStartedGeofencingAsync(GEOFENCE_TASK_NAME),
        Location.getCurrentPositionAsync({}),
      ]);
      await recordGeofenceDiagnostic({
        phase: 'manual_location_read',
        schedule_id: 'diagnostics',
        event: 'manual_read',
        observed_at: new Date(position.timestamp).toISOString(),
        detail: '点击刷新定位状态后由应用主动读取，不是系统围栏回调',
      });
      const diagnostics = await getGeofenceDiagnostics();
      const systemCallback = [...diagnostics]
        .reverse()
        .find((diagnostic) => diagnostic.phase === 'callback_received');
      setState({
        foreground: foreground.status,
        background: background.status,
        geofence: geofence ? '已注册' : '未注册',
        position: `${position.coords.latitude.toFixed(6)}, ${position.coords.longitude.toFixed(6)}`,
        systemCallback: systemCallback ? describeDiagnostic(systemCallback) : '本次未收到系统回调',
        events: diagnostics.slice(-8).reverse(),
      });
      setMessage('状态已刷新');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '读取定位状态失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const clearEvents = useCallback(async () => {
    setBusy(true);
    try {
      await clearGeofenceDiagnostics();
      setState((current) => ({
        ...current,
        systemCallback: '本次未收到系统回调',
        events: [],
      }));
      setMessage('已清空事件记录');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '清空事件记录失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const sendNotification = useCallback(async () => {
    setBusy(true);
    try {
      const receipt = await new ExpoSystemNotification().show({
        notification_id: 'timeflow-geofence-test',
        title: 'Timeflow 测试通知',
        body: '通知权限和系统通知通道正常。',
      });
      setMessage(receipt.shown ? '测试通知已发送' : '通知模块不可用');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '发送测试通知失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const simulate = useCallback(async (schedule: LocationScheduleView, event: 'enter' | 'exit') => {
    setBusy(true);
    try {
      await simulateGeofenceEventForTesting(schedule.scheduleId, event);
      setMessage(`${schedule.title}：已模拟${event === 'exit' ? '离开' : '进入'}，请观察提醒`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '模拟围栏事件失败');
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <View style={styles.panel} testID="geofence-diagnostics-panel">
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>地理围栏调试</Text>
          <Text style={styles.subtitle}>开发构建可见</Text>
        </View>
        {busy ? <ActivityIndicator color={colors.focus} /> : null}
      </View>

      <View style={styles.statusGrid}>
        <Status label="前台定位" value={state.foreground} />
        <Status label="后台定位" value={state.background} />
        <Status label="系统围栏" value={state.geofence} />
        <Status label="当前位置" value={state.position} />
        <Status label="最近系统回调" value={state.systemCallback} />
      </View>

      <View style={styles.actions}>
        <ActionButton label="刷新定位状态" onPress={() => void refresh()} disabled={busy} />
        <ActionButton
          label="清空事件"
          onPress={() => void clearEvents()}
          disabled={busy}
          secondary
        />
        <ActionButton
          label="发送测试通知"
          onPress={() => void sendNotification()}
          disabled={busy}
        />
      </View>

      <View style={styles.eventHistory}>
        <Text style={styles.eventHistoryTitle}>事件记录</Text>
        {state.events.map((event, index) => (
          <Text
            key={`${event.recorded_at}-${event.phase}-${event.schedule_id}-${index}`}
            numberOfLines={2}
            style={styles.eventRow}
          >
            {describeDiagnostic(event)}
          </Text>
        ))}
        {state.events.length === 0 ? <Text style={styles.eventRow}>暂无事件</Text> : null}
      </View>

      {schedules.map((schedule) => (
        <View key={schedule.scheduleId} style={styles.schedule}>
          <Text numberOfLines={1} style={styles.scheduleTitle}>
            {schedule.title}
          </Text>
          <View style={styles.actions}>
            <ActionButton
              label="模拟离开"
              onPress={() => void simulate(schedule, 'exit')}
              disabled={busy}
              secondary
            />
            <ActionButton
              label="模拟进入"
              onPress={() => void simulate(schedule, 'enter')}
              disabled={busy}
              secondary
            />
          </View>
        </View>
      ))}

      {schedules.length === 0 ? <Text style={styles.empty}>暂无可测试的地点提醒</Text> : null}
      {message ? <Text style={styles.message}>{message}</Text> : null}
    </View>
  );
}

function formatDiagnosticTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString();
}

function describeDiagnostic(diagnostic: GeofenceDiagnostic): string {
  const time = formatDiagnosticTime(diagnostic.recorded_at || diagnostic.observed_at);
  const phase = DIAGNOSTIC_LABELS[diagnostic.phase];
  return `${time} · ${phase} · ${diagnostic.event} · ${diagnostic.schedule_id.slice(0, 8)}`;
}

const DIAGNOSTIC_LABELS: Record<GeofenceDiagnostic['phase'], string> = {
  callback_received: '系统回调已收到',
  listener_completed: '业务处理完成',
  native_requested: '已请求原生提醒',
  notification_scheduled: '已安排系统通知',
  state_updated: '围栏状态已更新',
  queued: '等待会话恢复',
  delivery_failed: '提醒投递失败',
  registration_succeeded: '系统围栏已注册',
  initial_location_sample: '应用首次读取位置',
  manual_location_read: '手动读取位置',
};

function Status({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.status}>
      <Text style={styles.statusLabel}>{label}</Text>
      <Text numberOfLines={2} style={styles.statusValue}>
        {value}
      </Text>
    </View>
  );
}

function ActionButton({
  label,
  onPress,
  disabled,
  secondary = false,
}: {
  label: string;
  onPress: () => void;
  disabled: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondaryButton,
        pressed && styles.buttonPressed,
        disabled && styles.buttonDisabled,
      ]}
    >
      <Text style={[styles.buttonText, secondary && styles.secondaryButtonText]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  button: {
    alignItems: 'center',
    backgroundColor: colors.text,
    borderRadius: 8,
    justifyContent: 'center',
    minHeight: 38,
    paddingHorizontal: spacing.md,
  },
  buttonDisabled: { opacity: 0.45 },
  buttonPressed: { opacity: 0.7 },
  buttonText: { color: colors.onPrimary, fontSize: 13, fontWeight: '700' },
  empty: { color: colors.mutedText, fontSize: 13, marginTop: spacing.md },
  eventHistory: {
    borderTopColor: '#3B5A50',
    borderTopWidth: StyleSheet.hairlineWidth,
    marginTop: spacing.md,
    paddingTop: spacing.md,
  },
  eventHistoryTitle: { color: '#BFD1C8', fontSize: 11, marginBottom: spacing.xs },
  eventRow: { color: colors.onPrimary, fontSize: 12, lineHeight: 18, marginTop: 2 },
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  message: { color: colors.focus, fontSize: 13, marginTop: spacing.md },
  panel: {
    backgroundColor: colors.text,
    borderRadius: 12,
    marginHorizontal: spacing.md,
    marginTop: spacing.lg,
    padding: spacing.md,
  },
  schedule: {
    borderTopColor: '#3B5A50',
    borderTopWidth: StyleSheet.hairlineWidth,
    marginTop: spacing.md,
    paddingTop: spacing.md,
  },
  scheduleTitle: {
    color: colors.onPrimary,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: spacing.sm,
  },
  secondaryButton: { backgroundColor: '#2B4A40', borderColor: '#567267', borderWidth: 1 },
  secondaryButtonText: { color: colors.onPrimary },
  status: { minWidth: '48%', paddingVertical: spacing.xs },
  statusGrid: { flexDirection: 'row', flexWrap: 'wrap', marginVertical: spacing.md },
  statusLabel: { color: '#BFD1C8', fontSize: 11 },
  statusValue: { color: colors.onPrimary, fontSize: 13, fontWeight: '700', marginTop: 2 },
  subtitle: { color: '#BFD1C8', fontSize: 11, marginTop: 2 },
  title: { color: colors.onPrimary, fontSize: 17, fontWeight: '800' },
});
