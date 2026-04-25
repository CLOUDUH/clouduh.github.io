---
layout: post
title: DailyCheckin 相关设置
subtitle: 总是忘记在哪
date: 20260331
author: CLOUDUH
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/home-bg.jpg
permalink: /post/260331
tags:
  - Homelab
---

# DailyCheckin 相关设置

## Abstract

记录一下 DailyCheckin 的相关设置，总是忘记配置文件的设置方式

## 1 配置文件位置

- 适用 Termius 的 SFTP 连接到 192.168.1.83:22
- 找到 /var/lib/docker/volumes/dailycheckin/config
- 替换里面的配置文件
   
## 2 配置文件修改

下载最新的配置文件：[config.json 配置 – DailyCheckIn](https://sitoi.github.io/dailycheckin/settings/config/)

注意 Cookie 中的双引号需要通过反斜杠编译

```shell
"proxy": "http://192.168.1.2:7893
``` 

Bark 通知配置：

```shell
"BARK_URL": "https://api.day.app/XXX/DailyCheckin/",
```

## 3 Cookies 获取方法

- 登录网页，按 Cmd + Opt + I 打开开发者模式
- 刷新网页
- 点击“网络”或“Network”，点击“文档”或“Doc”
- 点击带有域名的条目，在详细中找到 Cookies
- 阿里云盘刷新后点击“控制台”或“Console”，输入 `copy(JSON.parse(localStorage.token).refresh_token)`

## 4 运行检查

- 登录 dockcloud，进入管理员模式
- 运行 `docker exec -it dailycheckin dailycheckin`