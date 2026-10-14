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
import org.json.JSONObject
import java.math.BigInteger

/**
 * FogHail 量測 App（2026-10-14 v3 版）。
 * ①②③ 與 8 月那版完全相同（E3／E5），④⑤⑥ 是這次新增的 v3 憑證量測：
 *   ④ v3 對拍（必先過）：手機算出的地址與簽章驗證結果，必須和 Python 參考版一致
 *   ⑤ 量 v3 憑證：3/4 門檻盲簽的發行／驗證／收據時間，並在同一次執行裡重量舊版 r1 當基準
 *   ⑥ 複製結果：把 ⑤ 的完整結果（JSON）複製到剪貼簿，直接貼到 LINE／Email 回傳
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
                    out.text = "執行中，請稍候…（⑤ 約需 1–3 分鐘，請不要切到別的 App）"
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
            text = "⑥ 複製 ⑤ 的結果"
            setOnClickListener { copyResult() }
        })

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
        sb.append("\n結果：${if (allPass) "全部通過 ✓ 可以按 ⑤ 量測了" else "有不符 ✗ 先不要量，截圖回報"}")
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
        )
        for ((label, key) in rows) sb.append("%-16s %9.3f %9.3f\n".format(label, s(key).p50, s(key).p95))
        val perTrip = s("cred_issue_3of4").p50 + s("receipt_issue_3of4").p50
        sb.append("\n每趟合計（憑證＋收據）p50 = %.2f ms\n".format(perTrip))
        sb.append("正確性：${if (r["correct_all_runs"] == true) "✓ 全部驗證通過" else "✗ 有驗證失敗，請截圖回報"}\n")
        sb.append("\n請按 ⑥ 複製完整結果，貼到 LINE／Email 傳給老師。")
        show(sb.toString())
    }

    private fun copyResult() {
        val j = lastJson
        if (j == null) {
            Toast.makeText(this, "請先按 ⑤ 量測", Toast.LENGTH_SHORT).show(); return
        }
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("FogHail v3 結果", j))
        Toast.makeText(this, "已複製，可以貼到 LINE／Email 了", Toast.LENGTH_LONG).show()
    }
}
