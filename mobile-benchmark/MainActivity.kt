package com.foghail.client

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * FogHail 量測 App：一個畫面、三個按鈕，點了就在畫面上顯示數字。
 * ① 驗證位元對拍（必先過）② 量 E3 用戶端延遲 ③ 量 E5 信譽開銷。
 * 不需 adb / logcat；結果直接顯示在手機上，抄下來填論文即可。
 *
 * 注意：本類別繼承基礎 android.app.Activity（不是 AppCompatActivity）。
 * 量測只用純運算＋基礎 android.widget 元件，不需要 AppCompat；用基礎 Activity
 * 可避免「App 主題非 Theme.AppCompat 後代」造成的一開機即閃退，且完全不影響 E3/E5 數字。
 */
class MainActivity : Activity() {

    // Python 參考真值（m=512,k=5,salt=foghail-epoch-0）——對拍必須完全吻合
    private val refVectors = listOf(
        Triple(0, 0, listOf(64, 94, 98, 128, 393)),
        Triple(3, -2, listOf(65, 219, 232, 296, 366)),
        Triple(120, 88, listOf(55, 57, 133, 209, 313)),
        Triple(-5, 17, listOf(119, 272, 340, 442, 473)),
    )

    private lateinit var out: TextView

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
        out = TextView(this).apply { textSize = 14f; setPadding(0, 30, 0, 0) }

        fun addButton(label: String, action: () -> Unit) {
            root.addView(Button(this).apply {
                text = label
                setOnClickListener {
                    out.text = "執行中，請稍候…"
                    Thread {
                        val result = runCatching(action).exceptionOrNull()?.let {
                            "錯誤：${it.message}\n（多半是位元對拍未過或相依未加，見指南疑難排解）"
                        }
                        runOnUiThread { if (result != null) out.text = result }
                    }.start()
                }
            })
        }

        root.addView(title)
        addButton("① 驗證位元對拍（必先過）") { verifyBits() }
        addButton("② 量 E3 用戶端延遲") { measureE3() }
        addButton("③ 量 E5 信譽開銷") { measureE5() }

        val scroll = ScrollView(this).apply { addView(root.apply { addView(out) }) }
        setContentView(scroll)
    }

    private fun show(s: String) = runOnUiThread { out.text = s }

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
        sb.append("\n結果：${if (allPass) "全部通過 ✓ 可以量延遲了" else "有不符 ✗ 先修（見指南疑難排解）"}")
        show(sb.toString())
    }

    private fun measureE3() {
        val r = E3LatencyBench.run(40.75, -73.99, ByteArray(32) { 1 }, "foghail-epoch-0")
        val sb = StringBuilder("② E3 用戶端編碼延遲（本機手機）\n\n")
        sb.append("段落            p50(ms)   p95(ms)\n")
        for (seg in listOf("T_grid", "T_neighbor", "T_bloom", "T_sign", "T_total")) {
            val s = r[seg]!!
            sb.append("%-14s %8.3f %8.3f\n".format(seg, s.p50, s.p95))
        }
        sb.append("\n填論文表 3「用戶端計算」欄（T_total）。\n對照 ORide 手機 15–26 ms。")
        show(sb.toString())
    }

    private fun measureE5() {
        val rider = FogHailACL.bench("rider", 200)
        val driver = FogHailACL.bench("driver", 200)
        val sb = StringBuilder("③ E5 ACL 信譽開銷（本機手機）\n\n")
        for (m in listOf(rider, driver)) {
            sb.append("【${m["role"]}】正確性=${m["verified_ok"]}\n")
            sb.append("  取得(盲簽) p50=%.3f ms\n".format(m["issue_p50"]))
            sb.append("  出示 p50=%.4f ms\n".format(m["show_p50"]))
            sb.append("  驗證 p50=%.3f ms\n".format(m["verify_p50"]))
            sb.append("  憑證大小 ${m["cred_bytes"]} B\n\n")
        }
        sb.append("填論文表 5 手機端欄。\n對照 PrivateRide LG G3：取得 554 / 出示 219 / 盲簽 68 ms。")
        show(sb.toString())
    }
}
