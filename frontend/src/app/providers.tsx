import { useMemo, type ReactNode } from 'react';
import { Platform, useWindowDimensions, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { OverlayProvider } from '@/app/overlay/OverlayProvider';
import { createReminderAlarmAdapter } from '@/app/integrations/reminderAlarmAdapter';
import { createScheduleConflictNotifier } from '@/app/integrations/scheduleConflictNotifier';
import { PowerSyncScheduleRepository } from '@/app/integrations/PowerSyncScheduleRepository';
import { SessionProvider, useSession } from '@/app/session/SessionProvider';
import type { DeviceIdStore } from '@/infrastructure/storage/deviceIdStore';
import {
  PowerSyncDevSync,
  usePowerSyncDatabase,
} from '@/infrastructure/powersync/PowerSyncDevSync';
import { ScheduleProvider, type ScheduleTransport } from '@/features/schedule';
import { AppDialogProvider, useAppDialog } from '@/shared/components/AppDialogProvider';

import { providerStyles as styles } from './providers.styles';

/** 将 session 注入 schedule，避免 feature 反向依赖 app。 */
function ScheduleSessionBridge({ children }: { children: ReactNode }) {
  const { client, connectionStatus, userId, sessionEpoch } = useSession();
  const { showNotice } = useAppDialog();
  const powerSyncDatabase = usePowerSyncDatabase();
  const alarmAdapter = useMemo(() => createReminderAlarmAdapter(showNotice), [showNotice]);
  const notifyConflicts = useMemo(() => createScheduleConflictNotifier(showNotice), [showNotice]);
  const repositoryFactory = useMemo(() => {
    if (!powerSyncDatabase || !userId) return undefined;
    return (transport: ScheduleTransport) =>
      new PowerSyncScheduleRepository(powerSyncDatabase, transport, userId);
  }, [powerSyncDatabase, userId]);
  return (
    <ScheduleProvider
      alarmAdapter={alarmAdapter}
      client={client}
      connectionStatus={connectionStatus}
      notifyConflicts={notifyConflicts}
      repositoryFactory={repositoryFactory}
      userId={userId}
      sessionEpoch={sessionEpoch}
    >
      {children}
    </ScheduleProvider>
  );
}

export function AppProviders({
  children,
  deviceIdStore,
}: {
  children: ReactNode;
  deviceIdStore?: DeviceIdStore;
}) {
  const { width } = useWindowDimensions();
  const tree = (
    <PowerSyncDevSync>
      <SessionProvider deviceIdStore={deviceIdStore}>
        <ScheduleSessionBridge>
          <OverlayProvider>{children}</OverlayProvider>
        </ScheduleSessionBridge>
      </SessionProvider>
    </PowerSyncDevSync>
  );

  if (Platform.OS !== 'web') {
    return (
      <SafeAreaProvider>
        <AppDialogProvider>{tree}</AppDialogProvider>
      </SafeAreaProvider>
    );
  }

  const compact = width < 480;
  return (
    <SafeAreaProvider>
      <AppDialogProvider>
        <View style={[styles.desktopCanvas, compact && styles.compactCanvas]}>
          <View style={[styles.webAppFrame, compact && styles.compactFrame]}>{tree}</View>
        </View>
      </AppDialogProvider>
    </SafeAreaProvider>
  );
}
