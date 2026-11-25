/*
 * MiguProbe — 用 App 里完全相同的 HTTP 栈验证咪咕能播。
 *
 * 复刻 app/src/main/java/com/sasau/pangetv/player/{MiguDns,PlayerFactory}.kt：
 *   OkHttpClient + 自定义 okhttp3.Dns（把被污染的 CDN 域名解析到真实 CDN IP）
 *   同一份 UA / Referer
 *
 * 与 tools/check_streams.py 的区别：那个用 socket pin 模拟解析替换，
 * 这个直接跑 App 上真正用的 HTTP 客户端，能验证 OkHttp 这条路确实成立。
 *
 * 编译（JDK 17）：
 *   javac -encoding UTF-8 -cp "<okhttp.jar>;<okio-jvm.jar>;<kotlin-stdlib.jar>" -d . MiguProbe.java
 * 运行：
 *   java -cp ".;<同上的jar>" MiguProbe "<m3u8地址>" "<referer>"
 */
import okhttp3.Dns;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

import java.io.InputStream;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class MiguProbe {

    /** 与 app/src/main/java/com/sasau/pangetv/player/MiguDns.kt 完全一致 */
    static final Map<String, String> ALIASES = Map.of(
            "cache.ott.fifalive.itv.cmvideo.cn",
            "base-v4v6-cm-miguvideo.e.cdn.chinamobile.com");

    static final String UA = "Mozilla/5.0 (Linux; Android 13; PangETV) AppleWebKit/537.36 "
            + "(KHTML, like Gecko) Chrome/122.0 Safari/537.36";

    static class MiguDns implements Dns {
        private final Dns delegate = Dns.SYSTEM;

        @Override
        public List<InetAddress> lookup(String hostname) throws UnknownHostException {
            String alias = ALIASES.get(hostname.toLowerCase());
            if (alias == null) {
                return delegate.lookup(hostname);
            }
            try {
                List<InetAddress> addrs = delegate.lookup(alias);
                System.out.println("  [Dns] " + hostname + " -> " + alias
                        + " (" + addrs.get(0).getHostAddress() + ")");
                return addrs;
            } catch (UnknownHostException e) {
                return delegate.lookup(hostname);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: MiguProbe <m3u8-url> [referer]");
            System.exit(2);
        }
        String url = args[0];
        String referer = args.length > 1 ? args[1] : "https://www.miguvideo.com/";

        OkHttpClient client = new OkHttpClient.Builder()
                .dns(new MiguDns())
                .followRedirects(true)
                .followSslRedirects(true)
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .retryOnConnectionFailure(true)
                .build();

        Request req = new Request.Builder()
                .url(url)
                .header("User-Agent", UA)
                .header("Accept", "*/*")
                .header("Referer", referer)
                .build();

        System.out.println("GET " + url);
        Response resp = client.newCall(req).execute();
        System.out.println("HTTP " + resp.code()
                + "  content-type=" + resp.header("Content-Type"));
        System.out.println("final url = " + resp.request().url());

        if (!resp.isSuccessful()) {
            System.out.println("RESULT: FAIL http " + resp.code());
            resp.close();
            System.exit(1);
        }

        ResponseBody body = resp.body();
        String head;
        try (InputStream in = body.byteStream()) {
            byte[] buf = new byte[2048];
            int total = 0, r;
            while (total < buf.length && (r = in.read(buf, total, buf.length - total)) > 0) {
                total += r;
            }
            head = new String(buf, 0, total, "UTF-8");
        }
        resp.close();

        String flat = head.replace("\n", " ");
        System.out.println("body head = " + flat.substring(0, Math.min(150, flat.length())));

        boolean isM3u = head.contains("#EXTM3U");
        System.out.println("RESULT: " + (isM3u
                ? "OK - got HLS playlist"
                : "NOT an HLS playlist"));
        System.exit(isM3u ? 0 : 2);
    }
}
