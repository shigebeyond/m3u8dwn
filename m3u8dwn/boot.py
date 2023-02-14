#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import time
from optparse import OptionParser
from pyutilb.util import read_init_file_meta
from pyutilb import log
from m3u8dwn.down import down_m3u8_video, parse_m3u8_url

# 解析命令的选项与参数
# :param name 命令名
# :param version 版本
# :return 命令选项+参数
def parse_cmd(name, version):
    # py文件外的参数
    args = sys.argv[1:]

    usage = f'Usage: {name} [options...]'
    optParser = OptionParser(usage)

    # 添加选项规则
    # optParser.add_option("-h", "--help", dest="help", action="store_true") # 默认自带help
    optParser.add_option('-v', '--version', dest='version', action="store_true", help='Show version number and quit')
    optParser.add_option("-m", "--m3u8", dest="m3u8", type="string", help="m3u8 url or file path")
    optParser.add_option("-p", "--p", dest="webpage", type="string", help="webpage, which contains m3u8 url") # 网页，包含m3u8 url
    optParser.add_option("-r", "--r", dest="webpagerange", type="string", help="webpagerange, which contains range expression(eg. [1,3]), represents multiple webpage") # 多个网页，包含范围表达式，每个值代表一个网址
    optParser.add_option("-o", "--o", dest="output", type="string", help="output directory") # 输出目录, 默认为当前目录
    optParser.add_option("-f", "--f", dest="filename", type="string", help="output filename") # 输出文件名, 默认是网页标题.mp4或result.mp4
    optParser.add_option("-c", "--c", dest="concurrency", type="string", help="download concurrency, default 200") # 并发数，就是单批次并发下载ts分片数
    optParser.add_option("-t", "--t", dest="tries", type="string", help="max try times, default 2") # 重试次数

    # 解析选项
    option, args = optParser.parse_args(args)

    # 输出帮助文档 -- 默认自带help
    # if option.help == True:
    #     print(usage)
    #     sys.exit(1)

    # 输出版本
    if option.version == True:
        print(version)
        sys.exit(1)

    return option, args

def main():
    # 读元数据：author/version/description
    dir = os.path.dirname(__file__)
    meta = read_init_file_meta(dir + os.sep + '__init__.py')
    # 解析命令
    option, args = parse_cmd('m3u8dwn', meta['version'])

    # 获得输出目录
    output = option.output
    if output == None:
        #output = os.path.abspath('.') # 当前目录
        output = os.getcwd() # 当前目录
    elif not os.path.isabs(output):
        output = os.path.abspath(output) # 绝对路径
    log.debug(f"下载目录为: {output}")

    # 获得并发数，就是单批次并发下载ts分片数
    concurrency = option.concurrency
    if concurrency == None:
        concurrency = 200
    concurrency = int(concurrency)

    # 获得尝试次数
    tries = option.tries
    if tries == None:
        tries = 2
    tries = int(tries)

    # 1 多网页
    if option.webpagerange != None:
        url = option.webpagerange
        # 找到范围表达式，如[1,3]
        mat = re.search(r'\[(\d+):(\d+)\]', url)
        if mat == None:
            raise Exception("ps选项没有指定范围表达式")
        start = int(mat.group(1))
        end = int(mat.group(2))
        log.debug(f"要下载{end-start+1}个网页的视频")
        for i in range(start, end+1):
            real_url = url.replace(mat.group(), str(i))
            # 解析网页中的m3u8 url
            m3u8_url, file = parse_m3u8_url(real_url)
            # 下载m3u8视频
            down_m3u8_video(m3u8_url, output, file, concurrency, tries)
            log.debug("----------\n 准备下载下一个网页视频 ")
            time.sleep(5)
        return

    # 2 单网页或单m3u8
    # 解析网页中的m3u8 url
    m3u8_url = option.m3u8
    file = 'result.mp4'
    if m3u8_url == None and option.webpage != None:
        m3u8_url, file = parse_m3u8_url(option.webpage)

    # 下载m3u8视频
    down_m3u8_video(m3u8_url, output, file, concurrency, tries)

if __name__ == '__main__':
    main()
