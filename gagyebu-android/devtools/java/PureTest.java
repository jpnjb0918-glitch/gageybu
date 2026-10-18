package kr.gagyebu.mobile;

/** PC의 자바(JDK)로 Pure 를 시험: 파이썬 hashlib 결과와 같은지, CP949 CSV 를 읽는지. */
public class PureTest {
    public static void main(String[] a) throws Exception {
        // a[0]=암호, a[1]=소금, a[2]=반복, a[3]=CP949 파일 경로
        System.out.println(Pure.pbkdf2Hex(a[0], a[1], Integer.parseInt(a[2])));
        System.out.println(Pure.pbkdf2Hex("", a[1], 1000));
        byte[] b = java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(a[3]));
        System.out.println(Pure.decodeText(b).trim());
        System.out.println(Pure.decodeText("가나다,1000".getBytes("UTF-8")).trim());
    }
}
