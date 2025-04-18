---
layout: post
title: "让 ChatGPT & GitHub Copilot 等人工智能帮你写论文"
subtitle: "即将失业"
date: 230304
author: "CLOUDUH"
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/blog-bg.jpg
permalink: /post/230304
tags:
- Research
- Apple
- Windows
---

# 让 ChatGPT & GitHub Copilot 等人工智能帮你写论文

## Abstract

本文主要介绍了在 Visual Studio Code 的 LaTeX 环境中，如何通过人工智能聊天机器人 ChatGPT、代码自动补全工具 GitHub Copilot 以及语法辅助写作工具 Grammarly 辅助撰写论文。文章主要介绍了如何配置相关环境，工具的账号注册、使用网络环境配置不在本文的考虑范围之内。

## 1 介绍

本文是在 Visual Studio Code 中部署的 LaTeX环境，得益于 VS Code 强大的拓展性，可以安装各种插件来实现丰富的拓展性。本文涉及到多个插件各有千秋，用途是不同的，比如 Copilot 帮助你输出，ChatGPT 帮你润色，Grammarly 帮助你纠错，基本涵盖了论文写作的三个过程。我列了如下表格，让你对这几个工具又一个初步的认识

| 名称             | 地位     | 功能             | 实现难度 | 增益等级   |     |
| -------------- | ------ | -------------- | ---- | ------ | --- |
| LaTeX          | 环境     | 将代码转换为PDF      | 简单   | 无      |     |
| VS Code        | 集大成者   | 整合多工具的高效编辑器    | 简单   | 一般     |     |
| GitHub Copilot | 狡猾的马屁精 | 不断猜你的心思，帮你写出来  | 一般   | 拍手叫绝   |     |
| ChatGPT        | 听话的女仆  | 帮你生成、润色你不想写的东西 | 地狱   | 人类终将灭亡 |     |
| Grammarly      | 盯梢的老师  | 一直找你的毛病        | 简单   | 防骂神器   |     |

## 2 安装 LaTeX 环境

LaTeX 是一种基于 TEX 的排版系统，利用这种格式系统的处理，即使用户没有排版和程序设计的知识也可以充分发挥由 TEX 所提供的强大功能，不必一一亲自去设计或校对，能在几天，甚至几小时内生成很多具有书籍质量的印刷品。对于生成复杂表格和数学公式，这一点表现得尤为突出。目前它广泛适用于论文写作中，基本上 80% 的硕博论文（尤其是英文）都是由 LaTeX 编辑生成的。

![](../attachment/Pasted%20image%2020230304193937.png)

Windows 推荐的 LaTeX 环境：[TeX Live](https://tug.org/texlive/)，macOS 推荐的 LaTeX 环境：[MacTeX](https://www.tug.org/mactex/)

### 2.1 Windows 安装 TeX Live

国内下载安装比较慢的话，可以使用镜像进行下载：[清华大学开源软件镜像站](https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/Images/)

![](../attachment/Pasted%20image%2020230304231411.png)

进入镜像，**右击install-tl-windows.bat-选择使用管理员身份运行**。

![](../attachment/Pasted%20image%2020230304212917.png)

如果你没有特殊需求，默认设置一直下一步即可，出现一下信息则说明安装完成。

![](../attachment/Pasted%20image%2020230304212616.png)

### 2.2 macOS 安装 MacTeX

下载地址：[MacTeX Download](https://www.tug.org/mactex/mactex-download.html)

跟着一步一步安装即可，安装没问题的话，会自动添加到环境中。

![](../attachment/Pasted%20image%2020230304205610.png)

安装完成后，**打开终端**，输入```latex -v```，查看是否环境配置成功。

![](../attachment/Pasted%20image%2020230304205818.png)

除了环境之外，会安装四个附加 APP：

![](../attachment/Pasted%20image%2020230304210207.png)

- LaTeXiT：数学公式编辑工具（非常好用，做图/做 PPT 不可缺少）
- TeX Live Utility：LaTeX 更新工具（必要组件，不可删除）
- TeXShop：LaTeX 排版编辑工具（自带 LaTeX 编辑器，不建议删除）
- BibDesk：参考文献管理工具（基本没用，可删除）

## 3 安装 Visual Studio Code

Visual Studio Code（简称 VS Code）是一款由微软开发且跨平台的免费源代码编辑器。该软件支持语法高亮、代码自动补全、代码重构功能，并且内置了命令行工具和 Git 版本控制系统。用户可以更改主题和键盘快捷方式实现个性化设置，也可以通过内置的扩展程序商店安装扩展以拓展软件功能。

![](../attachment/Pasted%20image%2020230304194112.png)

官方网站：[Visual Studio Code](https://code.visualstudio.com/)

官方下载对应的版本后，安装即可，过于简单不再赘述。

### 3.1 安装插件

在侧边栏找到**拓展**按钮，在插件市场里找到以下插件，或者通过 GitHub 找到他们的仓库，进行手动安装：

- Grammarly (ID: znck.grammarly)
- GitHub Copilot (ID: GitHub.copilot)
- ChatGPT (ID: gencay.vscode-chatgpt)

![](../attachment/Pasted%20image%2020230304211127.png)

安装完成后，我们只需要输入 API，就可以正常工作了。

## 4 配置 ChatGPT

最近非常火的人工智能工具，让他自己回答他是什么：

![](../attachment/Pasted%20image%2020230304192927.png)

官方网站：[ChatGPT](https://chat.openai.com/chat)

> ChatGPT 的注册方法本文不做讨论，可以通过淘宝等第三方帮助解决。

本文使用的 VS Code 接入插件是： [GitHub - gencay/vscode-chatgpt](https://github.com/gencay/vscode-chatgpt) 

### 4.1 获取 API

> 注意 API 的使用是消耗余额的，新用户只赠送 5 USD，因此如果您打算长期使用，请绑定您的国外银行卡。

访问 OpenAI 的管理网站：[OpenAI API](https://platform.openai.com/account/api-keys)

在 **API Keys** 中，点击 **Create new secret key**，创建一个新 Key。

![](../attachment/Pasted%20image%2020230304213646.png)

创建完成后，复制 API Key，注意前面的```sk-```也要保留。

![](../attachment/Pasted%20image%2020230304213823.png)

### 4.2 配置 API 和菜单

打开 VS Code，找到**插件设置**，找到 **API Key**，输入之后就可以使用了。

![](../attachment/Pasted%20image%2020230304214734.png)

你可以通过自定义菜单栏，通过**修改插件设置实现**，主要是修改前缀的表述。

![](../attachment/Pasted%20image%2020230304215754.png)

### 4.3 基本使用

找到一段代码，右击可以看到各种选项：

- Add tests：帮你测试
- Find bugs：帮你找到这里的 BUG
- Optimize：帮你优化（润色）这段代码
- Explain：帮你解释这段代码
- Add comments：帮你注释

![](../attachment/Pasted%20image%2020230304220027.png)

## 5 配置 GitHub Copilot

GitHub Copilot 是 GitHub 和 OpenAI 合作开发的一个人工智能工具，用户在使用Visual Studio Code 等集成开发环境时可以通过自动补全代码，并基于你的上下文给出推荐的代码建议。根据官方介绍，Copilot 已经接受了来自 GitHub 上公开可用存储库的数十亿行代码的训练，因此，理论上他支持目前所有主流编程语言，这意味着它也可以帮你写文档和论文。

![](../attachment/Pasted%20image%2020230304203545.png)

官方网站：[GitHub Copilot](https://github.com/features/copilot)

### 5.1 申请与安装

GitHub Copilot 对学生用户是免费使用的，因此可以申请 GitHub Education 来申请免费的使用权限：[GitHub Education](https://education.github.com/)

> GitHub Education 审核较为严格，而且审核周期比较长，请务必保证您的身份证件清晰，能够最详细地证明您是在校学生。

由于 VS Code 是支持通过 GitHub 账号登陆，因此，整个配置过程非常顺畅，点击右下角小人，根据提示跳转至 GitHub 网页认证，登录上就完成了。

认证完成之后，点击右下角的机器小人图标，即可选择是否在当前文件类型或者全局开启。

![](../attachment/Pasted%20image%2020230304221541.png)

### 5.2 基本使用

- 写完一个公式，让他去解释公式里面的符号的意思。

![](../attachment/Pasted%20image%2020230304222514.png)

- 写重复但是规律的代码/语句

![](../attachment/Pasted%20image%2020230304222551.png)

- 如果你的上下文足够丰富，那他还会根据你的思想来生成你可能需要的话

![](../attachment/Pasted%20image%2020230304222416.png)

> 人工智能直接伦理爆炸。

## 6 配置 Grammarly

Grammarly是一款在线语法纠正和校对工具，支持Windows、Mac、iOS和Android等多个平台。Grammarly可以自动检测用户所书写的英文是否存在语法、拼写、标点等错误，帮你纠正标点符号、修正语法错误、调整语气以及给出风格建议等；对学术写作来说，Grammarly还可以帮助查重。

![](../attachment/Pasted%20image%2020230304210718.png)

官方网站：[Grammarly](https://app.grammarly.com/)

## 6.1 绑定账号

这三个插件中只有 Grammarly 的获取方式最为简单，直接注册账号登陆后购买即可。他提供了免费版可以在线使用，购买会员之后的高级版才能够使用 API，请先去注册账号并充值会员之后再进行下一步。如果你囊中羞涩，通过别 (tao) 人 (bao) 搭 (gou) 车 (mai) 也是一个不错的选择。

获取高级版之后，通过**设置-命令面板**调出命令行，输入 **Grammarly**，选择 **Grammarly: Login / Connect your account**

![](../attachment/Pasted%20image%2020230304223427.png)

VS Code 弹出网页之后，点击继续即可。

![](../attachment/Pasted%20image%2020230304223613.png)

### 6.2 基本使用

找到一篇文本文档，点击右下角的按钮就可以开始自动检查。

![](../attachment/Pasted%20image%2020230304223717.png)

找到错误的位置，提示修改的位置会在文中直接使用波浪线标出。

![](../attachment/Pasted%20image%2020230304223915.png)

在错误上悬停即可出现修改意见，可以直接点击**快速修复**修改。

![](../attachment/Pasted%20image%2020230304224033.png)

## 7 Conclusion

本文首先介绍了如何在 Windows 和 macOS 上安装 LaTeX 环境，随后简单介绍了VS Code 安装几个插件的方法。随后，分别介绍了配置人工智能聊天机器人 ChatGPT、代码自动补全AI工具 GitHub Copilot 以及语法辅助写作工具 Grammarly 的方法，并通过一些小例子展示了其效果。