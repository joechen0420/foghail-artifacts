# E5 v3：3/4 門檻信譽憑證的手機實測（2026-10-14）

論文 Table 7 的「3-of-4, secp256k1」欄目前是**桌機倍率推估**（`experiments/phase5/bench_v3_client.py`）。
這個資料夾讓學生在 Redmi Note 8 Pro 上實測，把推估換成實測值。

## 檔案

| 檔案 | 內容 |
|---|---|
| `FogHailCredV3.kt` | v3 憑證的 Kotlin 實作，與 `../phase5/foghail_cred.py` 逐一對拍：secp256k1 Schnorr 盲簽、挑戰值綁 R 的地址（Keccak-256）、ROS 鎖、量測函式 |
| `MainActivity.kt` | 量測 App 的畫面。①②③ 與 8 月的 E3／E5 相同；④ v3 對拍、⑤ v3 量測、⑥ 把結果 JSON 複製到剪貼簿 |
| `V3VectorTest.kt` | JVM 單元測試：Python 參考向量、私鑰 1 的已知地址、盲簽自驗、ROS 鎖、量測冒煙測試 |
| `reference_vectors_v3.json` | Python 產生的參考向量（App 與測試內嵌同一組） |
| `app_build.gradle.kts`、`AndroidManifest.xml` | 建 APK 用的 app 模組設定（AGP 9.2.1、BouncyCastle 1.79、minSdk 26） |
| `check_phone_result.py` | 收到學生傳回的 JSON 後執行：用 Python 重驗手機簽出的樣本、印出 Table 7 數字，存到 `out/v3_phone_<裝置>.json` |

## 已在電腦上驗過的

- 4 項 JVM 單元測試全部通過。
- Kotlin 簽出的樣本，`check_phone_result.py` 用 Python 重新驗證：通過。
- APK 編譯成功：套件 `com.foghail.client`，Android 8.0（SDK 26）以上可裝。

另外，JVM 上 BouncyCastle 的 secp256k1 比 secp256r1 快，3/4 門檻只是單一 r1 流程的約 1.6 倍，不是桌機 Python 的 3.19 倍。所以手機實測值**很可能比論文目前的估計（每趟約 14 ms）好**。這只是 JVM 上的觀察，要以手機實測為準。

## 2026-10-14 再更新：v4 授權簽章

回應程式稽核 P0-2，v4 每個部分簽章的申請多附一個授權簽章（以太坊 personal_sign，secp256k1 ECDSA、RFC 6979、low-s）。
App 的 ⑤ 多量三項：`auth_sign_once`、`cred_issue_3of4_v4`、`receipt_issue_3of4_v4`；④ 多一行對拍
（手機簽出的授權簽章必須與 Python `foghail_cred.esign` **逐位元組相同**）。JVM 單元測試 5 項全過。
`check_phone_result.py` 會用 Python 還原手機簽的授權簽章位址，並以 v4 數字對照論文（9.5 ms／每趟 19 ms）。


⚠️ 建置注意：Android Gradle Plugin 拒絕含中文的專案路徑，要複製到純英文路徑再建；
`local.properties` 的 `sdk.dir` 用正斜線（反斜線會被當成 `\u` 跳脫而失敗）。
