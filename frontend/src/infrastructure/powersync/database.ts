import { PowerSyncDatabase } from '@powersync/react-native';

import { timeflowPowerSyncSchema } from './schema';

export function createTimeflowPowerSyncDatabase(dbFilename = 'timeflow.db') {
  return new PowerSyncDatabase({
    schema: timeflowPowerSyncSchema,
    database: { dbFilename },
  });
}
