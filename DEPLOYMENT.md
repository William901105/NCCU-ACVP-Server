# NCCU ACVP Server：單機 Docker 部署

本部署包使用三個服務：

- `frontend`：React 靜態檔與 Nginx 反向代理。
- `acvp-engine`：FastAPI、NIST GenVal Runner 與 Orleans ServerHost。
- `postgres`：PostgreSQL 16。

只有 frontend 連接埠會發布到主機。PostgreSQL、FastAPI、Orleans gateway、
silo 與 dashboard 都只存在於 Compose 內部網路。

## 主機需求

- Linux x86-64；目前交付版不保證 ARM64 或 Windows containers。
- Docker Engine 與 Docker Compose v2。
- 建議至少 4 個邏輯 CPU；NIST 設定的 `MaxConcurrentWork` 為 3。
- 首次建置需要存取 Debian、Microsoft Container Registry、Docker Hub、
  PyPI、npm 與 NuGet。離線環境應使用預先匯出的 images。

執行三個 production services 的主機不需要另行安裝 Python、Node.js、.NET 或
PostgreSQL。選用的 repository 驗收腳本需要主機具備 Python 3.10 以上；完整
ML-DSA 驗收另需可用的獨立 ML-DSA IUT library。

## 一次性設定

先確認 Docker daemon 可用：

```bash
docker info
```

以下每一行都是要在 repository root 的 **terminal** 執行的 shell 指令，不能貼進
`postgres_password.txt` 編輯器：

```bash
cp .env.example .env
install -d -m 700 secrets
install -m 600 /dev/null secrets/postgres_password.txt
read -rsp 'PostgreSQL password: ' ACVP_DB_PASSWORD
printf '%s' "${ACVP_DB_PASSWORD}" > secrets/postgres_password.txt
unset ACVP_DB_PASSWORD
chmod 0444 secrets/postgres_password.txt
```

`secrets/postgres_password.txt` 的內容只能是密碼本身，不應包含 `printf`、
`unset` 或 `chmod` 等指令。可在不顯示密碼的情況下檢查：

```bash
test -s secrets/postgres_password.txt
stat -c 'mode=%a owner=%U:%G bytes=%s' secrets/postgres_password.txt
```

Compose 的本機 file secret 是 bind mount，因此 engine 的非 root UID 必須能讀取
檔案本身；secret file 使用 `0444`，但其父目錄保持 `0700`，其他主機使用者無法
穿越目錄存取內容。不要放寬 `secrets/` 目錄權限。

PostgreSQL 第一次初始化後，單獨修改 secret file 不會自動更改既有 database
role 密碼。正式環境需用 `ALTER ROLE` 安全輪替並同步更新 secret；若是可丟棄的
全新測試環境，才可在確認備份後移除 volumes 再重新初始化。

如需讓其他內網電腦連線，在 `.env` 將 `ACVP_BIND_ADDRESS` 從
`127.0.0.1` 改為伺服器的指定內網 IP。不要在沒有防火牆或 TLS 的情況下使用
`0.0.0.0` 對不可信網路開放。

## 建置與啟動

```bash
./scripts/docker/build.sh
./scripts/docker/start.sh
```

預設網址：<http://127.0.0.1:8080>

狀態與日誌：

```bash
./scripts/docker/status.sh
docker compose logs --tail 200 frontend acvp-engine postgres
```

基本路由、token 與演算法 discovery 檢查：

```bash
./scripts/docker/smoke-test.sh
```


## 停止與重新啟動

```bash
./scripts/docker/stop.sh
./scripts/docker/start.sh
```

`docker compose down` 會移除 containers 與 network，但保留 PostgreSQL 和
GenVal artifact volumes。不要在一般操作中執行 `docker compose down -v`；`-v`
會刪除兩個持久 volume。

## 資料與備份

持久資料分為：

- `postgres-data`：session、vector set、response、report、token 與狀態資料。
- `genval-artifacts`：registration、prompt、expected results、
  `internalProjection`、response、validation 與診斷輸出。

兩者必須成對備份。備份腳本會短暫停止 frontend 與 engine，建立一致的
PostgreSQL dump 和 artifact archive，完成後重新啟動服務：

```bash
./scripts/docker/backup.sh /srv/nccu-acvp/backups
```

每次升級 image 前先備份。PostgreSQL major version 升級不可直接重用舊版 data
directory；必須使用 `pg_dump`/restore 或正式的 `pg_upgrade` 流程。

## 資料庫管理

```bash
docker compose exec postgres sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

PostgreSQL 5432 不會發布到主機。若需要圖形化管理工具，優先透過受控的 SSH
tunnel 或暫時的 loopback-only override，不要永久向內網公開 5432。

## 安全邊界

`POST /acvp/v1/accessTokens` 會公開簽發短效 bearer token，但目前沒有使用者、
角色或 tenant ownership。這個版本只適合單一組織的可信任內網。若內網並非
完全可信，應在 frontend 前加入 TLS 與額外的存取控制。

## 離線交付

在有網路的建置機建立 images 後：

```bash
docker save \
  nccu-acvp-frontend:0.1.0 \
  nccu-acvp-engine:0.1.0 \
  postgres:16.14-bookworm \
  -o nccu-acvp-images-0.1.0.tar
sha256sum nccu-acvp-images-0.1.0.tar > nccu-acvp-images-0.1.0.tar.sha256
```

廠商主機使用 `docker load` 載入，然後執行 `docker compose up -d --no-build`。
交付檔應同時包含 `compose.yaml`、`.env.example`、本文件、Git commit、NIST
source commit 與 checksum。
