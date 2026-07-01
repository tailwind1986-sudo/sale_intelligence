package com.salesintelligence.calluploader;

import android.Manifest;
import android.app.Activity;
import android.content.ContentUris;
import android.content.ContentResolver;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends Activity {
    private static final int REQ_PICK_AUDIO = 1001;
    private static final int REQ_AUDIO_PERMISSION = 1002;
    private static final String SAMPLE_PHONE = "01012345678";

    private EditText serverUrlInput;
    private EditText tokenInput;
    private EditText phoneInput;
    private EditText contactInput;
    private EditText durationInput;
    private TextView selectedFileText;
    private TextView statusText;
    private Uri selectedAudioUri;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("sales_call_uploader", MODE_PRIVATE);
        setContentView(buildContentView());
        loadPrefs();
        handleIncomingIntent(getIntent());
    }

    private View buildContentView() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(24), dp(20), dp(24));
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("Sales Call Uploader");
        title.setTextSize(24);
        title.setGravity(Gravity.START);
        root.addView(title);

        serverUrlInput = addInput(root, "Server URL", "https://your-sales-server.example.com");
        tokenInput = addInput(root, "Bearer token", "");
        phoneInput = addInput(root, "Phone number", "01012345678");
        contactInput = addInput(root, "Contact name", "");
        durationInput = addInput(root, "Duration seconds", "0");

        Button saveButton = addButton(root, "Save Settings");
        saveButton.setOnClickListener(v -> savePrefs());

        Button pickButton = addButton(root, "Select Recording File");
        pickButton.setOnClickListener(v -> pickAudioFile());

        Button latestButton = addButton(root, "Find Latest Call Recording");
        latestButton.setOnClickListener(v -> findLatestRecordingWithPermission());

        selectedFileText = new TextView(this);
        selectedFileText.setText("No file selected");
        selectedFileText.setPadding(0, dp(10), 0, dp(10));
        root.addView(selectedFileText);

        Button uploadButton = addButton(root, "Upload And Analyze");
        uploadButton.setOnClickListener(v -> uploadSelectedFile());

        statusText = new TextView(this);
        statusText.setText("Ready");
        statusText.setPadding(0, dp(16), 0, 0);
        root.addView(statusText);

        return scroll;
    }

    private EditText addInput(LinearLayout root, String label, String hint) {
        TextView tv = new TextView(this);
        tv.setText(label);
        tv.setPadding(0, dp(16), 0, dp(4));
        root.addView(tv);

        EditText input = new EditText(this);
        input.setHint(hint);
        input.setSingleLine(true);
        root.addView(input);
        return input;
    }

    private Button addButton(LinearLayout root, String text) {
        Button button = new Button(this);
        button.setText(text);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, dp(16), 0, 0);
        root.addView(button, params);
        return button;
    }

    private void loadPrefs() {
        serverUrlInput.setText(prefs.getString("server_url", "https://161.33.148.67.sslip.io"));
        tokenInput.setText(prefs.getString("token", ""));
    }

    private void savePrefs() {
        prefs.edit()
                .putString("server_url", serverUrlInput.getText().toString().trim())
                .putString("token", tokenInput.getText().toString().trim())
                .apply();
        toast("Saved");
    }

    private void pickAudioFile() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("audio/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, REQ_PICK_AUDIO);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIncomingIntent(intent);
    }

    private void handleIncomingIntent(Intent intent) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) {
            return;
        }
        Uri uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        if (uri == null) {
            return;
        }
        selectAudioUri(uri, "Shared recording selected", intent.getFlags());
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_PICK_AUDIO || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        selectAudioUri(data.getData(), "Recording selected", data.getFlags());
    }

    private void selectAudioUri(Uri uri, String message, int grantFlags) {
        selectedAudioUri = uri;
        int flags = grantFlags & Intent.FLAG_GRANT_READ_URI_PERMISSION;
        try {
            if (flags != 0) {
                getContentResolver().takePersistableUriPermission(selectedAudioUri, flags);
            }
        } catch (SecurityException ignored) {
        }
        String displayName = getDisplayName(selectedAudioUri);
        selectedFileText.setText(displayName);
        maybePrefillPhone(displayName);
        maybePrefillContactName(displayName);
        status(message);
    }

    private void findLatestRecordingWithPermission() {
        if (Build.VERSION.SDK_INT < 23 || checkSelfPermission(audioPermission()) == PackageManager.PERMISSION_GRANTED) {
            findLatestRecording();
            return;
        }
        requestPermissions(new String[]{audioPermission()}, REQ_AUDIO_PERMISSION);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_AUDIO_PERMISSION) {
            return;
        }
        if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            findLatestRecording();
        } else {
            status("Audio permission denied. Use Select Recording File instead.");
        }
    }

    private String audioPermission() {
        if (Build.VERSION.SDK_INT >= 33) {
            return Manifest.permission.READ_MEDIA_AUDIO;
        }
        return Manifest.permission.READ_EXTERNAL_STORAGE;
    }

    private void findLatestRecording() {
        Uri uri = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI;
        String[] projection = new String[]{
                MediaStore.Audio.Media._ID,
                MediaStore.Audio.Media.DISPLAY_NAME,
                MediaStore.Audio.Media.DATE_MODIFIED,
                MediaStore.Audio.Media.MIME_TYPE,
                Build.VERSION.SDK_INT >= 29 ? MediaStore.Audio.Media.RELATIVE_PATH : MediaStore.Audio.Media.DATA
        };
        String sort = MediaStore.Audio.Media.DATE_MODIFIED + " DESC";
        Uri bestUri = null;
        String bestName = "";
        try (Cursor cursor = getContentResolver().query(uri, projection, null, null, sort)) {
            if (cursor == null) {
                status("Cannot read audio library. Use Select Recording File.");
                return;
            }
            int idCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID);
            int nameCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DISPLAY_NAME);
            int mimeCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.MIME_TYPE);
            int pathCol = cursor.getColumnIndex(projection[4]);
            Uri fallbackUri = null;
            String fallbackName = "";
            int checked = 0;
            while (cursor.moveToNext() && checked < 200) {
                checked++;
                long id = cursor.getLong(idCol);
                String name = cursor.getString(nameCol);
                String mime = cursor.getString(mimeCol);
                String path = pathCol >= 0 ? cursor.getString(pathCol) : "";
                Uri candidate = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id);
                if (fallbackUri == null && mime != null && mime.startsWith("audio/")) {
                    fallbackUri = candidate;
                    fallbackName = name;
                }
                if (isLikelyCallRecording(name, path)) {
                    bestUri = candidate;
                    bestName = name;
                    break;
                }
            }
            if (bestUri == null) {
                bestUri = fallbackUri;
                bestName = fallbackName;
            }
        } catch (Exception e) {
            status("Latest recording lookup failed: " + e.getMessage());
            return;
        }
        if (bestUri == null) {
            status("No audio file found. Use Select Recording File.");
            return;
        }
        selectAudioUri(bestUri, "Latest recording selected: " + bestName, Intent.FLAG_GRANT_READ_URI_PERMISSION);
    }

    private boolean isLikelyCallRecording(String name, String path) {
        String value = ((name == null ? "" : name) + " " + (path == null ? "" : path)).toLowerCase();
        return value.contains("통화")
                || value.contains("call")
                || value.contains("recording")
                || value.contains("recordings");
    }

    private void uploadSelectedFile() {
        savePrefs();
        if (selectedAudioUri == null) {
            toast("Select a recording file first");
            return;
        }
        String serverUrl = trimTrailingSlash(serverUrlInput.getText().toString().trim());
        String token = tokenInput.getText().toString().trim();
        if (serverUrl.isEmpty()) {
            toast("Server URL is required");
            return;
        }
        status("Uploading...");
        new Thread(() -> {
            try {
                String response = uploadMultipart(serverUrl, token);
                runOnUiThread(() -> status("Done: " + response));
            } catch (Exception e) {
                runOnUiThread(() -> status("Failed: " + e.getMessage()));
            }
        }).start();
    }

    private String uploadMultipart(String serverUrl, String token) throws IOException {
        String boundary = "----SalesCall" + UUID.randomUUID();
        URL url = new URL(serverUrl + "/api/calls/upload");
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(30000);
        conn.setReadTimeout(600000);
        conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        if (!token.isEmpty()) {
            conn.setRequestProperty("Authorization", "Bearer " + token);
        }

        try (OutputStream out = conn.getOutputStream()) {
            writeField(out, boundary, "phone_number", phoneInput.getText().toString().trim());
            writeField(out, boundary, "contact_name", contactInput.getText().toString().trim());
            writeField(out, boundary, "duration_seconds", sanitizedDurationSeconds());
            writeField(out, boundary, "call_ended_at", OffsetDateTime.now().toString());
            writeFile(out, boundary, "file", selectedAudioUri);
            out.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        InputStream stream = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
        String body = readAll(stream);
        if (code < 200 || code >= 300) {
            throw new IOException("HTTP " + code + " " + body);
        }
        return body;
    }

    private String sanitizedDurationSeconds() {
        String value = durationInput.getText().toString().trim();
        if (value.matches("\\d+")) {
            return value;
        }
        durationInput.setText("0");
        return "0";
    }

    private void writeField(OutputStream out, String boundary, String name, String value) throws IOException {
        out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        out.write((value == null ? "" : value).getBytes(StandardCharsets.UTF_8));
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private void writeFile(OutputStream out, String boundary, String name, Uri uri) throws IOException {
        ContentResolver resolver = getContentResolver();
        String fileName = getDisplayName(uri);
        String mime = resolver.getType(uri);
        if (mime == null || mime.trim().isEmpty()) {
            mime = "audio/mp4";
        }
        out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + fileName + "\"\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Type: " + mime + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        try (InputStream input = new BufferedInputStream(resolver.openInputStream(uri))) {
            if (input == null) {
                throw new IOException("Cannot open selected file");
            }
            byte[] buffer = new byte[1024 * 64];
            int read;
            while ((read = input.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
        }
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private String getDisplayName(Uri uri) {
        String fallback = "call-recording.m4a";
        try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String name = cursor.getString(index);
                    if (name != null && !name.trim().isEmpty()) {
                        return name;
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return fallback;
    }

    private void maybePrefillPhone(String fileName) {
        String current = phoneInput.getText().toString().trim();
        if (!current.isEmpty() && !SAMPLE_PHONE.equals(current)) {
            return;
        }
        Matcher matcher = Pattern.compile("(\\d{8,15})").matcher(fileName == null ? "" : fileName);
        while (matcher.find()) {
            String candidate = matcher.group(1);
            if (candidate.length() == 6 || candidate.length() == 4) {
                continue;
            }
            phoneInput.setText(candidate);
            return;
        }
    }

    private void maybePrefillContactName(String fileName) {
        String current = contactInput.getText().toString().trim();
        if (!current.isEmpty()) {
            return;
        }
        String candidate = extractContactNameFromFileName(fileName);
        if (!candidate.isEmpty()) {
            contactInput.setText(candidate);
        }
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
        value = value.replaceFirst("^통화\\s*녹음\\s*", "");
        value = value.replaceFirst("^통화녹음\\s*", "");
        value = value.replaceFirst("^녹음\\s*", "");
        value = value.replaceAll("\\+?\\d[\\d\\s]{5,}\\d", " ");
        value = value.replaceAll("\\b\\d{4,}\\b", " ");
        value = value.replaceAll("\\s+", " ").trim();
        if (value.length() > 30) {
            value = value.substring(0, 30).trim();
        }
        return value;
    }

    private String readAll(InputStream stream) throws IOException {
        if (stream == null) {
            return "";
        }
        byte[] buffer = new byte[8192];
        StringBuilder builder = new StringBuilder();
        int read;
        while ((read = stream.read(buffer)) != -1) {
            builder.append(new String(buffer, 0, read, StandardCharsets.UTF_8));
        }
        return builder.toString();
    }

    private String trimTrailingSlash(String value) {
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    private void status(String text) {
        statusText.setText(text);
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
