package kr.gagyebu.mobile;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * 앱 캐시 안의 파일 하나를 다른 앱에 잠깐 내어 주는 곳의 공통 부분 (CaptureProvider · ShareProvider).
 * 어떤 파일을 내어 줄지(fileOf)와 파일 형식(getType)·열기 방식(openFile)만 각자 정한다.
 * 다른 앱이 마음대로 열 수는 없음 (exported=false, 부탁한 앱에게만 grantUriPermissions).
 */
abstract class CacheFileProvider extends ContentProvider {

    /** uri 가 가리키는 파일 (허락하지 않는 이름이면 FileNotFoundException) */
    abstract File fileOf(Uri uri) throws FileNotFoundException;

    static Uri uriOf(String authority, String name) {
        return new Uri.Builder().scheme("content").authority(authority).appendPath(name).build();
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    /** 받는 앱이 파일 이름·크기를 물을 때 */
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
                row[i] = f.getName();
            } else if (OpenableColumns.SIZE.equals(cols[i])) {
                row[i] = f.length();
            }
        }
        c.addRow(row);
        return c;
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
