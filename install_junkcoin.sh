#!/bin/bash

# 脚本说明
echo "正在安装和配置 Junkcoin 节点..."

# 更新系统
sudo apt-get update
sudo apt-get upgrade -y

# 克隆 Junkcoin 仓库
git clone https://github.com/JunkcoinCommunity/junkcoin
cd junkcoin || exit

# 安装依赖项
sudo apt-get install -y build-essential libtool autotools-dev automake pkg-config libssl-dev libevent-dev bsdmainutils \
    libboost-system-dev libboost-filesystem-dev libboost-chrono-dev libboost-program-options-dev libboost-test-dev \
    libboost-thread-dev libjpeg-dev libqt5gui5 libqt5core5a libqt5dbus5 qttools5-dev qttools5-dev-tools \
    libprotobuf-dev protobuf-compiler libqrencode-dev libdb5.3++-dev libdb5.3++ libdb5.3-dev \
    libzmq3-dev libminiupnpc-dev libcurl4-openssl-dev libncurses5-dev pkg-config automake yasm

# 开放 9771 端口
sudo ufw allow 9771

# 给予脚本执行权限
chmod +x autogen.sh
cd share || exit
chmod +x genbuild.sh
cd ..

# 运行自动生成脚本
./autogen.sh
./configure

# 编译
make -j $(nproc)
sudo make install

# 创建配置文件
mkdir -p ~/.junkcoin
cat <<EOL > ~/.junkcoin/junkcoin.conf
rpcuser=test
rpcpassword=test
dns=1
irc=1
listen=1
dnsseed=1
daemon=1
server=1
rpcport=9771
debug=1
addnode=159.89.85.93:9771
addnode=157.173.198.7:9771
addnode=72.5.43.135:9771
EOL

# 启动 Junkcoin 节点
junkcoind

# 克隆 CPU 矿工仓库并编译
git clone https://github.com/pooler/cpuminer.git
cd cpuminer || exit
./autogen.sh
./configure CFLAGS="-O3"
make

# 提示用户启动挖矿
echo "挖矿设置已完成。请使用以下命令启动挖矿："
echo "./minerd -a scrypt -o http://127.0.0.1:9771/ --coinbase-addr=你的钱包地址 -u test -p test"
