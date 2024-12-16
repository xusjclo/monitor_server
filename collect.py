#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import paramiko
import pandas as pd
from datetime import datetime
import time
import logging
from typing import List, Dict, Optional
import sys
import yaml

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server_monitor.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

class ServerMonitor:
    def __init__(self, config_file: str = 'server_config.yml'):
        """
        初始化监控器
        config_file: 配置文件路径
        """
        self.config = self._load_config(config_file)
        self.servers_info = self._process_servers_config()
        self.results = []

    def _load_config(self, config_file: str) -> dict:
        """加载配置文件"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"加载配置文件失败: {str(e)}")
            return {"default_credentials": {}, "servers": []}

    def _process_servers_config(self) -> List[Dict]:
        """处理服务器配置，应用默认凭据"""
        processed_servers = []
        default_creds = self.config.get('default_credentials', {})
        default_username = default_creds.get('username', '')
        default_password = default_creds.get('password', '')
        default_port = default_creds.get('port', 22)  # 默认端口22

        for server in self.config.get('servers', []):
            processed_server = {
                'host': server['host'],
                'username': server.get('username', default_username),
                'password': server.get('password', default_password),
                'port': server.get('port', default_port)  # 使用配置的端口或默认端口
            }
            processed_servers.append(processed_server)

        return processed_servers

    def get_server_stats(self, host: str, username: str, password: str, port: int = 22) -> Dict:
        """获取单个服务器的状态信息"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=host,
                username=username,
                password=password,
                port=port,  # 使用指定的端口
                timeout=10
            )

            # 获取CPU核心数
            cpu_cores_cmd = "nproc"
            _, stdout, _ = ssh.exec_command(cpu_cores_cmd)
            cpu_cores = int(stdout.read().decode().strip() or '1')  # 默认值为1

            # 获取CPU使用率
            cpu_samples = []
            for _ in range(3):
                try:
                    cpu_cmd = "top -bn1 | grep '%Cpu' | awk '{print $2}'"
                    _, stdout, _ = ssh.exec_command(cpu_cmd)
                    cpu_output = stdout.read().decode().strip()
                    if cpu_output:
                        cpu_usage = float(cpu_output)
                    else:
                        cpu_cmd = "mpstat 1 1 | grep 'all' | awk '{print 100-$NF}'"
                        _, stdout, _ = ssh.exec_command(cpu_cmd)
                        cpu_usage = float(stdout.read().decode().strip() or '0')
                    cpu_samples.append(cpu_usage)
                except (ValueError, IndexError):
                    cpu_samples.append(0.0)
                time.sleep(1)

            # 获取内存信息（GB）
            mem_cmd = "free -g | grep 'Mem:' | awk '{print $2,$3,$4}'"
            _, stdout, _ = ssh.exec_command(mem_cmd)
            mem_output = stdout.read().decode().strip()
            try:
                total_mem_gb, used_mem_gb, free_mem_gb = map(float, mem_output.split())
                mem_usage = round(used_mem_gb / total_mem_gb * 100, 2) if total_mem_gb > 0 else 0
            except (ValueError, ZeroDivisionError):
                total_mem_gb = used_mem_gb = free_mem_gb = 0
                mem_usage = 0

            # 获取网络带宽（KB/s）
            net_stats = []
            try:
                net_cmd = "sar -n DEV 1 3 | grep 'eth0' | tail -n 3 | awk '{print $5,$6}'"
                _, stdout, _ = ssh.exec_command(net_cmd)
                for line in stdout.readlines():
                    try:
                        rxkb, txkb = map(float, line.strip().split())
                        net_stats.append((rxkb, txkb))
                    except (ValueError, IndexError):
                        net_stats.append((0.0, 0.0))
            except:
                net_stats = [(0.0, 0.0)] * 3

            # 获取磁盘使用情况（GB）
            disk_stats = []
            try:
                disk_cmd = "df -BG | grep '^/dev/' | awk '{print $2,$3,$4}'"
                _, stdout, _ = ssh.exec_command(disk_cmd)
                for line in stdout.readlines():
                    try:
                        total, used, free = map(lambda x: float(x.replace('G','')), line.strip().split())
                        disk_stats.append((total, used, free))
                    except (ValueError, IndexError):
                        continue
            except:
                disk_stats = [(0, 0, 0)]

            ssh.close()

            # 安全计算统计值
            cpu_samples = cpu_samples or [0.0]  # 如果列表为空，使用默认值
            cpu_avg = sum(cpu_samples) / len(cpu_samples)
            cpu_max = max(cpu_samples)
            cpu_min = min(cpu_samples)

            net_stats = net_stats or [(0.0, 0.0)]
            net_rx_avg = sum(rx for rx, _ in net_stats) / len(net_stats)
            net_rx_max = max((rx for rx, _ in net_stats), default=0)
            net_rx_min = min((rx for rx, _ in net_stats), default=0)
            net_tx_avg = sum(tx for _, tx in net_stats) / len(net_stats)
            net_tx_max = max((tx for _, tx in net_stats), default=0)
            net_tx_min = min((tx for _, tx in net_stats), default=0)

            return {
                'host': host,
                'cpu_cores': cpu_cores,
                'cpu_usage_avg': round(cpu_avg, 2),
                'cpu_usage_max': round(cpu_max, 2),
                'cpu_usage_min': round(cpu_min, 2),
                'memory_total_gb': total_mem_gb,
                'memory_used_gb': used_mem_gb,
                'memory_free_gb': free_mem_gb,
                'memory_usage': mem_usage,
                'network_rx_kb_avg': round(net_rx_avg, 2),
                'network_rx_kb_max': round(net_rx_max, 2),
                'network_rx_kb_min': round(net_rx_min, 2),
                'network_tx_kb_avg': round(net_tx_avg, 2),
                'network_tx_kb_max': round(net_tx_max, 2),
                'network_tx_kb_min': round(net_tx_min, 2),
                'disk_total_gb': sum(total for total, _, _ in disk_stats),
                'disk_used_gb': sum(used for _, used, _ in disk_stats),
                'disk_free_gb': sum(free for _, _, free in disk_stats),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'success'
            }

        except Exception as e:
            logging.error(f"服务器 {host} 连接失败: {str(e)}")
            return {
                'host': host,
                'status': f'error: {str(e)}',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

    def collect_all_servers_data(self):
        """收集所有服务器的数据"""
        for server in self.servers_info:
            logging.info(f"正在收集服务器 {server['host']} 的数据...")
            result = self.get_server_stats(
                server['host'],
                server['username'],
                server['password'],
                server['port']  # 传入端口参数
            )
            self.results.append(result)
            time.sleep(1)  # 添加延时避免过快请求

    def export_to_excel(self, filename: str = None):
        """将收集的数据导出到 Excel 文件"""
        try:
            # 如果没有提供文件名，使用默认格式生成
            if filename is None:
                current_time = datetime.now().strftime('%Y%m%d-%H%M')
                filename = f'1服务器运行资源报表-{current_time}.xlsx'

            df = pd.DataFrame(self.results)
            if 'status' in df.columns and df['status'].str.contains('error').any():
                # 处理错误情况
                df = df[['host', 'timestamp', 'status']]
                df.columns = ['服务器地址', '采集时间', '状态']
            else:
                # 设置列名为中文
                columns_mapping = {
                    'host': '服务器地址',
                    'cpu_cores': 'CPU核心数',
                    'cpu_usage_avg': 'CPU平均使用率(%)',
                    'cpu_usage_max': 'CPU最大使用率(%)',
                    'cpu_usage_min': 'CPU最小使用率(%)',
                    'memory_total_gb': '总内存(GB)',
                    'memory_used_gb': '已用内存(GB)',
                    'memory_free_gb': '空闲内存(GB)',
                    'memory_usage': '内存使用率(%)',
                    'network_rx_kb_avg': '平均接收带宽(KB/s)',
                    'network_rx_kb_max': '最大接收带宽(KB/s)',
                    'network_rx_kb_min': '最小接收带宽(KB/s)',
                    'network_tx_kb_avg': '平均发送带宽(KB/s)',
                    'network_tx_kb_max': '最大发送带宽(KB/s)',
                    'network_tx_kb_min': '最小发送带宽(KB/s)',
                    'disk_total_gb': '总磁盘容量(GB)',
                    'disk_used_gb': '已用磁盘容量(GB)',
                    'disk_free_gb': '空闲磁盘容量(GB)',
                    'timestamp': '采集时间',
                    'status': '状态'
                }
                df = df.rename(columns=columns_mapping)
            
            df.to_excel(filename, index=False, engine='openpyxl')
            logging.info(f"数据已成功导出到 {filename}")
        except Exception as e:
            logging.error(f"导出Excel失败: {str(e)}")

def main():
    # 使用配置文件初始化监控器
    monitor = ServerMonitor('server_config.yml')
    monitor.collect_all_servers_data()
    # 不需要指定文件名，将使用默认格式
    monitor.export_to_excel()

if __name__ == '__main__':
    main()
