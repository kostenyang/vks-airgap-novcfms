# VCF 9.1.1 + Air-gap + VPC（VNA）+ NFS 獨立 VLAN — UI step by step（m06，2026-10-13）

> 📄 Word 版：[`VCF-VPC-Airgap-NFS-VLAN-Step-by-Step.docx`](VCF-VPC-Airgap-NFS-VLAN-Step-by-Step.docx)

在 **VCF 9.1.1 管理網域（不部署 VCF Management Services）** 上，用 **VLAN-backed VPC + VNA** 啟用 Supervisor、建立 VKS 叢集，image 全部從**外部 Harbor** 取得（air-gap），PersistentVolume 放在 **NAS（NFS）**，而且 **NFS 流量走獨立的 VLAN 7，不經過 VNA**。

把上一輪的 VKS 環境（Supervisor、VNA、Transit Gateway 連線、content library、NFS 設定）全部拆掉後，從頭再做一次，每一步都用 vSphere Client UI 截圖。

| 重點 | 做法 |
|---|---|
| 不部署 VCFMS | VCF Installer bring-up 跑完 NSX 就中止（見 [`ui-step-by-step/vpc-airgap-novcfms`](../ui-step-by-step/vpc-airgap-novcfms/README.md) 步驟 1-3） |
| VPC + VNA | Transit Gateway → Distributed VLAN Connection（VLAN 6）+ VNA cluster |
| Air-gap | VKr 從本機檔案匯入 Local Content Library；Supervisor **Container Registries** 下發外部 Harbor 的 CA；VLAN 6 / VLAN 7 都沒有 NAT |
| **NFS 不經過 VNA** | **ESXi 用 vmk3（VLAN 7）掛 NFS datastore + Vmknic binding**；VKS 的 PV 是這個 datastore 上的 VMDK。資料路徑是 VM → ESXi → vmk3 → NAS，**完全不進 NSX / VPC** |

## 架構

![](img/000-architecture.png)

（圖的原始檔：[`img/diagram/architecture.html`](img/diagram/architecture.html)）

| 流量 | 路徑 | 進 NSX / VPC？ | 經過 VNA？ |
|---|---|---|---|
| Pod 對外、拉 Harbor image | 節點 eth0 → VPC → Transit Gateway → VLAN 6 | ✅ | 未量測（不是本文重點） |
| LoadBalancer VIP | VLAN 6 → VNA（LB）→ VPC → 節點 | ✅ | ✅（9-4 對照組實測） |
| **PV 讀寫（NFS）** | 節點的虛擬磁碟 → ESXi → **vmk3** → VLAN 7 → NAS | ❌ | ❌（9-4 實測） |
| Supervisor / VNA 管理 | 管理網段 | ❌ | ❌ |

### 為什麼 NFS 不會經過 VNA

1. VKS 節點根本不掛 NFS。PV 是 NFS datastore 上的一顆 VMDK，節點只看到一顆虛擬磁碟（`/dev/sdX`）；讀寫由 **ESXi** 轉成 NFS。
2. ESXi 用 **vmk3**（`nas-vlan7` port group，VLAN 7）和 NAS 在同一個 L2 網段，不經過閘道，更不經過 NSX。
3. 掛 datastore 時勾 **Vmknic binding = vmk3**，NFS 一定從 vmk3 出去，不會因為路由表改走 vmk0（管理網段）。
4. NSX / VNA 只處理 VPC 的流量（VLAN 6 的 External Connection；VNA 提供 LoadBalancer 等服務）。VLAN 7 沒有加進 Transit Gateway，不屬於任何 VPC。

> ℹ️ 另一種做法是讓 VKS 節點多一張 eth1 直接掛 NFS（可以 RWX），那條路要在 NSX 建 VLAN 延伸 Subnet，見 [`ui-step-by-step/vpc-nas-pv`](../ui-step-by-step/vpc-nas-pv/README.md) 做法 2。這份只用「ESXi 掛 datastore」這條，NSX 完全不用為 NFS 做任何設定。

## 環境

| 項目 | 值 |
|---|---|
| 管理網域 | `vcf-m06`：vCenter `vcf-m06-vc01`（10.0.1.198）、NSX `vcf-m06-nsx01`（10.0.1.199）、SDDC Manager `vcf-m06-sddcm01`、vSAN OSA，3 台 nested ESX 9.1.0（10.0.1.195-197） |
| **沒有部署** | VCF Management Services（VSP）、VCF Operations、Fleet、VCF Automation |
| VPC 外部網路 | **VLAN 6**，192.168.16.0/24，閘道 .254，External IP Block `vks-block`（排除 .240-.254） |
| **NAS 網路** | **VLAN 7**，192.168.17.0/24：NAS .20、ESXi vmk3 .21-.23，閘道 .254（沒有 NAT） |
| NAS | `nfs-vks01`（Ubuntu 22.04，離線安裝 nfs-kernel-server），export `/export/vks-ds` 給 192.168.17.0/24，`no_root_squash` |
| 外部 Harbor | `harbor01.home.lab`（10.0.0.86），Harbor v2.15.4，自簽 CA，project `vks-apps`（public） |
| VNA | `vks-vna`，1 台 `vcf-m06-vna01a`（10.0.1.209），Large |
| Supervisor 管理 IP | 10.0.1.222-226 |
| DNS / NTP | 10.0.0.200 / 10.0.1.254 |

NAS 主機（[`cli/10-nas-server.txt`](cli/10-nas-server.txt)）：

```text
$ sudo exportfs -v
/export/vks-ds   192.168.17.0/24(sync,wdelay,hide,no_subtree_check,sec=sys,rw,secure,no_root_squash,no_all_squash)
$ timeout 5 bash -c 'echo > /dev/tcp/8.8.8.8/53' || echo ...
no internet（VLAN 7 沒有 NAT）
```

NAS 的建置（離線安裝）見 [`ui-step-by-step/vpc-nas-pv`](../ui-step-by-step/vpc-nas-pv/README.md) 步驟 0。正式環境就是你的 NAS 設備，只要在 VLAN 7 export NFS 3 給 ESXi 的 vmk3 網段即可。

## 前提

| 前提 | 參考 |
|---|---|
| VCF 9.1.1 管理網域，bring-up 跑完 NSX 就中止（不部署 VCFMS） | [`vpc-airgap-novcfms`](../ui-step-by-step/vpc-airgap-novcfms/README.md) 步驟 1-2 |
| vSphere Client 語言 English、HA/DRS、vSAN 靜音（nested）、storage policy `vks-ftt0`、port group 安全性（nested）、VLAN 6 不出網 | [`vpc-airgap-novcfms`](../ui-step-by-step/vpc-airgap-novcfms/README.md) 步驟 3 |
| 外部 Harbor（自簽 CA），`vks-apps` 已推好 `nginx-unprivileged:1.30.4-alpine`、`busybox:1.37.0` | 本 repo 主文件 |
| VKr 檔案（`.ovf` / `-disk1.vmdk` / `.mf` / `.cert`）已搬進內網 | 本 repo 主文件 |

> 🔴 vSphere Client 語言一定要是 English：Namespace 的 Resources（LCI）外掛沒有繁中翻譯，zh-TW 會整頁空白。

---

## 步驟 1：NFS 儲存走 VLAN 7（UI）

### 1-1 Port group `nas-vlan7`

VDS `vcf-m06-cl01-vds01` → **ACTIONS → Distributed Port Group → New Distributed Port Group**：Name `nas-vlan7` → VLAN type **VLAN**、VLAN ID **7**（其他預設）→ FINISH。

![](img/101-vds-actions-new-pg.png)
![](img/102-pg-1-name.png)
![](img/103-pg-2-vlan7.png)
![](img/104-pg-3-ready.png)
![](img/105-pg-created.png)

> NFS 用的 port group 不需要 Promiscuous / Forged transmits（那是給 nested 的 Supervisor / VNA 用的）。

### 1-2 每台主機加 vmk3

主機 → **Configure → Networking → VMkernel adapters → ADD NETWORKING**：

| 精靈頁 | 設定 |
|---|---|
| Connection type | VMkernel Network Adapter |
| Target device | Select an existing network → `nas-vlan7` |
| Port properties | **不勾任何服務**（NFS 不需要勾 service；vMotion / vSAN 都不要）；MTU 選 Custom 填 **1500**（要和 NAS 一致；不選的話會沿用 VDS 的 MTU） |
| IPv4 settings | Static：`192.168.17.21` / `255.255.255.0`（esx02 = .22、esx03 = .23）。**不要**改 default gateway：NAS 和 vmk3 在同一段 |

![](img/110-vmk-list.png)
![](img/111-vmk-target.png)
![](img/112-vmk-port-props.png)
![](img/113-vmk-ipv4.png)
![](img/114-vmk-ready.png)
![](img/115-vmk-added.png)

三台做完，用 vmk3 ping NAS（nested ESX 的 SSH 是關的，用 PowerCLI `Get-EsxCli -V2`，[`scripts/Test-NasPing.ps1`](scripts/Test-NasPing.ps1)，[`cli/11-vmk3-ping.txt`](cli/11-vmk3-ping.txt)）：

```text
vcf-m06-esx01.home.lab  vmk3 -> 192.168.17.20  sent 3 / recv 3  rtt avg 504 us
vcf-m06-esx02.home.lab  vmk3 -> 192.168.17.20  sent 3 / recv 3  rtt avg 603 us
vcf-m06-esx03.home.lab  vmk3 -> 192.168.17.20  sent 3 / recv 3  rtt avg 556 us
```

### 1-3 NFS datastore `nas-vks-ds`（Vmknic binding = vmk3）

叢集 `vcf-m06-cl01` → **ACTIONS → Storage → New Datastore**：

| 精靈頁 | 設定 |
|---|---|
| Type | **NFS** |
| NFS version | **NFS 3** |
| Name and configuration | Name `nas-vks-ds`、Folder `/export/vks-ds`、Server `192.168.17.20`、**勾 Vmknic binding** |
| Hosts accessibility | Select all（3 台） |
| **Vmknic bindings** | Vmknics on all hosts → **vmk3** |

![](img/120-cluster-actions-new-datastore.png)
![](img/121-ds-1-type-nfs.png)
![](img/122-ds-2-nfs3.png)
![](img/123-ds-3-name-config.png)
![](img/124-ds-4-hosts.png)
![](img/125-ds-5-vmknic-vmk3.png)
![](img/126-ds-6-ready.png)
![](img/127-ds-summary.png)

> 🔑 **Vmknic binding** 是讓 NFS 固定走 vmk3 的關鍵。不勾的話 ESXi 依路由表選介面；vmk3 和 NAS 同網段時通常也會走 vmk3，但綁定之後就不會因為路由改變而改走 vmk0（管理網段）。

ESXi 端確認（[`cli/12-esx-nfs.txt`](cli/12-esx-nfs.txt)）：每台的 NFS 連線來源都是自己的 vmk3：

```text
### vcf-m06-esx01.home.lab
nfs  nas-vks-ds  192.168.17.20:/export/vks-ds  accessible=true mounted=true
vmk3 192.168.17.21/255.255.255.0
tcp  192.168.17.21:728 -> 192.168.17.20:2049  ESTABLISHED
（esx02 = 192.168.17.22、esx03 = 192.168.17.23，同上）
```

### 1-4 Tag：`vks-storage` / `nas`

**Tags & Custom Attributes → Tags → NEW**：Name `nas` → **Create New Category**：`vks-storage`、One tag、Associable Object Types 只勾 **Datastore** → CREATE → CREATE。再到 `nas-vks-ds` → **ACTIONS → Tags & Custom Attributes → Assign Tag** → `nas`。

![](img/130-tags-home.png)
![](img/131-tag-new-category.png)
![](img/132-tag-create-nas.png)
![](img/133-tag-created.png)
![](img/134-ds-assign-tag.png)
![](img/135-ds-tag-assigned.png)

### 1-5 Storage policy `vks-nas`

**Policies and Profiles → VM Storage Policies → CREATE**：

| 精靈頁 | 設定 |
|---|---|
| Name and description | Name `vks-nas`，**K8s Compliant Name 自己填 `vks-nas`**（不會自動帶出；VKS 的 StorageClass 就叫這個名字） |
| Policy structure | 只勾 **Enable tag based placement rules** |
| Tag based placement | Tag category `vks-storage` → Use storage tagged with → BROWSE TAGS → `nas` |
| Storage compatibility | 只有 `nas-vks-ds`（NFS 3）——vSAN 不在清單裡就對了 |

![](img/140-policy-name.png)
![](img/141-policy-structure-tag.png)
![](img/142-policy-tag-rule.png)
![](img/143-policy-storage-compat.png)
![](img/144-policy-review.png)
![](img/145-policy-created.png)

到這裡 NFS 這條線已經完成，**NSX 完全沒有為 NFS 做任何設定**。

---

## 步驟 2：Transit Gateway + VNA（UI）

**Networks → Transit Gateways**：bring-up 已建立 **Default Transit Gateway**，Connection 是 None → **SETUP NETWORK CONNECTIVITY**：

| 頁 | 設定 |
|---|---|
| 1 Transit Gateway Connectivity | VLAN-backed 只有 **Distributed VLAN Connection**；NEXT 時的 *Networking Prerequisites* 勾 Select All → CONTINUE |
| 2 External Network Connectivity | VLAN ID **6**；Gateway CIDR **`192.168.16.254/24`**（輸入後按 Enter）；External IP Blocks → **Create New** `vks-block` = `192.168.16.0/24`，Excluded `192.168.16.240-192.168.16.254` |
| 3 VPC Services | VNA cluster `vks-vna`、Form Factor **Large**；ADD 節點 `vcf-m06-vna01a.home.lab`、cluster `vcf-m06-cl01`、vSAN、Static `10.0.1.209/23`、gw 10.0.0.1、port group `SDDC-DPortGroup-VM-Mgmt` |
| 4 Review and Deploy | DEPLOY |

![](img/230-transit-gateways.png)
![](img/231-setup-p1-distributed-vlan.png)
![](img/232-setup-prereq.png)
![](img/233-ipblock-vks-block.png)
![](img/234-setup-p2-external.png)
![](img/235-vna-add-node.png)
![](img/236-vna-cluster-large.png)
![](img/237-setup-review.png)
![](img/238-setup-deploying.png)

> 🔑 這裡**只有 VLAN 6**。VLAN 7（NAS）不要加進 Transit Gateway、也不要建成 External Connection——NFS 不屬於 VPC，加進來反而會讓 NAS 流量有機會繞進 NSX。

## 步驟 3：VKr — Local Content Library + 匯入本機檔案（UI）

**Content Libraries → CREATE**：`vkr-local` → **Local content library**（不開 publishing）→ 不套 security policy → storage 選 vSAN（library 放 vSAN 即可，NAS 只放 PV）。

![](img/240-cl-1-name.png)
![](img/241-cl-2-local.png)
![](img/242-cl-3-security.png)
![](img/243-cl-4-storage.png)
![](img/244-cl-5-ready.png)

`vkr-local` → **ACTIONS → Import item** → **Local file** → **UPLOAD FILES** 一次選 4 個檔案（`.ovf`、`-disk1.vmdk`、`.mf`、`.cert`）→ Item name 自動帶 `photon-5-amd64-v1.36.2---vmware.2-vkr.3` → IMPORT。

![](img/245-cl-actions-import.png)
![](img/246-cl-import-local-files.png)

上傳約 8 分鐘（和 VNA 部署同時進行；**上傳期間不要重新整理這個瀏覽器分頁**，上傳是瀏覽器在送），完成後 1 個 OVF template，11.87 GB：

![](img/247-cl-vkr-imported.png)

## 步驟 4：啟用 Supervisor（UI）

VNA 變成 UP 後（這次約 15 分鐘，和 VKr 上傳同時），Transit Gateway 狀態 **Success**（Connection = Distributed VLAN、External Connection = `Distributed-vlan-connection-6`）：

![](img/239-tgw-success.png)

**Supervisor Management → GET STARTED**：

| 精靈頁 | 設定 |
|---|---|
| 1 vCenter Server and Network | **VCF Networking with VPC (recommended)** |
| 2 Supervisor location | **Cluster deployment**：`vcf-m06-sv01`、`vcf-m06-cl01`、zone `vz-01` |
| 3 Storage | Control Plane / Ephemeral Disks / Image Cache 都選 `vks-ftt0`（vSAN）。**不要選 `vks-nas`**：Supervisor 控制平面放 vSAN，NAS 只放 VKS 的 PV |
| 4 Management Network | Static、`SDDC-DPortGroup-VM-Mgmt`、10.0.1.222-10.0.1.226、255.255.254.0、gw 10.0.0.1、DNS 10.0.0.200、search domain home.lab、NTP 10.0.1.254 |
| 5 Workload Network | NSX Project Default、VPC Connectivity Profile Default、External IP Blocks 自動帶出 `vks-block`；DNS 10.0.0.200、NTP 10.0.1.254 |
| 6 Advanced Settings | Control Plane **Small** |

![](img/350-supervisor-mgmt-home.png)
![](img/351-sv-1-network.png)
![](img/352-sv-2-location.png)
![](img/353-sv-3-storage.png)
![](img/354-sv-4-mgmt-network.png)
![](img/355-sv-5-workload.png)
![](img/356-sv-6-advanced.png)
![](img/357-sv-7-ready.png)
![](img/358-sv-configuring.png)

**30 分鐘**（23:24 → 23:54）變成 **Running**，Control Plane Node Address **192.168.16.3**（中途 kubernetes_status 在 ERROR / WARNING / READY 之間跳動屬正常）：

![](img/359-sv-running.png)

## 步驟 5：讓 Supervisor 和 VKS 信任外部 Harbor（UI）

**Supervisor → Configure → Container Registries → ADD REGISTRY**：Registry Name `harbor01`、Registry host URL `harbor01.home.lab`、TLS Certificate 貼 Harbor 的 **CA 憑證**、帳密留空（`vks-apps` 是 public project）。

![](img/460-sv-container-registries.png)
![](img/461-sv-add-registry.png)
![](img/462-sv-registry-added.png)

Supervisor 建立 `ClusterRegistryConfig`（[`cli/03-cluster-registry-config.txt`](cli/03-cluster-registry-config.txt)），Supervisor Services、Pods、VKS 叢集都會套用，**叢集 YAML 不用另外設 `trust`**。

## 步驟 6：Kubernetes Service library + Namespace（UI）

**Supervisor → Configure → General → Kubernetes Service → ADD** → 勾 `vkr-local` → ADD：

![](img/463-sv-k8s-service-library.png)
![](img/464-sv-add-library-local.png)
![](img/465-sv-library-added.png)

從本機匯入的 VKr 自動產生 KubernetesRelease（[`cli/02-kr.txt`](cli/02-kr.txt)）：

```text
NAME                       VERSION                  READY   COMPATIBLE
v1.36.2---vmware.2-vkr.3   v1.36.2+vmware.2-vkr.3   True    True
```

**Namespaces → NEW NAMESPACE**：Supervisor `vcf-m06-sv01` → Name `vks-lab` → zone `vz-01` → FINISH。

![](img/466-ns-1-location.png)
![](img/467-ns-2-config.png)
![](img/468-ns-3-zone.png)
![](img/469-ns-4-review.png)

Namespace Summary：

- **ADD STORAGE**：勾 **`vks-ftt0`**（節點磁碟，vSAN）和 **`vks-nas`**（PV，NAS）兩個
- **ADD VM CLASS**：`best-effort-xsmall` / `best-effort-small` / `best-effort-medium`

![](img/470-ns-add-storage.png)
![](img/471-ns-add-vmclass.png)
![](img/472-ns-summary-ready.png)

加完 storage policy，Supervisor 自動產生同名的 StorageClass（各一個 Immediate + `-latebinding`）：

```text
$ kubectl get sc | grep vks-
vks-ftt0               csi.vsphere.vmware.com   Delete   Immediate              true
vks-ftt0-latebinding   csi.vsphere.vmware.com   Delete   WaitForFirstConsumer   true
vks-nas                csi.vsphere.vmware.com   Delete   Immediate              true
vks-nas-latebinding    csi.vsphere.vmware.com   Delete   WaitForFirstConsumer   true
```

## 步驟 7：Public SubnetSet（UI）

Namespace → **Resources** → Network → **GO TO SERVICE** → **SubnetSets → NEW SUBNETSET**：Name `public`、Access Mode **Public**、16 IPs、DHCP None → CREATE（[`cli/04-subnetset.txt`](cli/04-subnetset.txt)）。

![](img/480-lci-network-service.png)
![](img/481-lci-new-subnetset.png)
![](img/482-lci-subnetset-created.png)

> ℹ️ Resources 第一次開啟時如果停在別的頁面（例如上一輪已刪掉的叢集），按麵包屑的 `vks-lab` 回到 namespace 首頁。

## 步驟 8：VKS 叢集（UI，Custom Configuration）

Resources → Kubernetes → **CREATE CLUSTER** → **Custom Configuration**：

| 精靈頁 | 設定 |
|---|---|
| General | Name `vks-cl01`、ClusterClass `builtin-generic-v3.7.0`、Kubernetes release v1.36.2、VM class `best-effort-medium`、**Storage Class `vks-ftt0`**（節點系統碟放 vSAN） |
| General → Storage → Persistent Volume Storage | **Default Storage Class = `vks-nas`**（guest cluster 裡的預設 StorageClass 就是 NAS） |
| General → Network → Node Network | **Use custom primary network** → `public (Subnet Set)` |
| Control Plane | 1 台、Photon |
| Node Pools | node pool 改名 `vks-cl01-np-1`，Overrides 的 VM class 改 `best-effort-small` |

![](img/583-vks-wizard-1-custom.png)
![](img/584-vks-wizard-2-general.png)
![](img/584b-vks-wizard-2-storage.png)
![](img/584c-vks-wizard-2-default-sc-nas.png)
![](img/585-vks-wizard-2-network.png)
![](img/586-vks-wizard-3-cp.png)
![](img/587-vks-nodepool-vmclass-small.png)
![](img/588-vks-nodepool-review.png)
![](img/589-vks-wizard-4-nodepools.png)
![](img/590-vks-wizard-5-review.png)

> ⚠️ 回頭展開 **General Settings** 修改任何欄位，精靈會把 **Node Network** 和 **Node Pools** 的自訂值重設（primary network 變回自動產生、node pool 名稱和 VM class override 消失）。改完要回去重選，送出前看右側 YAML 確認 `networks` 和 `overrides` 都還在。

精靈產生的 YAML（[`vks-cl01.yaml`](vks-cl01.yaml)）：

```yaml
    variables:
      - name: vmClass
        value: best-effort-medium
      - name: storageClass
        value: vks-ftt0            # 節點系統碟 → vSAN
      - name: vsphereOptions
        value:
          persistentVolumes:
            defaultStorageClass: vks-nas   # guest 預設 StorageClass → NAS
      - name: networks
        value:
          interfaces:
            primary:
              network: {name: public, kind: SubnetSet, apiVersion: crd.nsx.vmware.com/v1alpha1}
```

**沒有任何和 registry、NFS 有關的設定**：Harbor CA 由步驟 5 下發；NAS 對 VKS 來說只是一個 StorageClass。

第一次按 FINISH（Supervisor Running 後 15 分鐘）被擋：

![](img/590b-vks-finish-error-networks.png)

```text
admission webhook "capi.mutating.tanzukubernetescluster.run.tanzu.vmware.com" denied the request:
spec.topology.variables[networks]: Invalid value: ...: variable is not defined
```

Supervisor 剛 Running 時 VKS 的 webhook 還沒拿到 ClusterClass 的 `networks` 變數。用 `kubectl apply --dry-run=server -f vks-cl01.yaml` 測，通過後（這次 1 分鐘內）在精靈**再按一次 FINISH** 即可，不用重填。

![](img/591-vks-cluster-creating.png)

約 **6 分鐘**（00:11 → 00:17）變成 **Available**，CP 192.168.16.50、worker 192.168.16.51：

![](img/592-vks-cluster-available.png)
![](img/593-vks-cluster-detail.png)

---

## 步驟 9：驗證（CLI + vCenter 效能圖）

```bash
kubectl vsphere login --server=192.168.16.3 -u administrator@vsphere.local --insecure-skip-tls-verify \
  --tanzu-kubernetes-cluster-namespace vks-lab --tanzu-kubernetes-cluster-name vks-cl01
kubectl config use-context vks-cl01
```

### 9-1 節點與 StorageClass

[`cli/05-guest-nodes-sc.txt`](cli/05-guest-nodes-sc.txt)：兩個節點 Ready；guest 裡的 **`vks-nas` 是 default StorageClass**（精靈設的 `defaultStorageClass`）：

```text
NAME                   PROVISIONER              VOLUMEBINDINGMODE
vks-ftt0               csi.vsphere.vmware.com   Immediate
vks-ftt0-latebinding   csi.vsphere.vmware.com   WaitForFirstConsumer
vks-nas (default)      csi.vsphere.vmware.com   Immediate
vks-nas-latebinding    csi.vsphere.vmware.com   WaitForFirstConsumer
```

### 9-2 Air-gap：image 只從 Harbor 來

[`nginx-harbor.yaml`](nginx-harbor.yaml)（[`cli/06-nginx-from-harbor.txt`](cli/06-nginx-from-harbor.txt)）：

```text
Image:  harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine
kubelet: Successfully pulled image "harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine"
nginx-lb   LoadBalancer   10.110.46.25   192.168.16.33   80:31982/TCP
$ curl -s http://192.168.16.33/ | grep title      # 從管理網段
<title>Welcome to nginx!</title>
```

反向測試 [`pull-test.yaml`](pull-test.yaml)（[`cli/07-pull-test.txt`](cli/07-pull-test.txt)）：同一個 busybox，`docker.io` 拉不到、Harbor 拉得到：

```text
from-dockerhub   0/1   ImagePullBackOff   ← Head "https://registry-1.docker.io/v2/...": dial tcp ...:443: i/o timeout
from-harbor      0/1   Completed          ← hello-from-harbor，並且 wget 到 nginx-lb
```

### 9-3 PV 落在 NAS

[`pvc-nas.yaml`](pvc-nas.yaml)：PVC `storageClassName: vks-nas` + 一個寫檔的 Pod（[`cli/13-pvc-on-nas.txt`](cli/13-pvc-on-nas.txt)）：

```text
data-on-nas   Bound   pvc-9bf1617d-...   5Gi   RWO   vks-nas
/dev/sdb on /data type ext4 (rw,relatime)          ← Pod 看到的是一顆區塊磁碟，不是 NFS
hello from NAS PV ...

$ kubectl -n vks-lab get pvc      # Supervisor 端
cf2b08b2-...-9bf1617d-...         5Gi    vks-nas     ← guest 的 PV
vks-cl01-mqr72-xhxtr-1987f94d     20Gi   vks-ftt0    ← 節點系統碟（vSAN）
vks-cl01-vks-cl01-np-1-...        20Gi   vks-ftt0
```

vCenter **叢集 → Monitor → Cloud Native Storage → Container Volumes**：PV 的 Datastore 是 `nas-vks-ds`，節點碟在 vSAN：

![](img/690-cns-container-volumes.png)

NAS 上就是一顆 FCD VMDK（[`cli/14-nas-fcd-files.txt`](cli/14-nas-fcd-files.txt)）：

```text
/export/vks-ds/fcd/617951ff5f5546cbae092bf04044aa02-flat.vmdk   5368709120（thin）
```

### 9-4 NFS 流量沒有經過 VNA（重點）

在 Pod 裡往 NAS PV 寫 1 GiB，同時看 NAS 收到多少、VNA 和 worker VM 的網路 / 虛擬磁碟計數器；再用**同一個 1 GiB 檔案經 VPC LoadBalancer 下載**當對照組（[`path-control-lb.yaml`](path-control-lb.yaml)）。量法：vCenter realtime 效能計數器（[`scripts/Measure-VmTraffic.ps1`](scripts/Measure-VmTraffic.ps1)）+ NAS 的 `eth0 rx_bytes`。完整輸出：[`cli/15-nfs-path-proof.txt`](cli/15-nfs-path-proof.txt)。

| 測試 | NAS 收到 | VNA 網路（收 / 送） | worker 網路（收 / 送） | worker 虛擬磁碟寫入 |
|---|---|---|---|---|
| **A. Pod 寫 1 GiB 到 NAS PV** | **1025 MiB** | **0.7 / 0.7 MB** | 0.1 / 0.1 MB | **1074 MB** |
| B. 對照：同一個 1 GiB 經 VPC LB 下載 | — | **1083 / 1083 MB** | 12 / 1073 MB | 2 MB |

- A：worker 的 1 GiB 是「虛擬磁碟寫入」，不是網路流量；ESXi 把它轉成 NFS、從 vmk3 送到 NAS。VNA 幾乎是 0。
- B：只要是走 VPC 的流量，VNA 一定看得到（1 GiB 進、1 GiB 出）——證明 A 的 0 不是量不到，而是真的沒經過。
- NAS 上的 NFS 連線只來自三台 ESXi 的 vmk3：

```text
$ ss -tn state established '( sport = :2049 )'      # NAS 上
192.168.17.20:2049  192.168.17.23:804
192.168.17.20:2049  192.168.17.22:912
192.168.17.20:2049  192.168.17.21:728
```

vCenter 效能圖（Real-time）。VNA 的網路只有在對照組 B 時出現大峰值；寫入 NAS 的時段在 worker 的 **Virtual Disk Rate**，不在任何網路圖上：

![](img/691-vna-perf-network.png)
![](img/692-worker-perf-disk.png)
![](img/693-worker-perf-network.png)

> ℹ️ 量 VNA 要加總 vNIC 以外的 instance：VNA 的資料面流量在 vCenter 效能計數器裡記在 `vmnic0` / `vmnic1` 這兩個 instance，VM 彙總值（instance 空字串）不含它。一般 VM（worker）則記在 vNIC `4000`。腳本取「最忙的那個 instance」，避免同一筆流量同時記在 vNIC 和 vmnic 上被重複計算。
>
> ℹ️ 效能計數器用 vCenter 的時間。這個 lab 的跳板機（AD/DNS 主機）時鐘比 vCenter 快約 160 秒，腳本會先取 vCenter 時間換算。

## 時間

| 階段 | 時間 |
|---|---|
| 拆除上一輪（叢集、namespace、Supervisor 停用、NSX 連線 / VNA、zone、content library、NFS 設定） | 約 1 小時（Supervisor 停用就佔 36 分鐘） |
| 步驟 1：NFS 儲存（port group、vmk3 ×3、datastore、tag、policy） | 約 15 分鐘 |
| 步驟 2：Transit Gateway + VNA | 15 分鐘（23:05 → 23:20，和 VKr 上傳同時） |
| 步驟 3：VKr 上傳 | 8 分鐘（23:09 → 23:17） |
| 步驟 4：Supervisor | **30 分鐘**（23:24 → 23:54） |
| 步驟 5-7：Harbor 信任、library、namespace、SubnetSet | 約 15 分鐘 |
| 步驟 8：VKS 叢集 | **6 分鐘**（00:11 → 00:17） |

## 遇到的問題

| # | 症狀 | 原因 / 處理 |
|---|---|---|
| 1 | Port group 建出來 VLAN 是 1、Number of ports 是 7 | 自動化填錯欄位（填到 Number of ports）。UI 上照著 VLAN ID 欄位填即可；建錯就刪掉重建 |
| 2 | NFS datastore 的 Folder 變成 `C:/Program Files/Git/export/vks-ds` | Git Bash 把 `/export/...` 當成路徑轉換（自動化才會遇到）；`MSYS_NO_PATHCONV=1` |
| 3 | VKS 精靈回頭改 General Settings 後，Node Network 和 Node Pools 的自訂值不見 | 精靈的行為；改完要重選 `public (Subnet Set)`、重新編輯 node pool，送出前看 YAML |
| 4 | 第一次 FINISH 被擋：`variables[networks] ... variable is not defined` | Supervisor 剛 Running，VKS webhook 還沒同步 ClusterClass 變數；`kubectl apply --dry-run=server` 通過後再按 FINISH |
| 5 | NAS 上 `ss` 還看到已刪除節點的 NFS 連線（上一輪的 192.168.17.65/.66） | 對端已不存在的殘留 socket；`sudo ss -K dst <IP>` 清掉 |
| 6 | NSX 的 Transit Gateway attachment statistics 不會即時更新（停在幾分鐘前的值） | 不適合拿來比對短時間的流量；改用 vCenter realtime 效能計數器 |

## 和其他文件的差異

| 項目 | [`vpc-airgap-novcfms`](../ui-step-by-step/vpc-airgap-novcfms/README.md) | [`vpc-nas-pv`](../ui-step-by-step/vpc-nas-pv/README.md) | 這份 |
|---|---|---|---|
| 範圍 | VCF bring-up 中止 + VPC Supervisor + VKS | 在既有環境上外掛 NAS（兩種做法） | **拆掉重做**：NFS VLAN 7 → VPC/VNA → Supervisor → VKS，一路截圖 |
| PV | vSAN（`vks-ftt0`） | 做法 1 NFS datastore（RWO）/ 做法 2 VKS eth1 + NFS CSI（RWX） | **NFS datastore（vmk3 綁定），guest 預設 StorageClass = `vks-nas`** |
| NFS 是否碰到 NSX | — | 做法 1 不碰；做法 2 要建 VLAN 延伸 Subnet | **完全不碰** |
| 驗證 NFS 不經過 VNA | — | NAS `ss` 連線來源 | NAS `ss` + **1 GiB 寫入 vs LB 對照組的流量計數** |

**結論：VLAN-backed VPC + VNA 的 VKS，PV 放在獨立 VLAN 的 NAS 上，只要由 ESXi 用專用 vmk（Vmknic binding）掛 NFS datastore，NFS 流量就完全不會進 NSX / VNA。** VKS 這邊只看到一個 StorageClass；air-gap 部分（Harbor、Local CL、Container Registries）和 NAS 互不影響。
