package kr.gagyebu.mobile;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.database.Cursor;
import android.database.DatabaseErrorHandler;
import android.database.sqlite.SQLiteCursor;
import android.database.sqlite.SQLiteCursorDriver;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteProgram;
import android.database.sqlite.SQLiteQuery;
import android.database.sqlite.SQLiteStatement;
import android.net.Uri;
import android.os.Build;
import android.provider.DocumentsContract;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Date;
import java.util.Locale;
import java.util.Map;

/**
 * 웹 화면(JavaScript)에서 부르는 기능 모음. 이름: window.GagyebuNative
 * - SQLite: PC판과 같은 형식의 파일(gagyebu.sqlite3)을 앱 전용 폴더에 둠 → 백업 파일을 PC와 그대로 주고받음
 * - 파일 주고받기: 시스템 파일 선택 창(저장소 권한 필요 없음)
 * 모든 결과는 JSON 문자열 {"ok":true,...} / {"ok":false,"error":"..."} 로 돌려준다 (예외를 웹으로 던지지 않음).
 * 동기 함수는 모두 WebView 의 JavaBridge 스레드 하나에서 불리므로, 묶음 저장(트랜잭션)도 그 스레드에서 시작·끝난다.
 */
public class NativeBridge {
    private static final int REQ_EXPORT_DB = 101, REQ_IMPORT_DB = 102, REQ_SAVE_TEXT = 103, REQ_OPEN_TEXT = 104;
    private static final int REQ_PICK_PHOTO = 105, REQ_CAPTURE = 106;
    private static final int PHOTO_SIDE = 1600, PHOTO_QUALITY = 82;   // PC판 services/attach.py 와 같음
    private static final int MAX_PHOTO = 8 * 1024 * 1024;
    private static final String DB_NAME = "gagyebu.sqlite3";
    private static final long MAX_TEXT = 20L * 1024 * 1024;       // CSV 등 글 파일 최대 20MB
    private static final long MAX_DB = 512L * 1024 * 1024;        // 자료 파일 최대 512MB
    private static final byte[] SQLITE_HEADER = "SQLite format 3\0".getBytes(StandardCharsets.US_ASCII);

    private final MainActivity act;
    private final WebView web;
    private final File dbFile;
    private final SharedPreferences prefs;
    private SQLiteDatabase db;
    private int txDepth = 0;
    private String openError;       // 자료 파일을 못 열었을 때 이유
    private String corruptMoved;    // 손상된 자료 파일을 옮겨 둔 이름 (지우지 않음)

    // 진행 중인 파일 선택 요청 (한 번에 하나)
    private String pendingCb;
    private String pendingText;

    NativeBridge(MainActivity act, WebView web) {
        this.act = act;
        this.web = web;
        this.dbFile = act.getDatabasePath(DB_NAME);
        this.prefs = act.getSharedPreferences("gagyebu_prefs", Activity.MODE_PRIVATE);
        try {
            openDb();
        } catch (Throwable e) {
            db = null;
            openError = e.getMessage() == null ? e.toString() : e.getMessage();
        }
    }

    // ── DB 열고 닫기 ─────────────────────────────────────
    /** 안드로이드 기본 처리기는 손상된 파일을 지워 버리므로, 지우지 않고 corrupt 폴더로 옮겨 둔다. */
    private final DatabaseErrorHandler keepCorrupt = new DatabaseErrorHandler() {
        @Override
        public void onCorruption(SQLiteDatabase bad) {
            try {
                if (bad.isOpen()) {
                    bad.close();
                }
            } catch (Exception ignored) {
            }
            File dir = new File(act.getFilesDir(), "corrupt");
            dir.mkdirs();
            String name = "corrupt-" + new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(new Date()) + ".sqlite3";
            File to = new File(dir, name);
            if (dbFile.renameTo(to)) {
                corruptMoved = name;
            }
            db = null;           // 쓰는 중에 손상이 발견된 경우: 닫힌 연결을 더 쓰지 않게
            openError = "자료 파일이 손상되어 앱 안 corrupt 폴더로 옮겨 두었습니다 (" + name + ").";
            for (String ext : new String[]{"-journal", "-wal", "-shm"}) {
                File f = new File(dbFile.getPath() + ext);
                if (f.exists()) {
                    f.renameTo(new File(dir, name + ext));
                }
            }
        }
    };

    private synchronized void openDb() {
        File dir = dbFile.getParentFile();
        if (dir != null && !dir.exists()) {
            dir.mkdirs();
        }
        // NO_LOCALIZED_COLLATORS: PC판 파일에 없는 android_metadata 표를 만들지 않음
        db = SQLiteDatabase.openDatabase(dbFile.getPath(), null,
                SQLiteDatabase.CREATE_IF_NECESSARY | SQLiteDatabase.NO_LOCALIZED_COLLATORS, keepCorrupt);
        db.setForeignKeyConstraintsEnabled(true);
        txDepth = 0;
        openError = null;
    }

    /** 연결을 닫으면 WAL 내용까지 본 파일에 다 들어가므로, 파일을 복사하기 전에 항상 닫는다. */
    private synchronized void closeDb() {
        if (db != null) {
            while (txDepth > 0) {
                try {
                    db.endTransaction();     // 다른 스레드에서 닫을 때는 예외가 날 수 있음 → 무시하고 닫기
                } catch (Exception ignored) {
                }
                txDepth--;
            }
            try {
                db.close();
            } catch (Exception ignored) {
            }
            db = null;
        }
    }

    synchronized void shutdown() {
        closeDb();
    }

    private void needDb() {
        if (db == null) {
            throw new IllegalStateException("자료 파일이 열려 있지 않습니다" + (openError != null ? ": " + openError : ""));
        }
    }

    // ── JSON 도우미 ─────────────────────────────────────
    private static JSONObject ok() {
        JSONObject o = new JSONObject();
        try {
            o.put("ok", true);
        } catch (Exception ignored) {
        }
        return o;
    }

    private static String err(Throwable e) {
        return errObj(e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage()).toString();
    }

    private static JSONObject errObj(String msg) {
        JSONObject o = new JSONObject();
        try {
            o.put("ok", false);
            o.put("error", msg);
        } catch (Exception ignored) {
        }
        return o;
    }

    private static JSONArray parseArgs(String argsJson) throws Exception {
        if (argsJson == null || argsJson.isEmpty()) {
            return new JSONArray();
        }
        return new JSONArray(argsJson);
    }

    /** 값의 형(정수·실수·문자·NULL)을 그대로 살려 묶는다 (rawQuery 의 문자열 묶기와 달리). */
    private static void bindAll(SQLiteProgram p, JSONArray args) throws Exception {
        for (int i = 0; i < args.length(); i++) {
            int idx = i + 1;
            if (args.isNull(i)) {
                p.bindNull(idx);
                continue;
            }
            Object v = args.get(i);
            if (v instanceof Integer || v instanceof Long) {
                p.bindLong(idx, ((Number) v).longValue());
            } else if (v instanceof Number) {
                double d = ((Number) v).doubleValue();
                if (d == Math.rint(d) && Math.abs(d) < 9.0e15) {
                    p.bindLong(idx, (long) d);
                } else {
                    p.bindDouble(idx, d);
                }
            } else if (v instanceof Boolean) {
                p.bindLong(idx, ((Boolean) v) ? 1 : 0);
            } else {
                p.bindString(idx, v.toString());
            }
        }
    }

    // ── SQL ─────────────────────────────────────────────
    /** SELECT·PRAGMA. 결과: {"ok":true,"cols":[...],"rows":[[...],...]} */
    @JavascriptInterface
    public synchronized String query(String sql, String argsJson) {
        Cursor c = null;
        try {
            needDb();
            final JSONArray args = parseArgs(argsJson);
            SQLiteDatabase.CursorFactory factory = new SQLiteDatabase.CursorFactory() {
                @Override
                public Cursor newCursor(SQLiteDatabase d, SQLiteCursorDriver driver, String table, SQLiteQuery q) {
                    try {
                        bindAll(q, args);
                    } catch (Exception e) {
                        throw new IllegalArgumentException(e.getMessage());
                    }
                    return new SQLiteCursor(driver, table, q);
                }
            };
            c = db.rawQueryWithFactory(factory, sql, null, null);
            String[] names = c.getColumnNames();
            JSONArray cols = new JSONArray();
            for (String n : names) {
                cols.put(n);
            }
            JSONArray rows = new JSONArray();
            int n = names.length;
            while (c.moveToNext()) {
                JSONArray r = new JSONArray();
                for (int i = 0; i < n; i++) {
                    switch (c.getType(i)) {
                        case Cursor.FIELD_TYPE_NULL:
                        case Cursor.FIELD_TYPE_BLOB:
                            r.put(JSONObject.NULL);
                            break;
                        case Cursor.FIELD_TYPE_INTEGER:
                            r.put(c.getLong(i));
                            break;
                        case Cursor.FIELD_TYPE_FLOAT:
                            r.put(c.getDouble(i));
                            break;
                        default:
                            r.put(c.getString(i));
                    }
                }
                rows.put(r);
            }
            JSONObject o = ok();
            o.put("cols", cols);
            o.put("rows", rows);
            return o.toString();
        } catch (Throwable e) {
            return err(e);
        } finally {
            if (c != null) {
                c.close();
            }
        }
    }

    /** INSERT·UPDATE·DELETE·CREATE 등 한 문장. 결과: {"ok":true,"changes":n,"lastId":id} */
    @JavascriptInterface
    public synchronized String exec(String sql, String argsJson) {
        SQLiteStatement st = null;
        try {
            needDb();
            JSONArray args = parseArgs(argsJson);
            st = db.compileStatement(sql);
            bindAll(st, args);
            String head = sql.trim().toUpperCase(Locale.ROOT);
            JSONObject o = ok();
            if (head.startsWith("INSERT") || head.startsWith("REPLACE")) {
                long id = st.executeInsert();     // 같은 연결에서 바로 새 id 를 받음
                o.put("lastId", id);
                o.put("changes", id == -1 ? 0 : 1);
            } else if (head.startsWith("UPDATE") || head.startsWith("DELETE")) {
                o.put("changes", st.executeUpdateDelete());
            } else {
                st.execute();
                o.put("changes", 0);
            }
            return o.toString();
        } catch (Throwable e) {
            return err(e);
        } finally {
            if (st != null) {
                st.close();
            }
        }
    }

    @JavascriptInterface
    public synchronized String begin() {
        try {
            needDb();
            db.beginTransaction();
            txDepth++;
            return ok().toString();
        } catch (Throwable e) {
            return err(e);
        }
    }

    @JavascriptInterface
    public synchronized String commit() {
        if (txDepth <= 0 || db == null) {
            return ok().toString();
        }
        try {
            try {
                db.setTransactionSuccessful();
            } finally {
                try {
                    db.endTransaction();
                } finally {
                    txDepth--;           // 실패해도 세던 깊이는 줄여 이후 작업이 막히지 않게
                }
            }
            return ok().toString();
        } catch (Throwable e) {
            return err(e);
        }
    }

    @JavascriptInterface
    public synchronized String rollback() {
        if (txDepth <= 0 || db == null) {
            return ok().toString();
        }
        try {
            try {
                db.endTransaction();
            } finally {
                txDepth--;
            }
            return ok().toString();
        } catch (Throwable e) {
            return err(e);
        }
    }

    // ── 암호 (PC판과 같은 방식: PBKDF2-HMAC-SHA256) ──────
    @JavascriptInterface
    public String pbkdf2(String password, String saltHex, int iterations) {
        try {
            JSONObject o = ok();
            o.put("hex", Pure.pbkdf2Hex(password, saltHex, iterations));
            return o.toString();
        } catch (Throwable e) {
            return err(e);
        }
    }

    @JavascriptInterface
    public String randomHex(int bytes) {
        byte[] b = new byte[Math.max(1, Math.min(bytes, 64))];
        new SecureRandom().nextBytes(b);
        return Pure.toHex(b);
    }

    // ── 화면 꾸미기 등 기기별 설정 (자료 파일과 따로 보관 → 백업을 바꿔 끼워도 유지) ──
    @JavascriptInterface
    public String getPrefs() {
        JSONObject o = new JSONObject();
        try {
            for (Map.Entry<String, ?> e : prefs.getAll().entrySet()) {
                o.put(e.getKey(), String.valueOf(e.getValue()));
            }
        } catch (Exception ignored) {
        }
        return o.toString();
    }

    @JavascriptInterface
    public void setPref(String key, String value) {
        if (value == null) {
            prefs.edit().remove(key).apply();
        } else {
            prefs.edit().putString(key, value).apply();
        }
    }

    @JavascriptInterface
    public String appInfo() {
        JSONObject o = ok();
        try {
            PackageInfo pi = act.getPackageManager().getPackageInfo(act.getPackageName(), 0);
            o.put("version", pi.versionName);
            o.put("versionCode", pi.versionCode);
            o.put("sdk", Build.VERSION.SDK_INT);
            o.put("dbPath", dbFile.getPath());
            o.put("dbSize", dbFile.length());
            o.put("dbOpen", db != null);
            if (openError != null) {
                o.put("openError", openError);
            }
            if (corruptMoved != null) {
                o.put("corruptMoved", corruptMoved);
            }
        } catch (Exception ignored) {
        }
        return o.toString();
    }

    @JavascriptInterface
    public void openExternal(final String url) {
        act.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                act.openExternal(url);
            }
        });
    }

    /** 테마에 맞춰 맨 위 상태 표시줄·맨 아래 내비게이션 줄 색 바꾸기. lightBg 면 아이콘을 어둡게. */
    @JavascriptInterface
    public void setBars(final String color, final boolean lightBg) {
        act.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    int c = android.graphics.Color.parseColor(color);
                    android.view.Window w = act.getWindow();
                    w.setStatusBarColor(c);
                    w.setNavigationBarColor(c);
                    android.view.View d = w.getDecorView();
                    int f = d.getSystemUiVisibility();
                    final int lightStatus = 0x2000;   // SYSTEM_UI_FLAG_LIGHT_STATUS_BAR (API 23)
                    final int lightNav = 0x10;        // SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR (API 26)
                    f = lightBg ? (f | lightStatus) : (f & ~lightStatus);
                    if (Build.VERSION.SDK_INT >= 26) {
                        f = lightBg ? (f | lightNav) : (f & ~lightNav);
                    }
                    d.setSystemUiVisibility(f);
                } catch (RuntimeException ignored) {
                    // 색 이름이 틀리거나 창이 없으면 그대로 둠
                }
            }
        });
    }

    @JavascriptInterface
    public void exitApp() {
        act.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                act.finish();
            }
        });
    }

    // ── 자동 보관 (앱 안, 하루 한 번, 최근 N개) ───────────
    private File autoDir() {
        File d = new File(act.getFilesDir(), "autobackup");
        if (!d.exists()) {
            d.mkdirs();
        }
        return d;
    }

    private File keepDir() {
        File d = new File(act.getFilesDir(), "before-restore");
        if (!d.exists()) {
            d.mkdirs();
        }
        return d;
    }

    @JavascriptInterface
    public synchronized String autoBackup(int keep) {
        try {
            if (db == null || txDepth > 0 || !dbFile.exists()) {
                return ok().put("skipped", true).toString();
            }
            String name = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date()) + ".sqlite3";
            File f = new File(autoDir(), name);
            if (f.exists()) {
                return ok().put("skipped", true).toString();
            }
            File part = new File(autoDir(), name + ".part");
            closeDb();
            try {
                copyFile(dbFile, part);
            } finally {
                openDb();
            }
            if (!part.renameTo(f)) {
                part.delete();
                throw new IllegalStateException("보관 파일 이름을 바꾸지 못했습니다.");
            }
            prune(autoDir(), Math.max(1, keep));
            return ok().put("file", name).toString();
        } catch (Throwable e) {
            return err(e);
        }
    }

    private static void prune(File dir, int keep) {
        File[] fs = dir.listFiles();
        if (fs == null) {
            return;
        }
        Arrays.sort(fs);     // 이름이 날짜라 이름순 = 날짜순
        int n = 0;
        for (File f : fs) {
            if (f.getName().endsWith(".sqlite3")) {
                n++;
            }
        }
        for (File f : fs) {
            if (n <= keep) {
                break;
            }
            if (f.getName().endsWith(".sqlite3")) {
                f.delete();
                n--;
            }
        }
    }

    /** 앱 안에 보관된 사본 목록 */
    @JavascriptInterface
    public String listBackups() {
        try {
            JSONArray arr = new JSONArray();
            for (File dir : new File[]{autoDir(), keepDir(), new File(act.getFilesDir(), "corrupt")}) {
                File[] fs = dir.listFiles();
                if (fs == null) {
                    continue;
                }
                for (File f : fs) {
                    if (!f.getName().endsWith(".sqlite3")) {
                        continue;
                    }
                    JSONObject o = new JSONObject();
                    o.put("kind", dir.getName());
                    o.put("name", f.getName());
                    o.put("size", f.length());
                    o.put("mtime", f.lastModified());
                    arr.put(o);
                }
            }
            return ok().put("items", arr).toString();
        } catch (Throwable e) {
            return err(e);
        }
    }

    /** 앱 안 사본으로 되돌리기 (지금 자료는 before-restore 에 보관) */
    @JavascriptInterface
    public String restoreBackup(String kind, String name) {
        File tmp = null;
        try {
            File dir = "before-restore".equals(kind) ? keepDir()
                    : "corrupt".equals(kind) ? new File(act.getFilesDir(), "corrupt") : autoDir();
            File src = new File(dir, new File(name).getName());
            if (!src.exists()) {
                throw new IllegalArgumentException("사본을 찾을 수 없습니다.");
            }
            tmp = File.createTempFile("incoming", ".sqlite3", act.getCacheDir());
            copyFile(src, tmp);
            String kept = replaceWith(tmp);
            return ok().put("kept", kept).toString();
        } catch (Throwable e) {
            return err(e);
        } finally {
            if (tmp != null) {
                tmp.delete();
            }
        }
    }

    // ── 파일 주고받기 (시스템 파일 선택 창) ───────────────
    @JavascriptInterface
    public void exportDb(final String fileName, final String cb) {
        startPicker(cb, null, new Runnable() {
            @Override
            public void run() {
                Intent it = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                it.addCategory(Intent.CATEGORY_OPENABLE);
                it.setType("application/octet-stream");
                it.putExtra(Intent.EXTRA_TITLE, fileName);
                act.startActivityForResult(it, REQ_EXPORT_DB);
            }
        });
    }

    /** 백업 파일 보내기: 지금 자료의 사본을 만들어 공유 창(카카오톡·디스코드·메일·드라이브 등)에 내어 줌 */
    @JavascriptInterface
    public void shareDb(final String fileName, final String cb) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    String name = fileName == null ? "" : fileName.replaceAll("[\\\\/:*?\"<>|]", "_");
                    if (name.isEmpty() || name.contains("..")) {
                        name = "gagyebu.sqlite3";
                    }
                    File dir = ShareProvider.dir(act);
                    if (!dir.isDirectory() && !dir.mkdirs()) {
                        throw new IllegalStateException("보낼 파일을 만들 수 없습니다.");
                    }
                    File[] old = dir.listFiles();
                    if (old != null) {
                        for (File f : old) {            // 지난번에 보낸 사본은 지움 (캐시에 쌓이지 않게)
                            f.delete();
                        }
                    }
                    final File out = new File(dir, name);
                    snapshotTo(out);
                    final Uri uri = ShareProvider.uriFor(name);
                    final long size = out.length();
                    act.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            try {
                                Intent it = new Intent(Intent.ACTION_SEND);
                                it.setType("application/octet-stream");
                                it.putExtra(Intent.EXTRA_STREAM, uri);
                                it.putExtra(Intent.EXTRA_SUBJECT, "우리집 가계부 백업");
                                it.setClipData(android.content.ClipData.newRawUri("우리집 가계부 백업", uri));
                                it.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                                Intent ch = Intent.createChooser(it, "백업 파일 보내기");
                                ch.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                                act.startActivity(ch);
                                JSONObject o = ok();
                                o.put("size", size);
                                callback(cb, o);
                            } catch (Exception e) {
                                callback(cb, errObj("보내기 창을 열 수 없습니다: " + e.getMessage()));
                            }
                        }
                    });
                } catch (Throwable e) {
                    callback(cb, errObj(e.getMessage() == null ? e.toString() : e.getMessage()));
                }
            }
        }).start();
    }

    /** 다른 앱으로 백업 파일 고르기 (삼성 '내 파일'·Files·드라이브 등 앱을 먼저 고르고 그 안에서 경로 선택) */
    @JavascriptInterface
    public void importDbVia(final String cb) {
        startPicker(cb, null, new Runnable() {
            @Override
            public void run() {
                Intent it = new Intent(Intent.ACTION_GET_CONTENT);
                it.addCategory(Intent.CATEGORY_OPENABLE);
                it.setType("*/*");
                act.startActivityForResult(Intent.createChooser(it, "백업 파일이 있는 앱 고르기"), REQ_IMPORT_DB);
            }
        });
    }

    @JavascriptInterface
    public void importDb(final String cb) {
        startPicker(cb, null, new Runnable() {
            @Override
            public void run() {
                Intent it = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                it.addCategory(Intent.CATEGORY_OPENABLE);
                it.setType("*/*");
                act.startActivityForResult(it, REQ_IMPORT_DB);
            }
        });
    }

    @JavascriptInterface
    public void saveText(final String fileName, final String mime, String content, final String cb) {
        startPicker(cb, content, new Runnable() {
            @Override
            public void run() {
                Intent it = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                it.addCategory(Intent.CATEGORY_OPENABLE);
                it.setType(mime == null || mime.isEmpty() ? "text/plain" : mime);
                it.putExtra(Intent.EXTRA_TITLE, fileName);
                act.startActivityForResult(it, REQ_SAVE_TEXT);
            }
        });
    }

    @JavascriptInterface
    public void openText(final String cb) {
        startPicker(cb, null, new Runnable() {
            @Override
            public void run() {
                Intent it = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                it.addCategory(Intent.CATEGORY_OPENABLE);
                it.setType("*/*");
                act.startActivityForResult(it, REQ_OPEN_TEXT);
            }
        });
    }

    private void startPicker(String cb, String text, final Runnable launch) {
        synchronized (this) {
            if (pendingCb != null) {
                callback(cb, errObj("다른 파일 작업이 진행 중입니다."));
                return;
            }
            pendingCb = cb;
            pendingText = text;
        }
        act.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    launch.run();
                } catch (Exception e) {
                    String c = takePending();
                    callback(c, errObj("파일 선택 창을 열 수 없습니다: " + e.getMessage()));
                }
            }
        });
    }

    private synchronized String takePending() {
        String c = pendingCb;
        pendingCb = null;
        return c;
    }

    void onActivityResult(final int req, int resultCode, Intent data) {
        if (req != REQ_EXPORT_DB && req != REQ_IMPORT_DB && req != REQ_SAVE_TEXT && req != REQ_OPEN_TEXT
                && req != REQ_PICK_PHOTO && req != REQ_CAPTURE) {
            return;
        }
        final String cb;
        final String text;
        synchronized (this) {
            cb = pendingCb;
            text = pendingText;
            pendingCb = null;
            pendingText = null;
        }
        if (cb == null) {
            // 앱이 다시 시작되어 요청 내용(저장할 글 등)을 잃은 경우: 아무것도 하지 않음 (빈 파일 저장·화면 모르게 자료 교체 방지)
            return;
        }
        if (req == REQ_CAPTURE && resultCode == Activity.RESULT_OK) {      // 찍은 사진은 우리가 준 곳에 (data 없음)
            new Thread(new Runnable() {
                @Override
                public void run() {
                    JSONObject res;
                    try {
                        res = photoFrom(CaptureProvider.file(act), "사진.jpg");
                    } catch (Throwable e) {
                        res = errObj(e.getMessage() == null ? e.toString() : e.getMessage());
                    } finally {
                        CaptureProvider.file(act).delete();
                    }
                    callback(cb, res);
                }
            }).start();
            return;
        }
        if (resultCode != Activity.RESULT_OK || data == null || data.getData() == null) {
            JSONObject o = errObj("취소");
            try {
                o.put("cancel", true);
            } catch (Exception ignored) {
            }
            callback(cb, o);
            return;
        }
        final Uri uri = data.getData();
        new Thread(new Runnable() {     // 큰 파일도 화면이 멈추지 않게
            @Override
            public void run() {
                JSONObject res;
                try {
                    if (req == REQ_EXPORT_DB) {
                        res = doExport(uri);
                    } else if (req == REQ_IMPORT_DB) {
                        res = doImport(uri);
                    } else if (req == REQ_SAVE_TEXT) {
                        res = doSaveText(uri, text == null ? "" : text);
                    } else if (req == REQ_PICK_PHOTO) {
                        res = doPickPhoto(uri);
                    } else {
                        res = doOpenText(uri);
                    }
                } catch (Throwable e) {
                    res = errObj(e.getMessage() == null ? e.toString() : e.getMessage());
                }
                callback(cb, res);
            }
        }).start();
    }

    // ── 내역 사진 (영수증) ───────────────────────────────
    /** 사진 고르기(camera=false: 앨범·파일) 또는 찍기(camera=true). 결과: {"ok":true,"b64":JPEG,"name","size"} */
    @JavascriptInterface
    public void pickPhoto(final boolean camera, final String cb) {
        startPicker(cb, null, new Runnable() {
            @Override
            public void run() {
                if (camera) {
                    File f = CaptureProvider.file(act);
                    File dir = f.getParentFile();
                    if (dir != null) {
                        dir.mkdirs();
                    }
                    f.delete();
                    Uri out = CaptureProvider.uri();
                    Intent it = new Intent(android.provider.MediaStore.ACTION_IMAGE_CAPTURE);
                    it.putExtra(android.provider.MediaStore.EXTRA_OUTPUT, out);
                    it.setClipData(android.content.ClipData.newRawUri("photo", out));
                    it.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    act.startActivityForResult(it, REQ_CAPTURE);
                } else {
                    Intent it = new Intent(Intent.ACTION_GET_CONTENT);
                    it.addCategory(Intent.CATEGORY_OPENABLE);
                    it.setType("image/*");
                    act.startActivityForResult(Intent.createChooser(it, "사진 고르기"), REQ_PICK_PHOTO);
                }
            }
        });
    }

    private JSONObject doPickPhoto(Uri uri) throws Exception {
        File tmp = File.createTempFile("photo", ".img", act.getCacheDir());
        try {
            InputStream in = act.getContentResolver().openInputStream(uri);
            if (in == null) {
                throw new IllegalStateException("사진을 열 수 없습니다.");
            }
            copy(in, new FileOutputStream(tmp));
            String name = "사진.jpg";
            Cursor c = null;
            try {
                c = act.getContentResolver().query(uri, new String[]{android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null);
                if (c != null && c.moveToFirst() && !c.isNull(0)) {
                    name = c.getString(0).replaceAll("\\.[A-Za-z0-9]{1,5}$", "") + ".jpg";
                }
            } catch (Exception ignored) {
            } finally {
                if (c != null) {
                    c.close();
                }
            }
            return photoFrom(tmp, name);
        } finally {
            tmp.delete();
        }
    }

    /** 사진 파일 → 긴 변 1600px·JPEG 82 (회전 정보대로 바로 세움, 투명은 흰 바탕) */
    private static JSONObject photoFrom(File src, String name) throws Exception {
        if (!src.isFile() || src.length() == 0) {
            throw new IllegalStateException("사진을 받지 못했습니다.");
        }
        android.graphics.BitmapFactory.Options o = new android.graphics.BitmapFactory.Options();
        o.inJustDecodeBounds = true;
        android.graphics.BitmapFactory.decodeFile(src.getPath(), o);
        if (o.outWidth <= 0 || o.outHeight <= 0) {
            throw new IllegalArgumentException("사진을 읽을 수 없습니다. JPG·PNG 사진을 골라 주세요.");
        }
        int side = Math.max(o.outWidth, o.outHeight), sample = 1;
        while (side / (sample * 2) >= PHOTO_SIDE) {
            sample *= 2;
        }
        android.graphics.BitmapFactory.Options o2 = new android.graphics.BitmapFactory.Options();
        o2.inSampleSize = sample;
        android.graphics.Bitmap bm = android.graphics.BitmapFactory.decodeFile(src.getPath(), o2);
        if (bm == null) {
            throw new IllegalArgumentException("사진을 읽을 수 없습니다.");
        }
        int w = bm.getWidth(), h = bm.getHeight();
        float sc = Math.min(1f, (float) PHOTO_SIDE / Math.max(w, h));
        android.graphics.Matrix mx = new android.graphics.Matrix();
        if (sc < 1f) {
            mx.postScale(sc, sc);
        }
        int rot = 0;
        try {
            int or = new android.media.ExifInterface(src.getPath()).getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION,
                    android.media.ExifInterface.ORIENTATION_NORMAL);
            rot = or == android.media.ExifInterface.ORIENTATION_ROTATE_90 ? 90
                    : or == android.media.ExifInterface.ORIENTATION_ROTATE_180 ? 180
                    : or == android.media.ExifInterface.ORIENTATION_ROTATE_270 ? 270 : 0;
        } catch (Exception ignored) {
            rot = 0;
        }
        if (rot != 0) {
            mx.postRotate(rot);
        }
        if (!mx.isIdentity()) {
            android.graphics.Bitmap b2 = android.graphics.Bitmap.createBitmap(bm, 0, 0, w, h, mx, true);
            if (b2 != bm) {
                bm.recycle();
            }
            bm = b2;
        }
        if (bm.hasAlpha()) {
            android.graphics.Bitmap b3 = android.graphics.Bitmap.createBitmap(bm.getWidth(), bm.getHeight(), android.graphics.Bitmap.Config.ARGB_8888);
            android.graphics.Canvas cv = new android.graphics.Canvas(b3);
            cv.drawColor(android.graphics.Color.WHITE);
            cv.drawBitmap(bm, 0, 0, null);
            bm.recycle();
            bm = b3;
        }
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        bm.compress(android.graphics.Bitmap.CompressFormat.JPEG, PHOTO_QUALITY, bo);
        bm.recycle();
        byte[] jpg = bo.toByteArray();
        JSONObject r = ok();
        r.put("b64", android.util.Base64.encodeToString(jpg, android.util.Base64.NO_WRAP));
        r.put("name", name);
        r.put("size", jpg.length);
        return r;
    }

    /** 사진을 내역에 붙임. 결과: {"ok":true,"id":번호} */
    @JavascriptInterface
    public synchronized String addAttachment(long entryId, String b64, String name) {
        try {
            needDb();
            byte[] data = android.util.Base64.decode(b64 == null ? "" : b64, android.util.Base64.DEFAULT);
            if (data.length == 0 || data.length > MAX_PHOTO) {
                throw new IllegalArgumentException("사진이 비었거나 너무 큽니다.");
            }
            SQLiteStatement st = db.compileStatement("INSERT INTO attachment(entry_id,name,mime,data,created) VALUES(?,?,?,?,?)");
            try {
                st.bindLong(1, entryId);
                st.bindString(2, name == null ? "" : name);
                st.bindString(3, "image/jpeg");
                st.bindBlob(4, data);
                st.bindString(5, new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.ROOT).format(new Date()));
                return ok().put("id", st.executeInsert()).toString();
            } finally {
                st.close();
            }
        } catch (Throwable e) {
            return err(e);
        }
    }

    /** 사진 내용. 결과: {"ok":true,"b64":...} */
    @JavascriptInterface
    public synchronized String attachmentData(long id) {
        Cursor c = null;
        try {
            needDb();
            c = db.rawQuery("SELECT data FROM attachment WHERE id=?", new String[]{String.valueOf(id)});
            if (!c.moveToFirst()) {
                throw new IllegalArgumentException("사진이 없습니다.");
            }
            return ok().put("b64", android.util.Base64.encodeToString(c.getBlob(0), android.util.Base64.NO_WRAP)).toString();
        } catch (Throwable e) {
            return err(e);
        } finally {
            if (c != null) {
                c.close();
            }
        }
    }

    // ── 홈 화면 위젯·밖에서 들어온 부탁 ──────────────────
    /** 내역이 바뀌면 홈 화면 위젯을 새로 그림 (다른 스레드에서, 화면을 붙잡지 않게) */
    @JavascriptInterface
    public void widgetRefresh() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                GagyebuWidget.refreshAll(act);
            }
        }).start();
    }

    private String launch;          // {"action":"new"} 또는 {"action":"sms","text":...}

    synchronized void setLaunch(String json) {
        launch = json;
    }

    /** 위젯의 [＋ 입력]·문자 공유로 열렸으면 그 부탁을 한 번 돌려줌 (없으면 "") */
    @JavascriptInterface
    public synchronized String takeLaunchAction() {
        String l = launch;
        launch = null;
        return l == null ? "" : l;
    }

    // ── 매일 입력 알림 (1.8.0, Reminder.java) ─────────────
    /** 알림 켜기·끄기와 시각. ask=true 면 안드로이드 13+ 에서 알림 권한을 물어봄 (앱을 켤 때 다시 걸 때는 묻지 않음) */
    @JavascriptInterface
    public String setReminder(boolean on, int hour, int minute, boolean ask) {
        try {
            SharedPreferences.Editor ed = prefs.edit();
            if (on) {
                ed.putString("remind_on", "true");
            } else {
                ed.remove("remind_on");
            }
            ed.putString("remind_time", String.format(Locale.ROOT, "%02d:%02d", Math.max(0, Math.min(23, hour)), Math.max(0, Math.min(59, minute))));
            ed.commit();
            Reminder.schedule(act);
            if (on && ask && Build.VERSION.SDK_INT >= 33
                    && act.checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                act.runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        act.requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 77);
                    }
                });
            }
            return ok().toString();
        } catch (Exception e) {
            return err(e);
        }
    }

    /** {"ok":true,"on":..,"time":"HH:MM","allowed":알림이 휴대폰 설정에서 허락됐는지} */
    @JavascriptInterface
    public String reminderStatus() {
        JSONObject o = ok();
        try {
            int[] hm = Reminder.time(act);
            o.put("on", Reminder.isOn(act)).put("time", String.format(Locale.ROOT, "%02d:%02d", hm[0], hm[1])).put("allowed", Reminder.allowed(act));
        } catch (Exception ignored) {
        }
        return o.toString();
    }

    /** 시험 알림 한 번 (권한이 없으면 물어보고 안내) */
    @JavascriptInterface
    public void testReminder(final String cb) {
        JSONObject r;
        try {
            if (Build.VERSION.SDK_INT >= 33
                    && act.checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                act.runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        act.requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 77);
                    }
                });
                r = new JSONObject().put("ok", false).put("error", "알림 권한을 허락한 뒤 다시 눌러 주세요.");
            } else if (!Reminder.allowed(act)) {
                r = new JSONObject().put("ok", false).put("error", "휴대폰 설정에서 이 앱의 알림이 꺼져 있어요.");
            } else {
                r = Reminder.show(act, true) ? ok() : new JSONObject().put("ok", false).put("error", "알림을 보내지 못했어요.");
            }
        } catch (Exception e) {
            r = errObj(e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage());
        }
        callback(cb, r);
    }

    /** "wt"(비우고 쓰기)를 먼저 쓰고, 지원하지 않는 곳이면 "w" */
    private OutputStream openForWrite(Uri uri) throws Exception {
        ContentResolver cr = act.getContentResolver();
        OutputStream out = null;
        try {
            out = cr.openOutputStream(uri, "wt");
        } catch (Exception ignored) {
            // 아래에서 "w" 로 다시
        }
        if (out == null) {
            out = cr.openOutputStream(uri, "w");
        }
        if (out == null) {
            throw new IllegalStateException("저장할 곳을 열 수 없습니다.");
        }
        return out;
    }

    private void deleteQuietly(Uri uri) {
        try {
            DocumentsContract.deleteDocument(act.getContentResolver(), uri);
        } catch (Exception ignored) {
        }
    }

    /** 지금 자료 파일의 온전한 사본 (잠금 안에서는 닫기 → 복사 → 다시 열기만, 짧게) */
    private void snapshotTo(File snap) throws Exception {
        synchronized (this) {
            needDb();
            if (txDepth > 0) {
                throw new IllegalStateException("저장 중인 작업이 끝난 뒤 다시 시도하세요.");
            }
            closeDb();
            try {
                copyFile(dbFile, snap);
            } finally {
                openDb();
            }
        }
    }

    private JSONObject doExport(Uri uri) throws Exception {
        File snap = File.createTempFile("export", ".sqlite3", act.getCacheDir());
        try {
            snapshotTo(snap);
            long size;
            try {
                OutputStream out = openForWrite(uri);
                size = copy(new FileInputStream(snap), out);
            } catch (Exception e) {
                deleteQuietly(uri);         // 반쯤 쓴 파일을 남기지 않음
                throw e;
            }
            JSONObject o = ok();
            o.put("size", size);
            return o;
        } finally {
            snap.delete();
        }
    }

    private JSONObject doImport(Uri uri) throws Exception {
        File tmp = File.createTempFile("incoming", ".sqlite3", act.getCacheDir());
        try {
            InputStream in = act.getContentResolver().openInputStream(uri);
            if (in == null) {
                throw new IllegalStateException("파일을 열 수 없습니다.");
            }
            copyChecked(in, tmp);
            String kept = replaceWith(tmp);
            JSONObject o = ok();
            o.put("kept", kept);
            return o;
        } finally {
            tmp.delete();
        }
    }

    /** 앞 16바이트가 SQLite 머리말인지 먼저 보고, 크기 상한 안에서만 복사 */
    private static void copyChecked(InputStream in, File dst) throws Exception {
        FileOutputStream out = new FileOutputStream(dst);
        try {
            byte[] head = new byte[16];
            int got = 0;
            while (got < 16) {
                int r = in.read(head, got, 16 - got);
                if (r < 0) {
                    break;
                }
                got += r;
            }
            if (got < 16 || !Arrays.equals(head, SQLITE_HEADER)) {
                throw new IllegalArgumentException("SQLite 자료 파일이 아닙니다. PC판에서 만든 백업 파일(gagyebu.sqlite3)을 고르세요.");
            }
            out.write(head);
            byte[] buf = new byte[64 * 1024];
            long n = 16;
            int r;
            while ((r = in.read(buf)) > 0) {
                n += r;
                if (n > MAX_DB) {
                    throw new IllegalArgumentException("파일이 너무 큽니다.");
                }
                out.write(buf, 0, r);
            }
            out.flush();
            out.getFD().sync();
        } finally {
            in.close();
            out.close();
        }
    }

    /** tmp 가 가계부 자료 파일인지 확인 → 지금 자료를 보관 → 한 번에 바꿔 끼움. 확인에 실패하면 지금 자료는 그대로. */
    private synchronized String replaceWith(File tmp) throws Exception {
        for (String ext : new String[]{"-journal", "-wal", "-shm"}) {
            new File(tmp.getPath() + ext).delete();
        }
        SQLiteDatabase t = null;
        try {
            t = SQLiteDatabase.openDatabase(tmp.getPath(), null, SQLiteDatabase.OPEN_READWRITE | SQLiteDatabase.NO_LOCALIZED_COLLATORS,
                    new DatabaseErrorHandler() {
                        @Override
                        public void onCorruption(SQLiteDatabase d) {
                            // 임시 사본이라 지워도 되지만, 아래에서 오류로 알리기 위해 아무것도 안 함
                        }
                    });
            Cursor c = t.rawQuery("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entry'", null);
            boolean okTable = c.moveToFirst();
            c.close();
            if (!okTable) {
                throw new IllegalArgumentException("우리집 가계부(새 버전) 백업 파일이 아닙니다.");
            }
            c = t.rawQuery("PRAGMA quick_check", null);
            String check = c.moveToFirst() ? c.getString(0) : "";
            c.close();
            if (!"ok".equalsIgnoreCase(check)) {
                throw new IllegalArgumentException("손상된 자료 파일입니다 (" + check + ").");
            }
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("SQLite 자료 파일이 아니거나 손상된 파일입니다.");
        } finally {
            if (t != null) {
                t.close();
            }
        }
        for (String ext : new String[]{"-journal", "-wal", "-shm"}) {
            new File(tmp.getPath() + ext).delete();
        }
        if (txDepth > 0) {
            throw new IllegalStateException("저장 중인 작업이 끝난 뒤 다시 시도하세요.");
        }
        // 같은 폴더에 새 파일을 다 써 둔 뒤 이름 바꾸기 (도중에 꺼져도 본 파일이 반쯤 쓰이지 않게)
        File part = new File(dbFile.getPath() + ".part");
        copyFile(tmp, part);
        closeDb();
        String keptName = null;
        try {
            if (dbFile.exists()) {
                String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(new Date());
                File kept = new File(keepDir(), "before-restore-" + stamp + ".sqlite3");
                int k = 1;
                while (kept.exists()) {
                    k++;
                    kept = new File(keepDir(), "before-restore-" + stamp + "-" + k + ".sqlite3");
                }
                copyFile(dbFile, kept);
                keptName = kept.getName();
                prune(keepDir(), 10);
            }
            for (String ext : new String[]{"-journal", "-wal", "-shm"}) {
                new File(dbFile.getPath() + ext).delete();
            }
            if (!part.renameTo(dbFile)) {
                throw new IllegalStateException("자료 파일을 바꾸지 못했습니다.");
            }
        } finally {
            part.delete();
            openDb();
        }
        return keptName;
    }

    private JSONObject doSaveText(Uri uri, String text) throws Exception {
        OutputStream out = openForWrite(uri);
        try {
            out.write(text.getBytes(StandardCharsets.UTF_8));
            out.flush();
        } catch (Exception e) {
            try {
                out.close();
            } catch (Exception ignored) {
            }
            deleteQuietly(uri);
            throw e;
        }
        out.close();
        return ok();
    }

    private JSONObject doOpenText(Uri uri) throws Exception {
        InputStream in = act.getContentResolver().openInputStream(uri);
        if (in == null) {
            throw new IllegalStateException("파일을 열 수 없습니다.");
        }
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        try {
            byte[] buf = new byte[64 * 1024];
            long n = 0;
            int r;
            while ((r = in.read(buf)) > 0) {
                n += r;
                if (n > MAX_TEXT) {
                    throw new IllegalArgumentException("파일이 너무 큽니다 (20MB까지).");
                }
                bo.write(buf, 0, r);
            }
        } finally {
            in.close();
        }
        JSONObject o = ok();
        o.put("text", Pure.decodeText(bo.toByteArray()));
        return o;
    }

    private static long copy(InputStream in, OutputStream out) throws Exception {
        long n = 0;
        try {
            byte[] buf = new byte[64 * 1024];
            int r;
            while ((r = in.read(buf)) > 0) {
                out.write(buf, 0, r);
                n += r;
            }
            out.flush();
            if (out instanceof FileOutputStream) {
                try {
                    ((FileOutputStream) out).getFD().sync();   // 앱 안 파일은 디스크에 확실히 기록
                } catch (Exception ignored) {
                    // 파이프로 받는 저장소(구글 드라이브 등)는 sync 를 지원하지 않음
                }
            }
        } finally {
            try {
                in.close();
            } finally {
                out.close();
            }
        }
        return n;
    }

    private static void copyFile(File src, File dst) throws Exception {
        copy(new FileInputStream(src), new FileOutputStream(dst));
    }

    // ── 새 버전 (GitHub 릴리스) ──────────────────────────
    // 가계부 자료는 보내지 않는다. 공개 릴리스 목록(JSON)을 읽고, 정해진 주소의 APK 만 받는다.
    private static final String RELEASES_API = "https://api.github.com/repos/jpnjb0918-glitch/gageybu/releases?per_page=30";
    private static final String DOWNLOAD_PREFIX = "https://github.com/jpnjb0918-glitch/gageybu/releases/download/";
    private static final String APK_NAME = "[A-Za-z0-9._-]+\\.apk";
    private volatile long updId = -1;

    /** 릴리스 목록을 받아 cb 로 {"ok":true,"body":"<JSON 글>"} (다른 스레드에서) */
    @JavascriptInterface
    public void fetchReleases(final String cb) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                JSONObject res;
                java.net.HttpURLConnection c = null;
                try {
                    c = (java.net.HttpURLConnection) new java.net.URL(RELEASES_API).openConnection();
                    c.setConnectTimeout(8000);
                    c.setReadTimeout(12000);
                    c.setRequestProperty("Accept", "application/vnd.github+json");
                    c.setRequestProperty("User-Agent", "gagyebu-android-updater");
                    int code = c.getResponseCode();
                    if (code != 200) {
                        throw new Exception("HTTP " + code);
                    }
                    InputStream in = c.getInputStream();
                    ByteArrayOutputStream bo = new ByteArrayOutputStream();
                    try {
                        byte[] buf = new byte[16384];
                        int n;
                        while ((n = in.read(buf)) > 0) {
                            bo.write(buf, 0, n);
                            if (bo.size() > 4 * 1024 * 1024) {
                                throw new Exception("응답이 너무 큽니다");
                            }
                        }
                    } finally {
                        in.close();
                    }
                    res = ok();
                    res.put("body", new String(bo.toByteArray(), StandardCharsets.UTF_8));
                } catch (Throwable e) {
                    res = errObj(e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage());
                } finally {
                    if (c != null) {
                        c.disconnect();
                    }
                }
                callback(cb, res);
            }
        }).start();
    }

    private File updDir() {
        return act.getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS);
    }

    /** 새 APK 받기 (시스템 내려받기 관리자 → 알림 창에도 진행 표시).
     *  진행: window.__updProgress(받은, 전체). 끝나면 cb 로 {"ok":true,"name":...} — 크기·SHA-256 이 맞을 때만.
     *  설치는 하지 않음 (설치할지 물은 뒤 installUpdate). */
    @JavascriptInterface
    public void downloadUpdate(final String url, final String fileName, final String size, final String sha256, final String cb) {
        if (url == null || !url.startsWith(DOWNLOAD_PREFIX) || fileName == null || !fileName.matches(APK_NAME)) {
            callback(cb, errObj("업데이트 파일 주소가 올바르지 않습니다"));
            return;
        }
        new Thread(new Runnable() {
            @Override
            public void run() {
                JSONObject res;
                try {
                    long expect = 0;
                    try {
                        expect = Long.parseLong(size);
                    } catch (Exception ignored) {
                    }
                    android.app.DownloadManager dm = (android.app.DownloadManager) act.getSystemService(android.content.Context.DOWNLOAD_SERVICE);
                    File dir = updDir();
                    if (dm == null || dir == null) {
                        throw new Exception("이 휴대폰에서는 내려받기를 쓸 수 없습니다");
                    }
                    if (updId >= 0) {
                        try {
                            dm.remove(updId);
                        } catch (Exception ignored) {
                        }
                    }
                    File[] olds = dir.listFiles();               // 예전에 받은 APK 정리
                    if (olds != null) {
                        for (File f : olds) {
                            f.delete();
                        }
                    }
                    android.app.DownloadManager.Request rq = new android.app.DownloadManager.Request(Uri.parse(url));
                    rq.setTitle("우리집 가계부 새 버전");
                    rq.setDescription(fileName);
                    rq.setMimeType("application/vnd.android.package-archive");
                    rq.setNotificationVisibility(android.app.DownloadManager.Request.VISIBILITY_VISIBLE);
                    rq.setDestinationInExternalFilesDir(act, android.os.Environment.DIRECTORY_DOWNLOADS, fileName);
                    long id = dm.enqueue(rq);
                    updId = id;
                    while (true) {
                        Thread.sleep(500);
                        Cursor q = dm.query(new android.app.DownloadManager.Query().setFilterById(id));
                        if (q == null) {
                            throw new Exception("내려받기 상태를 알 수 없습니다");
                        }
                        int st;
                        long got, tot;
                        int reason;
                        try {
                            if (!q.moveToFirst()) {
                                throw new Exception("내려받기가 취소되었습니다");
                            }
                            st = q.getInt(q.getColumnIndex(android.app.DownloadManager.COLUMN_STATUS));
                            got = q.getLong(q.getColumnIndex(android.app.DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                            tot = q.getLong(q.getColumnIndex(android.app.DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                            reason = q.getInt(q.getColumnIndex(android.app.DownloadManager.COLUMN_REASON));
                        } finally {
                            q.close();
                        }
                        updProgress(got, tot > 0 ? tot : expect);
                        if (st == android.app.DownloadManager.STATUS_SUCCESSFUL) {
                            break;
                        }
                        if (st == android.app.DownloadManager.STATUS_FAILED) {
                            throw new Exception("내려받지 못했습니다 (이유 코드 " + reason + ")");
                        }
                    }
                    File f = new File(dir, fileName);
                    if (!f.isFile() || (expect > 0 && f.length() != expect)) {
                        throw new Exception("받은 파일 크기가 릴리스에 적힌 것과 다릅니다");
                    }
                    if (sha256 != null && !sha256.isEmpty() && !sha256.equalsIgnoreCase(sha256Hex(f))) {
                        dm.remove(id);
                        f.delete();
                        throw new Exception("받은 파일이 릴리스에 적힌 것과 다릅니다 (SHA-256)");
                    }
                    res = ok();
                    res.put("name", fileName);
                } catch (Throwable e) {
                    res = errObj(e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage());
                }
                callback(cb, res);
            }
        }).start();
    }

    /** 받아 둔 APK 가 있는지 */
    @JavascriptInterface
    public boolean hasUpdateFile(String fileName) {
        File dir = updDir();
        return dir != null && fileName != null && fileName.matches(APK_NAME) && new File(dir, fileName).isFile();
    }

    /** 받아 둔 APK 의 설치 화면 열기 (안드로이드가 '이 출처 허용'과 설치 확인을 따로 물음) */
    @JavascriptInterface
    public String installUpdate(String fileName) {
        try {
            File dir = updDir();
            if (dir == null || fileName == null || !fileName.matches(APK_NAME) || !new File(dir, fileName).isFile()) {
                return errObj("받아 둔 설치 파일이 없습니다. 다시 내려받아 주세요.").toString();
            }
            android.app.DownloadManager dm = (android.app.DownloadManager) act.getSystemService(android.content.Context.DOWNLOAD_SERVICE);
            long id = updId;
            if (id < 0) {                    // 앱을 다시 켠 뒤: 내려받기 목록에서 그 파일 찾기
                Cursor q = dm.query(new android.app.DownloadManager.Query().setFilterByStatus(android.app.DownloadManager.STATUS_SUCCESSFUL));
                if (q != null) {
                    try {
                        while (q.moveToNext()) {
                            String local = q.getString(q.getColumnIndex(android.app.DownloadManager.COLUMN_LOCAL_URI));
                            if (local != null && local.endsWith("/" + fileName)) {
                                id = q.getLong(q.getColumnIndex(android.app.DownloadManager.COLUMN_ID));
                            }
                        }
                    } finally {
                        q.close();
                    }
                }
            }
            Uri uri = id >= 0 ? dm.getUriForDownloadedFile(id) : null;
            if (uri == null) {
                return errObj("받아 둔 설치 파일을 찾지 못했습니다. 다시 내려받아 주세요.").toString();
            }
            final Intent it = new Intent(Intent.ACTION_VIEW);
            it.setDataAndType(uri, "application/vnd.android.package-archive");
            it.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            act.runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        act.startActivity(it);
                    } catch (Exception ignored) {
                    }
                }
            });
            return ok().toString();
        } catch (Throwable e) {
            return err(e);
        }
    }

    private void updProgress(long got, long total) {
        final String js = "window.__updProgress&&window.__updProgress(" + got + "," + total + ")";
        web.post(new Runnable() {
            @Override
            public void run() {
                web.evaluateJavascript(js, null);
            }
        });
    }

    private static String sha256Hex(File f) throws Exception {
        java.security.MessageDigest md = java.security.MessageDigest.getInstance("SHA-256");
        InputStream in = new FileInputStream(f);
        try {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) {
                md.update(buf, 0, n);
            }
        } finally {
            in.close();
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : md.digest()) {
            sb.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        }
        return sb.toString();
    }

    private void callback(String cb, JSONObject res) {
        if (cb == null) {
            return;
        }
        final String js = "window.__nativeDone&&window.__nativeDone(" + JSONObject.quote(cb) + "," + res.toString() + ")";
        web.post(new Runnable() {
            @Override
            public void run() {
                web.evaluateJavascript(js, null);
            }
        });
    }
}
