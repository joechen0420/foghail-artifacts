# Phase 5 — ACL 匿名信譽（表 5，Python 參考版）

雙邊不可連結信譽的密碼學核心:secp256r1 上的 Schnorr 盲簽章一次性憑證。此為 **Python 參考版**;論文表 5 的**手機端**數字由 Kotlin 版量測(見「乘客與駕駛端 App」包的 `FogHailACL.kt`)。

## 產生論文的哪些數據

- **表 5（Python 參考版對拍）**:憑證取得(盲簽)/出示/驗證時間、憑證大小 96 B。與 Kotlin 手機版邏輯逐一對拍;與 PrivateRide LG-G3（取得 554 / 出示 219 / 盲簽 68 ms）對照。

## 檔案

| 檔 | 用途 |
|---|---|
| `acl_reputation.py` | ACL 一次性憑證:發行方(鏈上多簽代表)盲簽假名 → 使用者去盲得憑證,證明「R≥θ」而不洩身分;量取得/出示/驗證時間,並驗證正確性 |

## 相依

```
pip install numpy ecdsa
```
（`secrets` 為 Python 標準庫。）

## 執行

```
python acl_reputation.py
```

## 備註

- 發行與出示以**隨機盲因子**確保不可連結;每張憑證**一次性**(一票一用)。
- 這支與 Kotlin 的 `FogHailACL.kt`(手機端)是**同一套盲簽章協定**,兩邊數字應對得起來——手機端量測請用「乘客與駕駛端 App」包在實體手機上跑。
- 論文對「發行方殘餘信任」的討論:鏈上多簽 = t-of-n 信任,弱於 PrivateRide 的單一 SP(§4.3 / §7)。
