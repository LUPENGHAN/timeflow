import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  nativeCheckTtsNow,
  nativeGetTtsDiagnostics,
  type NativeTtsDiagnostics,
} from '../../../infrastructure/notifications/native/TimeflowAlarmBridge';
import { colors, spacing } from '../../../shared/ui/theme';

type PanelState = {
  diagnostics: NativeTtsDiagnostics | null;
  loaded: boolean;
};

const INITIAL_STATE: PanelState = { diagnostics: null, loaded: false };

/**
 * 仅在开发构建挂载。设备本地 TTS 是不是真的能用，之前只能靠 adb logcat 才看得到——
 * 高强度提醒"没念语音、退回打包铃"这类问题，用户自己在设置里翻 TTS 引擎之前，
 * 至少先在这张卡片上看到一个明确的"不可用"，而不是猜。
 */
export function TtsDiagnosticsPanel() {
  const [state, setState] = useState(INITIAL_STATE);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const diagnostics = await nativeGetTtsDiagnostics();
      setState({ diagnostics, loaded: true });
      setMessage(diagnostics == null ? '还没有任何记录' : '已读取最近一次记录');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '读取 TTS 状态失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const checkNow = useCallback(async () => {
    setBusy(true);
    try {
      const diagnostics = await nativeCheckTtsNow();
      setState({ diagnostics, loaded: true });
      setMessage(
        diagnostics.ready
          ? '前台探测：TTS 引擎可用'
          : '前台探测：TTS 引擎不可用，见下方 detail',
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '探测 TTS 状态失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const { diagnostics, loaded } = state;

  return (
    <View style={styles.panel} testID="tts-diagnostics-panel">
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>本地 TTS 调试</Text>
          <Text style={styles.subtitle}>开发构建可见</Text>
        </View>
        {busy ? <ActivityIndicator color={colors.focus} /> : null}
      </View>

      <View style={styles.statusGrid}>
        <Status
          label="就绪状态"
          value={!loaded ? '未读取' : diagnostics == null ? '从未记录' : diagnostics.ready ? '可用' : '不可用'}
          warn={loaded && diagnostics != null && !diagnostics.ready}
        />
        <Status
          label="来源"
          value={
            diagnostics == null
              ? '—'
              : diagnostics.source === 'alarm'
                ? '真实闹钟触发'
                : diagnostics.source === 'manual'
                  ? '前台手动探测'
                  : diagnostics.source
          }
        />
        <Status
          label="statusCode"
          value={diagnostics == null ? '—' : String(diagnostics.statusCode)}
        />
        <Status label="detail" value={diagnostics == null ? '—' : diagnostics.detail} />
        <Status
          label="记录时间"
          value={diagnostics == null ? '—' : new Date(diagnostics.checkedAtMillis).toLocaleString()}
        />
      </View>

      {loaded && diagnostics != null && !diagnostics.ready ? (
        <Text style={styles.warning}>
          高强度提醒念不出语音，大概率就是这个——去系统设置里的「文字转语音输出」确认默认引擎有没有装好、能不能正常试听，弄好后点「立即探测」复查。
        </Text>
      ) : null}

      <View style={styles.actions}>
        <ActionButton label="读取最近记录" onPress={() => void load()} disabled={busy} />
        <ActionButton
          label="立即探测（前台）"
          onPress={() => void checkNow()}
          disabled={busy}
          secondary
        />
      </View>

      <Text style={styles.hint}>
        「读取最近记录」看的是真实闹钟上一次触发时原生自己记下的结果，最贴近实际故障场景；「立即探测」跑在当前前台
        App 进程里，方便的地方是不用等下一次提醒，但进程状态跟后台触发时不完全一样，仅供参考。
      </Text>

      {message ? <Text style={styles.message}>{message}</Text> : null}
    </View>
  );
}

function Status({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <View style={styles.status}>
      <Text style={styles.statusLabel}>{label}</Text>
      <Text numberOfLines={3} style={[styles.statusValue, warn && styles.statusValueWarn]}>
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
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  hint: { color: '#BFD1C8', fontSize: 11, lineHeight: 16, marginTop: spacing.md },
  message: { color: colors.focus, fontSize: 13, marginTop: spacing.md },
  panel: {
    backgroundColor: colors.text,
    borderRadius: 12,
    marginHorizontal: spacing.md,
    marginTop: spacing.lg,
    padding: spacing.md,
  },
  secondaryButton: { backgroundColor: '#2B4A40', borderColor: '#567267', borderWidth: 1 },
  secondaryButtonText: { color: colors.onPrimary },
  status: { minWidth: '48%', paddingVertical: spacing.xs },
  statusGrid: { flexDirection: 'row', flexWrap: 'wrap', marginVertical: spacing.md },
  statusLabel: { color: '#BFD1C8', fontSize: 11 },
  statusValue: { color: colors.onPrimary, fontSize: 13, fontWeight: '700', marginTop: 2 },
  statusValueWarn: { color: '#FF9D7A' },
  subtitle: { color: '#BFD1C8', fontSize: 11, marginTop: 2 },
  title: { color: colors.onPrimary, fontSize: 17, fontWeight: '800' },
  warning: {
    color: '#FF9D7A',
    fontSize: 12,
    lineHeight: 17,
    marginBottom: spacing.md,
  },
});
