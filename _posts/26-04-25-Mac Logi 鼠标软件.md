---
layout: post
title: Mac鼠标软件排查
subtitle: 如何优雅地在mac上使用Logi办公鼠标
date: 260425
author: CLOUDUH
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/home-bg.jpg
permalink: /post/260425
tags:
  - Apple
---

# Title

## Abstract

本文主要探讨了 macOS 上主流的几个鼠标软件与罗技办公鼠标的适配性，另外也记录了 Option 在不同软件中的一些设定，以防忘记。

## 1 起因

主播一直在用罗技办公系列键鼠，分别是 K780 和 M720，虽然不太好用，但是还挺好用的。之所以不换其他品牌以及罗技高端系列的主要原因是：

- MX Master 对我来说又大又沉，抓得手腕疼，而且同样也是 125k 低回报。之前用过 2 个月，实在用不习惯直接找京东客服折旧退了。
- M720 的手势按键刚刚好，为了减重我用了 7 号转 5 号电池套，价格也便宜。唯一诟病的就是那个滚轮太不舒服了。
- 习惯了 Mac 的触控板之后，就必须要搞一个手势按键配合上下左右滑动了，当然侧边键也能做到，但是还是更喜欢一个独立的按键。
- K780 前面有一个凹槽，正好能放下我的摸鱼平板。
- 两个产品都能用 U 联一个接收器搞定，而且都能连接 3 个不同的设备。

但是你知道 Logi 你得配合电脑上 Logi Option+ 一起用才能发挥设备的最大作用。坏就坏在这个 B 软件太臃肿了，它甚至往里面塞了一个 AI，用一段时间内存占用就很让你抓狂。
## 2 不同软件

### 2.1 MOS

- 识别不了手势按键
- 之前一直没更新，但是最近好像重新开始更新了。
- 滚动体验一般，但是可调参数。

### 2 .2 Mouser

- 感觉是 Vibe Coding 的产物，说是替代官方 Option
- 目前应该只支持 MX Master 系列，不支持 M720。
- 安装之后我的滚动出现卡顿，把与其相关的所有文件删了之后才恢复正常

### 2.3 Mac Mouse Fix

- 很夯的软件，滚动平滑是用过最舒服的。
- 但是不支持 Logi 的 HID++，识别不了手势按键。

### 2.4 BetterMouse

- 功能很齐全的软件，可自定义的空间很大。
- 收费，不过价格可以接受，开发者更新也比较快，也会回邮件。
- 平滑滚动得调整很久才能适合自己，而且不同软件中响应貌似不太一样。
- 手势按键是不是出现 Bug 需要重启软件

### 2 .5 SteerMouse

- 收费
- 比 BetterMouse 差一点，手势按键定义不自由。

## 3 最终解决方案

看了一圈感觉只能选择 Option+ 或者 BetterMouse，不甘心，于是突发奇想在 GitHub 上搜有没有魔改版的 Option+，结果还真让我找到了。

[GitHub - Qetesh/logi-options-plus-mini: A minimal Logi Options+ deployment preset for keyboard and mouse only, with configurable disabling of optional features like Logi Voice, Flow, Analytics, and more · GitHub](https://github.com/Qetesh/logi-options-plus-mini)

最小化安装 Option+ 的软件，意思是你可以不安装那些臃肿的东西。

![](../attachment/Pasted%20image%2020260425110723.png)

我愿给一个年度最佳，目前彻底解决了我的问题。

> 但是 Option+ 的手势滑动不如 BetterMouse 和 Mac Mouse Fix 好用，前者切换桌面是一个一次性的动作，后两者更像是一个触控板手势的模拟（你可以停留在两个桌面中间）

## 4 Option+ 设置备忘录

### 4.1 全局

![](../attachment/Pasted%20image%2020260425111103.png)

### 4.2 Excel 

主要注意左右滚动速度设置小一点，与 PowerPoint 一致。

侧边键主要用来切换 Sheet，实在没招了。

![](../attachment/Pasted%20image%2020260425112735.png)
### 4.3 PowerPoint

![](../attachment/Pasted%20image%2020260425111633.png)

### 4.4 VS Code

主要方便时回溯代码

![](../attachment/Pasted%20image%2020260425113510.png)