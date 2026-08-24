package com.timeflow.alarm;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.os.Build;

import androidx.test.core.app.ApplicationProvider;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;

/** 覆盖 recordTtsDiagnostics()/getTtsDiagnostics() 的落盘/读回，不牵涉真实 TextToSpeech 引擎。 */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = Build.VERSION_CODES.UPSIDE_DOWN_CAKE)
public class AlarmNativeBridgeTest {

    @Test
    public void getTtsDiagnostics_returnsNullBeforeAnyRecordHasBeenMade() {
        Context context = ApplicationProvider.getApplicationContext();
        assertNull(AlarmNativeBridge.getTtsDiagnostics(context));
    }

    @Test
    public void recordTtsDiagnostics_roundTripsTheLatestResult() {
        Context context = ApplicationProvider.getApplicationContext();

        AlarmNativeBridge.recordTtsDiagnostics(context, false, -1, "init_failed", "alarm");
        AlarmNativeBridge.TtsDiagnostics first = AlarmNativeBridge.getTtsDiagnostics(context);
        assertEquals(false, first.ready);
        assertEquals(-1, first.statusCode);
        assertEquals("init_failed", first.detail);
        assertEquals("alarm", first.source);
        assertTrue(first.checkedAtMillis > 0);

        // 只关心"最近一次"——第二次记录应该整个覆盖掉第一次，不是追加。
        AlarmNativeBridge.recordTtsDiagnostics(context, true, 0, "ready", "manual");
        AlarmNativeBridge.TtsDiagnostics second = AlarmNativeBridge.getTtsDiagnostics(context);
        assertEquals(true, second.ready);
        assertEquals(0, second.statusCode);
        assertEquals("ready", second.detail);
        assertEquals("manual", second.source);
    }
}
