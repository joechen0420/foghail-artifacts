package com.foghail.client

import java.security.MessageDigest
import java.security.Signature

/**
 * E3 用戶端編碼延遲量測：T = T_grid + T_neighbor + T_bloom + T_sign。
 *
 * 放進 Android app 的 instrumented test 或一支 Activity 按鈕跑；用 System.nanoTime()
 * 各段量 1000 次取 p50/p95（丟前 100 次熱身讓 JIT 穩定）。在 2–3 支不同級距實體
 * 手機各跑一輪，數字填論文表 3「用戶端計算」欄與圖 5。
 *
 * 注意：務必在「實體手機」跑（非模擬器）。輸出 CSV 貼進 experiments/phase1 對照。
 */
object E3LatencyBench {
    private const val WARMUP = 100
    private const val ITERS = 1000

    data class Stat(val p50: Double, val p95: Double, val mean: Double)

    private fun stat(xs: DoubleArray): Stat {
        xs.sort()
        fun q(p: Double) = xs[(p * (xs.size - 1)).toInt()]
        return Stat(q(0.5), q(0.95), xs.average())
    }

    /** 回傳四段（毫秒）與總和的 p50/p95。lat/lon 為測試上車點。 */
    fun run(lat: Double, lon: Double, rootSk: ByteArray, salt: String): Map<String, Stat> {
        val tGrid = DoubleArray(ITERS); val tNbr = DoubleArray(ITERS)
        val tBloom = DoubleArray(ITERS); val tSign = DoubleArray(ITERS)
        val tAll = DoubleArray(ITERS)

        repeat(WARMUP + ITERS) { it0 ->
            val i = it0 - WARMUP
            val t0 = System.nanoTime()
            val c = FogHailBloom.cell(lat, lon)
            val t1 = System.nanoTime()
            val nbr = FogHailBloom.neighborhood(c)
            val t2 = System.nanoTime()
            val bf = FogHailBloom.buildBF(nbr, salt)
            val t3 = System.nanoTime()
            // 簽章：對 {臨時標籤 || BF 位元 || 時間戳} 簽名
            // Android 9+ 不再提供 BC 的 EC 簽章實作，故不指定 "BC"，改用平台預設 provider
            // （AndroidOpenSSL/Conscrypt，硬體加速）；仍是 secp256r1 上的 SHA256withECDSA。
            val kp = FogHailBloom.derivePseudonym(rootSk, System.currentTimeMillis())
            val sig = Signature.getInstance("SHA256withECDSA")
            sig.initSign(kp.private)
            sig.update(bf.toByteArray())
            sig.sign()
            val t4 = System.nanoTime()
            if (i >= 0) {
                val ns = 1_000_000.0
                tGrid[i] = (t1 - t0) / ns; tNbr[i] = (t2 - t1) / ns
                tBloom[i] = (t3 - t2) / ns; tSign[i] = (t4 - t3) / ns
                tAll[i] = (t4 - t0) / ns
            }
        }
        return mapOf(
            "T_grid" to stat(tGrid), "T_neighbor" to stat(tNbr),
            "T_bloom" to stat(tBloom), "T_sign" to stat(tSign),
            "T_total" to stat(tAll)
        )
    }

    @JvmStatic
    fun main(args: Array<String>) {
        val res = run(40.75, -73.99, ByteArray(32) { 1 }, "foghail-epoch-0")
        println("段落, p50(ms), p95(ms), mean(ms)")
        for ((k, s) in res) println("%s, %.4f, %.4f, %.4f".format(k, s.p50, s.p95, s.mean))
    }
}
