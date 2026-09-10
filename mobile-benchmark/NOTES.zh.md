# FogHail 乘客與駕駛端 App — 源碼與安裝說明

本包是論文 §5.1「乘客與駕駛端 App 使用 Kotlin 開發、跑在實體 Redmi Note 8 Pro (Android 9)、密碼學套件使用 BouncyCastle」所需的**完整手機端程式**。乘客端與駕駛端**共用同一套編碼與密碼學**(乘客編 9 格、駕駛編 1 格),這支 App 同時量測並填論文的表 3(用戶端計算)與表 5(信譽開銷)。

## 一、檔案清單(`src/`)

| 檔案 | 角色 | 用到的 BouncyCastle |
|---|---|---|
| `FogHailBloom.kt` | **核心編碼模組**:GPS→網格 cell→9 格鄰域→加鹽布隆過濾器;每趟假名派生(secp256r1) | `Blake2bDigest`、`BouncyCastleProvider` |
| `FogHailACL.kt` | **雙邊匿名信譽**:ACL 一次性憑證(secp256r1 上 Schnorr 盲簽章),發行/出示/驗證 | `CustomNamedCurves`、`ECPoint` 群運算 |
| `E3LatencyBench.kt` | **E3 量測**:用戶端編碼四段延遲 `T = T_grid + T_neighbor + T_bloom + T_sign`(nanoTime,1000 次 p50/p95) | 簽章 `SHA256withECDSA` |
| `MainActivity.kt` | **前端**:一畫面三按鈕(①位元對拍 ②量 E3 ③量 E5),結果直接顯示在手機上 | — |
| `reference_vectors.json` | Python 版產生的位元真值,供正確性對拍 | — |

## 二、密碼學套件(BouncyCastle)

只需一行 Gradle 相依,不必手動下載 jar:

```gradle
dependencies {
    implementation 'org.bouncycastle:bcprov-jdk18on:1.78'
}
```

程式已在 `FogHailBloom.kt` 用 `Security.addProvider(BouncyCastleProvider())` 註冊。**雜湊(Blake2b)與 ACL 群運算走 BouncyCastle;但 EC 金鑰與 ECDSA 簽章刻意用 Android 平台預設 provider**(見下方 Android 9 注意事項)。

## 三、建置與執行步驟(Android Studio)

1. **建新專案**:Android Studio → New Project → **Empty Views Activity**;
   - Language 選 **Kotlin**;Package name 設 **`com.foghail.client`**(要和檔案裡的 `package` 一致);
   - Minimum SDK 選 **API 28 (Android 9)** 或更低。
2. **放入源碼**:把 `src/` 裡的 4 個 `.kt` 覆蓋/加入到 `app/src/main/java/com/foghail/client/`(直接取代精靈產生的 `MainActivity.kt`)。
3. **加相依**:在 `app/build.gradle` 的 `dependencies { }` 加上上面那行 BouncyCastle,按 **Sync**。
4. **AndroidManifest**:確認 `AndroidManifest.xml` 的 `<activity>` 指向 `.MainActivity` 且為啟動頁(精靈預設就對)。本 App **不需要任何權限**(不連網、不定位,全在本機算)。
5. **接手機**:用 USB 接 **實體 Android 手機**(務必實機,非模擬器),開發者選項開 USB 偵錯。
6. **Run**:按綠色三角形安裝到手機。畫面出現三個按鈕。

## 四、怎麼跑、看什麼數字

依序按:

- **① 驗證位元對拍(必先過)**:對 `reference_vectors.json` 的每個 cell 比對本機算出的位元是否與 Python 版**完全一致**。**沒全過就不能量延遲**——代表投影/雜湊/位元序有落差(見疑難排解)。
- **② 量 E3 用戶端延遲**:顯示 `T_grid / T_neighbor / T_bloom / T_sign / T_total` 的 p50/p95。**把 `T_total` 填論文表 3「用戶端計算」欄**(對照 ORide 手機 15–26 ms)。
- **③ 量 E5 信譽開銷**:顯示乘客/駕駛的憑證取得(盲簽)/出示/驗證時間與大小。**填論文表 5 手機端欄**(對照 PrivateRide LG G3:取得 554 / 出示 219 / 盲簽 68 ms)。

抄下畫面數字即可,不需 adb / logcat。

## 五、Android 9 兩個必知的坑(程式已處理)

1. **BouncyCastle 的 EC 被移除**:Android 9(API 28)起平台拿掉了 `KeyPairGenerator.getInstance("EC","BC")` 與 `Signature.getInstance(...,"BC")`。程式**改用平台預設 provider(AndroidOpenSSL/Conscrypt,還有硬體加速)**,曲線仍是 **secp256r1**、演算法仍是 **SHA256withECDSA**,不影響量測數字。
2. **主題閃退**:`MainActivity` 繼承**基礎 `android.app.Activity`**(不是 `AppCompatActivity`),量測只用純運算＋基礎 `android.widget`,避免「App 主題非 Theme.AppCompat 後代」造成一開機就閃退。

## 六、疑難排解

| 症狀 | 原因 / 解法 |
|---|---|
| 位元對拍某格不符 | Blake2b 要用 `Blake2bDigest(64)`(64 bit = 8 byte 輸出),**不是** BLAKE2b-512 取前 8 bytes;little-endian 轉 long;負數取正 `((v%m)+m)%m`;9 格順序要一致 |
| 一開機閃退 | 確認 `MainActivity` 是繼承 `Activity`(非 AppCompatActivity);package 名是否為 `com.foghail.client` |
| 找不到 BouncyCastle 類別 | `build.gradle` 那行相依沒加或沒 Sync |
| EC/簽章拋例外 | 不要指定 `"BC"` provider(Android 9 已移除),用平台預設(程式已改好) |

## 七、誠實備註

- **量測務必用實體手機**(非模擬器),且表 3 與表 5 要用**同一支手機**量,環境一致才可比較。
- 位元對拍是為了確保**手機端與 Python 參考版(`experiments/phase1/bloom.py`)產生完全相同的編碼**——這是數字可信的前提。
