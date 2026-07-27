import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { createItem, getHealth, listItems, type Item } from '../api/client';
import { colors, spacing } from '../constants/theme';

type ViewMode = 'today' | 'week' | 'month';
type ItemType = 'calendar_event' | 'todo';

export function HomeScreen() {
  const [healthState, setHealthState] = useState<'checking' | 'ok' | 'failed'>('checking');
  const [viewMode, setViewMode] = useState<ViewMode>('today');
  const [items, setItems] = useState<Item[]>([]);
  const [title, setTitle] = useState('');
  const [itemType, setItemType] = useState<ItemType>('todo');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

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
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.confirmation}>
          <Text style={styles.confirmationLabel}>Pending confirmation</Text>
          <Text style={styles.confirmationTitle}>Create todo: Pick up parcel</Text>
          <Text style={styles.itemMeta}>Reminder when arriving home</Text>
          <View style={styles.actions}>
            <Pressable style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>Cancel</Text>
            </Pressable>
            <Pressable style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Confirm</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>

      <Pressable style={styles.voiceButton}>
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
  checkbox: {
    borderColor: colors.border,
    borderRadius: 6,
    borderWidth: 2,
    height: 22,
    width: 22,
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
});
