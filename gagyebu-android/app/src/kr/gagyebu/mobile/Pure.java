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
