import { UpdateType } from '@powersync/common';
import { describe, expect, it, jest } from '@jest/globals';

import { TimeflowPowerSyncConnector } from '@/infrastructure/powersync/connector';

describe('TimeflowPowerSyncConnector', () => {
  it('uploads one PowerSync transaction and completes it after a successful response', async () => {
    const complete = jest.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const fetchMock = jest
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ results: [] }), { status: 200 }));
    const transaction = {
      transactionId: 12,
      crud: [
        {
          clientId: 48,
          id: 'schedule_dev_1',
          op: UpdateType.PUT,
          opData: { title: 'PowerSync 验证' },
        },
      ],
      complete,
    };
    const database = {
      getNextCrudTransaction: jest
        .fn<() => Promise<typeof transaction>>()
        .mockResolvedValue(transaction),
      getClientId: jest.fn<() => Promise<string>>().mockResolvedValue('client_dev'),
    };
    const connector = new TimeflowPowerSyncConnector({
      powerSyncEndpoint: 'https://powersync.example.test',
      apiBaseUrl: 'http://127.0.0.1:8000/api/v1',
      tokenProvider: async () => 'dev-token',
    });

    await connector.uploadData(database as never);

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/sync/push',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          operations: [
            {
              operation_id: 'client_dev:12:48',
              entity: 'schedules',
              entity_id: 'schedule_dev_1',
              operation: 'create',
              payload: { id: 'schedule_dev_1', title: 'PowerSync 验证' },
              base_version: null,
            },
          ],
        }),
      }),
    );
    expect(complete).toHaveBeenCalledTimes(1);
  });

  it('keeps the transaction queued when the upload endpoint fails', async () => {
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 503 }));
    const complete = jest.fn<() => Promise<void>>();
    const transaction = {
      transactionId: 1,
      crud: [],
      complete,
    };
    const database = {
      getNextCrudTransaction: jest
        .fn<() => Promise<typeof transaction>>()
        .mockResolvedValue(transaction),
      getClientId: jest.fn<() => Promise<string>>().mockResolvedValue('client_dev'),
    };
    const connector = new TimeflowPowerSyncConnector({
      powerSyncEndpoint: 'https://powersync.example.test',
      apiBaseUrl: 'http://127.0.0.1:8000/api/v1',
      tokenProvider: async () => null,
    });

    await expect(connector.uploadData(database as never)).rejects.toThrow(
      'PowerSync upload failed with HTTP 503',
    );
    expect(complete).not.toHaveBeenCalled();
  });
});
