# ML-KEM（FIPS 203）手動 IUT 驗證

本文件說明目前 `strict` 分支的 Docker 操作方式。不要切換到舊的 `203IUT`
分支，也不需要在主機分別安裝或啟動 Node.js、FastAPI、PostgreSQL 與 Orleans。

目前產品支援：

- ML-KEM `keyGen` / `FIPS203`
- ML-KEM `encapDecap` / `FIPS203`
- `ML-KEM-512`、`ML-KEM-768`、`ML-KEM-1024`
- `encapsulation`、`decapsulation`、`encapsulationKeyCheck`、
  `decapsulationKeyCheck`

目前**不支援** ML-KEM `FIPS203-tr1`。2026-08-14 發布的官方 ML-KEM
draft 已另外列出該 test revision；它的 `keyFormats`、group `keyFormat` 與
seed/expanded decapsulation schema 不可直接套用到現有 `FIPS203` 實作。

## 1. 啟動系統

先依 [`../DEPLOYMENT.md`](../DEPLOYMENT.md) 建立 `.env` 與 PostgreSQL
password secret，然後：

```bash
./scripts/docker/start.sh
./scripts/docker/smoke-test.sh
```

三個 services 應為 `healthy`，瀏覽器開啟
<http://127.0.0.1:8080>。若 Docker daemon 尚未啟動，必須先啟動 Docker
Engine 或 Docker Desktop。

## 2. keyGen 正向驗證

1. 點選 **Get New Access Token**。
2. 選擇 FIPS 203 / ML-KEM、`keyGen` 與一個或多個 parameter set。
3. 建立 test session，等待狀態成為 `vectorReady`。
4. 在 vector workspace 下載 prompt JSON。
5. 在 repository root 執行 IUT harness：

   ```bash
   python3 IUT-tests/mlkem-native/run_test.py \
     --prompt /path/to/downloaded-prompt.json \
     --response-dir /tmp/mlkem-keygen-response \
     --variant pass \
     --expect-mode keyGen
   ```

6. 在網頁上傳 `/tmp/mlkem-keygen-response/response_pass_keyGen.json`。
7. 點選 **Submit response**，再點 **Refresh results**。
8. vector disposition 與 session result 應顯示 `passed`。

不要把下載的 prompt 當成 response 上傳；prompt 是題目，IUT 產生的 response
才是答案。

## 3. encapDecap 正向驗證

建立新的 session，選擇 `encapDecap`、parameter set，並至少選一個 function。
完整驗收建議四個 functions 全選。下載 prompt 後執行：

```bash
python3 IUT-tests/mlkem-native/run_test.py \
  --prompt /path/to/downloaded-prompt.json \
  --response-dir /tmp/mlkem-encapdecap-response \
  --variant pass \
  --expect-mode encapDecap
```

上傳 `response_pass_encapDecap.json`、提交並刷新結果。單一
`ML-KEM-512` 加四個 functions 的參考輸出為 4 groups、55 test cases；實際數量
仍以 NIST GenVal prompt 為準。

## 4. 負向驗證

負向測試請建立另一個新 session，避免已提交的 vector set 狀態干擾結果：

```bash
python3 IUT-tests/mlkem-native/run_test.py \
  --prompt /path/to/downloaded-prompt.json \
  --response-dir /tmp/mlkem-negative-response \
  --variant fail \
  --expect-mode keyGen
```

測試 `encapDecap` 時把 mode 改成 `encapDecap`。上傳對應的
`response_fail_<mode>.json` 後，HTTP submission 可成功，但 NIST disposition
應為 `fail`。這表示 response JSON 格式有效，而密碼學答案被正確拒絕。

## 5. 自動完整驗收

以下腳本從公開 frontend URL 執行 ML-DSA 與 ML-KEM 共五種情境；每一種都驗證
`passed → fail → passed`：

```bash
python3 scripts/docker/full-stack-test.py \
  --output /tmp/acvp-docker-e2e.json
```

這是驗收工具，不是 production container 的一部分。

## 6. 故障排除與停止

```bash
docker compose logs --tail 200 frontend acvp-engine postgres
./scripts/docker/status.sh
```

- `NIST_GENVAL_EXECUTION_ERROR`：先查看 `acvp-engine` 日誌與 health 狀態。
- `ACCESS_TOKEN_REQUIRED` 或 HTTP 401：重新取得 access token。
- `invalid_key_format`：確認目前 session 是 `FIPS203`，不要上傳
  `FIPS203-tr1` 的 registration、prompt 或 response。
- `decapsulationKeyCheck` 必須輸出 JSON boolean `testPassed`，不是 key bytes。

測試完成後：

```bash
./scripts/docker/stop.sh
```

這會移除 containers 與 network，但保留 PostgreSQL 與 GenVal artifact volumes。
