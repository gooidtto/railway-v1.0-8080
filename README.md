# Railway Portable Runtime — 8080 Gateway

这是一个面向新 Railway 项目的可移植母版。仓库不保存任何旧项目的 Railway 域名、随机 TCP Proxy 端口或实例 ID；容器启动时从 Railway 运行时环境重新发现这些值，并重新生成当前实例的运行时路由、Xray 配置和 4 节点订阅。

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

## 最终运行时架构

公网只有两个入口，内部 Xray 端口全部动态化：

```text
                         Railway
                            │
             ┌──────────────┴──────────────┐
             │                             │
       Generate Domain                 TCP Proxy
       *.up.railway.app             *.proxy.rlwy.net
       Target = 8080                Target = 8080
       :443                          :random-port
             │                             │
             └──────────────┬──────────────┘
                            ▼
                     Gateway :8080
                     固定 / 唯一公网目标
                            │
             ┌──────────────┼──────────────┐
             │              │              │
        SNI=CF          SNI=Canva       SNI=Epic
             │              │              │
             ▼              ▼              ▼
       XHTTP REALITY   Vision REALITY   gRPC REALITY
       127.0.0.1       127.0.0.1       127.0.0.1
       :动态端口        :动态端口        :动态端口
```

HTTPS Generate Domain 另外提供：

```text
Railway Domain :443
        ↓
Gateway :8080
        ↓
XHTTP + TLS
127.0.0.1:<动态端口>
```

### 端口职责

| 层级 | 端口 | 是否固定 | 公网可见 |
|---|---:|---|---|
| Railway Generate Domain | 443 | Railway 管理 | 是 |
| Railway TCP Proxy | 随机 | Railway 管理 | 是 |
| Gateway | 8080 | **固定** | 仅作为 Railway Target |
| XHTTP + REALITY | 动态 localhost | **每次启动重新分配** | 否 |
| XHTTP + TLS | 动态 localhost | **每次启动重新分配** | 否 |
| Vision + REALITY | 动态 localhost | **每次启动重新分配** | 否 |
| gRPC + REALITY | 动态 localhost | **每次启动重新分配** | 否 |

客户端永远不会看到 Xray 的 localhost 端口。

## Runtime Manifest：唯一事实来源

所有运行时端口由 `port_allocator.py` 一次生成，然后写回：

```text
/data/runtime.json
```

随后由同一份 runtime state 驱动：

```text
runtime.json
   │
   ├── xray-config-generator
   │        ↓
   │     Xray listeners
   │
   ├── gateway-router
   │        ↓
   │     SNI → localhost port
   │
   └── subscription-generator
            ↓
         Railway public endpoint
```

因此不存在：

```text
Xray 自己随机一次
Gateway 再随机一次
Subscription 再随机一次
```

而是：

```text
allocate once
     ↓
shared manifest/runtime
     ↓
Xray + Gateway + Subscription
```

### 动态端口示例

第一次启动：

```text
Gateway              :8080
XHTTP REALITY        127.0.0.1:18321
Vision REALITY       127.0.0.1:24173
gRPC REALITY         127.0.0.1:31642
XHTTP TLS            127.0.0.1:15491
```

下一次启动可以变成：

```text
Gateway              :8080
XHTTP REALITY        127.0.0.1:28731
Vision REALITY       127.0.0.1:15427
gRPC REALITY         127.0.0.1:32764
XHTTP TLS            127.0.0.1:19243
```

客户端完全不需要知道这些变化，因为公网仍然只连接当前 Railway Domain 或 TCP Proxy。

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
│ port_allocator.py           │
│ 动态 localhost Xray ports   │
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

`port_allocator.py` 是运行时内部资源分配层；公网 Railway discovery 与协议配置仍保持职责分离。

## 1. runtime-discovery

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

如果没有同时发现 Generate Domain、TCP Proxy Domain/Port，启动会拒绝进入 READY 状态。

## 2. port-allocator

保持 Gateway `8080` 固定；为 4 个 Xray inbound 在 `127.0.0.1` 上动态分配互不重复的 TCP 端口：

```text
xhttp_reality
xhttp_tls
vision_reality
grpc_reality
```

端口每次进程启动重新选择，不写入客户端订阅，也不作为公网接口。

## 3. xray-config-generator

从 `/data/runtime.json` 读取动态 listener ports，生成：

```text
VLESS + XHTTP + REALITY
VLESS + XHTTP + TLS
VLESS + RAW/TCP + REALITY + Vision
VLESS + gRPC + REALITY
```

UUID、REALITY key、Short ID 等身份保存到 `/data`；Railway 网络地址与 Xray 身份完全分离。

REALITY profile 要求：

```text
SNI == serverNames == camouflage target hostname
```

并且 XHTTP、Vision、gRPC 三组 SNI 必须互斥。重复 SNI 或缺失协议池会阻止启动，而不是产生一个错误路由的“假稳定”实例。

生成的 `/data/xray-manifest.json` 同时记录：

- 当前 UUID / public key / short ID
- 三组 REALITY profile
- 当前动态 localhost listener ports
- XHTTP / gRPC transport 参数

## 4. subscription-generator

每个协议只产生 **1 个节点**，总计 **4 个节点**：

```text
① VLESS + XHTTP + TLS
② VLESS + XHTTP + REALITY
③ VLESS + RAW/TCP + REALITY + Vision
④ VLESS + gRPC + REALITY
```

公网节点只使用：

```text
Generate Domain :443
TCP Proxy Domain :Railway random port
```

绝不会把：

```text
127.0.0.1:<dynamic-port>
```

写入订阅。

主要输出：

```text
/data/vless.txt
/data/subscription.txt
/data/subscription_endpoints.txt
/data/subscription_url.txt
```

## 5. gateway-router

统一监听 `0.0.0.0:8080`，读取 `/data/runtime.json` + `/data/xray-manifest.json` 建立唯一 route table，负责：

- `/health`
- `/ready`
- `/sub/<token>`
- 静态网站
- Railway HTTPS → XHTTP/TLS
- REALITY TLS ClientHello SNI → 对应 XHTTP / Vision / gRPC inbound

Gateway 不终止 REALITY TLS，只做首包分类和 TCP relay。

未知 REALITY SNI 会明确拒绝：

```text
reject unknown TLS SNI=...
```

不会再把未知 TLS 错误回落到 Vision。

Gateway 还输出入口诊断：

```text
accepted peer=...
initial ...
tls sni=... route=... target=...
```

因此可以直接判断故障位于：

```text
Railway → Gateway
Gateway → Xray
Xray REALITY
Client subscription
```

## 启动顺序

```text
START
  ↓
runtime-discovery
  ↓
port-allocator
  ↓
xray-config-generator
  ↓
subscription-generator
  ↓
xray -test
  ↓
启动 Xray
  ↓
等待 4 个动态 localhost listeners
  ↓
启动 Gateway :8080
  ↓
Gateway bind/readiness
  ↓
READY
```

如果任意一个 Xray listener 无法启动，Gateway 不会进入 READY。

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
动态分配 localhost Xray ports
      ↓
自动生成 Xray 4 inbound
      ↓
自动生成 4 节点订阅
      ↓
Gateway + Xray ready
```

**没有自己的 Custom Domain 时，到这里就结束。**

Custom Domain 只是可选扩展，不是四协议运行的前置条件。

## 身份与网络状态分离

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

Railway Domain、TCP Proxy external port 和 Xray localhost listener ports 属于运行时网络状态；其中前两者由 Railway 发现，最后一组由 `port_allocator.py` 每次启动重新分配。

身份不会因为内部端口变化而重新生成。

## Runtime 状态检查

```bash
cat /data/runtime.json
cat /data/xray-manifest.json
cat /data/subscription_endpoints.txt
cat /data/subscription_url.txt
cat /data/vless.txt
```

重点检查：

```text
railway.public_domain
railway.tcp_proxy_domain
railway.tcp_proxy_port
listeners.gateway
listeners.xhttp_reality
listeners.xhttp_tls
listeners.vision_reality
listeners.grpc_reality
```

## 可选变量

```text
REALITY_FINGERPRINT=chrome
XHTTP_PATH=/xhttp
XHTTP_MODE=auto
GRPC_SERVICE_NAME=grpc
CUSTOM_DOMAIN=<可选>
GRPC_DOMAIN=<可选>
```

协议专属 SNI override 只有在三组互斥且完整时才会被接受；否则使用仓库内 canonical SNI 分组，避免旧 Railway 环境变量污染新部署。

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
