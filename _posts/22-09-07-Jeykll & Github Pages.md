---
layout: post
title: "利用 Github Pages 建立个人博客"
subtitle: "本网站的来源"
date: "2022-09-07"
author: "CLOUDUH"
header-img: "/cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/blog-bg.jpg"
permalink: "/post/22090701"
tags:
- Website
---

# 利用 Github Pages 建立个人博客

## Abstract

本篇文章介绍了我是如何搭建自己的个人网站的，本人没有任何前端基础，所有 HTML 文件的更改都是靠猜出来的，简单来说，这个网站是我东拼西凑出来的。主要内容如下：

1. 仓库创建：使用 GitHub Pages 功能创建仓库，并使用主题
2. 域名指向：购买域名，设置 DNS 解析将域名指向 GitHub Pages 的域名。
3. 环境配置：M1 Mac 的本地调试环境配置，包括 Homebrew、Ruby、jekyll
4. 个性化设置：本博客的个性化更改与当前的问题

## 1 建立仓库

### 什么是 GitHub Pages？

> GitHub Pages 是一项静态网站托管服务，它直接从 GitHub 上的存储库中获取 HTML、CSS 和 JavaScript 文件，也可以选择通过构建过程运行这些文件，并发布一个网站。你可以在 GitHub Pages 示例集里看到 GitHub Pages 网站的例子。

### 什么是 Jekyll？

> Jekyll 是一个简单的博客形态的静态站点生产机器。它有一个模版目录，其中包含原始文本格式的文档，通过一个转换器（如 Markdown）和我们的 Liquid 渲染器转化成一个完整的可发布的静态网站，你可以发布在任何你喜爱的服务器上。Jekyll 也可以运行在 GitHub Page 上，也就是说，你可以使用 GitHub 的服务来搭建你的项目页面、博客或者网站，而且是完全免费的。

### 能不能简单点？

简单来说，你可以在 GitHub 上 Fork 别人的模版，然后根据 README 修改之后，就可以拥有一个自己的网站了。

GitHub 是基于 Jekyll 建构的网页，因此你可以在 GitHub 上搜索到各种各样子的模版，或者在 Jekyll 主题库中找到自己喜欢的模版：[Jekyll Themes](http://jekyllthemes.org/)

建立仓库之后，一定设置为 Public，然后名字一定要遵循：`XXX.github.io`这样的格式。

## 2 域名指向

拥有域名之前，你只能通过 xxxx.github.io 这个域名访问你的个人网页，对于很多人来说，这并不是一个好记的域名。因此，购买一个耳熟能详的域名，然后设置 DNS 解析，使得此域名最终指向你的个人网站。

域名的购买方式有很多，通过各大服务商购买都可以，需要注意的是，购买域名之前必须通过实名认证和备案，这个时间可能需要花上点时间，我个人大概等待了 1 天左右。

阿里云域名购买：[域名注册-阿里云](https://www.alibabacloud.com/zh/domain)

打开 **Setting——Pages**，请务必保证有第一行最下面已经说明您的网页已经可以使用了

![](../attachment/Pasted%20image%2020220911223544.png)
### 设置阿里云 DNS 云解析

打开云解析 DNS 控制台：[云解析 DNS](https://dns.console.aliyun.com/)，找到你刚买的域名，设置解析。

这里应当注意，需要添加两种主机记录，一种是@，一种是 WWW。

> 这里可以理解为：WWW 使得域名可以通过 www.xxxx.com 进行访问，@直接解析 xxxx.com，\*则为泛解析，可以访问 docs.xxxx.com

![](../attachment/Pasted%20image%2020220911224259.png)
### 设置 GitHub Pages 页面自定义域名

打开 **Setting——Pages——Custom Domain**，将自己的域名填入框内，保存后 GitHub 会检查 DNS 配置，由于云解析 DNS 有延迟，因此需要耐心等待一会。

![](../attachment/Pasted%20image%2020220911225130.png)
如果提示 DNS 检查通过，显示为绿色，则就可以通过域名进行访问了。

![](../attachment/Pasted%20image%2020220911225431.png)

## 3 本地调试的环境配置

为什么要本地调试？难道 GitHub 不是可以直接访问吗？

> GitHub 使用 jekyll 进行构建的时候，要求个人用户一个小时不能超过 10 次，因此如果你想实时看到你的改动，最好配置好本地环境方便查看。

### 安装 Homebrew

新版本的 mac 的 mac 可能版本低于 3.0，因此需要安装最新版本的 Homebrew

Gitee 上有一个一键安装 Homebrew 的脚本，并且可以一键替换镜像

```Shell
/bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh"
```

### 安装 rbenv 和 Ruby

M1 版本使用 RVM 安装的 Ruby 存在兼容性问题，因此通过 rbenv 安装，但是缺点是需要手动添加到环境变量中，不过也不麻烦。

```Shell
brew install rbenv ruby-build
```

使用 Homebrew 安装的 ruby 可能是 2.6 版本，无法兼容 ARM 架构。

因此使用 ruby 安装 ruby 3.0 版本，这一步可能有点慢，视网络情况而定，耐心等待一会。

```Shell
rbenv install 3.0.0
rbenv global 3.0.0
ruby -v
rbenv rehash
```

### 添加 Ruby 到环境变量

将 rbenv 初始化放入环境变量，一旦检测到 rbenv 路径变化，即可进行初始化

```
echo 'eval "$(rbenv init - zsh)"' >> ~/.zshrc
```

或者直接在命令行运行：

```shell
rbenv init -zsh
```

但是由于 macos 自带 2.6 的 ruby，指向的 ruby 可能不是 3.0 版本的，==需要根据上述安装的 ruby 的位置，手动添加到环境变量中==

```shell
echo 'export PATH="/usr/local/opt/ruby/bin:/usr/local/lib/ruby/gems/3.0.0/bin:$PATH"' >> ~/.zshrc
```

或者手动找到 ruby 3.0 的安装位置，手动添加到环境变量中

```shell
export PATH="/Users/cloudu/.rbenv/versions/3.0.0/bin:$PATH"
```

直到在命令行输入

```shell
$ ruby -v

ruby 3.0.0p0 (2020-12-25 revision 95aff21468) [arm64-darwin21]
```

### 安装 jekyll 和 bundle

安装 ruby 的时候，默认安装了 rubygem

```shell
sudo gem install --user-install bundler jekyll
```

### M1 额外的操作

更新 bundler，添加 webrick，并重建一切。

```shell
bundle update --bundler
bundle add webrick
bundle install --redownload
```

因为我不知道的原因，在很多项目里面 install 的时候是默认不添加 webrick 的，因此在 install 后，请务必要添加上 webrick。

### 测试一下

创建一个默认博客试一下

```shell
jekyll new my-awesome-site
cd my-awesome-site
```

输入以下命令运行

```shell
bundle exec jekyll serve
```

命令行显示如下内容即可成功

```shell
Auto-regeneration: enabled for '/Users/cloudu/Desktop/clouduh.github.io'
Server address: http://127.0.0.1:4000/huxblog-boilerplate/
Server running... press ctrl-c to stop.
```

此时，在浏览器访问(http://127.0.0.1:4000)可以了。

一般通过`bundle exec jekyll install`运行网页，运行时通过按动 Ctrl+C 来终止运行。

### Git 的安装

使用 Git 是确保你能及时把你的网页推到 GitHub 服务器上，如果你执意不学，也可以一遍一遍地通过网页上传。

通过 Homebrew 安装

```bash
$ brew install git
```

配置默认用户名和账户

```bash
git config user.name "CLOUDUH"
git config user.email "clouduh@outlook.com"
```

生成本地 SSH 文件

```bash
ssh-keygen -t rsa -C"CLOUDUH@clouduh@outlook.com"
enter
enter
```

生成的文件在一下路径中

```bash
\Users\cloudu\.ssh
```

将 SSH 倒入 GitHub 中

-   登录 GitHub
-   头像——Setting——SSH and GPG keys——SSH keys 栏——New SSH key
-   填写 Title，随你便
-   用记事本打开 id_rsa.pub，复制所有内容到 Key 中
-   点击 Add SSH key
-   打开 cmd 输入`ssh -T git@github.com`

![](../attachment/Pasted%20image%2020220911232014.png)

## 4 个性化设置

这里先作为一个 0 基础的小白谈谈对于 jekyll 的理解。

在进行模版改动的任何操作之前，必须要整体的看完一边 jekyll 的官方文档，我有很多不懂的地方都是后来发现文档中已经写的明明白白了：[Jekyll](https://jekyllcn.com/)

### Jekyll 结构

一个 Jekyll 的项目文件可以主要分为下面的几个部分（纯属我自己的理解）

- \_config 文件：写入最主要的配置
- \_posts 文件夹：存放所有的文章，必须以 22-09-08-xxxx.md 的格式命名
- \_layouts 文件夹：存放所有的布局（不包括样式）
- \_includes 文件夹：常常存放例如导航栏等小 html 部件
- \_site 文件夹：可以视为缓存文件
- css 和 less 文件夹：less 可以用一种更简单的方式定义样式，然后通过 grunt 生成 ccs 文件。
- index 文件：首页的 html 样式
- pages 文件夹：存放所有的子页面，可以是 html 和 md 格式

### 个性化原则

作为一个零基础的小白，走过两天，我觉得应该这样开始学习比较好：

- 先修改_config 文件，至少先让这个网页属于自己
- 先试试增加和删除 pages 中的内容，了解每段代码的意义
- 再试试修改_layout 的布局，了解 layout 的层级结构（有的模版是嵌套的）
- 最后再尝试学习 css 和 less 的知识，进行更高级的个性化（我还没到这一步）