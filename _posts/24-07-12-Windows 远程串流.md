---
layout: post
title: 利用 Sunshine 和 Moonlight 实现 Windows 远程串流
subtitle: 可以在宿舍低延迟打电脑游戏了
date: 2024-07-12
author: CLOUDUH
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/home-bg.jpg
permalink: /post/240712
tags:
  - Windows
---

# 利用 Sunshine 和 Moonlight 实现 Windows 远程串流

## Abstract

本文利用 Sunshine 作为串流 HOST 端，并利用 MOONLIGHT 作为串流 CLIENT 端实现 WINDOWS 的远程串流。在校园网下实现了低延迟的远程游戏体验。

## 1 Background

远程串流即通过局域网或者广域网下连接个人电脑，实现在不同设备端访问个人电脑的桌面，达到与直接连接屏幕使用设备相似的体验，目前具体应用如下：

- 使用平板电脑作为电脑副屏
- 使用闲置手机作为电脑性能监测器
- 远程访问办公室电脑传输和处理文档
- 远程访问游戏实现在线游戏

## 1.1 为什么要串流

本文的需求：**不挪动兼有工作和游戏属性主机位置的情况下，在宿舍串流玩游戏**

电脑在课题室，日常办公需要（跑代码或者测试软件），总想趁着休息时间打游戏，但不可行。如果搬回宿舍打游戏，那么就需要以一个奇怪的姿势拔下所有的线，然后抱着 20 多斤带玻璃的机箱爬 5 楼并插上所有的线。除此之外，我还需要准备另外一套键鼠，并配备一个 4K 显示器。

## 1.2 为什么是 SUNSHINE 方案

目前主流串流方案：

- ToDesk，向日葵：经过服务商中转的远程桌面，画质延迟不行，适合外网访问
- Microsoft Remote Desktop：Windows 自带应用，配置相对简单，适合内网办公
- Parsec：没用过，但据说键盘鼠标兼容性不好
- Steam Link：Steam 自带软件，配置超级简单但不稳定，适合内网打游戏
- Sunshine + Moonlight：网友一致好评的方案，配置相对复杂

Sunshine 支持 AMD、Intel、Nvidia GPU 硬件编码以及软件编码，可以方便的将电脑画面传输到各主流操作系统的客户端软件上，如 Android、iOS 、Windows 、macOS 以及 Linux 平台上。

## 1.3 该文的创新点

网上有各种不同的教程了，本文的相比于其他教程的创新点如下：

- 详细介绍路由器的设置思路。
- 通过 DDNS 实现校园网内的 IP 定位。

# 2 Sunshine 安装与配置

## 2.1 下载与安装

前往 Sunshine 的 GitHub 仓库下载最新的发行版，注意要选择 Latest 版本中（注意区别 Pre-release 的测试版），选择 `sunshine-windows-installer.exe` 进行下载。

[GitHub - LizardByte/Sunshine: Self-hosted game stream host for Moonlight.](https://github.com/LizardByte/Sunshine)

安装过程中，请注意安装路径不能存在中文，并安装所有控件。

![](../attachment/Pasted%20image%2020240712200436.png)

安装完成后，Sunshine 会在后台运行并在本机地址上开启一个端口作为配置页面，点击右下角状态栏的 Sunshine 图标，在弹出菜单中选择 `Open`，随后浏览器会跳转至 `https://localhost:47990` 进入管理页面。

![](../attachment/Pasted%20image%2020240712201229.png)

> 理论上在安装完成后，会自行打开浏览器跳转到管理页面

> 这里的 localhsot 是代表本地回环地址，指向 127.0.0.1，只能在本机访问。

由于强制 HTTPS 访问但缺少证书，浏览器会提示非私密连接，点击 `详情` 后，选择 `继续前往localhost（不安全）`，以后的访问会自动跳过这个页面。

![](../attachment/Pasted%20image%2020240712202825.png)

初次进入管理页面，需要设置用户名和密码，根据自己的情况设置即可。

注册完成之后，等待几秒，浏览器会自动刷新，随后弹出一个小窗口，输入刚才设置的用户名和密码即可。

> 这里的用户名和密码是进入管理页面所需要的，并不是一个联网账户，也无法通过邮箱注册的方式进行找回，所以请务必牢记。理论上，每次重新开启服务后进入配置页面，都需要重新输入密码，但是这不影响已经配置好的服务进程。

![](../attachment/Pasted%20image%2020240712203006.png)
## 2.2 设置语言

点击菜单栏 `Configuration` 进入配置页面，点击进入 `General` 。

配置语言成 `简体中文`，随后点击页面最下方的 `Save`，然后再点击 `Apply` ，等待一会然后刷新网页。

![](../attachment/Pasted%20image%2020240712203024.png)

> Apply 之后会重启页面服务，即可刷新可能无法连接，等待几秒重新刷新即可。

后续只需要简单设置网络即可，其他设置无特殊需要不需要动。
## 2.3 设置网络

点击菜单栏 `配置` 进入配置页面，点击进入 `网络` ，这里有两种设置方案：（1）利用 UPnP 实现自动端口转发，需要路由器支持 UPnP 协议，配置相对简单；（2）手动设置路由器端口映射，基本全部路由器都支持但是比较繁琐。这里先逐步介绍每个选项的意思：

- UPnP：即插即用网络协议，能够省去端口映射的麻烦，需要上级路由器支持，比较适合公网中端口不确定的情况下使用。
- IP 地址族：设置 IPv4 还是 IPv6 进行访问，目前公网 IPv 6 设置相对 IPv4 方便一点，如果有 DDNS 域名，就根据解析记录的类型进行选择。
- 端口：如果使用 UPnP 方式的话不要动，硬要更改的话也要将端口群更改到 UPnP 的排除端口以外；如果使用端口映射的方式的话，可以自行设置。

> 端口分为公认端口（0-1023）、注册端口（1024-49151）和动态/私有端口（49152-65535），一般 UPnP 使用的是动态/私有端口，如 49989；如果设置端口映射的话使用注册端口的范围即可，例如 12345。

- 允许 Web UI 访问来源：意思就是当前这个页面能不能在广域网进行访问（前提是开启了相应端口映射或者 UPnP），建议开启，不然跑回宿舍访问不了。
- 外部 IP：就是你的公网 IP 或者是 DDNS 绑定好的域名。

> 例如你的路由器广域网地址为 202.123.123.123 或 www.wanyouxi.com ，那么你就可以在异地通过访问 202.123.123.1 23:47990 或 www.wanyouxi.com:47990 进行访问。

- 局域网和公网加密模式：加密可以提高安全性，局域网内基本不用考虑，公网的话根据自己需求吧，开了可能会对速度有影响。

![](../attachment/Pasted%20image%2020240712203946.png)

端口映射方案相比于 UPnP 方案就禁用一下 UPnP，并且设置一个好记的端口群，假设设置的为 7777，端口群为 `7772,7777,7778,7798,7786-7788`，其中 7777 是连接端口，7778 是管理端口。

# 3 路由器的安装与配置

每一家的路由器设置不尽相同，这里以功能比较丰富的 iKuai 路由器作为例子，我也找了几个 TP-Link 路由器的截图，可以参考。

## 3.1 公网 IP 或者 DDNS

常用的方案有以下几类：

- 申请固定公网 IPv4 或 IPv 6 地址：申请超级难且贵。
- 申请动态公网 IPv4 地址配 DDNS 服务：申请比较难，配置服务有现成方案。
- 申请动态公网 IPv6 地址配 DDNS 服务：比较容易实现的方案。
- 通过 FRP 经中转服务器实现数据传输：存在明显延迟。
- 通过异地组网实现 P2P 组网：免费方案 ZeroTier，或者一大堆付费
- 校园网 IP 配 DDNS 服务：理解大内网，折腾但快乐。

> 这里感谢我校信网中心近几年的倾力付出，基本实现了高速 Wi-Fi6 无死角覆盖，让我随时随地在学校里看 NAS 上的 PLEX 和畅玩串流游戏。

这部分内容比较麻烦，这里不做详细介绍了，给大家一个思路可以去自己琢磨一下。

## 3.2 UPnP 方案设置

进入 `网络设置——UPnP设置——UPnP设置`，开启 UPnP 服务，然后添加一条线路。

![](../attachment/Pasted%20image%2020240712213558.png)

![](../attachment/Pasted%20image%2020240712213631.png)

## 3.3 端口映射方案

如果你的路由器不支持 UPnP 服务，则需要通过设置端口映射，打开 `网络设置——端口映射——端口映射`，添加一个端口映射的内网地址。

![](../attachment/Pasted%20image%2020240712213836.png)

记得设置协议要勾选 TCP 和 UDP 兼有，或者分开设置（没必要）

![](../attachment/Pasted%20image%2020240712213909.png)

# 4 Moonlight 安装与配置

## 4.1 下载与安装

进入 Moonlight 的官网，选择 Client Downloads，选择响应的平台进行下载。

[Moonlight Game Streaming: Play Your PC Games Remotely](https://moonlight-stream.org/)

![](../attachment/Pasted%20image%2020240712214238.png)

安卓版本会直接跳到 Google Play 商店，手机无法访问的话，进入该项目的 GitHub 仓库的最新 Release 中进行下载。

[GitHub - moonlight-stream/moonlight-android: GameStream client for Android](https://github.com/moonlight-stream/moonlight-android)
![](../attachment/Pasted%20image%2020240712214410.png)

> 不建议使用 iOS 进行串流游玩，据网友反馈 iOS 端无法支持非加密的 IPv4 访问。

## 4.2 添加 Host 电脑

软件相当干净直接，如果你的连接在局域网内，会自动搜索并显示。

![](../attachment/Pasted%20image%2020240712214847.png)

添加远程的电脑需要输入响应的 IP 或者域名，如果你更改了默认端口，请添加端口号。

![](../attachment/Pasted%20image%2020240712214754.png)

# 5 设置虚拟显示器

Sunshine 啥都好，就要求必须有一个实体显示器才能进行映射，目前的解决方案：

- 显卡诱骗器（插在显卡上，假装有一个高清的输出）
- 虚拟显示器，按照连接安装一下即可

[GitHub - KtzeAbyss/Easy-Virtual-Display: Effortlessly create virtual displays in Windows, capable of supporting various resolutions and refresh rates, suitable for remote control or graphics card spoofing.在win中轻松创建支持多种分辨率和刷新率的虚拟显示器，可用于远程控制或显卡欺骗。](https://github.com/KtzeAbyss/Easy-Virtual-Display)

# 5 实机延迟测试

这是非局域网的延迟，我很惊讶为啥几乎看不到延迟。

![](../attachment/Pasted%20image%2020240712215114.png)

这是开启了加密的延迟，也就损失了 20ms。

![](../attachment/Pasted%20image%2020240712215216.png)

玩个骚的，不直接连接校园网，通过 EasyConnect 连接学校 VPN 测试一下，在最低画质和最低帧率下，延迟比较可观，但是至少简单能用一下。，

![](../attachment/Pasted%20image%2020240712215722.png)