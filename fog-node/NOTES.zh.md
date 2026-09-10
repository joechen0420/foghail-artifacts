# FogHail 霧節點（PC 版）— 程式碼與安裝說明

用一台 PC(或 Raspberry Pi)當 FogHail 霧節點,**重現論文的「霧端媒合 0.28 ms」那格數字**,並可看媒合示範。

## 這包裡有什麼

| 檔案 | 用途 |
|---|---|
| `bloom.py` | 霧節點媒合器**核心**(加鹽布隆過濾器,論文的實際參考實作) |
| `fog_latency_bench.py` | **量延遲**——在你這台機器上重現「0.28 ms」(池 100/1000/10000) |
| `fog_node_demo.py` | 媒合示範——直觀看到霧節點收請求→盲測判定→選定駕駛 |

## 需求

- **Python 3.8 以上**。
- **不用 pip 安裝任何套件**——全部只用 Python 標準庫。

裝 Python:
- **Windows**:到 python.org 下載安裝(勾選「Add Python to PATH」);或 `winget install Python.Python.3.12`。
- **Linux / Raspberry Pi**:`sudo apt update && sudo apt install -y python3`。
- 驗證:`python --version`(或 `python3 --version`)顯示 3.8+ 即可。

## 執行

解壓後,在這個資料夾裡開終端機:

**① 量延遲(重點,重現 0.28 ms)**
```
python fog_latency_bench.py
```
會印出三種駕駛池大小的媒合時間,例如:
```
  駕駛池 =   1000：   0.283 ms   （  0.28 µs/駕駛）
```
**「池=1000」那行的 ms,就是對應論文表 2 的 0.28 ms。**

**② 媒合示範(選配,看它怎麼運作)**
```
python fog_node_demo.py
```

> Linux/Pi 若是多核桌機、想對齊論文用的 t3.medium(2 vCPU),限制只用 2 核再量一次:
> ```
> taskset -c 0-1 python fog_latency_bench.py
> ```

## 量完要記下什麼(寫進論文 §5)

1. **「池=1000」那行的 ms**(取代或佐證原本的 0.28 ms)。
2. **這台機器的規格**:CPU 型號、核心數、RAM(腳本會印核心數與 Python 版本;CPU 型號請自行補)。
3. (可選)有沒有用 `taskset` 限 2 核。

## 原理一句話

霧節點把每個駕駛的位元向量和乘客的做一次 `AND` 再比較(`BF_d ⊆ BF_p`),就判斷駕駛那格是否落在乘客的 9 格鄰域裡——**只做位元運算,看不到任何座標**。這就是為什麼一台低規格機器就能在毫秒內完成媒合。

## 誠實備註

這是**論文霧節點的 Python 參考實作**(和 `experiments/phase1/bloom.py`、`experiments/phase2/oride_ref.py` 同一套邏輯)。Python 大整數位元運算其實比編譯語言慢,所以量到的數字是**保守值**(真用 Rust/C 會更快)。
