#!/bin/sh
echo '卸载'
pip3 uninstall m3u8dwn -y

echo '清理旧包'
rm -rf dist/*

echo '打新包'
python3 setup.py sdist bdist_wheel

echo '安装到本地'
pip3 install dist/*.whl