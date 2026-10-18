# 手机访问

默认情况下服务器只监听 `127.0.0.1`，那是**只有本机能访问**的地址，手机连不进来。

## 让手机能打开

```powershell
.\scripts\serve.ps1
```

脚本会放行防火墙、用 `--host 0.0.0.0` 启动、打印手机能用的地址。

然后手机连**同一个 WiFi**，打开那个地址，**注意要带端口号**：

```
192.168.0.101:8780
```

## 踩过的坑（按出现顺序）

### 1. 地址漏了端口

```
192.168.0.101        ← 浏览器走 80 端口，那里没人
192.168.0.101:8780   ← 正确
```

### 2. 网络被判定为「公用」，防火墙规则不生效

这是最隐蔽的一个。Windows 经常把家里的 WiFi 判成 **Public**，
而防火墙规则如果只写 `-Profile Private,Domain`，对 Public 网络**完全不生效**——
服务在跑、本机自测 200、手机却连不上。

检查：

```powershell
Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory
```

如果是 Public：

```powershell
Set-NetConnectionProfile -InterfaceAlias "WLAN" -NetworkCategory Private
```

同时把防火墙规则改成覆盖所有类型（脚本已处理）：

```powershell
Get-NetFirewallRule -DisplayName "*绒球*" | Set-NetFirewallRule -Profile Any
```

### 3. 路由器开了 AP 隔离

如果上面都对还是连不上，去路由器设置里找
「无线隔离 / AP Isolation / 客户端隔离」，关掉它。

## 排查顺序

| 现象 | 检查 |
|---|---|
| 手机转圈超时 | 地址带端口了吗 |
| 同上 | `Get-NetTCPConnection -LocalPort 8780 -State Listen` 有输出吗 |
| 同上 | 网络是 Public 吗 |
| 同上 | 路由器 AP 隔离 |
| 能开但慢 | 判断要调模型和搜索，20-40 秒，正常 |

## 安全提醒

监听 `0.0.0.0` 意味着**同一局域网内的任何设备都能读到判断记录**
（`/api/pending`、`/api/stats`）。

家里的私有 WiFi 下没问题；咖啡厅、宿舍、公司网络下建议别开。

用完改回只监听本机：

```powershell
python -m uvicorn app.server:app --host 127.0.0.1 --port 8780
```
