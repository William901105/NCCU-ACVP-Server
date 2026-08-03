# ML-KEM `FIPS203-tr1` 狀態報告（組員交接）

> 分支：`203IUT`　｜　日期：2026-08-03
> 主題：ML-KEM `FIPS203-tr1` 支援已完成，並以真實 NIST GenVal **v1.1.0.43** 端到端驗證。
> 詳細技術規格見 [`docs/mlkem-fips203-tr1-spec.md`](mlkem-fips203-tr1-spec.md)。

---

## 1. 已進 git 的東西（分支 `203IUT`）

- 後端 tr1 模組：多-revision 架構 + `keyFormats`（`seed` / `expanded` 私鑰格式）。
- IUT harness（`IUT-tests/mlkem-native/`）：支援 seed（`d`+`z` 展開）與 decapsulationKeyCheck 的優雅略過。
- tr1 測試（`backend/tests/test_mlkem_tr1.py`）＋ 官方 NIST tr1 sample fixtures。
- 規格文件（`docs/mlkem-fips203-tr1-spec.md`，含 NIST 缺陷的原始碼與活體證據）。

**驗證狀態**：後端 **241 passed**；前端 build / typecheck / vitest 全綠。

## 2. 沒有進 git 的東西（刻意，且不需要）

- **NIST ACVP-Server v1.1.0.43 原始碼（約 1.1GB）沒有 commit。** 它只是**一次性的建置
  來源**，用來在本機編出 GenVal 執行檔；tr1 的程式碼**執行期不依賴它在 repo 裡**。
  推 1.1GB 進 git 會讓 repo 歷史永久肥大、每位組員被迫多載、與現有 `third_party/`
  重複，甚至可能被 GitHub 擋，故不放。已於 `.gitignore` 排除。
- **git 上 vendored 的 GenVal 仍是 v1.1.0.42（commit `15c0f3de`，不含 tr1）。**
  也就是說：tr1 的**應用層程式碼完整**，但要讓 GenVal 實際「生成 tr1 向量」，需自行
  build v1.1.0.43（GenVal 升級屬獨立工作，見第 5 節）。

## 3. 真實 NIST GenVal v1.1.0.43 端到端結果（本機實跑，2026-08-03）

流程：GenVal `-g` 生成 → 後端 `validate_prompt` → IUT harness 作答 →
後端 `validate_response` → GenVal `-n -b` 驗證。

| 測試 | 結果 |
|------|------|
| 正向（harness 正確作答） | ✅ `disposition: passed`，**55 / 55 全過** |
| 負向（harness fail 變體，故意答錯） | ✅ `disposition: failed`（1 failed / 54 passed） |

涵蓋功能：`encapsulation`、`decapsulation`（expanded + seed）、`encapsulationKeyCheck`。

## 4. ⚠️ 重要：`decapsulationKeyCheck` 是 NIST 自己的「雙層」缺陷

在 v1.1.0.43 上，此功能**兩端都壞**，已由本機實跑活體重現：

1. **產生層**：GenVal 生成該群組時 `keyFormat = "none"`、prompt **完全不含金鑰**
   （`dk` / `d`+`z` 都沒有）→ 符規 IUT 無從計算 `testPassed`。
2. **驗證層**：NIST 的 `TestCaseValidatorKeyCheck.ValidateAsync`（tr1）對 supplied 的
   `testPassed`（nullable）**未做 `.HasValue` 檢查**就直接取 `.Value`。IUT 正確地未回
   `testPassed`（值為 null）→ NIST 拋 `Nullable object must have a value` →
   整份驗證中止、**連 `validation.json` 都產不出來**。

**⟹ 暫行對策（NIST 修正前）**：**tr1 註冊請勿勾選 `decapsulationKeyCheck`**；其餘三個
功能端到端完全可用。本專案 schema 已正確容許此形狀、harness 對它略過屬正確行為，且已
由 `test_mlkem_tr1.py` 的往返測試固定。細節見 `mlkem-fips203-tr1-spec.md` §3.3。

## 5. 如何自行重現 GenVal v1.1.0.43 端到端

前置：安裝 .NET 8 SDK。以下所有產物都放在 **repo 外**，不進 git。

1. 取得 NIST ACVP-Server **v1.1.0.43** 原始碼（例如解壓到 `~/Desktop/ACVP-Server-1.1.0.43`）。
2. 把 `_config/Directory.Build.props`、`_config/Directory.Packages.props` 複製到該原始碼根目錄。
3. `dotnet publish` 兩個專案到 repo 外目錄（例如 `~/nist-run/`）：
   - `gen-val/samples/GenValAppRunner/src/NIST.CVP.ACVTS.Generation.GenValApp.csproj`
   - `gen-val/samples/NIST.CVP.ACVTS.Orleans.ServerHost/NIST.CVP.ACVTS.Orleans.ServerHost.csproj`
   > 建議輸出到**非 dot 開頭**的目錄（避免 .NET 對 `.nist-bin` 之類 dot-dir 讀不到
   > `sharedappsettings.json` 的問題）。
4. 從 orleans-server 目錄啟動 silo：`dotnet NIST.CVP.ACVTS.Orleans.ServerHost.dll --console`
   （gateway 埠 `30000`；後端固定用 `8001`/其他埠以免和 Orleans 的埠衝突）。
5. 後端設環境變數指向新 runner：
   `ACVP_GENVAL_RUNNER_DLL=~/nist-run/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll`
6. 建 tr1 sample session（**functions 排除 `decapsulationKeyCheck`**）→ 生成 → 用
   `IUT-tests/mlkem-native/run_test.py` 作答 → 提交 → 取得驗證結果。

> 若要把 git 上的 vendored GenVal 也升級到 v1.1.0.43：那會改動 `third_party/` 底下
> 數千個被追蹤檔案（超大 diff），且 v1.1.0.43 的 decapsulationKeyCheck 本就有上述缺陷，
> 因此列為**獨立、非緊急**的後續工作。
