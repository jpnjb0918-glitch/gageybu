package kr.gagyebu.mobile;

import android.content.Context;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * 영수증 사진 찍기: 사진기 앱이 찍은 사진을 써 넣을 곳 (앱 캐시의 capture/photo.jpg 하나만).
 * 찍기를 부탁한 사진기 앱에게만 잠깐 쓰기 권한을 준다 (exported=false, grantUriPermissions=true).
 * content://kr.gagyebu.mobile.capture/photo.jpg
 */
public class CaptureProvider extends CacheFileProvider {
    static final String AUTHORITY = "kr.gagyebu.mobile.capture";
    static final String NAME = "photo.jpg";

    static File file(Context ctx) {
        return new File(new File(ctx.getCacheDir(), "capture"), NAME);
    }

    static Uri uri() {
        return uriOf(AUTHORITY, NAME);
    }

    @Override
    File fileOf(Uri uri) throws FileNotFoundException {
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
    public String getType(Uri uri) {
        return "image/jpeg";
    }
}
