import { useEffect, useState } from 'react';
import { Animated, Easing, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../../../shared/ui/theme';

import { TempoAssistantIcon } from './TempoAssistantIcon';

const WAVE_BAR_HEIGHTS = [11, 18, 24, 16, 12] as const;
const MIN_BAR_SCALE = 0.4;
const LEVEL_ANIMATION_MS = 120;

export type VoiceListenStatus = 'off' | 'listening' | 'speaking' | 'interrupted' | 'busy';

interface VoiceListenToggleProps {
  status: VoiceListenStatus;
  /** 麦克风音量，dBFS（-160~0）；只在 status === 'listening' 时有意义。 */
  soundLevel: number | null;
  onToggle: () => void;
}

const HINTS: Record<VoiceListenStatus, string | null> = {
  busy: '连接中…',
  interrupted: '已打断',
  listening: '免提聆听中…',
  off: null,
  speaking: '正在回复…',
};

/**
 * 免提连续对话入口：单击开/关，不是按住说话。视觉上仿 VoiceTalkButton 的波形
 * 和配色，但换成 onToggle 而不是 onPressIn/onPressOut——两者状态机形状不同，
 * 故意不复用同一个组件，避免为了共享视觉细节而搅动已经在用的按住说话路径。
 */
export function VoiceListenToggle({ status, soundLevel, onToggle }: VoiceListenToggleProps) {
  const [waveValues] = useState(() =>
    WAVE_BAR_HEIGHTS.map(() => new Animated.Value(MIN_BAR_SCALE)),
  );
  const isOn = status !== 'off';

  useEffect(() => {
    if (status !== 'listening') {
      waveValues.forEach((value) => {
        value.stopAnimation();
        value.setValue(MIN_BAR_SCALE);
      });
      return;
    }
    const target = MIN_BAR_SCALE + (1 - MIN_BAR_SCALE) * normalizeLevel(soundLevel);
    Animated.parallel(
      waveValues.map((value) =>
        Animated.timing(value, {
          duration: LEVEL_ANIMATION_MS,
          easing: Easing.out(Easing.ease),
          toValue: target,
          useNativeDriver: Platform.OS !== 'web',
        }),
      ),
    ).start();
  }, [status, soundLevel, waveValues]);

  return (
    <View style={styles.wrap}>
      <View style={styles.hintSlot}>{HINTS[status] ? <Text style={styles.hint}>{HINTS[status]}</Text> : null}</View>
      <Pressable
        accessibilityLabel={isOn ? '关闭免提' : '开启免提'}
        accessibilityRole="button"
        onPress={onToggle}
        style={({ pressed }) => [
          styles.button,
          status === 'interrupted' && styles.buttonInterrupted,
          pressed && styles.buttonPressed,
        ]}
      >
        {status === 'listening' ? (
          <View style={styles.wave}>
            {waveValues.map((value, index) => (
              <Animated.View
                key={`wave-${WAVE_BAR_HEIGHTS[index]}-${index}`}
                style={[
                  styles.waveBar,
                  {
                    height: WAVE_BAR_HEIGHTS[index],
                    opacity: value,
                    transform: [{ scaleY: value }],
                  },
                ]}
              />
            ))}
          </View>
        ) : (
          <TempoAssistantIcon color={colors.onPrimary} size={24} />
        )}
      </Pressable>
    </View>
  );
}

function normalizeLevel(dbfs: number | null): number {
  if (dbfs === null) {
    return 0;
  }
  const clamped = Math.max(-50, Math.min(0, dbfs));
  return (clamped + 50) / 50;
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    backgroundColor: colors.text,
    borderRadius: 999,
    height: 64,
    justifyContent: 'center',
    width: 64,
  },
  buttonInterrupted: {
    backgroundColor: colors.error,
  },
  buttonPressed: {
    opacity: 0.86,
  },
  hint: {
    color: colors.mutedText,
    fontSize: 12,
    fontWeight: '600',
  },
  hintSlot: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 18,
  },
  wave: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
    height: 24,
  },
  waveBar: {
    backgroundColor: colors.onPrimary,
    borderRadius: 999,
    width: 3.5,
  },
  wrap: {
    alignItems: 'center',
    gap: spacing.xs,
  },
});
