import { describe, expect, it, jest } from '@jest/globals';

import type { Schedule, WsJsonMessage } from '@/contracts';
import { PowerSyncScheduleRepository } from '@/app/integrations/PowerSyncScheduleRepository';
import type { ScheduleTransport } from '@/features/schedule';

const scheduleRow: Omit<Schedule, 'geofence_armed'> & { geofence_armed: number } = {
  id: 'schedule_1',
  user_id: 'user_1',
  source_mode: 'manual',
  schedule_type: 'time',
  status: 'scheduled',
  title: 'PowerSync read',
  notes: null,
  start_time: '2026-08-05T10:00:00+08:00',
  end_time: null,
  timezone: 'Asia/Shanghai',
  location_name: null,
  location_address: null,
  latitude: null,
  longitude: null,
  geofence_radius_meters: 100,
  geofence_armed: 1,
  time_remind_offset_minutes: 0,
  time_triggered_at: null,
  geo_triggered_at: null,
  system_schedule_ref_id: null,
  system_alarm_ref_id: null,
  created_at: '2026-08-05T01:00:00Z',
  updated_at: '2026-08-05T01:00:00Z',
};

function createTransport() {
  const request = jest.fn(
    async (
      message: WsJsonMessage & { request_id: string },
      _isMatch?: (response: WsJsonMessage) => boolean,
    ) => {
      if (message.type === 'schedule.upsert.command') {
        return {
          type: 'schedule.upsert.result',
          request_id: message.request_id,
          ok: true,
          payload: {
            schedule_id: 'schedule_1',
            schedule_type: 'time',
            status: 'scheduled',
            conflicts: [],
            geofence_armed: true,
          },
        };
      }
      throw new Error(`Unexpected message: ${message.type}`);
    },
  );
  return {
    transport: {
      onMessage: () => () => undefined,
      request,
      sendJson: () => undefined,
    } as unknown as ScheduleTransport,
    request,
  };
}

describe('PowerSyncScheduleRepository', () => {
  it('reads the current user schedules from PowerSync and maps SQLite booleans', async () => {
    const getAll = jest.fn(async () => [scheduleRow]);
    const database = { getAll, watch: jest.fn() };
    const { transport } = createTransport();
    const repository = new PowerSyncScheduleRepository(database as never, transport, 'user_1');

    await expect(repository.list({ status: null, include_deleted: false })).resolves.toEqual([
      { ...scheduleRow, geofence_armed: true },
    ]);
    expect(getAll).toHaveBeenCalledWith(
      "SELECT * FROM schedules WHERE user_id = ? AND status != 'deleted'",
      ['user_1'],
    );

    repository.dispose();
  });

  it('publishes PowerSync changes as schedule snapshots and aborts the watch', async () => {
    const watch = jest.fn();
    const database = { getAll: jest.fn(async () => []), watch };
    const { transport } = createTransport();
    const repository = new PowerSyncScheduleRepository(database as never, transport, 'user_1');
    await repository.list({ status: 'scheduled', include_deleted: true });
    const listener = jest.fn();

    const unsubscribe = repository.subscribe(listener);
    const [, parameters, handler, options] = watch.mock.calls[0] as unknown as [
      string,
      string[],
      { onResult: (result: { array: unknown[] }) => void },
      { signal: AbortSignal; triggerImmediate: boolean },
    ];
    handler.onResult({ array: [scheduleRow] });

    expect(parameters).toEqual(['user_1', 'scheduled']);
    expect(options.triggerImmediate).toBe(true);
    expect(listener).toHaveBeenCalledWith({
      type: 'schedule.snapshot',
      schedules: [{ ...scheduleRow, geofence_armed: true }],
    });
    unsubscribe();
    expect(options.signal.aborted).toBe(true);

    repository.dispose();
  });

  it('keeps schedule writes on the WebSocket repository', async () => {
    const database = { getAll: jest.fn(async () => []), watch: jest.fn() };
    const { transport, request } = createTransport();
    const repository = new PowerSyncScheduleRepository(database as never, transport, 'user_1');
    const command = {
      type: 'schedule.upsert.command',
      request_id: 'req_1',
      payload: {
        source_mode: 'manual',
        schedule_type: 'time',
        title: 'Write over WebSocket',
        start_time: '2026-08-05T10:00:00+08:00',
      },
    } as const;

    await expect(repository.upsert(command)).resolves.toMatchObject({ ok: true });
    expect(request).toHaveBeenCalledWith(command, expect.any(Function));

    repository.dispose();
  });
});
