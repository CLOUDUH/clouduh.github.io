---
layout: post
title: "在 M1 Mac 上运行 ARM 架构的 MATLAB 2022b"
subtitle: "工科果粉喜大普奔"
date: 221124
author: "CLOUDUH"
header-img: /cloudu-oss.oss-cn-beijing.aliyuncs.com/blogimg/blog-bg.jpg
permalink: /post/221124
tags:
- Research
- Apple
---

# 在 M1 Mac 上运行 ARM 架构的 MATLAB 2022b

## Abstract

本文主要介绍了适用于M系列芯片（ARM架构）的Matlab 2022b Beta的特性，记录进行此版本的下载与安装，随后使用Matlab Benchmark和民间代码进行测试，对比Rosetta转译x86版本与ARM测试版本的性能。

> 重点是，这次或许真的可以好好的在M1上使用Matlab了。

## 1 ARM测试版介绍

Matlab于近日开启了Matlab 2022b Apple Silicon Beta版本的公开测试，这次适配了很多的原生工具包，在打开速度、运行速度以及兼容性上提升了不少。最重要的是，beta测试版是免费使用的，截止日期为2023年6月30日。

[R2022b Native Apple Silicon Platform Open Beta Installation - MATLAB & Simulink](https://ww2.mathworks.cn/support/apple-silicon-r2022b-beta.html)

### 1.1 可用产品

此测试版本中，以下的产品（工具箱/包）都可以正常使用：

-   MATLAB
-   Simulink
-   Signal Processing Toolbox
-   Statistics and Machine Learning Toolbox
-   Image Processing Toolbox
-   DSP System Toolbox
-   Parallel Computing Toolbox
-   Curve Fitting Toolbox
-   Symbolic Math Toolbox
-   Communications Toolbox
-   Control System Toolbox
-   Deep Learning Toolbox
-   5G Toolbox
-   LTE Toolbox
-   MATLAB Compiler
-   MATLAB Compiler SDK

### 1.2 限制

- 测试版本没有正式签名，因此使用时可能会报错。
- 附加组件管理器仍然不能使用，不过可以手动安装来实现。
- 适用于Python的MATLAB引擎API是不可用的。
- 公开测试版需要 Java 运行时环境 (JRE)。

相比于之前2022a beta版本什么都用不了的情况，这次2022b beta版本属实带来了不少的惊喜，很多基础的功能都可以正常使用了。

>  The MATLAB R2022a native Apple silicon platform open beta has the following limitations: **The open beta includes MATLAB only.** Simulink and toolboxes are not available.

## 2 下载与安装

官方开启了MATLAB R2022b针对于苹果芯片的公开测试，填写姓名和邮箱即可获取下载链接。

![](../attachment/Pasted%20image%2020221127231934.png)

> 实测是可以同时安装一个正式版和一个beta版本的。

### 2.1 安装运行环境JRE

公开测试版需要安装JRE才能正常打开程序，官方推荐了Amazon Corretto 8，选择`macOS aarch64`平台的版本进行下载和安装。

官方说明：[Amazon Corretto 8 Installation Instructions for macOS 10.10 or later - Amazon Corretto](https://docs.aws.amazon.com/corretto/latest/corretto-8-ug/macos-install.html?version=java-8-lts&os=macos&architecture=arm-64-bit&package=jdk#download-openjdk)

直接下载链接：[Amazon Corretto 8 for macOS aarch64 pkg](https://corretto.aws/downloads/latest/amazon-corretto-8-aarch64-macos-jdk.pkg)

根据安装器一步一步安装完成即可。

![](../attachment/Pasted%20image%2020221124154458.png)

在终端运行以下代码来检查是否安装成功，如果显示路径则证明安装成功：

```shell
/usr/libexec/java_home --verbose
```

（可选的）添加JRE至环境变量中：

```shell
export JAVA_HOME=/Library/Java/JavaVirtualMachines/amazon-corretto-8.jdk/Contents/Home
```

> 如何添加环境变量的操作不再赘述，自行google。

### 2.2 安装Matlab R2022b

下载链接：[下载 MATLAB、Simulink、Stateflow 和其他 MathWorks 产品](https://ww2.mathworks.cn/downloads/csd/AppleSiliconPlatformOpenBeta/MATLAB_R2022b_Beta_install.dmg) 

> 如果你无法打开此网页，请在点击第一章节的链接，填写邮箱后找到下载链接。

下载完成后，双击打开安装，拖拽至应用程序（Applications）

![](../attachment/Pasted%20image%2020221124155015.png)

### 2.3 成功运行

开放测试版没有经过公证。 macOS会将其标记为来自不明身份的开发者，因此可能打不开，按照官方的操作流程：

- 按住CTRL键，右键单击MATLAB_R2022b_beta.app
- 从上下文菜单中选择 "打开"
- 然后，在弹出的窗口中点击 "打开"，以启动MATLAB

![](../attachment/Pasted%20image%2020221124160935.png)

打开活动监视器看一下种类，是Apple无疑。

![](../attachment/Pasted%20image%2020221124160951.png)

## 3 ARM与Rosetta的性能对比

本章节使用ARM架构的Mac运行了两个不同的版本，进行了性能对比。

### 3.1 测试平台

设备：MacBook Pro M1 Pro 16GB + 512GB
版本：macOS 12.6 Monterey
ARM：Matlab R2022b Apple Silicon Open Beta
Rosetta： Matlab R2021b x64

> 实测Mac这两个可以共存，但是不要一起打开，为了方便区分我改了图标。

![](../attachment/Pasted%20image%2020221127233906.png)

### 3.2 Benchmark性能测试

Matlab 提供了官方的测试函数，只要在Matlab命令行窗口输入`bench`即可执行。

`bench()`函数将测量六个不同基准任务的执行时间，并将结果与几台基准计算机进行比较：返回包含测量的执行时间的 1×6 向量、显示基准计算机的执行时间、创建一个条形图，根据计算机的速度对其进行排序。

官方说明文档：[MATLAB bench - MathWorks 中国](https://ww2.mathworks.cn/help/matlab/ref/bench.html)

这里运行10次bench，取10次每个基准的最优解，测试结果如下：

```matlab
% 进行10圈bench测试(两个软件中运行）
Rosetta = bench(10)
ARM = bench(10)

% bench函数输出对比
Rosetta_min = min(Rosetta)
ARM_min = min(ARM)
------------------------------------------------------------
Rosetta_min =
    0.7665    0.2535    0.3134    0.5538    1.1266    0.9006
ARM_min =
    0.4757    0.1529    0.1466    0.2978    0.9582    0.7098
```

不同基准测试所有的时间，2022b ARM版本相比于2021b Rosetta转译版本，整体速度提升在50%以上。

```matlab
% bench各个基准速度提升(%)
Enhancement = 100 * ARM_min ./ Rosetta_min
------------------------------------------------------------
Enhancement = [54.7156, 48.2302, 44.4283, 25.1799, 61.8257, 75.2962]
```

运行得到的截图如下，可以看出2022b ARM要比2021b Rosetta快了接近50%以上。

![](../attachment/Pasted%20image%2020221124164845.png)

![](../attachment/Pasted%20image%2020221124160022.png)

### 3.3 民间矩阵性能测试

知乎上一段Matlab测试代码，使用各种cpu运行同一段matlab代码的用时比较，代码中考察了乘法、系数矩阵、逆矩阵、快速傅里叶、LU分解、QR分解、奇异值分解以及特征值等8种常用运算，感兴趣的可以点进去看一下。

[请问AMD锐龙5000系列在MATLAB下的表现？ - 知乎](https://www.zhihu.com/question/435741427/answer/1687421295)

> 由于使用版本不同，可比性较差，但是可以反应一定的问题。

```matlab
% Copyright [知乎用户uRMDp6](https://www.zhihu.com/people/uuu-51-75)

clear, clc
A = rand(3e3);
B = rand(3e3);
num = 3;
T = zeros(8,num);
for i = 1:num
    % Test1 乘法
    clc
    disp('^-------')
    disp(['第' sprintf('%4i',i) ' 轮乘法测试中...'])
    tic, X1 = A*B; T(1,i) = toc;
    % Test2 稀疏矩阵
    clc
    disp('-^------')
    disp(['第' sprintf('%4i',i) ' 轮稀疏矩阵测试中...'])
    tic, X2 = sparse(A); T(2,i) = toc;
    % Test3 逆矩阵
    clc
    disp('--^-----')
    disp(['第' sprintf('%4i',i) ' 轮逆矩阵测试中...'])
    tic, X3 = inv(A); T(3,i) = toc;
    % Test4 快速傅里叶
    clc
    disp('---^----')
    disp(['第' sprintf('%4i',i) ' 轮快速傅里叶测试中...'])
    tic, X4 = fft(A); T(4,i) = toc;
    % Test5 LU分解
    clc
    disp('----^---')
    disp(['第' sprintf('%4i',i) ' 轮LU分解测试中...'])
    tic, [L5,U5,P5] = lu(A); T(5,i) = toc;
    % Test6 QR分解
    clc
    disp('-----^--')
    disp(['第' sprintf('%4i',i) ' 轮QR分解测试中...'])
    tic, X6 = qr(A); T(6,i) = toc;
    % Test7 奇异值分解
    clc
    disp('------^-')
    disp(['第' sprintf('%4i',i) ' 轮奇异值分解测试中...'])
    tic, [U7,S7,V7] = svd(A); T(7,i) = toc;
    % Test8 特征值与特征向量
    clc
    disp('-------^')
    disp(['第' sprintf('%4i',i) ' 轮特征值与特征向量测试中...'])
    tic, [V8,D8] = eig(A); T(8,i) = toc;
end
clc
% 各项测试平均时间
t = sum(T,2)./num;
disp(['Multiplication :   ' sprintf('%6f',t(1))])
disp(['Sparse         :   ' sprintf('%6f',t(2))])
disp(['Inverse        :   ' sprintf('%6f',t(3))])
disp(['FFT            :   ' sprintf('%6f',t(4))])
disp(['LU             :   ' sprintf('%6f',t(5))])
disp(['QR             :   ' sprintf('%6f',t(6))])
disp(['SVD            :   ' sprintf('%6f',t(7))])
disp(['Eigen          :   ' sprintf('%6f',t(8))])
% Total
total = sum(t);
disp('----------------------------')
disp(['Total          :   ' sprintf('%6f',total)])
```

测试结果如下：

| Category       | Rosetta   | ARM       | Enhancement |
|----------------|-----------|-----------|-------------|
| Multiplication | 0.584282  | 0.263584  | 45.11%      |
| Sparse         | 0.025109  | 0.032099  | -78.22%     |
| Inverse        | 0.807738  | 0.332982  | 41.22%      |
| FFT            | 0.053224  | 0.026907  | 50.55%      |
| LU             | 0.25222   | 0.133889  | 53.08%      |
| QR             | 0.453977  | 0.877916  | -51.71%     |
| SVD            | 7.928892  | 5.016261  | 63.27%      |
| Eigen          | 19.114926 | 13.883716 | 72.63%      |
| Total          | 29.220369 | 20.567354 | 70.39%      |

可以看出总体有50%以上的提升，虽然仍然不能跟x86平台battle，但是目前来说已经足够使用了，可以参考上述链接评论区的数据或者我挑选出的几个数据。

```matlab
% AMD 5950X R2020b  @Falccm
Total : 5.774436

% Intel i5-10600KF  R2020b  @吴昊
Total : 14.645794

% Intel i7-7700HQ  @星星
Total : 22.004549

% AMD 5800H R2021a @余生不渡沧海
Total : 7.564641
```