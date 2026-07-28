import { StatusBar } from 'expo-status-bar';
import {
  getRecordingPermissionsAsync,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import * as Location from 'expo-location';
import * as Notifications from 'expo-notifications';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  applyReminderAction,
  confirmWriteRequest,
  createRepeatRule,
  createWriteRequest,
  createPlace,
  createVoiceCommand,
  deletePlace,
  degradePermission,
  getHealth,
  getRealtimeUrl,
  listItems,
  listOutboxMessages,
  listPendingWriteRequests,
  listPlaces,
  listReminders,
  listRepeatRules,
  rejectWriteRequest,
  updateWriteRequest,
  type Item,
  type Place,
  type OutboxMessage,
  type Reminder,
  type RepeatPattern,
  type RepeatRule,
  type RepeatSeriesStatus,
  type VoiceCommandResult,
  type WriteRequest,
} from '../api/client';
import { colors, spacing } from '../constants/theme';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

type ViewMode = 'today' | 'week' | 'month';
type ItemType = 'todo' | 'calendar_event';
type ConnectionState = 'checking' | 'online' | 'offline';
type SocketState = 'connecting' | 'connected' | 'reconnecting' | 'closed';
type DevicePermission = 'microphone' | 'notification' | 'location';
type DevicePermissionState = 'checking' | 'granted' | 'denied' | 'undetermined' | 'unavailable';
type ManualOperation =
  | 'create_todo'
  | 'create_calendar_event'
  | 'update_item'
  | 'complete_item'
  | 'cancel_complete_item'
  | 'delete_item';
type ReminderAction =
  | 'armed'
  | 'registered'
  | 'delivered'
  | 'failed'
  | 'registration_failed'
  | 'local_unavailable'
  | 'dismiss'
  | 'snooze'
  | 'cancel';

type EditDraft = {
  title: string;
  description: string;
  start_at: string;
  end_at: string;
  due_at: string;
  place_text: string;
};

type ReminderDraft = {
  trigger_at: string;
  trigger_type: 'time' | 'enter_place' | 'leave_place' | 'return_to_place';
  place_id: string;
  priority: 'low' | 'normal' | 'high';
};

export function HomeScreen() {
  const [connection, setConnection] = useState<ConnectionState>('checking');
  const [socketState, setSocketState] = useState<SocketState>('connecting');
  const [viewMode, setViewMode] = useState<ViewMode>('today');
  const [items, setItems] = useState<Item[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [repeatRules, setRepeatRules] = useState<RepeatRule[]>([]);
  const [outboxMessages, setOutboxMessages] = useState<OutboxMessage[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [pendingWrites, setPendingWrites] = useState<WriteRequest[]>([]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [itemType, setItemType] = useState<ItemType>('todo');
  const [banner, setBanner] = useState<string | null>(null);
  const [devicePermissions, setDevicePermissions] = useState<
    Record<DevicePermission, DevicePermissionState>
  >({
    location: 'checking',
    microphone: 'checking',
    notification: 'checking',
  });
  const [permissionBusy, setPermissionBusy] = useState<DevicePermission | null>(null);
  const [loading, setLoading] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('到家后提醒我取快递');
  const [voiceResult, setVoiceResult] = useState<VoiceCommandResult | null>(null);
  const [selectedVoiceCandidateId, setSelectedVoiceCandidateId] = useState<string | null>(null);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [editItem, setEditItem] = useState<Item | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft>(emptyEditDraft());
  const [editBusy, setEditBusy] = useState(false);
  const [reminderItem, setReminderItem] = useState<Item | null>(null);
  const [reminderDraft, setReminderDraft] = useState<ReminderDraft>(defaultReminderDraft());
  const [reminderBusy, setReminderBusy] = useState(false);
  const [actingReminderId, setActingReminderId] = useState<string | null>(null);
  const [checkingPlaceReminders, setCheckingPlaceReminders] = useState(false);
  const [placeLabel, setPlaceLabel] = useState('家');
  const [placeType, setPlaceType] = useState<Place['place_type']>('home');
  const [placeRadius, setPlaceRadius] = useState('100');
  const [placeDescription, setPlaceDescription] = useState('');
  const [placeBusy, setPlaceBusy] = useState(false);
  const [saveCurrentPlaceBusy, setSaveCurrentPlaceBusy] = useState(false);
  const [deletingPlaceId, setDeletingPlaceId] = useState<string | null>(null);
  const [repeatPattern, setRepeatPattern] = useState<RepeatPattern>('weekdays');
  const [repeatTimeOfDay, setRepeatTimeOfDay] = useState('09:00');
  const [repeatWeekdays, setRepeatWeekdays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [repeatSeriesStatus, setRepeatSeriesStatus] = useState<RepeatSeriesStatus>('active');
  const [repeatBusy, setRepeatBusy] = useState(false);
  const [degradeTitle, setDegradeTitle] = useState('到家取快递');
  const [degradePlaceText, setDegradePlaceText] = useState('家');
  const [degradeBusy, setDegradeBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [
      itemResponse,
      pendingResponse,
      placeResponse,
      repeatResponse,
      outboxResponse,
      reminderResponse,
    ] = await Promise.all([
      listItems(),
      listPendingWriteRequests(),
      listPlaces(),
      listRepeatRules(),
      listOutboxMessages(),
      listReminders(),
    ]);
    setItems(itemResponse);
    setPendingWrites(pendingResponse);
    setPlaces(placeResponse);
    setRepeatRules(repeatResponse);
    setOutboxMessages(outboxResponse);
    setReminders(reminderResponse);
  }, []);

  const refreshDevicePermissions = useCallback(async () => {
    setDevicePermissions(await loadDevicePermissions());
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

    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let socket: WebSocket | null = null;
    let reconnectAttempt = 0;

    const scheduleReconnect = () => {
      if (!active) {
        return;
      }
      setSocketState('reconnecting');
      const delayMs = Math.min(5000, 500 * 2 ** reconnectAttempt);
      reconnectAttempt += 1;
      reconnectTimer = setTimeout(connectRealtime, delayMs);
    };

    const requestSync = (target: WebSocket) => {
      target.send(JSON.stringify({ after: syncCursorRef.current, type: 'sync.request' }));
    };

    const handleRealtimeMessage = (rawMessage: string) => {
      const message = parseRealtimeMessage(rawMessage);
      if (!message) {
        return;
      }

      if (message.event_type === 'sync.response') {
        const payload = message.payload;
        const nextCursor =
          payload && typeof payload.next_cursor === 'number' ? payload.next_cursor : null;
        const events = Array.isArray(payload?.events) ? payload.events : [];
        syncCursorRef.current =
          nextCursor ??
          events.reduce(
            (cursor, event) =>
              typeof event.version === 'number' ? Math.max(cursor, event.version) : cursor,
            syncCursorRef.current,
          );
        refresh().catch(() => {
          if (active) {
            setBanner('同步失败');
          }
        });
        return;
      }

      if (typeof message.version === 'number') {
        syncCursorRef.current = Math.max(syncCursorRef.current, message.version);
      }

      if (
        message.event_type &&
        message.event_type !== 'connection.ready' &&
        message.event_type !== 'connection.heartbeat'
      ) {
        refresh().catch(() => {
          if (active) {
            setBanner('同步失败');
          }
        });
      }
    };

    const connectRealtime = () => {
      if (!active) {
        return;
      }

      setSocketState(reconnectAttempt === 0 ? 'connecting' : 'reconnecting');
      const nextSocket = new WebSocket(getRealtimeUrl());
      socket = nextSocket;
      let reconnectScheduled = false;

      nextSocket.onopen = () => {
        if (!active) {
          return;
        }
        reconnectAttempt = 0;
        setSocketState('connected');
        requestSync(nextSocket);
      };
      nextSocket.onclose = () => {
        if (reconnectScheduled) {
          return;
        }
        reconnectScheduled = true;
        scheduleReconnect();
      };
      nextSocket.onerror = () => {
        if (!active) {
          return;
        }
        setSocketState('reconnecting');
        nextSocket.close();
      };
      nextSocket.onmessage = (event) => {
        if (active) {
          handleRealtimeMessage(String(event.data));
        }
      };
    };

    connectRealtime();

    return () => {
      active = false;
      clearTimeout(initialLoadTimer);
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [refresh]);

  useEffect(() => {
    let active = true;

    loadDevicePermissions()
      .then((nextPermissions) => {
        if (active) {
          setDevicePermissions(nextPermissions);
        }
      })
      .catch(() => {
        if (active) {
          setDevicePermissions({
            location: 'unavailable',
            microphone: 'unavailable',
            notification: 'unavailable',
          });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const calendarItems = useMemo(
    () => items.filter((item) => item.type === 'calendar_event'),
    [items],
  );
  const todoItems = useMemo(() => items.filter((item) => item.type === 'todo'), [items]);
  const itemTitleById = useMemo(() => new Map(items.map((item) => [item.id, item.title])), [items]);
  const placeById = useMemo(() => new Map(places.map((place) => [place.id, place])), [places]);
  const processedNotificationIdsRef = useRef(new Set<string>());
  const syncCursorRef = useRef(0);
  const visibleItems = useMemo(() => filterItemsByMode(items, viewMode), [items, viewMode]);

  const markReminderDelivered = useCallback(
    async (reminderId: string, notificationId: string | null) => {
      const dedupeKey = notificationId ?? reminderId;
      if (processedNotificationIdsRef.current.has(dedupeKey)) {
        return;
      }
      processedNotificationIdsRef.current.add(dedupeKey);

      try {
        await applyReminderAction(reminderId, {
          action: 'delivered',
          local_notification_id: notificationId ?? undefined,
        });
        await refresh();
      } catch {
        // Keep the app moving; the reminder card already carries the current state.
      }
    },
    [refresh],
  );

  useEffect(() => {
    const receivedListener = Notifications.addNotificationReceivedListener((notification) => {
      const reminderId = notification.request.content.data?.reminderId;
      if (typeof reminderId === 'string') {
        void markReminderDelivered(reminderId, notification.request.identifier);
      }
    });

    const responseListener = Notifications.addNotificationResponseReceivedListener((response) => {
      const reminderId = response.notification.request.content.data?.reminderId;
      if (typeof reminderId === 'string') {
        void markReminderDelivered(reminderId, response.notification.request.identifier);
      }
    });

    return () => {
      receivedListener.remove();
      responseListener.remove();
    };
  }, [markReminderDelivered]);

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

  async function handleRequestDevicePermission(permission: DevicePermission) {
    if (permissionBusy) {
      return;
    }

    setPermissionBusy(permission);
    setBanner(null);
    try {
      if (permission === 'microphone') {
        await requestRecordingPermissionsAsync();
      } else if (permission === 'notification') {
        await Notifications.requestPermissionsAsync();
      } else {
        await Location.requestForegroundPermissionsAsync();
      }
      await refreshDevicePermissions();
      setBanner(`${devicePermissionLabel(permission)}权限已更新`);
    } catch {
      setBanner(`${devicePermissionLabel(permission)}权限请求失败`);
    } finally {
      setPermissionBusy(null);
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

  function handleOpenEdit(item: Item) {
    setEditItem(item);
    setEditDraft({
      description: item.description ?? '',
      due_at: toInputDateTime(item.due_at),
      end_at: toInputDateTime(item.end_at),
      place_text: item.place_text ?? '',
      start_at: toInputDateTime(item.start_at),
      title: item.title,
    });
  }

  function handleOpenReminder(item: Item) {
    setReminderItem(item);
    setReminderDraft(defaultReminderDraft(places[0]?.id));
  }

  async function handlePrepareEditItem() {
    if (!editItem || !editDraft.title.trim() || editBusy) {
      return;
    }

    setEditBusy(true);
    setBanner(null);
    try {
      const dueAt = normalizeInputDateTime(editDraft.due_at);
      const endAt = normalizeInputDateTime(editDraft.end_at);
      const startAt = normalizeInputDateTime(editDraft.start_at);

      await createWriteRequest({
        source_command_id: `manual-edit-${editItem.id}-${Date.now()}`,
        candidate_payload: {
          item: {
            description: editDraft.description.trim() || null,
            due_at: dueAt,
            end_at: endAt,
            place_text: editDraft.place_text.trim() || null,
            start_at: startAt,
            title: editDraft.title.trim(),
            type: editItem.type,
          },
          operation: 'update_item',
          operations: [
            {
              changes: {
                description: editDraft.description.trim() || null,
                due_at: dueAt,
                end_at: endAt,
                place_text: editDraft.place_text.trim() || null,
                start_at: startAt,
                title: editDraft.title.trim(),
              },
              op: 'update_item',
              target_id: editItem.id,
            },
          ],
          source_text: 'manual edit',
          target_id: editItem.id,
        },
      });
      setEditItem(null);
      await refresh();
      setBanner('已生成待确认写入');
    } catch (error) {
      setBanner(
        error instanceof Error && error.message === 'invalid datetime'
          ? '时间格式不正确'
          : '创建确认请求失败',
      );
    } finally {
      setEditBusy(false);
    }
  }

  async function handlePrepareReminder() {
    if (!reminderItem || reminderBusy) {
      return;
    }

    setReminderBusy(true);
    setBanner(null);
    try {
      const triggerAt =
        reminderDraft.trigger_type === 'time'
          ? normalizeInputDateTime(reminderDraft.trigger_at)
          : null;
      if (reminderDraft.trigger_type === 'time' && !triggerAt) {
        throw new Error('invalid datetime');
      }
      if (reminderDraft.trigger_type !== 'time' && !reminderDraft.place_id) {
        throw new Error('missing place');
      }

      await createWriteRequest({
        source_command_id: `manual-reminder-${reminderItem.id}-${Date.now()}`,
        candidate_payload: {
          item: {
            title: reminderItem.title,
            type: reminderItem.type,
          },
          operation: 'create_reminder',
          reminders: [
            {
              place_id: reminderDraft.trigger_type === 'time' ? null : reminderDraft.place_id,
              priority: reminderDraft.priority,
              trigger_at: triggerAt,
              trigger_type: reminderDraft.trigger_type,
            },
          ],
          source_text: 'manual reminder',
          target_id: reminderItem.id,
        },
      });
      setReminderItem(null);
      await refresh();
      setBanner('已生成待确认写入');
    } catch (error) {
      setBanner(
        error instanceof Error && error.message === 'invalid datetime'
          ? '时间格式不正确'
          : error instanceof Error && error.message === 'missing place'
            ? '请先选择地点'
            : '创建确认请求失败',
      );
    } finally {
      setReminderBusy(false);
    }
  }

  async function handleCreatePlace() {
    if (!placeLabel.trim() || placeBusy) {
      return;
    }

    const radius = Number.parseInt(placeRadius, 10);
    if (!Number.isFinite(radius) || radius <= 0) {
      setBanner('半径不正确');
      return;
    }

    setPlaceBusy(true);
    setBanner(null);
    try {
      await createPlace({
        accuracy_meters: null,
        description: placeDescription.trim() || null,
        label: placeLabel.trim(),
        latitude: null,
        longitude: null,
        place_type: placeType,
        radius_meters: radius,
      });
      await refresh();
      setBanner('地点已保存');
    } catch {
      setBanner('保存地点失败');
    } finally {
      setPlaceBusy(false);
    }
  }

  async function handleSaveCurrentPlace() {
    if (!placeLabel.trim() || saveCurrentPlaceBusy) {
      return;
    }

    const radius = Number.parseInt(placeRadius, 10);
    if (!Number.isFinite(radius) || radius <= 0) {
      setBanner('半径不正确');
      return;
    }

    setSaveCurrentPlaceBusy(true);
    setBanner(null);
    try {
      const permission = await Location.getForegroundPermissionsAsync();
      const granted = permission.granted
        ? permission
        : await Location.requestForegroundPermissionsAsync();
      if (!granted.granted) {
        setBanner('定位权限未开启');
        return;
      }

      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const accuracy = position.coords.accuracy ?? null;
      await createPlace({
        accuracy_meters: accuracy != null ? Math.round(accuracy) : null,
        description: placeDescription.trim() || null,
        label: placeLabel.trim(),
        latitude: position.coords.latitude.toFixed(6),
        longitude: position.coords.longitude.toFixed(6),
        place_type: placeType,
        radius_meters: radius,
      });
      await refresh();
      setBanner(
        accuracy !== null && accuracy > radius
          ? '已保存当前位置，定位不精确，提醒可能不准'
          : '当前位置已保存',
      );
    } catch (error) {
      setBanner(error instanceof Error ? error.message : '保存当前位置失败');
    } finally {
      setSaveCurrentPlaceBusy(false);
    }
  }

  async function handleDeletePlace(place: Place) {
    if (deletingPlaceId === place.id) {
      return;
    }

    setDeletingPlaceId(place.id);
    setBanner(null);
    try {
      await deletePlace(place.id);
      await refresh();
      setBanner('地点已删除');
    } catch {
      setBanner('删除地点失败');
    } finally {
      setDeletingPlaceId(null);
    }
  }

  async function handleCreateRepeatRule() {
    if (repeatBusy) {
      return;
    }

    const timeOfDay = repeatTimeOfDay.trim();
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(timeOfDay)) {
      setBanner('重复时间格式应为 24 小时 HH:MM');
      return;
    }

    const weekdays =
      repeatPattern === 'daily'
        ? []
        : repeatPattern === 'weekdays'
          ? [1, 2, 3, 4, 5]
          : repeatWeekdays;
    if (repeatPattern === 'custom_weekdays' && weekdays.length === 0) {
      setBanner('请至少选择一个周几');
      return;
    }

    setRepeatBusy(true);
    setBanner(null);
    try {
      await createRepeatRule({
        pattern: repeatPattern,
        series_status: repeatSeriesStatus,
        time_of_day: timeOfDay,
        weekdays,
      });
      await refresh();
      setBanner('重复规则已保存');
    } catch {
      setBanner('保存重复规则失败');
    } finally {
      setRepeatBusy(false);
    }
  }

  function handleToggleRepeatWeekday(weekday: number) {
    setRepeatWeekdays((current) => {
      if (current.includes(weekday)) {
        return current.filter((value) => value !== weekday);
      }
      return [...current, weekday].sort((left, right) => left - right);
    });
  }

  async function handleLocationDegrade() {
    if (!degradeTitle.trim() || degradeBusy) {
      return;
    }

    setDegradeBusy(true);
    setBanner(null);
    try {
      await degradePermission({
        permission: 'location',
        place_text: degradePlaceText.trim() || null,
        reason: 'location_permission_denied',
        title: degradeTitle.trim(),
      });
      await refresh();
      setBanner('已降级为普通待办');
    } catch {
      setBanner('权限降级失败');
    } finally {
      setDegradeBusy(false);
    }
  }

  async function handleReminderAction(reminder: Reminder, action: ReminderAction) {
    if (actingReminderId === reminder.id) {
      return;
    }

    setActingReminderId(reminder.id);
    setBanner(null);
    try {
      let nextAction = action;
      let localNotificationId: string | undefined;
      let registrationFailedReason: string | undefined;
      if (action === 'registered') {
        try {
          localNotificationId = await scheduleLocalReminderNotification(
            reminder,
            itemTitleById.get(reminder.item_id) ?? 'Timeflow 提醒',
          );
        } catch (error) {
          nextAction = 'registration_failed';
          registrationFailedReason =
            error instanceof Error ? error.message : 'notification_registration_failed';
        }
      }
      await applyReminderAction(reminder.id, {
        action: nextAction,
        fallback_after_seconds:
          nextAction === 'failed' ||
          nextAction === 'registration_failed' ||
          nextAction === 'local_unavailable'
            ? 300
            : undefined,
        failed_reason:
          nextAction === 'failed'
            ? 'manual_failed'
            : nextAction === 'registration_failed'
              ? (registrationFailedReason ?? 'registration_failed')
              : nextAction === 'local_unavailable'
                ? 'local_unavailable'
                : undefined,
        local_notification_id: localNotificationId,
        snooze_minutes: nextAction === 'snooze' ? 10 : undefined,
      });
      await refresh();
      setBanner(reminderActionSuccessLabel(nextAction));
    } catch {
      setBanner('提醒处理失败');
    } finally {
      setActingReminderId(null);
    }
  }

  async function handleCheckPlaceReminders() {
    if (checkingPlaceReminders) {
      return;
    }

    setCheckingPlaceReminders(true);
    setBanner(null);
    try {
      const permission = await Location.getForegroundPermissionsAsync();
      const granted = permission.granted
        ? permission
        : await Location.requestForegroundPermissionsAsync();
      if (!granted.granted) {
        setBanner('定位权限未开启');
        return;
      }

      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      let appliedCount = 0;
      for (const reminder of reminders) {
        const action = resolvePlaceReminderAction(reminder, placeById, position.coords);
        if (!action) {
          continue;
        }
        await applyReminderAction(reminder.id, { action });
        appliedCount += 1;
      }
      if (appliedCount > 0) {
        await refresh();
      }
      setBanner(appliedCount > 0 ? `已更新 ${appliedCount} 条地点提醒` : '没有触发地点提醒');
    } catch (error) {
      setBanner(error instanceof Error ? error.message : '检查地点提醒失败');
    } finally {
      setCheckingPlaceReminders(false);
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
    setSelectedVoiceCandidateId(null);
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

    if (voiceResult.candidates.length > 1 && !selectedVoiceCandidateId) {
      setBanner('请先选择一个候选事项');
      return;
    }

    setVoiceBusy(true);
    try {
      await confirmWriteRequest(writeRequestId);
      await refresh();
      setVoiceOpen(false);
      setVoiceResult(null);
      setSelectedVoiceCandidateId(null);
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
      setSelectedVoiceCandidateId(null);
      setBanner('已取消语音候选');
    } catch {
      setBanner('取消失败');
    } finally {
      setVoiceBusy(false);
    }
  }

  async function handleChooseVoiceCandidate(candidate: Item) {
    if (!voiceResult?.write_request || voiceBusy) {
      return;
    }

    setVoiceBusy(true);
    setBanner(null);
    try {
      const narrowedPayload = narrowCandidatePayload(
        voiceResult.write_request.candidate_payload,
        candidate,
      );
      const response = await updateWriteRequest(voiceResult.write_request.id, {
        candidate_payload: narrowedPayload,
      });
      setVoiceResult((current) =>
        current
          ? {
              ...current,
              write_request: response.write_request,
            }
          : current,
      );
      setSelectedVoiceCandidateId(candidate.id);
      await refresh();
      setBanner('已选择候选事项');
    } catch {
      setBanner('选择候选失败');
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
          <Metric label="提醒" value={reminders.length} />
          <Metric label="地点" value={places.length} />
          <Metric label="待确认" value={pendingWrites.length} />
        </View>

        {banner ? <Text style={styles.banner}>{banner}</Text> : null}

        <PermissionPanel
          busy={permissionBusy}
          onRequest={handleRequestDevicePermission}
          permissions={devicePermissions}
        />

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

        <View style={styles.placeSection}>
          <View style={styles.quickAddHeader}>
            <Text style={styles.sectionTitle}>地点库</Text>
            <View style={styles.typeToggle}>
              {(['home', 'work', 'custom', 'temporary_parking'] as const).map((type) => (
                <Pressable
                  key={type}
                  onPress={() => setPlaceType(type)}
                  style={[styles.typeButton, placeType === type && styles.typeButtonActive]}
                >
                  <Text
                    style={[
                      styles.typeButtonText,
                      placeType === type && styles.typeButtonTextActive,
                    ]}
                  >
                    {placeTypeLabel(type)}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
          <TextInput
            value={placeLabel}
            onChangeText={setPlaceLabel}
            placeholder="地点名称"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <TextInput
            value={placeRadius}
            onChangeText={setPlaceRadius}
            placeholder="触发半径，默认 100"
            placeholderTextColor={colors.muted}
            style={styles.input}
            keyboardType="number-pad"
          />
          <TextInput
            value={placeDescription}
            onChangeText={setPlaceDescription}
            placeholder="文字描述，可选"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <Pressable
            onPress={handleCreatePlace}
            style={[styles.primaryButton, placeBusy && styles.disabledButton]}
          >
            <Text style={styles.primaryButtonText}>{placeBusy ? '保存中' : '保存地点'}</Text>
          </Pressable>
          <Pressable
            onPress={handleSaveCurrentPlace}
            style={[styles.secondaryButton, saveCurrentPlaceBusy && styles.disabledButton]}
          >
            <Text style={styles.secondaryButtonText}>
              {saveCurrentPlaceBusy ? '定位中' : '保存当前位置'}
            </Text>
          </Pressable>

          {places.length > 0 ? (
            <View style={styles.placeList}>
              {places.map((place) => (
                <View key={place.id} style={styles.placeRow}>
                  <View style={styles.placeBody}>
                    <View style={styles.itemHeader}>
                      <Text style={styles.itemTitle}>{place.label}</Text>
                      <Text style={styles.itemKind}>{placeTypeLabel(place.place_type)}</Text>
                    </View>
                    <Text style={styles.placeMeta}>
                      半径 {place.radius_meters}m
                      {place.description ? ` · ${place.description}` : ''}
                    </Text>
                  </View>
                  <View style={styles.rowActions}>
                    <Pressable
                      onPress={() => handleDeletePlace(place)}
                      style={styles.smallButtonDanger}
                    >
                      <Text style={styles.smallButtonDangerText}>
                        {deletingPlaceId === place.id ? '删除中' : '删除'}
                      </Text>
                    </Pressable>
                  </View>
                </View>
              ))}
            </View>
          ) : null}
        </View>

        <View style={styles.repeatSection}>
          <View style={styles.quickAddHeader}>
            <Text style={styles.sectionTitle}>重复规则</Text>
            <Text style={styles.subtle}>{repeatRules.length} 项</Text>
          </View>
          <View style={styles.placePicker}>
            {(['daily', 'weekdays', 'custom_weekdays'] as const).map((pattern) => {
              const selected = repeatPattern === pattern;
              return (
                <Pressable
                  key={pattern}
                  onPress={() => setRepeatPattern(pattern)}
                  style={[styles.placeChip, selected && styles.placeChipActive]}
                >
                  <Text style={[styles.placeChipText, selected && styles.placeChipTextActive]}>
                    {repeatPatternLabel(pattern)}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          {repeatPattern === 'custom_weekdays' ? (
            <View style={styles.placePicker}>
              {[1, 2, 3, 4, 5, 6, 7].map((weekday) => {
                const selected = repeatWeekdays.includes(weekday);
                return (
                  <Pressable
                    key={weekday}
                    onPress={() => handleToggleRepeatWeekday(weekday)}
                    style={[styles.placeChip, selected && styles.placeChipActive]}
                  >
                    <Text style={[styles.placeChipText, selected && styles.placeChipTextActive]}>
                      {weekdayLabel(weekday)}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ) : null}
          <TextInput
            value={repeatTimeOfDay}
            onChangeText={setRepeatTimeOfDay}
            placeholder="触发时间，例如 09:00"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <View style={styles.placePicker}>
            {(['active', 'paused', 'stopped'] as const).map((status) => {
              const selected = repeatSeriesStatus === status;
              return (
                <Pressable
                  key={status}
                  onPress={() => setRepeatSeriesStatus(status)}
                  style={[styles.placeChip, selected && styles.placeChipActive]}
                >
                  <Text style={[styles.placeChipText, selected && styles.placeChipTextActive]}>
                    {seriesStatusLabel(status)}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          <Pressable
            onPress={handleCreateRepeatRule}
            style={[styles.primaryButton, repeatBusy && styles.disabledButton]}
          >
            <Text style={styles.primaryButtonText}>{repeatBusy ? '保存中' : '保存重复规则'}</Text>
          </Pressable>

          {repeatRules.length > 0 ? (
            <View style={styles.placeList}>
              {repeatRules.map((repeatRule) => (
                <View key={repeatRule.id} style={styles.placeRow}>
                  <View style={styles.placeBody}>
                    <View style={styles.itemHeader}>
                      <Text style={styles.itemTitle}>{repeatPatternLabel(repeatRule.pattern)}</Text>
                      <Text style={styles.itemKind}>
                        {seriesStatusLabel(repeatRule.series_status)}
                      </Text>
                    </View>
                    <Text style={styles.placeMeta}>{repeatRuleSummary(repeatRule)}</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : null}
        </View>

        <View style={styles.degradeSection}>
          <View style={styles.quickAddHeader}>
            <Text style={styles.sectionTitle}>权限降级</Text>
            <Text style={styles.subtle}>定位</Text>
          </View>
          <TextInput
            value={degradeTitle}
            onChangeText={setDegradeTitle}
            placeholder="事项标题"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <TextInput
            value={degradePlaceText}
            onChangeText={setDegradePlaceText}
            placeholder="文字地点"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <Pressable
            onPress={handleLocationDegrade}
            style={[styles.primaryButton, degradeBusy && styles.disabledButton]}
          >
            <Text style={styles.primaryButtonText}>{degradeBusy ? '处理中' : '降级为待办'}</Text>
          </Pressable>
        </View>

        <View style={styles.reminderOverviewSection}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>提醒总览</Text>
            <Text style={styles.subtle}>{reminders.length} 条</Text>
          </View>
          <Pressable
            onPress={handleCheckPlaceReminders}
            style={[styles.secondaryButton, checkingPlaceReminders && styles.disabledButton]}
          >
            <Text style={styles.secondaryButtonText}>
              {checkingPlaceReminders ? '检查中' : '检查地点提醒'}
            </Text>
          </Pressable>
          {reminders.length > 0 ? (
            <View style={styles.placeList}>
              {reminders.map((reminder) => (
                <View key={reminder.id} style={styles.queryRow}>
                  <View style={styles.itemHeader}>
                    <Text style={styles.itemTitle}>
                      {itemTitleById.get(reminder.item_id) ?? reminder.item_id.slice(0, 8)}
                    </Text>
                    <Text style={styles.itemKind}>{statusLabel(reminder.status)}</Text>
                  </View>
                  <Text style={styles.placeMeta}>{reminderOverviewMeta(reminder)}</Text>
                  <ReminderControl
                    actingReminderId={actingReminderId}
                    onAction={handleReminderAction}
                    reminder={reminder}
                  />
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.emptyText}>还没有提醒。</Text>
          )}
        </View>

        <View style={styles.outboxSection}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>同步事件</Text>
            <Text style={styles.subtle}>{outboxMessages.length} 条</Text>
          </View>
          {outboxMessages.length > 0 ? (
            <View style={styles.placeList}>
              {outboxMessages.slice(-5).map((message) => (
                <View key={message.id} style={styles.queryRow}>
                  <View style={styles.itemHeader}>
                    <Text style={styles.itemTitle}>{outboxMessageSummary(message)}</Text>
                    <Text style={styles.itemKind}>{message.status}</Text>
                  </View>
                  <Text style={styles.placeMeta}>{outboxMessageMeta(message)}</Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.emptyText}>还没有同步事件。</Text>
          )}
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
              <ItemRow
                key={item.id}
                item={item}
                actingReminderId={actingReminderId}
                onEdit={handleOpenEdit}
                onPrepareOperation={handlePrepareItemOperation}
                onReminderAction={handleReminderAction}
                onRemind={handleOpenReminder}
              />
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
        onChooseCandidate={handleChooseVoiceCandidate}
        result={voiceResult}
        selectedCandidateId={selectedVoiceCandidateId}
        transcript={voiceTranscript}
        visible={voiceOpen}
        onTranscriptChange={setVoiceTranscript}
      />

      <EditSheet
        busy={editBusy}
        draft={editDraft}
        item={editItem}
        onClose={() => setEditItem(null)}
        onChangeDraft={setEditDraft}
        onSubmit={handlePrepareEditItem}
        visible={editItem !== null}
      />

      <ReminderSheet
        busy={reminderBusy}
        draft={reminderDraft}
        item={reminderItem}
        onChangeDraft={setReminderDraft}
        onClose={() => setReminderItem(null)}
        onSubmit={handlePrepareReminder}
        places={places}
        visible={reminderItem !== null}
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
  const label = online
    ? '已连接'
    : socketState === 'connecting' || socketState === 'reconnecting'
      ? '重连中'
      : connection === 'checking'
        ? '检查中'
        : '离线';
  return (
    <View style={[styles.statusPill, online ? styles.statusPillOnline : styles.statusPillMuted]}>
      <Text style={[styles.statusText, online ? styles.statusTextOnline : styles.statusTextMuted]}>
        {label}
      </Text>
    </View>
  );
}

function parseRealtimeMessage(
  rawMessage: string,
): { event_type?: string; payload?: { events?: unknown; next_cursor?: unknown }; version?: unknown } | null {
  try {
    const parsed = JSON.parse(rawMessage) as unknown;
    if (parsed && typeof parsed === 'object') {
      return parsed as {
        event_type?: string;
        payload?: { events?: unknown; next_cursor?: unknown };
        version?: unknown;
      };
    }
  } catch {
    return null;
  }
  return null;
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

function PermissionPanel({
  busy,
  onRequest,
  permissions,
}: {
  busy: DevicePermission | null;
  onRequest: (permission: DevicePermission) => void;
  permissions: Record<DevicePermission, DevicePermissionState>;
}) {
  return (
    <View style={styles.permissionSection}>
      {(['microphone', 'notification', 'location'] as const).map((permission) => {
        const granted = permissions[permission] === 'granted';
        return (
          <View key={permission} style={styles.permissionRow}>
            <View style={styles.placeBody}>
              <Text style={styles.itemTitle}>{devicePermissionLabel(permission)}</Text>
              <Text style={styles.placeMeta}>
                {devicePermissionStateLabel(permissions[permission])}
              </Text>
            </View>
            <Pressable
              onPress={() => onRequest(permission)}
              style={[styles.smallButton, busy === permission && styles.disabledButton]}
            >
              <Text style={styles.smallButtonText}>
                {busy === permission ? '请求中' : granted ? '刷新' : '开启'}
              </Text>
            </Pressable>
          </View>
        );
      })}
    </View>
  );
}

function ItemRow({
  item,
  actingReminderId,
  onEdit,
  onPrepareOperation,
  onReminderAction,
  onRemind,
}: {
  item: Item;
  actingReminderId: string | null;
  onEdit: (item: Item) => void;
  onPrepareOperation: (item: Item, operation: ManualOperation) => void;
  onReminderAction: (reminder: Reminder, action: ReminderAction) => void;
  onRemind: (item: Item) => void;
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
              <ReminderControl
                key={reminder.id}
                actingReminderId={actingReminderId}
                onAction={onReminderAction}
                reminder={reminder}
              />
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
        <Pressable onPress={() => onEdit(item)} style={styles.smallButton}>
          <Text style={styles.smallButtonText}>编辑</Text>
        </Pressable>
        <Pressable onPress={() => onRemind(item)} style={styles.smallButton}>
          <Text style={styles.smallButtonText}>提醒</Text>
        </Pressable>
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

function ReminderControl({
  actingReminderId,
  onAction,
  reminder,
}: {
  actingReminderId: string | null;
  onAction: (reminder: Reminder, action: ReminderAction) => void;
  reminder: Reminder;
}) {
  const active =
    reminder.status === 'pending' ||
    reminder.status === 'armed' ||
    reminder.status === 'snoozed' ||
    reminder.status === 'delivered';
  const canReportDelivery = active || reminder.status === 'failed';
  const busy = actingReminderId === reminder.id;
  return (
    <View style={styles.reminderControl}>
      <View style={styles.badge}>
        <Text style={styles.badgeText}>
          {reminderLabel(reminder)} · {statusLabel(reminder.status)}
        </Text>
      </View>
      {active ? (
        <View style={styles.reminderActions}>
          <Pressable
            onPress={() => onAction(reminder, 'snooze')}
            style={[styles.tinyButton, busy && styles.disabledButton]}
          >
            <Text style={styles.tinyButtonText}>延后</Text>
          </Pressable>
          <Pressable
            onPress={() => onAction(reminder, 'dismiss')}
            style={[styles.tinyButton, busy && styles.disabledButton]}
          >
            <Text style={styles.tinyButtonText}>确认</Text>
          </Pressable>
          <Pressable
            onPress={() => onAction(reminder, 'cancel')}
            style={[styles.tinyButtonDanger, busy && styles.disabledButton]}
          >
            <Text style={styles.tinyButtonDangerText}>取消</Text>
          </Pressable>
        </View>
      ) : null}
      {canReportDelivery ? (
        <View style={styles.reminderDiagnostics}>
          <Pressable
            onPress={() => onAction(reminder, 'registered')}
            style={[styles.tinyButton, busy && styles.disabledButton]}
          >
            <Text style={styles.tinyButtonText}>注册</Text>
          </Pressable>
          <Pressable
            onPress={() => onAction(reminder, 'delivered')}
            style={[styles.tinyButton, busy && styles.disabledButton]}
          >
            <Text style={styles.tinyButtonText}>送达</Text>
          </Pressable>
          <Pressable
            onPress={() => onAction(reminder, 'failed')}
            style={[styles.tinyButtonDanger, busy && styles.disabledButton]}
          >
            <Text style={styles.tinyButtonDangerText}>失败</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

function VoiceSheet({
  busy,
  onClose,
  onConfirm,
  onParse,
  onReject,
  onChooseCandidate,
  onTranscriptChange,
  result,
  selectedCandidateId,
  transcript,
  visible,
}: {
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
  onParse: () => void;
  onReject: () => void;
  onChooseCandidate: (candidate: Item) => void;
  onTranscriptChange: (value: string) => void;
  result: VoiceCommandResult | null;
  selectedCandidateId: string | null;
  transcript: string;
  visible: boolean;
}) {
  const recorder = useAudioRecorder(RecordingPresets.LOW_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const [recordingBusy, setRecordingBusy] = useState(false);
  const [recordingMessage, setRecordingMessage] = useState<string | null>(null);
  const [recordedUri, setRecordedUri] = useState<string | null>(null);
  const preview = result?.write_request?.candidate_payload;
  const needsSelection = Boolean(result?.write_request && result.candidates.length > 1);
  const canConfirm = Boolean(preview) && (!needsSelection || selectedCandidateId !== null) && !busy;

  async function handleToggleRecording() {
    if (recordingBusy) {
      return;
    }

    setRecordingBusy(true);
    setRecordingMessage(null);
    try {
      if (recorderState.isRecording) {
        await recorder.stop();
        setRecordedUri(recorder.uri ?? recorderState.url ?? null);
        setRecordingMessage('录音已保存');
        return;
      }

      const permission = await getRecordingPermissionsAsync();
      const granted = permission.granted ? permission : await requestRecordingPermissionsAsync();
      if (!granted.granted) {
        setRecordingMessage('麦克风权限未开启');
        return;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        interruptionMode: 'doNotMix',
        playsInSilentMode: true,
      });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecordedUri(null);
      setRecordingMessage('正在录音');
    } catch (error) {
      setRecordingMessage(error instanceof Error ? error.message : '录音失败');
    } finally {
      setRecordingBusy(false);
    }
  }

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
            <Pressable
              onPress={handleToggleRecording}
              style={[styles.secondaryButton, recordingBusy && styles.disabledButton]}
            >
              <Text style={styles.secondaryButtonText}>
                {recorderState.isRecording ? '停止录音' : '开始录音'}
              </Text>
            </Pressable>
            <Text style={styles.previewMeta}>
              {recorderState.isRecording
                ? `录音中 ${Math.ceil(recorderState.durationMillis / 1000)} 秒`
                : '可先录音，再手动整理转写'}
            </Text>
            {recordingMessage ? <Text style={styles.noticeText}>{recordingMessage}</Text> : null}
            {recordedUri ? <Text style={styles.previewMeta}>录音文件 {recordedUri}</Text> : null}
          </View>

          {result?.clarification ? (
            <View style={styles.notice}>
              <Text style={styles.noticeTitle}>需要补充</Text>
              <Text style={styles.noticeText}>{result.clarification}</Text>
            </View>
          ) : null}

          {needsSelection ? (
            <View style={styles.preview}>
              <Text style={styles.sectionTitle}>选择候选</Text>
              <View style={styles.candidateList}>
                {result?.candidates.map((item) => {
                  const selected = selectedCandidateId === item.id;
                  return (
                    <Pressable
                      key={item.id}
                      onPress={() => onChooseCandidate(item)}
                      style={[styles.candidateRow, selected && styles.candidateRowActive]}
                    >
                      <View style={styles.placeBody}>
                        <View style={styles.itemHeader}>
                          <Text style={styles.itemTitle}>{item.title}</Text>
                          <Text style={styles.itemKind}>
                            {item.type === 'todo' ? '待办' : '日历'}
                          </Text>
                        </View>
                        <Text style={styles.itemMeta}>{itemSummary(item)}</Text>
                      </View>
                      <Text style={styles.secondaryButtonText}>{selected ? '已选' : '选择'}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          ) : null}

          {!result?.write_request && result?.candidates.length ? (
            <View style={styles.preview}>
              <Text style={styles.sectionTitle}>查询结果</Text>
              <View style={styles.queryList}>
                {result.candidates.map((item) => (
                  <View key={item.id} style={styles.queryRow}>
                    <View style={styles.placeBody}>
                      <View style={styles.itemHeader}>
                        <Text style={styles.itemTitle}>{item.title}</Text>
                        <Text style={styles.itemKind}>
                          {item.type === 'todo' ? '待办' : '日历'}
                        </Text>
                      </View>
                      <Text style={styles.itemMeta}>{itemSummary(item)}</Text>
                    </View>
                    {item.reminders.length > 0 ? (
                      <View style={styles.badges}>
                        {item.reminders.slice(0, 2).map((reminder) => (
                          <View key={reminder.id} style={styles.badge}>
                            <Text style={styles.badgeText}>
                              {reminderLabel(reminder)} · {statusLabel(reminder.status)}
                            </Text>
                          </View>
                        ))}
                      </View>
                    ) : null}
                  </View>
                ))}
              </View>
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
                  style={[styles.primaryButton, (!canConfirm || busy) && styles.disabledButton]}
                  disabled={!canConfirm}
                >
                  <Text style={styles.primaryButtonText}>
                    {needsSelection && selectedCandidateId === null ? '先选候选' : '确认写入'}
                  </Text>
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

function EditSheet({
  busy,
  draft,
  item,
  onChangeDraft,
  onClose,
  onSubmit,
  visible,
}: {
  busy: boolean;
  draft: EditDraft;
  item: Item | null;
  onChangeDraft: (value: EditDraft) => void;
  onClose: () => void;
  onSubmit: () => void;
  visible: boolean;
}) {
  return (
    <Modal animationType="slide" visible={visible}>
      <View style={styles.modalRoot}>
        <ScrollView contentContainerStyle={styles.modalContent}>
          <View style={styles.topBar}>
            <View>
              <Text style={styles.kicker}>事项编辑</Text>
              <Text style={styles.title}>修改内容</Text>
            </View>
            <Pressable onPress={onClose} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>关闭</Text>
            </Pressable>
          </View>

          <View style={styles.sheetSection}>
            <Text style={styles.sectionTitle}>{item?.type === 'todo' ? '待办' : '日历'}</Text>
            <TextInput
              onChangeText={(value) => onChangeDraft({ ...draft, title: value })}
              placeholder="标题"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={draft.title}
            />
            <TextInput
              multiline
              onChangeText={(value) => onChangeDraft({ ...draft, description: value })}
              placeholder="备注"
              placeholderTextColor={colors.muted}
              style={styles.textArea}
              value={draft.description}
            />
            <TextInput
              onChangeText={(value) => onChangeDraft({ ...draft, place_text: value })}
              placeholder="地点"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={draft.place_text}
            />
            <TextInput
              onChangeText={(value) => onChangeDraft({ ...draft, start_at: value })}
              placeholder="开始时间"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={draft.start_at}
            />
            <TextInput
              onChangeText={(value) => onChangeDraft({ ...draft, end_at: value })}
              placeholder="结束时间"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={draft.end_at}
            />
            <TextInput
              onChangeText={(value) => onChangeDraft({ ...draft, due_at: value })}
              placeholder="截止时间"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={draft.due_at}
            />
            <Pressable
              onPress={onSubmit}
              style={[styles.primaryButton, busy && styles.disabledButton]}
            >
              <Text style={styles.primaryButtonText}>{busy ? '生成中' : '生成确认'}</Text>
            </Pressable>
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

function ReminderSheet({
  busy,
  draft,
  item,
  onChangeDraft,
  onClose,
  onSubmit,
  places,
  visible,
}: {
  busy: boolean;
  draft: ReminderDraft;
  item: Item | null;
  onChangeDraft: (value: ReminderDraft) => void;
  onClose: () => void;
  onSubmit: () => void;
  places: Place[];
  visible: boolean;
}) {
  return (
    <Modal animationType="slide" visible={visible}>
      <View style={styles.modalRoot}>
        <ScrollView contentContainerStyle={styles.modalContent}>
          <View style={styles.topBar}>
            <View>
              <Text style={styles.kicker}>添加提醒</Text>
              <Text style={styles.title}>{item?.title ?? '事项'}</Text>
            </View>
            <Pressable onPress={onClose} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>关闭</Text>
            </Pressable>
          </View>

          <View style={styles.sheetSection}>
            <View style={styles.priorityRow}>
              {(['time', 'enter_place', 'leave_place', 'return_to_place'] as const).map(
                (triggerType) => (
                  <Pressable
                    key={triggerType}
                    onPress={() =>
                      onChangeDraft({
                        ...draft,
                        place_id:
                          triggerType === 'time'
                            ? draft.place_id
                            : draft.place_id || places[0]?.id || '',
                        trigger_type: triggerType,
                      })
                    }
                    style={[
                      styles.priorityButton,
                      draft.trigger_type === triggerType && styles.priorityButtonActive,
                    ]}
                  >
                    <Text
                      style={[
                        styles.priorityButtonText,
                        draft.trigger_type === triggerType && styles.priorityButtonTextActive,
                      ]}
                    >
                      {triggerTypeLabel(triggerType)}
                    </Text>
                  </Pressable>
                ),
              )}
            </View>
            {draft.trigger_type === 'time' ? (
              <TextInput
                onChangeText={(value) => onChangeDraft({ ...draft, trigger_at: value })}
                placeholder="提醒时间"
                placeholderTextColor={colors.muted}
                style={styles.input}
                value={draft.trigger_at}
              />
            ) : (
              <View style={styles.placePicker}>
                {places.length === 0 ? (
                  <Text style={styles.emptyText}>先在地点库保存一个地点。</Text>
                ) : (
                  places.map((place) => (
                    <Pressable
                      key={place.id}
                      onPress={() => onChangeDraft({ ...draft, place_id: place.id })}
                      style={[
                        styles.placeChip,
                        draft.place_id === place.id && styles.placeChipActive,
                      ]}
                    >
                      <Text
                        style={[
                          styles.placeChipText,
                          draft.place_id === place.id && styles.placeChipTextActive,
                        ]}
                      >
                        {place.label}
                      </Text>
                    </Pressable>
                  ))
                )}
              </View>
            )}
            <View style={styles.priorityRow}>
              {(['low', 'normal', 'high'] as const).map((priority) => (
                <Pressable
                  key={priority}
                  onPress={() => onChangeDraft({ ...draft, priority })}
                  style={[
                    styles.priorityButton,
                    draft.priority === priority && styles.priorityButtonActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.priorityButtonText,
                      draft.priority === priority && styles.priorityButtonTextActive,
                    ]}
                  >
                    {priorityLabel(priority)}
                  </Text>
                </Pressable>
              ))}
            </View>
            <View style={styles.preview}>
              <Text style={styles.sectionTitle}>写入预览</Text>
              <Text style={styles.previewTitle}>{triggerTypeLabel(draft.trigger_type)}</Text>
              <Text style={styles.previewMeta}>
                {reminderDraftSummary(draft, places)} · {priorityLabel(draft.priority)}
              </Text>
            </View>
            <Pressable
              onPress={onSubmit}
              style={[styles.primaryButton, busy && styles.disabledButton]}
            >
              <Text style={styles.primaryButtonText}>{busy ? '生成中' : '生成确认'}</Text>
            </Pressable>
          </View>
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

function filterItemsByMode(items: Item[], mode: ViewMode) {
  const { end, start } = modeRange(mode, new Date());
  return items
    .filter((item) => {
      const anchor = itemAnchorDate(item);
      if (!anchor) {
        return item.type === 'todo';
      }
      return anchor >= start && anchor < end;
    })
    .sort((left, right) => {
      const leftAnchor = itemAnchorDate(left)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      const rightAnchor = itemAnchorDate(right)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      if (leftAnchor !== rightAnchor) {
        return leftAnchor - rightAnchor;
      }
      return left.title.localeCompare(right.title, 'zh-CN');
    });
}

function itemAnchorDate(item: Item) {
  const anchor =
    item.start_at ??
    item.due_at ??
    item.reminders.find((reminder) => reminder.trigger_at)?.trigger_at ??
    null;
  return anchor ? new Date(anchor) : null;
}

function modeRange(mode: ViewMode, now: Date) {
  if (mode === 'week') {
    const start = startOfWeek(now);
    return { end: addDays(start, 7), start };
  }
  if (mode === 'month') {
    const start = startOfMonth(now);
    return { end: addMonths(start, 1), start };
  }
  const start = startOfDay(now);
  return { end: addDays(start, 1), start };
}

function startOfDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function startOfWeek(value: Date) {
  const start = startOfDay(value);
  const day = start.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  start.setDate(start.getDate() + mondayOffset);
  return start;
}

function startOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function addMonths(value: Date, months: number) {
  const next = new Date(value);
  next.setMonth(next.getMonth() + months);
  return next;
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

async function scheduleLocalReminderNotification(reminder: Reminder, title: string) {
  if (reminder.trigger_type !== 'time' || !reminder.trigger_at) {
    throw new Error('Only time reminders can be scheduled locally.');
  }

  const triggerAt = new Date(reminder.trigger_at);
  if (Number.isNaN(triggerAt.getTime()) || triggerAt <= new Date()) {
    throw new Error('Reminder trigger time must be in the future.');
  }

  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted) {
    permission = await Notifications.requestPermissionsAsync();
  }
  if (!permission.granted) {
    throw new Error('Notification permission denied.');
  }

  return Notifications.scheduleNotificationAsync({
    content: {
      body: reminderLabel(reminder),
      data: { reminderId: reminder.id },
      title,
    },
    trigger: {
      date: triggerAt,
      type: Notifications.SchedulableTriggerInputTypes.DATE,
    },
  });
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
  if (operation === 'update_item') {
    return '编辑事项';
  }
  if (operation === 'create_reminder') {
    return '新增提醒';
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
  if (status === 'armed') {
    return '已布防';
  }
  if (status === 'delivered') {
    return '已提醒';
  }
  if (status === 'dismissed') {
    return '已确认';
  }
  if (status === 'snoozed') {
    return '已延后';
  }
  if (status === 'cancelled') {
    return '已取消';
  }
  if (status === 'failed') {
    return '失败';
  }
  return status;
}

function emptyEditDraft(): EditDraft {
  return {
    description: '',
    due_at: '',
    end_at: '',
    place_text: '',
    start_at: '',
    title: '',
  };
}

function defaultReminderDraft(placeId = ''): ReminderDraft {
  return {
    place_id: placeId,
    priority: 'normal',
    trigger_at: toInputDateTime(new Date(Date.now() + 60 * 60 * 1000).toISOString()),
    trigger_type: 'time',
  };
}

function triggerTypeLabel(triggerType: ReminderDraft['trigger_type']) {
  if (triggerType === 'time') {
    return '时间提醒';
  }
  if (triggerType === 'enter_place') {
    return '到达地点';
  }
  if (triggerType === 'leave_place') {
    return '离开地点';
  }
  return '回到地点';
}

function reminderDraftSummary(draft: ReminderDraft, places: Place[]) {
  if (draft.trigger_type === 'time') {
    return draft.trigger_at || '未设置';
  }
  const place = places.find((current) => current.id === draft.place_id);
  return place ? place.label : '未选择地点';
}

function reminderOverviewMeta(reminder: Reminder) {
  const fallback =
    reminder.fallback_status === 'not_required' ? '无兜底' : `兜底 ${reminder.fallback_status}`;
  return `${reminderLabel(reminder)} · 通知 ${reminder.local_registration_status} · ${fallback}`;
}

function resolvePlaceReminderAction(
  reminder: Reminder,
  placeById: Map<string, Place>,
  currentCoords: { latitude: number; longitude: number },
): ReminderAction | null {
  if (!reminder.place_id || reminder.status === 'delivered' || reminder.status === 'dismissed') {
    return null;
  }
  const place = placeById.get(reminder.place_id);
  if (!place?.latitude || !place.longitude) {
    return null;
  }

  const distanceMeters = distanceBetweenMeters(
    currentCoords.latitude,
    currentCoords.longitude,
    Number.parseFloat(place.latitude),
    Number.parseFloat(place.longitude),
  );
  if (!Number.isFinite(distanceMeters)) {
    return null;
  }
  const inside = distanceMeters <= place.radius_meters;

  if (reminder.trigger_type === 'enter_place' && inside) {
    return 'delivered';
  }
  if (reminder.trigger_type === 'leave_place' && !inside) {
    return 'delivered';
  }
  if (reminder.trigger_type === 'return_to_place') {
    if (reminder.status === 'pending' && !inside) {
      return 'armed';
    }
    if (reminder.status === 'armed' && inside) {
      return 'delivered';
    }
  }
  return null;
}

function distanceBetweenMeters(
  fromLatitude: number,
  fromLongitude: number,
  toLatitude: number,
  toLongitude: number,
) {
  const earthRadiusMeters = 6371000;
  const fromLat = degreesToRadians(fromLatitude);
  const toLat = degreesToRadians(toLatitude);
  const deltaLat = degreesToRadians(toLatitude - fromLatitude);
  const deltaLon = degreesToRadians(toLongitude - fromLongitude);
  const a =
    Math.sin(deltaLat / 2) * Math.sin(deltaLat / 2) +
    Math.cos(fromLat) * Math.cos(toLat) * Math.sin(deltaLon / 2) * Math.sin(deltaLon / 2);
  return earthRadiusMeters * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function degreesToRadians(value: number) {
  return (value * Math.PI) / 180;
}

function priorityLabel(priority: ReminderDraft['priority']) {
  if (priority === 'low') {
    return '低';
  }
  if (priority === 'high') {
    return '高';
  }
  return '普通';
}

function placeTypeLabel(placeType: Place['place_type']) {
  if (placeType === 'home') {
    return '家';
  }
  if (placeType === 'work') {
    return '公司';
  }
  if (placeType === 'temporary_parking') {
    return '停车';
  }
  return '自定义';
}

function weekdayLabel(weekday: number) {
  return ['一', '二', '三', '四', '五', '六', '日'][weekday - 1] ?? String(weekday);
}

function repeatPatternLabel(pattern: RepeatPattern) {
  if (pattern === 'daily') {
    return '每天';
  }
  if (pattern === 'weekdays') {
    return '工作日';
  }
  return '自定义周几';
}

function repeatRuleSummary(repeatRule: RepeatRule) {
  const pattern =
    repeatRule.pattern === 'custom_weekdays' && repeatRule.weekdays.length > 0
      ? repeatRule.weekdays.map((weekday) => `周${weekdayLabel(weekday)}`).join('、')
      : repeatPatternLabel(repeatRule.pattern);
  return repeatRule.time_of_day ? `${pattern} · ${repeatRule.time_of_day}` : pattern;
}

function seriesStatusLabel(status: RepeatSeriesStatus) {
  if (status === 'active') {
    return '启用';
  }
  if (status === 'paused') {
    return '暂停';
  }
  return '停止';
}

function outboxMessageSummary(message: OutboxMessage) {
  const payload = message.payload as Record<string, unknown>;
  if (typeof payload.operation === 'string') {
    return payload.operation;
  }
  if (typeof payload.event_type === 'string') {
    return payload.event_type;
  }
  if (typeof payload.type === 'string') {
    return payload.type;
  }
  return message.event_id.slice(0, 8);
}

function outboxMessageMeta(message: OutboxMessage) {
  return `${message.channel} · ${message.attempts} 次 · ${formatDate(message.created_at)}`;
}

function reminderActionSuccessLabel(action: ReminderAction) {
  if (action === 'armed') {
    return '提醒已布防';
  }
  if (action === 'registered') {
    return '提醒已注册';
  }
  if (action === 'delivered') {
    return '提醒已送达';
  }
  if (action === 'failed' || action === 'registration_failed' || action === 'local_unavailable') {
    return '提醒已标记失败';
  }
  if (action === 'snooze') {
    return '提醒已延后';
  }
  if (action === 'cancel') {
    return '提醒已取消';
  }
  return '提醒已确认';
}

async function loadDevicePermissions(): Promise<Record<DevicePermission, DevicePermissionState>> {
  const [microphone, notification, location] = await Promise.allSettled([
    getRecordingPermissionsAsync(),
    Notifications.getPermissionsAsync(),
    Location.getForegroundPermissionsAsync(),
  ]);

  return {
    location: permissionStateFromResult(location),
    microphone: permissionStateFromResult(microphone),
    notification: permissionStateFromResult(notification),
  };
}

function permissionStateFromResult(
  result: PromiseSettledResult<{ granted: boolean; status?: string }>,
): DevicePermissionState {
  if (result.status === 'rejected') {
    return 'unavailable';
  }
  if (result.value.granted) {
    return 'granted';
  }
  if (result.value.status === 'denied') {
    return 'denied';
  }
  if (result.value.status === 'undetermined') {
    return 'undetermined';
  }
  return 'unavailable';
}

function devicePermissionLabel(permission: DevicePermission) {
  if (permission === 'microphone') {
    return '麦克风';
  }
  if (permission === 'notification') {
    return '通知';
  }
  return '定位';
}

function devicePermissionStateLabel(state: DevicePermissionState) {
  if (state === 'granted') {
    return '已允许';
  }
  if (state === 'denied') {
    return '已拒绝';
  }
  if (state === 'undetermined') {
    return '未设置';
  }
  if (state === 'checking') {
    return '检查中';
  }
  return '不可用';
}

function narrowCandidatePayload(payload: Record<string, unknown>, candidate: Item) {
  const operations = Array.isArray(payload.operations) ? payload.operations : [];
  const selectedOperation = operations.find(
    (operation) =>
      operation &&
      typeof operation === 'object' &&
      'target_id' in operation &&
      (operation as { target_id?: unknown }).target_id === candidate.id,
  );
  if (!selectedOperation || typeof selectedOperation !== 'object') {
    throw new Error('candidate not found');
  }

  return {
    ...payload,
    candidates: [itemToCandidatePreview(candidate)],
    operations: [selectedOperation],
    target_id: candidate.id,
  };
}

function itemToCandidatePreview(item: Item) {
  return {
    description: item.description,
    due_at: item.due_at,
    end_at: item.end_at,
    id: item.id,
    place_text: item.place_text,
    start_at: item.start_at,
    status: item.status,
    title: item.title,
    type: item.type,
    version: item.version,
  };
}

function toInputDateTime(value: string | null) {
  return value ? value.slice(0, 16) : '';
}

function normalizeInputDateTime(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error('invalid datetime');
  }
  return parsed.toISOString();
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
  candidateList: {
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  candidateRow: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    padding: spacing.md,
  },
  candidateRowActive: {
    borderColor: colors.accent,
    borderWidth: 2,
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
  reminderActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  reminderDiagnostics: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  reminderControl: {
    gap: 6,
  },
  priorityButton: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    justifyContent: 'center',
    minHeight: 40,
  },
  priorityButtonActive: {
    backgroundColor: colors.text,
    borderColor: colors.text,
  },
  priorityButtonText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  priorityButtonTextActive: {
    color: colors.surface,
  },
  priorityRow: {
    flexDirection: 'row',
    gap: spacing.sm,
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
  permissionRow: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    padding: spacing.md,
  },
  permissionSection: {
    gap: spacing.sm,
  },
  placeBody: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  placeChip: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
  },
  placeChipActive: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  placeChipText: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '800',
  },
  placeChipTextActive: {
    color: colors.surface,
  },
  placePicker: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  queryList: {
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  queryRow: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.md,
  },
  placeList: {
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  placeMeta: {
    color: colors.muted,
    fontSize: 13,
  },
  placeRow: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    padding: spacing.md,
  },
  placeSection: {
    gap: spacing.md,
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
  repeatSection: {
    gap: spacing.md,
  },
  degradeSection: {
    gap: spacing.md,
  },
  reminderOverviewSection: {
    gap: spacing.md,
  },
  outboxSection: {
    gap: spacing.md,
  },
  rowActions: {
    alignItems: 'flex-end',
    gap: spacing.sm,
    justifyContent: 'center',
    padding: spacing.md,
  },
  tinyButton: {
    alignItems: 'center',
    backgroundColor: '#EAF1FF',
    borderRadius: 6,
    minWidth: 48,
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  tinyButtonDanger: {
    alignItems: 'center',
    backgroundColor: '#FFEDEE',
    borderRadius: 6,
    minWidth: 48,
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  tinyButtonDangerText: {
    color: '#B4232C',
    fontSize: 11,
    fontWeight: '900',
  },
  tinyButtonText: {
    color: colors.accent,
    fontSize: 11,
    fontWeight: '900',
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
