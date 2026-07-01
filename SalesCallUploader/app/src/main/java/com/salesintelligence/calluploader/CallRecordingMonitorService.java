package com.salesintelligence.calluploader;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ContentUris;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.MediaStore;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class CallRecordingMonitorService extends Service {
    public static final String ACTION_START = "com.salesintelligence.calluploader.MONITOR_START";
    public static final String ACTION_STOP = "com.salesintelligence.calluploader.MONITOR_STOP";

    private static final String MONITOR_CHANNEL_ID = "call_monitor";
    private static final String ALERT_CHANNEL_ID = "call_alerts";
    private static final int FOREGROUND_ID = 4101;
    private static final long POLL_INTERVAL_MS = 60_000L;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;
    private boolean running = false;

    private final Runnable pollRunnable = new Runnable() {
        @Override
        public void run() {
            if (!running) {
                return;
            }
            pollForNewRecordings();
            handler.postDelayed(this, POLL_INTERVAL_MS);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("sales_call_uploader", MODE_PRIVATE);
        createNotificationChannels();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            stopMonitoring();
            return START_NOT_STICKY;
        }
        startMonitoring();
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        running = false;
        handler.removeCallbacks(pollRunnable);
        super.onDestroy();
    }

    private void startMonitoring() {
        createNotificationChannels();
        prefs.edit()
                .putBoolean("monitoring_enabled", true)
                .putLong("monitoring_heartbeat_ms", System.currentTimeMillis())
                .apply();
        startForeground(FOREGROUND_ID, monitorNotification());
        long nowSeconds = System.currentTimeMillis() / 1000L;
        if (!prefs.contains("monitor_last_seen_seconds")) {
            prefs.edit().putLong("monitor_last_seen_seconds", Math.max(0L, nowSeconds - 10L)).apply();
        }
        if (!running) {
            running = true;
            handler.removeCallbacks(pollRunnable);
            handler.post(pollRunnable);
        }
    }

    private void stopMonitoring() {
        running = false;
        handler.removeCallbacks(pollRunnable);
        prefs.edit().putBoolean("monitoring_enabled", false).apply();
        stopForeground(true);
        stopSelf();
    }

    private void pollForNewRecordings() {
        prefs.edit().putLong("monitoring_heartbeat_ms", System.currentTimeMillis()).apply();
        Uri baseUri = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI;
        String[] projection = new String[]{
                MediaStore.Audio.Media._ID,
                MediaStore.Audio.Media.DISPLAY_NAME,
                MediaStore.Audio.Media.DATE_MODIFIED,
                MediaStore.Audio.Media.MIME_TYPE,
                Build.VERSION.SDK_INT >= 29 ? MediaStore.Audio.Media.RELATIVE_PATH : MediaStore.Audio.Media.DATA
        };
        String sort = MediaStore.Audio.Media.DATE_MODIFIED + " DESC";
        long lastSeen = prefs.getLong("monitor_last_seen_seconds", 0L);
        long maxSeen = lastSeen;

        try (Cursor cursor = getContentResolver().query(baseUri, projection, null, null, sort)) {
            if (cursor == null) {
                return;
            }
            int idCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID);
            int nameCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DISPLAY_NAME);
            int modifiedCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DATE_MODIFIED);
            int mimeCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.MIME_TYPE);
            int pathCol = cursor.getColumnIndex(projection[4]);
            int checked = 0;
            while (cursor.moveToNext() && checked < 100) {
                checked++;
                long modified = cursor.getLong(modifiedCol);
                if (modified <= lastSeen) {
                    break;
                }
                if (modified > maxSeen) {
                    maxSeen = modified;
                }
                String name = cursor.getString(nameCol);
                String mime = cursor.getString(mimeCol);
                String path = pathCol >= 0 ? cursor.getString(pathCol) : "";
                if (mime == null || !mime.startsWith("audio/") || !isLikelyCallRecording(name, path)) {
                    continue;
                }
                TrackedMatch match = findTrackedMatch(name);
                if (match == null) {
                    continue;
                }
                long id = cursor.getLong(idCol);
                Uri audioUri = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id);
                String notificationKey = buildNotificationKey(audioUri, name, modified);
                if (wasNotified(notificationKey)) {
                    continue;
                }
                rememberNotified(notificationKey);
                notifyTrackedRecording(audioUri, name, match);
            }
        } catch (Exception ignored) {
        }

        if (maxSeen > lastSeen) {
            prefs.edit().putLong("monitor_last_seen_seconds", maxSeen).apply();
        }
    }

    private void notifyTrackedRecording(Uri audioUri, String fileName, TrackedMatch match) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.setAction(MainActivity.ACTION_REVIEW_RECORDING);
        intent.putExtra(MainActivity.EXTRA_AUDIO_URI, audioUri.toString());
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                (int) (System.currentTimeMillis() & 0x7fffffff),
                intent,
                flags
        );

        Notification.Builder builder = notificationBuilder(ALERT_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_sys_upload_done)
                .setContentTitle("Tracked call recording found")
                .setContentText(match.displayName + " -> " + match.companyName)
                .setStyle(new Notification.BigTextStyle().bigText(fileName + "\n" + match.displayName + " -> " + match.companyName))
                .setContentIntent(pendingIntent)
                .addAction(android.R.drawable.ic_menu_upload, "Review Upload", pendingIntent)
                .setAutoCancel(true);
        if (Build.VERSION.SDK_INT < 26) {
            builder.setPriority(Notification.PRIORITY_HIGH);
        }

        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.notify((int) (System.currentTimeMillis() & 0x7fffffff), builder.build());
    }

    private Notification monitorNotification() {
        Intent intent = new Intent(this, MainActivity.class);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent pendingIntent = PendingIntent.getActivity(this, 4102, intent, flags);
        Intent stopIntent = new Intent(this, CallRecordingMonitorService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPendingIntent = PendingIntent.getService(this, 4103, stopIntent, flags);
        Notification.Builder builder = notificationBuilder(MONITOR_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_menu_upload)
                .setContentTitle("Sales Call Uploader 감시중")
                .setContentText("추적 대상 통화녹음을 감시하고 있습니다")
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .setAutoCancel(false)
                .setOnlyAlertOnce(true)
                .addAction(android.R.drawable.ic_menu_close_clear_cancel, "감시 중지", stopPendingIntent);
        if (Build.VERSION.SDK_INT >= 21) {
            builder.setCategory(Notification.CATEGORY_SERVICE);
        }
        if (Build.VERSION.SDK_INT < 26) {
            builder.setPriority(Notification.PRIORITY_LOW);
        }
        return builder.build();
    }

    private Notification.Builder notificationBuilder(String channelId) {
        if (Build.VERSION.SDK_INT >= 26) {
            return new Notification.Builder(this, channelId);
        }
        return new Notification.Builder(this);
    }

    private void createNotificationChannels() {
        if (Build.VERSION.SDK_INT < 26) {
            return;
        }
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        NotificationChannel monitor = new NotificationChannel(
                MONITOR_CHANNEL_ID,
                "Call recording monitor",
                NotificationManager.IMPORTANCE_LOW
        );
        NotificationChannel alerts = new NotificationChannel(
                ALERT_CHANNEL_ID,
                "Tracked call alerts",
                NotificationManager.IMPORTANCE_HIGH
        );
        manager.createNotificationChannel(monitor);
        manager.createNotificationChannel(alerts);
    }

    private TrackedMatch findTrackedMatch(String fileName) {
        String phone = extractPhoneFromFileName(fileName);
        String contactName = extractContactNameFromFileName(fileName);
        JSONArray rows;
        try {
            rows = new JSONArray(prefs.getString("tracked_contacts", "[]"));
        } catch (Exception e) {
            return null;
        }
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null) {
                continue;
            }
            if (phonesMatch(phone, row.optString("phone", ""))) {
                return trackedMatch(row);
            }
        }
        String needle = normalizeName(contactName);
        if (needle.isEmpty()) {
            return null;
        }
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null) {
                continue;
            }
            String candidate = normalizeName(row.optString("name", ""));
            if (!candidate.isEmpty() && (candidate.equals(needle) || needle.contains(candidate) || candidate.contains(needle))) {
                return trackedMatch(row);
            }
        }
        return null;
    }

    private String buildNotificationKey(Uri uri, String fileName, long modified) {
        return (fileName == null ? "" : fileName) + "|" + modified + "|" + uri.toString();
    }

    private boolean wasNotified(String key) {
        JSONArray rows = notifiedKeysJson();
        for (int i = 0; i < rows.length(); i++) {
            if (key.equals(rows.optString(i, ""))) {
                return true;
            }
        }
        return false;
    }

    private void rememberNotified(String key) {
        JSONArray oldRows = notifiedKeysJson();
        JSONArray rows = new JSONArray();
        rows.put(key);
        for (int i = 0; i < oldRows.length() && rows.length() < 100; i++) {
            String old = oldRows.optString(i, "");
            if (!old.isEmpty() && !key.equals(old)) {
                rows.put(old);
            }
        }
        prefs.edit().putString("notified_recording_keys", rows.toString()).apply();
    }

    private JSONArray notifiedKeysJson() {
        try {
            return new JSONArray(prefs.getString("notified_recording_keys", "[]"));
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    private TrackedMatch trackedMatch(JSONObject row) {
        String name = row.optString("name", "");
        String phone = row.optString("phone", "");
        String companyName = row.optString("company_name", "");
        int companyId = row.optInt("company_id", 0);
        return new TrackedMatch(displayContact(name, phone), companyName + " (#" + companyId + ")");
    }

    private boolean isLikelyCallRecording(String name, String path) {
        String value = ((name == null ? "" : name) + " " + (path == null ? "" : path)).toLowerCase();
        return value.contains("\uD1B5\uD654")
                || value.contains("call")
                || value.contains("recording")
                || value.contains("recordings");
    }

    private String extractPhoneFromFileName(String fileName) {
        Matcher matcher = Pattern.compile("(\\d{8,15})").matcher(fileName == null ? "" : fileName);
        while (matcher.find()) {
            String candidate = matcher.group(1);
            if (candidate.length() == 6 || candidate.length() == 4) {
                continue;
            }
            return candidate;
        }
        return "";
    }

    private String extractContactNameFromFileName(String fileName) {
        String value = fileName == null ? "" : fileName;
        int dot = value.lastIndexOf('.');
        if (dot > 0) {
            value = value.substring(0, dot);
        }
        value = value
                .replace('_', ' ')
                .replace('-', ' ')
                .replace('(', ' ')
                .replace(')', ' ')
                .replace('[', ' ')
                .replace(']', ' ')
                .trim();
        value = value.replaceFirst("(?i)^call\\s*recording\\s*", "");
        value = value.replaceFirst("^\\uD1B5\\uD654\\s*\\uB179\\uC74C\\s*", "");
        value = value.replaceFirst("^\\uD1B5\\uD654\\uB179\\uC74C\\s*", "");
        value = value.replaceFirst("^\\uB179\\uC74C\\s*", "");
        value = value.replaceAll("\\+?\\d[\\d\\s]{5,}\\d", " ");
        value = value.replaceAll("\\b\\d{4,}\\b", " ");
        value = value.replaceAll("\\s+", " ").trim();
        if (value.length() > 30) {
            value = value.substring(0, 30).trim();
        }
        return value;
    }

    private boolean phonesMatch(String left, String right) {
        String a = normalizePhone(left);
        String b = normalizePhone(right);
        if (a.isEmpty() || b.isEmpty()) {
            return false;
        }
        if (a.equals(b)) {
            return true;
        }
        return a.length() >= 8 && b.length() >= 8
                && (a.endsWith(b.substring(Math.max(0, b.length() - 8)))
                || b.endsWith(a.substring(Math.max(0, a.length() - 8))));
    }

    private String normalizePhone(String value) {
        String digits = value == null ? "" : value.replaceAll("\\D+", "");
        if (digits.startsWith("82") && digits.length() > 4) {
            return "0" + digits.substring(2);
        }
        return digits;
    }

    private String normalizeName(String value) {
        return value == null ? "" : value.replaceAll("\\s+", "").trim();
    }

    private String displayContact(String name, String phone) {
        String safeName = name == null ? "" : name.trim();
        String safePhone = phone == null ? "" : phone.trim();
        if (!safeName.isEmpty() && !safePhone.isEmpty()) {
            return safeName + " / " + safePhone;
        }
        if (!safeName.isEmpty()) {
            return safeName;
        }
        return safePhone;
    }

    private static class TrackedMatch {
        final String displayName;
        final String companyName;

        TrackedMatch(String displayName, String companyName) {
            this.displayName = displayName;
            this.companyName = companyName;
        }
    }
}
