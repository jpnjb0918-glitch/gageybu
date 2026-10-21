package kr.gagyebu.mobile;

import android.app.Activity;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.database.DatabaseErrorHandler;
import android.database.sqlite.SQLiteDatabase;
import android.os.Build;

import java.io.File;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;

/**
 * 매일 입력 알림 (1.8.0): 정한 시각에 그날 적은 내역이 하나도 없으면 "오늘 쓴 돈을 적어 볼까요?" 알림.
 * 설정은 기기별 설정(gagyebu_prefs)의 remind_on("true") · remind_time("HH:MM") — 화면(설정 › 매일 입력 알림)에서 바꾼다.
 * 알림을 누르면 위젯의 [＋ 입력]과 같이 새 내역 입력 창이 열린다.
 * 절전(도즈) 중에도 울리도록 하루에 한 번씩 setAndAllowWhileIdle 로 다음 알림을 건다 (정확한 알람 권한은 쓰지 않음 → 몇 분 늦을 수 있음).
 */
final class Reminder {
    static final String ACTION_REMIND = "kr.gagyebu.mobile.REMIND";
    private static final String CHANNEL = "daily_entry";
    private static final int NOTE_ID = 3001;

    private Reminder() {
    }

    static SharedPreferences prefs(Context ctx) {
        return ctx.getSharedPreferences("gagyebu_prefs", Activity.MODE_PRIVATE);
    }

    static boolean isOn(Context ctx) {
        return "true".equals(prefs(ctx).getString("remind_on", ""));
    }

    /** "HH:MM" → {시, 분} (잘못되면 21:00) */
    static int[] time(Context ctx) {
        String t = prefs(ctx).getString("remind_time", "21:00");
        try {
            int h = Integer.parseInt(t.substring(0, 2)), m = Integer.parseInt(t.substring(3, 5));
            if (h >= 0 && h < 24 && m >= 0 && m < 60) {
                return new int[]{h, m};
            }
        } catch (Exception ignored) {
            // 아래 기본값
        }
        return new int[]{21, 0};
    }

    private static PendingIntent alarmIntent(Context ctx) {
        Intent i = new Intent(ctx, ReminderReceiver.class).setAction(ACTION_REMIND);
        return PendingIntent.getBroadcast(ctx, 10, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** 켜져 있으면 다음 알림 시각에 알람을 걸고, 꺼져 있으면 걸어 둔 알람을 지움 */
    static void schedule(Context ctx) {
        AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        PendingIntent pi = alarmIntent(ctx);
        am.cancel(pi);
        if (!isOn(ctx)) {
            return;
        }
        int[] hm = time(ctx);
        Calendar c = Calendar.getInstance();
        c.set(Calendar.HOUR_OF_DAY, hm[0]);
        c.set(Calendar.MINUTE, hm[1]);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        if (c.getTimeInMillis() <= System.currentTimeMillis() + 1000) {
            c.add(Calendar.DAY_OF_YEAR, 1);
        }
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, c.getTimeInMillis(), pi);
    }

    /** 오늘 날짜로 적은 내역이 (어느 가계부든) 하나라도 있는지. 자료를 못 읽으면 false (알림을 보냄) */
    static boolean hasEntryToday(Context ctx) {
        File f = ctx.getDatabasePath("gagyebu.sqlite3");
        if (!f.isFile()) {
            return false;
        }
        SQLiteDatabase db = null;
        try {
            db = SQLiteDatabase.openDatabase(f.getPath(), null,
                    SQLiteDatabase.OPEN_READONLY | SQLiteDatabase.NO_LOCALIZED_COLLATORS, new DatabaseErrorHandler() {
                        @Override
                        public void onCorruption(SQLiteDatabase bad) {
                            // 손상돼도 파일을 지우지 않음 (앱이 열 때 따로 옮겨 보관함)
                        }
                    });
            String today = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date());
            Cursor c = db.rawQuery("SELECT 1 FROM entry WHERE date=? LIMIT 1", new String[]{today});
            try {
                return c.moveToFirst();
            } finally {
                c.close();
            }
        } catch (Exception e) {
            return false;
        } finally {
            if (db != null) {
                try {
                    db.close();
                } catch (Exception ignored) {
                }
            }
        }
    }

    /** 알림 채널 (안드로이드 8.0+). android-23 으로 컴파일하므로 리플렉션으로 만든다 */
    private static void ensureChannel(Context ctx, NotificationManager nm) {
        if (Build.VERSION.SDK_INT < 26) {
            return;
        }
        try {
            Class<?> chc = Class.forName("android.app.NotificationChannel");
            Object ch = chc.getConstructor(String.class, CharSequence.class, int.class)
                    .newInstance(CHANNEL, "매일 입력 알림", 3 /* IMPORTANCE_DEFAULT */);
            chc.getMethod("setDescription", String.class).invoke(ch, "그날 적은 내역이 없을 때 정한 시각에 알려 줍니다");
            NotificationManager.class.getMethod("createNotificationChannel", chc).invoke(nm, ch);
        } catch (Exception ignored) {
            // 채널을 못 만들면 알림이 안 보일 수 있음 (덤 기능)
        }
    }

    private static Notification.Builder builder(Context ctx) {
        if (Build.VERSION.SDK_INT >= 26) {
            try {
                return Notification.Builder.class.getConstructor(Context.class, String.class).newInstance(ctx, CHANNEL);
            } catch (Exception ignored) {
                // 아래 옛 방식
            }
        }
        return new Notification.Builder(ctx);
    }

    /** 휴대폰 설정에서 이 앱의 알림을 껐으면 false */
    static boolean allowed(Context ctx) {
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) {
            return false;
        }
        if (Build.VERSION.SDK_INT >= 33
                && ctx.checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            return false;
        }
        try {                          // areNotificationsEnabled 는 API 24 (android-23 으로 컴파일하므로 리플렉션)
            return (Boolean) NotificationManager.class.getMethod("areNotificationsEnabled").invoke(nm);
        } catch (Exception e) {
            return true;
        }
    }

    /** 알림 보내기. test=true 면 시험 알림 (글만 다름) */
    static boolean show(Context ctx, boolean test) {
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) {
            return false;
        }
        ensureChannel(ctx, nm);
        Intent open = new Intent(ctx, MainActivity.class);
        open.setAction(GagyebuWidget.ACTION_NEW);
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi = PendingIntent.getActivity(ctx, 11, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String text = test ? "알림 시험: 정한 시각에 이렇게 알려 드려요. 누르면 새 내역 입력 창이 열려요."
                : "오늘 쓴 돈을 아직 안 적었어요. 눌러서 바로 적어 볼까요?";
        Notification n = builder(ctx)
                .setSmallIcon(R.drawable.ic_notify)
                .setColor(0xFF139A9A)
                .setContentTitle("우리집 가계부")
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .setCategory(Notification.CATEGORY_REMINDER)
                .build();
        try {
            nm.notify(NOTE_ID, n);
            return true;
        } catch (Exception e) {
            return false;            // 알림 권한이 없는 경우 등
        }
    }
}
