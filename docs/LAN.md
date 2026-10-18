# 手机访问

默认情况下服务器只监听 `127.0.0.1`，那是**只有本机能访问**的地址，手机连不进来。

## 让手机能打开

```powershell
.\scripts\serve.ps1
```

脚本会：

1. 检查并放行防火墙端口 8780（需要管理员身份）
2. 用 `--host 0.0.0.0` 启动，监听所有网卡
3. 打印本机和局域网访问地址

然后手机连**同一个 WiFi**，打开脚本打印的那个局域网地址，例如：

```
http://192.168.0.101:8780
```

## 打不开的排查顺序

| 现象 | 原因 | 处理 |
|---|---|---|
| 手机浏览器转圈超时 | 不在同一个 WiFi | 连同一个路由器 |
| 同上 | 防火墙没放行 | 用管理员 PowerShell 重跑 serve.ps1 |
| 同上 | 路由器开了 AP 隔离 | 关掉「无线隔离 / AP Isolation」 |
| 同上 | 电脑 IP 变了 | 重跑 serve.ps1 看新地址 |
| 能打开但很慢 | 判断要调模型和搜索，一次 20-40 秒 | 正常 |

## 查当前局域网 IP

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' } |
  Select-Object IPAddress, InterfaceAlias
```

## 安全提醒

监听 `0.0.0.0` 意味着**同一局域网内的任何设备都能访问**，
包括判断记录（`/api/pending`、`/api/stats`）。
在家里的私有 WiFi 下没问题；在咖啡厅、宿舍、公司网络下建议别开。

用完改回只监听本机：

```powershell
python -m uvicorn app.server:app --host 127.0.0.1 --port 8780
```