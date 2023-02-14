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
from pyutilb import log
from asyncio import coroutines
from urllib.parse import urlparse

timeout = 50
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
            log.debug('重定向m3u8地址: ' + url)
            video = do_load_m3u8(url)
        else:
            log.debug("m3u8文件没有分片信息: " + url)
    return video

# 真正的加载m3u8
def do_load_m3u8(url):
    try:
        return m3u8.load(url, timeout=timeout)
    except Exception as e: # m3u8.load()不支持重定向
        log.error(f"直接加载m3u8报错: {e}")
        log.debug(f"先下载m3u8后解析: {url}")
        # 支持重定向
        res = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        check_response(res)
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
        key_url = fix_ts_url(key_url, url)
    res = httpx.get(key_url, headers=headers)
    check_response(res)
    key = res.content
    log.debug('解析method=%s, key=%s', method, key.decode('utf-8'))
    return method, key

# 检查响应
def check_response(res):
    if res.status_code != 200:
        url = res.request.url
        raise Exception(f'请求失败, 响应码为{res.status_code}, url为 {url}')

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

# 从下载ts地址中获得文件名
# :param down_url ts地址，可能是绝对地址，也可能是相对地址，也可能仅是文件名
def get_ts_filename(ts_url):
    # 1 url
    if is_url(ts_url):
        return ts_url.rsplit("/", 1)[1]

    # 2 相对地址：目录+文件名, 如/a/b/c.ts
    if '/' in ts_url: # 相对uri
        return ts_url.split("/")[-1]

    # 3 纯文件名, 如c.ts
    return ts_url

# 获得ts文件名顺序，用于指导有序合并
def get_ts_list(video):
    ts_list = []
    for seg in video.segments:
        filename = get_ts_filename(seg.uri) # ts文件名
        ts_list.append(filename)
    return ts_list

# 获得要下载的分片，去掉下载过的
def get_downing_segs(video, down_path):
    segs = [] # 去掉下载过的分片
    for seg in video.segments:
        filename = get_ts_filename(seg.uri)
        # 去掉下载过的分片
        if not os.path.exists(down_path + "/" + filename):
            segs.append(seg)
    return segs

# 修正ts下载地址
# :param down_url ts地址，可能是绝对地址，也可能是相对地址，也可能仅是文件名
def fix_ts_url(ts_url, m3u8_url):
    # 1 url
    if is_url(ts_url):
        return ts_url

    # 2 相对地址：目录+文件名, 如/a/b/c.ts
    if '/' in ts_url:
        # 获得域名
        parts = urlparse(m3u8_url)
        domain = parts.scheme + '://' + parts.netloc
        # 域名+相对uri
        return domain + ts_url

    # 3 纯文件名, 如c.ts
    return m3u8_url.rsplit("/", 1)[0] + "/" + ts_url

# 下载ts分片文件 -- 异步下载，提高并发下载能力
# :param down_url ts文件地址
# :param url m3u8文件地址
# :param down_path 下载地址
# :param aes aes加密器，为null则不加密
async def download_ts(ts_url, m3u8_url, down_path, aes):
    # 文件名
    filename = get_ts_filename(ts_url)
    # 修正下载地址
    ts_url = fix_ts_url(ts_url, m3u8_url)

    # 文件路径
    down_ts_path = down_path + "/" + filename
    # 检查是否下载过了
    if os.path.exists(down_ts_path):
        log.debug(f'已下载过{filename}, 跳过')
        return

    log.debug(f'开始下载{filename}: {ts_url}')
    #res = await client.get(down_url, headers=headers)
    # res = client.stream('GET', down_url, headers=headers) # 流式处理 -- 异步的，不能同步调用
    try:
        async with client.stream('GET', ts_url, headers=headers) as res:
            check_response(res)
            if aes != None:
                log.debug(f'结束下载+解密{filename}')
            else:
                log.debug(f'结束下载{filename}')
            with open(down_ts_path, "wb+") as file:
                #for chunk in res.iter_content(chunk_size=1024):
                async for chunk in res.aiter_bytes(): # httpx的流式响应
                    if chunk:
                        if aes != None:
                            chunk = fill_ciphertext(chunk) # 填充密文长度为16的倍数
                            chunk = aes.decrypt(chunk)
                        file.write(chunk)
    except Exception as e:
        log.error(f"下载{ts_url}失败，需重新下载: {e}")
        # 删除旧文件, 可能只下载了一半
        if os.path.exists(down_ts_path):
            os.remove(down_ts_path)

# 密文长度不为16的倍数，则添加b"0"直到长度为16的倍数
# aes-128加密算法要求
def fill_ciphertext(chunk):
    pad = 16 - len(chunk) % 16
    if pad == 0:
        return chunk
    return chunk + pad * b"0"

# 合并ts文件
# dest_file:合成文件名
# source_path:ts文件目录
# ts_list:文件列表，用于指导有序合并
# delete:合成结束是否删除ts文件
def merge_to_mp4(dest_file, down_path, ts_list, delete=False):
    if not check_down_ts_done(down_path, len(ts_list)):
        raise Exception("ts分片文件未下载完")

    log.debug(f'合并到{dest_file}')
    dest_file = down_path + "/../" + dest_file
    with open(dest_file, 'wb') as fw:
        # 按顺序合并ts，不然合并的视频是错乱的
        for ts_file in ts_list:
            ts_file = down_path + "/" + ts_file
            with open(ts_file, 'rb') as fr:
                fw.write(fr.read())
            if delete: # 删ts文件
                os.remove(ts_file)

    if delete and os.path.exists(dest_file): # 删ts目录
        os.rmdir(down_path)

# 检查是否ts下载完成
def check_down_ts_done(down_path, ts_num):
    files = glob.glob(down_path + '/*.ts')
    return len(files) == ts_num

# 下载，获取m3u8文件，读出ts链接，并写入文档
# :param concurrency 并发下载数
# :param retries 尝试次数
def down_m3u8_video(url, down_path, result_filename = 'result.mp4', concurrency = 200, tries = 2):
    # 检查是否下载过
    if result_filename != None and os.path.exists(down_path + '/' + result_filename):
        log.debug(f"已下载过{result_filename}: 跳过")
        return

    log.debug(f"开始下载{result_filename}")
    # 准备下载目录
    # 每个电影建一个子目录，防止多个电影的ts分片文件混在一起
    down_path = down_path + '/' + get_ts_subdir(url)
    if not os.path.exists(down_path):
        os.mkdir(down_path)

    # 1 加载m3u8
    video = load_m3u8(url)
    na = len(video.segments)
    if na == 0:
        log.error(f"ts分片数为0，无法下载")
        return

    # 2 构建aes加密器，为null则不加密
    aes = build_aes(url, video)

    # 3 记录ts文件名顺序，用于指导有序合并
    ts_list = get_ts_list(video)

    # 4 下载
    begin = time.time()

    # bug: 由于分片太多，全部并发下载的话，会导致后端处理不过来，导致很多请求中断，只下载了一半
    # 旧代码: batch_download_ts(segs, url, down_path, aes)
    # fix: 每次只并发200分片，见参数concurrency
    while tries > 0 and not check_down_ts_done(down_path, na): # 如果ts文件未下载完，则重试，最多试2次
        tries -= 1
        segs = get_downing_segs(video, down_path)
        n = len(segs)  # 要下载的ts分片数
        round = math.ceil(n / concurrency)
        log.debug(f"第{tries}次尝试: 要下载{n}个ts分片文件, 分{round}批下载, 每批并发下载{concurrency}个分片")
        for start in range(0, n, concurrency):
            log.debug(f"第{int(start/concurrency)+1}批下载")
            end = min(start + concurrency, n)
            batch_download_ts(segs[start:end], url, down_path, aes)

    # 5 合并ts文件
    merge_to_mp4(result_filename, down_path, ts_list, True)

    times = time.time() - begin  # 记录完成时间
    log.debug(f"下载耗时: {times} s")

# 批量异步下载ts文件，并等待下载完成
# :param down_url ts文件地址
# :param url *.m3u8文件地址
# :param down_path 下载地址
# :param aes aes加密器，为null则不加密
def batch_download_ts(segs, url, down_path, aes):
    tasks = []  # 下载任务
    for seg in segs:
        # 启动下载任务
        task = download_ts(seg.uri, url, down_path, aes)
        # 有可能是已下载过的任务，就不是协程，因此需要先判断
        if coroutines.iscoroutine(task):
            tasks.append(task)
    if len(tasks) > 0:
        # 等待下载任务执行完成
        loop.run_until_complete(asyncio.wait(tasks))

# 解析网页中的m3u8 url
def parse_m3u8_url(page_url, file = None):
    log.debug("解析网页中的m3u8 url: " + page_url)
    # 加载网页
    res = httpx.get(page_url, headers=headers)
    check_response(res)
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
        log.error("没有解析出m3u8地址")
        return
    m3u8_url = m.group().replace('\/', '/')
    log.debug('解析出m3u8 url为 ' + m3u8_url)

    return m3u8_url, file

if __name__ == '__main__':
    try:
        url = "https://hot.qqaku.com/20230122/Pqr6TSpb/1000kb/hls/index.m3u8?_t=1675844302284"
        down_path = "/home/shi/Downloads/video" # 下载路径
        down_m3u8_video(url, down_path)
    finally:
        # 关闭资源
        close()
