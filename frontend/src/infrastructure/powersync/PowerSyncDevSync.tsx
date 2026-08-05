import { Platform } from 'react-native';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

import type { CommonPowerSyncDatabase } from '@powersync/common';

const UPLOAD_SMOKE_ID = 'powersync_live_upload_test';
const PowerSyncDatabaseContext = createContext<CommonPowerSyncDatabase | null>(null);

export function usePowerSyncDatabase(): CommonPowerSyncDatabase | null {
  return useContext(PowerSyncDatabaseContext);
}

async function queueDevelopmentUploadSmoke(database: CommonPowerSyncDatabase): Promise<void> {
  if (process.env.EXPO_PUBLIC_POWERSYNC_UPLOAD_SMOKE !== 'true') return;

  const now = new Date().toISOString();
  await database.execute(
    `INSERT OR IGNORE INTO schedules (
      id, user_id, source_mode, schedule_type, status, title, start_time,
      timezone, geofence_radius_meters, geofence_armed,
      time_remind_offset_minutes, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      UPLOAD_SMOKE_ID,
      'default_user',
      'manual',
      'time',
      'scheduled',
      'PowerSync 真机上行测试',
      now,
      'UTC',
      100,
      0,
      0,
      now,
      now,
    ],
  );
  console.warn('[PowerSync] upload smoke queued', { id: UPLOAD_SMOKE_ID });
}

/**
 * Starts the PowerSync database only when explicitly enabled. The dynamic
 * imports keep the native SQLite module out of web and Jest startup paths.
 */
export function PowerSyncDevSync({ children }: { children: ReactNode }) {
  const databaseRef = useRef<CommonPowerSyncDatabase | null>(null);
  const [database, setDatabase] = useState<CommonPowerSyncDatabase | null>(null);

  useEffect(() => {
    if (Platform.OS === 'web' || process.env.EXPO_PUBLIC_POWERSYNC_ENABLED !== 'true') {
      return;
    }

    let cancelled = false;
    void Promise.all([import('./connector'), import('./database')])
      .then(
        async ([{ createDevelopmentPowerSyncConnector }, { createTimeflowPowerSyncDatabase }]) => {
          const database = createTimeflowPowerSyncDatabase();
          if (cancelled) {
            await database.close();
            return;
          }
          databaseRef.current = database;
          await database.connect(createDevelopmentPowerSyncConnector());
          if (cancelled) return;
          setDatabase(database);
          await queueDevelopmentUploadSmoke(database);
        },
      )
      .catch((error: unknown) => {
        if (!cancelled) {
          console.warn('[PowerSync] development sync failed to start', error);
        }
      });

    return () => {
      cancelled = true;
      const database = databaseRef.current;
      databaseRef.current = null;
      if (database) {
        void database.close();
      }
    };
  }, []);

  return (
    <PowerSyncDatabaseContext.Provider value={database}>
      {children}
    </PowerSyncDatabaseContext.Provider>
  );
}
