# VKS UI Step by Step（m05，vSphere Client UI 版）

在另一套 nested lab（m05，`home.lab`，VCF 9.1.1，用 VCF Installer「Deploy a new VCF Instance」部署）把 VKS 從頭做了四次：VPC / 非 VPC 各一次，每種再做一次 air-gap。
**vSphere 的操作全部用 UI 並逐步截圖**（Supervisor 精靈、Content Library、Namespace、Container Registries、VKS 叢集精靈），CLI 只用在驗證。每份都附 Word 版（docx）。

| Supervisor 網路 | 一般 | air-gap |
|---|---|---|
| **VPC**：VCF Networking with VPC（VLAN-backed VPC，NSX + VNA） | [`vpc/`](vpc/README.md)（[docx](vpc/VKS-VLAN-backed-VPC-UI-Step-by-Step.docx)） | [`vpc-airgap/`](vpc-airgap/README.md)（[docx](vpc-airgap/VKS-VLAN-backed-VPC-Airgap-UI-Step-by-Step.docx)） |
| **非 VPC**：VDS + Foundation Load Balancer | [`vds-flb/`](vds-flb/README.md)（[docx](vds-flb/VKS-VDS-FLB-UI-Step-by-Step.docx)） | [`vds-flb-airgap/`](vds-flb-airgap/README.md)（[docx](vds-flb-airgap/VKS-VDS-FLB-Airgap-UI-Step-by-Step.docx)） |

## 四份的差異

| | VPC | VPC air-gap | VDS + FLB | VDS + FLB air-gap |
|---|---|---|---|---|
| 網路 / LB | NSX VPC + VNA | NSX VPC + VNA | VDS + FLB | VDS + FLB |
| 叢集網路 | SubnetSet `public`（ClusterClass 有 `networks` 變數） | SubnetSet `public` | namespace 預設網路（沒有 `networks` 變數） | namespace 預設網路 |
| VKr | 訂閱內部 depot | Local Content Library 匯入本機檔案 | 訂閱內部 depot | Local Content Library 匯入本機檔案 |
| 應用 image | —（CoreDNS LB 測試） | 內部 Harbor | —（CoreDNS LB 測試） | 內部 Harbor |
| 信任內部 CA | — | Supervisor → Configure → Container Registries | — | Supervisor → Configure → Container Registries |
| Supervisor 時間 | 30 分 | 50 分 | 41 分 | 35 分 |

## 和本 repo 主文件（alan.lab）的差異

| 項目 | 主文件（[docs/](../docs)） | UI step-by-step（m05） |
|---|---|---|
| 環境 | alan.lab，bring-up 中止、不部署 VCFMS | home.lab，**m05 有部署 VCFMS**（`vcf-m05-vsp01`），不是 no-VCFMS 環境；文件裡的 VKS 步驟沒有用到 VCFMS |
| 操作方式 | 程序 + 腳本 | vSphere Client UI，逐步截圖 |
| Supervisor | VDS + FLB | VPC 和 VDS + FLB 兩種 |
| VKS 信任 Harbor CA | `osConfiguration.trust`（叢集 YAML） | Supervisor 的 **Container Registries**（UI，產生 `ClusterRegistryConfig`，叢集 YAML 不用改） |
| VKr | content library | Local Content Library → **Import item** 匯入本機 `.ovf/.vmdk/.mf/.cert`，KR 自動產生 |
| air-gap 範圍 | DNS 層級 | workload VLAN 本身沒有對外路由，Harbor VM 用 iptables 擋對外；管理網段沒擋 |
| addon 套件庫改指 Harbor | 有（流程摘要第 6 點） | **沒有涵蓋**，需要時請照主文件做 |

## 共同的坑

- vSphere Client 語言是**繁體中文時，Resources（LCI）外掛整頁空白** → 右上角 My Preferences → Language 改 English。
- VKS 叢集精靈建出來報 `variables[networks] not defined`（VPC 版）：Supervisor 剛 RUNNING 時 ClusterClass 還沒有 `networks` 變數，等 15–20 分鐘 CAPI 重新同步後再按 FINISH。
- FLB 精靈：HA 選項 `1` = SINGLE_NODE、`2` = ACTIVE_PASSIVE；FLB 的 Management Network 要另外命名（不能和 Supervisor 管理網路同名）且要 **2 個 IP**。
- workload port group 名稱要用小寫（RFC 1123）。
