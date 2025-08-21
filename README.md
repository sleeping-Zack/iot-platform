# IoT 边缘–云数据同步监控平台

> 课程大作业 · 基于 **MySQL + Django + DRF + Chart.js** 的“边缘采集 → 告警/入队 → 云端归档 → 日报可视化”完整链路。

## 项目概览

* **目标**：模拟真实 IIoT 场景，贯通“边缘设备采集 → 阈值触发告警/入队 → 定时同步到云 → 生成日报 → 前端可视化”。
* **特点**：数据库内置触发器与存储过程；云端图表与日报可视化；支持 MySQL 事件调度定时执行。

## 系统架构

```
[Edge Devices] 
   ↓ (写 edge_data)
[MySQL: iot_platform]
   ├─ TRIGGER: trg_edge_alerts       （超阈值自动写 alerts）
   ├─ TRIGGER: trg_edge_enqueue      （采集数据自动入 sync_queue）
   ├─ PROC: PROC_sync_to_cloud()     （队列 → cloud_data）
   ├─ PROC: PROC_generate_report()   （生成 daily_summary 日报）
   └─ EVENT: ev_sync_to_cloud / ev_daily_report （定时任务）
         ↓
[Django + DRF API]  /api/...
         ↓
[前端页面]  /charts/ （Chart.js 折线 & 日报柱状）
```

## 功能清单

* **核心表**：`devices / edge_data / alerts / sync_queue / cloud_data / daily_summary`
* **触发器**：插入 `edge_data` 时自动判断阈值、写 `alerts`、入 `sync_queue`
* **存储过程**：`PROC_sync_to_cloud`（同步云端）、`PROC_generate_report`（日报）
* **事件调度**：`ev_sync_to_cloud`（每 5 分钟）、`ev_daily_report`（每日 00:05）
* **API**：云端时间序列、日报汇总、设备列表、最新告警
* **前端**：`/charts/` 可视化（折线+柱状）

## 技术栈

* **后端**：Python 3.11、Django、Django REST Framework
* **数据库**：MySQL 8.0（启用 event\_scheduler）
* **前端**：Chart.js（纯模板）
* **文档**：drf-spectacular（Swagger/OpenAPI）

## 接口文档（自动）

* 访问：**`/api/docs/`**（Swagger UI）
* 主要接口一览：

  * `GET /api/cloud/series?device_code=...&from=...&to=...&limit=...`
    返回云端时间序列（`cloud_data`），按 `ts` 升序。
  * `GET /api/report/daily/series?device_code=...&days=7`
    返回近 N 天日报统计（平均/最高/最低/告警数）。
  * `GET /api/devices/`
    设备列表（`device_code / device_name / sensor_type / threshold_hi / location / last_seen`）。
  * `GET /api/alerts/recent/?limit=50&device_code=...`
    最近告警（倒序）。

> 提示：接口基于 DRF，支持分页/过滤可按需扩展。

## 可视化页面

* 访问：**`/charts/`**
* 功能：输入设备代码、可选时间范围，加载云端折线图与日报柱状图；支持定时自动刷新。

## 常见排障

* **根路径 404**：项目已将根路径重定向至 `/charts/`；直接访问该路径即可。
* **1055 ONLY\_FULL\_GROUP\_BY**：来自客户端 profiling，与本项目逻辑无关，可忽略；必要时可在当前会话移除该 sql\_mode。
* **事件未执行**：确认 `SHOW VARIABLES LIKE 'event_scheduler';` 为 `ON`；在 `information_schema.EVENTS` 查看 `STATUS / LAST_EXECUTED`。


## 项目结构

```
iot-platform/
├─ iot_platform/            # 项目配置（settings.py / urls.py）
├─ iotcore/                 # 业务App（models / views / urls / serializers）
│  ├─ models.py             # 对应 MySQL 表（db_table 指向已有表）
│  ├─ views.py              # cloud_series / daily_series / devices / alerts
│  ├─ urls.py               # 路由注册（含 /charts/）
│  └─ serializers.py
├─ templates/
│  └─ cloud_dashboard.html  # Chart.js 可视化页面
└─ manage.py
```

## 后续拓展建议

* 设备鉴权（API Key + HMAC）、防重（幂等键）
* 接入真实传感器（串口/Modbus/MQTT），或网关数据上报
* 前端扩展：设备列表页、告警列表页、设备详情页
* 指标下采样与大数据量可视化（按分钟/5 分钟聚合）


## 贡献者

* **朱旭**：云端归档、存储过程与报表、后端接口、告警与同步控制
* **胡振鹏**：数据库设计,设备信息与采集逻辑、文档
* **吕文潇**：前端页面（设备/告警/报表/登录以及操作面板）

---

