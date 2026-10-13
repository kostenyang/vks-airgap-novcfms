# VKS on VLAN-backed VPC — Air-gap Step by Step（m05，2026-10-11 ~ 10-12）

> 📄 Word 版：[`VKS-VLAN-backed-VPC-Airgap-UI-Step-by-Step.docx`](VKS-VLAN-backed-VPC-Airgap-UI-Step-by-Step.docx)

在**連不到網際網路**的前提下，從頭把 VKS 建起來：Supervisor、VKS 叢集，以及從內部 Harbor 部署應用。網路架構和 [`../m05-step-by-step`](../vpc/README.md)（UI 版）相同（VLAN-backed VPC + VNA），這份只整理 **air-gap 多出來的部分**：內部 registry、離線匯入的 VKr、信任內部 CA，以及怎麼證明真的沒有連外。

vSphere / NSX / Harbor 的操作全部用 UI，每一步都有截圖。只有本來就只能下指令的步驟才用 CLI：安裝 Docker / Harbor、搬 image、在叢集裡部署應用。

## 成果

| 項目 | 值 |
|---|---|
| 內部 registry | `harbor01.home.lab`（10.0.0.86），Harbor v2.15.4，自簽 CA，**主機本身也擋掉對外連線** |
| VKr 來源 | Local Content Library `vkr-local`，**從本機檔案匯入** OVF / VMDK（不靠任何 HTTP 訂閱） |
| 信任 Harbor CA | Supervisor → Configure → **Container Registries** 加一次，Supervisor Services、Pods、VKS 叢集都會套用 |
| VKS 叢集 | `vks-lab/vks-cl01`，v1.36.2，CP 192.168.15.50 + worker 192.168.15.51 |
| 測試應用 | `harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine` ×2，LoadBalancer VIP **192.168.15.33** |
| 斷網證明 | 同一個 busybox：`docker.io` 拉不到（ImagePullBackOff），Harbor 拉得到 |
| 時間 | Harbor 約 30 分鐘 → TGW + VNA 16 分鐘 → Supervisor 50 分鐘 → VKS 叢集 15 分鐘 |

## Air-gap 的範圍

| 網段 | 對外 | 說明 |
|---|---|---|
| VLAN 5（192.168.15.0/24：Supervisor 工作網路、VKS 節點、LB VIP） | ❌ 本來就出不去 | 上游閘道沒有替這段做 NAT（[`cli/00-vlan5-no-internet.txt`](cli/00-vlan5-no-internet.txt)） |
| Harbor VM | ❌ 用 iptables 擋 | 只放行私有網段（[`scripts/airgap-egress-block.sh`](scripts/airgap-egress-block.sh)） |
| m05 管理網段（vCenter、ESXi、NSX、SDDC Manager） | ⚠️ 這個 lab 沒有擋 | 管理網段直接走上游閘道，這次沒有改上游設備；所有內容都只從內部來源取得。**正式 air-gap 環境這段也要斷** |

> 這個 lab 沒有「另一台 staging 機」：檔案都是在可上網的工作機下載，再搬進 air-gap 的機器。正式環境把下面「要帶進去的東西」放到外部 staging 機準備，再用媒體或單向傳輸搬進去即可。

## 要帶進 air-gap 的東西

| 檔案 | 大小 | 來源 / 準備方式 |
|---|---|---|
| `docker-29.9.0.tgz` | 86 MB | download.docker.com（靜態二進位，不需要 apt） |
| `docker-compose-linux-x86_64`（v5.6.0） | 31 MB | GitHub release，附 `.sha256` |
| `harbor-online-installer-v2.15.4.tgz` | 12 KB | GitHub release（只有安裝腳本） |
| `harbor-images-v2.15.4.tar.gz` | 761 MB | 在 staging 機 `docker pull goharbor/*:v2.15.4` 12 個 image → `docker save`（等同 offline installer 裡的 image 包） |
| VKr `photon-5-amd64-v1.36.2---vmware.2-vkr.3`（.ovf / -disk1.vmdk / .mf / .cert） | 3.3 GB | 內部 depot；用 `.mf` 的 SHA256 校驗 |
| 應用 image tar（nginx-unprivileged、busybox） | 66 MB | [`scripts/pull-image-tar.py`](scripts/pull-image-tar.py)：staging 機不需要裝 docker，直接用 registry API 存成 `docker load` 格式 |

> 🔴 這次 GitHub release 的下載速度只有 30-50 KB/s，713 MB 的 Harbor offline installer 要好幾個小時。改成「online installer 腳本 + 自己 `docker save` 的 image 包」，結果相同。
> 🔑 Harbor 2.15 的 image 清單已經沒有 `redis-photon`，改成 **`valkey-photon`**。正確清單可以從 `goharbor/prepare` 的 `templates/docker_compose/docker-compose.yml.jinja` 取得。

## 步驟 0：準備

和 UI 版的[步驟 0](../vpc/README.md#步驟-0準備) 相同：vSphere Client 語言改 English、HA / DRS、vSAN Health 靜音、storage policy `vks-ftt0`、port group 安全性、VLAN 5 閘道測試、DNS。

另外加一筆 DNS：`harbor01.home.lab` → 10.0.0.86（A + PTR）。

## 步驟 1：Harbor（內部 registry）

### 1-1 安裝（CLI）

Harbor VM：Ubuntu 20.04，4 vCPU / 8 GB，系統碟 100 GB，另加一顆 100 GB 資料碟掛在 `/data`。

```bash
# Docker（靜態二進位 + systemd unit + compose plugin）
./install-docker-static.sh /root/staging/docker-29.9.0.tgz /root/staging/docker-compose-linux-x86_64

# 自簽 CA + Harbor 憑證（SAN：harbor01.home.lab、harbor01、10.0.0.86）
./make-harbor-certs.sh harbor01.home.lab 10.0.0.86 /data/cert

# 主機和容器只能連私有網段（systemd 開機自動套用）
./airgap-egress-block.sh

# 載入 Harbor image → 安裝（不加 --with-trivy：Trivy 要上網更新漏洞資料庫）
sha256sum -c harbor-images-v2.15.4.tar.gz.sha256
docker load -i harbor-images-v2.15.4.tar.gz
tar -xzf harbor-online-installer-v2.15.4.tgz -C /opt
cp /opt/harbor/harbor.yml.tmpl /opt/harbor/harbor.yml   # 改 hostname / https 憑證 / data_volume / admin 密碼
cd /opt/harbor && ./install.sh
```

[`harbor.yml`](harbor.yml.example) 只改這幾項：`hostname: harbor01.home.lab`、`https.certificate` / `private_key` 指到 `/data/cert`、`data_volume: /data/harbor`、`harbor_admin_password`。

✅ `docker compose ps`：9 個容器都是 healthy；`curl https://harbor01.home.lab/api/v2.0/ping` 回 200。主機上 `curl https://registry-1.docker.io` 會逾時（已經斷網）。

### 1-2 建專案（UI）

登入 `https://harbor01.home.lab`（admin）→ **NEW PROJECT**：名稱 `vks-apps`、Access Level 勾 **Public**（VKS 節點不帶帳密就能拉）。

![](img/10-harbor-login.png)
![](img/11-harbor-projects.png)
![](img/12-harbor-new-project.png)
![](img/13-harbor-project-created.png)

### 1-3 推應用 image（CLI）

```bash
# staging 機（可上網、不需要 docker）
python pull-image-tar.py nginxinc/nginx-unprivileged:1.30.4-alpine nginx-unprivileged-1.30.4-alpine.tar
python pull-image-tar.py busybox:1.37.0 busybox-1.37.0.tar
sha256sum *.tar > SHA256SUMS

# 搬進 air-gap 後，在 Harbor 主機上
sha256sum -c SHA256SUMS
docker load -i nginx-unprivileged-1.30.4-alpine.tar
docker login harbor01.home.lab -u admin
docker tag nginxinc/nginx-unprivileged:1.30.4-alpine harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine
docker push harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine
```

（完整輸出：[`cli/01-harbor-push.txt`](cli/01-harbor-push.txt)。正式環境請改用 Robot Account。）

![](img/14-harbor-repos.png)
![](img/15-harbor-nginx-artifact.png)

## 步驟 2：Transit Gateway + VNA（UI）

和 UI 版[步驟 1](../vpc/README.md#步驟-1transit-gateway--vnasetup-network-connectivity) 相同：Distributed VLAN Connection → VLAN 5 / `192.168.15.254/24` → External IP Block `vks-block`（192.168.15.0/24，排除 .240-.254）→ VNA `vks-vna` **Large**，節點 10.0.1.183。

![](img/20-transit-gateways.png)
![](img/21-setup-p1-distributed-vlan.png)
![](img/22-setup-prereq.png)
![](img/23-ipblock-vks-block.png)
![](img/24-setup-p2-external.png)
![](img/25-vna-add-node.png)
![](img/26-vna-cluster-large.png)
![](img/27-setup-review.png)
![](img/28-setup-deploying.png)

約 16 分鐘後 VNA 變成 `NODE_READY`，Transit Gateway 狀態為 **Success**。這次同時在上傳 VKr，所以比 UI 版慢一點。

![](img/29-tgw-success.png)

## 步驟 3：VKr — Local Content Library + 匯入本機檔案（UI）

Air-gap 不能訂閱外部的 `lib.json`，改建**本地** library，再從本機檔案匯入 VKr。

**Content Libraries → CREATE**：名稱 `vkr-local` → **Local content library**（不開 publishing）→ 不套 security policy → storage 選 vSAN。

![](img/40-cl-1-name.png)
![](img/41-cl-2-local.png)
![](img/42-cl-3-security.png)
![](img/43-cl-4-storage.png)
![](img/44-cl-5-ready.png)

進 `vkr-local` → **ACTIONS → Import item** → Source 選 **Local file** → **UPLOAD FILES**，一次選 4 個檔案（`.ovf`、`-disk1.vmdk`、`.mf`、`.cert`；有 `.mf` 和 `.cert` 時會做校驗）→ Item name 填 `ob-25650988-photon-5-amd64-v1.36.2---vmware.2-vkr.3` → IMPORT。

![](img/45-cl-actions-import.png)
![](img/46-cl-import-local-files.png)

上傳約 3 分鐘，完成後 library 裡有 1 個 OVF template（11.87 GB）：

![](img/47-cl-vkr-imported.png)

## 步驟 4：啟用 Supervisor（UI）

和 UI 版[步驟 2](../vpc/README.md#步驟-2啟用-supervisor) 相同：VCF Networking with VPC → CLUSTER DEPLOYMENT（`vcf-m05-sv01`、zone `vz-01`）→ storage policy 三個都選 `vks-ftt0` → Management Static 10.0.1.184-188 → Workload 自動帶出 `vks-block` → CP Small。

![](img/30-supervisor-mgmt-home.png)
![](img/31-sv-1-network.png)
![](img/32-sv-2-location.png)
![](img/33-sv-3-storage.png)
![](img/34-sv-4-mgmt-network.png)
![](img/35-sv-5-workload.png)
![](img/36-sv-6-advanced.png)
![](img/37-sv-7-ready.png)
![](img/38-sv-configuring.png)

約 50 分鐘（22:52 → 23:42）變成 **Running**，API VIP 192.168.15.5。中間 kubernetes_status 會在 ERROR → WARNING → READY 之間跳動，屬正常。

![](img/39-sv-running.png)

> **Supervisor 本身不需要額外的 content library**：9.1.1 會用 vCenter 內建的 Supervisor 映像。這和 9.1.0 時要手動準備 `supervisor-local` library 的經驗不同。

## 步驟 5：讓 Supervisor 和 VKS 信任 Harbor（UI）

**Supervisor → Configure → Container Registries → ADD REGISTRY**：

| 欄位 | 值 |
|---|---|
| Registry Name | `harbor01` |
| Registry host URL | `harbor01.home.lab` |
| TLS Certificate | 貼上 Harbor 的 **CA 憑證**（`/data/cert/ca.crt`） |
| Username / Password | 空白（`vks-apps` 是 public project） |
| Use this registry as default | 不勾 |

![](img/60-sv-container-registries.png)
![](img/61-sv-add-registry.png)
![](img/62-sv-registry-added.png)

🔑 頁面上寫明：*"Settings applied here will be honored for Supervisor Services, Pods, and VKS clusters."*
Supervisor 會建立一個 `ClusterRegistryConfig`（[`cli/03-cluster-registry-config.txt`](cli/03-cluster-registry-config.txt)），VKS 節點會自動信任這個 CA。**不需要**在叢集 YAML 裡另外設定 `trust` 變數或建立 `*-user-trusted-ca-secret`。

## 步驟 6：Namespace（UI）

**NEW NAMESPACE** `vks-lab` → ADD STORAGE `vks-ftt0` → ADD VM CLASS（xsmall / small / medium）→ Kubernetes Service **ADD LIBRARY** → 選 **`vkr-local`**。

![](img/50-ns-config.png)
![](img/51-ns-add-storage.png)
![](img/52-ns-add-vmclass.png)
![](img/53-sv-k8s-service-library.png)
![](img/54-sv-add-library-local.png)
![](img/55-sv-library-added.png)
![](img/56-ns-summary-ready.png)

✅ 從本機匯入的 VKr 一樣會**自動產生 KubernetesRelease**（[`cli/02-kr.txt`](cli/02-kr.txt)）：

```text
NAME                       VERSION                  READY   COMPATIBLE
v1.36.2---vmware.2-vkr.3   v1.36.2+vmware.2-vkr.3   True    True
```

## 步驟 7：Public SubnetSet（UI）

Resources（LCI）→ Network → **SubnetSets → NEW SUBNETSET**：`public` / **Public** / 16 IPs / DHCP None。

![](img/70-lci-network-service.png)
![](img/71-lci-new-subnetset.png)
![](img/72-lci-subnetset-created.png)

## 步驟 8：VKS 叢集（UI，Custom Configuration）

和 UI 版[步驟 6](../vpc/README.md#步驟-6建立-vks-叢集uicustom-configuration) 相同：Custom Configuration → `vks-cl01` / v3.7.0 / v1.36.2 / medium / `vks-ftt0` → Node Network 選 **public (Subnet Set)** → CP ×1 Photon → node pool 改名 `vks-cl01-np-1`，Overrides 改 VM class 為 `best-effort-small`。

![](img/73-vks-wizard-1-custom.png)
![](img/74-vks-wizard-2-general.png)
![](img/75-vks-wizard-2-network.png)
![](img/76-vks-wizard-3-cp.png)
![](img/77-vks-nodepool-vmclass-small.png)
![](img/78-vks-nodepool-review.png)
![](img/79-vks-wizard-4-nodepools.png)
![](img/80-vks-wizard-5-review.png)

精靈產生的 YAML（[`vks-cl01.yaml`](vks-cl01.yaml)）和 UI 版完全相同，**沒有任何和 registry 有關的設定**。

> ⚠️ 和 UI 版遇到的一樣：Supervisor 剛 Running 時，ClusterClass 還沒有 `networks` 變數，送出會被擋。這次等到 Running 後 15 分鐘（23:57）變數出現，00:02 才送出。

約 15 分鐘（00:03 → 00:18）變成 **Available**：

![](img/81-vks-cluster-creating.png)
![](img/82-vks-cluster-available.png)
![](img/83-vks-cluster-detail.png)

## 步驟 9：驗證（CLI）

從 Harbor 部署 nginx（[`nginx-harbor.yaml`](nginx-harbor.yaml)，PSA restricted 要求的 securityContext 都已加上）：

```text
$ kubectl -n demo get pods
nginx-5658995685-m49m6   1/1   Running
nginx-5658995685-v2lzf   1/1   Running
Successfully pulled image "harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine"

$ kubectl -n demo get svc nginx-lb
nginx-lb   LoadBalancer   10.106.7.157   192.168.15.33   80:32719/TCP

$ curl -s http://192.168.15.33/ | grep title      # 從管理網段執行
<title>Welcome to nginx!</title>
```

沒有出現 `x509: certificate signed by unknown authority`，表示 Harbor CA 已經透過 Container Registries 下發到節點（[`cli/05-nginx-from-harbor.txt`](cli/05-nginx-from-harbor.txt)）。

**反向測試**（[`pull-test.yaml`](pull-test.yaml)，[`cli/06-pull-test.txt`](cli/06-pull-test.txt)）：同一個 busybox，分別從 Docker Hub 和 Harbor 拉：

```text
NAME             READY   STATUS
from-dockerhub   0/1     ImagePullBackOff    ← Head "https://registry-1.docker.io/v2/..." 逾時
from-harbor      0/1     Completed           ← hello-from-harbor，並且 wget 到 nginx-lb
```

Harbor UI 上也看得到 pull 次數增加：

![](img/90-harbor-pulls.png)

## 遇到的問題

| # | 症狀 | 原因 / 處理 |
|---|---|---|
| 1 | GitHub release 下載只有 30-50 KB/s | 不下載 713 MB 的 offline installer，改成「online installer 腳本 + 自己 `docker save` 的 image 包」 |
| 2 | `goharbor/redis-photon:v2.15.4: not found` | Harbor 2.15 改用 `valkey-photon` |
| 3 | 用 Playwright（CDP）上傳 VKr 時出現 *Cannot transfer files larger than 50Mb* | 自動化工具的限制，手動操作不會遇到。改用 CDP `DOM.setFileInputFiles`，讓瀏覽器直接讀本機路徑 |
| 4 | 建叢集被擋：`variables[networks] ... variable is not defined` | Supervisor 剛 Running 時 ClusterClass 還沒有 `networks` 變數，等 15-20 分鐘 |
| 5 | Supervisor 這次要 50 分鐘 | nested lab 的 CPU 被 VKr 上傳、VNA 部署同時搶用；沒有做任何修改，等它完成 |

## 和 UI 版的差異

| 項目 | UI 版（`m05-step-by-step`） | Air-gap 版（這份） |
|---|---|---|
| VKr | Subscribed library，訂閱內部 depot 的 `lib.json` | **Local library**，UI 從本機檔案匯入 |
| 應用 image | 無（nginx 拉 Docker Hub 失敗） | 內部 Harbor `harbor01.home.lab/vks-apps` |
| 信任內部 CA | 不需要 | Supervisor → **Container Registries**（自動套到 VKS） |
| 證明斷網 | — | Docker Hub ImagePullBackOff vs Harbor 成功 |
| 叢集 YAML | 相同 | 相同（沒有 registry 相關設定） |
