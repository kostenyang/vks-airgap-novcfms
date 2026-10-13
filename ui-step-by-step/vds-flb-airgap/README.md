# VKS on VDS + Foundation Load Balancer — Air-gap Step by Step（m05，UI air-gap 版，2026-10-12）

> 📄 Word 版：[`VKS-VDS-FLB-Airgap-UI-Step-by-Step.docx`](VKS-VDS-FLB-Airgap-UI-Step-by-Step.docx)

在**連不到網際網路**的前提下，用 **VDS 網路 + Foundation Load Balancer（FLB）** 啟用 Supervisor 並建立 VKS 叢集，應用 image 從內部 Harbor 拉取。

vSphere 的操作全部用 UI 並截圖，只有驗證用 CLI。這份是兩份文件的組合：

- 網路和 Supervisor 的做法同 [`../m05-flb-step-by-step`](../vds-flb/README.md)（FLB UI 版）
- air-gap 的做法（內部 Harbor、從本機匯入 VKr、信任內部 CA）同 [`../m05-airgap-step-by-step`](../vpc-airgap/README.md)（VPC 的 UI air-gap 版）

## 成果

| 項目 | 值 |
|---|---|
| Supervisor | `vcf-m05-sv01`，VDS + **Foundation Load Balancer**，API VIP **192.168.15.64** |
| 內部 registry | `harbor01.home.lab`（10.0.0.86），Harbor v2.15.4，自簽 CA，主機本身也擋掉對外連線 |
| VKr 來源 | Local Content Library `vkr-local`，從本機檔案匯入 |
| 信任 Harbor CA | Supervisor → Configure → **Container Registries** |
| VKS 叢集 | `vks-lab/vks-cl01`，v1.36.2，CP 192.168.15.37 + worker 192.168.15.38 |
| 測試應用 | `harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine` ×2，LoadBalancer VIP **192.168.15.67**（FLB 配發） |
| 斷網證明 | 同一個 busybox：`docker.io` 拉不到（ImagePullBackOff），Harbor 拉得到 |
| 時間 | VKr 匯入 5 分鐘 → Supervisor 35 分鐘 → VKS 叢集 10 分鐘 |

## Air-gap 的範圍

和 VPC 的 air-gap 版相同：VLAN 5（Supervisor workload、VKS 節點、FLB VIP）本來就連不到網際網路，Harbor VM 用 iptables 擋掉對外連線；m05 管理網段這個 lab 沒有擋，但所有內容都只從內部來源取得。正式 air-gap 環境請連管理網段一起斷網。

## 步驟 0：準備

| 項目 | 做法 |
|---|---|
| vSphere Client 語言 English、HA / DRS、vSAN Health 靜音、storage policy `vks-ftt0`、管理 port group 安全性、VLAN 5 閘道測試 | UI 版的[步驟 0](../vpc/README.md#步驟-0準備) |
| workload port group `vks-workload-vlan5`（VLAN 5，安全性三項 Accept） | FLB UI 版的 [0-7](../vds-flb/README.md#0-7-建立-workload-port-groupvlan-5) |
| Harbor（安裝、建立 public project `vks-apps`、推 image） | VPC air-gap 版的[步驟 1](../vpc-airgap/README.md#步驟-1harbor內部-registry) |

## 步驟 1：VKr — Local Content Library + 匯入本機檔案（UI）

**Content Libraries → CREATE**：`vkr-local` → **Local content library** → 不套 security policy → vSAN。

![](img/30-cl-1-name.png)
![](img/31-cl-2-local.png)
![](img/32-cl-3-security.png)
![](img/33-cl-4-storage.png)
![](img/34-cl-5-ready.png)

`vkr-local` → **ACTIONS → Import item** → **Local file** → 一次選 `.ovf`、`-disk1.vmdk`、`.mf`、`.cert` 4 個檔案 → Item name `ob-25650988-photon-5-amd64-v1.36.2---vmware.2-vkr.3` → IMPORT。上傳約 5 分鐘。

![](img/35-cl-actions-import.png)
![](img/36-cl-import-local-files.png)
![](img/37-cl-vkr-imported.png)

## 步驟 2：啟用 Supervisor（VDS + Foundation Load Balancer，UI）

設定和 FLB UI 版的[步驟 1](../vds-flb/README.md#步驟-1啟用-supervisorvds--foundation-load-balancer) 完全相同。air-gap 對 Supervisor 精靈**沒有任何影響**：9.1.1 會用 vCenter 內建的 Supervisor 映像，FLB 的映像也一樣內建。

| 精靈頁 | 設定 |
|---|---|
| 1 | VDS；Load Balancer Type = **Foundation Load Balancer** |
| 2 | CLUSTER DEPLOYMENT：`vcf-m05-sv01`、`vcf-m05-cl01`、zone `vz-01` |
| 3 | storage policy 都選 `vks-ftt0` |
| 4 Management | Static、`SDDC-DPortGroup-VM-Mgmt`、10.0.1.184-188 |
| 5 Workload | Static、`vks-workload-vlan5`、192.168.15.32-63、gw 192.168.15.254 |
| 6 Load Balancer | `flb-vcf-m05-sv01`、One Arm、Small、HA 1；Management Network ASSIGN → `flb-mgmt-net` 10.0.1.193-194；VIP 192.168.15.64-95 |
| 7 | Control Plane Small |

![](img/10-supervisor-mgmt-home.png)
![](img/11-sv-1-vds-flb.png)
![](img/12-sv-2-location.png)
![](img/13-sv-3-storage.png)
![](img/14-sv-4-mgmt-network.png)
![](img/15-sv-5-workload.png)
![](img/16-flb-mgmt-network.png)
![](img/17-sv-6-flb.png)
![](img/18-sv-7-advanced.png)
![](img/19-sv-8-ready.png)
![](img/20-sv-configuring.png)

約 35 分鐘（19:32 → 20:07）變成 **Running**，API VIP 192.168.15.64。

![](img/21-sv-running.png)

## 步驟 3：讓 Supervisor 和 VKS 信任 Harbor（UI）

**Supervisor → Configure → Container Registries → ADD REGISTRY**：Registry Name `harbor01`、Registry host URL `harbor01.home.lab`、TLS Certificate 貼 Harbor 的 **CA 憑證**、帳密留空、不勾 default。

![](img/60-sv-container-registries.png)
![](img/61-sv-add-registry.png)
![](img/62-sv-registry-added.png)

Supervisor 會建立 `ClusterRegistryConfig`（[`cli/03-cluster-registry-config.txt`](cli/03-cluster-registry-config.txt)），VKS 節點會自動信任這個 CA。VDS + FLB 模式和 VPC 模式一樣有效。

## 步驟 4：Namespace（UI）

**NEW NAMESPACE** `vks-lab`（Default Network 自動帶 `vks-workload-vlan5`）→ ADD STORAGE `vks-ftt0` → ADD VM CLASS（xsmall / small / medium）→ Kubernetes Service **ADD LIBRARY** → **`vkr-local`**。

![](img/40-ns-config.png)
![](img/41-ns-add-storage.png)
![](img/42-ns-add-vmclass.png)
![](img/43-sv-k8s-service-library.png)
![](img/44-sv-add-library-local.png)
![](img/45-sv-library-added.png)
![](img/46-ns-summary-ready.png)

✅ KR 自動產生（[`cli/02-kr.txt`](cli/02-kr.txt)）：`v1.36.2---vmware.2-vkr.3` READY / COMPATIBLE。

## 步驟 5：VKS 叢集（UI）

Resources（LCI）→ Kubernetes → **CREATE CLUSTER** → **Custom Configuration**。設定和 FLB UI 版相同：`vks-cl01` / v3.7.0 / v1.36.2 / medium / `vks-ftt0`，Node Network 不用改，node pool 改名 `vks-cl01-np-1` 並 override 成 `best-effort-small`。產生的 YAML 見 [`vks-cl01.yaml`](vks-cl01.yaml)，沒有 `networks` 變數，也沒有任何 registry 設定。

![](img/73-vks-wizard-1-custom.png)
![](img/74-vks-wizard-2-general.png)
![](img/75-vks-wizard-2-network.png)
![](img/76-vks-wizard-3-cp.png)
![](img/77-vks-nodepool-vmclass-small.png)
![](img/78-vks-nodepool-review.png)
![](img/79-vks-wizard-4-nodepools.png)
![](img/80-vks-wizard-5-review.png)

約 10 分鐘（20:18 → 20:28）變成 **Available**：

![](img/81-vks-cluster-creating.png)
![](img/82-vks-cluster-available.png)
![](img/83-vks-cluster-detail.png)

## 步驟 6：驗證（CLI）

從 Harbor 部署 nginx（[`nginx-harbor.yaml`](nginx-harbor.yaml)；[`cli/05-nginx-from-harbor.txt`](cli/05-nginx-from-harbor.txt)）：

```text
$ kubectl -n demo get pods
nginx-5658995685-4kvgs   1/1   Running
nginx-5658995685-6xlfj   1/1   Running
Successfully pulled image "harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine"

$ kubectl -n demo get svc nginx-lb
nginx-lb   LoadBalancer   10.96.116.16   192.168.15.67   80:32082/TCP

$ curl -s http://192.168.15.67/ | grep title      # 從管理網段執行
<title>Welcome to nginx!</title>
```

LoadBalancer VIP 由 FLB 從 192.168.15.64-95 依序配出（[`cli/07-supervisor-lb-svcs.txt`](cli/07-supervisor-lb-svcs.txt)）：.64 Supervisor API、.65 mgmt-image-proxy、.66 叢集 API、.67 `nginx-lb`。

**反向測試**（[`pull-test.yaml`](pull-test.yaml)；[`cli/06-pull-test.txt`](cli/06-pull-test.txt)）：

```text
NAME             READY   STATUS
from-dockerhub   0/1     ImagePullBackOff    ← Head "https://registry-1.docker.io/v2/..." 逾時
from-harbor      0/1     Completed           ← hello-from-harbor，並且 wget 到 nginx-lb
```

Harbor UI 上兩個 repository 的 Pulls 都從 1 增加到 2（第 1 次是 VPC air-gap 版，第 2 次是這次）：

![](img/90-harbor-pulls.png)

## 四份文件的比較

| | VPC UI 版 | VPC UI air-gap 版 | FLB UI 版 | FLB UI air-gap 版（這份） |
|---|---|---|---|---|
| 網路 / LB | NSX VPC + VNA | NSX VPC + VNA | VDS + FLB | VDS + FLB |
| 叢集網路 | SubnetSet `public` | SubnetSet `public` | namespace 預設網路 | namespace 預設網路 |
| VKr | 訂閱內部 depot | Local library 匯入 | 訂閱內部 depot | Local library 匯入 |
| 應用 image | —（CoreDNS LB 測試） | Harbor | —（CoreDNS LB 測試） | Harbor |
| 內部 CA | — | Container Registries | — | Container Registries |
| Supervisor 時間 | 30 分 | 50 分 | 41 分 | 35 分 |
