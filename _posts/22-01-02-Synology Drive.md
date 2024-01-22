---
layout: post
title: "实验室 NAS Synology Drive 同步使用指南"
subtitle: "给实验室做的指南"
date: 220102
author: "CLOUDUH"
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/blog-bg.jpg
permalink: /post/220102
tags:
- TJU
- NAS
---

# 实验室 NAS Synology Drive 同步使用指南

## Abstract

团队协作时，非常容易存在大量用户文件不同步的情况，因此需要通过各种云同步手段，实现对于工作文件夹的实时更新。

借助实验室的本地存储器，通过 Synology 套件库中的 Synology Drive 功能，实现在校内 IP 下的文件自动同步功能，有助于提高工作效率。

## 1 使用前提

- 在校园网的环境下使用
- 通过 VPN 连接校园网使用
- 拥有 DS447 团队文件夹的访问权限
- NAS 父级路由器开放 6690 端口

## 2 下载并安装

需要同步的用户请下载 Synology Drive Client

下载地址：[下载中心 - DS220+ | 群晖科技 Synology Inc.](https://www.synology.cn/zh-cn/support/download/DS220+?version=7.0#utilities)

![](../attachment/Pasted%20image%2020220102165511.png)

![](../attachment/Pasted%20image%2020220102165634.png)

等待安装完成

![](../attachment/Pasted%20image%2020220102165830.png)


## 03 设置同步

打开已经安装好的 Synology Drive Client，选择**立即开始**

![](../attachment/Pasted%20image%2020220102165944.png)

输入 IP / 用户名 / 密码，取消勾选 SSL 数据传输加密

```Python
NAS IP Address: 172.27.51.3
```

> 开启SSl数据传输加密会极大增加 NAS 的 CPU 负载，减小传输速度，因此不推荐开启。

![](../attachment/Pasted%20image%2020220102170612.png)

选择**同步任务**

![](../attachment/Pasted%20image%2020220102170755.png)

设置同步文件夹的位置

![](../attachment/Pasted%20image%2020220102171244.png)

![](../attachment/Pasted%20image%2020220102171510.png)

设置同步高级设置

- 取消勾选**启动按需同步以节省计算机的硬盘空间**
- 在**高级设置-文件夹**中勾选**同步带前缀"."的文件和文件夹**
- 在**高级设置-文件夹**中勾选**同步临时文件及文件夹**
- 在**高级设置-同步模式**中取消勾选**启动高级一致性检测**

> 按需同步是指只是同步NAS上的文件目录，而非同步文件本体，不适用于本指南所描述的工作环境。
> 编程工作中会有很多隐藏的带有前缀的文件夹以及临时文件夹，如 .git 文件夹，务必勾选两个选项。
> 高级一致性检测会占用系统资源，请勿勾选。

![](../attachment/Pasted%20image%2020220102172233.png)

![](../attachment/Pasted%20image%2020220102172350.png)

基本设置完成，进入客户端

![](../attachment/Pasted%20image%2020220102172752.png)

- 在**全局设置-常规**中开启**用户登陆后自动启动 Synology Drive Client**
- 在**全局设置-常规**中选择**本地删除的文件将从您的NAS上再次下载**
- 在**全局设置-常规**中选择**保留最新修改版本**
- 在**全局设置-常规**中开启**重命名以保留放弃的版本**

> 不占用太多系统资源，如果正在做项目，建议开启
> 其实这里的设置就是默认设置，不用自己动就好

![](../attachment/Pasted%20image%2020220102173425.png)

- 在**全局设置-通知**中关闭**现实文件时间的桌面通知**

> 关上吧，不然你会被 Windows 的横幅通知给烦死

![](../attachment/Pasted%20image%2020220102173358.png)

## 4 基本使用

在你选择的文件夹里创建文件/修改文件/删除文件都会同步到 NAS 上

![](../attachment/Pasted%20image%2020220102174028.png)

在**同步日志**里查看同步的记录

![](../attachment/Pasted%20image%2020220102172919.png)

查看文件版本

> 文件在更新中有所修改，Drive 开启了版本控制，通过版本控制，可以很好地找回原来的文件。

![](../attachment/Pasted%20image%2020220102174543.png)

![](../attachment/Pasted%20image%2020220102174730.png)

通过点击右侧下载图标，可以将过去的版本下载到本地的任意位置

![](../attachment/Pasted%20image%2020220102174905.png)

删除的文件，可以在群晖DSM中的回收站查看

![](../attachment/Pasted%20image%2020220102175604.png)

在系统托盘中有最近更改的记录

![](../attachment/Pasted%20image%2020220102175658.png)

