# Deploy 3 nested ESXi 9.1.1 for the air-gap VKS round (no SDDC Manager).
$ErrorActionPreference='Continue'
Set-PowerCLIConfiguration -InvalidCertificateAction Ignore -DefaultVIServerMode Multiple -Scope Session -Confirm:$false | Out-Null
$OVA="E:\9.1\Nested_ESXi9.1.1.0_Appliance_Template_v1.0.ova"
$oc = Connect-VIServer 192.168.110.32 -User 'administrator@vsphere.local' -Password $env:OUTER_VC_PASSWORD -ErrorAction Stop
$vmhost = Get-VMHost -Server $oc | Where-Object {$_.Name -like '192.168.110.16*'} | Select-Object -First 1
$ds = Get-Datastore -Server $oc -Name 'Datastore2'; $net='VCF91-Nested-Trunk'
$Domain='alan.lab'; $Netmask='255.255.255.0'; $GW='192.168.120.1'; $DNS='192.168.120.5'; $NTP='192.168.110.1'; $PW=$env:LAB_PASSWORD
# name, ip, vcpu, memGB, cacheGB, capGB
$hosts = @(
  @('esx01','192.168.120.61',24,96,40,250),
  @('esx02','192.168.120.62',24,96,40,250),
  @('esx03','192.168.120.63',24,96,40,250)
)
foreach($h in $hosts){
  $VMName,$IP,$vCPU,$vMEM,$CacheGB,$CapGB = $h
  if(Get-VM -Server $oc -Name $VMName -ErrorAction SilentlyContinue){ Write-Host "  $VMName already exists, skip" -ForegroundColor Yellow; continue }
  Write-Host "=== Deploy $VMName ($IP) ${vCPU}vCPU/${vMEM}GB cache$CacheGB/cap$CapGB ===" -ForegroundColor Cyan
  $cfg = Get-OvfConfiguration $OVA -Server $oc
  $nml = ($cfg.ToHashTable().keys | Where-Object {$_ -match 'NetworkMapping'}) -replace 'NetworkMapping.','' -replace '-','_' -replace ' ','_' | Select-Object -First 1
  $cfg.NetworkMapping.$nml.value = $net
  $cfg.common.guestinfo.hostname.value="$VMName.$Domain"; $cfg.common.guestinfo.ipaddress.value=$IP
  $cfg.common.guestinfo.netmask.value=$Netmask; $cfg.common.guestinfo.gateway.value=$GW
  $cfg.common.guestinfo.dns.value=$DNS; $cfg.common.guestinfo.domain.value=$Domain
  $cfg.common.guestinfo.ntp.value=$NTP; $cfg.common.guestinfo.password.value=$PW; $cfg.common.guestinfo.ssh.value=$true
  try { $cfg.common.guestinfo.syslog.value='' } catch {}
  $vm = Import-VApp -Server $oc -Source $OVA -OvfConfiguration $cfg -Name $VMName -VMHost $vmhost -Datastore $ds -DiskStorageFormat thin
  if(-not $vm){ Write-Host "  IMPORT FAILED" -ForegroundColor Red; continue }
  New-NetworkAdapter -VM $vm -Type Vmxnet3 -NetworkName $net -StartConnected -Confirm:$false | Out-Null
  Set-VM -Server $oc -VM $vm -NumCpu $vCPU -MemoryGB $vMEM -Confirm:$false | Out-Null
  Get-HardDisk -Server $oc -VM $vm -Name 'Hard disk 2' | Set-HardDisk -CapacityGB $CacheGB -Confirm:$false | Out-Null
  Get-HardDisk -Server $oc -VM $vm -Name 'Hard disk 3' | Set-HardDisk -CapacityGB $CapGB -Confirm:$false | Out-Null
  Start-VM -VM $vm -RunAsync -Confirm:$false | Out-Null
  Write-Host "  $VMName deployed + powering on" -ForegroundColor Green
}
Get-VM -Server $oc | Where-Object {$_.Name -match '^esx0[1-3]$'} | ForEach-Object { Write-Host ("  {0,-12} {1,-10} vCPU{2}/{3}GB" -f $_.Name,$_.PowerState,$_.NumCpu,$_.MemoryGB) }
Disconnect-VIServer $oc -Confirm:$false | Out-Null
