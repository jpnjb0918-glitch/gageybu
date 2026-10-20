package kr.gagyebu.mobile;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * 영수증 사진 찍기: 사진기 앱이 찍은 사진을 써 넣을 곳 (앱 캐시의 capture/photo.jpg 하나만).
 * 찍기를 부탁한 사진기 앱에게만 잠깐 쓰기 권한을 준다 (exported=false, grantUriPermissions=true).
 * content://kr.gagyebu.mobile.capture/photo.jpg
 */
public class CaptureProvider extends ContentProvider {
    static final String AUTHORITY = "kr.gagyebu.mobile.capture";
    static final String NAME = "photo.jpg";

    static File file(Context ctx) {
        return new File(new File(ctx.getCacheDir(), "capture"), NAME);
    }

    static Uri uri() {
        return new Uri.Builder().scheme("content").authority(AUTHORITY).appendPath(NAME).build();
    }

    private File fileOf(Uri uri) throws FileNotFoundException {
        if (!NAME.equals(uri.getLastPathSegment())) {
            throw new FileNotFoundException("잘못된 파일 이름");
        }
        File f = file(getContext());
        File dir = f.getParentFile();
        if (dir != null && !dir.isDirectory() && !dir.mkdirs()) {
            throw new FileNotFoundException("사진을 둘 곳을 만들 수 없습니다");
        }
        return f;
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        File f = fileOf(uri);
        int m;
        if (mode == null || "r".equals(mode)) {
            m = ParcelFileDescriptor.MODE_READ_ONLY;
        } else {
            m = ParcelFileDescriptor.MODE_READ_WRITE | ParcelFileDescriptor.MODE_CREATE;
            if (mode.contains("t") || "w".equals(mode)) {
                m |= ParcelFileDescriptor.MODE_TRUNCATE;
            }
        }
        return ParcelFileDescriptor.open(f, m);
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        File f;
        try {
            f = fileOf(uri);
        } catch (FileNotFoundException e) {
            return null;
        }
        String[] cols = projection != null ? projection : new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
        MatrixCursor c = new MatrixCursor(cols, 1);
        Object[] row = new Object[cols.length];
        for (int i = 0; i < cols.length; i++) {
            if (OpenableColumns.DISPLAY_NAME.equals(cols[i])) {
                row[i] = NAME;
            } else if (OpenableColumns.SIZE.equals(cols[i])) {
                row[i] = f.length();
            }
        }
        c.addRow(row);
        return c;
    }

    @Override
    public String getType(Uri uri) {
        return "image/jpeg";
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException();
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        throw new UnsupportedOperationException();
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        throw new UnsupportedOperationException();
    }
}
