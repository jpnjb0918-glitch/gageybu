package android.webkit;

/** 컴파일할 때만 쓰는 빈 껍데기 (실제 클래스는 안드로이드 8.0/API 26 에 있음). APK 에는 넣지 않는다. */
public abstract class RenderProcessGoneDetail {
    public abstract boolean didCrash();

    public abstract int rendererPriorityAtExit();
}
