#!/bin/sh
# 安装
#pip3 install --user --upgrade setuptools wheel twine

# 清理
echo '清理旧包'
rm -rf dist/*

# 打包
echo '打新包'
python3 setup.py sdist bdist_wheel

# 上传
echo '上传新包'
twine upload dist/*