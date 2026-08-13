import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../../../shared/ui/theme';
import type { AssistantApplicationPort } from '../application/AssistantApplication';
import type { ConversationTurnState } from '../domain/ConversationTurn';

import { useAssistantConversation } from './useAssistantConversation';
import { VoiceListenToggle, type VoiceListenStatus } from './VoiceListenToggle';
import { VoiceTalkButton } from './VoiceTalkButton';

export type VoiceMode = 'push_to_talk' | 'continuous';

interface AssistantVoiceOverlayProps {
  application: AssistantApplicationPort;
  voiceMode: VoiceMode;
  onToggleVoiceMode: () => void;
}

function listenStatusFor(phase: ConversationTurnState['phase']): VoiceListenStatus {
  switch (phase) {
    case 'connecting':
      return 'busy';
    case 'listening':
      return 'listening';
    case 'speaking':
    case 'asking':
      return 'speaking';
    case 'interrupted':
      return 'interrupted';
    default:
      return 'off';
  }
}

const CONTINUOUS_OPEN_PHASES: ReadonlySet<ConversationTurnState['phase']> = new Set([
  'listening',
  'speaking',
  'asking',
  'interrupted',
]);

/**
 * 叠在日历屏上的语音入口：底部居中按住说话按钮，说完话上方冒出流式文字气泡
 * （voice.dialogue.reply）。外层 pointerEvents="box-none" 让按钮和气泡之外的
 * 区域穿透给下面的日历，不挡滚动和点日期。
 *
 * 气泡出现时会多铺一层全屏蒙层（"box-none" 让位给它），点气泡本身不关闭
 * （包了一层自己的 Pressable 吃掉点击），点气泡以外的任何地方——包括蒙层本身
 * 覆盖的日历区域——都会关掉气泡并打断正在播放的 TTS。按钮渲染在蒙层之后，
 * 层级更高，蒙层出现时按钮仍能正常按。
 *
 * 免提模式下气泡是"常驻"的：只要连续会话开着（listening/speaking/asking/
 * interrupted），气泡就一直显示——没有回复前占位显示"聆听中…"，有回复后显示
 * 上一句，直到下一句覆盖。点气泡外仍会 dismissReply()，但那只是清空当前这句
 * 回复、打断 TTS，气泡本身因为会话还开着会立刻回落成"聆听中…"占位，不会消失；
 * 真正让气泡整体消失的是关掉免提（回到 idle）。按住说话模式行为不变。
 */
export function AssistantVoiceOverlay({
  application,
  voiceMode,
  onToggleVoiceMode,
}: AssistantVoiceOverlayProps) {
  const { dismissReply, endTurn, replyText, soundLevel, startTurn, state } =
    useAssistantConversation(application);
  const isRecording = state.phase === 'recording';
  const isContinuousSessionOpen =
    voiceMode === 'continuous' && CONTINUOUS_OPEN_PHASES.has(state.phase);
  const showBubble = replyText !== null || isContinuousSessionOpen;
  const bubbleText = replyText ?? (isContinuousSessionOpen ? '聆听中…' : '');

  return (
    <View pointerEvents="box-none" style={StyleSheet.absoluteFill}>
      {/* 铺满全屏的蒙层：点气泡和按钮以外的任何地方（包括上面的日历区域）都会
          命中这层，因为它渲染在 overlay 内容之前、又是 box-none 容器唯一会
          拦截"空白处"点击的兜底。 */}
      {showBubble ? (
        <Pressable
          accessibilityLabel="关闭回复"
          onPress={dismissReply}
          style={StyleSheet.absoluteFill}
        />
      ) : null}
      <View pointerEvents="box-none" style={styles.overlay}>
        {showBubble ? (
          <Pressable onPress={() => {}} style={styles.bubble}>
            <Text style={styles.bubbleText}>{bubbleText}</Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityLabel={voiceMode === 'push_to_talk' ? '切换到免提' : '切换到按住说话'}
          accessibilityRole="button"
          onPress={onToggleVoiceMode}
          style={styles.modePill}
        >
          <Text style={styles.modePillText}>
            {voiceMode === 'push_to_talk' ? '按住说话' : '免提'}
          </Text>
        </Pressable>
        {voiceMode === 'push_to_talk' ? (
          <VoiceTalkButton
            isRecording={isRecording}
            onPressIn={startTurn}
            onPressOut={endTurn}
            soundLevel={soundLevel}
          />
        ) : (
          <VoiceListenToggle
            onToggle={() => {
              void (state.phase === 'idle' ? startTurn() : endTurn());
            }}
            soundLevel={soundLevel}
            status={listenStatusFor(state.phase)}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: spacing.md,
    maxWidth: 280,
    padding: spacing.md,
  },
  bubbleText: {
    color: colors.text,
    fontSize: 15,
  },
  modePill: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  modePillText: {
    color: colors.mutedText,
    fontSize: 12,
    fontWeight: '600',
  },
  overlay: {
    alignItems: 'center',
    bottom: spacing.xl,
    left: 0,
    position: 'absolute',
    right: 0,
  },
});
