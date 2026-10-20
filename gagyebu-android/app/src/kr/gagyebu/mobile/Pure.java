package kr.gagyebu.mobile;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** 안드로이드에 기대지 않는 계산 (PC의 자바로도 시험할 수 있게 따로 둠). */
final class Pure {
    private Pure() {
    }

    /** PBKDF2-HMAC-SHA256, 32바이트 (PC판 hashlib.pbkdf2_hmac('sha256', ...) 와 같음) */
    static String pbkdf2Hex(String password, String saltHex, int iterations) throws Exception {
        byte[] key = password.getBytes(StandardCharsets.UTF_8);
        if (key.length == 0) {
            key = new byte[1];       // HMAC 은 짧은 키를 0으로 채우므로 빈 키 = 0 한 바이트 키
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        mac.update(fromHex(saltHex));
        mac.update(new byte[]{0, 0, 0, 1});
        byte[] u = mac.doFinal();
        byte[] t = u.clone();
        for (int i = 1; i < iterations; i++) {
            u = mac.doFinal(u);
            for (int j = 0; j < t.length; j++) {
                t[j] ^= u[j];
            }
        }
        return toHex(t);
    }

    static String toHex(byte[] b) {
        StringBuilder sb = new StringBuilder(b.length * 2);
        for (byte x : b) {
            sb.append(String.format(Locale.ROOT, "%02x", x & 0xff));
        }
        return sb.toString();
    }

    static byte[] fromHex(String s) {
        int n = s.length() / 2;
        byte[] out = new byte[n];
        for (int i = 0; i < n; i++) {
            out[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    // ── 홈 화면 위젯용 날짜·금액 (util.js settlePeriod·fmtMoney 와 같은 규칙) ──
    static int monthEnd(int y, int m) {
        int[] d = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
        boolean leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
        return m == 2 && leap ? 29 : d[m - 1];
    }

    static String iso(int y, int m, int d) {
        return String.format(Locale.ROOT, "%04d-%02d-%02d", y, m, d);
    }

    /** 결산일 기준 '그 달' 기간 [시작, 끝] (YYYY-MM-DD). 결산일 25일이면 25일 ~ 다음 달 24일 */
    static String[] settlePeriod(int y, int m, int sd) {
        sd = Math.max(1, Math.min(31, sd));
        int ny = m == 12 ? y + 1 : y, nm = m == 12 ? 1 : m + 1;
        int ed = Math.min(sd, monthEnd(ny, nm)) - 1;
        String end;
        if (ed >= 1) {
            end = iso(ny, nm, ed);
        } else {
            end = iso(y, m, monthEnd(y, m));         // 결산일 1일: 그 달 말일까지
        }
        return new String[]{iso(y, m, Math.min(sd, monthEnd(y, m))), end};
    }

    /** 오늘(YYYY-MM-DD)이 들어 있는 결산 '달' {연, 월} */
    static int[] periodOf(String today, int sd) {
        int y = Integer.parseInt(today.substring(0, 4)), m = Integer.parseInt(today.substring(5, 7));
        if (today.compareTo(settlePeriod(y, m, sd)[0]) >= 0) {
            return new int[]{y, m};
        }
        return m == 1 ? new int[]{y - 1, 12} : new int[]{y, m - 1};
    }

    static String money(long v) {
        return String.format(Locale.ROOT, "%,d", v);
    }

    /** UTF-8 로 읽고, 안 되면 엑셀이 흔히 쓰는 CP949(EUC-KR 확장)로 */
    static String decodeText(byte[] b) {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(b)).toString();
        } catch (CharacterCodingException e) {
            for (String n : new String[]{"x-windows-949", "MS949", "windows-949", "EUC-KR"}) {
                try {
                    if (Charset.isSupported(n)) {
                        return new String(b, Charset.forName(n));
                    }
                } catch (Exception ignored) {
                    // 다음 이름으로
                }
            }
            return new String(b, StandardCharsets.UTF_8);
        }
    }
}
