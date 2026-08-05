import { Schema, Table, column } from '@powersync/common';

/**
 * The first PowerSync spike mirrors the existing schedules table exactly.
 * Device-only alarm state is intentionally kept out of this schema.
 */
export const timeflowPowerSyncSchema = new Schema({
  schedules: new Table(
    {
      user_id: column.text,
      source_mode: column.text,
      schedule_type: column.text,
      status: column.text,
      title: column.text,
      notes: column.text,
      start_time: column.text,
      end_time: column.text,
      timezone: column.text,
      location_name: column.text,
      location_address: column.text,
      latitude: column.real,
      longitude: column.real,
      geofence_radius_meters: column.integer,
      geofence_armed: column.integer,
      time_remind_offset_minutes: column.integer,
      time_triggered_at: column.text,
      geo_triggered_at: column.text,
      system_schedule_ref_id: column.text,
      system_alarm_ref_id: column.text,
      created_at: column.text,
      updated_at: column.text,
    },
    {
      indexes: { by_start: ['start_time'] },
      trackPrevious: true,
    },
  ),
});
