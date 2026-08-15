# Web UI + Railway + 动态订阅生成

A portable Railway deployment variant derived from the verified production baseline.

---

# 🚀 Deploy on Railway

# 点击下面按钮：

<p align="center">
  <a href="https://railway.com/new/github?utm_source=github&utm_medium=readme&utm_campaign=railway-portable">
    <img src="https://railway.com/button.svg" alt="Deploy on Railway" width="260">
  </a>
</p>

---
# 选择仓库并刷新网页；
<img width="1338" height="562" alt="image" src="https://github.com/user-attachments/assets/4bb8b5c0-49ec-4f2e-9a2e-0a0c397a5752" />

# Deploy Repo
  ↓
# 第一次构建 / 启动
  ↓
# 首次会失败
  ↓
# 失败后，Settings → Networking 必须手动添加：
- 统一端口：8080
  
- Generate Domain
- TCP Proxy


<img width="759" height="233" alt="image" src="https://github.com/user-attachments/assets/88810187-bb2e-47ea-994c-547c83997e00" />

---

# Scale

## Regions & Replicas

选择部署国家，可以随时更换！

<img width="1368" height="786" alt="image" src="https://github.com/user-attachments/assets/c885ecdf-dfc8-439d-9dcb-058ac6d40e37" />

选择完成，点击左上角：Deploy

---

完成整个部署，获取订阅：

<img width="1447" height="748" alt="image" src="https://github.com/user-attachments/assets/9540145a-db55-4c0e-8ad9-28d729e3e5d1" />


输入以下命令获取订阅链接：

```bash
cat /data/subscription_url.txt
```
