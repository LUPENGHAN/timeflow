import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { getHealth } from '../api/client';
import { colors, spacing } from '../constants/theme';

const todayItems = [
  { id: 'standup', time: '09:30', title: 'Project standup', meta: 'Calendar' },
  { id: 'gym', time: '18:00', title: 'Gym session', meta: 'Reminder 30m before' },
] as const;

const todos = [
  { id: 'milk', title: 'Buy milk', meta: 'Normal' },
  { id: 'parcel', title: 'Pick up parcel', meta: 'Arrive home' },
] as const;

export function HomeScreen() {
  const [healthState, setHealthState] = useState<'checking' | 'ok' | 'failed'>('checking');

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

    return () => {
      active = false;
    };
  }, []);

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

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Timeline</Text>
            <Text style={styles.count}>{todayItems.length}</Text>
          </View>
          {todayItems.map((item) => (
            <View key={item.id} style={styles.timelineRow}>
              <Text style={styles.time}>{item.time}</Text>
              <View style={styles.rowBody}>
                <Text style={styles.itemTitle}>{item.title}</Text>
                <Text style={styles.itemMeta}>{item.meta}</Text>
              </View>
            </View>
          ))}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Todos</Text>
            <Text style={styles.count}>{todos.length}</Text>
          </View>
          {todos.map((todo) => (
            <View key={todo.id} style={styles.todoRow}>
              <View style={styles.checkbox} />
              <View style={styles.rowBody}>
                <Text style={styles.itemTitle}>{todo.title}</Text>
                <Text style={styles.itemMeta}>{todo.meta}</Text>
              </View>
            </View>
          ))}
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
  eyebrow: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '600',
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
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
    backgroundColor: colors.accent,
    borderRadius: 8,
    minWidth: 92,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
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
    fontSize: 13,
    fontWeight: '800',
  },
});
