# Railway Portable Runtime — 8080 Gateway

这是一个面向新 Railway 项目的可移植母版。仓库不保存任何旧项目的 Railway 域名、随机 TCP Proxy 端口或实例 ID；容器启动时从 Railway 运行时环境重新发现这些值，并重新生成当前实例的路由、Xray 配置和 **4 节点订阅**。

## Railway 控制面：只需要 2 个公网资源

没有自己的 Custom Domain 时，手动配置：

```text
Settings → Networking

1. Generate Domain
   Target Port = 8080

2. TCP Proxy
   Target/Application Port = 8080
```

不需要创建 4 个 Generate Domain，也不需要 Custom Domain。

Railway 会自动产生当前实例的：

```text
<current>.up.railway.app
<current>.proxy.rlwy.net:<random-external-port>
```

容器通过 Railway 运行时变量动态读取它们；随机域名、随机 TCP external port 和实例 ID 不进入源代码。

## Runtime 架构

```text
                         Railway
                            │
             ┌──────────────┴──────────────┐
             │                             │
       Generate Domain                 TCP Proxy
       *.up.railway.app             *.proxy.rlwy.net
       Target = 8080                Target = 8080
             │                       :random-port
             │                             │
             └──────────────┬──────────────┘
                            ▼
                     Gateway :8080
                            │
              ┌─────────────┼─────────────┐
              │             │             │
           HTTP/TLS       TLS SNI        TCP
              │             │             │
              ▼             ▼             ▼
           10086          10087         10085 / 10088
           XHTTP/TLS      XHTTP          Vision / gRPC
                          REALITY        REALITY

127.0.0.1:10087  VLESS + XHTTP + REALITY
127.0.0.1:10086  VLESS + XHTTP + TLS
127.0.0.1:10085  VLESS + RAW/TCP + REALITY + Vision
127.0.0.1:10088  VLESS + gRPC + REALITY
```

四个 Xray inbound 都只监听 `127.0.0.1`。公网只暴露 Railway 提供的 `$PORT` Gateway。一个 TCP Proxy 通过 TLS ClientHello 的 SNI 在三个 REALITY inbound 之间分流。

## 四层 Runtime Pipeline

```text
Railway Runtime
      │
      ▼
┌─────────────────────────────┐
│ runtime-discovery.py        │
│ 当前 Domain / TCP Port / ID │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ xray-config-generator.py    │
│ identity + 4 Xray inbounds  │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ subscription-generator.py   │
│ 当前 Railway 地址 + 4 节点  │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ gateway-router.py            │
│ HTTP / TLS SNI / TCP routing │
└──────────────┬──────────────┘
               ▼
             Xray
```

### 1. runtime-discovery

读取当前 Railway 实例的：

- `PORT`
- `RAILWAY_PUBLIC_DOMAIN`
- `RAILWAY_TCP_PROXY_DOMAIN`
- `RAILWAY_TCP_PROXY_PORT`
- `RAILWAY_TCP_APPLICATION_PORT`
- `RAILWAY_PROJECT_ID`
- `RAILWAY_ENVIRONMENT_ID`
- `RAILWAY_SERVICE_ID`
- `RAILWAY_REPLICA_ID`
- `RAILWAY_REPLICA_REGION`
- `RAILWAY_DEPLOYMENT_ID`

写入：

```text
/data/runtime.json
```

任何旧 Railway 域名、随机端口、实例 ID 都不会作为配置常量保存。

### 2. xray-config-generator

生成四个本地 inbound：

```text
10087  VLESS + XHTTP + REALITY
10086  VLESS + XHTTP + TLS
10085  VLESS + RAW/TCP + REALITY + Vision
10088  VLESS + gRPC + REALITY
```

UUID、REALITY key、Short ID 等身份保存到 `/data`；Railway 网络地址与身份完全分离。

### 3. subscription-generator

每个协议只产生 **1 个节点**，总计 **4 个节点**：

```text
① VLESS + XHTTP + TLS
② VLESS + XHTTP + REALITY
③ VLESS + RAW/TCP + REALITY + Vision
④ VLESS + gRPC + REALITY
```

REALITY SNI 候选池只是内部 failover/candidate pool，不会把一个协议扩展成多个订阅节点。

主要输出：

```text
/data/vless.txt
/data/subscription.txt
/data/subscription_endpoints.txt
```

### 4. gateway-router

统一监听 `$PORT`，负责：

- `/health`
- `/ready`
- `/sub/<token>`
- 静态网站
- Railway HTTPS → XHTTP/TLS inbound
- REALITY TLS ClientHello SNI → XHTTP / Vision / gRPC inbound
- opaque TCP → Vision inbound

Gateway 不终止 REALITY TLS，只做首包分类和 TCP relay。未知 REALITY SNI 不会错误地回落到 HTTPS/XHTTP inbound。

## 部署流程

```text
Deploy on Railway
      ↓
Settings → Networking
      ↓
Generate Domain
Target Port = 8080
      ↓
TCP Proxy
Target/Application Port = 8080
      ↓
Deploy / Redeploy
      ↓
runtime-discovery
      ↓
自动发现当前 Domain + 随机 TCP Port
      ↓
自动生成 Xray 4 inbound
      ↓
自动生成 4 节点订阅
      ↓
Gateway + Xray ready
```

**没有自己的 Custom Domain 时，到这里就结束。**

Custom Domain 只是可选扩展，不是四协议运行的前置条件。

## 身份持久化

挂载 Railway Volume 后，以下身份跨重新部署保留：

```text
/data/uuid.txt
/data/reality_private_key.txt
/data/reality_public_key.txt
/data/vless_decryption.txt
/data/vless_encryption.txt
/data/short_id.txt
/data/subscription_token.txt
```

Railway 域名或 TCP Proxy 随机端口变化时，只重新发现并生成 runtime/config/subscription，不因为网络地址变化而重新生成身份。

## Runtime 状态检查

```bash
cat /data/runtime.json
cat /data/xray-manifest.json
cat /data/subscription_endpoints.txt
cat /data/vless.txt
```

## 可选变量

```text
REALITY_TARGET=www.cloudflare.com:443
REALITY_FINGERPRINT=chrome
XHTTP_PATH=/xhttp
XHTTP_MODE=auto
GRPC_SERVICE_NAME=grpc
CUSTOM_DOMAIN=<可选>
GRPC_DOMAIN=<可选>
```

`CUSTOM_DOMAIN` / `GRPC_DOMAIN` 不属于 Railway 随机运行时数据；默认部署不需要它们。

## 安全边界

应用不需要 Railway API Token。

绝不要提交：

- Railway API Token
- UUID
- REALITY private key
- subscription token
- `/data` runtime 文件

Railway Public Domain 是 HTTP/HTTPS 公网入口；TCP Proxy 是独立的 TCP 公网入口。REALITY 必须保持端到端 TCP passthrough，不能把 REALITY 节点当成普通 Railway HTTPS Domain 使用。

本项目仅作为学习与实验用途。
