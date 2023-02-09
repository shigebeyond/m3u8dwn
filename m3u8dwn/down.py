#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
下载m3u8视频，使用异步http client来优化m3u8_down3
1. 下载
https://blog.csdn.net/sinat_31062885/article/details/124608519
主要是思路： 读m3u8文件的每一行： 1 收集每行指定的分片文件 2 收集秘钥+加密方法 3 最后根据秘钥来解密分片文件，并合并

2. httpx库：强化版的 requests
https://zhuanlan.zhihu.com/p/400422455
'''

import m3u8
import os
import re
from Crypto.Cipher import AES
import glob
import time
import math
import hashlib
import asyncio
import httpx

timeout = 100
client = httpx.AsyncClient(verify=False, timeout=timeout) # 异步http client
loop = asyncio.get_event_loop() # 异步io线程池

async def close():
    loop.close()
    await client.aclose()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36"
}

# 正则表达判断是否为网站地址
def is_url(url):
    pattern = re.compile(r'^((https|http|ftp|rtsp|mms)?:\/\/)[^\s]+')
    m = pattern.search(url)
    if m is None:
        return False
    else:
        return True

# 使用m3u8库获取文件信息
def load_m3u8(url):
    # 使用m3u8库获取文件信息
    video = do_load_m3u8(url)
    # 本地址无数据，要重定向
    if len(video.segments) == 0:
        # 获得重定向地址
        if len(video.playlists) == 1:
            url = video.playlists[0].absolute_uri
            print('重定向m3u8地址: ' + url)
            video = do_load_m3u8(url)
        else:
            print("m3u8文件没有分片信息: " + url)
    return video

# 真正的加载m3u8
def do_load_m3u8(url):
    try:
        return m3u8.load(url, timeout=timeout)
    except Exception as e: # m3u8.load()不支持重定向
        print(f"直接加载m3u8报错: {e}")
        print(f"先下载m3u8后解析: {url}")
        # 支持重定向
        res = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        video = m3u8.loads(res.text, url)
        if video.base_uri == None:
            video.base_uri = url.rsplit("/", 1)[0] + "/"
        return video

# 获取密钥
def get_key(keystr, url):
    keyinfo = str(keystr)
    method_pos = keyinfo.find('METHOD')
    comma_pos = keyinfo.find(",")
    method = keyinfo[method_pos:comma_pos].split('=')[1]
    uri_pos = keyinfo.find("URI")
    quotation_mark_pos = keyinfo.rfind('"')
    key_url = keyinfo[uri_pos:quotation_mark_pos].split('"')[1]
    if is_url(key_url) == False:
        key_url = url.rsplit("/", 1)[0] + "/" + key_url
    res = httpx.get(key_url, headers=headers)
    key = res.content
    print('解析key: ', method, key)
    # print(key.decode('utf-8'))
    return method, key

# 构建aes加密器
def build_aes(url, video):
    aes = None
    if video.keys and video.keys[0] is not None:
        method, key = get_key(video.keys[0], url)  # 秘钥
        aes = AES.new(key, AES.MODE_CBC, key)  # aes加密器
    return aes

# 获得ts分片文件存储的子目录 = m3u8 url的hash
def get_ts_subdir(url):
    m = hashlib.md5(url.encode(encoding='utf-8'))
    return m.hexdigest()  # 转化为16进制

# 下载ts分片文件 -- 异步下载，提高并发下载能力
# :param down_url ts文件地址
# :param url *.m3u8文件地址
# :param down_path 下载地址
# :param aes aes加密器，为null则不加密
async def download_ts(down_url, url, down_path, aes):
    # 文件名
    if is_url(down_url) == False:
        filename = down_url
        down_url = url.rsplit("/", 1)[0] + "/" + down_url
    else:
        filename = down_url.rsplit("/", 1)[1]

    # 文件路径
    down_ts_path = down_path + "/" + filename
    # 检查是否下载过了
    if os.path.exists(down_ts_path):
        print(f'已下载过{filename}, 跳过')
        return

    print(f'开始下载{filename}')
    #res = await client.get(down_url, headers=headers)
    # res = client.stream('GET', down_url, headers=headers) # 流式处理 -- 异步的，不能同步调用
    try:
        async with client.stream('GET', down_url, headers=headers) as res:
            print(f'结束下载{filename}')
            if aes != None:
                print(f'解密并保存{filename}')
            else:
                print(f'保存{filename}')
            with open(down_ts_path, "wb+") as file:
                #for chunk in res.iter_content(chunk_size=1024):
                async for chunk in res.aiter_bytes(): # httpx的流式响应
                    if chunk:
                        if aes != None:
                            chunk = aes.decrypt(chunk)
                        file.write(chunk)
    except Exception as e:
        print(f"下载{down_url}失败，需重新下载: {e}")
        # 删除旧文件, 可能只下载了一半
        if os.path.exists(down_ts_path):
            os.remove(down_ts_path)


# 合并ts文件
# dest_file:合成文件名
# source_path:ts文件目录
# ts_list:文件列表
# delete:合成结束是否删除ts文件
def merge_to_mp4(dest_file, down_path, ts_list, delete=False):
    files = glob.glob(down_path + '/*.ts')
    if len(files) != len(ts_list):
        raise Exception("文件不完整！")

    print(f'合并到{dest_file}')
    with open(down_path + "/../" + dest_file, 'wb') as fw:
        for file in ts_list:
            file = down_path + "/" + file
            with open(file, 'rb') as fr:
                fw.write(fr.read())
            if delete:
                os.remove(file)


# 下载，获取m3u8文件，读出ts链接，并写入文档
def down_m3u8_video(url, down_path, result_filename = 'result.mp4', concurrency = 200):
    # 检查是否下载过
    if result_filename != None and os.path.exists(down_path + '/' + result_filename):
        print(f"已下载过{result_filename}: 跳过")
        return

    # 准备下载目录
    # 每个电影建一个子目录，防止多个电影的ts分片文件混在一起
    down_path = down_path + '/' + get_ts_subdir(url)
    if not os.path.exists(down_path):
        os.mkdir(down_path)

    # 1 加载m3u8
    video = load_m3u8(url)

    # 2 构建aes加密器，为null则不加密
    aes = build_aes(url, video)

    # 3 记录ts文件名，用于指导合并
    ts_list = []
    for seg in video.segments:
        if is_url(seg.uri):
            ts_list.append(seg.uri.rsplit("/", 1)[1])
        else:
            ts_list.append(seg.uri)

    # 4 下载
    n = len(video.segments)
    print(f"要下载 {n} 个ts分片文件")
    begin = time.time()

    # bug: 由于分片太多，全部并发下载的话，会导致后端处理不过来，导致很多请求中断，只下载了一半
    # 旧代码: batch_download_ts(video.segments, url, down_path, aes)
    # fix: 每次只并发200分片，见参数concurrency
    round = math.ceil(n / concurrency)
    print(f"分{round}批下载,每批并发下载{concurrency}个分片")
    for start in range(0, n, concurrency):
        print(f"第{int(start/concurrency)+1}批下载")
        end = min(start + concurrency, n)
        batch_download_ts(video.segments[start:end], url, down_path, aes)

    # 4 合并ts文件
    merge_to_mp4(result_filename, down_path, ts_list, True)

    times = time.time() - begin  # 记录完成时间
    print(f"下载耗时: {times} s")

# 批量异步下载ts文件，并等待下载完成
# :param down_url ts文件地址
# :param url *.m3u8文件地址
# :param down_path 下载地址
# :param aes aes加密器，为null则不加密
def batch_download_ts(segs, url, down_path, aes):
    tasks = []  # 下载任务
    for seg in segs:
        # 启动下载任务
        tasks.append(download_ts(seg.uri, url, down_path, aes))
    # 等待下载任务执行完成
    loop.run_until_complete(asyncio.wait(tasks))


# 解析网页中的m3u8 url
def parse_m3u8_url(page_url, file = None):
    print("解析网页中的m3u8 url: " + page_url)
    # 加载网页
    res = httpx.get(page_url, headers=headers)
    html = res.content.decode("utf-8")

    # 解析电影名=网页标签
    if file == None:
        m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if m == None:
            file = 'result.mp4'
        else:
            file = m.group(1) + '.mp4'

    # 从网页中解析 m3u8 地址
    m = re.search(r"https:\\?/\\?/([^/]+)\\?/[^\.]+\.m3u8", html, re.IGNORECASE)
    if m == None:
        print("没有解析出m3u8地址")
        return
    m3u8_url = m.group().replace('\/', '/')
    print('解析出m3u8 url为 ' + m3u8_url)

    return m3u8_url, file

if __name__ == '__main__':
    try:
        url = "https://hot.qqaku.com/20230122/Pqr6TSpb/1000kb/hls/index.m3u8?_t=1675844302284"
        down_path = "/home/shi/Downloads/video" # 下载路径
        down_m3u8_video(url, down_path)
    finally:
        # 关闭资源
        close()
