package com.salesintelligence.calluploader;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
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

public class MainActivity extends Activity {
    private static final int REQ_PICK_AUDIO = 1001;

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
        serverUrlInput.setText(prefs.getString("server_url", ""));
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
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_PICK_AUDIO || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        selectedAudioUri = data.getData();
        int flags = data.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION;
        try {
            getContentResolver().takePersistableUriPermission(selectedAudioUri, flags);
        } catch (SecurityException ignored) {
        }
        selectedFileText.setText(getDisplayName(selectedAudioUri));
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
            writeField(out, boundary, "duration_seconds", durationInput.getText().toString().trim());
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
