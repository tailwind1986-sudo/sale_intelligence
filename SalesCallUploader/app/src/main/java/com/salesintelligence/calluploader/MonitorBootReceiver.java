package com.salesintelligence.calluploader;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

public class MonitorBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        SharedPreferences prefs = context.getSharedPreferences("sales_call_uploader", Context.MODE_PRIVATE);
        if (!prefs.getBoolean("monitoring_enabled", false)) {
            return;
        }
        Intent serviceIntent = new Intent(context, CallRecordingMonitorService.class);
        serviceIntent.setAction(CallRecordingMonitorService.ACTION_START);
        if (Build.VERSION.SDK_INT >= 26) {
            context.startForegroundService(serviceIntent);
        } else {
            context.startService(serviceIntent);
        }
    }
}
