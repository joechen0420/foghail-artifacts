package com.foghail.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.math.BigInteger

/** 在電腦 JVM 上先驗 v3 程式：對拍 Python 參考向量、盲簽自驗、ROS 鎖、跑一次小量測並輸出樣本。 */
class V3VectorTest {
    private val V = FogHailCredV3
    private val msg = V.unhex("1111111111111111111111111111111111111111")
    private val vectors = listOf(
        listOf("44b47b75112ccd766df0fc3f6cd3970b7bcc50d857915211b48ea6e03fe56250", "914b727fcea9985a7b8f746c99dde7ac2fda9cab",
               "5dd4ba9b8c603a6f595535072984caf9e2342305", "7e22ac2f322c7ff410ecb1930a6346dc0f744159bb4ea39899405eaf49927016"),
        listOf("5edf81d118c8353da9e62f86ed948c66c7d28bf3bb75671b693322f8868e33a7", "a28e32fecb540bdd060c842e2330b0653c5d6367",
               "ff3860e05e62ee4d1a5ed0a62a4e1d37bb5f888c", "4881c8db9f28ef8dadd93419d624672f660710f6ef40f19d199838c1f29fd7f1"),
        listOf("bc9b41099e57ca6e5ce415d23b7729bab029cd73a6f42eed9a94945c2cb4555e", "d3f39db69c61470ca01e82531614b384a511e993",
               "c6efc3de1e4a7d8be80e7e2bc2f4028a1d3c9aad", "d85de3863bda28cd461bc05f3890cbbc37663fe412bae67cc0e0dfa3618a534d"),
    )

    @Test fun keccakAddress() {
        assertEquals("7e5f4552091a69125d5dfcb7b8c2659029395bdf", V.hex(V.addrOf(V.G.multiply(BigInteger.ONE))))
    }

    @Test fun pythonVectors() {
        for (v in vectors) {
            val P = V.G.multiply(BigInteger(v[0], 16)).normalize()
            assertEquals(v[1], V.hex(V.addrOf(P)))
            assertTrue(V.verify(P, msg, FogHailCredV3.Sig(V.unhex(v[2]), BigInteger(v[3], 16))))
            assertFalse(V.verify(P, msg, FogHailCredV3.Sig(V.unhex(v[2]), BigInteger(v[3], 16).add(BigInteger.ONE))))
        }
    }

    @Test fun blindAndRos() {
        val iss = FogHailCredV3.Issuer()
        assertTrue(V.verify(iss.P, msg, V.blindSign(iss, msg)))
        iss.commit()
        assertTrue(runCatching { iss.commit() }.isFailure)
    }

    @Test fun benchSmokeAndSample() {
        val r = V.bench(30, 5)
        assertEquals(true, r["correct_all_runs"])
        @Suppress("UNCHECKED_CAST") val s = r["sample"] as Map<String, String>
        File("build/v3_sample.txt").writeText(s.entries.joinToString("\n") { "${it.key}=${it.value}" })
        val out = StringBuilder()
        for ((k, v) in r) if (v is FogHailCredV3.Stat) out.append("$k p50=%.3f p95=%.3f\n".format(v.p50, v.p95))
        File("build/v3_bench_jvm.txt").writeText(out.toString())
    }
}
