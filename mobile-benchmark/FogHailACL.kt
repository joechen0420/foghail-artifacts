package com.foghail.client

import org.bouncycastle.crypto.ec.CustomNamedCurves
import java.math.BigInteger
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * E5：ACL 一次性信譽憑證（secp256r1 上的 Schnorr 盲簽章），與 Python 參考版
 * experiments/phase5/acl_reputation.py 邏輯逐一對拍。
 *
 * 流程：發行方（鏈上多簽合約代表）盲簽使用者假名 → 使用者去盲得一次性憑證，
 * 證明「信譽 R≥θ」而不洩身分；發行與出示以隨機盲因子確保不可連結。
 * 量測：取得（盲簽）/ 出示 / 驗證 的時間，填論文表 5 手機端欄。
 */
object FogHailACL {
    private val P = CustomNamedCurves.getByName("secp256r1")
    private val G = P.g                 // 生成元
    private val N: BigInteger = P.n      // 群階
    private val rng = SecureRandom()

    /** 隨機 scalar ∈ [1, N-1] */
    private fun randScalar(): BigInteger {
        while (true) {
            val k = BigInteger(N.bitLength(), rng)
            if (k >= BigInteger.ONE && k < N) return k
        }
    }

    /** 32-byte big-endian（對齊 Python int.to_bytes(32,'big')） */
    private fun to32(x: BigInteger): ByteArray {
        val b = x.toByteArray()
        val out = ByteArray(32)
        when {
            b.size == 32 -> return b
            b.size < 32 -> System.arraycopy(b, 0, out, 32 - b.size, b.size)
            else -> System.arraycopy(b, b.size - 32, out, 0, 32)   // 去掉前導 0
        }
        return out
    }

    /** H(point..., msgBytes) mod N，對齊 Python _H（點以 x||y 各 32B，訊息直接接） */
    private fun hash(vararg items: Any): BigInteger {
        val md = MessageDigest.getInstance("SHA-256")
        for (it in items) when (it) {
            is ByteArray -> md.update(it)
            is org.bouncycastle.math.ec.ECPoint -> {
                val q = it.normalize()
                md.update(to32(q.affineXCoord.toBigInteger()))
                md.update(to32(q.affineYCoord.toBigInteger()))
            }
        }
        return BigInteger(1, md.digest()).mod(N)
    }

    // ---- 發行方金鑰 ----
    class Issuer {
        val sk: BigInteger = randScalarPublic()
        val PK = G.multiply(sk).normalize()
        companion object { private fun randScalarPublic() = FogHailACL.randScalar() }
    }

    data class Credential(val ePrime: BigInteger, val sPrime: BigInteger)

    /** 盲簽章一輪：對 msg 取得可驗證的一次性憑證（發行方不知 msg 內容）。 */
    fun blindIssue(iss: Issuer, msg: ByteArray): Credential {
        val k = randScalar()
        val Rc = G.multiply(k).normalize()                 // 發行方承諾
        val a = randScalar(); val b = randScalar()          // 使用者盲因子
        val Rp = Rc.add(G.multiply(a)).add(iss.PK.multiply(b)).normalize()
        val ePrime = hash(Rp, msg)
        val e = ePrime.add(b).mod(N)                        // 送給發行方的挑戰
        val s = k.add(e.multiply(iss.sk)).mod(N)            // 發行方回應
        val sPrime = s.add(a).mod(N)                        // 使用者去盲
        return Credential(ePrime, sPrime)
    }

    /** 驗證一次性憑證：H(s'G − e'·PK, msg) == e' */
    fun verify(PK: org.bouncycastle.math.ec.ECPoint, msg: ByteArray, c: Credential): Boolean {
        val Rv = G.multiply(c.sPrime).add(PK.multiply(N.subtract(c.ePrime))).normalize()
        return hash(Rv, msg) == c.ePrime
    }

    data class Stat(val p50: Double, val p95: Double)
    private fun stat(xs: DoubleArray): Stat {
        xs.sort(); fun q(p: Double) = xs[(p * (xs.size - 1)).toInt()]
        return Stat(q(0.5), q(0.95))
    }

    /** 量測某一方（乘客/駕駛）n 次憑證操作（毫秒 p50/p95），並驗證正確性。 */
    fun bench(role: String, n: Int): Map<String, Any> {
        val iss = Issuer()
        val issue = DoubleArray(n); val show = DoubleArray(n); val ver = DoubleArray(n)
        var ok = 0
        for (i in 0 until n) {
            val md = MessageDigest.getInstance("SHA-256")
            val msg = md.digest("$role-pseudo-$i-R>=theta".toByteArray())
            var t = System.nanoTime()
            val cred = blindIssue(iss, msg)
            issue[i] = (System.nanoTime() - t) / 1e6
            t = System.nanoTime()
            val payload = msg + to32(cred.ePrime) + to32(cred.sPrime)   // 出示酬載
            show[i] = (System.nanoTime() - t) / 1e6
            t = System.nanoTime()
            if (verify(iss.PK, msg, cred)) ok++
            ver[i] = (System.nanoTime() - t) / 1e6
            @Suppress("UNUSED_EXPRESSION") payload
        }
        val si = stat(issue); val ss = stat(show); val sv = stat(ver)
        return mapOf(
            "role" to role, "verified_ok" to (ok == n),
            "issue_p50" to si.p50, "issue_p95" to si.p95,
            "show_p50" to ss.p50, "verify_p50" to sv.p50, "verify_p95" to sv.p95,
            "cred_bytes" to 96
        )
    }
}
