# Portable Railway deployment helpers

这个目录只描述 Railway 控制面的网络配置。容器不依赖旧项目数据，也不需要 Railway API Token。

## 新 Railway 账户：标准配置

没有自己的 Custom Domain 时，**只手动添加两个资源**：

```text
Settings → Networking

1. Generate Domain
   Target Port = 8080

2. TCP Proxy
   Target/Application Port = 8080
```

不要创建 4 个 Generate Domain。
不要为四种 Xray 协议分别创建 Railway 公网端口。
不要把 Railway 随机 TCP external port 写进代码。

Railway 自动产生：

```text
<current>.up.railway.app
<current>.proxy.rlwy.net:<random-external-port>
```

容器通过运行时变量自动发现这些值。

## 为什么两个入口足够

```text
Generate Domain :8080
        │
        ▼
   Gateway :8080
        │
        └── HTTP/XHTTP/TLS → 10086

TCP Proxy :8080
        │
        ▼
   Gateway :8080
        │
        ├── REALITY SNI A → 10087 XHTTP
        ├── REALITY SNI B → 10085 Vision
        └── REALITY SNI C → 10088 gRPC
```

一个 TCP Proxy 承载三个 REALITY inbound；Gateway 根据 TLS ClientHello 的 SNI 做纯 TCP passthrough 分流。

## 自动生成的四个节点

部署完成后订阅严格生成 4 个节点：

```text
1. VLESS + XHTTP + TLS
2. VLESS + XHTTP + REALITY
3. VLESS + RAW/TCP + REALITY + Vision
4. VLESS + gRPC + REALITY
```

REALITY SNI 候选池用于内部候选/容错，不会把每个 SNI 扩展成额外订阅节点。

## 动态运行时值

容器读取：

```text
PORT
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
RAILWAY_TCP_APPLICATION_PORT
RAILWAY_PROJECT_ID
RAILWAY_ENVIRONMENT_ID
RAILWAY_SERVICE_ID
RAILWAY_REPLICA_ID
RAILWAY_REPLICA_REGION
RAILWAY_DEPLOYMENT_ID
```

其中：

```text
*.up.railway.app       → Railway 当前 Public Domain
*.proxy.rlwy.net       → Railway 当前 TCP Proxy Domain
random external port   → Railway 当前 TCP Proxy Port
```

这些值全部属于当前实例 runtime state，不属于 GitHub 母版。

## 本地 Xray 端口

```text
10087  VLESS + XHTTP + REALITY
10086  VLESS + XHTTP + TLS
10085  VLESS + RAW/TCP + REALITY + Vision
10088  VLESS + gRPC + REALITY
```

四个端口只监听 `127.0.0.1`。

## 验证

网络资源添加完成后，可使用：

```bash
./deploy/verify.sh
```

验证目标：

```text
1. Public Domain → 8080
2. TCP Proxy → 8080
3. TCP external port 为 Railway 当前随机值
4. /health = 200
5. /ready = 200
6. /data/subscription.txt 包含 4 个节点
7. 4 个节点地址均使用当前 Railway runtime 信息
```

## Custom Domain

Custom Domain 是可选扩展，不是四协议运行的前置条件。

没有自己的域名时，不需要配置：

```text
CUSTOM_DOMAIN
GRPC_DOMAIN
```

## 安全

应用不需要 Railway API Token。

绝不要提交：

- Railway API Token
- UUID
- REALITY private key
- subscription token
- `/data` runtime 文件
