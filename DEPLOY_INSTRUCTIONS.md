# 部署更新指南 (Deployment Guide)

## 快捷操作 (推荐)

我们已经配置了 `manage.sh` 和私钥 `jizhang.pem`，您可以直接通过脚本管理 VPS。

**前提**: 请确保 `manage.sh` 有执行权限，且 `jizhang.pem` 权限为 600。
```bash
chmod +x manage.sh
chmod 600 jizhang.pem
```

**1. 一键部署代码并重启**
```bash
./manage.sh deploy
```
*此命令会自动上传 app 代码、安装依赖并重启服务。*

**2. 仅重启 VPS 服务**
```bash
./manage.sh restart_vps
```

**3. 查看 VPS 日志**
```bash
./manage.sh logs
```

**4. 数据库迁移 (Alembic)**
部署新代码后，如果涉及数据库变更，请执行：
```bash
./manage.sh migrate
```

**5. 启用自动备份 (Cron)**
在 VPS 上配置每日自动备份：
```bash
./manage.sh setup_cron
```

**6. SSH 连接到 VPS**
```bash
./manage.sh ssh
```

---

## VPS 信息
- **IP**: 52.193.196.41
- **User**: ubuntu
- **Path**: /home/ubuntu/jishubot
- **Key**: ./jizhang.pem

---

## 手动操作 (备用)

如果脚本无法使用，请手动执行以下命令：

**SSH 连接:**
```bash
ssh -i jizhang.pem ubuntu@52.193.196.41
```

**重启服务:**
```bash
ssh -i jizhang.pem ubuntu@52.193.196.41 "sudo systemctl restart jishubot"
```