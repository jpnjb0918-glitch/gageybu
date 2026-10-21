package kr.gagyebu.mobile;

import android.content.Context;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * 백업 파일을 다른 앱(카카오톡·디스코드·메일·드라이브 등)으로 '보내기' 할 때 읽기 전용으로 내어 주는 곳.
 * 앱 캐시의 share/ 폴더 안 파일만, 공유 창에서 고른 앱에게 잠깐(읽기 권한 부여) 보여 준다. 다른 앱이 마음대로 열 수는 없음(exported=false).
 * content://kr.gagyebu.mobile.share/<파일 이름>
 */
public class ShareProvider extends CacheFileProvider {
    static final String AUTHORITY = "kr.gagyebu.mobile.share";

    static File dir(Context ctx) {
        return new File(ctx.getCacheDir(), "share");
    }

    static Uri uriFor(String name) {
        return uriOf(AUTHORITY, name);
    }

    @Override
    File fileOf(Uri uri) throws FileNotFoundException {
        String name = uri.getLastPathSegment();
        if (name == null || name.isEmpty() || name.contains("/") || name.contains("..")) {
            throw new FileNotFoundException("잘못된 파일 이름");
        }
        File f = new File(dir(getContext()), name);
        if (!f.isFile()) {
            throw new FileNotFoundException(name);
        }
        return f;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (mode != null && !"r".equals(mode)) {
            throw new FileNotFoundException("읽기만 됩니다");
        }
        return ParcelFileDescriptor.open(fileOf(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        return "application/octet-stream";
    }
}
