import type {
  CommonPowerSyncDatabase,
  PowerSyncBackendConnector,
  PowerSyncCredentials,
} from '@powersync/common';
import { UpdateType } from '@powersync/common';

export type TimeflowPowerSyncConnectorOptions = {
  powerSyncEndpoint: string;
  apiBaseUrl: string;
  tokenProvider: () => Promise<string | null>;
};

type SyncOperation = {
  operation_id: string;
  entity: 'schedules';
  entity_id: string;
  operation: 'create' | 'update' | 'delete';
  payload: Record<string, unknown>;
  base_version?: number | null;
};

function operationType(updateType: UpdateType): SyncOperation['operation'] {
  if (updateType === UpdateType.PUT) return 'create';
  if (updateType === UpdateType.PATCH) return 'update';
  return 'delete';
}

/**
 * PowerSync connector for the local spike.
 *
 * Authentication and production idempotency are intentionally injected later
 * by the account/sync workstreams. The upload contract remains stable.
 */
export class TimeflowPowerSyncConnector implements PowerSyncBackendConnector {
  constructor(private readonly options: TimeflowPowerSyncConnectorOptions) {}

  async fetchCredentials(): Promise<PowerSyncCredentials | null> {
    const token = await this.options.tokenProvider();
    if (!token) return null;
    return { endpoint: this.options.powerSyncEndpoint, token };
  }

  async uploadData(database: CommonPowerSyncDatabase): Promise<void> {
    const transaction = await database.getNextCrudTransaction();
    if (!transaction) return;

    const clientId = await database.getClientId();
    const operations: SyncOperation[] = transaction.crud.map((entry) => ({
      operation_id: `${clientId}:${transaction.transactionId ?? 'none'}:${entry.clientId}`,
      entity: 'schedules',
      entity_id: entry.id,
      operation: operationType(entry.op),
      payload: { id: entry.id, ...(entry.opData ?? {}) },
      base_version:
        typeof entry.previousValues?.version === 'number' ? entry.previousValues.version : null,
    }));

    const token = await this.options.tokenProvider();
    const response = await fetch(`${this.options.apiBaseUrl}/sync/push`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ operations }),
    });

    if (!response.ok) {
      throw new Error(`PowerSync upload failed with HTTP ${response.status}`);
    }

    await response.json();
    await transaction.complete();
  }
}

export function createDevelopmentPowerSyncConnector(): TimeflowPowerSyncConnector {
  const powerSyncEndpoint = process.env.EXPO_PUBLIC_POWERSYNC_URL?.trim().replace(/\/+$/, '');
  const apiBaseUrl = process.env.EXPO_PUBLIC_API_URL?.trim().replace(/\/+$/, '');
  const token = process.env.EXPO_PUBLIC_POWERSYNC_TOKEN?.trim();
  if (!powerSyncEndpoint || !apiBaseUrl) {
    throw new Error(
      'Missing EXPO_PUBLIC_POWERSYNC_URL or EXPO_PUBLIC_API_URL for the PowerSync spike',
    );
  }
  return new TimeflowPowerSyncConnector({
    powerSyncEndpoint,
    apiBaseUrl,
    tokenProvider: async () => token || null,
  });
}
