# MVP Demo Script

## Start

Backend:

```bash
cd backend
python -m uvicorn timeapp.main:app --reload
```

Frontend:

```bash
cd frontend
npm run start
```

Set `EXPO_PUBLIC_API_URL` when using a device that cannot reach `127.0.0.1`.

## Stories

1. Health check
   - Open the app.
   - Confirm the header status changes to `Connected`.
   - Open `/docs` and confirm Swagger loads.

2. Manual item create
   - Add a `Todo` from `Quick add`.
   - Confirm it appears in `Todos`.
   - Add a `Calendar` item.
   - Confirm it appears in `Timeline`.

3. Write request gate
   - Tap `Done` on a todo.
   - Confirm the `Pending confirmation` card appears.
   - Tap `Cancel` and verify the item is unchanged.
   - Tap `Done` again, then `Confirm`; verify the status changes to completed.

4. Mock voice create
   - Tap `Voice`.
   - Submit `到家后提醒我取快递`.
   - Confirm a write request preview appears.
   - Tap `Confirm`.
   - Verify the todo appears with an `enter_place` reminder badge.

5. Mock voice update candidate
   - Create a calendar item named `明天会议`.
   - Submit `把明天会议改到四点`.
   - Verify the candidate list and write request preview appear.

6. Place skeleton
   - Save `Home` as a `home` place.
   - Verify it appears in the `Places` section.

7. Repeat skeleton
   - Save `weekdays` as a repeat rule.
   - Verify it appears in the `Repeat` section.

8. Sync skeleton
   - Call `GET /api/v1/events`.
   - Open `WS /api/v1/ws`.
   - Send `{"type":"sync.request","after":0}` and verify a `sync.response`.
   - Disconnect and reconnect, then confirm the client replays `sync.request` automatically.

9. Offline quick add
   - Turn off network access.
   - Add a todo from `Quick add`.
   - Confirm it enters the offline queue.
   - Restore network and confirm it is replayed.

## Known Risks

- Voice is mock transcript input; real ASR/audio recording is not wired.
- Local notifications, true location permissions and geofencing are still local-device only.
- Persistence-backed repositories are not active; the MVP runtime uses process-local memory.
- Cloud fallback adapters are skeleton-only and do not send SMS, email or calls.
- WS reconnect/backfill, local cache, offline quick add queue, and Swagger entrypoint are wired.

