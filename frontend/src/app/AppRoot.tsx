import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { accessAuth } from '../api/auth';
import type { AuthAccessResponse } from '../contracts/auth';
import { AssistantConversationService } from '../features/assistant/application/AssistantConversationService';
import { ExpoAudioCapture } from '../features/assistant/data/audio/ExpoAudioCapture';
import { ExpoAudioPlayback } from '../features/assistant/data/audio/ExpoAudioPlayback';
import { LocalScheduleWriter } from '../features/assistant/data/local/LocalScheduleWriter';
import { WebSocketVoiceTransport } from '../features/assistant/data/websocket/WebSocketVoiceTransport';
import { SqliteScheduleClientService } from '../features/schedule/application';
import { ScheduleLocalRepository } from '../features/schedule/data';
import { openTimeflowDatabase } from '../infrastructure/database';
import { ExpoLocationProvider } from '../infrastructure/location/ExpoLocationProvider';
import { HomeScreen } from '../screens/HomeScreen';
import { LoginScreen } from '../screens/LoginScreen';
import { colors, spacing } from '../shared/ui/theme';
import { AppProviders } from './AppProviders';

const WS_URL = (process.env.EXPO_PUBLIC_WS_URL ?? 'ws://127.0.0.1:8000/ws').replace(/\/$/, '');

export function AppRoot() {
  const [session, setSession] = useState<AuthAccessResponse>();
  // 登录流程目前不带 device_id；先按会话生成一个稳定 id，持久化设备标识不在本轮范围。
  const [deviceId] = useState(() => `device-${Math.random().toString(36).slice(2)}`);
  const [repository, setRepository] = useState<ScheduleLocalRepository>();
  const [databaseError, setDatabaseError] = useState<string | null>(null);
  const [databaseRetryToken, setDatabaseRetryToken] = useState(0);

  useEffect(() => {
    if (!session) return;
    let active = true;
    openTimeflowDatabase()
      .then((database) => {
        if (active) {
          setRepository(new ScheduleLocalRepository(database));
        }
      })
      .catch(() => {
        if (active) setDatabaseError('本地日程存储初始化失败');
      });
    return () => {
      active = false;
    };
  }, [databaseRetryToken, session]);

  const retryDatabase = useCallback(() => {
    setRepository(undefined);
    setDatabaseError(null);
    setDatabaseRetryToken((value) => value + 1);
  }, []);

  const scheduleService = useMemo(
    () => (repository ? new SqliteScheduleClientService(repository) : undefined),
    [repository],
  );

  const assistantApplication = useMemo(() => {
    if (!session || !repository) {
      return null;
    }
    return new AssistantConversationService(
      { accessToken: session.access_token, accountId: session.account_id, deviceId, wsUrl: WS_URL },
      {
        capture: new ExpoAudioCapture(),
        localScheduleWriter: new LocalScheduleWriter(repository),
        location: new ExpoLocationProvider(),
        playback: new ExpoAudioPlayback(),
        transport: new WebSocketVoiceTransport(),
      },
    );
  }, [session, deviceId, repository]);

  return (
    <AppProviders>
      {session ? (
        scheduleService && assistantApplication ? (
          <HomeScreen
            accountId={session.account_id}
            application={assistantApplication}
            scheduleService={scheduleService}
            timezone={Intl.DateTimeFormat().resolvedOptions().timeZone}
          />
        ) : (
          <View style={styles.authenticatedScreen}>
            <Text style={styles.title}>{databaseError ?? '正在准备日程'}</Text>
            <Text style={styles.account}>账号：{session.account_id}</Text>
            {databaseError ? (
              <Pressable accessibilityRole="button" onPress={retryDatabase} style={styles.retry}>
                <Text style={styles.retryText}>重试</Text>
              </Pressable>
            ) : null}
          </View>
        )
      ) : (
        <LoginScreen authAccess={accessAuth} onAuthenticated={setSession} />
      )}
    </AppProviders>
  );
}

const styles = StyleSheet.create({
  account: { color: colors.mutedText, fontSize: 16, marginTop: spacing.sm },
  authenticatedScreen: {
    alignItems: 'center',
    backgroundColor: colors.background,
    flex: 1,
    justifyContent: 'center',
    padding: spacing.xl,
  },
  retry: {
    backgroundColor: colors.text,
    borderRadius: 8,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  retryText: { color: colors.onPrimary, fontWeight: '700' },
  title: { color: colors.text, fontSize: 22, fontWeight: '700' },
});
