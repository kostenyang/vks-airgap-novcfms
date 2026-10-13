# VKS on VDS + Foundation Load Balancer — Step by Step（m05，UI 版，2026-10-12）

> 📄 Word 版：[`VKS-VDS-FLB-UI-Step-by-Step.docx`](VKS-VDS-FLB-UI-Step-by-Step.docx)

不使用 NSX VPC，改用 **vSphere Distributed Switch（VDS）網路 + Foundation Load Balancer（FLB）** 啟用 Supervisor，再建立 VKS 叢集。不需要 Avi，也不需要 VNA / Transit Gateway。所有 vSphere 操作都在 vSphere Client UI 完成並截圖，只有驗證用 CLI。

> 同一套 m05 的 NSX VPC 版本見 [`../m05-step-by-step`](../vpc/README.md)（UI 版）和 [`../m05-airgap-step-by-step`](../vpc-airgap/README.md)（UI air-gap 版）。這份是把 VPC 版拆掉後，在同一個叢集上改用 VDS + FLB 重做。

## 成果

| 項目 | 值 |
|---|---|
| Supervisor | `vcf-m05-sv01`，**VDS** networking，Load Balancer = **Foundation Load Balancer**，control plane small ×1 |
| Supervisor API VIP | **192.168.15.64**（FLB 從 VIP 範圍配出），管理 IP 10.0.1.184 |
| FLB | `flb-vcf-m05-sv01`，One Arm、Small、1 台 VM（2 vCPU / 4 GB）；管理 10.0.1.193，virtual server 網卡 192.168.15.33 |
| VKS 叢集 | `vks-lab/vks-cl01`，v1.36.2，CP 192.168.15.37 + worker 192.168.15.38 |
| LoadBalancer | 叢集 API 192.168.15.66、測試服務 **192.168.15.67**（從管理網段可以直接存取） |
| 時間 | Supervisor 41 分鐘 → VKS 叢集 15 分鐘 |

## 和 VPC 版的差異

| 項目 | VPC 版 | VDS + FLB 版（這份） |
|---|---|---|
| Supervisor 網路 | VCF Networking with VPC | **vSphere Distributed Switch (VDS)** |
| 對外 / LB | Transit Gateway + VNA（Large）+ External IP Block | **Foundation Load Balancer**（Supervisor 精靈裡一起部署） |
| NSX 設定 | 要先做 Setup Network Connectivity | **不需要** |
| Workload 網路 | 每個 namespace 一個 VPC，subnet 由 `vks-block` 切 | 一個 VDS port group（VLAN 5）+ 固定的 IP 範圍 |
| VKS 叢集網路 | 要先建 Public SubnetSet，叢集指定 `networks` | **不用 SubnetSet**，節點直接用 namespace 的預設網路 |
| ClusterClass `networks` 變數 | 要等它出現才能建叢集 | 不存在、也不需要 |

## 規劃值

| 項目 | 值 | 說明 |
|---|---|---|
| Supervisor 管理網路 | `SDDC-DPortGroup-VM-Mgmt`，10.0.1.184-188（5 個 IP），/23，gw 10.0.0.1 | |
| Workload 網路 | port group **`vks-workload-vlan5`**（VLAN 5），**192.168.15.32-63**，/24，gw 192.168.15.254 | Supervisor CP 的 workload 網卡、VKS 節點、FLB 的 virtual server 網卡都從這段拿 IP |
| Kubernetes Services 內部網段 | 10.96.0.0/23（預設） | |
| FLB 管理網路 | 名稱 `flb-mgmt-net`，`SDDC-DPortGroup-VM-Mgmt`，**10.0.1.193-194**（要 2 個 IP） | 名稱不能和 Supervisor 管理網路相同 |
| FLB VIP 範圍 | **192.168.15.64-95** | Supervisor API、VKS 叢集 API、LoadBalancer Service 都從這裡配 |
| Storage policy | `vks-ftt0` | 見 UI 版 0-4 |
| VKr | 訂閱 `http://10.0.0.61:8888/PROD/COMP/VKR/lib.json` | 內部 depot |

> Workload 範圍（.32-.63）和 VIP 範圍（.64-.95）在同一個 /24，但不可以重疊。

## 步驟 0：準備

### 0-1 ~ 0-6 和 UI 版相同

vSphere Client 語言改 English、HA / DRS、vSAN Health 靜音、storage policy `vks-ftt0`、`SDDC-DPortGroup-VM-Mgmt` 安全性改 Accept、VLAN 5 閘道測試。做法見 UI 版的[步驟 0](../vpc/README.md#步驟-0準備)。

### 0-7 建立 workload port group（VLAN 5）

VDS `vcf-m05-cl01-vds01` → ACTIONS → **Distributed Port Group → New Distributed Port Group**：

| 精靈頁 | 設定 |
|---|---|
| Name and location | **`vks-workload-vlan5`**（全小寫，見下方說明） |
| Configure settings | VLAN type **VLAN**、VLAN ID **5**，勾 **Customize default policies configuration** |
| Security | Promiscuous mode / MAC address changes / Forged transmits 都改 **Accept**（nested 需要） |
| 其他頁 | 預設 |

![](img/01-vds-new-pg-menu.png)
![](img/02-pg-name.png)
![](img/03-pg-settings-vlan5.png)
![](img/04-pg-security-accept.png)
![](img/05-pg-ready.png)

> 🔑 Supervisor 精靈的 Workload **Network Name** 會自動帶入 port group 名稱，而這個名稱必須符合 RFC-1123（小寫英數字和 `-`）。port group 名稱若有大寫，FINISH 時會被擋，要手動把 Network Name 改成小寫。這裡直接用小寫命名就不會遇到。

## 步驟 1：啟用 Supervisor（VDS + Foundation Load Balancer）

Menu → **Supervisor Management → GET STARTED**。

![](img/10-supervisor-mgmt-home.png)

| 精靈頁 | 設定 |
|---|---|
| 1 vCenter Server and Network | **vSphere Distributed Switch (VDS)**；Load Balancer Type 選 **Foundation Load Balancer**（另兩個選項是 Avi、HAProxy） |
| 2 Supervisor location | **CLUSTER DEPLOYMENT**：`vcf-m05-sv01`、HA 關、叢集 `vcf-m05-cl01`、zone `vz-01` |
| 3 Storage | 三個都選 `vks-ftt0` |
| 4 Management Network | **Static**；`SDDC-DPortGroup-VM-Mgmt`；`10.0.1.184-10.0.1.188`；255.255.254.0；gw 10.0.0.1；DNS 10.0.0.200；search `home.lab`；NTP 10.0.1.254 |
| 5 Workload Network | **Static**；選 port group `vks-workload-vlan5`（Network Name 自動帶入）；Internal Network for Kubernetes Services 用預設 `10.96.0.0/23`；IP Address Range **`192.168.15.32-192.168.15.63`**；255.255.255.0；gw **192.168.15.254**；DNS / NTP 同上 |
| 6 Load Balancer | 見下方 |
| 7 Advanced Settings | Control Plane Size **Small** |

![](img/11-sv-1-vds-flb.png)
![](img/12-sv-2-location.png)
![](img/13-sv-3-storage.png)
![](img/14-sv-4-mgmt-network.png)
![](img/15-sv-5-workload.png)

### 第 6 頁：Load Balancer（Foundation Load Balancer）

| 欄位 | 值 |
|---|---|
| Name | `flb-vcf-m05-sv01`（預設） |
| Networks Topology | **One Arm**（Two Arm 要再多一個 port group，見 `kostenyang/vcf9.1vks` 的 same-VLAN / Two Arm 實測） |
| Size | Small |
| High Availability | 預設 **2**（Active / Passive，2 台 VM）。nested lab 改成 **1** 省資源；正式環境建議保留 2 |
| Management Network | 按 **ASSIGN** → Static、port group `SDDC-DPortGroup-VM-Mgmt`、Network Name 改 **`flb-mgmt-net`**、IP `10.0.1.193-10.0.1.194`（畫面註明要 2 個 IP）、255.255.254.0、gw 10.0.0.1、DNS / NTP |
| Virtual Server Network | 自動沿用 workload 網路 `vks-workload-vlan5`（192.168.15.32-63） |
| Virtual IP Address Range(s) | **`192.168.15.64-192.168.15.95`** |

![](img/16-flb-mgmt-network.png)
![](img/17-sv-6-flb.png)
![](img/18-sv-7-advanced.png)
![](img/19-sv-8-ready.png)

FINISH 後開始設定，約 41 分鐘（17:59 → 18:40）變成 **Running**。過程中 config_status 曾短暫變成 ERROR 再回到 CONFIGURING，屬正常。

![](img/20-sv-configuring.png)
![](img/21-sv-running.png)

✅ Supervisor API VIP = **192.168.15.64**（從 FLB 的 VIP 範圍配出）：`https://192.168.15.64` 回 200、`:6443` 回 401。

FLB 本身是一台 VM，放在 `Namespaces/vcf-m05-sv01/` 資料夾下，有兩張網卡：virtual server 網路 192.168.15.33、管理網路 10.0.1.193。

![](img/22-flb-vm-summary.png)

## 步驟 2：VKr Content Library

和 UI 版[步驟 3](../vpc/README.md#步驟-3vkr-content-library) 相同：`vkr-depot`，Subscribed，`http://10.0.0.61:8888/PROD/COMP/VKR/lib.json`，immediately，storage 選 vSAN。

![](img/30-cl-1-name.png)
![](img/31-cl-2-subscribed.png)
![](img/32-cl-3-security.png)
![](img/33-cl-4-storage.png)
![](img/34-cl-5-ready.png)
![](img/35-cl-created.png)

## 步驟 3：Namespace

**NEW NAMESPACE** → Supervisor `vcf-m05-sv01` → 名稱 `vks-lab`。VDS 模式會多一個 **Default Network** 欄位，自動帶入 `vks-workload-vlan5`。

![](img/40-ns-config.png)

在 Summary 頁：ADD STORAGE `vks-ftt0` → ADD VM CLASS（xsmall / small / medium）→ Kubernetes Service **ADD LIBRARY** → `vkr-depot`。

![](img/41-ns-add-storage.png)
![](img/42-ns-add-vmclass.png)
![](img/43-sv-k8s-service-library.png)
![](img/44-sv-add-library.png)
![](img/45-sv-library-added.png)
![](img/46-ns-summary-ready.png)

✅ KR 自動產生（[`cli/02-kr.txt`](cli/02-kr.txt)）：v1.35.6、v1.36.2 都是 READY / COMPATIBLE。

## 步驟 4：VKS 叢集（UI）

Namespace → **Resources**（LCI）→ Kubernetes → **CREATE CLUSTER** → **Custom Configuration**：

| 精靈頁 | 設定 |
|---|---|
| General Settings | `vks-cl01`、`builtin-generic-v3.7.0`、`v1.36.2---vmware.2-vkr.3`、VM Class `best-effort-medium`、Storage Class `vks-ftt0` |
| Network | **不用改**：Node Network 維持預設（使用 namespace 的預設網路），Pods `10.95.0.0/16`、Services `10.96.0.0/12` |
| Control plane | Replicas 1、Photon 5 |
| Node pools | 預設 node pool → Edit：改名 `vks-cl01-np-1`、Overrides → VM Class `best-effort-small` |

![](img/73-vks-wizard-1-custom.png)
![](img/74-vks-wizard-2-general.png)
![](img/75-vks-wizard-2-network.png)
![](img/76-vks-wizard-3-cp.png)
![](img/77-vks-nodepool-vmclass-small.png)
![](img/78-vks-nodepool-review.png)
![](img/79-vks-wizard-4-nodepools.png)
![](img/80-vks-wizard-5-review.png)

精靈產生的 YAML（[`vks-cl01.yaml`](vks-cl01.yaml)）**沒有 `networks` 變數**。VDS 模式的 ClusterClass 本來就沒有這個變數，也不需要 SubnetSet。

FINISH 後約 15 分鐘（18:50 → 19:05）變成 **Available**，節點 IP 是 192.168.15.37 / .38（來自 workload 範圍）：

![](img/81-vks-cluster-creating.png)
![](img/82-vks-cluster-available.png)
![](img/83-vks-cluster-detail.png)

## 步驟 5：驗證

登入 guest cluster，2 個節點 Ready、系統 pod 全部 Running（[`cli/03-guest-cluster.txt`](cli/03-guest-cluster.txt)）：

```bash
kubectl vsphere login --server=192.168.15.64 -u administrator@vsphere.local --insecure-skip-tls-verify \
  --tanzu-kubernetes-cluster-namespace vks-lab --tanzu-kubernetes-cluster-name vks-cl01
kubectl get nodes -o wide
```

LoadBalancer 測試（[`dns-lb.yaml`](dns-lb.yaml)，後端用叢集內建的 CoreDNS，不需要拉 image；[`cli/04-dns-lb.txt`](cli/04-dns-lb.txt)）：

```text
$ kubectl -n kube-system get svc coredns-lb-demo
NAME              TYPE           CLUSTER-IP      EXTERNAL-IP     PORT(S)
coredns-lb-demo   LoadBalancer   10.110.250.26   192.168.15.67   53:30697/TCP

$ nslookup -vc kubernetes.default.svc.cluster.local 192.168.15.67     # 從管理網段執行
Name:    kubernetes.default.svc.cluster.local
Address: 10.96.0.1
```

所有 LoadBalancer 都由 FLB 從 VIP 範圍依序配出（[`cli/05-supervisor-lb-svcs.txt`](cli/05-supervisor-lb-svcs.txt)）：

| VIP | 用途 |
|---|---|
| 192.168.15.64 | Supervisor API（443 / 6443） |
| 192.168.15.65 | mgmt-image-proxy |
| 192.168.15.66 | VKS 叢集 `vks-cl01` API（6443） |
| 192.168.15.67 | 測試服務 `coredns-lb-demo`（53/TCP） |

FLB 的設定和健康狀態：Supervisor → Configure → **Network → Load Balancer**（Health Status = Healthy；EDIT 可以調整設定）。

![](img/84-sv-configure-network-lb.png)

## 注意事項

| # | 項目 | 說明 |
|---|---|---|
| 1 | Workload Network Name 要符合 RFC-1123 | 會自動帶 port group 名稱。名稱有大寫時 FINISH 會被擋，要手動改成小寫（m02 實測過） |
| 2 | FLB 管理網路名稱 | 不能和 Supervisor 的管理網路同名，這裡用 `flb-mgmt-net` |
| 3 | FLB 管理網路要 2 個 IP | HA 設 1 時畫面仍要求兩個 IP |
| 4 | IP 範圍不可重疊 | workload（.32-.63）和 VIP（.64-.95）放在同一個 /24 沒問題，但範圍不能重疊 |
| 5 | nested 環境 | 管理和 workload 兩個 port group 都要開 Promiscuous / MAC changes / Forged transmits |
| 6 | vSAN Health | 非 green 時 spherelet 的 vLCM remediation 會被擋，主機無法加入成 Supervisor 節點（m02 實測過）→ 先做 UI 版 0-3 的靜音 |
