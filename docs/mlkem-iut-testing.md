# ML-KEM (FIPS 203) IUT 測試總流程

從一台全新的機器，到看到綠色的 `passed` 結果，完整測試 ML-KEM 受測實作（IUT）
harness 的步驟。流程與 ML-DSA 相同，只是換成 FIPS 203 / ML-KEM。

## IUT 是什麼（以及不是什麼）

IUT **不是**網頁程式，而是位於 `IUT-tests/mlkem-native/` 的一支 CLI harness。
它把 ACVP **prompt**（伺服器出的挑戰向量）轉成 **response**（作答），底層用
vendored 的 `third_party/kyber-py` 做運算。ACVP 迴圈：

```
建立 session ──▶ 伺服器 (NIST GenVal) 產生 prompt
                     │
                     ▼
             用 IUT harness 跑 prompt  ──▶ response.json
                     │
                     ▼
             上傳並提交 response ──▶ GenVal 驗證 ──▶ passed / failed
```

- **prompt** 裝的是輸入：`d`、`z`（keyGen）；`ek`、`m` /`dk`、`c`（encapDecap）。
- **response** 裝的是輸出：`ek`、`dk`（keyGen）；`c`、`k` / `k` / `testPassed`。
- **不要把 prompt 當成 response 上傳**——那是題目，不是答案。

## 前置需求

- **Python 3.9+**、**.NET 8 SDK**、**Node.js**（用 Homebrew：`brew install node`）
- 切到 `203IUT` 分支：`git checkout 203IUT`
- NIST 原始碼已 vendored 在 `third_party/nist-acvp-server/`

## 一次性設定

```bash
cd ~/Desktop/NCCU-ACVP-Server

# 1. 建置 NIST GenVal（編譯 .NET 方案 → .nist-bin/）
bash scripts/nist/build_nist_genval.sh

# 2. 坑一：.nist-bin 是 dot 開頭目錄；.NET 的 PhysicalFileProvider 會拒絕讀取
#    dot 目錄下的 sharedappsettings.json。把二進位複製到「非 dot 目錄」再從那裡執行。
mkdir -p ~/nist-run
cp -R .nist-bin/genval-runner  ~/nist-run/
cp -R .nist-bin/orleans-server ~/nist-run/

# 3. 後端 Python 環境
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cd ..

# 4. 前端依賴
cd frontend && npm ci && cd ..
```

## 啟動三個服務（三個終端機，全部保持開著）

> 坑二：Orleans silo 會佔用 **8000** 埠，跟後端預設衝突。後端改用 **8001**。

**終端機 1 — Orleans silo**（會一直執行；「卡住不動」是正常的）：
```bash
cd ~/nist-run/orleans-server
dotnet ./NIST.CVP.ACVTS.Orleans.ServerHost.dll --console
# gateway 監聽 30000；macOS 上的 PerfCounter 警告可忽略
```

**終端機 2 — 後端（8001）：**
```bash
cd ~/Desktop/NCCU-ACVP-Server/backend
source .venv/bin/activate
export ACVP_GENVAL_RUNNER_DLL="$HOME/nist-run/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll"
export ACVP_GENVAL_TIMEOUT_SECONDS=300
uvicorn app.main:app --host 127.0.0.1 --port 8001
# 健康檢查：curl -s http://127.0.0.1:8001/acvp/v1/algorithms | head -c 100
```

**終端機 3 — 前端（5173）：**
```bash
cd ~/Desktop/NCCU-ACVP-Server/frontend
VITE_API_BASE_URL=http://127.0.0.1:8001 npm run dev
# 瀏覽器開 http://127.0.0.1:5173
```

## 測試迴圈 A：keyGen（網頁版）

1. 演算法選 **FIPS 203 / ML-KEM**、模式 `keyGen`、參數集 `ML-KEM-512`，勾選
   **isSample**。
2. **建立 test session** → 狀態變 `vectorReady`（GenVal 已產生 prompt）。
3. **下載 prompt**（例如 `ML-KEM-keyGen-vs1-prompt.json`）。
4. **用 IUT harness 跑這份 prompt**（終端機 4）：
   ```bash
   cd ~/Desktop/NCCU-ACVP-Server/IUT-tests/mlkem-native
   python3 run_test.py \
     --prompt ~/Downloads/ML-KEM-keyGen-vs1-prompt.json \
     --response-dir ./response --variant pass --expect-mode keyGen
   ```
   產生 `response/response_pass_keyGen.json`（每筆現在都有 `ek` / `dk`）。
5. **Upload response JSON** → 選 `response_pass_keyGen.json`（**不是** prompt）。
6. 點 **Submit response**，再點 **Refresh results**。
   - `unreceived` → `passed`；test session `passed: true`。✅

參考數量：`ML-KEM-512` 單一參數集約 25 筆測試。

### 負向測試（試錯）

同樣流程但改用 `--variant fail`，上傳 `response_fail_keyGen.json`，在**新的
session** 提交。GenVal 會回 `disposition: fail`，第一筆會失敗
（`EncapsulationKey does not match`）——證明驗證端確實會擋掉錯誤答案。

## 測試迴圈 B：encapDecap（網頁版）

`encapDecap` 才是 ML-KEM 的核心功能（金鑰封裝／解封裝）。**兩個模式都測過才算
完整驗證 FIPS 203**，只測 `keyGen` 等於只驗證「會生鑰匙」。

1. 演算法選 **FIPS 203 / ML-KEM**、模式 **`encapDecap`**、參數集 `ML-KEM-512`，
   勾選 **isSample**，並**勾選 functions**（建議四個全勾）：
   - `encapsulation`
   - `decapsulation`
   - `encapsulationKeyCheck`
   - `decapsulationKeyCheck`

   > `encapDecap` 的 function 清單**不可為空**，這點與 `keyGen` 不同。

2. **建立 test session** → `vectorReady`。
3. **下載 prompt**（例如 `ML-KEM-encapDecap-vs1-prompt.json`；檔案會比 keyGen
   大不少，約 150 KB 是正常的）。
4. **用 IUT harness 跑這份 prompt**：
   ```bash
   cd ~/Desktop/NCCU-ACVP-Server/IUT-tests/mlkem-native
   python3 run_test.py \
     --prompt ~/Downloads/ML-KEM-encapDecap-vs1-prompt.json \
     --response-dir ./response --variant pass --expect-mode encapDecap
   ```
   產生 `response/response_pass_encapDecap.json`。也可以用包裝腳本，效果相同：
   ```bash
   python3 run_encapdecap.py --prompt ~/Downloads/ML-KEM-encapDecap-vs1-prompt.json
   ```
5. **Upload response JSON** → 選 `response_pass_encapDecap.json`。
6. **Submit response** → **Refresh results** → `passed`。✅

參考數量：`ML-KEM-512` + 四個 function 約 **4 個測試組、55 筆**，其中
encapsulation 25 筆（輸出 `c`,`k`）、decapsulation 10 筆（輸出 `k`）、
兩種 keyCheck 共 20 筆（輸出 `testPassed`）。

### 關於 `--expect-mode`

這是**選用的安全檢查**，不影響運算。harness 會自己從 prompt 讀出 mode；加了
`--expect-mode` 只是多一道「拿錯檔案就報錯」的保險：

```
prompt 是 encapDecap + --expect-mode keyGen → error: prompt mode 'encapDecap'
does not match expected mode 'keyGen'
```

不加也可以，harness 一樣會自動判斷並輸出對應檔名：

```bash
python3 run_test.py --prompt ~/Downloads/ML-KEM-encapDecap-vs1-prompt.json
```

## 測試迴圈（curl 版，不用開前端）

```bash
BASE=http://127.0.0.1:8001
SID=$(curl -s -X POST $BASE/acvp/v1/testSessions -H "Content-Type: application/json" -d '[
  {"acvVersion":"1.0"},
  {"algorithms":[{"algorithm":"ML-KEM","revision":"FIPS203","mode":"keyGen","parameterSets":["ML-KEM-512"]}],
   "autoGenerateVectorSets":true,"isSample":true}
]' | python3 -c "import sys,json;print(json.load(sys.stdin)[1]['testSessionId'])")

curl -s $BASE/acvp/v1/testSessions/$SID/vectorSets/1 > /tmp/p.json
cd IUT-tests/mlkem-native
python3 run_test.py --prompt /tmp/p.json --response-dir /tmp/r --variant pass --expect-mode keyGen
python3 -c "import json;json.dump([{'acvVersion':'1.0'},json.load(open('/tmp/r/response_pass_keyGen.json'))],open('/tmp/sub.json','w'))"
curl -s -X POST $BASE/acvp/v1/testSessions/$SID/vectorSets/1/results \
  -H "Content-Type: application/json" --data @/tmp/sub.json > /dev/null
curl -s $BASE/acvp/v1/testSessions/$SID/vectorSets/1/results | python3 -m json.tool | head -20
#   → disposition: "passed"
```

要改測 `encapDecap`，只要把上面第一段的註冊物件換成下面這個，其餘流程相同
（記得把 `--expect-mode` 與檔名的 `keyGen` 一併改成 `encapDecap`）：

```json
{"algorithm":"ML-KEM","revision":"FIPS203","mode":"encapDecap",
 "parameterSets":["ML-KEM-512"],
 "functions":["encapsulation","decapsulation","encapsulationKeyCheck","decapsulationKeyCheck"]}
```

## harness 涵蓋的模式與函式

| mode | function | 包裝腳本 | 讀取 | 輸出 |
|------|----------|---------|------|------|
| keyGen | — | `run_keygen.py` / `run_keygen_fail.py` | `z`、`d` | `ek`、`dk` |
| encapDecap | encapsulation | `run_encapdecap.py` | `ek`、`m` | `c`、`k` |
| encapDecap | decapsulation | `run_encapdecap.py` | `dk`、`c` | `k` |
| encapDecap | encapsulationKeyCheck | `run_encapdecap.py` | `ek` | `testPassed` |
| encapDecap | decapsulationKeyCheck | `run_encapdecap.py` | `dk` | `testPassed` |

若要測 `encapDecap`，建立 session 時用 `"mode":"encapDecap"` 並選好要測的
function，然後對下載的 prompt 跑 `run_test.py --expect-mode encapDecap`。

## 收尾

在三個服務的終端機各按 `Ctrl+C` 即可。`IUT-tests/mlkem-native/` 底下的
`response/` 和 `prompt/` 目錄已被 git 忽略，產生的檔案不會污染版控。

## 故障排除

| 症狀 | 原因 | 解法 |
|------|------|------|
| `sharedappsettings.json was not found` | 從 `.nist-bin`（dot 目錄）執行 GenVal | 改從 `~/nist-run/...` 執行（坑一） |
| `address already in use (8001)` | 已經有一個後端在 8001 上跑 | 先關掉它，或換一個埠 |
| `zsh: command not found: npm` | 沒裝 Node.js | `brew install node` |
| Orleans 終端機「卡住不動」 | 它是伺服器，本來就這樣 | 讓它開著，用其他終端機操作 |
| 驗證一直顯示 `unreceived` | 還沒提交 response，或把 prompt 當 response 上傳 | 上傳 harness 產生的 **response**，再按 Submit |
| 第一筆失敗 `EncapsulationKey does not match` | 你上傳的是 `fail` 變體 | 負向測試的預期結果；要看 pass 就用 `pass` 變體 |
| `zsh: command not found: #` | 把本文件裡 `#` 開頭的**註解行**一起貼進終端機了（zsh 互動模式預設不把 `#` 當註解） | 無害，可忽略；貼指令時跳過 `#` 開頭的行 |
| `error: prompt mode 'X' does not match expected mode 'Y'` | `--expect-mode` 與 prompt 實際模式不符（拿錯 prompt 檔） | 改用正確的 prompt，或把 `--expect-mode` 改對／直接不加 |
