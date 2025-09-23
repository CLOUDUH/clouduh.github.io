---
layout: post
title: 利用 Scrcpy 和 ADB 远程控制安卓手机
subtitle: 懒得骂某些软件了真的
date: 250922
author: CLOUDUH
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/home-bg.jpg
permalink: /post/250922
tags:
  - Crack
---

# 利用 Scrcpy 和 ADB 远程控制安卓手机

## Abstract

事情的起因是自己一直双开微信，自己砸壳自己自签，没做过什么过分的事情，但是微信这一个月给我封了 10 次号，实在是难受死了。经过 V2EX 大佬指点找到了 Scrcpy 远程控制安卓手机这一个方式

## 1 设置 Tailscale 和端口转发

### 1.1 Tailscale 设置

登陆 Tailscale，注册一个账户，注册过程略

[Tailscale · Best VPN Service for Secure Networks](https://tailscale.com/)

在安卓和 iOS 上均下载 Tailscale

![](../attachment/Pasted%20image%2020250923105938.png)

> iOS 需要外区账号，可以淘宝搜一下。安卓需要更改 Google 商店地区，可以用第三方应用商店进行下载。

在各自的设备登录之后，进入 Tailscale 官网把 IP 改一个好记的

![](../attachment/Pasted%20image%2020250922214605.png)

![](../attachment/Pasted%20image%2020250922214706.png)

如果要长时间使用 Tailscale 的话，记得在后天锁定，并关闭电池优化。

![](../attachment/Pasted%20image%2020250922224723.png)

电池—查看详情——Tailscale——后台运行——选择“不受限制”

![](../attachment/Pasted%20image%2020250922224704.png)

登陆 Tailscale，获取一个 Auth Key：

[Tailscale](https://login.tailscale.com/admin/settings/keys)

![](../attachment/Pasted%20image%2020250922215515.png)

设置一个方便记的名字，Reusable 开不开都行（看你懒不懒）

![](../attachment/Pasted%20image%2020250922215543.png)

复制这个 Auth Key，后面要用到。
### 1.2 公网路由器设置

> 博主是校园的大内网，所以直接暴露出来了。

![](../attachment/Pasted%20image%2020250922214918.png)

假设此时此刻的域名和 Tailscale IP 为：

- 公网域名： www.sbwechat.com
- 公网端口：5555
- Tailscale IP：100.105.105.105

## 2 Scrcpy 配置与连接

### 2.1 安装并配置 Scrcpy Remote

> 国区现在应该是没有了，美区 2.99 美元，直接 Pockty 买点卡充了。

![](../attachment/Pasted%20image%2020250923105952.png)

打开设置，选择配置 Tailscale 认证，输入 Auth Key，点击 Connect & Test Tailscale 进行测试。

![](../attachment/Pasted%20image%2020250922223314.png)

### 2.2 使用 iSH 修改端口

在 iPhone 的 App Store 搜索并安装 iSH

![](../attachment/Pasted%20image%2020250923103841.png)

安装 ADB 包 

```shell
apk add andriod-tools
```

在安卓手机上重新“使用配对码配对设备”，使用新的端口和配对码连接

```shell
adb pair 192.168.1.91:[pair-port] [pair-code] 
```

连接安卓手机

```shell
adb connect 192.168.1.91:[connect-port]
```

> 注意配对端口和连接端口是不一样的

修改无线调试端口号

```shell
adb tcpip 5555
```

> 建议 5555 是因为最早安卓的默认 ADB 端口就是 5555

![](../attachment/Pasted%20image%2020250923104417.png)

此时此刻，你会发现无线调试中多了一个授权，并且 Scrcpy 中的网络延迟有数据了。

> 迫不得已的情况下再更新 ADB 密钥，选择“管理 ADB 密钥”，点击“生成新的密钥对”，这个一般不要碰，除非你懂你在做什么。

### 2.3 添加配对

> 有点乱，这里我们从刚下载软件以及重启说起

在首页添加配置：

- 会话名称：不填也行
- Host or vnc：填你的域名，如果是 Tailscale 就填设备 IP
- 端口：填写你想固定的端口号
- 如果是填写了 Tailscale IP 的话记得勾选“通过 Tailscale 连接”
- 编码格式可以选择“h.265”，更加高效
- 勾选“连接后关闭远程屏幕”和“断开后关闭远程屏幕”
- 保存回话即可

![](../attachment/Pasted%20image%2020250923101718.png)

这个时候你怎么连接都是失败的，因为设备没有配对，端口号也没有固定。

在安卓设备中，“设置”——“开发者选项”——开启“USB 调试”和“无线调试”——选择“使用配对码匹配设备”

在 iOS 设备中，选择“使用配对码进行 ADB 配对”——输入地址和配对码——选择“Pair Device”

![](../attachment/Pasted%20image%2020250923102405.png)

> 配对成功后，即安卓设备认可了 iOS 设备提供的 ADBKey 和 ADBKey.PUB

成功之后的样子：

![](../attachment/Pasted%20image%2020250923103014.png)

如果使用的 Tailscale 进行连接，请打开 Tailscale 之后再进行配对，注意这个时候要填的 IP 地址一定是 Tailscale 配分的 IP 地址。

![](../attachment/Pasted%20image%2020250923110522.png)

> 那为什么不全部在 iSH 中完成呢？因为 iSH 配对成功后生成的 ADB 文件和 Scrcpy 中的生成的 ADB 文件是相互独立的，如果 Scrcpy 不通过配对授权 ADB 的话，是无法进行连接的。

### 2.4 连接测试

在首页点击添加好的配置，就能进行连接了

![](../attachment/Pasted%20image%2020250923104603.png)

这里可能会黑屏，是因为要输入密码。点击右下角选择小键盘输入密码，再点击“return”就能进入了。

![](../attachment/Pasted%20image%2020250922222903.png)

这是最终效果，整体流畅度还是可以的。

![](../attachment/Pasted%20image%2020250923104919.png)

## 3 进阶自动化

### 3.1 免输密码

每次进去还得找键盘输密码比较麻烦，可以直接创建一个自动化来实现自动输入密码

- 选择“自动化”
- 创建新的自动化
- 选择你的连接
- 选择你的密码，建议“延迟 1s 后执行”，避免反应不及时

![](../attachment/Pasted%20image%2020250922223918.png)

这时候运行自动化就是直接打开，延迟后直接输入密码

### 3.2 桌面快捷指令

> 还是太麻烦，需要判断网络选择，这里做一个快捷指令

首先在 Scrcpy 中复制一下刚刚创建的自动化的 URL Scheme

![](../attachment/Pasted%20image%2020250922224005.png)

快捷指令中加入判断

- 添加获取无线局域网的信息——选择网络名称
- 添加如果——等于——ssid1、ssid2
- 打开 URL——把公网自动化 URL Scheme 复制进去 
- 否则
- 添加 Tailscale——Connect
- 打开 URL——把 Tailscale自动化 URL Scheme 复制进去 

![](../attachment/Pasted%20image%2020250922224130.png)

随后改个名字，添加到主页。

![](../attachment/Pasted%20image%2020250922224209.png)

## 4 重启后快速指南

如果 iOS 重启，则不受影响

如果安卓设备重启，无需重新配对，因为 ADB 没有变，需要只要更改端口即可：

1、打开安卓无线调试，查看新的连接端口 [connect-port]

2、打开 iOS 上 iSH，输入：

```shell
adb connect 192.168.1.91:[connect-port]
adb tcpip 5555
```

3、Enjoy it
## Reference

【换了 iPhone，不忘安卓 - iOS 如何远程控制安卓手机】 https://www.bilibili.com/video/BV1Ps4y1P7Ex/?share_source=copy_web&vd_source=61cc68144f3cb14f9e00df37186f5ab1
