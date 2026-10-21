package kr.gagyebu.mobile;

import android.app.Activity;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.database.DatabaseErrorHandler;
import android.database.sqlite.SQLiteDatabase;
import android.view.View;
import android.widget.RemoteViews;

import java.io.File;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * 홈 화면 위젯 '가계부 한눈에': 오늘 지출 · 이번 달 지출 · 이달 예산 남은 돈(막대) + [＋ 입력].
 * 자료 파일을 읽기만 한다. 앱에 암호가 걸려 있으면 금액을 숨긴다 (홈 화면은 누구나 보므로).
 * 앱에서 내역을 저장하면 NativeBridge.widgetRefresh 로 바로, 그 밖에는 30분마다 새로 그린다.
 */
public class GagyebuWidget extends AppWidgetProvider {
    static final String ACTION_NEW = "kr.gagyebu.mobile.NEW_ENTRY";

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        update(ctx, mgr, ids);
    }

    /** 놓인 위젯 모두 새로 그리기 (없으면 아무것도 안 함) */
    static void refreshAll(Context ctx) {
        try {
            AppWidgetManager mgr = AppWidgetManager.getInstance(ctx);
            int[] ids = mgr.getAppWidgetIds(new ComponentName(ctx, GagyebuWidget.class));
            if (ids != null && ids.length > 0) {
                update(ctx, mgr, ids);
            }
        } catch (Exception ignored) {
            // 위젯은 덤 — 실패해도 앱은 그대로
        }
    }

    static void update(Context ctx, AppWidgetManager mgr, int[] ids) {
        Summary s = Summary.read(ctx);
        for (int id : ids) {
            RemoteViews v = new RemoteViews(ctx.getPackageName(), R.layout.widget);
            v.setTextViewText(R.id.w_title, s.title);
            v.setTextViewText(R.id.w_today, s.today);
            v.setTextViewText(R.id.w_month, s.month);
            v.setTextViewText(R.id.w_extra, s.extra);
            v.setViewVisibility(R.id.w_bar, s.barPct >= 0 ? View.VISIBLE : View.GONE);
            if (s.barPct >= 0) {
                v.setProgressBar(R.id.w_bar, 100, Math.min(100, s.barPct), false);
            }
            Intent open = new Intent(ctx, MainActivity.class);
            open.setAction(Intent.ACTION_MAIN);
            open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(ctx, 1, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
            Intent add = new Intent(ctx, MainActivity.class);
            add.setAction(ACTION_NEW);
            add.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            v.setOnClickPendingIntent(R.id.w_add, PendingIntent.getActivity(ctx, 2, add,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
            mgr.updateAppWidget(id, v);
        }
    }

    /** 위젯에 쓸 글 (자료 파일에서 읽음) */
    static final class Summary {
        String title = "우리집 가계부", today = "", month = "", extra = "";
        int barPct = -1;

        static Summary read(Context ctx) {
            Summary s = new Summary();
            File f = ctx.getDatabasePath("gagyebu.sqlite3");
            if (!f.isFile()) {
                s.today = "아직 자료가 없어요";
                s.month = "앱을 열어 첫 내역을 넣어 보세요";
                return s;
            }
            SQLiteDatabase db = null;
            try {
                // 손상을 발견해도 파일을 지우지 않게 (안드로이드 기본 처리기는 지워 버림 — 앱이 열 때 따로 옮겨 보관함)
                db = SQLiteDatabase.openDatabase(f.getPath(), null,
                        SQLiteDatabase.OPEN_READWRITE | SQLiteDatabase.NO_LOCALIZED_COLLATORS, new DatabaseErrorHandler() {
                            @Override
                            public void onCorruption(SQLiteDatabase bad) {
                                // 아무것도 하지 않음
                            }
                        });
                String pw = one(db, "SELECT value FROM meta WHERE key='password'", null);
                long lid = -1;
                try {
                    lid = Long.parseLong(ctx.getSharedPreferences("gagyebu_prefs", Activity.MODE_PRIVATE).getString("last_lid", "-1"));
                } catch (Exception ignored) {
                    lid = -1;
                }
                String name = one(db, "SELECT name FROM ledger WHERE id=?", new String[]{String.valueOf(lid)});
                if (name == null) {
                    Cursor c = db.rawQuery("SELECT id, name FROM ledger ORDER BY sort, id LIMIT 1", null);
                    try {
                        if (c.moveToFirst()) {
                            lid = c.getLong(0);
                            name = c.getString(1);
                        }
                    } finally {
                        c.close();
                    }
                }
                s.title = name == null ? "우리집 가계부" : name;
                if (pw != null && !pw.isEmpty()) {
                    s.today = "암호가 걸려 있어 금액은 숨겼어요";
                    s.month = "눌러서 앱 열기";
                    return s;
                }
                String L = String.valueOf(lid);
                String today = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date());
                int y = Integer.parseInt(today.substring(0, 4)), m = Integer.parseInt(today.substring(5, 7));
                long texp = num(db, "SELECT COALESCE(SUM(expense),0) FROM entry WHERE ledger_id=? AND date=?", new String[]{L, today});
                long mexp = num(db, "SELECT COALESCE(SUM(expense),0) FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ?",
                        new String[]{L, Pure.iso(y, m, 1), Pure.iso(y, m, Pure.monthEnd(y, m))});
                s.today = "오늘 지출 " + Pure.money(texp) + "원";
                s.month = m + "월 지출 " + Pure.money(mexp) + "원";
                // 이달 예산 (결산일 기준 그 달, 지출 계정 예산만)
                int sd = 1;
                try {
                    sd = Integer.parseInt(one(db, "SELECT value FROM meta WHERE key='settle_day'", null));
                } catch (Exception ignored) {
                    sd = 1;
                }
                int[] pm = Pure.periodOf(today, sd);
                String[] per = Pure.settlePeriod(pm[0], pm[1], sd);
                Map<String, Long> bud = new HashMap<>();
                Cursor c = db.rawQuery("SELECT code, amount FROM budget WHERE ledger_id=? AND ym=? AND amount>0 AND substr(code,1,1)<>'0'",
                        new String[]{L, String.format(Locale.ROOT, "%04d-%02d", pm[0], pm[1])});
                try {
                    while (c.moveToNext()) {
                        bud.put(c.getString(0), c.getLong(1));
                    }
                } finally {
                    c.close();
                }
                // 한 달 전체 예산 (1.8.0): meta 'budget_total:<가계부>' = {"2026-10": 금액} — 있으면 지출 전체 / 전체 예산
                long totalBudget = 0;
                try {
                    String tj = one(db, "SELECT value FROM meta WHERE key=?", new String[]{"budget_total:" + L});
                    if (tj != null) {
                        totalBudget = Math.max(0, new org.json.JSONObject(tj).optLong(String.format(Locale.ROOT, "%04d-%02d", pm[0], pm[1]), 0));
                    }
                } catch (Exception ignored) {
                    totalBudget = 0;
                }
                if (bud.isEmpty() && totalBudget <= 0) {
                    long bal = num(db, "SELECT COALESCE(SUM(income)-SUM(expense),0) FROM entry WHERE ledger_id=? AND date<=?", new String[]{L, today});
                    s.extra = "잔액 " + Pure.money(bal) + "원";
                    return s;
                }
                long total = 0, spent = 0;
                for (long b : bud.values()) {
                    total += b;
                }
                if (totalBudget > 0) {
                    total = totalBudget;
                }
                c = db.rawQuery("SELECT code, COALESCE(SUM(income),0), COALESCE(SUM(expense),0) FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY code",
                        new String[]{L, per[0], per[1]});
                try {
                    while (c.moveToNext()) {
                        String code = c.getString(0);
                        boolean isExp = code != null && !code.startsWith("0");
                        if (totalBudget > 0 ? isExp : bud.containsKey(code)) {
                            spent += c.getLong(2) - c.getLong(1);
                        }
                    }
                } finally {
                    c.close();
                }
                long left = total - spent;
                s.barPct = total > 0 ? (int) Math.max(0, Math.min(999, Math.floor(spent * 100.0 / total + 0.5))) : 0;
                if (left < 0) {
                    s.extra = "예산보다 " + Pure.money(-left) + "원 더 썼어요";
                } else {
                    long days = Math.max(1, daysBetween(today, per[1]) + 1);
                    s.extra = (totalBudget > 0 ? "전체 예산 남은 돈 " : "예산 남은 돈 ") + Pure.money(left) + "원 · 하루 " + Pure.money(left / days) + "원";
                }
            } catch (Exception e) {
                s.today = "자료를 읽지 못했어요";
                s.month = "눌러서 앱 열기";
                s.extra = "";
                s.barPct = -1;
            } finally {
                if (db != null) {
                    try {
                        db.close();
                    } catch (Exception ignored) {
                    }
                }
            }
            return s;
        }

        private static String one(SQLiteDatabase db, String sql, String[] args) {
            Cursor c = db.rawQuery(sql, args);
            try {
                return c.moveToFirst() && !c.isNull(0) ? c.getString(0) : null;
            } finally {
                c.close();
            }
        }

        private static long num(SQLiteDatabase db, String sql, String[] args) {
            Cursor c = db.rawQuery(sql, args);
            try {
                return c.moveToFirst() ? c.getLong(0) : 0;
            } finally {
                c.close();
            }
        }

        private static long daysBetween(String a, String b) {
            try {
                SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
                f.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
                return (f.parse(b).getTime() - f.parse(a).getTime()) / 86400000L;
            } catch (Exception e) {
                return 0;
            }
        }
    }
}
