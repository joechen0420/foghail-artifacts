package com.foghail.client

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigInteger
import java.security.Signature
import java.security.interfaces.ECPrivateKey
import java.security.interfaces.ECPublicKey

/**
 * FogHail 量測 App（2026-10-14 v3 版）。
 * ①②③ 與 8 月那版完全相同（E3／E5），④⑤⑥ 是這次新增的 v3 憑證量測：
 *   ④ v3 對拍（必先過）：手機算出的地址與簽章驗證結果，必須和 Python 參考版一致
 *   ⑤ 量 v3 憑證：3/4 門檻盲簽的發行／驗證／收據時間，並在同一次執行裡重量舊版 r1 當基準
 *   ⑥ 複製結果：把 ⑤ 的完整結果（JSON）複製到剪貼簿，直接貼到 LINE／Email 回傳
 *
 * 2026-10-30 v5（E3 重測）：新增 ⑦。假名金鑰改成真的由根私鑰推導後，E3 的簽章段要重量；
 *   ⑦ 在同一次執行裡交替跑「舊：隨機產生金鑰」與「新：由根私鑰推導」各 3 輪，
 *   先檢查推導結果與 Python 參考值一致才開始計時。⑥ 改成複製最近一次 ⑤ 或 ⑦ 的結果。
 * 2026-11-03 v6：⑦ 加第三種「預先推導」——推導在計時外（閒置時先算好），另記推導本身的時間。
 *   三種交替各 3 輪；論文用「預先推導／隨機」的同機倍率換算 Redmi。
 * 繼承基礎 android.app.Activity（不是 AppCompatActivity），避免主題問題造成閃退。
 */
class MainActivity : Activity() {

    // E3 Python 參考真值（m=512,k=5,salt=foghail-epoch-0）
    private val refVectors = listOf(
        Triple(0, 0, listOf(64, 94, 98, 128, 393)),
        Triple(3, -2, listOf(65, 219, 232, 296, 366)),
        Triple(120, 88, listOf(55, 57, 133, 209, 313)),
        Triple(-5, 17, listOf(119, 272, 340, 442, 473)),
    )

    // v3 Python 參考真值（experiments/e5v3_kotlin/reference_vectors_v3.json）
    private val v3Msg = "1111111111111111111111111111111111111111"
    private val v3Known1 = "7e5f4552091a69125d5dfcb7b8c2659029395bdf"   // 私鑰 1 的以太坊地址（公認答案）
    // v4 授權簽章的 Python 參考值（foghail_cred.esign(auth_digest(...))）
    private val v4AuthSig = "57516efbfc0ac3112f22b564a69abb55a1240d68d62107574d7be20af3949f98" +
        "3e23e7a2a5407aa6dc7d6cd894e49fa8b88c7cc4315e08db3ae80c0b80be8feb1c"
    private val v3Vectors = listOf(
        listOf("44b47b75112ccd766df0fc3f6cd3970b7bcc50d857915211b48ea6e03fe56250",
               "914b727fcea9985a7b8f746c99dde7ac2fda9cab",
               "5dd4ba9b8c603a6f595535072984caf9e2342305",
               "7e22ac2f322c7ff410ecb1930a6346dc0f744159bb4ea39899405eaf49927016"),
        listOf("5edf81d118c8353da9e62f86ed948c66c7d28bf3bb75671b693322f8868e33a7",
               "a28e32fecb540bdd060c842e2330b0653c5d6367",
               "ff3860e05e62ee4d1a5ed0a62a4e1d37bb5f888c",
               "4881c8db9f28ef8dadd93419d624672f660710f6ef40f19d199838c1f29fd7f1"),
        listOf("bc9b41099e57ca6e5ce415d23b7729bab029cd73a6f42eed9a94945c2cb4555e",
               "d3f39db69c61470ca01e82531614b384a511e993",
               "c6efc3de1e4a7d8be80e7e2bc2f4028a1d3c9aad",
               "d85de3863bda28cd461bc05f3890cbbc37663fe412bae67cc0e0dfa3618a534d"),
    )

    // ⑦ 推導對拍：root_sk = 32 個 0x01、t = 7，SHA-256(root||t 8B BE) mod n（secp256r1）的 Python 參考值
    private val e3RefD = "bd4f52148138952712e9584ef9db8e55aaf44d4d404541c67b32d3aef69a8e1"
    private val e3RefX = "a09813e5741e83715d97a7ea7d2dc88a91065c8cd57403a09be93df16577fe6e"

    private lateinit var out: TextView
    private var lastJson: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 60, 40, 40)
        }
        val title = TextView(this).apply {
            text = "FogHail 手機量測"; textSize = 22f; gravity = Gravity.CENTER
            setPadding(0, 0, 0, 30)
        }
        out = TextView(this).apply { textSize = 14f; setPadding(0, 30, 0, 0); setTextIsSelectable(true) }

        fun addButton(label: String, action: () -> Unit) {
            root.addView(Button(this).apply {
                text = label
                setOnClickListener {
                    out.text = "執行中，請稍候…（⑤⑦ 約需 1–3 分鐘，請不要切到別的 App）"
                    Thread {
                        val result = runCatching(action).exceptionOrNull()?.let {
                            "錯誤：${it.message}\n（見教學文件的疑難排解）"
                        }
                        runOnUiThread { if (result != null) out.text = result }
                    }.start()
                }
            })
        }

        root.addView(title)
        addButton("① 驗證位元對拍（E3）") { verifyBits() }
        addButton("② 量 E3 用戶端延遲") { measureE3() }
        addButton("③ 量 E5 信譽開銷（舊版）") { measureE5() }
        addButton("④ v3 對拍（必先過）") { verifyV3() }
        addButton("⑤ 量 v3 憑證（3/4 門檻）") { measureV3() }
        root.addView(Button(this).apply {
            text = "⑥ 複製最近一次 ⑤ 或 ⑦ 的結果"
            setOnClickListener { copyResult() }
        })
        addButton("⑦ E3 重測：新舊金鑰對照") { measureE3Compare() }

        val scroll = ScrollView(this).apply { addView(root.apply { addView(out) }) }
        setContentView(scroll)
    }

    private fun show(s: String) = runOnUiThread { out.text = s }

    // ---------------------------------------------------------------- ①②③（原樣保留）
    private fun verifyBits() {
        FogHailBloom.m = 512; FogHailBloom.k = 5
        val salt = "foghail-epoch-0"
        val sb = StringBuilder("① 位元對拍（與 Python 參考版）\n\n")
        var allPass = true
        for ((gx, gy, want) in refVectors) {
            val bs = FogHailBloom.cellBits(Pair(gx, gy), salt)
            val got = (0 until FogHailBloom.m).filter { bs.get(it) }
            val pass = got == want
            allPass = allPass && pass
            sb.append("cell($gx,$gy): ${if (pass) "✓ 通過" else "✗ 不符\n  應為 $want\n  實得 $got"}\n")
        }
        sb.append("\n結果：${if (allPass) "全部通過 ✓" else "有不符 ✗"}")
        show(sb.toString())
    }

    private fun measureE3() {
        val r = E3LatencyBench.run(40.75, -73.99, ByteArray(32) { 1 }, "foghail-epoch-0")
        val sb = StringBuilder("② E3 用戶端編碼延遲\n\n段落            p50(ms)   p95(ms)\n")
        for (seg in listOf("T_grid", "T_neighbor", "T_bloom", "T_sign", "T_total")) {
            val s = r[seg]!!
            sb.append("%-14s %8.3f %8.3f\n".format(seg, s.p50, s.p95))
        }
        show(sb.toString())
    }

    private fun measureE5() {
        val sb = StringBuilder("③ E5 ACL 信譽開銷（舊版 r1）\n\n")
        for (m in listOf(FogHailACL.bench("rider", 200), FogHailACL.bench("driver", 200))) {
            sb.append("【${m["role"]}】正確性=${m["verified_ok"]}\n")
            sb.append("  取得 p50=%.3f ms  出示 p50=%.4f ms  驗證 p50=%.3f ms\n\n"
                .format(m["issue_p50"], m["show_p50"], m["verify_p50"]))
        }
        show(sb.toString())
    }

    // ---------------------------------------------------------------- ④⑤⑥（v3 新增）
    private fun verifyV3() {
        val V = FogHailCredV3
        val sb = StringBuilder("④ v3 對拍（與 Python 參考版）\n\n")
        var allPass = true
        fun line(name: String, pass: Boolean, detail: String = "") {
            allPass = allPass && pass
            sb.append("$name：${if (pass) "✓ 通過" else "✗ 不符 $detail"}\n")
        }
        val k1 = V.hex(V.addrOf(V.G.multiply(BigInteger.ONE)))
        line("Keccak 與地址（私鑰 1）", k1 == v3Known1, "\n  應為 $v3Known1\n  實得 $k1")
        val m = V.unhex(v3Msg)
        for ((i, v) in v3Vectors.withIndex()) {
            val P = V.G.multiply(BigInteger(v[0], 16)).normalize()
            val addr = V.hex(V.addrOf(P))
            line("驗證節點 ${i + 1} 地址", addr == v[1], "\n  應為 ${v[1]}\n  實得 $addr")
            val sig = FogHailCredV3.Sig(V.unhex(v[2]), BigInteger(v[3], 16))
            line("驗證節點 ${i + 1} 的 Python 簽章", V.verify(P, m, sig))
            val bad = FogHailCredV3.Sig(V.unhex(v[2]), BigInteger(v[3], 16).add(BigInteger.ONE))
            line("竄改過的簽章應被拒絕 ${i + 1}", !V.verify(P, m, bad))
        }
        val iss = FogHailCredV3.Issuer()
        val mine = V.blindSign(iss, m)
        line("手機自己盲簽後自己驗", V.verify(iss.P, m, mine))
        iss.commit()
        val rosOk = runCatching { iss.commit() }.isFailure
        line("同一把金鑰不能同時開兩個流程（ROS）", rosOk)
        // v4 授權簽章：與 Python 簽出的位元組完全相同（RFC 6979 決定性簽章）
        val key = BigInteger("4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318", 16)
        val h = V.sessionHash(V.G.multiply(BigInteger.valueOf(7)), BigInteger.valueOf(123456789))
        val auth = V.hex(V.ethSign(key, V.authDigest(ByteArray(20) { 0x11 }, 1337, V.KIND_CRED, 1, 2, h)))
        line("v4 授權簽章與 Python 相同", auth == v4AuthSig, "\n  應為 $v4AuthSig\n  實得 $auth")
        sb.append("\n結果：${if (allPass) "全部通過 ✓ 可以按 ⑤ 量測了" else "有不符 ✗ 先不要量，截圖回報"}")
        show(sb.toString())
    }

    // ---------------------------------------------------------------- ⑦（v5 新增：E3 重測）
    private fun measureE3Compare() {
        val root = ByteArray(32) { 1 }
        // 先對拍：推導出的私鑰與公鑰 x 座標必須和 Python 一致，簽章要驗得過
        val kp = FogHailBloom.derivePseudonym(root, 7)
        val d = (kp.private as ECPrivateKey).s.toString(16)
        val x = (kp.public as ECPublicKey).w.affineX.toString(16)
        val msg = "foghail-e3".toByteArray()
        val sig = Signature.getInstance("SHA256withECDSA").run { initSign(kp.private); update(msg); sign() }
        val ok = Signature.getInstance("SHA256withECDSA").run { initVerify(kp.public); update(msg); verify(sig) }
        val checkPass = d == e3RefD && x == e3RefX && ok
        if (!checkPass) {
            show("⑦ 推導對拍不符 ✗ 先不要量，截圖回報\n\n私鑰 應為 $e3RefD\n     實得 $d\n公鑰x 應為 $e3RefX\n     實得 $x\n簽章驗證 $ok")
            return
        }
        FogHailBloom.m = 512; FogHailBloom.k = 5
        val segs = listOf("T_grid", "T_neighbor", "T_bloom", "T_sign", "T_total")
        val rounds = JSONArray()
        val modes = listOf("random", "derived", "precomputed")
        val modeName = mapOf("random" to "舊（隨機金鑰）", "derived" to "推導（計時內）", "precomputed" to "預先推導")
        val tot = modes.associateWith { ArrayList<Double>() }
        val tot95 = modes.associateWith { ArrayList<Double>() }
        val der = ArrayList<Double>(); val der95 = ArrayList<Double>()
        for (r in 1..3) for (mode in modes) {     // 交替跑，抵消降頻與溫度漂移
            show("⑦ 量測中：第 $r/3 輪，${modeName[mode]}…")
            val res = E3LatencyBench.run(40.75, -73.99, root, "foghail-epoch-0", mode)
            val o = JSONObject().put("round", r).put("mode", mode)
            for (k in segs + listOf("T_derive")) res[k]?.let { o.put(k, JSONObject().put("p50_ms", it.p50).put("p95_ms", it.p95)) }
            rounds.put(o)
            tot[mode]!!.add(res["T_total"]!!.p50); tot95[mode]!!.add(res["T_total"]!!.p95)
            res["T_derive"]?.let { der.add(it.p50); der95.add(it.p95) }
        }
        fun med(xs: List<Double>) = xs.sorted()[xs.size / 2]
        val r50 = med(tot["random"]!!); val d50 = med(tot["derived"]!!); val p50 = med(tot["precomputed"]!!)
        val r95 = med(tot95["random"]!!); val d95 = med(tot95["derived"]!!); val p95 = med(tot95["precomputed"]!!)
        val json = JSONObject()
        json.put("test", "E3 random vs derived vs precomputed pseudonym key")
        json.put("app", "v6-e3-20261103")
        json.put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
        json.put("android", Build.VERSION.RELEASE)
        json.put("sdk", Build.VERSION.SDK_INT)
        json.put("iters", 1000); json.put("warmup", 100)
        json.put("derive_check_pass", checkPass)
        json.put("rounds", rounds)
        json.put("summary", JSONObject()
            .put("random_total_p50_ms", r50).put("random_total_p95_ms", r95)
            .put("derived_total_p50_ms", d50).put("derived_total_p95_ms", d95)
            .put("ratio_p50", d50 / r50).put("ratio_p95", d95 / r95)
            .put("precomputed_total_p50_ms", p50).put("precomputed_total_p95_ms", p95)
            .put("pre_ratio_p50", p50 / r50).put("pre_ratio_p95", p95 / r95)
            .put("derive_p50_ms", med(der)).put("derive_p95_ms", med(der95)))
        lastJson = json.toString(1)
        val sb = StringBuilder("⑦ E3 新舊對照（${Build.MANUFACTURER} ${Build.MODEL}，Android ${Build.VERSION.RELEASE}）\n\n")
        sb.append("推導對拍：✓ 通過\n\n")
        sb.append("T_total（三輪取中位）  p50(ms)   p95(ms)\n")
        sb.append("舊：隨機金鑰          %8.3f %8.3f\n".format(r50, r95))
        sb.append("推導（計時內）        %8.3f %8.3f\n".format(d50, d95))
        sb.append("預先推導              %8.3f %8.3f\n".format(p50, p95))
        sb.append("預先推導/舊倍率       %8.2f %8.2f\n".format(p50 / r50, p95 / r95))
        sb.append("推導本身（閒置時）    %8.3f %8.3f\n".format(med(der), med(der95)))
        sb.append("\n完成 ✓ 請按 ⑥ 複製結果，貼給老師")
        show(sb.toString())
    }

    private fun measureV3() {
        val r = FogHailCredV3.bench(200, 20)
        fun s(k: String) = r[k] as FogHailCredV3.Stat
        val json = JSONObject()
        json.put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
        json.put("android", Build.VERSION.RELEASE)
        json.put("sdk", Build.VERSION.SDK_INT)
        json.put("n", 200); json.put("warmup", 20)
        for ((k, v) in r) {
            when (v) {
                is FogHailCredV3.Stat -> json.put(k, JSONObject().put("p50_ms", v.p50).put("p95_ms", v.p95))
                is Map<*, *> -> json.put(k, JSONObject(v))
                else -> json.put(k, v)
            }
        }
        lastJson = json.toString(1)

        val sb = StringBuilder("⑤ v3 憑證量測（${Build.MANUFACTURER} ${Build.MODEL}，Android ${Build.VERSION.RELEASE}）\n\n")
        sb.append("項目                   p50(ms)   p95(ms)\n")
        val rows = listOf(
            "r1 單一盲簽（舊基準）" to "r1_single_issue",
            "r1 驗一次（舊基準）" to "r1_single_verify",
            "k1 單一盲簽" to "k1_single_issue",
            "k1 驗一次" to "k1_single_verify",
            "憑證發行 3/4" to "cred_issue_3of4",
            "憑證驗證 3/4" to "cred_verify_3of4",
            "憑證出示" to "cred_show",
            "收據發行 3/4" to "receipt_issue_3of4",
            "授權簽章一次（v4）" to "auth_sign_once",
            "憑證發行 v4" to "cred_issue_3of4_v4",
            "收據發行 v4" to "receipt_issue_3of4_v4",
        )
        for ((label, key) in rows) sb.append("%-16s %9.3f %9.3f\n".format(label, s(key).p50, s(key).p95))
        val perTrip = s("cred_issue_3of4").p50 + s("receipt_issue_3of4").p50
        val perTripV4 = s("cred_issue_3of4_v4").p50 + s("receipt_issue_3of4_v4").p50
        sb.append("\n每趟合計（憑證＋收據）p50 = %.2f ms（v3）、%.2f ms（v4，論文採用）\n".format(perTrip, perTripV4))
        sb.append("正確性：${if (r["correct_all_runs"] == true) "✓ 全部驗證通過" else "✗ 有驗證失敗，請截圖回報"}\n")
        sb.append("\n請按 ⑥ 複製完整結果，貼到 LINE／Email 傳給老師。")
        show(sb.toString())
    }

    private fun copyResult() {
        val j = lastJson
        if (j == null) {
            Toast.makeText(this, "請先按 ⑤ 或 ⑦ 量測", Toast.LENGTH_SHORT).show(); return
        }
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("FogHail 結果", j))
        Toast.makeText(this, "已複製，可以貼到 LINE／Email 了", Toast.LENGTH_LONG).show()
    }
}
