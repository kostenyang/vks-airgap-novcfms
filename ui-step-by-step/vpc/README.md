# VKS on VLAN-backed VPC — Step by Step（m05，全部用 vSphere Client UI，2026-10-11）

> 📄 Word 版：[`VKS-VLAN-backed-VPC-UI-Step-by-Step.docx`](VKS-VLAN-backed-VPC-UI-Step-by-Step.docx)

在 VCF 9.1.1 的 **VLAN-backed VPC（TEP-less）** 環境啟用 Supervisor，建立 VKS 叢集。流程依照 [`notchcc/vcf-lab` 的 `vks/README.md`](https://github.com/notchcc/vcf-lab/blob/main/vks/README.md)（William Lam 的 VLAN-backed VPC 做法），在另一套 nested lab（m05）從頭做一次。**每一步都用 vSphere Client UI 操作並截圖**，包含 SubnetSet 和 VKS 叢集（Namespace → Resources，LCI 外掛）。CLI 只用在驗證。

> 這套 m05 是用 VCF Installer 的「Deploy a new VCF Instance」部署的第二個 instance。Day-0 選了 **VLAN backed VPC**，spec 裡會帶 `nsxtSpec.overlayVtepSpec.vtepType: NO_IP`，主機沒有 TEP。部署過程見 [`vcf-installer/new-instance-step-by-step`](https://github.com/notchcc/vcf-lab/tree/docs/m05-new-instance-vks-step-by-step/vcf-installer/new-instance-step-by-step)。
>
> Air-gap 版（內部 Harbor + 離線匯入 VKr）見 [`../m05-airgap-step-by-step`](../vpc-airgap/README.md)。
>
> 2026-10-10 第一次做的時候，Namespace 的 **Resources** 分頁（LCI 外掛）一直是空白，SubnetSet 和 VKS 叢集只好改用 kubectl。後來查出原因是 **vSphere Client 的語言是繁體中文**（見步驟 0-1），所以把 Supervisor 停用、VNA / Transit Gateway 拆掉，全部用 UI 重做一次，就是這份文件。

## 成果

| 項目 | 值 |
|---|---|
| Supervisor | `vcf-m05-sv01`，**VCF Networking with VPC**，單一 control plane（small），zone `vz-01` |
| Supervisor API VIP | **192.168.15.5**（由 VNA 從 External IP Block 分配），管理 IP 10.0.1.184 |
| VKS 叢集 | `vks-lab/vks-cl01`，v1.36.2+vmware.2，Photon，CP `best-effort-medium` ×1 + worker `best-effort-small` ×1 |
| 節點 IP | CP 192.168.15.50、worker 192.168.15.51（SubnetSet `public`）；K8s API VIP 192.168.15.32 |
| LoadBalancer Service | VIP 192.168.15.33（從管理網段可以直接存取） |
| 總時間 | 準備約 30 分鐘 → Transit Gateway + VNA 約 8 分鐘 → Supervisor 30 分鐘 → Namespace / SubnetSet 數分鐘 → VKS 叢集約 16 分鐘 |

## 規劃值

| 項目 | 值 | 說明 |
|---|---|---|
| 對外 VLAN | **5**，閘道 `192.168.15.254/24` | 閘道是 lab 的 RouterOS。步驟 0-6 先確認主機到得了閘道 |
| External IP Block | `vks-block` = **192.168.15.0/24**，排除 `.240-.254` | **必須和閘道網段一致**，不要切小塊（見notchcc `vks/README.md`） |
| VNA | cluster `vks-vna`，**Large（8 vCPU / 32 GB）**，1 個節點 `vcf-m05-vna01a` 10.0.1.183 | Small 規格放不下 Supervisor 的第二個 VPC LB（見notchcc `vks/README.md`） |
| Supervisor | `vcf-m05-sv01`，CLUSTER DEPLOYMENT，zone `vz-01`，control plane small ×1 | |
| Supervisor 管理 IP | 10.0.1.184-188（5 個連續 IP） | Port group `SDDC-DPortGroup-VM-Mgmt`、/23、gw 10.0.0.1 |
| Storage policy | `vks-ftt0`（FTT=0 + Force provisioning） | nested vSAN 上用 FTT=0 比較穩 |
| VKr 來源 | 訂閱 `http://10.0.0.61:8888/PROD/COMP/VKR/lib.json` | 內部 offline depot 上的 v1.36.2 / v1.35.6（Photon） |
| Namespace | `vks-lab` | |
| SubnetSet | `public`（Access mode Public，16 個 IP） | VLAN-backed VPC 只有 Public subnet |
| VKS 叢集 | `vks-cl01`，v1.36.2，1 CP + 1 worker | |

## 步驟 0：準備

### 0-1 vSphere Client 語言改成 English（🔴 一定要做）

右上角使用者 → **My Preferences → Language → Specify a language → English** → SAVE，然後重新整理頁面。

![](img/00-pref-language-english.png)

> 🔴 **Namespace → Resources 分頁（LCI 外掛 `com.vmware.cci-ns` 9.1.2.0）在繁體中文介面下是整片空白。**
> 外掛用 vSphere Client 的語系（`htmlClientSdk.app.getClientLocale()` = `zh-TW`）去載入翻譯檔，但外掛只附 en / es / fr / ja 四種語系，載不到就整個畫面都不渲染。
> 只改瀏覽器語言（Chrome `--lang`）不夠，因為語言偏好是 *Browser Default* 時，是以登入當下的語系為準。直接在 My Preferences 指定 English 最確實。
> 空白時常見的 `config.json` 404、`cerebro/point-of-presence` 404 都是煙霧彈，和這個問題無關。

### 0-2 叢集 HA / DRS

叢集必須是 vSphere HA 開啟、DRS **Fully Automated**（VCF 部署好就是這樣）：Cluster → Configure → Services。

![](img/01-cluster-drs.png)
![](img/02-cluster-ha.png)

### 0-3 vSAN Health 靜音（nested 才需要）

nested 環境的 vSAN 會有幾個永遠不會綠的項目。William Lam 建議啟用 Supervisor 前先處理；另一套 lab 曾經因為 vSAN health 擋住 spherelet 安裝。

Cluster → Monitor → **vSAN → vSAN Health**：Unhealthy 有 *NVMe device is VMware certified*、*Performance service status*，Info 有 *vSAN Support Insight*。每一項按 **SILENCE ALERT → YES**：

![](img/03-cluster-issues.png)
![](img/04-vsan-health.png)
![](img/05-vsan-health-findings.png)
![](img/06-vsan-silence-dialog.png)

三項都移到 **SILENCED (3)**，Unhealthy 變成 0：

![](img/07-vsan-silenced.png)

### 0-4 VM Storage Policy `vks-ftt0`

Menu → **Policies and Profiles → VM Storage Policies → CREATE**：

| 精靈頁 | 設定 |
|---|---|
| Name and description | `vks-ftt0`（K8s Compliant Name 會自動產生同名） |
| Policy structure | 勾 **Enable rules for "vSAN" storage** |
| vSAN → Availability | 🔴 先把最上面的 **vSAN ESA Auto-RAID (9.1 onwards)** 關掉（這套是 OSA，預設是開的，開著就沒有 FTT 選項）→ Site disaster tolerance *None - standard cluster*、Failures to tolerate **No data redundancy** |
| vSAN → Advanced Policy Rules | **Force provisioning** 打開 |
| Storage compatibility | `vcf-m05-cl01-ds-vsan01` 相容 |

![](img/09-policy-list.png)
![](img/10-policy-name.png)
![](img/11-policy-structure.png)
![](img/12-policy-vsan-availability.png)
![](img/13-policy-vsan-advanced-force.png)
![](img/14-policy-storage-compat.png)
![](img/15-policy-review.png)
![](img/16-policy-created.png)

### 0-5 Port group 安全性（nested 限定）

Supervisor control plane VM 接在 `SDDC-DPortGroup-VM-Mgmt`。nested 環境要把這個 port group 的 **Promiscuous mode / MAC address changes / Forged transmits** 都改成 **Accept**，否則 CP VM 會卡在 CONFIGURING。

Networking → `SDDC-DPortGroup-VM-Mgmt` → Configure → Policies → **EDIT... → Security**：

![](img/17-pg-policies-before.png)
![](img/18-pg-security-accept.png)
![](img/19-pg-policies-after.png)

> 改完如果主機的 VDS 狀態變成 *out of sync*（這次 esx03 回 `DvsApplyOperationFault` / `vob.fssvec.Ioctl.file.failed`，寫 vSAN 上的 `.dvsData` 暫時失敗），對該主機做 **Rectify**，或把設定再套一次就會恢復。

### 0-6 確認 VLAN 5 到得了閘道

先用一個臨時 port group + vmk 確認主機在 VLAN 5 上可以 ping 到閘道，測完就刪掉。

1. VDS `vcf-m05-cl01-vds01` → ACTIONS → **Distributed Port Group → New Distributed Port Group**：名稱 `tmp-vlan5-test`、VLAN type **VLAN**、VLAN ID **5**

   ![](img/20-vds-new-pg-menu.png)
   ![](img/21-tmp-pg-vlan5.png)

2. 主機 `vcf-m05-esx03` → Configure → Networking → VMkernel adapters → **ADD NETWORKING** → VMkernel Network Adapter → 選 `tmp-vlan5-test` → 服務都不勾 → Static `192.168.15.240` / `255.255.255.0`

   ![](img/22-vmk-target-tmp-pg.png)
   ![](img/23-vmk-ipv4.png)
   ![](img/24-vmk-ready.png)
   ![](img/25-vmk-added.png)

3. 從新的 vmk ping 閘道（[`cli/00-vlan5-ping.txt`](cli/00-vlan5-ping.txt)）：

   ```text
   esxcli network diag ping -H 192.168.15.254 -I vmk3 -c 3
   Transmitted : 3   Received : 3   PacketLost : 0
   ```

4. 通了就把 vmk3 移除（VMkernel adapters → ⋮ → **Remove**），再刪掉 `tmp-vlan5-test`（ACTIONS → **Delete**）

   ![](img/26-vmk-remove.png)

### 0-7 DNS

VNA 節點的 A / PTR 記錄：`vcf-m05-vna01a.home.lab` ↔ 10.0.1.183（[`cli/00-dns-vna.txt`](cli/00-dns-vna.txt)）。

## 步驟 1：Transit Gateway + VNA（Setup Network Connectivity）

Networking → **Virtual Private Clouds** → Summary → **GO TO NETWORK CONNECTIVITY**（也就是 vCenter → Networks → **Transit Gateways**）。這個畫面是 NSX 外掛，Default Transit Gateway 的 Connection 一開始是 None。

![](img/27-vpc-get-started.png)
![](img/28-transit-gateways.png)

按 **SETUP NETWORK CONNECTIVITY**。

**頁 1：Transit Gateway Connectivity**。VLAN-backed 模式只有 **Distributed VLAN Connection** 可以選。

![](img/29-setup-p1.png)

NEXT 會跳出 **Networking Prerequisites**：勾 **Select All** → CONTINUE。其中「外部閘道要關閉 ICMP redirect」是實體閘道的設定，這次 lab 沒有改 RouterOS 也能正常運作，正式環境請照做。

![](img/30-setup-prereq.png)

**頁 2：External Network Connectivity**。VLAN ID 填 `5`；Gateway CIDR 填**閘道 IP** `192.168.15.254/24`（不是網段，輸入後要按 **Enter** 變成標籤）。

![](img/31-setup-p2-vlan.png)

VPC External IP Blocks 一開始是空的，要從右邊的 ⋮ → **Create New** 建立：

![](img/32-setup-ipblock-menu.png)

名稱 `vks-block`，Visibility 固定 External，CIDR 填 `192.168.15.0/24`，Excluded IP Ranges 填 `192.168.15.240-192.168.15.254`（兩個欄位都要按 Enter）→ SAVE：

![](img/33-ipblock-filled.png)
![](img/34-setup-p2-done.png)

**頁 3：VPC Services（VNA cluster）**。Cluster Name `vks-vna`，**Node Form Factor 選 Large**（預設 Medium；選項有 Small 2/4、Medium 4/8、Large 8/32、Extra Large 16/64，**建好後就不能改**）：

![](img/35-vna-cluster-large.png)

按 **ADD** 加一個節點：FQDN `vcf-m05-vna01a.home.lab`、vSphere Cluster `vcf-m05-cl01`、Data Store vSAN；IP Assignment **Static**，Management CIDR `10.0.1.183/23`、Default Gateway `10.0.0.1`（兩個都要按 Enter），**Port Group 改成 `SDDC-DPortGroup-VM-Mgmt`**（預設會帶 esx-mgmt）→ APPLY：

![](img/36a-vna-add-node-top.png)
![](img/36-vna-add-node.png)
![](img/37-vna-node-added.png)

> 密碼會自動產生，之後到 SDDC Manager 查。

**頁 4：Review and Deploy** → DEPLOY：

![](img/38-setup-review.png)
![](img/39-setup-deploying.png)

約 7 分鐘後 VNA 變成 `NODE_READY`，Transit Gateway 狀態為 **Success**，Connection = Distributed VLAN / `Distributed-vlan-connection-5`：

![](img/40-tgw-success.png)

✅ NSX API 檢查（[`cli/01-nsx-check.txt`](cli/01-nsx-check.txt)）：

```text
Distributed-vlan-connection-5 vlan 5 ['192.168.15.254/24']
Default VPC Connectivity Profile: external_ip_blocks ['/infra/ip-blocks/vks-block']
  service_gateway {'enable': True, 'edge_cluster_paths': [.../virtual-network-appliance-clusters/vks-vna]}
vks-block ['192.168.15.0/24'] EXTERNAL excluded 192.168.15.240-192.168.15.254
```

> 9.1.1 的 VNA transport node 類型是 `VirtualNetworkAppliance`，用 `/api/v1/transport-nodes?node_types=EdgeNode` 查不到。

## 步驟 2：啟用 Supervisor

Menu → **Supervisor Management → GET STARTED**（URL `/ui/app/workload-platform`）。

![](img/41-supervisor-mgmt-home.png)

| 精靈頁 | 設定 |
|---|---|
| 1 vCenter Server and Network | **VCF Networking with VPC (recommended)** |
| 2 Supervisor location | **CLUSTER DEPLOYMENT** 分頁；Supervisor name `vcf-m05-sv01`、control plane HA 關閉、選叢集 `vcf-m05-cl01`、vSphere Zone name `vz-01` |
| 3 Storage | Control Plane / Ephemeral Disks / Image Cache 三個都選 `vks-ftt0` |
| 4 Management Network | **Static**；Network 選 `SDDC-DPortGroup-VM-Mgmt`（要點右邊 ▼ 才會列出選項）；**IP Addresses 填範圍** `10.0.1.184-10.0.1.188`；Subnet Mask `255.255.254.0`、Gateway `10.0.0.1`、DNS `10.0.0.200`、Search domain `home.lab`、NTP `10.0.1.254` |
| 5 Workload Network | 自動帶出 NSX Project *Default*、VPC Connectivity Profile *default*、External IP Blocks `vks-block`；Service CIDR 用預設 `172.29.0.0/16`；補填 DNS / NTP |
| 6 Advanced Settings | Control Plane Size **Small**（4 vCPU / 16 GB）；API Server DNS Name 不填 |

![](img/42-sv-1-network.png)
![](img/43-sv-2-location.png)
![](img/44-sv-3-storage.png)
![](img/45-sv-4-mgmt-network.png)
![](img/46-sv-5-workload.png)
![](img/47-sv-6-advanced.png)
![](img/48-sv-7-ready.png)

> 如果這個叢集以前啟用過 Supervisor，停用後 vSphere Zone（`vz-01`）**不會被刪掉**，第 2 頁 CLUSTER DEPLOYMENT 就沒辦法再用同一個名字。先移除 zone 和叢集的關聯再刪 zone：
> `POST /api/vcenter/consumption-domains/zones/cluster/vz-01/associations?action=remove`（body `["domain-c9"]`）→ `DELETE /api/vcenter/consumption-domains/zones/vz-01`

FINISH 後開始設定：

![](img/49-sv-configuring.png)

約 30 分鐘後（19:34 → 20:04）變成 **Running**。Supervisor API VIP = **192.168.15.5**：

![](img/58-sv-running.png)

```text
config_status=RUNNING  kubernetes_status=READY
api_server_cluster_endpoint=192.168.15.5   api_server_management_endpoint=10.0.1.184
```

✅ 從管理網段 10.0.0.200 測試：`https://192.168.15.5` 回 200、`:6443` 回 401（尚未登入，正常）。

> 第一次（10-10）做的時候，中途出現過一次 ERROR（CP small 的 CPU 被外層主機餓到，kube-apiserver 重啟），等了 15 分鐘自己恢復。這次沒有出現。
> Supervisor CP VM 是受保護的 agent VM，**不能手動 vMotion**（`Resource.ColdMigrate` 被拒）。

## 步驟 3：VKr Content Library

Supervisor 設定的同時就可以做。Menu → **Content Libraries → CREATE**：

| 精靈頁 | 設定 |
|---|---|
| Name and location | `vkr-depot` |
| Configure content library | **Subscribed content library**，URL `http://10.0.0.61:8888/PROD/COMP/VKR/lib.json`，Download content：**immediately** |
| Apply security policy | 不勾 |
| Add storage | `vcf-m05-cl01-ds-vsan01` |

![](img/50-cl-list.png)
![](img/51-cl-1-name.png)
![](img/52-cl-2-subscribed.png)
![](img/53-cl-3-security-policy.png)
![](img/54-cl-4-storage.png)
![](img/55-cl-5-ready.png)
![](img/56-cl-created.png)

約 8 分鐘下載完兩個 VKr（v1.36.2 11.81 GB、v1.35.6 7.86 GB）：

![](img/57-cl-vkr-synced.png)

## 步驟 4：建立 vSphere Namespace

**Supervisor Management → Namespaces → NEW NAMESPACE**：選 Supervisor `vcf-m05-sv01` → 名稱 `vks-lab` → Zone `vz-01` → FINISH。

![](img/59-ns-1-location.png)
![](img/60-ns-2-config.png)
![](img/61-ns-3-zones.png)
![](img/62-ns-4-review.png)
![](img/63-ns-summary.png)

在 Namespace 的 Summary 頁依序設定：

1. **Storage → ADD STORAGE** → 勾 `vks-ftt0`

   ![](img/64-ns-add-storage.png)

2. **VM Service → ADD VM CLASS** → `best-effort-xsmall` / `best-effort-small` / `best-effort-medium`

   ![](img/65-ns-add-vmclass.png)
   ![](img/66-ns-vmclass-added.png)

3. **Kubernetes Service → ADD LIBRARY**：會跳到 **Supervisor → Configure → General → Kubernetes Service**，按 **ADD** → 勾 `vkr-depot` → ADD

   ![](img/67-sv-k8s-service-library.png)
   ![](img/68-sv-add-library.png)
   ![](img/69-sv-library-added.png)

完成後 Namespace 顯示 1 個 storage policy、3 個 VM class、Kubernetes Service 有 1 個 content library：

![](img/70-ns-summary-ready.png)

✅ **KubernetesRelease 幾秒內自動產生**（[`cli/02-kr.txt`](cli/02-kr.txt)）：

```text
$ kubectl get kr
NAME                       VERSION                  READY   COMPATIBLE
v1.35.6---vmware.2-vkr.3   v1.35.6+vmware.2-vkr.3   True    True
v1.36.2---vmware.2-vkr.3   v1.36.2+vmware.2-vkr.3   True    True
```

## 步驟 5：Public SubnetSet（UI）

> **VKS 3.7（含）以前預設使用 Private VPC Subnet**，而 VLAN-backed VPC 沒有 private subnet，也不支援 SNAT，所以要先建一個 Public 的 SubnetSet，等一下讓 VKS 叢集指定使用。

Namespace `vks-lab` → **Resources** 分頁（LCI）。語言是 English 時會看到六張卡片：

![](img/71-ns-resources.png)

**Network → GO TO SERVICE** → **SubnetSets** 分頁 → **NEW SUBNETSET**：

![](img/72-lci-network-service.png)
![](img/73-lci-subnetsets-empty.png)

| 欄位 | 值 |
|---|---|
| Name | `public` |
| Access Mode | **Public**（選項：Private - VPC / Private - TGW / Public） |
| Size | 16 IPs（/28），用完會自動再建一個 subnet |
| DHCP | None（預設的 Static IP Allocation） |

![](img/74-lci-new-subnetset.png)

CREATE 後狀態 **Success**：

![](img/75-lci-subnetset-created.png)

> 這時候 `NETWORKADDRESSES` 還是空的，第一台 VM 接上時才會真正從 `vks-block` 切出 /28（[`cli/03-subnetset.txt`](cli/03-subnetset.txt)）。等效的 YAML 見 [`subnetset-public.yaml`](subnetset-public.yaml)。

## 步驟 6：建立 VKS 叢集（UI，Custom Configuration）

Resources → **Kubernetes → CREATE CLUSTER**。

![](img/76-lci-resources-before-cluster.png)

| 精靈頁 | 設定 |
|---|---|
| 1 Configuration Type | **Custom Configuration**（Default Configuration 會用自動產生的 private 網路，VLAN-backed VPC 不能用） |
| 2 General Settings | Cluster Name `vks-cl01`；Cluster Class `builtin-generic-v3.7.0`；Kubernetes Release `v1.36.2---vmware.2-vkr.3`；VM Class `best-effort-medium`；Storage Class `vks-ftt0` |
| 2 → Network → Node Network | 展開 **Primary &#124; eth0** → **Use custom primary network** → Network 選 **`public (Subnet Set)`** |
| 2 → Network → Pod Network | 預設 Pods `10.95.0.0/16`、Services `10.96.0.0/12`（**不能和 `vks-block` 192.168.15.0/24 重疊**）；CNI 不選＝Antrea |
| 3 Control plane | Replicas 1、OS Image Photon 5 |
| 4 Node pools | 預設的 node pool → ⋮ **Edit**：名稱改 `vks-cl01-np-1`、打開 **Overrides** → VM Class 改 `best-effort-small`（Node Network 會沿用 `public`） |
| 5 Review and Confirm | 右邊是產生的 YAML → FINISH |

![](img/77-vks-wizard-1-custom.png)
![](img/78-vks-wizard-2-general.png)
![](img/79-vks-wizard-2-network.png)
![](img/80-vks-wizard-2-podnet.png)
![](img/81-vks-wizard-3-cp.png)
![](img/82-vks-nodepool-edit.png)
![](img/83-vks-nodepool-vmclass-small.png)
![](img/84-vks-nodepool-review.png)
![](img/85-vks-wizard-4-nodepools.png)
![](img/86-vks-wizard-5-review.png)

精靈產生的 YAML（[`vks-cl01.yaml`](vks-cl01.yaml)）重點：`topology.variables` 裡的 `networks.interfaces.primary.network` 指到 `SubnetSet public`，worker 用 `variables.overrides` 改 VM class。

> 🔴 **Supervisor 剛 Running 就按 FINISH，會被 webhook 擋下來**：
> `spec.topology.variables[networks]: Invalid value: ... variable is not defined`
>
> ![](img/87-vks-finish-error-networks.png)
>
> `builtin-generic-v3.7.0` 的變數是 VKS runtime extension 動態提供的（`kubectl get clusterclass builtin-generic-v3.7.0 -n vmware-system-vks-public -o jsonpath='{.status.variables[*].name}'`）。這次 ClusterClass 在 runtime extension 起來之前就算好了變數，清單裡**少了 `networks`**；ClusterClass 帶有保留 label，不能手動改它來觸發重算。
> **處理：等 CAPI 定期重新 reconcile（預設 10 分鐘），`networks` 出現後在同一個精靈頁再按一次 FINISH 就成功了**（20:17 被擋 → 20:22 變數出現 → 20:22 送出成功）。保險起見，Supervisor Running 後等 20 分鐘再建叢集。

送出後列表顯示 *Not Available*，約 16 分鐘（20:22 → 20:38）變成 **Available**：

![](img/88-vks-cluster-creating.png)
![](img/89-vks-cluster-available.png)

點進叢集可以看到 Node Network = `Primary | eth0`（public）、Pods CIDR、Cluster health status，也可以直接 **DOWNLOAD KUBECONFIG FILE**：

![](img/90-vks-cluster-detail.png)

vCenter → Networks → **VPC Subnets**：`vks-lab` 的 VPC 多了一個 `public-…` subnet，上面有 2 台 VM（VKS 節點）：

![](img/91-vpc-subnets.png)
![](img/92-vpcs.png)

## 步驟 7：驗證

Supervisor 端（[`cli/05-supervisor-view.txt`](cli/05-supervisor-view.txt)）：

```text
cluster.cluster.x-k8s.io/vks-cl01   builtin-generic-v3.7.0   True ... Provisioned   v1.36.2+vmware.2
vks-cl01-pzgwg-7s79m                       PoweredOn   best-effort-medium   192.168.15.50
vks-cl01-vks-cl01-np-1-wk4lj-q2dr6-xv2sg   PoweredOn   best-effort-small    192.168.15.51
```

登入 guest cluster（[`cli/04-guest-cluster.txt`](cli/04-guest-cluster.txt)）：

```bash
kubectl vsphere login --server=192.168.15.5 -u administrator@vsphere.local --insecure-skip-tls-verify \
  --tanzu-kubernetes-cluster-namespace vks-lab --tanzu-kubernetes-cluster-name vks-cl01
kubectl config use-context vks-cl01
kubectl get nodes -o wide        # 2 個節點 Ready，Photon，containerd 2.3.2+vmware.3-fips
kubectl get pods -A              # antrea / coredns / csi / cloud-provider / kapp-controller 全部 Running
```

LoadBalancer 測試（[`dns-lb.yaml`](dns-lb.yaml)，後端用叢集內建的 CoreDNS，不需要拉 image；[`cli/06-dns-lb.txt`](cli/06-dns-lb.txt)）：

```text
$ kubectl -n kube-system get svc coredns-lb-demo
NAME              TYPE           CLUSTER-IP       EXTERNAL-IP     PORT(S)
coredns-lb-demo   LoadBalancer   10.109.137.171   192.168.15.33   53:30827/TCP

$ nslookup -vc kubernetes.default.svc.cluster.local 192.168.15.33     # 從管理網段 10.0.0.200 執行
Name:    kubernetes.default.svc.cluster.local
Address: 10.96.0.1
```

在 LCI 的 Network Service → **Services** 也看得到兩個 LB：叢集 API `192.168.15.32:6443` 和剛建的 `192.168.15.33:53`：

![](img/94-lci-network-services.png)

✅ 整條路徑都通：VNA 從 `vks-block` 分配 LB VIP，從管理網段可以直接存取 VKS 叢集內的服務。

> 🔴 用 nginx 測試會遇到兩個問題（10-10 第一次實測）：
> 1. **Pod Security Admission 預設是 `restricted`**，root 容器會被擋（`allowPrivilegeEscalation != false`）→ 要改用 `nginxinc/nginx-unprivileged`，並加上完整的 securityContext。
> 2. **ImagePullBackOff**：VKS 節點在 VLAN-backed VPC 上，沒有 SNAT，lab 的上游也沒有替 192.168.15.0/24 做 NAT，所以連不到 Docker Hub → 一般工作負載需要私有 registry（見 [`harbor-depot-plan.md`](https://github.com/notchcc/vcf-lab/blob/main/vks/harbor-depot-plan.md)）。

## 拆除重做時要注意（從已經有 Supervisor 的環境重來）

這次是把 10-10 做好的整套拆掉再用 UI 重做，順序和遇到的狀況：

| 順序 | 動作 | 備註 |
|---|---|---|
| 1 | guest cluster 裡的 LoadBalancer Service 先刪 | 避免 LB 殘留 |
| 2 | 刪 VKS 叢集 → 刪 Namespace | |
| 3 | Supervisor → DEACTIVATE | 約 12 分鐘；過程中 kubernetes_status 會跳 WARNING / ERROR，屬正常 |
| 4 | NSX：Default VPC Connectivity Profile 拿掉 External IP Block、關掉 service gateway → 刪 TGW attachment → 刪 Distributed VLAN Connection → 刪 IP block → 刪 VNA cluster | VNA VM 和 `vna-seg-…` port group 會一起消失。用 API PATCH profile 時 body 一定要帶 `transit_gateway_path`，否則 400 |
| 5 | **vSphere Zone 不會自動刪** | 要先移除 zone 和叢集的關聯再刪 zone，否則 CLUSTER DEPLOYMENT 不能重用同一個 zone 名稱 |
| 6 | 舊的 storage policy 刪不掉 | 停用 Supervisor 後 PBM 仍回報 *still associated with 2 entities*（CNS volume、VM Compliance 都查不到）→ 改名留著，新建 `vks-ftt0` |

## 和 notchcc/vcf-lab `vks/README.md`（單台主機 Consolidated）的差異

| 項目 | notchcc `vks/README.md` | m05（這份） |
|---|---|---|
| 環境 | 單台 ESX，Consolidated | 3 台 nested ESX，第二個 VCF instance |
| Day-0 | JSON spec `vtepType: NO_IP` | Installer 精靈 Plan → Network Options → **VLAN backed VPC**（會自動帶 `NO_IP`） |
| VNA | Small 失敗 → 改 Large | 一開始就用 Large |
| VKr | govc 匯入 local library | **訂閱** depot 上的 `lib.json`；Supervisor → Kubernetes Service 加 library 後 **KR 自動產生** |
| VKS 版本 | 3.7.0 → 推 3.7.2 | 內建的 3.7.0 + 明確指定 `networks` → public SubnetSet |
| 建立 SubnetSet / 叢集 | UI | UI（**vSphere Client 語言要用 English**，否則 LCI 空白） |
| 叢集網段 | 預設即可 | 預設 Pods `10.95.0.0/16` 即可；不要用 192.168.0.0/16（會和 `vks-block` 重疊） |
