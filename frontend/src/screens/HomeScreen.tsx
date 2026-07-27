import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  confirmWriteRequest,
  createItem,
  createPlace,
  createWriteRequest,
  createVoiceCommand,
  getHealth,
  listItems,
  listPlaces,
  rejectWriteRequest,
  type Item,
  type Place,
  type VoiceCommandResult,
} from '../api/client';
import { colors, spacing } from '../constants/theme';

type ViewMode = 'today' | 'week' | 'month';
type ItemType = 'calendar_event' | 'todo';

export function HomeScreen() {
  const [healthState, setHealthState] = useState<'checking' | 'ok' | 'failed'>('checking');
  const [viewMode, setViewMode] = useState<ViewMode>('today');
  const [items, setItems] = useState<Item[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [title, setTitle] = useState('');
  const [itemType, setItemType] = useState<ItemType>('todo');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('到家后提醒我取快递');
  const [voiceSubmitting, setVoiceSubmitting] = useState(false);
  const [voiceResult, setVoiceResult] = useState<VoiceCommandResult | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<string | null>(null);
  const [selectedVoiceCandidateId, setSelectedVoiceCandidateId] = useState<string | null>(null);
  const [pendingWriteRequest, setPendingWriteRequest] = useState<{
    id: string;
    candidate_payload: Record<string, unknown>;
  } | null>(null);
  const [pendingWriteLabel, setPendingWriteLabel] = useState<string | null>(null);
  const [placeLabel, setPlaceLabel] = useState('');
  const [placeType, setPlaceType] = useState<Place['place_type']>('home');
  const [placeSubmitting, setPlaceSubmitting] = useState(false);

  useEffect(() => {
    let active = true;

    getHealth()
      .then(() => {
        if (active) {
          setHealthState('ok');
        }
      })
      .catch(() => {
        if (active) {
          setHealthState('failed');
        }
      });

    listItems()
      .then((response) => {
        if (active) {
          setItems(response);
        }
      })
      .catch(() => {
        if (active) {
          setBanner('Failed to load items');
        }
      });

    listPlaces()
      .then((response) => {
        if (active) {
          setPlaces(response);
        }
      })
      .catch(() => {
        if (active) {
          setPlaces([]);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const timelineItems = useMemo(
    () => items.filter((item) => item.type === 'calendar_event'),
    [items],
  );
  const todoItems = useMemo(() => items.filter((item) => item.type === 'todo'), [items]);

  async function handleCreateItem() {
    if (!title.trim() || submitting) {
      return;
    }

    const optimisticItem: Item = {
      id: `local-${Date.now()}`,
      type: itemType,
      title: title.trim(),
      description: description.trim() || null,
      status: 'active',
      start_at: null,
      end_at: null,
      due_at: null,
      place_text: null,
      reminders: [],
    };

    const previousItems = items;
    setSubmitting(true);
    setBanner(null);
    setItems([optimisticItem, ...previousItems]);

    try {
      await createItem({
        type: itemType,
        title: title.trim(),
        description: description.trim() || null,
      });
      const refreshed = await listItems();
      setItems(refreshed);
      setTitle('');
      setDescription('');
      setBanner('Item saved');
    } catch {
      setItems(previousItems);
      setBanner('Create failed');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreatePlace() {
    if (!placeLabel.trim() || placeSubmitting) {
      return;
    }

    setPlaceSubmitting(true);
    try {
      const result = await createPlace({
        label: placeLabel.trim(),
        place_type: placeType,
      });
      setPlaces((current) => [result.place, ...current]);
      setPlaceLabel('');
      setBanner('Place saved');
    } catch {
      setBanner('Place save failed');
    } finally {
      setPlaceSubmitting(false);
    }
  }

  async function handlePrepareItemAction(item: Item, operation: 'complete_item' | 'delete_item') {
    const label = operation === 'complete_item' ? 'Complete item' : 'Delete item';
    setBanner(null);
    try {
      const result = await createWriteRequest({
        source_command_id: `manual-${item.id}-${operation}`,
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
          source_text: label,
          target_id: item.id,
        },
      });
      setPendingWriteRequest({
        candidate_payload: result.write_request.candidate_payload,
        id: result.write_request.id,
      });
      setPendingWriteLabel(`${label}: ${item.title}`);
      setBanner(null);
    } catch {
      setBanner('Failed to prepare write request');
    }
  }

  async function refreshItems() {
    const refreshed = await listItems();
    setItems(refreshed);
  }

  async function handleSubmitVoice() {
    if (!voiceTranscript.trim() || voiceSubmitting) {
      return;
    }

    setVoiceSubmitting(true);
    setVoiceStatus(null);
    try {
      const result = await createVoiceCommand(voiceTranscript.trim());
      setVoiceResult(result);
      setSelectedVoiceCandidateId(null);
      setVoiceStatus(result.write_request ? 'Write request created' : 'No write requested');
    } catch {
      setVoiceStatus('Voice command failed');
    } finally {
      setVoiceSubmitting(false);
    }
  }

  async function handleConfirmVoice() {
    const writeRequestId = voiceResult?.write_request?.id;
    if (!writeRequestId || voiceSubmitting) {
      return;
    }

    setVoiceSubmitting(true);
    try {
      await confirmWriteRequest(writeRequestId);
      await refreshItems();
      setVoiceStatus('Write request applied');
    } catch {
      setVoiceStatus('Confirm failed');
    } finally {
      setVoiceSubmitting(false);
    }
  }

  async function handleRejectVoice() {
    const writeRequestId = voiceResult?.write_request?.id;
    if (!writeRequestId || voiceSubmitting) {
      return;
    }

    setVoiceSubmitting(true);
    try {
      await rejectWriteRequest(writeRequestId);
      setVoiceStatus('Write request cancelled');
    } catch {
      setVoiceStatus('Cancel failed');
    } finally {
      setVoiceSubmitting(false);
    }
  }

  async function handleConfirmPendingWriteRequest() {
    if (!pendingWriteRequest) {
      return;
    }

    try {
      await confirmWriteRequest(pendingWriteRequest.id);
      await refreshItems();
      setBanner('Item updated');
      setPendingWriteRequest(null);
      setPendingWriteLabel(null);
    } catch {
      setBanner('Confirm failed');
    }
  }

  async function handleRejectPendingWriteRequest() {
    if (!pendingWriteRequest) {
      return;
    }

    try {
      await rejectWriteRequest(pendingWriteRequest.id);
      setPendingWriteRequest(null);
      setPendingWriteLabel(null);
      setBanner('Action cancelled');
    } catch {
      setBanner('Cancel failed');
    }
  }

  return (
    <View style={styles.root}>
      <StatusBar style="auto" />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>Today</Text>
            <Text style={styles.title}>Timeflow</Text>
          </View>
          <Pressable style={styles.syncButton}>
            <Text style={styles.syncButtonText}>
              {healthState === 'ok'
                ? 'Connected'
                : healthState === 'failed'
                  ? 'Offline'
                  : 'Checking'}
            </Text>
          </Pressable>
        </View>
        <Text style={styles.connectionStatus}>
          {healthState === 'ok'
            ? 'Backend health check passed'
            : healthState === 'failed'
              ? 'Backend health check failed'
              : 'Checking backend health'}
        </Text>
        {banner ? <Text style={styles.banner}>{banner}</Text> : null}

        <View style={styles.segmented}>
          {(['today', 'week', 'month'] as const).map((mode) => (
            <Pressable
              key={mode}
              onPress={() => setViewMode(mode)}
              style={[styles.segment, viewMode === mode && styles.segmentActive]}
            >
              <Text style={[styles.segmentText, viewMode === mode && styles.segmentTextActive]}>
                {mode}
              </Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Quick add</Text>
            <Text style={styles.count}>{items.length}</Text>
          </View>
          <View style={styles.form}>
            <View style={styles.segmentedCompact}>
              {(['todo', 'calendar_event'] as const).map((type) => (
                <Pressable
                  key={type}
                  onPress={() => setItemType(type)}
                  style={[styles.segment, itemType === type && styles.segmentActive]}
                >
                  <Text style={[styles.segmentText, itemType === type && styles.segmentTextActive]}>
                    {type === 'todo' ? 'Todo' : 'Calendar'}
                  </Text>
                </Pressable>
              ))}
            </View>
            <TextInput
              value={title}
              onChangeText={setTitle}
              placeholder="New item title"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              value={description}
              onChangeText={setDescription}
              placeholder="Description"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <Pressable
              onPress={handleCreateItem}
              style={[styles.primaryButton, submitting && styles.primaryButtonDisabled]}
            >
              <Text style={styles.primaryButtonText}>{submitting ? 'Saving' : 'Save'}</Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Places</Text>
            <Text style={styles.count}>{places.length}</Text>
          </View>
          <View style={styles.form}>
            <View style={styles.segmentedCompact}>
              {(['home', 'work', 'custom', 'temporary_parking'] as const).map((type) => (
                <Pressable
                  key={type}
                  onPress={() => setPlaceType(type)}
                  style={[styles.segment, placeType === type && styles.segmentActive]}
                >
                  <Text
                    style={[styles.segmentText, placeType === type && styles.segmentTextActive]}
                  >
                    {type.replace('_', ' ')}
                  </Text>
                </Pressable>
              ))}
            </View>
            <TextInput
              value={placeLabel}
              onChangeText={setPlaceLabel}
              placeholder="Place label"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <Pressable
              onPress={handleCreatePlace}
              style={[styles.primaryButton, placeSubmitting && styles.primaryButtonDisabled]}
            >
              <Text style={styles.primaryButtonText}>
                {placeSubmitting ? 'Saving' : 'Save place'}
              </Text>
            </Pressable>
          </View>
          {places.length === 0 ? (
            <Text style={styles.emptyState}>No places yet.</Text>
          ) : (
            places.map((place) => (
              <View key={place.id} style={styles.timelineRow}>
                <Text style={styles.time}>{place.place_type}</Text>
                <View style={styles.rowBody}>
                  <Text style={styles.itemTitle}>{place.label}</Text>
                  <Text style={styles.itemMeta}>{place.radius_meters}m radius</Text>
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Timeline</Text>
            <Text style={styles.count}>{timelineItems.length}</Text>
          </View>
          {timelineItems.length === 0 ? (
            <Text style={styles.emptyState}>No calendar items yet.</Text>
          ) : (
            timelineItems.map((item, index) => (
              <View key={item.id} style={styles.timelineRow}>
                <Text style={styles.time}>{`0${index + 9}:00`.slice(-5)}</Text>
                <View style={styles.rowBody}>
                  <Text style={styles.itemTitle}>{item.title}</Text>
                  <Text style={styles.itemMeta}>{item.description ?? 'Calendar'}</Text>
                  <View style={styles.badgeRow}>
                    {item.reminders.map((reminder) => (
                      <View key={reminder.id} style={styles.badge}>
                        <Text style={styles.badgeText}>{reminder.trigger_type}</Text>
                      </View>
                    ))}
                  </View>
                </View>
                <View style={styles.inlineActions}>
                  <Pressable
                    onPress={() => handlePrepareItemAction(item, 'delete_item')}
                    style={styles.inlineActionButton}
                  >
                    <Text style={styles.inlineActionText}>Delete</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Todos</Text>
            <Text style={styles.count}>{todoItems.length}</Text>
          </View>
          {todoItems.length === 0 ? (
            <Text style={styles.emptyState}>No todos yet.</Text>
          ) : (
            todoItems.map((todo) => (
              <View key={todo.id} style={styles.todoRow}>
                <View style={styles.checkbox} />
                <View style={styles.rowBody}>
                  <Text style={styles.itemTitle}>{todo.title}</Text>
                  <Text style={styles.itemMeta}>{todo.description ?? 'Normal'}</Text>
                  <View style={styles.badgeRow}>
                    {todo.reminders.map((reminder) => (
                      <View key={reminder.id} style={styles.badge}>
                        <Text style={styles.badgeText}>{reminder.trigger_type}</Text>
                      </View>
                    ))}
                  </View>
                </View>
                <View style={styles.inlineActions}>
                  <Pressable
                    onPress={() => handlePrepareItemAction(todo, 'complete_item')}
                    style={styles.inlineActionButton}
                  >
                    <Text style={styles.inlineActionText}>Done</Text>
                  </Pressable>
                  <Pressable
                    onPress={() => handlePrepareItemAction(todo, 'delete_item')}
                    style={styles.inlineActionButton}
                  >
                    <Text style={styles.inlineActionText}>Delete</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.confirmation}>
          <Text style={styles.confirmationLabel}>Pending confirmation</Text>
          <Text style={styles.confirmationTitle}>
            {pendingWriteLabel ?? 'Create todo: Pick up parcel'}
          </Text>
          <Text style={styles.itemMeta}>
            {pendingWriteRequest
              ? String(pendingWriteRequest.candidate_payload.operation ?? 'pending')
              : 'Reminder when arriving home'}
          </Text>
          <View style={styles.actions}>
            <Pressable onPress={handleRejectPendingWriteRequest} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>Cancel</Text>
            </Pressable>
            <Pressable onPress={handleConfirmPendingWriteRequest} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Confirm</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>

      <Modal animationType="slide" visible={voiceOpen}>
        <View style={styles.modalRoot}>
          <ScrollView contentContainerStyle={styles.modalContent}>
            <View style={styles.header}>
              <View>
                <Text style={styles.eyebrow}>Mock voice</Text>
                <Text style={styles.sectionTitle}>Voice command</Text>
              </View>
              <Pressable
                onPress={() => {
                  setVoiceOpen(false);
                }}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>Close</Text>
              </Pressable>
            </View>

            <View style={styles.voiceCard}>
              <Text style={styles.confirmationLabel}>RecordingCard</Text>
              <TextInput
                value={voiceTranscript}
                onChangeText={setVoiceTranscript}
                placeholder="Speak or type a mock transcript"
                placeholderTextColor={colors.muted}
                multiline
                style={styles.textArea}
              />
              <Pressable
                onPress={handleSubmitVoice}
                style={[styles.primaryButton, voiceSubmitting && styles.primaryButtonDisabled]}
              >
                <Text style={styles.primaryButtonText}>
                  {voiceSubmitting ? 'Parsing' : 'Send mock voice'}
                </Text>
              </Pressable>
            </View>

            <View style={styles.voiceCard}>
              <Text style={styles.confirmationLabel}>TranscriptCard</Text>
              <Text style={styles.cardText}>{voiceTranscript || 'No transcript yet'}</Text>
            </View>

            {voiceResult?.clarification ? (
              <View style={styles.voiceCard}>
                <Text style={styles.confirmationLabel}>ClarificationCard</Text>
                <Text style={styles.cardText}>{voiceResult.clarification}</Text>
              </View>
            ) : null}

            {voiceResult?.candidates?.length ? (
              <View style={styles.voiceCard}>
                <Text style={styles.confirmationLabel}>CandidateListCard</Text>
                <View style={styles.candidateList}>
                  {voiceResult.candidates.map((candidate) => (
                    <Pressable
                      key={candidate.id}
                      onPress={() => {
                        setSelectedVoiceCandidateId(candidate.id);
                        setVoiceStatus(`Selected ${candidate.title}`);
                      }}
                      style={[
                        styles.candidateRow,
                        selectedVoiceCandidateId === candidate.id && styles.candidateRowActive,
                      ]}
                    >
                      <Text style={styles.itemTitle}>{candidate.title}</Text>
                      <Text style={styles.itemMeta}>{candidate.type}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}

            {voiceResult?.write_request ? (
              <View style={styles.voiceCard}>
                <Text style={styles.confirmationLabel}>WriteRequestPreviewCard</Text>
                <Text style={styles.codeText}>
                  {JSON.stringify(voiceResult.write_request.candidate_payload, null, 2)}
                </Text>
                <View style={styles.actions}>
                  <Pressable onPress={handleRejectVoice} style={styles.secondaryButton}>
                    <Text style={styles.secondaryButtonText}>Cancel</Text>
                  </Pressable>
                  <Pressable
                    onPress={handleConfirmVoice}
                    style={[styles.primaryButton, voiceSubmitting && styles.primaryButtonDisabled]}
                  >
                    <Text style={styles.primaryButtonText}>Confirm</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}

            <View style={styles.voiceCard}>
              <Text style={styles.confirmationLabel}>ResultCard</Text>
              <Text style={styles.cardText}>{voiceStatus ?? 'Waiting for voice input'}</Text>
            </View>
          </ScrollView>
        </View>
      </Modal>

      <Pressable onPress={() => setVoiceOpen(true)} style={styles.voiceButton}>
        <Text style={styles.voiceButtonText}>Voice</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'flex-end',
    marginTop: spacing.md,
  },
  banner: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: '600',
    marginTop: -spacing.sm,
  },
  badge: {
    backgroundColor: colors.background,
    borderRadius: 999,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  badgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  badgeText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  checkbox: {
    borderColor: colors.border,
    borderRadius: 6,
    borderWidth: 2,
    height: 22,
    width: 22,
  },
  cardText: {
    color: colors.text,
    fontSize: 15,
    marginTop: spacing.sm,
  },
  candidateList: {
    gap: spacing.sm,
  },
  candidateRow: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    padding: spacing.md,
  },
  candidateRowActive: {
    borderColor: colors.accent,
  },
  codeText: {
    backgroundColor: colors.background,
    borderRadius: 8,
    color: colors.text,
    fontSize: 12,
    marginTop: spacing.sm,
    padding: spacing.sm,
  },
  confirmation: {
    backgroundColor: colors.surface,
    borderColor: colors.warning,
    borderRadius: 8,
    borderWidth: 1,
    padding: spacing.md,
  },
  confirmationLabel: {
    color: colors.warning,
    fontSize: 12,
    fontWeight: '700',
  },
  confirmationTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
    marginTop: spacing.sm,
  },
  content: {
    gap: spacing.lg,
    padding: spacing.lg,
    paddingBottom: 112,
    paddingTop: 72,
  },
  count: {
    color: colors.muted,
    fontSize: 14,
  },
  connectionStatus: {
    color: colors.muted,
    fontSize: 13,
    marginTop: -spacing.sm,
  },
  emptyState: {
    color: colors.muted,
    fontSize: 13,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  eyebrow: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '600',
  },
  form: {
    gap: spacing.sm,
    padding: spacing.md,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  input: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    color: colors.text,
    fontSize: 15,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  inlineActionButton: {
    borderColor: colors.border,
    borderRadius: 6,
    borderWidth: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
  },
  inlineActionText: {
    color: colors.text,
    fontSize: 12,
    fontWeight: '600',
  },
  inlineActions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  itemMeta: {
    color: colors.muted,
    fontSize: 13,
    marginTop: spacing.xs,
  },
  itemTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '600',
  },
  modalContent: {
    gap: spacing.md,
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    paddingTop: 64,
  },
  modalRoot: {
    backgroundColor: colors.background,
    flex: 1,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: 8,
    minWidth: 92,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  primaryButtonDisabled: {
    opacity: 0.7,
  },
  primaryButtonText: {
    color: colors.surface,
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
  root: {
    backgroundColor: colors.background,
    flex: 1,
  },
  rowBody: {
    flex: 1,
  },
  secondaryButton: {
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    minWidth: 92,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  secondaryButtonText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
  section: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
  },
  sectionHeader: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: spacing.md,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '700',
  },
  segment: {
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  segmentActive: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  segmented: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  segmentedCompact: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  segmentText: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  segmentTextActive: {
    color: colors.surface,
  },
  syncButton: {
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  syncButtonText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  time: {
    color: colors.muted,
    fontSize: 14,
    width: 56,
  },
  timelineRow: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    minHeight: 72,
    padding: spacing.md,
  },
  title: {
    color: colors.text,
    fontSize: 32,
    fontWeight: '800',
  },
  todoRow: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    minHeight: 68,
    padding: spacing.md,
  },
  voiceButton: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: 36,
    bottom: 28,
    height: 72,
    justifyContent: 'center',
    left: '50%',
    marginLeft: -36,
    position: 'absolute',
    width: 72,
  },
  voiceButtonText: {
    color: colors.surface,
    fontSize: 14,
    fontWeight: '700',
  },
  voiceCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.md,
  },
  textArea: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    color: colors.text,
    fontSize: 15,
    minHeight: 96,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    textAlignVertical: 'top',
  },
});
