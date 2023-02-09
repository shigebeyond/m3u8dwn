[GitHub](https://github.com/shigebeyond/m3u8dwn) | [Gitee](https://gitee.com/shigebeyond/m3u8dwn)

# m3u8dwn - m3u8视频下载器
## 概述
python实现的m3u8视频多协程下载器，支持多个ts切片文件同时下载；
使用httpx异步请求库+协程来实现，下载速度嗖嗖的。

## 使用
### 1. 安装
```
pip install m3u8dwn
```

### 2. 下载命令
2.1 命令格式
```
m3u8dwn -m m3u8地址 -p 内含m3u8地址的网页地址 -o 输出目录 [-f 下载文件名] [-c 并发下载数] 
```

其中选项
`-m`与`-p`是二选一;
`-m`为 m3u8 url;
`-p`为 网页url, 网页内容需包含m3u8 url, 同时其标题可作为输出文件名;
`-o`可省, 为输出目录, 默认为当前目录;
`-f`可省, 为输出文件名, 默认是网页标题.mp4或result.mp4;
`-c`可省, 默认并发下载数为200

2.2 例子
```
m3u8dwn -m http://xxx.com/yyy.m3u8
m3u8dwn -m http://xxx.com/yyy.m3u8 -o /home/shi/video
m3u8dwn -p http://xxx.com/yyy.html -o /home/shi/video
```