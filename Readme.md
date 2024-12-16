# 说明
服务器资源监控工具，支持以下功能：
- 多服务器监控
- CPU使用率统计
- 内存使用情况
- 网络带宽监控
- 磁盘使用统计
- 自动生成Excel报表
## 使用
```bash
python3 collect.py
```

## server_config.yml说明
```
# 默认账号配置
default_credentials:
  username: root
  password: yourpasswd
  port: 22

# 服务器列表
servers:
  - host: 127.0.0.1
    # 使用默认账号密码
  # - host: 192.168.1.2
  #   username: custom_user  # 单独指定用户名
  #   password: custom_pass  # 单独指定密码
  # - host: 192.168.1.3
  #   # 使用默认账号密码

```
