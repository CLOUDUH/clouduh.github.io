---
layout: post
title: APC UPS 在群晖和 PVE 的部署
subtitle: 保护我珍贵的硬盘
date: 2025-08-11
author: CLOUDUH
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/home-bg.jpg
permalink: /post/250811
tags:
  - X
---

# APC UPS 在群晖和 PVE 的部署

## Abstract

本文简单介绍了 APC UPS BK650M2 的安装，以及在群晖和 PVE 上的安装和部署。

## 1 开箱

> 这部分回头再补

## 2 群晖 UPS 设置

使用 LAN-USB 连接 NAS 与 UPS 之后，即可在设置中看到。

![](../attachment/Pasted%20image%2020250811173329.png)

下面一条一条来解释这些设置的理解：

### 2.1 UPS 类型

- USB UPS：即本产品或者山特的通过 USB 连接到 NAS 上的 UPS 设备。
- SNMP 不断电系统：是网络 UPS，山特的有，连接到局域网的。
- Synology 不断电系统服务器：如果你有另外一台群晖设备，可以开启 UPS 服务器，使得其他的群晖设备都可以同步收到消息。

> Synology 不断电系统服务器必须在同一网络中，跨网段不允许，官方也没说出对应端口。

### 2.2 Synology NAS 进入待机模式之前的时间

待机模式解释：逐步关闭所有服务（体现在 DSM 上则是各个小图标开始变灰消失），关闭硬盘，关闭 HTTP 服务（即无法看到网页），在此之前 NAS 的灯还是亮的。

- 直到电量不足：市电断电后，UPS 继续供电，当群晖估计 UPS 的电量不足支撑接下来的运行后，开始进行待机模式，并最后关机。
- 自定义时间：在设定的时间后进入待机模式，并最后关机。如果电量不足以支撑该时间，则提前进入程序。

### 2.3 当系统进入待机模式时关闭 UPS

在完成待机状态的所有关闭后，给 UPS 发消息，让 UPS 断电，然后 NAS 自己彻底关机。

### 2.4 启用网络 UPS 服务器

把该 NAS 当做一个 UPS 服务器（类似于 SNMP 的意思），给需要的设备广播进行 UPS 配置服务。

> 还是注意，必须跟 NAS 在一个网络内，如图第一个就不行。

![](../attachment/Pasted%20image%2020250811173359.png)

## 3 PVE 配置

在 Synology 启用网络 UPS 服务器的基础上，PVE 可以使用 NUT 来实现连接。

### 3.1 安装 NUT

进入 root 模式

```shell
apt install nut -y
```

### 3.2 配置 NUT

修改 nut 配置文件，将 MODE 改为 `netclient`

```shell
vim /etc/nut/nut.conf
```

![](../attachment/Pasted%20image%2020250811173726.png)

添加监视 UPS，在 MONITOR 下添加一行：

```shell
MONITOR ups@192.168.1.20 1 upsmon pass slave
```

![](../attachment/Pasted%20image%2020250811173847.png)

启动客户端服务，并设置自动启动

```shell
systemctl start nut-client
systemctl enable nut-client
```

### 3.3 测试连接

测试连接是否正常

```shell
upsc ups@192.168.1.20
```

![](../attachment/Pasted%20image%2020250811174100.png)
## 4 运行逻辑

虽说是后备式 UPS，但是貌似有些逻辑是不同的，小白一个，尝试梳理整个流程。

![](../attachment/Pasted%20image%2020250811174900.png)

