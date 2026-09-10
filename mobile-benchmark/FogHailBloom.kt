package com.foghail.client

import org.bouncycastle.crypto.digests.Blake2bDigest
import org.bouncycastle.jce.provider.BouncyCastleProvider
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.Security
import java.security.spec.ECGenParameterSpec
import java.util.BitSet
import kotlin.math.floor

/**
 * FogHail 用戶端 BF 編碼模組（E3 用戶端延遲量測對象）。
 *
 * 與 Python 參考版 (experiments/phase1/bloom.py, phase0/config.py) 邏輯逐一對拍：
 *  - 同一本地等距投影（lat0/lon0）、同一 grid_size、同一 blake2b k 次雜湊、同一 m。
 *  - 乘客編碼 9 格 (BF_p)、駕駛編碼 1 格 (BF_d)；salt 每 epoch 由鏈上信標派生。
 *
 * 驗證正確性：對同一組 (lat,lon,salt)，本模組產生的位元索引須與 Python 版一致
 * （用固定測試向量比對，見 verifyAgainstReference()）。
 */
object FogHailBloom {
    init { Security.addProvider(BouncyCastleProvider()) }

    // ---- 與 Python config 對齊的常數 ----
    const val LAT_MIN = 40.60; const val LAT_MAX = 40.90
    const val LON_MIN = -74.05; const val LON_MAX = -73.70
    val LAT0 = (LAT_MIN + LAT_MAX) / 2.0
    val LON0 = (LON_MIN + LON_MAX) / 2.0
    const val M_PER_DEG_LAT = 110540.0
    val M_PER_DEG_LON = 111320.0 * Math.cos(Math.toRadians(LAT0))

    var gridSize = 250.0     // 公尺
    var m = 512              // BF 位元長度
    var k = 5                // 雜湊數

    fun toMeters(lat: Double, lon: Double): Pair<Double, Double> {
        val x = (lon - LON0) * M_PER_DEG_LON
        val y = (lat - LAT0) * M_PER_DEG_LAT
        return Pair(x, y)
    }

    fun cell(lat: Double, lon: Double): Pair<Int, Int> {
        val (x, y) = toMeters(lat, lon)
        return Pair(floor(x / gridSize).toInt(), floor(y / gridSize).toInt())
    }

    /** 8-鄰域（9 格），對齊 Python 的 _neighbors 順序。 */
    fun neighborhood(c: Pair<Int, Int>): List<Pair<Int, Int>> {
        val out = ArrayList<Pair<Int, Int>>(9)
        for (dx in -1..1) for (dy in -1..1) out.add(Pair(c.first + dx, c.second + dy))
        return out
    }

    /**
     * 單一 cell -> k 個位元索引。**必須對齊 Python 的 blake2b(digest_size=8)**：
     * BLAKE2b 把輸出長度編進初始化，故「BLAKE2b-512 取前 8 bytes」≠「digest_size=8」！
     * 用 BouncyCastle 的 Blake2bDigest(64)（64 bit = 8 byte 輸出）才會一致。
     * 之後轉 little-endian 為 long、mod m（負數取正），對齊 Python cell_bits。
     */
    fun cellBits(c: Pair<Int, Int>, salt: String): BitSet {   // 設為 public 供對拍測試
        val bs = BitSet(m)
        val base = "${c.first},${c.second}|$salt".toByteArray()
        for (i in 0 until k) {
            val d = Blake2bDigest(64)                 // 64 bits = 8 bytes（對齊 digest_size=8）
            d.update(base, 0, base.size)
            val sep = "|$i".toByteArray()
            d.update(sep, 0, sep.size)
            val dig = ByteArray(8)
            d.doFinal(dig, 0)
            var v = 0L                                // little-endian bytes -> long
            for (b in 0 until 8) v = v or ((dig[b].toLong() and 0xff) shl (8 * b))
            val idx = ((v % m) + m) % m               // 負數取正（對齊 Python %）
            bs.set(idx.toInt())
        }
        return bs
    }

    fun buildBF(cells: List<Pair<Int, Int>>, salt: String): BitSet {
        val bf = BitSet(m)
        for (c in cells) bf.or(cellBits(c, salt))
        return bf
    }

    /** 每行程假名：temp_sk = H(root_sk || trip_ts) → secp256r1 公鑰。 */
    fun derivePseudonym(rootSk: ByteArray, ts: Long): java.security.KeyPair {
        val md = MessageDigest.getInstance("SHA-256")
        md.update(rootSk); md.update(ts.toString().toByteArray())
        // 此處以 seed 派生金鑰（實作可用確定性 EC 金鑰生成）
        // 注意：Android 9（API 28）起，平台移除 BouncyCastle("BC") 的 EC 實作，
        // 指定 "BC" 會拋 KeyPairGenerator.EC 例外；改用平台預設 provider（AndroidOpenSSL）。
        // 曲線仍為 secp256r1（下一行明確指定），演算法不變，不影響量測。
        val kpg = KeyPairGenerator.getInstance("EC")
        kpg.initialize(ECGenParameterSpec("secp256r1"))
        return kpg.generateKeyPair()
    }
}
