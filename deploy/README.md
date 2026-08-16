# Portable Railway deployment helpers

这个目录只描述 Railway 控制面的可选网络配置。容器本身不依赖旧项目数据，也不需要 Railway API Token。

## 新账户部署

```text
Deploy on Railway
      ↓
runtime-discovery
      ↓
Xray config generation
      ↓
Subscription generation
      ↓
Gateway + Xray
```

首次部署不再因为缺少 Public Domain / TCP Proxy 而故意失败。容器会使用当前可见的 Railway 运行时变量启动健康检查，并把缺失的公网资源记录为未配置。

## 可选网络资源

### Public Domain

```text
Settings → Networking → Generate Domain
Target/application port = service PORT
```

Railway 生成的 `*.up.railway.app` 会在运行时通过 `RAILWAY_PUBLIC_DOMAIN` 被发现。

### TCP Proxy

```text
Settings → Networking → TCP Proxy
Target/application port = service PORT
```

Railway 会生成当前实例的 TCP proxy domain 和随机 external port。容器通过：

```text
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
RAILWAY_TCP_APPLICATION_PORT
```

动态获取这些值，不会把历史随机端口写进代码。

## 动态与固定项

### Railway 动态项

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

### 用户自己的固定项（可选）

```text
CUSTOM_DOMAIN
GRPC_DOMAIN
REALITY_TARGET
XHTTP_PATH
GRPC_SERVICE_NAME
```

用户自己的域名不属于 Railway 随机运行时数据，因此不应该由 runtime discovery 猜测。

## Runtime 文件

容器启动后会产生：

```text
/data/runtime.json
/data/xray-manifest.json
/data/vless.txt
/data/subscription.txt
/data/subscription_endpoints.txt
```

这些都是当前实例的运行时产物，不应提交到 Git。

## 验证

网络资源配置完成后可以运行：

```bash
./deploy/verify.sh
```

它会读取当前环境变量，不要求固定 8080，也不会验证历史域名或历史 TCP 端口。

## 安全

应用不需要 Railway API Token。

绝不要提交：

- Railway API Token
- UUID
- REALITY private key
- subscription token
- `/data` runtime 文件
