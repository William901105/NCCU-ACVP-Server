# ML-KEM `FIPS203-tr1` 支援 — 實作規格書

> 狀態：**已實作（code 側），端到端待 GenVal 升級**　｜　日期：2026-07-23　｜　分支：203IUT
> 目的：定義並記錄本專案新增 ACVP `ML-KEM / encapDecap / FIPS203-tr1` 測試修訂的
> 全部變更。第 3 節資料模型已對照真實 GenVal v1.1.0.43 樣本校正。
>
> **已完成並驗證**：後端多-revision 模組 + `keyFormats`（233 backend tests 綠，含
> 驗證真實 NIST tr1 sample prompt）；harness 對真實 NIST tr1 prompt 的 encapsulation
> / decapsulation(seed+expanded) / encapsulationKeyCheck 輸出，逐欄比對 NIST 官方
> expectedResults **240 項 0 mismatch**。
> **decapsulationKeyCheck 已解**：原「待釐清」的互動，已直接以 GenVal v1.1.0.43
> 原始碼證實為 **NIST 端缺陷**（keyCheck group 未設 keyFormat → 預設 `none` → prompt
> 不附金鑰），符規 IUT 無法產出 `testPassed`；本專案行為正確（見 3.3）。
> **未完成**：GenVal 升級到 v1.1.0.43 才能在本站台實跑生成/驗證（非必要，格式與
> 語意已以官方 sample + 原始碼完整確認）。

---

## 0. 一句話總結

`FIPS203-tr1` 是 **ACVP 測試修訂第 1 版**（test revision 1），針對**不變的** FIPS 203
密碼標準，新增了 `keyFormats`（`seed` / `expanded` 私鑰格式）測試能力。要支援它，
**必先升級 vendored 的 NIST GenVal**，再改後端模組與 IUT harness。

---

## 1. 背景與差異

| 項目 | `FIPS203`（現況） | `FIPS203-tr1`（新增目標） |
|------|------------------|--------------------------|
| 密碼標準 | FIPS 203 正式版 | 同一份，**未變** |
| `functions`（registration） | 本專案掛在此（現況） | 規格上屬於 tr1（`encapsulation`/`decapsulation`/`encapsulationKeyCheck`/`decapsulationKeyCheck`） |
| `keyFormats`（registration） | 無 | **新增**，array，值為 `"expanded"`、`"seed"` |
| testGroup `function` | 有（現況） | 有 |
| testGroup `keyFormat` | 無 | **新增**，`"expanded"` 或 `"seed"` |
| 私鑰在向量中的表示 | `dk`（expanded） | `dk`（expanded）**或** `seed`（64 bytes = d‖z） |

> 相容策略：**保留現有 `FIPS203` 不動，新增 `FIPS203-tr1` 為並行 revision**（additive），
> 避免破壞已通過 240/240 的既有流程。

---

## 2. 硬前提（階段 0）：升級 NIST GenVal 到 v1.1.0.43

本架構的向量**生成與驗證全部委派 GenVal**。目前 vendored 版本為 **2026-07-09**
（commit `15c0f3d…`，約 v1.1.0.42），**不含 tr1**（ML-KEM 生成端 revision 寫死
`"FIPS203"`，無 `keyFormats`/`seed`）。tr1 由上游 **v1.1.0.43（2026-07-20）** 引入。

**步驟：**
1. 取得上游 `usnistgov/ACVP-Server` 標籤 **v1.1.0.43** 的原始碼（clone 或下載）。
2. 執行 `bash scripts/nist/copy_nist_genval.sh <path-to-ACVP-Server>` 重新 vendor
   到 `third_party/nist-acvp-server`（會是數千檔的大 diff）。
3. 更新 `third_party/nist-acvp-server/NIST_SOURCE.md`（commit / 版本 / 時間）。
4. 執行 `bash scripts/nist/build_nist_genval.sh` 重新編譯（記得 GenVal 執行時的
   `.nist-bin` dot-dir 坑：實跑要從非 dot 目錄，見 `docs/mlkem-iut-testing.md`）。
5. **回歸測試**：先用新 GenVal 重跑既有 `FIPS203` keyGen + encapDecap，確認仍
   240/240 通過，再進行後續。

**風險：** 此步會**取代目前已驗證可用的 GenVal**；v1.1.0.43 可能含其他行為變更，
須以既有 fixtures 回歸驗證。

---

## 3. tr1 資料模型（權威依據：draft-celi-acvp-ml-kem，2026-07-21）

### 3.1 Registration（能力宣告）
```json
{
  "algorithm": "ML-KEM",
  "mode": "encapDecap",
  "revision": "FIPS203-tr1",
  "parameterSets": ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"],
  "functions": ["encapsulation", "decapsulation",
                "encapsulationKeyCheck", "decapsulationKeyCheck"],
  "keyFormats": ["expanded", "seed"]
}
```
- `functions`、`keyFormats` **僅適用於 tr1**；`keyFormats` 值域 = `{"expanded","seed"}`。

### 3.2 testGroup（prompt 內）— 以真實 GenVal v1.1.0.43 樣本為準
每個 encapDecap group 都帶 `function` 與 **`keyFormat`**。`keyFormat` 的值域是
**`{"none", "seed", "expanded"}`**（注意：與 registration 的 `keyFormats`
`{"seed","expanded"}` 不同——不使用私鑰的 function 用 `"none"`）。

### 3.3 各 function 的輸入/輸出（已對照真實樣本校正）

| function | testType | group keyFormat | prompt test 欄位 | IUT 輸出 |
|----------|----------|-----------------|------------------|----------|
| encapsulation | AFT | `none` | `ek`, `m` | `c`, `k` |
| decapsulation | VAL | `expanded` | `dk`, `c` | `k` |
| decapsulation | VAL | `seed` | **`d`(32B), `z`(32B)**, `c` | `k` |
| encapsulationKeyCheck | VAL | `none` | `ek` | `testPassed` |
| decapsulationKeyCheck | VAL | `none` | **僅 `tcId`（prompt 不含 dk）** | `testPassed` |

- **seed 格式關鍵校正**：不是單一 `seed` 欄位，而是**分開的 `d`(32B) 與 `z`(32B)**；
  IUT 以 `d,z` 呼叫 `_keygen_internal` 展開出 dk 再解封裝。
- expanded 的 `dk` 尺寸沿用 `DECAPSULATION_KEY_BYTES`（1632/2400/3168）。
- ✅ **decapsulationKeyCheck 已從 GenVal v1.1.0.43 原始碼釐清（原「開放問題」）**：
  真實 sample 的 prompt **只有 `tcId`、完全不含金鑰**（dk 或 d/z 都沒有），這**不是
  sample 精簡**，而是 NIST GenVal 產生器的行為 —— 且經原始碼證實為 **NIST 端的缺陷**：
  - `TestGroupGeneratorKeyCheckVal` 建立 `DecapsulationKeyCheck` group 時
    **未設定 `KeyFormat`**（對照 decapsulation VAL 會逐一產生 seed/expanded group）。
  - `TestGroup.KeyFormat` 無初值 → 落在 `PrivateKeyFormat` enum 預設 `None`（序列化 `"none"`）。
  - `PromptProjectionContractResolver` 對 decap 這側的金鑰（`dk` / `d`+`z`）**以 keyFormat
    當條件**：Expanded 才出 `dk`、Seed 才出 `d`+`z`；`none` → 兩者皆不出。
    （對照 encapsulationKeyCheck 的 `ek` 投影**不看 keyFormat**，故 `ek` 照常出現，
    這也是為何同樣 keyFormat `none`，encap 側有 key、decap 側沒有。）

  **結論**：v1.1.0.43 的 tr1 `decapsulationKeyCheck` 向量，符規 IUT **無法**從 prompt
  算出 `testPassed`（拿不到待檢金鑰）；`testPassed` 只存在於伺服器端的 expected results。
  這是 NIST GenVal 的 bug，非本專案問題。本專案 schema 已正確容許此形狀（keyFormat
  `none` 時 dk 選用/缺省），harness 對此功能不產出 `testPassed` 屬**正確**行為。
  待 NIST 修正（讓 keyCheck group 帶 seed/expanded 並在 prompt 附金鑰）後，harness 再
  比照 decapsulation 的 seed/expanded 分支補上即可，無需改動底層庫。

- ✅ **活體確認（2026-08-03，實跑 GenVal v1.1.0.43）——缺陷其實是「雙層」的**：
  在本機 build 起 v1.1.0.43（runner + Orleans silo），用本專案 mapper 產生的 tr1 註冊
  實跑 `-g` 生成、harness 作答、再 `-n -b` 交回 NIST 驗證，證實：
  1. **產生層**：GenVal 現生成的 `decapsulationKeyCheck` group 仍是 keyFormat `none`、
     prompt 無金鑰（與上述原始碼分析一致）。
  2. **驗證層（新發現）**：NIST 自己的 `TestCaseValidatorKeyCheck.ValidateAsync`
     （tr1，line 20–28）在 `_expectedResult.TestPassed != suppliedResult.TestPassed`
     成立時，直接對 `suppliedResult.TestPassed.Value` 取值而**未做 `.HasValue` 檢查**。
     由於 IUT（正確地）未回 `testPassed`，該 nullable 為 null → 拋
     `System.InvalidOperationException: Nullable object must have a value` →
     `TaskCanceledException` → **整份提交中止、連 `validation.json` 都產不出來**。
     也就是說：這個功能不只 IUT 答不出來，**NIST 自己也驗不下去**。
  3. **其餘 3 個 function 完整迴圈通過**：註冊排除 `decapsulationKeyCheck`（其餘
     `encapsulation` / `decapsulation`(expanded+seed) / `encapsulationKeyCheck`）時，
     生成 → harness → NIST 驗證全綠：`disposition: passed`、**55/55 passed**；
     harness 的 fail 變體則正確得到 `disposition: failed`（1 failed / 54 passed）。
  ⇒ **實務建議**：在 NIST 修正前，tr1 註冊**不要勾 `decapsulationKeyCheck`**，其餘功能
  端到端完全可用。這也已由本專案 `test_mlkem_tr1.py` 的往返測試在應用層固定下來。

---

## 4. 後端變更（`backend/app/algorithms/mlkem/`）

> 核心改動觀念：**`REVISION` 由單一常數改為「多 revision」**，且 encapDecap 需
> 依 revision 決定是否處理 `keyFormats`。

| 檔案 | 變更內容 |
|------|----------|
| `constants.py` | 新增 `REVISIONS = {"FIPS203", "FIPS203-tr1"}`；新增 `KEY_FORMATS = {"expanded", "seed"}`；新增 `SEED_BYTES = 64`。保留既有常數。 |
| `descriptor.py` | 新增第二個 descriptor（`provider_id="nist-ml-kem-fips203-tr1"`, `revision="FIPS203-tr1"`），`capability_metadata` 加 `keyFormats`；或將 descriptor 擴充為可帶多 revision。 |
| `bootstrap.py`（`acvp_core`） | 註冊 tr1 descriptor/module（若採並行 descriptor）。 |
| `registration_schema.py` | 依 `revision` 分流：`FIPS203-tr1` 且 `mode=encapDecap` 時，`functions` 必填、**新增 `keyFormats` 必填**且值須 ∈ `KEY_FORMATS`；`FIPS203` 維持現況（不接受 `keyFormats`）。 |
| `validators.py` | 新增 `keyFormats` 正規化/驗證（非空、去重、值域檢查）。 |
| `capabilities.py` | 協商回應在 tr1 的 encapDecap entry 內回帶 `keyFormats`。 |
| `nist_mapper.py` | `revision` 改為依 registration 帶入（非寫死 `REVISION`）；tr1 時把 `keyFormats` 一併映射到 NIST registration。 |

**注意點：**
- `capabilities.py` / `nist_mapper.py` 目前都 `from .constants import REVISION` 寫死，
  需改成「用該筆 registration 的 revision」。
- 需決定 `FIPS203` 基礎版是否仍保留 `functions`（現況有）——建議**維持現況**以相容，
  tr1 為疊加。

---

## 5. IUT harness 變更（`IUT-tests/mlkem-native/run_test.py`）

現況 encapDecap 只處理 expanded `dk`。tr1 需加 `keyFormat` 分支：

| 情境 | harness 行為 |
|------|--------------|
| group `keyFormat == "expanded"`（或無此欄位＝FIPS203） | 沿用現行：讀 `dk` → `_decaps_internal(dk, c)` |
| group `keyFormat == "seed"`（decapsulation） | 讀 **`d`(32B) 與 `z`(32B)** → `ek,dk = ML_KEM._keygen_internal(d,z)` → `_decaps_internal(dk, c)` → `k` |
| `encapsulation` / `encapsulationKeyCheck` | 與現行相同（`ek`,`m` / `ek`） |
| `decapsulationKeyCheck` | prompt 只有 `tcId`、無金鑰（NIST v1.1.0.43 缺陷，見 3.3）；符規 IUT 無法產出 testPassed，harness 略過屬正確行為 |

- kyber-py 已有 `key_derive(seed)`（64B）與 `_keygen_internal(d,z)`，**無需改底層庫**。
- `run_test.py` 讀 group 時多讀 `keyFormat`；`_generate_test_response` 的 decapsulation
  分支依 `keyFormat` 取 `seed` 或 `dk`。
- `--expect-mode` 不受影響（mode 仍是 `encapDecap`）；可另加 `run_encapdecap_tr1.py`
  包裝或讓現行腳本自動依 prompt 內的 revision/keyFormat 判斷（建議後者）。

---

## 6. 前端（選作，`frontend/src/`）

若要能在網頁上發起 tr1 session：
- `registry.ts`：新增 `FIPS203-tr1` revision 選項與 `keyFormats`（expanded/seed）多選。
- `registration.ts`：tr1 的 encapDecap 需帶 `keyFormats`（非空）；沿用「functions 非空」規則。
- 若暫不改前端，可先用 curl 發起 tr1 registration 測試（見第 7 節）。

---

## 7. 驗證計畫

1. **回歸**：新 GenVal 重跑既有 `FIPS203` keyGen/encapDecap → 仍 240/240。
2. **tr1 expanded**：發起 `FIPS203-tr1` + `keyFormats:["expanded"]` session → 下載 prompt
   → harness → 提交 → `passed`。
3. **tr1 seed**：`keyFormats:["seed"]` → prompt 的 decapsulation group 帶 `seed` →
   harness 走 seed 分支 → 提交 → `passed`。
4. **負向**：seed/expanded 各跑一次 `--variant fail`，確認 GenVal 判 `fail`。
5. 留存四項佐證（截圖／results JSON）。

curl 發起範例（registration 片段）：
```json
{"algorithm":"ML-KEM","revision":"FIPS203-tr1","mode":"encapDecap",
 "parameterSets":["ML-KEM-512"],
 "functions":["encapsulation","decapsulation","encapsulationKeyCheck","decapsulationKeyCheck"],
 "keyFormats":["expanded","seed"]}
```

---

## 8. 風險與回滾

- **取代既有 GenVal**：升級後若既有 FIPS203 回歸失敗，回滾方式＝還原
  `third_party/nist-acvp-server` 與 `.nist-bin`（git checkout 舊版 + 重編）。
- **schema 分流錯誤**：tr1 與 FIPS203 的 registration 驗證需嚴格分流，避免把
  `keyFormats` 誤收進 FIPS203 或漏驗 tr1 必填欄位。
- **seed 展開正確性**：務必確認 `seed = d‖z`（非 z‖d）順序（kyber-py `key_derive`
  取 `d=seed[:32], z=seed[32:]`）。

---

## 9. 工作分解與相依

```
階段0 GenVal 升級(v1.1.0.43) ──┐（硬前提，最重）
                               ├─▶ 階段1 後端多-revision + keyFormats
                               ├─▶ 階段2 harness seed 分支
                               └─▶ 階段3 驗證(回歸 + tr1 expanded/seed + 負向)
階段4（選）前端 tr1 UI ── 可與 1/2 並行
```

估時（粗估）：階段0 半天～1 天（含 clone/編譯/回歸）；階段1 半天；階段2 2–3 小時；
階段3 半天；階段4（選）半天。

---

## 附：判定依據

- 上游 release：`usnistgov/ACVP-Server` **v1.1.0.43（2026-07-20）** release note 明列
  新增 `ML-KEM / encapDecap / FIPS203-tr1` 與 `keyFormats`。
- 規格：`draft-celi-acvp-ml-kem`（NIST 頁面 2026-07-21）第 5、7、8 節。
- 現況佐證：vendored GenVal `NIST_SOURCE.md` = 2026-07-09；ML-KEM 生成端
  `TestVectorSet.cs` 之 `Revision` 寫死 `"FIPS203"`、查無 `tr1`/`keyFormat`。
