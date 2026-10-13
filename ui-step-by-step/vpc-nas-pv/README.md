# VKS on VLAN-backed VPC — 外掛 NAS（NFS）做 PV，走另一條線（m06，2026-10-13）

> 📄 Word 版：[`VKS-VPC-NAS-PV-Step-by-Step.docx`](VKS-VPC-NAS-PV-Step-by-Step.docx)

在 [`vpc-airgap-novcfms`](../vpc-airgap-novcfms/README.md)（m06：VLAN-backed VPC、air-gap、不部署 VCFMS）的環境上，加一台 NAS（NFS），讓 VKS 用它做 PersistentVolume。**NAS 的流量走獨立的 VLAN 7，不經過 VKS 的 public subnet（VLAN 6）**。兩種做法都做了、都驗證過：

| | 做法 1：ESXi 掛 NFS datastore（vSphere CSI） | 做法 2：VKS 節點加 eth1 直接掛 NAS（NFS CSI） |
|---|---|---|
| PV 的樣子 | NAS 上的一顆 VMDK（First Class Disk） | NAS 上的一個子目錄 |
| Access mode | RWO | **RWX**（多個 Pod / 多個節點同時讀寫） |
| NAS 流量 | ESXi 的 vmk3（VLAN 7） | VKS 節點的 eth1（VLAN 7） |
| 要裝的東西 | 無（VKS 內建 vSphere CSI） | guest 裡裝 NFS CSI driver（6 個 image，air-gap 要先推進 Harbor） |
| NSX 設定 | 無 | Distributed VLAN Connection（Dedicated to Subnet）+ VLAN 延伸 Subnet |
| 誰管 | vSphere 管理員（datastore、storage policy） | vSphere 管理員（網路）+ K8s 管理員（CSI、StorageClass） |
| 適合 | 一般 PV、要用 vSphere 的 CNS 管理 | 需要 RWX、或應用本來就要直接掛 NFS |

所有 vSphere / NSX / Harbor 的設定都用 UI 截圖；NAS 主機的安裝、搬 image、Kubernetes 內的部署與驗證用 CLI。**只有一個步驟 UI 做不到**：VLAN 延伸 Subnet 要開 NSX 的 static IP allocation，NSX UI 沒有這個選項，用 API 建（步驟 2-3）。

## 網路

| 網段 | 用途 | IP |
|---|---|---|
| VLAN 6，192.168.16.0/24 | VKS public subnet（eth0）、LoadBalancer VIP | Supervisor / VKS 節點 / VIP |
| **VLAN 7，192.168.17.0/24** | **NAS 專用** | NAS `nfs-vks01` .20；ESXi vmk3 .21-.23；VKS 節點 eth1 .64 起（NSX 配）；閘道 .254（上游，沒有 NAT） |

VLAN 7 和 VLAN 6 一樣出不了網際網路；NAS 本身也只開放 192.168.17.0/24。

## 步驟 0：NAS（NFS VM，air-gap 離線安裝，CLI）

Lab 用一台 Ubuntu 22.04 VM 模擬 NAS，接在外層的 `VLAN7` port group（正式環境就是你的 NAS 設備，只要在 VLAN 7 上 export NFS 即可）。

```powershell
# 外層 vCenter：Ubuntu 22.04 cloud image OVA → cloud-init 設靜態 IP 192.168.17.20/24、gw .254
$env:VIPASS='...'; $env:NFSPASS='...'
.\Deploy-VksNfsVm.ps1
```

```bash
# NFS VM 上（沒有網路）：離線安裝 nfs-kernel-server、建 export
#   bundle 是 jammy 的 102 個 deb；只裝「沒裝或比較新」的 10 個，不會把系統的 libc6 / dpkg 降版
tar -xzf nfs-offline-bundle-jammy.tar.gz && sudo ./install-vks-nfs.sh 192.168.17.0/24
```

結果（[`cli/10-nfs-server.txt`](cli/10-nfs-server.txt)）：

```text
/export/vks-ds   192.168.17.0/24(rw,sync,no_subtree_check,no_root_squash)   ← 做法 1：ESXi NFS datastore
/export/vks-rwx  192.168.17.0/24(rw,sync,no_subtree_check,no_root_squash)   ← 做法 2：NFS CSI
no internet（VLAN 7 沒有 NAT）
```

`no_root_squash`：ESXi 的 NFS 3 和 NFS CSI driver 都以 root 建立檔案 / 子目錄。腳本：[`scripts/Deploy-VksNfsVm.ps1`](scripts/Deploy-VksNfsVm.ps1)、[`scripts/install-vks-nfs.sh`](scripts/install-vks-nfs.sh)。

---

## 做法 1：ESXi 掛 NFS datastore → vSphere CSI

### 1-1 Port group `nas-vlan7`（UI）

VDS `vcf-m06-cl01-vds01` → ACTIONS → **New Distributed Port Group**：`nas-vlan7`、VLAN **7**。

![](img/01-pg-name.png)
![](img/02-pg-vlan7.png)

### 1-2 每台主機加 NFS 專用的 vmk3（UI）

主機 → Configure → VMkernel adapters → **ADD NETWORKING** → VMkernel Network Adapter → `nas-vlan7` → MTU **Custom 1500**（和 NAS 一致）、服務都不勾 → Static `192.168.17.21`（esx02 .22、esx03 .23）/ 255.255.255.0。三台都做。

![](img/10-vmk-list.png)
![](img/11-vmk-target.png)
![](img/12-vmk-port-props.png)
![](img/13-vmk-ipv4.png)
![](img/14-vmk-ready.png)
![](img/15-vmk-added.png)

三台都 ping 得到 NAS（[`cli/11-esx-vmk3-ping.txt`](cli/11-esx-vmk3-ping.txt)，用 PowerCLI `Get-EsxCli -V2` 執行 `esxcli network diag ping -I vmk3`）。

### 1-3 NFS datastore `nas-vks-ds`（UI）

Cluster → ACTIONS → **New Datastore** → **NFS** → **NFS 3** → Name `nas-vks-ds`、Folder `/export/vks-ds`、Server `192.168.17.20`、勾 **Vmknic binding**（把 NFS 流量綁在 vmk3）→ 三台主機都勾 → Vmknic bindings 選 **vmk3**（All hosts）。

![](img/20-cluster-actions-new-datastore.png)
![](img/21-ds-1-type-nfs.png)
![](img/22-ds-2-nfs3.png)
![](img/23-ds-3-name-config.png)
![](img/24-ds-4-hosts.png)
![](img/25-ds-5-vmknic-vmk3.png)
![](img/26-ds-6-ready.png)
![](img/27-ds-summary.png)

NAS 上看得到三台 ESXi 都從 **vmk3（.21-.23）** 連進來（[`cli/12-nas-connections-esx.txt`](cli/12-nas-connections-esx.txt)）。

### 1-4 Tag（UI）

**Tags & Custom Attributes → NEW**：Tag `nas` → **Create New Category** `vks-storage`（One tag、只關聯 **Datastore**）。再到 datastore `nas-vks-ds` → ACTIONS → **Assign Tag** → `nas`。

![](img/30-tags-home.png)
![](img/31-tag-new-category.png)
![](img/32-tag-create-nas.png)
![](img/33-tag-created.png)
![](img/34-ds-assign-tag.png)
![](img/35-ds-tag-assigned.png)

### 1-5 Storage policy `vks-nas`（UI）

**VM Storage Policies → CREATE**：Name / K8s Compliant Name `vks-nas` → 勾 **Enable tag based placement rules** → Tag category `vks-storage`、Use storage tagged with `nas` → 相容的只有 `nas-vks-ds`。

![](img/40-policy-name.png)
![](img/41-policy-structure-tag.png)
![](img/42-policy-tag-rule.png)
![](img/43-policy-storage-compat.png)
![](img/44-policy-review.png)

### 1-6 加到 Namespace（UI）

Namespace `vks-lab` → Summary → Storage → **EDIT STORAGE** → 勾 `vks-nas`。

![](img/45-ns-edit-storage-nas.png)
![](img/46-ns-storage-two-policies.png)

VKS 叢集會自動出現 StorageClass `vks-nas` / `vks-nas-latebinding`。

### 1-7 驗證

[`pvc-nas-rwo.yaml`](pvc-nas-rwo.yaml)：PVC `storageClassName: vks-nas` + 一個寫檔的 Pod（[`cli/13-pvc-nas-rwo.txt`](cli/13-pvc-nas-rwo.txt)）：

```text
persistentvolumeclaim/data-on-nas   Bound   pvc-cddec61c-...   2Gi   RWO   vks-nas
/dev/sdb   1.9G   540.0K   1.8G   0% /data
hello from NAS PV Tue Oct 13 11:01:58 UTC 2026
```

PV 就是 NAS 上 `/export/vks-ds/fcd/` 的一顆 VMDK（[`cli/14-nas-fcd-files.txt`](cli/14-nas-fcd-files.txt)），在 vSphere 的 **Cloud Native Storage → Container Volumes** 看得到它放在 `nas-vks-ds`：

![](img/47-cns-container-volume-on-nas.png)

---

## 做法 2：VKS 節點加 eth1（VLAN 7）→ NFS CSI，RWX

### 2-1 NSX External Connection `nas-vlan7`（NSX UI）

NSX Manager → Networking → **External Connections → ADD EXTERNAL CONNECTION**：

| 欄位 | 值 |
|---|---|
| Name | `nas-vlan7` |
| Type | **Distributed VLAN Connection**，打開 **Dedicated to Subnet**（"extends at layer 2 this VLAN and its CIDR block to a single VPC subnet"） |
| Subnet Extension Connection | **Layer 2** |
| VLAN ID | 7 |
| Gateway CIDR IPv4 Address | `192.168.17.254/24`（上游閘道，要和實體路由器一致） |
| VLAN/Subnet Block | `nas-vlan7-block`（由 Gateway CIDR 推出 192.168.17.0/24） |

![](img/50-nsx-external-connections.png)
![](img/51-nsx-add-dvc-nas-vlan7.png)
![](img/52-nsx-external-connections-two.png)

> ⚠️ **不要**把它加到 Transit Gateway 的 External Connection：會報 *"subnet extension connection mode as ENABLED_L2 cannot be used for attachment"*。Dedicated 的連線是直接給 Subnet 用的。

### 2-2 IP block 排除已經在用的 IP（NSX UI）

Networking → IP Address Pools → **IP Address Blocks** → `nas-vlan7-block` → Edit → Excluded IP Ranges `192.168.17.1-192.168.17.63`（NAS .20、ESXi vmk3 .21-.23 都在這段）。NSX 配給節點 eth1 的 IP 就會從 .64 開始。

![](img/53-nsx-ipblock-exclude.png)
![](img/54-nsx-ipblock-excluded.png)

### 2-3 VLAN 延伸 Subnet（NSX API）

在 namespace 的 VPC（`vks-lab_tug8x`）建一個 Subnet，`vlan_connection` 指到 `nas-vlan7`，並且**打開 static IP allocation**（VKS 節點的 eth1 要靠它拿 IP）：

```bash
curl -k -u "admin:$NSX_PASS" -X PATCH -H 'Content-Type: application/json' \
  https://vcf-m06-nsx01.home.lab/policy/api/v1/orgs/default/projects/default/vpcs/vks-lab_tug8x/subnets/nas-vlan7-sn \
  -d @nsx-subnet-nas-vlan7.json
```

[`nsx-subnet-nas-vlan7.json`](nsx-subnet-nas-vlan7.json)：`access_mode: Public`、`vlan_connection: /infra/distributed-vlan-connections/nas-vlan7`、`ip_addresses: 192.168.17.0/24`、`static_ip_allocation.enabled: true`、`connectivity_state: DISCONNECTED`（Layer 2 延伸的 Subnet 不能接 VPC gateway）、DHCP 關閉。

> 為什麼不用 UI：NSX UI 的 VPCs → Subnets → ADD SUBNET 可以建 VLAN 延伸 Subnet（VLAN Extension = Yes、Access Mode 選 **Public** 才列得出 `nas-vlan7`），但**沒有 IP 配置選項**，建出來的 Subnet 沒開 static IP allocation，VKS 節點的 eth1 只會有 link-local；這個設定建好之後也改不了。

建好後 NSX UI 的 Subnets 清單：

![](img/64-nsx-subnet-created.png)

### 2-4 把 Subnet 分享給 Namespace（vCenter UI）

Namespace `vks-lab` → **Configure → General → Namespace Networks → ADD**：NSX Project Default、VPC `vks-lab_tug8x`、Subnet `nas-vlan7-subnet`（要打字搜尋才會列出）、Subnet CR Name `nas-vlan7`、Usage 兩個都不勾。

![](img/60-ns-configure-namespace-networks.png)
![](img/65-ns-add-network-nas-subnet.png)
![](img/66-ns-namespace-networks-added.png)

Supervisor 會在 namespace 裡建立 `Subnet` CR `nas-vlan7`（`shared: true`、VLAN 7）；Resources → Network → Subnets 也看得到：

![](img/67-lci-subnets-shared-nas-vlan7.png)

> 直接用 `kubectl apply` 建帶 `vlanConnectionName` 的 Subnet 會被擋：*"spec.vlanConnectionName can only be set by NSX Operator"*。一定要先在 NSX 建、再從 vCenter 分享進來。

### 2-5 VKS 叢集 `vks-cl02`，加 eth1（UI）

Resources → Kubernetes → **CREATE CLUSTER** → Custom Configuration，和 `vks-cl01` 相同，只多一步：Network → Node Network → **ADD ADDITIONAL NETWORK** → `Additional | eth1` 的 Network 選 **`nas-vlan7 (Subnet)`**。

![](img/73-vks-wizard-1-custom.png)
![](img/74-vks-wizard-2-general.png)
![](img/75-vks-wizard-2-network.png)
![](img/76-vks-wizard-2-eth1-nas-vlan7.png)
![](img/77-vks-wizard-3-cp.png)
![](img/78-vks-nodepool-vmclass-small.png)
![](img/79-vks-nodepool-review.png)
![](img/80-vks-wizard-4-nodepools.png)
![](img/81-vks-wizard-5-review.png)
![](img/82-vks-cluster-creating.png)
![](img/83-vks-cl02-detail.png)

產生的 YAML（[`vks-cl02.yaml`](vks-cl02.yaml)）多了：

```yaml
      - name: networks
        value:
          interfaces:
            primary:   {network: {name: public,    kind: SubnetSet, apiVersion: crd.nsx.vmware.com/v1alpha1}}
            secondary:
              - name: eth1
                network: {name: nas-vlan7, kind: Subnet, apiVersion: crd.nsx.vmware.com/v1alpha1}
```

約 7 分鐘 Available。每個節點兩張網卡，eth1 的 IP 由 NSX 配（[`cli/21-vks-cl02-eth1.txt`](cli/21-vks-cl02-eth1.txt)）：

```text
vks-cl02-2lnqd-qsppm                       eth0 192.168.16.52   eth1 192.168.17.64
vks-cl02-vks-cl02-np-1-...-8sw7s           eth0 192.168.16.53   eth1 192.168.17.65
```

節點裡到 NAS 的路由直接走 eth1、不經過閘道（[`cli/23-node-eth1-route.txt`](cli/23-node-eth1-route.txt)）：

```text
$ ip route get 192.168.17.20
192.168.17.20 dev eth1  src 192.168.17.65
```

> 為了驗證跨節點 RWX，之後把 worker 從 1 台加到 2 台（`kubectl patch cluster vks-cl02 ... replicas: 2`），新節點的 eth1 拿到 .66。

### 2-6 NFS CSI driver（air-gap，CLI + Harbor UI）

用 [`csi-driver-nfs`](https://github.com/kubernetes-csi/csi-driver-nfs) **v4.13.4**。6 個 image 先在 staging 機抓成 tar（[`scripts/pull-image-tar2.py`](scripts/pull-image-tar2.py)，不需要 docker，支援 registry.k8s.io），在 Harbor 建 public project `csi`，再推進去：

![](img/90-harbor-new-project-csi.png)

```bash
# staging 機
python pull-image-tar2.py registry.k8s.io/sig-storage/nfsplugin:v4.13.4 nfsplugin.tar
#   csi-provisioner:v6.3.0、csi-resizer:v2.2.0、csi-snapshotter:v8.6.0、csi-node-driver-registrar:v2.17.0、livenessprobe:v2.19.0 同上
sha256sum *.tar > SHA256SUMS

# Harbor 主機
sha256sum -c SHA256SUMS
docker load -i nfsplugin.tar
docker tag registry.k8s.io/sig-storage/nfsplugin:v4.13.4 harbor01.home.lab/csi/nfsplugin:v4.13.4
docker push harbor01.home.lab/csi/nfsplugin:v4.13.4
```

官方 manifest 只改 image 位置（`registry.k8s.io/sig-storage/` → `harbor01.home.lab/csi/`），放在 [`nfs-csi/`](nfs-csi)：

```bash
kubectl apply -f rbac-csi-nfs.yaml -f csi-nfs-driverinfo.yaml -f csi-nfs-controller.yaml -f csi-nfs-node.yaml
```

推 image 的完整輸出：[`cli/20-harbor-push-csi.txt`](cli/20-harbor-push-csi.txt)。controller 和每個節點的 node pod 都 Running，image 都從 Harbor 拉（[`cli/22-nfs-csi-install.txt`](cli/22-nfs-csi-install.txt)）。

### 2-7 StorageClass + RWX 驗證

[`nfs-csi/storageclass-nas-nfs-rwx.yaml`](nfs-csi/storageclass-nas-nfs-rwx.yaml)：`server: 192.168.17.20`、`share: /export/vks-rwx`、`mountPermissions: "0777"`（讓 PSA restricted 的非 root Pod 能寫）、`nfsvers=4.1`。

[`nfs-csi/rwx-demo.yaml`](nfs-csi/rwx-demo.yaml)：一個 **ReadWriteMany** PVC，兩個 Pod 分散在兩台 worker，每 10 秒往同一個檔案寫一行（[`cli/24-rwx-demo.txt`](cli/24-rwx-demo.txt)）：

```text
shared-data   Bound   pvc-104bfa32-...   5Gi   RWX   nas-nfs-rwx

writer-...-8kx9k   Running   vks-cl02-...-nwfkj
writer-...-z2547   Running   vks-cl02-...-8sw7s

$ kubectl -n rwx-demo exec writer-...-8kx9k -- tail /data/shared.log
12:13:47 writer-...-z2547 on vks-cl02-...-8sw7s
12:13:49 writer-...-8kx9k on vks-cl02-...-nwfkj
```

NAS 上看連線來源（[`cli/25-nas-connections-vks.txt`](cli/25-nas-connections-vks.txt)）：

```text
192.168.17.21 / .22 / .23   ← ESXi vmk3（做法 1）
192.168.17.65 / .66         ← VKS worker 的 eth1（做法 2）
（沒有任何 192.168.16.x：NAS 流量完全沒經過 public subnet）
```

---

## 用 YAML 建節點和 Pod

前面的叢集是用 UI 精靈建的，精靈產生的就是下面這份 YAML，直接用 kubectl apply 也可以，結果相同。整個流程分兩層，**對象不同**：

1. **建節點（VKS 叢集）**：在 **Supervisor** 的 namespace `vks-lab` 套用 `Cluster` YAML。VKS 依照 YAML 建出節點 VM，`secondary` 那段會讓每個節點自動多一張 eth1。
2. **建 Pod**：登入 **guest cluster** `vks-cl02`，照一般方式套用 PVC + Pod。Pod 的 YAML 裡**不會出現 eth1**；NFS 由節點上的 CSI driver 掛載，節點的路由表自然從 eth1 出去。

### 建節點：Cluster YAML（在 Supervisor 套用）

[`vks-cl02.yaml`](vks-cl02.yaml)，重點欄位加了註解：

```yaml
apiVersion: cluster.x-k8s.io/v1beta2
kind: Cluster
metadata:
  name: vks-cl02
  namespace: vks-lab                       # vSphere Namespace
spec:
  clusterNetwork:
    pods:     {cidrBlocks: ["10.95.0.0/16"]}
    services: {cidrBlocks: ["10.96.0.0/12"]}
    serviceDomain: cluster.local
  topology:
    classRef:
      name: builtin-generic-v3.7.0
      namespace: vmware-system-vks-public  # ClusterClass 在這個 namespace
    version: v1.36.2---vmware.2-vkr.3      # KR（來自 vkr-local library）
    variables:
      - name: vmClass
        value: best-effort-medium
      - name: storageClass
        value: vks-ftt0                    # 節點自己的磁碟仍放 vSAN
      - name: networks
        value:
          interfaces:
            primary:                       # eth0：VLAN 6，public SubnetSet
              network: {name: public, kind: SubnetSet, apiVersion: crd.nsx.vmware.com/v1alpha1}
            secondary:                     # eth1：VLAN 7，分享進來的 nas-vlan7 Subnet
              - name: eth1
                network: {name: nas-vlan7, kind: Subnet, apiVersion: crd.nsx.vmware.com/v1alpha1}
    controlPlane:
      replicas: 1
      metadata:
        annotations:
          run.tanzu.vmware.com/resolve-os-image: os-name=photon
    workers:
      machineDeployments:
        - class: node-pool
          name: vks-cl02-np-1
          replicas: 2                      # worker 數量
          metadata:
            annotations:
              run.tanzu.vmware.com/resolve-os-image: os-name=photon
          variables:
            overrides:
              - name: vmClass
                value: best-effort-small
```

指令：

```bash
kubectl vsphere login --server=192.168.16.5 -u administrator@vsphere.local --insecure-skip-tls-verify
kubectl config use-context vks-lab
kubectl apply -f vks-cl02.yaml
kubectl -n vks-lab get cluster,machines
```

注意：

- 套用前 namespace 裡要已經有 Subnet `nas-vlan7`（步驟 2-1 到 2-4：NSX 建 + Namespace Networks 分享）；這個 Subnet 不能自己用 kubectl 建。
- 每個節點都會有 eth1，IP 由 NSX 自動配，YAML 裡不用寫任何 IP。
- 之後要加 worker，改 `replicas` 再 apply 一次；新節點一樣會有 eth1（這次加的第二台 worker 拿到 .66）。

### 建 Pod：PVC + Pod（在 guest cluster 套用）

先登入 guest cluster：

```bash
kubectl vsphere login --server=192.168.16.5 -u administrator@vsphere.local --insecure-skip-tls-verify \
  --tanzu-kubernetes-cluster-namespace vks-lab --tanzu-kubernetes-cluster-name vks-cl02
kubectl config use-context vks-cl02
```

**做法 1：RWO**（StorageClass `vks-nas` 由 storage policy 自動產生），[`pvc-nas-rwo.yaml`](pvc-nas-rwo.yaml)：

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: data-on-nas, namespace: nas-demo}
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: vks-nas           # = 加到 namespace 的 vks-nas storage policy
  resources: {requests: {storage: 2Gi}}
---
apiVersion: v1
kind: Pod
metadata: {name: writer, namespace: nas-demo}
spec:
  securityContext:                    # VKS 預設 PSA restricted
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000                     # 讓非 root 能寫這個 volume
    seccompProfile: {type: RuntimeDefault}
  containers:
  - name: c
    image: harbor01.home.lab/vks-apps/busybox:1.37.0
    command: ["sh", "-c", "echo hello >> /data/hello.txt; sleep 3600"]
    volumeMounts: [{name: data, mountPath: /data}]
    securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: ["ALL"]}}
  volumes:
  - name: data
    persistentVolumeClaim: {claimName: data-on-nas}
```

**做法 2：RWX**（要先裝好 csi-driver-nfs，步驟 2-6），[`nfs-csi/storageclass-nas-nfs-rwx.yaml`](nfs-csi/storageclass-nas-nfs-rwx.yaml) + [`nfs-csi/rwx-demo.yaml`](nfs-csi/rwx-demo.yaml)：

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata: {name: nas-nfs-rwx}
provisioner: nfs.csi.k8s.io
parameters:
  server: 192.168.17.20               # NAS，節點從 eth1（VLAN 7）直接到
  share: /export/vks-rwx
  mountPermissions: "0777"            # 讓非 root 的 Pod 能寫
mountOptions: ["nfsvers=4.1"]
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: shared-data, namespace: rwx-demo}
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: nas-nfs-rwx
  resources: {requests: {storage: 5Gi}}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: writer, namespace: rwx-demo}
spec:
  replicas: 2
  selector: {matchLabels: {app: writer}}
  template:
    metadata: {labels: {app: writer}}
    spec:
      topologySpreadConstraints:      # 兩個 Pod 盡量分到不同節點
      - {maxSkew: 1, topologyKey: kubernetes.io/hostname, whenUnsatisfiable: ScheduleAnyway, labelSelector: {matchLabels: {app: writer}}}
      securityContext: {runAsNonRoot: true, runAsUser: 1000, seccompProfile: {type: RuntimeDefault}}
      containers:
      - name: c
        image: harbor01.home.lab/vks-apps/busybox:1.37.0
        command: ["sh", "-c", "while true; do echo \"$(date) $HOSTNAME\" >> /data/shared.log; sleep 10; done"]
        volumeMounts: [{name: data, mountPath: /data}]
        securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: ["ALL"]}}
      volumes:
      - name: data
        persistentVolumeClaim: {claimName: shared-data}
```

（repo 裡的檔案還包含 `nas-demo`、`rwx-demo` 兩個 Namespace。）

```bash
kubectl apply -f pvc-nas-rwo.yaml
kubectl apply -f nfs-csi/storageclass-nas-nfs-rwx.yaml -f nfs-csi/rwx-demo.yaml
kubectl -n rwx-demo get pvc,pods -o wide
```

### 為什麼 Pod 不用指定 eth1

NFS 是**節點**上的 CSI node plugin（hostNetwork）掛的，不是 Pod 自己連。節點的路由表把 192.168.17.0/24 直接指向 eth1（`ip route get 192.168.17.20` → `dev eth1`），所以 NAS 流量自動走 VLAN 7；Pod 自己的流量仍然走 eth0 / Antrea 的 Pod 網路。只有當應用程式要在 Pod 裡**直接**連 VLAN 7（不是透過 PV），才需要另外設定 Antrea secondary network。

---

## 遇到的問題

| # | 症狀 | 原因 / 處理 |
|---|---|---|
| 1 | NSX ADD SUBNET 選 **L2 Only** 時，VLAN Connection 清單是 *No Items Found* | Access Mode 改 **Public** 就列得出 `nas-vlan7` |
| 2 | 用 NSX UI 建的 VLAN 延伸 Subnet，VKS 節點 eth1 只有 link-local、SubnetPort 沒有 IP | UI 不會開 static IP allocation，而且事後改不了（*"Static IP pool allocation ... cannot be modified after configuration"*）。刪掉重建，用 API 建並打開 `static_ip_allocation`（步驟 2-3）。刪掉的 path 要等最多 5 分鐘才能重用，所以換了 id `nas-vlan7-sn` |
| 3 | 把 `nas-vlan7` 加到 Transit Gateway 的 External Connection 存檔失敗 | *"ENABLED_L2 cannot be used for attachment"*：Dedicated to Subnet 的連線不接 TGW |
| 4 | `kubectl apply` 帶 `vlanConnectionName` 的 Subnet 被 webhook 擋 | 只有 NSX Operator 能設；改成 NSX 建 + vCenter **Namespace Networks → ADD** 分享 |
| 5 | vCenter Resources（LCI）的 NEW SUBNET 沒有 VLAN 延伸選項 | 同上，用 Namespace Networks 分享預先建好的 Subnet |
| 6 | VLAN 7 上已經有 NAS / ESXi 的 IP，怕 NSX 配到重複的 | 在 IP block 排除 .1-.63，NSX 從 .64 開始配 |
| 7 | 從 vmk ping NAS，nested ESX 的 SSH 連不上 | bring-up 後 SSH 是關的；用 PowerCLI `Get-EsxCli -V2` 透過 vCenter 執行 esxcli |

![](img/55-nsx-tgw-add-nas-vlan7.png)

## 結論

- **只要一般 PV（RWO）**：做法 1。完全在 vSphere 內設定，VKS 不用裝東西，NAS 流量只在 ESXi 的 vmk3 上。
- **要 RWX，或應用要直接掛 NFS**：做法 2。NSX 9.1 的 Distributed VLAN Connection（Dedicated to Subnet）+ VLAN 延伸 Subnet，可以讓 VKS 節點多一張直接在 NAS VLAN 上的網卡；IP 由 NSX 配，NAS 流量不經過 VPC / public subnet。
- 兩種做法都**不需要 VCFMS**，air-gap 下也能運作（NFS CSI 的 image 從內部 Harbor 拉）。
