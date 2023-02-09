# coding=utf-8
import re
import ast
from setuptools import setup, find_packages
from os.path import dirname, join, abspath
import setuptools
from pyutilb.util import *

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# 读元数据：author/version/description
meta = read_init_file_meta('m3u8dwn/__init__.py')

# 读依赖
with open('requirements.txt', 'rb') as f:
    text = f.read().decode('utf-8')
    text = text.replace(' ', '') # 去掉空格
    requires = text.split('\n')

setup(
    name='m3u8dwn',
    version=meta['version'],
    url='https://github.com/shigebeyond/m3u8dwn',
    license='BSD',
    author=meta['author'],
    author_email='772910474@qq.com',
    description=meta['description'],
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.6",
    install_requires=requires,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Operating System :: POSIX :: Linux",
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    # 把python中的函数自动生成为一个可执行的脚本
    entry_points={
       'console_scripts': [
           'm3u8dwn=m3u8dwn.boot:main',  # 格式为'命令名 = 模块名:函数名'
       ]
    },
)
