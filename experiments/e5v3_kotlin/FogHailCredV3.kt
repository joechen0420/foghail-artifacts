package com.foghail.client

import org.bouncycastle.crypto.digests.KeccakDigest
import org.bouncycastle.crypto.digests.SHA256Digest
import org.bouncycastle.crypto.signers.HMacDSAKCalculator
import org.bouncycastle.crypto.ec.CustomNamedCurves
import org.bouncycastle.math.ec.ECPoint
import java.math.BigInteger
import java.security.SecureRandom

/**
 * E5 v3：FogHail v3 信譽憑證（secp256k1 Schnorr 盲簽章、3/4 門檻），
 * 與 Python 參考版 experiments/phase5/foghail_cred.py 逐一對拍。
 *
 * 簽章格式 (addrR', s')：e' = keccak(addrR' ‖ m) mod N，驗證 addr(s'G − e'P) == addrR'。
 * 這個格式讓鏈上合約用一次 ecrecover 就能驗一個簽章（見 contracts/FogHailAttestation.sol）。
 * 盲化：R' = R + aG + bP，e = e' + b，s' = s + a。
 *
 * 量測（填論文 Table 7 的「3-of-4, secp256k1」欄，取代目前的桌機倍率推估）：
 *   - 一次 secp256k1 盲簽、驗一次
 *   - 憑證發行 = 向 3 個驗證節點各做一次盲簽；憑證驗證 = 驗 3 個簽章
 *   - 收據發行 = 同樣 3 次盲簽，訊息是 32 B 隨機序號
 * 計時方式與舊版 FogHailACL.blindIssue 相同（含發行方那一側的運算），兩者才能直接相比。
 *
 * v4（2026-10-14，回應程式稽核 P0-2）：每個部分簽章的申請多附一個「授權簽章」——
 * 以太坊 personal_sign（secp256k1 ECDSA、RFC 6979、low-s）簽
 * authDigest = keccak(abi.encode(合約, 鏈ID, 種類, 批次號, 節點編號, h))，h = keccak(R.x ‖ R.y ‖ e)。
 * 量測多三項：授權簽章一次、v4 憑證發行（3 ×（盲簽＋授權））、v4 收據發行；對拍多一組 Python 向量。
 */
object FogHailCredV3 {
    private val C = CustomNamedCurves.getByName("secp256k1")
    val G: ECPoint = C.g
    val N: BigInteger = C.n
    private val rng = SecureRandom()

    fun randScalar(): BigInteger {
        while (true) {
            val k = BigInteger(N.bitLength(), rng)
            if (k >= BigInteger.ONE && k < N) return k
        }
    }

    /** 32-byte big-endian（對齊 Python int.to_bytes(32,'big')） */
    fun to32(x: BigInteger): ByteArray {
        val b = x.toByteArray()
        val out = ByteArray(32)
        when {
            b.size == 32 -> return b
            b.size < 32 -> System.arraycopy(b, 0, out, 32 - b.size, b.size)
            else -> System.arraycopy(b, b.size - 32, out, 0, 32)
        }
        return out
    }

    /** 以太坊的 Keccak-256（不是 SHA3-256） */
    fun keccak(vararg parts: ByteArray): ByteArray {
        val d = KeccakDigest(256)
        for (p in parts) d.update(p, 0, p.size)
        val o = ByteArray(32)
        d.doFinal(o, 0)
        return o
    }

    /** 點 → 以太坊地址：keccak(x ‖ y) 後 20 B */
    fun addrOf(P: ECPoint): ByteArray {
        val q = P.normalize()
        val h = keccak(to32(q.affineXCoord.toBigInteger()), to32(q.affineYCoord.toBigInteger()))
        return h.copyOfRange(12, 32)
    }

    fun challenge(addrR: ByteArray, m: ByteArray): BigInteger = BigInteger(1, keccak(addrR, m)).mod(N)

    class Sig(val addrR: ByteArray, val s: BigInteger)

    fun verify(P: ECPoint, m: ByteArray, sig: Sig): Boolean {
        val e = challenge(sig.addrR, m)
        val rv = G.multiply(sig.s).add(P.multiply(N.subtract(e))).normalize()
        if (rv.isInfinity) return false
        return addrOf(rv).contentEquals(sig.addrR)
    }

    /** 一把發行金鑰。同一時間只允許一個盲簽流程（防 ROS 攻擊）。 */
    class Issuer(val x: BigInteger = randScalar()) {
        val P: ECPoint = G.multiply(x).normalize()
        private var k: BigInteger? = null

        @Synchronized fun commit(): ECPoint {
            check(k == null) { "issuer busy: concurrent blind session refused (ROS)" }
            val kk = randScalar(); k = kk
            return G.multiply(kk).normalize()
        }

        @Synchronized fun respond(e: BigInteger): BigInteger {
            val kk = k ?: error("no open session")
            k = null
            return kk.add(e.multiply(x)).mod(N)
        }
    }

    /** 使用者端一次盲簽流程（含發行方回應），回傳去盲後的簽章。 */
    fun blindSign(iss: Issuer, m: ByteArray): Sig {
        val r = iss.commit()
        val a = randScalar(); val b = randScalar()
        val rp = r.add(G.multiply(a)).add(iss.P.multiply(b)).normalize()
        val addrRp = addrOf(rp)
        val eP = challenge(addrRp, m)
        val s = iss.respond(eP.add(b).mod(N))
        return Sig(addrRp, s.add(a).mod(N))
    }

    // ------------------------------------------------------------------ v4：持有人授權簽章
    val KIND_CRED: ByteArray = keccak("FOGHAIL_CRED".toByteArray(Charsets.US_ASCII))
    val KIND_RCPT: ByteArray = keccak("FOGHAIL_RCPT".toByteArray(Charsets.US_ASCII))
    private val HALF_N: BigInteger = N.shiftRight(1)
    private val ETH_PREFIX = "\u0019Ethereum Signed Message:\n32".toByteArray(Charsets.US_ASCII)

    /** abi.encode 的一個 32 B 字（address／uint 一律左補零） */
    private fun word(b: ByteArray): ByteArray {
        val o = ByteArray(32); System.arraycopy(b, 0, o, 32 - b.size, b.size); return o
    }

    fun sessionHash(R: ECPoint, e: BigInteger): ByteArray {
        val q = R.normalize()
        return keccak(to32(q.affineXCoord.toBigInteger()), to32(q.affineYCoord.toBigInteger()), to32(e))
    }

    fun authDigest(contract: ByteArray, chainId: Long, kind: ByteArray, ctx: Long, v: Int, h: ByteArray): ByteArray =
        keccak(word(contract), to32(BigInteger.valueOf(chainId)), kind, to32(BigInteger.valueOf(ctx)),
               to32(BigInteger.valueOf(v.toLong())), h)

    fun ethAddress(d: BigInteger): ByteArray = addrOf(G.multiply(d))

    /** personal_sign：ECDSA over keccak(前綴 ‖ digest)，RFC 6979 決定性 k、low-s；回傳 r ‖ s ‖ v（65 B）。 */
    fun ethSign(d: BigInteger, digest: ByteArray): ByteArray {
        val z = keccak(ETH_PREFIX, digest)
        val zi = BigInteger(1, z)
        val kc = HMacDSAKCalculator(SHA256Digest()); kc.init(N, d, z)
        while (true) {
            val k = kc.nextK()
            val R = G.multiply(k).normalize()
            val r = R.affineXCoord.toBigInteger().mod(N)
            if (r.signum() == 0) continue
            var s = k.modInverse(N).multiply(zi.add(r.multiply(d))).mod(N)
            if (s.signum() == 0) continue
            var rec = if (R.affineYCoord.toBigInteger().testBit(0)) 1 else 0
            if (s > HALF_N) { s = N.subtract(s); rec = rec xor 1 }
            return to32(r) + to32(s) + byteArrayOf((27 + rec).toByte())
        }
    }

    /** v4 一次部分簽章的申請：盲簽會談＋持有人對這次會談的授權簽章。 */
    fun blindSignV4(iss: Issuer, m: ByteArray, holder: BigInteger, contract: ByteArray, kind: ByteArray,
                    ctx: Long, vIdx: Int): Pair<Sig, ByteArray> {
        val r = iss.commit()
        val a = randScalar(); val b = randScalar()
        val rp = r.add(G.multiply(a)).add(iss.P.multiply(b)).normalize()
        val addrRp = addrOf(rp)
        val e = challenge(addrRp, m).add(b).mod(N)
        val auth = ethSign(holder, authDigest(contract, 1337, kind, ctx, vIdx, sessionHash(r, e)))
        val s = iss.respond(e)
        return Sig(addrRp, s.add(a).mod(N)) to auth
    }

    fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
    fun unhex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    // ------------------------------------------------------------------ 量測
    data class Stat(val p50: Double, val p95: Double)

    private fun stat(xs: DoubleArray): Stat {
        xs.sort(); fun q(p: Double) = xs[(p * (xs.size - 1)).toInt()]
        return Stat(q(0.5), q(0.95))
    }

    private inline fun timeIt(n: Int, warm: Int, f: (Int) -> Unit): Stat {
        for (i in 0 until warm) f(i)
        val ts = DoubleArray(n)
        for (i in 0 until n) {
            val t = System.nanoTime(); f(i); ts[i] = (System.nanoTime() - t) / 1e6
        }
        return stat(ts)
    }

    /**
     * 跑全部量測。r1 基準（舊版 FogHailACL，單一發行者 secp256r1）在同一次執行裡一起量，
     * 這樣「v3 / v1」的倍率是同一支手機、同一個時段量出來的。
     */
    fun bench(n: Int = 200, warm: Int = 20): Map<String, Any> {
        val res = LinkedHashMap<String, Any>()
        // r1 基準
        val iss1 = FogHailACL.Issuer()
        val msg1 = ByteArray(32) { 7 }
        val c1 = FogHailACL.blindIssue(iss1, msg1)
        res["r1_single_issue"] = timeIt(n, warm) { FogHailACL.blindIssue(iss1, msg1) }
        res["r1_single_verify"] = timeIt(n, warm) { FogHailACL.verify(iss1.PK, msg1, c1) }

        // v3：3 個驗證節點
        val vals = List(3) { Issuer() }
        val pseud = ByteArray(20) { 0x11 }                 // 憑證訊息 = 20 B 假名地址
        val one = blindSign(vals[0], pseud)
        res["k1_single_issue"] = timeIt(n, warm) { blindSign(vals[0], pseud) }
        res["k1_single_verify"] = timeIt(n, warm) { verify(vals[0].P, pseud, one) }

        var okCred = 0
        val sigs = vals.map { blindSign(it, pseud) }
        res["cred_issue_3of4"] = timeIt(n, warm) { vals.forEach { v -> blindSign(v, pseud) } }
        res["cred_verify_3of4"] = timeIt(n, warm) {
            if (vals.indices.all { j -> verify(vals[j].P, pseud, sigs[j]) }) okCred++
        }
        res["cred_show"] = timeIt(n, warm) {
            // 出示 = 假名地址 20 B + 3 × (索引 1 B + addrR 20 B + s 32 B) = 179 B
            var out = pseud
            for ((i, s) in sigs.withIndex()) out += byteArrayOf(i.toByte()) + s.addrR + to32(s.s)
            check(out.size == 179)
        }

        val serial = ByteArray(32) { 0x22 }               // 收據訊息 = 32 B 隨機序號
        res["receipt_issue_3of4"] = timeIt(n, warm) { vals.forEach { v -> blindSign(v, serial) } }

        // v4：每個部分簽章多一個授權簽章（憑證由根私鑰簽、收據由假名私鑰簽）
        val rootKey = randScalar(); val pseudKey = randScalar()
        val contract = ByteArray(20) { 0x11 }
        val hSample = sessionHash(G.multiply(BigInteger.valueOf(7)), BigInteger.valueOf(123456789))
        res["auth_sign_once"] = timeIt(n, warm) {
            ethSign(rootKey, authDigest(contract, 1337, KIND_CRED, 1, 0, hSample))
        }
        res["cred_issue_3of4_v4"] = timeIt(n, warm) {
            vals.forEachIndexed { j, v -> blindSignV4(v, pseud, rootKey, contract, KIND_CRED, 1, j) }
        }
        res["receipt_issue_3of4_v4"] = timeIt(n, warm) {
            vals.forEachIndexed { j, v -> blindSignV4(v, serial, pseudKey, contract, KIND_RCPT, 0, j) }
        }
        val dg = authDigest(contract, 1337, KIND_CRED, 1, 0, hSample)
        res["auth_sample"] = mapOf("key_hex" to hex(to32(rootKey)), "digest_hex" to hex(dg),
                                   "sig_hex" to hex(ethSign(rootKey, dg)), "addr_hex" to hex(ethAddress(rootKey)))

        res["correct_all_runs"] = (okCred == n + warm)
        res["cred_bytes"] = 179
        res["receipt_bytes"] = 32 + 1 + 3 * 53
        // 一筆手機簽出的樣本，回傳後在電腦上用 Python 再驗一次（check_phone_result.py）。
        // 這把金鑰是本次量測臨時產生的測試金鑰，公開無妨。
        val sample = blindSign(vals[0], pseud)
        res["sample"] = mapOf(
            "x_hex" to hex(to32(vals[0].x)), "msg_hex" to hex(pseud),
            "addrR_hex" to hex(sample.addrR), "s_hex" to hex(to32(sample.s))
        )
        return res
    }
}
