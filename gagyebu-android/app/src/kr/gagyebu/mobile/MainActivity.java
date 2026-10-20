package kr.gagyebu.mobile;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

/** 화면은 앱 안에 든 웹 페이지(assets/www)로 그리고, 자료는 NativeBridge 가 SQLite 파일에 저장한다. */
public class MainActivity extends Activity {
    private WebView web;
    private NativeBridge bridge;
    private boolean resumed;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        try {
            web = new WebView(this);
        } catch (Exception e) {
            // WebView 가 업데이트 중이거나 없는 기기
            TextView t = new TextView(this);
            t.setText("화면 엔진(Android System WebView)을 불러오지 못했습니다.\n플레이 스토어에서 'Android System WebView'를 업데이트한 뒤 다시 여세요.");
            t.setGravity(Gravity.CENTER);
            t.setPadding(48, 48, 48, 48);
            setContentView(t);
            return;
        }
        WebSettings ws = web.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setAllowContentAccess(false);
        ws.setTextZoom(100);            // 시스템 글자 크기와 관계없이 배치 유지 (앱 안 설정에서 글자 크기 조절)
        ws.setSupportZoom(false);
        bridge = new NativeBridge(this, web);
        web.addJavascriptInterface(bridge, "GagyebuNative");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url.startsWith("file:///android_asset/")) {
                    return false;
                }
                openExternal(url);       // 전화(tel:)·메일(mailto:)·웹 주소는 다른 앱으로
                return true;
            }

            /** 안드로이드 8.0+: 화면 엔진이 죽으면 앱 전체가 꺼지지 않게 화면만 다시 만듦 (8.0 미만에서는 불리지 않음) */
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                if (view.getParent() instanceof ViewGroup) {
                    ((ViewGroup) view.getParent()).removeView(view);
                }
                view.destroy();
                if (view == web) {
                    web = null;
                }
                if (!isFinishing()) {
                    recreate();
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient());
        handleIntent(getIntent());
        web.loadUrl("file:///android_asset/www/index.html");
        setContentView(web);
    }

    /** 위젯의 [＋ 입력]·문자 앱에서 '공유'로 열렸을 때: 부탁을 적어 두고, 화면이 떠 있으면 바로 알림 */
    private void handleIntent(Intent it) {
        if (it == null || bridge == null) {
            return;
        }
        String json = null;
        try {
            if (GagyebuWidget.ACTION_NEW.equals(it.getAction())) {
                json = new org.json.JSONObject().put("action", "new").toString();
            } else if (Intent.ACTION_SEND.equals(it.getAction())) {
                CharSequence t = it.getCharSequenceExtra(Intent.EXTRA_TEXT);
                if (t != null && t.length() > 0) {
                    String text = t.toString();
                    if (text.length() > 20000) {
                        text = text.substring(0, 20000);
                    }
                    json = new org.json.JSONObject().put("action", "sms").put("text", text).toString();
                }
            }
        } catch (Exception ignored) {
            json = null;
        }
        if (json == null) {
            return;
        }
        bridge.setLaunch(json);
        it.setAction(Intent.ACTION_MAIN);          // 화면을 다시 만들 때(회전 등) 또 하지 않게
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
        if (web != null) {
            web.evaluateJavascript("window.App&&App.onLaunch&&App.onLaunch()", null);
        }
    }

    void openExternal(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignored) {
            // 열 수 있는 앱이 없으면 무시
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
    }

    @Override
    protected void onPause() {
        resumed = false;
        super.onPause();
    }

    @Override
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        // 열린 창·하위 화면이 있으면 웹 화면이 먼저 닫고, 없으면 앱 종료
        web.evaluateJavascript("(window.App&&App.onBack)?String(App.onBack()):'false'", new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String v) {
                if (!resumed || isFinishing() || isDestroyed()) {
                    return;              // 그사이 화면을 떠났으면 아무것도 안 함
                }
                if (!"\"true\"".equals(v)) {
                    MainActivity.super.onBackPressed();
                }
            }
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (bridge != null) {
            bridge.onActivityResult(requestCode, resultCode, data);
        }
    }

    @Override
    protected void onDestroy() {
        if (bridge != null) {
            bridge.shutdown();
        }
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }
}
