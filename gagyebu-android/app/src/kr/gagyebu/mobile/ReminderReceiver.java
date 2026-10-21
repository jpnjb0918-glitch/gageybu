package kr.gagyebu.mobile;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** 매일 입력 알림: 알람이 울리면 오늘 적은 내역이 없을 때만 알리고 다음 날 알람을 건다. 휴대폰을 켜거나 앱을 업데이트하면 다시 건다. */
public class ReminderReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        String a = intent == null ? null : intent.getAction();
        try {
            if (Reminder.ACTION_REMIND.equals(a) && Reminder.isOn(ctx) && !Reminder.hasEntryToday(ctx)) {
                Reminder.show(ctx, false);
            }
        } catch (Exception ignored) {
            // 알림은 덤 — 실패해도 다음 날 알람은 건다
        }
        Reminder.schedule(ctx);
    }
}
