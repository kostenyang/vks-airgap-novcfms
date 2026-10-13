# VKS on VLAN-backed VPC — Air-gap、不部署 VCFMS（m06，2026-10-13，UI step by step）

> 📄 Word 版：[`VKS-VPC-Airgap-NoVCFMS-UI-Step-by-Step.docx`](VKS-VPC-Airgap-NoVCFMS-UI-Step-by-Step.docx)

在**不部署 VCF Management Services（VCFMS）**的 VCF 9.1.1 管理網域上，用 **VLAN-backed VPC** 啟用 Supervisor，建立 VKS 叢集，並在**連不到網際網路**的前提下從內部 Harbor 部署應用。

- 不部署 VCFMS 的做法和本 repo 主文件相同：VCF Installer bring-up 跑完 NSX 之後、在 VCF Management Platform（VSP）開始時中止。主文件是用 API 送 spec，這份從 **VCF Installer UI 精靈**開始。
- 主文件的 Supervisor 是 VDS + Foundation LB；這份是 **VPC**（VLAN-backed VPC + VNA）。
- 所有 vSphere / NSX / Installer 的設定都用 UI 操作並截圖；只有中止 bring-up、驗證這兩件本來就只能下指令的事用 CLI。

## 成果

| 項目 | 值 |
|---|---|
| 管理網域 | `vcf-m06`：vCenter `vcf-m06-vc01`、NSX `vcf-m06-nsx01`、SDDC Manager `vcf-m06-sddcm01`、vSAN OSA（3 台 nested ESX 9.1.0） |
| **沒有部署** | VCF Management Services（VSP）、VCF Operations、Cloud proxy、Fleet / Identity Broker、License Server、VCF Automation |
| Supervisor 網路 | VLAN-backed VPC：Distributed VLAN Connection（VLAN 6 / 192.168.16.254）+ VNA `vks-vna`（Large） |
| 內部 registry | `harbor01.home.lab`（10.0.0.86），Harbor v2.15.4，自簽 CA，主機本身也擋掉對外連線 |
| VKr 來源 | Local Content Library `vkr-local`，從本機檔案匯入 |
| 信任 Harbor CA | Supervisor → Configure → **Container Registries** |
| VKS 叢集 | `vks-lab/vks-cl01`，v1.36.2，ClusterClass `builtin-generic-v3.7.0`，CP 192.168.16.50 + worker 192.168.16.51 |
| 測試應用 | `harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine` ×2，LoadBalancer VIP **192.168.16.33** |
| 斷網證明 | 同一個 busybox：`docker.io` 拉不到（ImagePullBackOff），Harbor 拉得到 |
| 時間 | bring-up（到 NSX）2 小時 14 分 → TGW + VNA 約 6 分 → Supervisor 25 分 → VKS 叢集 5 分 |

## 環境

| 項目 | 值 |
|---|---|
| nested ESX | `vcf-m06-esx01..03`（10.0.1.195-197），20 vCPU / 80 GB，vSAN cache 60 GB + capacity 3600 GB（thin） |
| 管理網段 | 10.0.0.0/23，gw 10.0.0.1，DNS 10.0.0.200，NTP 10.0.1.254 |
| vMotion / vSAN | 192.168.65.0/24 / 192.168.66.0/24（VLAN 0，不路由） |
| VPC 外部網路 | **VLAN 6**，192.168.16.0/24，閘道 192.168.16.254（上游閘道沒有 NAT，本來就出不去） |
| VCF Installer | 9.1.1，offline depot 為內部 depot（10.0.0.61） |

DNS（A + PTR）要先建好。即使 VCFMS、Ops 等元件不會部署，精靈驗證仍要求它們的 FQDN 能正反解：

| FQDN | IP | 會不會部署 |
|---|---|---|
| `vcf-m06-esx01..03` | 10.0.1.195-197 | ✅ |
| `vcf-m06-vc01` | 10.0.1.198 | ✅ |
| `vcf-m06-nsx01`（VIP）/ `vcf-m06-nsx01a` | 10.0.1.199 / .200 | ✅ |
| `vcf-m06-sddcm01` | 10.0.1.201 | ✅ |
| `vcf-m06-ops01` / `opsc01` / `lic01` / `fleet01` / `vsp01` / `shared01` / `vidb` | 10.0.1.202-208 | ❌ 只為了通過驗證 |
| VCF management services IP pool（12 個） | 10.0.1.210-221 | ❌ 只為了通過驗證 |
| `vcf-m06-vna01a`（VNA） | 10.0.1.209 | ✅（步驟 2） |
| Supervisor 管理 IP | 10.0.1.222-226 | ✅（步驟 4） |

## Air-gap 的範圍

| 網段 | 對外 | 說明 |
|---|---|---|
| VLAN 6（Supervisor 工作網路、VKS 節點、LB VIP） | ❌ 本來就出不去 | 上游閘道沒有替這段做 NAT |
| Harbor VM | ❌ 用 iptables 擋 | 只放行私有網段 |
| 管理網段（Installer、vCenter、ESX、NSX、SDDC Manager） | ⚠️ 這個 lab 沒有擋 | 所有內容都只從內部來源取得（內部 depot、本機檔案、Harbor）。**正式 air-gap 環境這段也要斷** |

## 步驟 1：VCF Installer 精靈（UI）

Installer 首頁：depot 已連到內部 offline depot，9.1.1 的元件都已下載。按 **DEPLOYMENT WIZARD → VMware Cloud Foundation**。

![](img/bringup/01-installer-home.png)
![](img/bringup/02-wizard-menu.png)
![](img/bringup/03-intro-about.png)

**Deployment Paths** 選 **Deploy a new VCF fleet**。

![](img/bringup/04-paths-new-fleet.png)

### Plan

| 步驟 | 設定 |
|---|---|
| 1 Existing Component | 只勾 **I have an existing VCF Automation instance or I will deploy later**（不部署 VCF Automation） |
| 2 Size Options | Deployment model **Simple**、size Small |
| 3 Network Options | **CUSTOMIZE**：VM management network = **Use ESX management network**；VCF management network = Use VM management network；VPC = **VLAN backed VPC**（Gateway Connectivity 只剩 Distributed） |
| 4 Storage | vSAN，architecture **vSAN OSA** |
| 5 Review Prerequisites | 3 hosts / 52 vCPU / 155 GB / 6748 GB / 4 VLANs |

![](img/bringup/05-plan-existing-component.png)
![](img/bringup/06-plan-size-simple.png)
![](img/bringup/07-plan-network-default.png)
![](img/bringup/08-plan-network-custom.png)
![](img/bringup/09-plan-storage-vsan-osa.png)
![](img/bringup/10-plan-prereq-summary.png)

資源需求明細：其中 **VCF management services 就佔 28 vCPU / 58 GB / 2900 GB**，這次不會部署，但精靈仍以完整需求檢查。

![](img/bringup/11-plan-prereq-resources.png)
![](img/bringup/12-plan-prereq-vlans.png)
![](img/bringup/13-plan-prereq-fqdns.png)

### Prepare

| 步驟 | 設定 |
|---|---|
| 1 General Information | 9.1.1.0、instance `vcf-m06-instance`、domain `vcf-m06`；DNS / NTP / suffix；**CEIP 關閉、Autogenerate passwords 關閉** |
| 2 Hosts | 3 台 FQDN + root 密碼 → **CONFIRM ALL FINGERPRINTS** → NEXT 跳出 *Resource Requirements Warning*（資源夠，但沒有 20% 餘裕）→ **YES, PROCEED** |
| 3 Networks | ESX mgmt VLAN 0 / `10.0.0.1/23`；VCF Management Services IP Pool `10.0.1.210-10.0.1.221`；vMotion / vSAN VLAN 0、`192.168.65.1/24` / `192.168.66.1/24`、各 .11-.20 |
| 4 VCF Management | Ops `vcf-m06-ops01`、Cloud Proxy `vcf-m06-opsc01`、License Server `vcf-m06-lic01`、Fleet / Instance / Identity Broker / services runtime FQDN（**全部不會部署**，只是必填） |
| 5 vCenter | `vcf-m06-vc01`、datacenter `vcf-m06-dc01`、cluster `vcf-m06-cl01`、`vsphere.local` |
| 6 Storage | vSAN OSA，**FTT 固定為 1**（UI 不能改） |
| 7 Distributed Switch | **Default** profile（一個 VDS、MTU 9000、vmnic0/1）；VLAN backed VPC **沒有 TEP 欄位** |
| 8 NSX Manager | VIP `vcf-m06-nsx01`、appliance `vcf-m06-nsx01a` |
| 9 SDDC Manager | `vcf-m06-sddcm01`（Installer 不在這三台主機上，所以會另部一台 SDDC Manager） |

![](img/bringup/14-prepare-general.png)
![](img/bringup/15-prepare-hosts-fingerprints.png)
![](img/bringup/16-prepare-hosts-resource-warning.png)
![](img/bringup/17-prepare-networks.png)
![](img/bringup/18-prepare-vcf-management.png)
![](img/bringup/19-prepare-vcenter.png)
![](img/bringup/20-prepare-storage.png)
![](img/bringup/21-prepare-vds-default.png)
![](img/bringup/22-prepare-nsx.png)
![](img/bringup/23-prepare-sddcm.png)

> 🔑 選 **VLAN backed VPC** 時，Networks 頁**沒有** Transit Gateway / 外部網路的欄位，Day-0 只會建立預設 Transit Gateway；外部連線（VLAN、閘道、IP block、VNA）在 bring-up 之後才從 vCenter UI 設定（步驟 3）。

### Deploy

![](img/bringup/24-deploy-review-summary.png)
![](img/bringup/25-deploy-review-json.png)

驗證 15 項，3 個 Warning，全部按 **ACKNOWLEDGE ALL WARNINGS**：

| Warning | 原因 |
|---|---|
| vMotion / vSAN 閘道 `.1` 沒有回應 | 這兩段 lab 不路由，正常 |
| *Insufficient Storage. 5400 GB storage is less than the required 6748 GB* | 6748 GB 含 VCFMS 的 2900 GB；FTT=1 時 3 × 3600 GB 只算一半。VCFMS 不會部署，所以可以忽略 |
| 建議至少 65 cores | nested lab |

![](img/bringup/26-deploy-validate-result-1.png)
![](img/bringup/28-deploy-acknowledged.png)

**DEPLOY**：

![](img/bringup/29-deploy-started.png)

## 步驟 2：在 VCF Management Platform 開始時中止 bring-up（CLI）

9.1.1 greenfield 的 milestone 順序：

1. Deploy vCenter
2. Deploy SDDC Manager
3. Configure vSphere cluster
4. Deploy and configure NSX
5. **Deploy and configure VCF Management Platform** ← 第一個 subtask #271/#272 *Deploy VCF Management Services via SDDC Manager* 就是 VSP bootstrap
6. Deploy and configure the operations appliance
7. Deploy and configure VCF Management Services

在第 5 個 milestone 一開始就中止，前 4 個完成的東西（vCenter、SDDC Manager、vSAN、NSX）都保留。

```bash
# 觸發時（#272 Deploy VCF Management Services via SDDC Manager 開始執行）
systemctl stop domainmanager       # VCF Installer：不再往下跑
systemctl restart domainmanager    # SDDC Manager：中斷剛送出的 VSP_BOOTSTRAP 任務
# 刪掉 inner vCenter 上 VSP 相關的 VM（這次還沒建立就被中斷，沒有東西要刪）
systemctl start domainmanager      # VCF Installer：恢復服務，保留可重用
```

這次用監看程式 [`scripts/abort_watcher_m06.py`](scripts/abort_watcher_m06.py) 自動執行（每 10 秒查 `/v1/sddcs/{id}`；加了兩道保險：NSX milestone 必須已完成、`PREVALIDATION_*` 狀態不算開始）。紀錄見 [`cli/02-abort-watcher.log`](cli/02-abort-watcher.log)：

```text
2026-10-13 14:09:32 >>> TRIGGER: [('Update VCF Management Services Deployment Status', 'POSTVALIDATION_COMPLETED_WITH_SUCCESS'), ('Deploy VCF Management Services via SDDC Manager', 'POSTVALIDATION_COMPLETED_WITH_SUCCESS'), ('Monitor VCF Management Services Deployment Task', 'IN_PROGRESS')]
2026-10-13 14:09:32 step 1: stop domainmanager on installer 10.0.1.135
2026-10-13 14:09:36   systemctl is-active → failed（已停止）
2026-10-13 14:09:36 step 2: restart domainmanager on SDDC Manager 10.0.1.201(砍掉進行中的 VSP 任務)
2026-10-13 14:09:47   systemctl is-active → active
2026-10-13 14:09:47 step 3: 等 60 秒,刪除 inner vCenter 上 VSP 相關 VM
2026-10-13 14:10:47   VSP-looking VMs: none
2026-10-13 14:10:47 step 4: start domainmanager on installer 10.0.1.135
2026-10-13 14:10:55   systemctl is-active → active
2026-10-13 14:10:55 ABORT COMPLETE — 之後 30 分鐘每 2 分鐘確認沒有重送 / 沒有新的 VSP VM
（post-check：之後 30 分鐘每 2 分鐘確認一次）
2026-10-13 14:12:56   post-check installer status=COMPLETED_WITH_FAILURE running=[] vsp_vms=[]
2026-10-13 14:41:13   post-check installer status=COMPLETED_WITH_FAILURE running=[] vsp_vms=[]
2026-10-13 14:41:13 POST-CHECK DONE
```

中止後 Installer 顯示前 4 個 milestone 完成、VCF Management Platform 失敗（4/14）。**不要按 RETRY AND PROCEED WITH DEPLOYMENT**，否則會繼續部署 VSP。

![](img/bringup/30-deploy-aborted.png)

inner vCenter 只有 vCenter、SDDC Manager、NSX 三台 VM：

![](img/01-after-abort-vms.png)

## 步驟 3：VKS 前置準備（UI）

### 3-1 vSphere Client 語言改成 English（🔴 一定要做）

右上角使用者 → **My Preferences → Language → Specify a language → English** → SAVE。Namespace → Resources（LCI 外掛）只有 en / es / fr / ja 四種語系，用繁體中文介面會整片空白。

![](img/02-pref-language-english.png)

### 3-2 叢集 HA / DRS

bring-up 完成的叢集已經是 vSphere HA 開啟、DRS **Fully Automated**（Cluster → Configure → Services）。

![](img/03-cluster-drs.png)
![](img/04-cluster-ha.png)

### 3-3 vSAN Health 靜音（nested 才需要）

Cluster → Monitor → **vSAN → vSAN Health**：Unhealthy 有 *NVMe device is VMware certified*、*Performance service status*，Info 有 *vSAN Support Insight*。三項都 **SILENCE ALERT → YES**。

![](img/05-cluster-issues.png)
![](img/06-vsan-health-findings.png)
![](img/07-vsan-silence-dialog.png)
![](img/08-vsan-silenced.png)

### 3-4 VM Storage Policy `vks-ftt0`

**Policies and Profiles → VM Storage Policies → CREATE**：

| 精靈頁 | 設定 |
|---|---|
| Name and description | Name `vks-ftt0`、**K8s Compliant Name `vks-ftt0`**（沒有自動帶出時要自己填） |
| Policy structure | 勾 **Enable rules for "vSAN" storage** |
| vSAN → Availability | 先關掉 **vSAN ESA Auto-RAID (9.1 onwards)**（這套是 OSA）→ Site disaster tolerance *None - standard cluster*、Failures to tolerate **No data redundancy** |
| vSAN → Advanced Policy Rules | **Force provisioning** 打開 |
| Storage compatibility | `vcf-m06-cl01-ds-vsan01` 相容 |

![](img/09-policy-list.png)
![](img/10-policy-name.png)
![](img/11-policy-structure.png)
![](img/12-policy-vsan-availability.png)
![](img/13-policy-vsan-advanced-force.png)
![](img/14-policy-storage-compat.png)
![](img/15-policy-review.png)
![](img/16-policy-created.png)

### 3-5 Port group 安全性（nested 限定）

Supervisor control plane VM 接在 `SDDC-DPortGroup-VM-Mgmt`。nested 環境要把 **Promiscuous mode / MAC address changes / Forged transmits** 改成 **Accept**（Networking → port group → Configure → Policies → EDIT... → Security）。

![](img/17-pg-policies-before.png)
![](img/18-pg-security-accept.png)
![](img/19-pg-policies-after.png)

### 3-6 確認 VLAN 6 到得了閘道、但出不了網際網路

臨時 port group + vmk 測試，測完就刪：

1. VDS `vcf-m06-cl01-vds01` → ACTIONS → **New Distributed Port Group**：`tmp-vlan6-test`、VLAN **6**

   ![](img/20-vds-new-pg-menu.png)
   ![](img/21-tmp-pg-vlan6.png)

2. `vcf-m06-esx03` → Configure → VMkernel adapters → **ADD NETWORKING** → VMkernel Network Adapter → `tmp-vlan6-test` → 服務都不勾 → Static `192.168.16.240/24`

   ![](img/22-vmk-target-tmp-pg.png)
   ![](img/23-vmk-ipv4.png)
   ![](img/24-vmk-ready.png)
   ![](img/25-vmk-added.png)

3. 從新的 vmk ping 閘道（[`cli/00-vlan6-ping.txt`](cli/00-vlan6-ping.txt)）。bring-up 後 nested ESX 的 SSH 是關的，所以用 PowerCLI `Get-EsxCli -V2` 透過 vCenter 執行同一個 esxcli：

   ```text
   esxcli network diag ping -H 192.168.16.254 -I vmk3 -c 3
   Transmitted : 3   Received : 3   PacketLost : 0
   ```

4. 移除 vmk3（VMkernel adapters → ⋮ → **Remove**），再刪掉 `tmp-vlan6-test`（ACTIONS → **Delete**）

   ![](img/26-vmk-remove.png)

VLAN 6 本身出不了網際網路（[`cli/00-vlan6-no-internet.txt`](cli/00-vlan6-no-internet.txt)：閘道以 192.168.16.254 為來源 ping 8.8.8.8 全部逾時；以管理網段位址為來源則通）。

### 3-7 DNS

VNA 節點 `vcf-m06-vna01a.home.lab` ↔ 10.0.1.209（A + PTR，[`cli/00-dns-vna.txt`](cli/00-dns-vna.txt)）；Harbor `harbor01.home.lab` ↔ 10.0.0.86。

## 步驟 4：Transit Gateway + VNA（UI）

Networking → **Virtual Private Clouds → Transit Gateways**。bring-up 已建立 **Default Transit Gateway**，Connection 還是 None → **SETUP NETWORK CONNECTIVITY**：

| 頁 | 設定 |
|---|---|
| 1 Transit Gateway Connectivity | VLAN-backed 只有 **Distributed VLAN Connection**；NEXT 時的 *Networking Prerequisites* 勾 Select All → CONTINUE |
| 2 External Network Connectivity | VLAN ID **6**；Gateway CIDR **`192.168.16.254/24`**（閘道 IP，輸入後按 Enter）；External IP Blocks → **Create New** `vks-block` = `192.168.16.0/24`，排除 `192.168.16.240-192.168.16.254` |
| 3 VPC Services | VNA cluster `vks-vna`，Form Factor **Large**；ADD 節點 `vcf-m06-vna01a.home.lab`、cluster `vcf-m06-cl01`、vSAN、Static `10.0.1.209/23`、gw 10.0.0.1、port group `SDDC-DPortGroup-VM-Mgmt` |
| 4 Review and Deploy | DEPLOY |

![](img/30-transit-gateways.png)
![](img/31-setup-p1-distributed-vlan.png)
![](img/32-setup-prereq.png)
![](img/33-ipblock-vks-block.png)
![](img/34-setup-p2-external.png)
![](img/35-vna-add-node.png)
![](img/36-vna-cluster-large.png)
![](img/37-setup-review.png)
![](img/38-setup-deploying.png)

VNA 變成 `NODE_READY` 後，Transit Gateway 狀態 **Success**（Connection = Distributed VLAN、External Connection = `Distributed-vlan-connection-6`）：

![](img/39-tgw-success.png)

> 🔑 **VPC 和 VNA 完全不需要 VCFMS。** Transit Gateway、External IP Block、VNA 都是 NSX 的功能，透過 vCenter 的 NSX 外掛操作。

## 步驟 5：VKr — Local Content Library + 匯入本機檔案（UI）

**Content Libraries → CREATE**：`vkr-local` → **Local content library**（不開 publishing）→ 不套 security policy → vSAN。

![](img/40-cl-1-name.png)
![](img/41-cl-2-local.png)
![](img/42-cl-3-security.png)
![](img/43-cl-4-storage.png)
![](img/44-cl-5-ready.png)

`vkr-local` → **ACTIONS → Import item** → **Local file** → **UPLOAD FILES** 一次選 4 個檔案（`.ovf`、`-disk1.vmdk`、`.mf`、`.cert`）→ Item name `ob-25650988-photon-5-amd64-v1.36.2---vmware.2-vkr.3` → IMPORT。

![](img/45-cl-actions-import.png)
![](img/46-cl-import-local-files.png)

上傳約 10 分鐘（和 VNA 部署同時進行），完成後 1 個 OVF template，11.79 GB：

![](img/47-cl-vkr-imported.png)

## 步驟 6：啟用 Supervisor（UI）

**Supervisor Management → GET STARTED**：

| 精靈頁 | 設定 |
|---|---|
| 1 vCenter Server and Network | **VCF Networking with VPC (recommended)** |
| 2 Supervisor location | **CLUSTER DEPLOYMENT**：`vcf-m06-sv01`、`vcf-m06-cl01`、zone `vz-01` |
| 3 Storage | Control Plane / Ephemeral Disks / Image Cache 都選 `vks-ftt0` |
| 4 Management Network | Static、`SDDC-DPortGroup-VM-Mgmt`、10.0.1.222-10.0.1.226、255.255.254.0、gw 10.0.0.1、DNS 10.0.0.200、search domain home.lab、NTP 10.0.1.254 |
| 5 Workload Network | NSX Project Default、VPC Connectivity Profile Default、External IP Blocks 自動帶出 `vks-block`；DNS 10.0.0.200、NTP 10.0.1.254 |
| 6 Advanced Settings | Control Plane **Small** |

![](img/50-supervisor-mgmt-home.png)
![](img/51-sv-1-network.png)
![](img/52-sv-2-location.png)
![](img/53-sv-3-storage.png)
![](img/54-sv-4-mgmt-network.png)
![](img/55-sv-5-workload.png)
![](img/56-sv-6-advanced.png)
![](img/57-sv-7-ready.png)
![](img/58-sv-configuring.png)

**25 分鐘**（14:57 → 15:22）變成 **Running**，API VIP **192.168.16.5**（kubernetes_status 中途 ERROR → WARNING → READY 跳動屬正常）：

![](img/59-sv-running.png)

> 🔑 **Supervisor 也不需要 VCFMS**：9.1.1 用 vCenter 內建的 Supervisor 映像，不需要另外準備 content library。

## 步驟 7：讓 Supervisor 和 VKS 信任 Harbor（UI）

**Supervisor → Configure → Container Registries → ADD REGISTRY**：Registry Name `harbor01`、Registry host URL `harbor01.home.lab`、TLS Certificate 貼 Harbor 的 **CA 憑證**、帳密留空（`vks-apps` 是 public project）、不勾 default。

![](img/60-sv-container-registries.png)
![](img/61-sv-add-registry.png)
![](img/62-sv-registry-added.png)

Supervisor 建立 `ClusterRegistryConfig`（[`cli/03-cluster-registry-config.txt`](cli/03-cluster-registry-config.txt)），Supervisor Services、Pods、VKS 叢集都會套用，叢集 YAML 不用另外設 `trust`。

## 步驟 8：Kubernetes Service library + Namespace（UI）

**Supervisor → Configure → General → Kubernetes Service → ADD** → 勾 `vkr-local` → ADD：

![](img/63-sv-k8s-service-library.png)
![](img/64-sv-add-library-local.png)
![](img/65-sv-library-added.png)

✅ 從本機匯入的 VKr 自動產生 KubernetesRelease（[`cli/02-kr.txt`](cli/02-kr.txt)）：

```text
NAME                       VERSION                  READY   COMPATIBLE
v1.36.2---vmware.2-vkr.3   v1.36.2+vmware.2-vkr.3   True    True
```

**Namespaces → NEW NAMESPACE**：Supervisor `vcf-m06-sv01` → Name `vks-lab` → zone `vz-01` → FINISH。再到 namespace Summary：**ADD STORAGE** `vks-ftt0`、**ADD VM CLASS** `best-effort-xsmall` / `small` / `medium`。

![](img/66-ns-1-location.png)
![](img/67-ns-2-config.png)
![](img/68-ns-3-zone.png)
![](img/69-ns-4-review.png)
![](img/70-ns-add-storage.png)
![](img/71-ns-add-vmclass.png)
![](img/72-ns-summary-ready.png)

## 步驟 9：Public SubnetSet（UI）

Namespace → **Resources**（LCI）→ Network → **GO TO SERVICE** → **SubnetSets → NEW SUBNETSET**：`public` / Access Mode **Public** / 16 IPs / DHCP None → CREATE（[`cli/04-subnetset.txt`](cli/04-subnetset.txt)）。

![](img/80-lci-network-service.png)
![](img/81-lci-new-subnetset.png)
![](img/82-lci-subnetset-created.png)

## 步驟 10：VKS 叢集（UI，Custom Configuration）

Resources（LCI）→ Kubernetes → **CREATE CLUSTER** → **Custom Configuration**：

| 精靈頁 | 設定 |
|---|---|
| General | Name `vks-cl01`、ClusterClass `builtin-generic-v3.7.0`、Kubernetes release v1.36.2、VM class `best-effort-medium`、storage `vks-ftt0` |
| Node Network | **Use custom primary network** → `public (Subnet Set)` |
| Control Plane | 1 台、Photon |
| Node Pools | node pool 改名 `vks-cl01-np-1`，Overrides 的 VM class 改 `best-effort-small` |

![](img/83-vks-wizard-1-custom.png)
![](img/84-vks-wizard-2-general.png)
![](img/85-vks-wizard-2-network.png)
![](img/86-vks-wizard-3-cp.png)
![](img/87-vks-nodepool-vmclass-small.png)
![](img/88-vks-nodepool-review.png)
![](img/89-vks-wizard-4-nodepools.png)
![](img/90-vks-wizard-5-review.png)

精靈產生的 YAML（[`vks-cl01.yaml`](vks-cl01.yaml)）和有 VCFMS 的 m05 完全相同，**沒有任何和 registry 有關的設定**。

> ℹ️ `builtin-generic-v3.7.0` 在 `vmware-system-vks-public` namespace（`kubectl get clusterclass -A`）。namespace 自己只會複製到 v3.3.0，查 `networks` 變數要看對 namespace。這次 Supervisor Running 後約 45 分鐘才送出，`networks` 變數早就在了，沒有遇到 `variables[networks] not defined`。

約 **5 分鐘**（16:08 → 16:13）變成 **Available**，CP 192.168.16.50、worker 192.168.16.51：

![](img/91-vks-cluster-creating.png)
![](img/92-vks-cluster-available.png)
![](img/93-vks-cluster-detail.png)

## 步驟 11：驗證（CLI）

```bash
kubectl vsphere login --server=192.168.16.5 -u administrator@vsphere.local --insecure-skip-tls-verify \
  --tanzu-kubernetes-cluster-namespace vks-lab --tanzu-kubernetes-cluster-name vks-cl01
kubectl config use-context vks-cl01
```

兩個節點 Ready（[`cli/05-guest-nodes.txt`](cli/05-guest-nodes.txt)）。從 Harbor 部署 nginx（[`nginx-harbor.yaml`](nginx-harbor.yaml)，[`cli/06-nginx-from-harbor.txt`](cli/06-nginx-from-harbor.txt)）：

```text
$ kubectl -n demo get pods
nginx-5658995685-7t5q2   1/1   Running
nginx-5658995685-q9sxd   1/1   Running
Successfully pulled image "harbor01.home.lab/vks-apps/nginx-unprivileged:1.30.4-alpine"

$ kubectl -n demo get svc nginx-lb
nginx-lb   LoadBalancer   10.102.54.20   192.168.16.33   80:32411/TCP

$ curl -s http://192.168.16.33/ | grep title      # 從管理網段執行
<title>Welcome to nginx!</title>
```

沒有出現 `x509: certificate signed by unknown authority`：Harbor CA 已經透過 Container Registries 下發到節點。LoadBalancer VIP 由 VNA 從 `vks-block` 配發。

**反向測試**（[`pull-test.yaml`](pull-test.yaml)，[`cli/07-pull-test.txt`](cli/07-pull-test.txt)）：同一個 busybox，分別從 Docker Hub 和 Harbor 拉：

```text
NAME             READY   STATUS
from-dockerhub   0/1     ImagePullBackOff    ← Head "https://registry-1.docker.io/v2/..." dial tcp ...:443: i/o timeout
from-harbor      0/1     Completed           ← hello-from-harbor，並且 wget 到 nginx-lb
```

Harbor UI 上兩個 repository 的 Pulls 都從 2 增加到 3：

![](img/95-harbor-pulls.png)

## 時間

| 階段 | 時間 |
|---|---|
| nested ESX ×3 部署 | 3 分鐘 |
| Installer 精靈 + 驗證 | 約 35 分鐘（驗證 15 項約 5 分鐘） |
| bring-up：vCenter → SDDC Manager → vSphere cluster → NSX | 2 小時 14 分鐘（11:54 → 14:08） |
| 中止 + 確認 | 2 分鐘（另外觀察 30 分鐘沒有重送） |
| 前置準備（步驟 3） | 約 20 分鐘 |
| Transit Gateway + VNA | 約 6 分鐘（和 VKr 上傳同時） |
| VKr 上傳 | 約 10 分鐘 |
| Supervisor | 25 分鐘 |
| VKS 叢集 | 5 分鐘 |

## 遇到的問題

| # | 症狀 | 原因 / 處理 |
|---|---|---|
| 1 | Installer 剛開機登入後跳 *Service Interruption — Multiple services are currently down* | Installer 服務還在啟動，等幾分鐘再 RELOAD |
| 2 | 驗證出現 *Insufficient Storage. 5400 GB storage is less than the required 6748 GB* | UI 精靈的 vSAN FTT 固定為 1，而且需求含 VCFMS 的 2900 GB。這次不部署 VCFMS，所以 ACKNOWLEDGE 即可（nested ESX 的 capacity 碟先線上擴到 3600 GB） |
| 3 | 中止後 SDDC Manager 的 `VSP_BOOTSTRAP` 任務從 Pending 變成 Failed | `domainmanager` 重啟後曾接手，但 *Bootstrap VCF Services Platform* 失敗，沒有建立任何 VM；之後 30 分鐘沒有重送。**不要**在 Installer 按 RETRY |
| 4 | Storage policy 的 K8s Compliant Name 沒有自動帶出 | 自己填 `vks-ftt0`（Supervisor 精靈會用到這個名稱） |
| 5 | 要從 vmk ping VLAN 6 閘道，但 nested ESX 的 SSH 連不上 | bring-up 後 SSH 是關的；用 PowerCLI `Get-EsxCli -V2` 透過 vCenter 執行 `esxcli network diag ping`，不必開 SSH |
| 6 | `kubectl -n vks-lab get clusterclass` 只看到 v3.1.0-v3.3.0 | v3.4.0-v3.7.0 在 `vmware-system-vks-public` namespace；叢集 YAML 的 `classRef.namespace` 本來就指向那裡 |

## 和其他文件的差異

| 項目 | 本 repo 主文件（alan.lab） | [`vpc-airgap`](../vpc-airgap/README.md)（m05） | 這份（m06） |
|---|---|---|---|
| VCFMS | ❌ 不部署（API bring-up 後中止） | ✅ 有 | ❌ 不部署（**UI 精靈** bring-up 後中止） |
| Supervisor 網路 | VDS + Foundation LB | VLAN-backed VPC + VNA | VLAN-backed VPC + VNA |
| VKr | content library | Local library 匯入 | Local library 匯入 |
| 信任 Harbor CA | `osConfiguration.trust` | Container Registries | Container Registries |
| addon 套件庫改指 Harbor | 有 | 沒有涵蓋 | 沒有涵蓋 |
| Supervisor / VKS 時間 | — | 50 分 / 15 分 | 25 分 / 5 分 |

**結論：VLAN-backed VPC 的 Supervisor 和 VKS 不依賴 VCFMS。** bring-up 只要完成 vCenter、SDDC Manager、vSAN、NSX 四個 milestone，之後 Transit Gateway、VNA、Supervisor、VKS、Harbor 信任都可以全部在 vSphere Client UI 完成，air-gap 下也能運作。


