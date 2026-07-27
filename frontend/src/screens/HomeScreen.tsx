import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  confirmWriteRequest,
  createWriteRequest,
  createVoiceCommand,
  getHealth,
  getRealtimeUrl,
  listItems,
  listPendingWriteRequests,
  rejectWriteRequest,
  type Item,
  type Reminder,
  type VoiceCommandResult,
  type WriteRequest,
} from '../api/client';
import { colors, spacing } from '../constants/theme';

type ViewMode = 'today' | 'week' | 'month';
type ItemType = 'todo' | 'calendar_event';
type ConnectionState = 'checking' | 'online' | 'offline';
type SocketState = 'connecting' | 'connected' | 'closed';
type ManualOperation =
  | 'create_todo'
  | 'create_calendar_event'
  | 'complete_item'
  | 'cancel_complete_item'
  | 'delete_item';

export function HomeScreen() {
  const [connection, setConnection] = useState<ConnectionState>('checking');
  const [socketState, setSocketState] = useState<SocketState>('connecting');
  const [viewMode, setViewMode] = useState<ViewMode>('today');
  const [items, setItems] = useState<Item[]>([]);
  const [pendingWrites, setPendingWrites] = useState<WriteRequest[]>([]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [itemType, setItemType] = useState<ItemType>('todo');
  const [banner, setBanner] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('到家后提醒我取快递');
  const [voiceResult, setVoiceResult] = useState<VoiceCommandResult | null>(null);
  const [voiceBusy, setVoiceBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [itemResponse, pendingResponse] = await Promise.all([
      listItems(),
      listPendingWriteRequests(),
    ]);
    setItems(itemResponse);
    setPendingWrites(pendingResponse);
  }, []);

  useEffect(() => {
    let active = true;

    getHealth()
      .then(() => {
        if (active) {
          setConnection('online');
        }
      })
      .catch(() => {
        if (active) {
          setConnection('offline');
        }
      });

    const initialLoadTimer = setTimeout(() => {
      refresh().catch(() => {
        if (active) {
          setBanner('加载事项失败');
        }
      });
    }, 0);

    const socket = new WebSocket(getRealtimeUrl());
    socket.onopen = () => {
      if (active) {
        setSocketState('connected');
      }
    };
    socket.onclose = () => {
      if (active) {
        setSocketState('closed');
      }
    };
    socket.onerror = () => {
      if (active) {
        setSocketState('closed');
      }
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(String(event.data)) as { event_type?: string };
      if (message.event_type === 'sync.response') {
        refresh().catch(() => setBanner('同步失败'));
        return;
      }
      if (
        message.event_type &&
        message.event_type !== 'connection.ready' &&
        message.event_type !== 'connection.heartbeat'
      ) {
        refresh().catch(() => setBanner('同步失败'));
      }
    };

    return () => {
      active = false;
      clearTimeout(initialLoadTimer);
      socket.close();
    };
  }, [refresh]);

  const calendarItems = useMemo(
    () => items.filter((item) => item.type === 'calendar_event'),
    [items],
  );
  const todoItems = useMemo(() => items.filter((item) => item.type === 'todo'), [items]);
  const visibleItems = viewMode === 'today' ? items : items;

  async function handlePrepareCreateItem() {
    if (!title.trim() || loading) {
      return;
    }

    setLoading(true);
    setBanner(null);
    try {
      await createWriteRequest({
        source_command_id: `manual-create-${Date.now()}`,
        candidate_payload: {
          item: {
            description: description.trim() || null,
            due_at: null,
            end_at: null,
            place_text: null,
            priority: 'normal',
            start_at: null,
            title: title.trim(),
            type: itemType,
          },
          operation: itemType === 'todo' ? 'create_todo' : 'create_calendar_event',
          source_text: 'manual quick add',
        },
      });
      setTitle('');
      setDescription('');
      await refresh();
      setBanner('已生成待确认写入');
    } catch {
      setBanner('创建确认请求失败');
    } finally {
      setLoading(false);
    }
  }

  async function handlePrepareItemOperation(item: Item, operation: ManualOperation) {
    setBanner(null);
    try {
      await createWriteRequest({
        source_command_id: `manual-${item.id}-${operation}-${Date.now()}`,
        candidate_payload: {
          item: {
            description: item.description,
            due_at: item.due_at,
            end_at: item.end_at,
            place_text: item.place_text,
            start_at: item.start_at,
            title: item.title,
            type: item.type,
          },
          operation,
          source_text: manualOperationLabel(operation),
          target_id: item.id,
        },
      });
      await refresh();
      setBanner('已生成待确认写入');
    } catch {
      setBanner('创建确认请求失败');
    }
  }

  async function handleConfirmPending(writeRequestId: string) {
    try {
      await confirmWriteRequest(writeRequestId);
      await refresh();
      setBanner('已确认写入');
    } catch {
      setBanner('确认失败');
    }
  }

  async function handleRejectPending(writeRequestId: string) {
    try {
      await rejectWriteRequest(writeRequestId);
      await refresh();
      setBanner('已取消写入');
    } catch {
      setBanner('取消失败');
    }
  }

  async function handleParseVoice() {
    if (!voiceTranscript.trim() || voiceBusy) {
      return;
    }

    setVoiceBusy(true);
    setVoiceResult(null);
    try {
      const result = await createVoiceCommand(voiceTranscript.trim());
      setVoiceResult(result);
      await refresh();
    } catch {
      setBanner('语音解析失败');
    } finally {
      setVoiceBusy(false);
    }
  }

  async function handleConfirmVoice() {
    const writeRequestId = voiceResult?.write_request?.id;
    if (!writeRequestId || voiceBusy) {
      return;
    }

    setVoiceBusy(true);
    try {
      await confirmWriteRequest(writeRequestId);
      await refresh();
      setVoiceOpen(false);
      setVoiceResult(null);
      setBanner('语音事项已确认写入');
    } catch {
      setBanner('确认失败');
    } finally {
      setVoiceBusy(false);
    }
  }

  async function handleRejectVoice() {
    const writeRequestId = voiceResult?.write_request?.id;
    if (!writeRequestId || voiceBusy) {
      return;
    }

    setVoiceBusy(true);
    try {
      await rejectWriteRequest(writeRequestId);
      await refresh();
      setVoiceResult(null);
      setBanner('已取消语音候选');
    } catch {
      setBanner('取消失败');
    } finally {
      setVoiceBusy(false);
    }
  }

  return (
    <View style={styles.root}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.topBar}>
          <View>
            <Text style={styles.kicker}>Timeflow</Text>
            <Text style={styles.title}>日程与待办</Text>
          </View>
          <StatusPill connection={connection} socketState={socketState} />
        </View>

        <View style={styles.metricsRow}>
          <Metric label="日历" value={calendarItems.length} />
          <Metric label="待办" value={todoItems.length} />
          <Metric label="待确认" value={pendingWrites.length} />
        </View>

        {banner ? <Text style={styles.banner}>{banner}</Text> : null}

        <View style={styles.toolbar}>
          {(['today', 'week', 'month'] as const).map((mode) => (
            <Pressable
              key={mode}
              onPress={() => setViewMode(mode)}
              style={[styles.segmentButton, viewMode === mode && styles.segmentButtonActive]}
            >
              <Text
                style={[
                  styles.segmentButtonText,
                  viewMode === mode && styles.segmentButtonTextActive,
                ]}
              >
                {modeLabel(mode)}
              </Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.quickAdd}>
          <View style={styles.quickAddHeader}>
            <Text style={styles.sectionTitle}>快速新增</Text>
            <View style={styles.typeToggle}>
              {(['todo', 'calendar_event'] as const).map((type) => (
                <Pressable
                  key={type}
                  onPress={() => setItemType(type)}
                  style={[styles.typeButton, itemType === type && styles.typeButtonActive]}
                >
                  <Text
                    style={[
                      styles.typeButtonText,
                      itemType === type && styles.typeButtonTextActive,
                    ]}
                  >
                    {type === 'todo' ? '待办' : '日历'}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
          <TextInput
            value={title}
            onChangeText={setTitle}
            placeholder="输入标题"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <TextInput
            value={description}
            onChangeText={setDescription}
            placeholder="备注，可选"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <Pressable
            onPress={handlePrepareCreateItem}
            style={[styles.primaryButton, loading && styles.disabledButton]}
          >
            <Text style={styles.primaryButtonText}>{loading ? '生成中' : '生成确认'}</Text>
          </Pressable>
        </View>

        {pendingWrites.length > 0 ? (
          <View style={styles.pendingSection}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>待确认</Text>
              <Text style={styles.subtle}>{pendingWrites.length} 项</Text>
            </View>
            {pendingWrites.map((writeRequest) => (
              <PendingWriteRow
                key={writeRequest.id}
                onConfirm={handleConfirmPending}
                onReject={handleRejectPending}
                writeRequest={writeRequest}
              />
            ))}
          </View>
        ) : null}

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>{modeLabel(viewMode)}事项</Text>
          <Text style={styles.subtle}>{visibleItems.length} 项</Text>
        </View>

        <View style={styles.list}>
          {visibleItems.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>暂无事项</Text>
              <Text style={styles.emptyText}>用快速新增或底部语音按钮创建第一条事项。</Text>
            </View>
          ) : (
            visibleItems.map((item) => (
              <ItemRow key={item.id} item={item} onPrepareOperation={handlePrepareItemOperation} />
            ))
          )}
        </View>
      </ScrollView>

      <Pressable onPress={() => setVoiceOpen(true)} style={styles.voiceDock}>
        <Text style={styles.voiceDockText}>语音</Text>
      </Pressable>

      <VoiceSheet
        busy={voiceBusy}
        onClose={() => setVoiceOpen(false)}
        onConfirm={handleConfirmVoice}
        onParse={handleParseVoice}
        onReject={handleRejectVoice}
        result={voiceResult}
        transcript={voiceTranscript}
        visible={voiceOpen}
        onTranscriptChange={setVoiceTranscript}
      />
    </View>
  );
}

function StatusPill({
  connection,
  socketState,
}: {
  connection: ConnectionState;
  socketState: SocketState;
}) {
  const online = connection === 'online' && socketState === 'connected';
  return (
    <View style={[styles.statusPill, online ? styles.statusPillOnline : styles.statusPillMuted]}>
      <Text style={[styles.statusText, online ? styles.statusTextOnline : styles.statusTextMuted]}>
        {online ? '已连接' : connection === 'checking' ? '检查中' : '离线'}
      </Text>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

function ItemRow({
  item,
  onPrepareOperation,
}: {
  item: Item;
  onPrepareOperation: (item: Item, operation: ManualOperation) => void;
}) {
  const completed = item.status === 'completed';
  return (
    <View style={styles.itemRow}>
      <View
        style={[styles.itemStripe, item.type === 'todo' ? styles.todoStripe : styles.eventStripe]}
      />
      <View style={styles.itemBody}>
        <View style={styles.itemHeader}>
          <Text style={[styles.itemTitle, completed && styles.completedText]}>{item.title}</Text>
          <Text style={styles.itemKind}>{item.type === 'todo' ? '待办' : '日历'}</Text>
        </View>
        <Text style={styles.itemMeta}>{itemSummary(item)}</Text>
        {item.reminders.length > 0 ? (
          <View style={styles.badges}>
            {item.reminders.slice(0, 2).map((reminder) => (
              <ReminderBadge key={reminder.id} reminder={reminder} />
            ))}
            {item.reminders.length > 2 ? (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>+{item.reminders.length - 2}</Text>
              </View>
            ) : null}
          </View>
        ) : null}
      </View>
      <View style={styles.rowActions}>
        {item.type === 'todo' ? (
          <Pressable
            onPress={() =>
              onPrepareOperation(item, completed ? 'cancel_complete_item' : 'complete_item')
            }
            style={styles.smallButton}
          >
            <Text style={styles.smallButtonText}>{completed ? '恢复' : '完成'}</Text>
          </Pressable>
        ) : null}
        <Pressable
          onPress={() => onPrepareOperation(item, 'delete_item')}
          style={styles.smallButtonDanger}
        >
          <Text style={styles.smallButtonDangerText}>删除</Text>
        </Pressable>
      </View>
    </View>
  );
}

function PendingWriteRow({
  onConfirm,
  onReject,
  writeRequest,
}: {
  onConfirm: (writeRequestId: string) => void;
  onReject: (writeRequestId: string) => void;
  writeRequest: WriteRequest;
}) {
  return (
    <View style={styles.pendingRow}>
      <View style={styles.itemBody}>
        <Text style={styles.itemTitle}>{previewTitle(writeRequest.candidate_payload)}</Text>
        <Text style={styles.itemMeta}>
          {manualOperationLabel(String(writeRequest.candidate_payload.operation))}
        </Text>
      </View>
      <View style={styles.rowActions}>
        <Pressable onPress={() => onReject(writeRequest.id)} style={styles.smallButtonDanger}>
          <Text style={styles.smallButtonDangerText}>取消</Text>
        </Pressable>
        <Pressable onPress={() => onConfirm(writeRequest.id)} style={styles.smallButton}>
          <Text style={styles.smallButtonText}>确认</Text>
        </Pressable>
      </View>
    </View>
  );
}

function ReminderBadge({ reminder }: { reminder: Reminder }) {
  return (
    <View style={styles.badge}>
      <Text style={styles.badgeText}>
        {reminderLabel(reminder)} · {statusLabel(reminder.status)}
      </Text>
    </View>
  );
}

function VoiceSheet({
  busy,
  onClose,
  onConfirm,
  onParse,
  onReject,
  onTranscriptChange,
  result,
  transcript,
  visible,
}: {
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
  onParse: () => void;
  onReject: () => void;
  onTranscriptChange: (value: string) => void;
  result: VoiceCommandResult | null;
  transcript: string;
  visible: boolean;
}) {
  const preview = result?.write_request?.candidate_payload;
  return (
    <Modal animationType="slide" visible={visible}>
      <View style={styles.modalRoot}>
        <ScrollView contentContainerStyle={styles.modalContent}>
          <View style={styles.topBar}>
            <View>
              <Text style={styles.kicker}>语音输入</Text>
              <Text style={styles.title}>确认候选</Text>
            </View>
            <Pressable onPress={onClose} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>关闭</Text>
            </Pressable>
          </View>

          <View style={styles.sheetSection}>
            <Text style={styles.sectionTitle}>转写内容</Text>
            <TextInput
              multiline
              onChangeText={onTranscriptChange}
              placeholder="输入或粘贴一句语音转写"
              placeholderTextColor={colors.muted}
              style={styles.textArea}
              value={transcript}
            />
            <Pressable
              onPress={onParse}
              style={[styles.primaryButton, busy && styles.disabledButton]}
            >
              <Text style={styles.primaryButtonText}>{busy ? '解析中' : '生成候选'}</Text>
            </Pressable>
          </View>

          {result?.clarification ? (
            <View style={styles.notice}>
              <Text style={styles.noticeTitle}>需要补充</Text>
              <Text style={styles.noticeText}>{result.clarification}</Text>
            </View>
          ) : null}

          {preview ? (
            <View style={styles.preview}>
              <Text style={styles.sectionTitle}>写入预览</Text>
              <Text style={styles.previewTitle}>{previewTitle(preview)}</Text>
              <Text style={styles.previewMeta}>{String(preview.operation ?? 'pending')}</Text>
              <View style={styles.modalActions}>
                <Pressable onPress={onReject} style={styles.secondaryButton}>
                  <Text style={styles.secondaryButtonText}>取消</Text>
                </Pressable>
                <Pressable
                  onPress={onConfirm}
                  style={[styles.primaryButton, busy && styles.disabledButton]}
                >
                  <Text style={styles.primaryButtonText}>确认写入</Text>
                </Pressable>
              </View>
            </View>
          ) : (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>等待候选</Text>
              <Text style={styles.emptyText}>生成候选后，写入前会停在确认门禁。</Text>
            </View>
          )}
        </ScrollView>
      </View>
    </Modal>
  );
}

function itemSummary(item: Item) {
  if (item.start_at) {
    return `开始 ${formatDate(item.start_at)}${item.place_text ? ` · ${item.place_text}` : ''}`;
  }
  if (item.due_at) {
    return `截止 ${formatDate(item.due_at)}${item.description ? ` · ${item.description}` : ''}`;
  }
  return item.description || statusLabel(item.status);
}

function previewTitle(payload: Record<string, unknown>) {
  const item = payload.item;
  if (item && typeof item === 'object' && 'title' in item) {
    return String((item as { title?: unknown }).title ?? '未命名事项');
  }
  return '未命名事项';
}

function reminderLabel(reminder: Reminder) {
  if (reminder.trigger_type === 'time' && reminder.trigger_at) {
    return formatDate(reminder.trigger_at);
  }
  if (reminder.trigger_type === 'enter_place') {
    return '到达地点';
  }
  if (reminder.trigger_type === 'leave_place') {
    return '离开地点';
  }
  return '回到地点';
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
  });
}

function modeLabel(mode: ViewMode) {
  return mode === 'today' ? '今日' : mode === 'week' ? '本周' : '本月';
}

function manualOperationLabel(operation: string) {
  if (operation === 'create_todo') {
    return '新增待办';
  }
  if (operation === 'create_calendar_event') {
    return '新增日历';
  }
  if (operation === 'complete_item') {
    return '完成待办';
  }
  if (operation === 'cancel_complete_item') {
    return '恢复待办';
  }
  if (operation === 'delete_item') {
    return '删除事项';
  }
  return operation;
}

function statusLabel(status: string) {
  if (status === 'active') {
    return '进行中';
  }
  if (status === 'completed') {
    return '已完成';
  }
  if (status === 'pending') {
    return '等待中';
  }
  if (status === 'delivered') {
    return '已提醒';
  }
  return status;
}

const styles = StyleSheet.create({
  badge: {
    backgroundColor: '#E9F7EF',
    borderColor: '#B8E3C8',
    borderRadius: 6,
    borderWidth: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  badgeText: {
    color: '#17633A',
    fontSize: 12,
    fontWeight: '700',
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  banner: {
    backgroundColor: '#FFF4D8',
    borderColor: '#E7C46A',
    borderRadius: 8,
    borderWidth: 1,
    color: '#775300',
    fontSize: 14,
    padding: spacing.md,
  },
  completedText: {
    color: colors.muted,
    textDecorationLine: 'line-through',
  },
  content: {
    gap: spacing.lg,
    padding: spacing.lg,
    paddingBottom: 116,
    paddingTop: 64,
  },
  disabledButton: {
    opacity: 0.65,
  },
  emptyState: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 8,
    borderStyle: 'dashed',
    borderWidth: 1,
    padding: spacing.xl,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 14,
    marginTop: spacing.xs,
    textAlign: 'center',
  },
  emptyTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '800',
  },
  eventStripe: {
    backgroundColor: '#7C5CFF',
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    color: colors.text,
    fontSize: 15,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  itemBody: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  itemHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
  },
  itemKind: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '700',
  },
  itemMeta: {
    color: colors.muted,
    fontSize: 13,
  },
  itemRow: {
    alignItems: 'stretch',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 82,
    overflow: 'hidden',
  },
  itemStripe: {
    width: 5,
  },
  itemTitle: {
    color: colors.text,
    flex: 1,
    fontSize: 16,
    fontWeight: '800',
  },
  kicker: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '700',
  },
  list: {
    gap: spacing.md,
  },
  metric: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    padding: spacing.md,
  },
  metricLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '700',
    marginTop: 2,
  },
  metricValue: {
    color: colors.text,
    fontSize: 22,
    fontWeight: '900',
  },
  metricsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  modalActions: {
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'flex-end',
    marginTop: spacing.md,
  },
  modalContent: {
    gap: spacing.lg,
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    paddingTop: 64,
  },
  modalRoot: {
    backgroundColor: colors.background,
    flex: 1,
  },
  notice: {
    backgroundColor: '#FFF4D8',
    borderColor: '#E7C46A',
    borderRadius: 8,
    borderWidth: 1,
    padding: spacing.md,
  },
  noticeText: {
    color: '#775300',
    fontSize: 14,
    marginTop: spacing.xs,
  },
  noticeTitle: {
    color: '#775300',
    fontSize: 15,
    fontWeight: '800',
  },
  preview: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    padding: spacing.md,
  },
  previewMeta: {
    color: colors.muted,
    fontSize: 13,
    marginTop: spacing.xs,
  },
  previewTitle: {
    color: colors.text,
    fontSize: 20,
    fontWeight: '900',
    marginTop: spacing.sm,
  },
  pendingRow: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: '#E7C46A',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    padding: spacing.md,
  },
  pendingSection: {
    gap: spacing.sm,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: 8,
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  primaryButtonText: {
    color: colors.surface,
    fontSize: 14,
    fontWeight: '900',
  },
  quickAdd: {
    gap: spacing.md,
  },
  quickAddHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  root: {
    backgroundColor: colors.background,
    flex: 1,
  },
  rowActions: {
    alignItems: 'flex-end',
    gap: spacing.sm,
    justifyContent: 'center',
    padding: spacing.md,
  },
  secondaryButton: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  secondaryButtonText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  sectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '900',
  },
  segmentButton: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    minHeight: 40,
    justifyContent: 'center',
  },
  segmentButtonActive: {
    backgroundColor: colors.text,
    borderColor: colors.text,
  },
  segmentButtonText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  segmentButtonTextActive: {
    color: colors.surface,
  },
  sheetSection: {
    gap: spacing.md,
  },
  smallButton: {
    alignItems: 'center',
    backgroundColor: '#EAF1FF',
    borderRadius: 6,
    minWidth: 58,
    paddingHorizontal: spacing.sm,
    paddingVertical: 7,
  },
  smallButtonDanger: {
    alignItems: 'center',
    backgroundColor: '#FFEDEE',
    borderRadius: 6,
    minWidth: 58,
    paddingHorizontal: spacing.sm,
    paddingVertical: 7,
  },
  smallButtonDangerText: {
    color: '#B4232C',
    fontSize: 12,
    fontWeight: '900',
  },
  smallButtonText: {
    color: colors.accent,
    fontSize: 12,
    fontWeight: '900',
  },
  statusPill: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  statusPillMuted: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
  },
  statusPillOnline: {
    backgroundColor: '#E9F7EF',
    borderColor: '#B8E3C8',
  },
  statusText: {
    fontSize: 13,
    fontWeight: '900',
  },
  statusTextMuted: {
    color: colors.muted,
  },
  statusTextOnline: {
    color: '#17633A',
  },
  subtle: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '700',
  },
  textArea: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    color: colors.text,
    fontSize: 16,
    minHeight: 120,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    textAlignVertical: 'top',
  },
  title: {
    color: colors.text,
    fontSize: 30,
    fontWeight: '900',
  },
  todoStripe: {
    backgroundColor: colors.accent,
  },
  toolbar: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  typeButton: {
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  typeButtonActive: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  typeButtonText: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '800',
  },
  typeButtonTextActive: {
    color: colors.surface,
  },
  typeToggle: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  voiceDock: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: 34,
    bottom: 28,
    height: 68,
    justifyContent: 'center',
    left: '50%',
    marginLeft: -34,
    position: 'absolute',
    width: 68,
  },
  voiceDockText: {
    color: colors.surface,
    fontSize: 14,
    fontWeight: '900',
  },
});
