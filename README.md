# Railway Portable Runtime — 8080 Gateway

这是一个面向新 Railway 项目的可移植母版。仓库不保存任何旧项目的 Railway 域名、随机 TCP Proxy 端口或实例 ID；容器启动时从 Railway 运行时环境重新发现这些值，并重新生成当前实例的路由、Xray 配置和订阅。

## Runtime 架构

```text
Railway Runtime
      │
      ▼
┌─────────────────────────────┐
│ runtime-discovery.py        │  ← PORT / Domain / TCP Proxy / instance
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ xray-config-generator.py    │  ← identity + 4 Xray inbounds
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ subscription-generator.py   │  ← current Railway endpoints + nodes
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ gateway-router.py            │  ← HTTP / TLS SNI / TCP routing
└──────────────┬──────────────┘
               ▼
             Xray

127.0.0.1:10087  VLESS + XHTTP + REALITY
127.0.0.1:10086  VLESS + XHTTP
127.0.0.1:10085  VLESS + RAW/TCP + REALITY + Vision
127.0.0.1:10088  VLESS + gRPC + REALITY
```

REALITY 的 XHTTP、RAW、gRPC 组合由 Xray transport 模型提供；四个 inbound 均只监听 `127.0.0.1`，公网只暴露 Railway 提供的 `$PORT` Gateway。

## Railway 动态发现

容器使用 Railway 提供的运行时变量：

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

这些值会写入 `/data/runtime.json`，只作为当前运行实例状态，不写回源代码。

## 身份持久化

如果挂载 Railway Volume，以下身份会跨重新部署保留：

```text
/data/uuid.txt
/data/reality_private_key.txt
/data/reality_public_key.txt
/data/vless_decryption.txt
/data/vless_encryption.txt
/data/short_id.txt
/data/subscription_token.txt
```

Railway 域名或 TCP Proxy 随机端口变化时，只重新生成 runtime/config/subscription；不会因为网络地址变化而重新生成身份。

## 四层职责

### 1. runtime-discovery

只负责发现 Railway 当前实例信息。缺少 Public Domain 或 TCP Proxy 时不会伪造旧值，也不会让镜像绑定旧项目；可先正常启动健康检查，网络资源准备后下一次部署会自动吸收新值。

### 2. xray-config-generator

根据当前 runtime state 和持久身份生成 `/etc/xray/config.json`，同时生成 `xray-manifest.json` 供 Gateway 与订阅层共享。

REALITY 的不同 transport 使用独立 SNI 池，Gateway 可通过 TLS ClientHello 的 SNI 做纯 TCP passthrough 分流，而不终止 REALITY。

### 3. subscription-generator

根据当前 Railway Public Domain / TCP Proxy domain / random port 生成节点和订阅。不会引用历史 Railway 地址。

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
- 静态伪装站点
- Railway HTTPS → XHTTP/TLS inbound
- REALITY TLS ClientHello SNI → XHTTP / Vision / gRPC inbound
- opaque TCP → Vision inbound

Gateway 不终止 REALITY TLS，只做首包分类和 TCP relay。

## 部署

点击 Railway Deploy 按钮，把仓库作为新 Service 部署即可。

```text
Deploy
  ↓
Runtime Discovery
  ↓
Xray config generation
  ↓
Subscription generation
  ↓
Gateway + Xray ready
```

然后在 Railway 的 Networking 中按实际需要启用：

1. **Generate Domain** → 指向应用监听的 `$PORT`
2. **TCP Proxy** → 指向同一个 Gateway `$PORT`
3. 如需自有域名，在 Railway Custom Domain 中绑定；自定义 TCP 域名仍使用 Railway TCP Proxy 提供的端口。

不需要把任何 Railway API Token 放进仓库，也不要把某个账户产生的 `.up.railway.app` 或随机 TCP 端口复制到代码里。

## 可选变量

```text
CUSTOM_DOMAIN=<你自己的域名>
GRPC_DOMAIN=<你自己的 gRPC 域名>
REALITY_TARGET=www.cloudflare.com:443
REALITY_FINGERPRINT=chrome
XHTTP_PATH=/xhttp
XHTTP_MODE=auto
GRPC_SERVICE_NAME=grpc
```

其中 `CUSTOM_DOMAIN` / `GRPC_DOMAIN` 是用户自己的稳定配置，不属于 Railway 随机运行时数据。

## Runtime 状态检查

```bash
cat /data/runtime.json
cat /data/xray-manifest.json
cat /data/subscription_endpoints.txt
cat /data/vless.txt
```

## 注意

Railway Public Domain 是 HTTP/HTTPS 公网入口；TCP Proxy 是独立的 TCP 公网入口。REALITY 必须保持端到端 TCP passthrough，因此不能把 REALITY 节点当成普通 Railway HTTPS Domain 使用。Railway 当前支持同一 Service 同时使用 Public Networking 和 TCP Proxy。

本项目仅作为学习与实验用途。
